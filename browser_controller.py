"""
浏览器控制模块 - 使用Patchright通过CDP连接真实小红书页面并截图
"""
import os
import asyncio
import subprocess
import time
import http.client
import json
import threading
import shutil
from patchright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError
from config import Config

class BrowserController:
    _start_lock = threading.Lock()
    _init_lock = asyncio.Lock() # 这是一个类属性，所有实例共享，但其实只有一个实例
    
    def __init__(self):
        self._local = threading.local()
        self.user_data_dir = os.path.join(os.path.dirname(__file__), "browser_data")
        os.makedirs(self.user_data_dir, exist_ok=True)
        
        self.chrome_path = self._resolve_chrome_path()
            
        self.debug_port = 9222
        self.chrome_process = None

    def _resolve_chrome_path(self) -> str:
        """解析 Chrome/Chromium 路径，允许通过 CHROME_PATH 环境变量覆盖。"""
        if Config.CHROME_PATH:
            return Config.CHROME_PATH

        import platform
        system = platform.system()
        if system == "Darwin":
            return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

        if system == "Windows":
            paths = [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
            ]
            for path in paths:
                if os.path.exists(path):
                    return path
            return "chrome.exe"

        for candidate in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            if shutil.which(candidate):
                return candidate
        return "google-chrome"

    @property
    def loop(self):
        return getattr(self._local, 'loop', None)

    @loop.setter
    def loop(self, value):
        self._local.loop = value

    @property
    def playwright(self):
        return getattr(self._local, 'playwright', None)

    @playwright.setter
    def playwright(self, value):
        self._local.playwright = value

    @property
    def browser(self):
        return getattr(self._local, 'browser', None)

    @browser.setter
    def browser(self, value):
        self._local.browser = value

    @property
    def context(self):
        return getattr(self._local, 'context', None)

    @context.setter
    def context(self, value):
        self._local.context = value
    
    def _is_port_in_use(self, port: int) -> bool:
        """检查调试端口是否已被占用（判断Chrome是否已在调试模式运行）"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    def _start_real_chrome(self) -> str:
        """启动真实的Chrome实例，并获取CDP WebSocket URL"""
        with self._start_lock:
            if not self._is_port_in_use(self.debug_port):
                print("正在启动真实Chrome浏览器...")
                # 确保启动的Chrome有独立的user_data_dir，这样开端口才会被允许
                cmd = [
                    self.chrome_path,
                    f"--remote-debugging-port={self.debug_port}",
                    f"--user-data-dir={self.user_data_dir}",
                    "--no-first-run",
                    "--no-default-browser-check"
                ]
                if Config.BROWSER_HEADLESS:
                    cmd.extend(["--headless=new", "--disable-gpu", "--no-sandbox"])
                self.chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # 等待端口启动
                for _ in range(10):
                    if self._is_port_in_use(self.debug_port):
                        break
                    time.sleep(0.5)
        
        # 通过 http.client 手动获取 WebSocket URL (规避Patchright自带发现在尾部加斜杠导致400的问题)
        ws_url = None
        for _ in range(5):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.debug_port, timeout=2)
                conn.request("GET", "/json/version")
                res = conn.getresponse()
                if res.status == 200:
                    data = json.loads(res.read())
                    ws_url = data.get('webSocketDebuggerUrl')
                    if ws_url:
                        break
            except Exception as e:
                pass
            time.sleep(0.5)
            
        if not ws_url:
            raise Exception("无法从真实Chrome获取WebSocket Debugger URL，请确保浏览器已完全退出后重试。")
            
        return ws_url

    async def init_browser(self):
        """初始化CDP连接 (线程安全版)"""
        current_loop = asyncio.get_event_loop()
        
        # 加锁防止并发初始化
        async with self._init_lock:
            # 如果当前线程的 loop 已变，则强制重连
            if self.loop != current_loop:
                print(f"[{threading.current_thread().name}] 检测到新的 EventLoop，重置连接状态...")
                self.playwright = None
                self.browser = None
                self.context = None
                self.loop = current_loop

            if self.playwright is None:
                print(f"[{threading.current_thread().name}] 启动 Playwright...")
                self.playwright = await async_playwright().start()
            
            # 检查当前线程的 browser 连接是否有效
            if self.browser:
                try:
                    await self.browser.version()
                    return # 连接有效
                except:
                    print(f"[{threading.current_thread().name}] ⚠️ 浏览器连接已断开，正在尝试重连...")
                    self.browser = None
                    self.context = None

            if self.browser is None:
                ws_url = self._start_real_chrome()
                print(f"[{threading.current_thread().name}] 连接 CDP: {ws_url}")
                # 使用connect_over_cdp接管现有Chrome
                self.browser = await self.playwright.chromium.connect_over_cdp(ws_url, is_local=False)
                # CDP模式下直接使用第一个上下文
                self.context = self.browser.contexts[0]
    
    async def close_browser(self):
        """
        关闭浏览器连接（但不杀掉浏览器进程）
        学习参考项目逻辑：只关闭连接，保持浏览器进程在后台运行
        """
        if self.browser:
            # 注意：在 Playwright 的 connect_over_cdp 中，browser.close() 可能会尝试关闭远程浏览器
            # 为了保持浏览器不关闭，我们只清理引用，不调用 browser.close()
            # 或者只关闭我们打开的 context/pages
            print("正在断开浏览器连接（保持浏览器进程运行）...")
            self.browser = None
            self.context = None
        
        # 保持 playwright 运行，避免频繁启停
        # if self.playwright:
        #     await self.playwright.stop()
        #     self.playwright = None
            
        # 注意：此处不主动kill chrome主进程，让用户环境保持，需要时由app.py清理
    
    async def get_page(self) -> Page:
        """获取一个新页面，供data_collector复用"""
        await self.init_browser()
        # 直接在原上下文新建窗口，不使用new_context
        # 也绝不使用stealth插件，以免引发网络异常覆盖navigator
        page = await self.context.new_page()
        return page

    async def _emit_step(self, step_callback, message: str) -> None:
        if not step_callback:
            return
        try:
            result = step_callback(message)
            if asyncio.iscoroutine(result):
                await result
        except:
            pass
    
    async def capture_homepage(self, url: str, screenshot_path: str, platform: str = "xhs", step_callback=None) -> dict:
        """
        打开博主主页并截图
        """
        await self._emit_step(step_callback, "初始化浏览器")
        await self.init_browser()
        page = await self.context.new_page()
        
        try:
            await self._emit_step(step_callback, "打开链接")
            await page.set_viewport_size({"width": 1280, "height": 900})
            # 访问页面。小红书会持续发后台请求，等待 networkidle 容易误超时。
            await page.goto(url, timeout=Config.PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeoutError:
                pass
            
            # 等待页面加载完成
            await asyncio.sleep(2)

            if platform == "douyin":
                await self._emit_step(step_callback, "检查抖音登录状态")
            else:
                await self._emit_step(step_callback, "关闭登录弹窗")
                closed_login_modal = await self._close_login_modal(page)
                if closed_login_modal:
                    await self._emit_step(step_callback, "登录弹窗已关闭")
                else:
                    await self._emit_step(step_callback, "未发现登录弹窗")
            
            await self._emit_step(step_callback, "检查页面状态")
            # 1. 检查可见页面状态。不要用完整HTML，脚本里会包含各种错误文案模板，容易误判。
            title = await page.title()
            try:
                body_text = await page.evaluate("document.body ? document.body.innerText : ''")
            except:
                body_text = ""
            page_url = page.url
            page_text = f"{title} {body_text}"

            if platform == "douyin" and self._is_douyin_login_required(page_url, page_text):
                return {
                    "success": False,
                    "error": "需要登录抖音",
                    "need_login": True,
                    "screenshot_path": None
                }

            verification_keywords = ["扫码认证", "扫码验证", "安全验证", "身份验证", "请完成验证"]
            if any(kw in page_text for kw in verification_keywords):
                return {
                    "success": False,
                    "error": "需要扫码认证",
                    "need_login": True,
                    "screenshot_path": None
                }

            rate_limit_keywords = [
                "操作过于频繁", "访问频繁", "请求过于频繁", "请稍后再试", "稍后再试"
            ]
            if any(kw in page_text for kw in rate_limit_keywords):
                return {
                    "success": False,
                    "error": "操作过于频繁，请稍后再试",
                    "is_banned": False,
                    "need_login": False,
                    "screenshot_path": None
                }

            # 2. 检查是否为封禁/注销/不存在页面
            banned_keywords = [
                "404", "出错", "没有找到", "因相关法律法规",
                "账号已封禁", "该用户不存在", "用户未找到",
                "页面不存在", "内容不存在", "违规",
                "账号已注销", "账号注销", "用户已注销", "该账号已注销",
                "账号异常", "访问受限", "此账号已注销", "System Error"
            ]
            if any(kw in page_text for kw in banned_keywords):
                return {
                    "success": False,
                    "error": "账号已封禁或注销",
                    "is_banned": True,
                    "need_login": False,
                    "screenshot_path": None
                }

            # 只截页面顶部 1280x900 区域，不截长屏。
            await self._emit_step(step_callback, "截屏")
            await page.screenshot(
                path=screenshot_path,
                full_page=False,
                clip={"x": 0, "y": 0, "width": 1280, "height": 900}
            )
            await self._emit_step(step_callback, "截屏完成")
            
            title = await page.title()
            
            return {
                "success": True,
                "screenshot_path": screenshot_path,
                "page_title": title,
                "need_login": False
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "need_login": False,
                "screenshot_path": None
            }
        finally:
            await page.close()

    async def _close_login_modal(self, page: Page) -> bool:
        """关闭未登录访问时的小红书登录提示卡。"""
        closed = False

        close_selectors = [
            '[aria-label="关闭"]',
            '[title="关闭"]',
            'button:has-text("关闭")',
            'text="×"',
            'text="✕"',
            'text="X"',
            '[class*="close"]',
        ]

        for selector in close_selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() and await locator.is_visible(timeout=300):
                    await locator.click(timeout=800)
                    closed = True
                    await asyncio.sleep(0.5)
                    break
            except:
                pass

        if not closed:
            try:
                closed = await page.evaluate("""
                    () => {
                        const visible = (el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.visibility !== 'hidden'
                                && style.display !== 'none'
                                && rect.width > 0
                                && rect.height > 0;
                        };

                        const loginWords = ['登录', '手机号登录', '扫码登录', '验证码登录'];
                        const hasLoginText = loginWords.some((word) => document.body.innerText.includes(word));
                        if (!hasLoginText) return false;

                        const candidates = Array.from(document.querySelectorAll(
                            '[aria-label], [title], button, [role="button"], span, div, svg'
                        ));

                        const closeLike = candidates.filter((el) => {
                            if (!visible(el)) return false;
                            const label = [
                                el.getAttribute('aria-label') || '',
                                el.getAttribute('title') || '',
                                el.textContent || '',
                                el.className ? String(el.className) : ''
                            ].join(' ').trim().toLowerCase();

                            if (label === 'x' || label === '×' || label === '✕') return true;
                            return label.includes('关闭') || label.includes('close');
                        });

                        closeLike.sort((a, b) => {
                            const ar = a.getBoundingClientRect();
                            const br = b.getBoundingClientRect();
                            const ascore = ar.top + (window.innerWidth - ar.right);
                            const bscore = br.top + (window.innerWidth - br.right);
                            return ascore - bscore;
                        });

                        const target = closeLike[0];
                        if (!target) return false;
                        target.click();
                        return true;
                    }
                """)
                if closed:
                    await asyncio.sleep(0.5)
            except:
                pass

        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except:
            pass

        return closed

    def _is_douyin_login_required(self, page_url: str, page_text: str) -> bool:
        """判断抖音主页是否被登录页/登录弹窗拦住。"""
        if "login" in page_url:
            return True

        login_keywords = [
            "登录后可查看更多",
            "登录后",
            "请先登录",
            "扫码登录",
            "验证码登录",
            "手机号登录",
            "密码登录",
            "抖音登录",
            "登录抖音",
            "点击登录",
        ]
        return any(keyword in page_text for keyword in login_keywords)
    
    async def wait_for_login(self, timeout: int = 120) -> bool:
        """等待用户手动登录"""
        await self.init_browser()
        page = await self.context.new_page()
        
        try:
            print("正在打开小红书...")
            await page.goto("https://www.xiaohongshu.com/explore", timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            print("=" * 50)
            print("请在真实的浏览器窗口中扫码登录小红书...")
            print(f"等待登录中（{timeout}秒超时）...")
            print("=" * 50)
            
            # 轮询检查登录状态
            for i in range(timeout):
                await asyncio.sleep(1)
                try:
                    # 已登录的标志：URL不在登录页、页面包含用户相关元素
                    has_avatar = await page.query_selector('[class*="avatar"], [class*="user-info"], [class*="sidebar"]')
                    has_feed = await page.query_selector('[class*="feed"], [class*="note-item"], [class*="explore"]')
                    no_login_btn = (await page.query_selector('text="登录"')) is None
                    
                    if has_avatar or (has_feed and no_login_btn):
                        print("✅ 登录成功！")
                        return True
                        
                    if i > 0 and i % 15 == 0:
                        print(f"仍在等待登录... ({i}/{timeout}秒)")
                except:
                    pass
            
            print("❌ 登录超时")
            return False
        except Exception as e:
            print(f"登录流程出错: {e}")
            return False
        finally:
            await page.close()

# 全局浏览器控制器实例
browser_controller = BrowserController()

async def capture_homepage(url: str, screenshot_path: str, platform: str = "xhs", step_callback=None) -> dict:
    return await browser_controller.capture_homepage(url, screenshot_path, platform, step_callback)

async def init_browser():
    await browser_controller.init_browser()

async def close_browser():
    await browser_controller.close_browser()

async def wait_for_login(timeout: int = 120) -> bool:
    return await browser_controller.wait_for_login(timeout)
