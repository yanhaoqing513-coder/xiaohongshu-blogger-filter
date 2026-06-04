"""
数据采集模块 - 使用Playwright从小红书博主主页提取粉丝数据
不依赖OCR和AI，直接读取DOM元素
"""
import asyncio
import random
import re
import os
import logging
from playwright.async_api import Page
from config import Config


def _init_logger() -> logging.Logger:
    logger = logging.getLogger("collector")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    os.makedirs(Config.OUTPUT_FOLDER, exist_ok=True)
    log_path = os.path.join(Config.OUTPUT_FOLDER, "collector.log")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


logger = _init_logger()


class DataCollector:
    """博主主页数据采集器"""
    
    MAX_RETRIES = 2  # 失败时重试次数
    
    async def collect_profile(self, page: Page, url: str) -> dict:
        """
        访问博主主页并提取数据，失败时自动重试
        """
        last_error = ""
        for attempt in range(1, self.MAX_RETRIES + 1):
            result = await self._try_collect(page, url)
            
            # 成功 或 被封禁 → 直接返回，不重试
            if result.get("success"):
                return result
            
            # 需要登录 → 直接返回
            if result.get("need_login"):
                return result
            
            last_error = result.get("error", "未知错误")
            
            # 被封禁不重试
            if "封禁" in last_error or "不存在" in last_error:
                return result
            
            # 其他失败：重试
            if attempt < self.MAX_RETRIES:
                logger.warning(f"第{attempt}次采集失败({last_error})，等待后重试...")
                print(f"    ⚠️ 第{attempt}次采集失败({last_error})，等待后重试...")
                await asyncio.sleep(random.uniform(2, 4))
        
        logger.error(f"重试{self.MAX_RETRIES}次后仍失败: {last_error}")
        return {"success": False, "error": f"重试{self.MAX_RETRIES}次后仍失败: {last_error}"}
    
    async def _try_collect(self, page: Page, url: str) -> dict:
        """单次采集尝试"""
        # 1. 加载页面
        try:
            await page.goto(url, timeout=Config.PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass
            await asyncio.sleep(1)
        except Exception as e:
            # 页面加载出错 → 检查是否为封禁页面
            title = ""
            try:
                title = await page.title()
            except:
                pass
            if self._is_banned_page(title=title):
                return {"success": True, "fans": "无法获取", "status": "账号被封禁/注销"}
            return {"success": False, "error": f"页面加载异常: {str(e)}"}
        
        # 2. 检查封禁/不存在
        try:
            title = await page.title()
            content = await page.content()
            if self._is_banned_page(title=title, content=content):
                return {"success": True, "fans": "无法获取", "status": "账号被封禁/注销"}
        except:
            pass
        
        # 3. 检查是否需要登录
        try:
            page_url = page.url
            if "login" in page_url:
                return {"success": False, "error": "需要登录小红书", "need_login": True}
        except:
            pass
        
        # 4. 等待粉丝模块出现（仅支持指定结构）
        try:
            await page.wait_for_selector("span.shows", state="attached", timeout=10000)
        except Exception:
            pass

        # 4.1 诊断信息：统计 span.shows
        try:
            debug = await page.evaluate(r"""() => {
                const shows = [...document.querySelectorAll('span.shows')];
                return {
                    count: shows.length,
                    sample: shows.slice(0, 3).map(el => ({
                        text: (el.innerText || '').trim(),
                        prevText: (el.previousElementSibling && el.previousElementSibling.innerText || '').trim(),
                        prevClass: (el.previousElementSibling && el.previousElementSibling.className) || '',
                        parentHtml: el.parentElement ? el.parentElement.outerHTML.slice(0, 200) : ''
                    }))
                };
            }""")
        except Exception as e:
            debug = {"count": 0, "sample": [], "error": str(e)}
        
        if not debug or debug.get("count", 0) == 0:
            logger.warning(f"未找到粉丝元素(span.shows)。debug={debug}")
            return {
                "success": False,
                "error": f"未找到粉丝元素(span.shows)，可能未登录或页面未渲染完成。debug={debug}"
            }
        
        # 5. 使用JS提取指定结构
        try:
            data = await self._extract_all_via_js(page)
            if data.get("fans"):
                data["success"] = True
                data["need_login"] = False
                data["status"] = "成功"
                return data
        except Exception as e:
            logger.warning(f"JS提取出错: {e}")
            print(f"    JS提取出错: {e}")

        # 6. 不使用滚动/备用选择器，严格限定单一结构
        logger.warning("未匹配到指定结构(span.count + span.shows=粉丝)")
        return {"success": False, "error": "未匹配到指定结构(span.count + span.shows=粉丝)"}
    
    def _is_banned_page(self, title="", content="") -> bool:
        """判断是否为封禁/不存在页面"""
        # 1. 优先检查标题，标题通常最直接反映状态
        banned_titles = [
            "404", "页面不存在", "用户不存在", "账号已封禁", "账号已注销", 
            "出错了", "System Error", "访问受限"
        ]
        if any(kw in title for kw in banned_titles):
            return True
            
        # 2. 检查页面正文中的特定提示文本 (不再检查全量 content，避免命中脚本内容)
        # 只检查前 2000 个字符或使用特定的选择器文本
        banned_keywords = [
            "账号已封禁", "该用户不存在", "用户未找到", "内容不存在",
            "账号已注销", "账号注销", "用户已注销", "该账号已注销",
            "账号异常", "此账号已注销", "因相关法律法规"
        ]
        
        # 尝试只获取 body 的文本内容，而不是全量 HTML
        text_to_check = title
        if content:
            # 粗略提取正文文本（简单过滤 HTML 标签）
            text_to_check += " " + re.sub(r'<[^>]+>', ' ', content[:5000])
            
        return any(kw in text_to_check for kw in banned_keywords)
    
    async def _extract_all_via_js(self, page: Page) -> dict:
        """
        通过JS直接在浏览器中提取所有数据
        这是最可靠的方式，因为可以遍历整个DOM
        """
        data = await page.evaluate(r"""() => {
            const result = {
                nickname: '',
                fans: '',
                following: '',
                likes_and_collects: '',
                desc: '',
                ip_location: '',
                red_id: ''
            };
            
            // 提取待处理文本的辅助函数
            const cleanText = (text) => (text || '').trim();
            const extractNum = (text) => {
                // 匹配数字，支持 小数点、逗号、万/千/亿
                // 例如: 100, 1.2万, 1,234, 100.5
                const match = text.match(/[\\d][\\d,.]*[万千亿]?/);
                return match ? match[0] : '';
            };
            
            // 仅按指定结构提取粉丝数：
            // <div><span class="count">18</span><span class="shows">粉丝</span></div>
            const shows = [...document.querySelectorAll('span.shows')].find(
                el => cleanText(el.innerText) === '粉丝'
            );
            if (shows) {
                const prevEl = shows.previousElementSibling;
                if (prevEl && prevEl.classList.contains('count')) {
                    const num = extractNum(prevEl.innerText);
                    if (num) result.fans = num;
                }
            }
            
            // 提取昵称
            const nameEl = document.querySelector('.user-name') 
                || document.querySelector('.name-detail')
                || document.querySelector('[class*="user-name"]');
            if (nameEl) result.nickname = cleanText(nameEl.innerText);
            
            // 提取简介
            const descEl = document.querySelector('.user-desc')
                || document.querySelector('.user-brief')
                || document.querySelector('[class*="user-desc"]');
            if (descEl) result.desc = cleanText(descEl.innerText);
            
            // 提取IP
            const ipEl = document.querySelector('.user-IP') || document.querySelector('[class*="ip-location"]');
            if (ipEl) {
                result.ip_location = cleanText(ipEl.innerText).replace('IP属地：', '').replace('IP属地:', '');
            }
            
            // 提取小红书号
            const allPageText = document.body.innerText;
            const redIdMatch = allPageText.match(/小红书号[：:]\\s*([a-zA-Z0-9_]+)/);
            if (redIdMatch) result.red_id = redIdMatch[1];
            
            return result;
        }""")
        
        return data
    
    async def _extract_via_selectors(self, page: Page) -> dict:
        """已禁用：保留空实现以防外部调用"""
        return {
            "nickname": "",
            "fans": "",
            "following": "",
            "likes_and_collects": "",
            "desc": "",
            "ip_location": "",
            "red_id": "",
        }
    
    def _extract_number_from_text(self, text: str, label: str) -> str:
        """
        从文本中提取与标签相关的数字
        "1.2万 粉丝" -> "1.2万"
        "123 粉丝" -> "123"
        "粉丝 1,234" -> "1,234"
        """
        # 去除标签文字
        text = text.replace(label, "").strip()
        # 查找完整数字（包含逗号、小数点、万/千/亿单位）
        # 修复：确保匹配完整的数字序列，不要被空格截断
        numbers = re.findall(r'[\d][\d,\.]*[万千亿]?', text)
        if numbers:
            # 取最长的匹配（避免只取到一位数）
            return max(numbers, key=len)
        return text.strip() if text.strip() else ""

    @staticmethod
    def parse_number(text: str) -> int:
        """
        将中文数字格式转为整数
        "1.2万" -> 12000
        "3456" -> 3456
        "1,234" -> 1234
        """
        if not text:
            return 0
        text = text.strip().replace(",", "")
        try:
            if "亿" in text:
                return int(float(text.replace("亿", "")) * 100000000)
            elif "万" in text:
                return int(float(text.replace("万", "")) * 10000)
            elif "千" in text:
                return int(float(text.replace("千", "")) * 1000)
            else:
                return int(float(text))
        except (ValueError, TypeError):
            try:
                 # 尝试只提取数字部分
                 import re
                 nums = re.findall(r"[\d\.]+", text)
                 if nums:
                     return int(float(nums[0]))
            except:
                pass
            return 0

    async def _simulate_human(self, page: Page):
        """已禁用：不再滚动页面"""
        return


async def random_delay():
    """反检测：随机请求间隔"""
    delay = random.uniform(Config.COLLECT_MIN_DELAY, Config.COLLECT_MAX_DELAY)
    await asyncio.sleep(delay)


async def batch_rest():
    """反检测：批次间长休息"""
    rest = random.uniform(Config.COLLECT_BATCH_REST_MIN, Config.COLLECT_BATCH_REST_MAX)
    await asyncio.sleep(rest)


# 全局数据采集器实例
data_collector = DataCollector()
