"""
小红书博主筛选工具 - Flask主应用
"""
import os
import asyncio
import uuid
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import Config
from excel_handler import (
    create_collection_excel,
    create_result_excel,
    ensure_fixed_format_headers,
    generate_output_filename,
    read_excel_links,
    read_fixed_format_links,
    write_fixed_format_result,
)
from browser_controller import capture_homepage, init_browser, close_browser, wait_for_login, browser_controller
from ocr_service import recognize_image
from ai_judge import judge_blogger, judge_blogger_image, test_ai_connection
from data_collector import data_collector, random_delay, batch_rest
from prompt_settings import load_prompt_templates, save_default_filter_prompt, save_prompt_templates

# 确保目录存在
Config.ensure_dirs()

app = Flask(__name__, static_folder='static')
CORS(app)

# 存储任务状态
tasks = {}


def allowed_file(filename):
    """检查文件类型"""
    return filename.lower().endswith(('.xlsx', '.xls'))


def is_rate_limited_error(error: str) -> bool:
    """判断是否为小红书频率限制提示"""
    if not error:
        return False
    keywords = ["操作过于频繁", "访问频繁", "请求过于频繁", "稍后再试", "请稍后再试", "too frequent"]
    return any(keyword in str(error) for keyword in keywords)


async def wait_for_user_login_confirmation(task: dict, timeout: int = 600) -> bool:
    """等待前端“我已登录”确认。"""
    task["login_confirmed"] = False
    for _ in range(timeout):
        if task.get("login_confirmed"):
            task["login_confirmed"] = False
            return True
        await asyncio.sleep(1)
    return False


@app.route('/')
def index():
    """主页"""
    return app.send_static_file('index.html')


@app.route('/api/test-connection', methods=['GET'])
def api_test_connection():
    """测试AI服务连接"""
    result = test_ai_connection()
    return jsonify(result)


@app.route('/api/prompt-template', methods=['GET'])
def api_get_prompt_template():
    """获取AI筛选提示词模板"""
    return jsonify({
        "success": True,
        **load_prompt_templates()
    })


@app.route('/api/prompt-template', methods=['POST'])
def api_save_prompt_template():
    """保存AI筛选提示词模板"""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "请求数据为空"}), 400

    try:
        saved = save_prompt_templates(
            data.get("text_system_prompt", ""),
            data.get("vision_system_prompt", "")
        )
        return jsonify({
            "success": True,
            **saved
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/default-filter-prompt', methods=['GET'])
def api_get_default_filter_prompt():
    """获取默认筛选条件"""
    templates = load_prompt_templates()
    return jsonify({
        "success": True,
        "default_filter_prompt": templates["default_filter_prompt"]
    })


@app.route('/api/default-filter-prompt', methods=['POST'])
def api_save_default_filter_prompt():
    """保存默认筛选条件"""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "请求数据为空"}), 400

    try:
        saved = save_default_filter_prompt(data.get("default_filter_prompt", ""))
        return jsonify({
            "success": True,
            "default_filter_prompt": saved["default_filter_prompt"]
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """上传Excel文件"""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "没有上传文件"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"success": False, "error": "没有选择文件"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "只支持.xlsx和.xls格式"}), 400
    
    try:
        # 保存文件
        # secure_filename 会破坏中文文件名和扩展名，改用时间戳+原始扩展名
        original_name = file.filename
        ext = os.path.splitext(original_name)[1] or '.xlsx'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_filename = f"{timestamp}{ext}"
        file_path = os.path.join(Config.UPLOAD_FOLDER, saved_filename)
        file.save(file_path)
        
        # 读取链接
        links = read_excel_links(file_path)
        
        return jsonify({
            "success": True,
            "filename": saved_filename,
            "original_filename": original_name,
            "file_path": file_path,
            "link_count": len(links),
            "links": [l["link"] for l in links[:5]],  # 预览前5个
            "has_more": len(links) > 5
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def run_async_task(coro):
    """在新线程中运行异步任务"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route('/api/start-screening', methods=['POST'])
def api_start_screening():
    """开始筛选任务"""
    data = request.json
    
    if not data:
        return jsonify({"success": False, "error": "请求数据为空"}), 400
    
    file_path = data.get("file_path")
    filter_prompt = data.get("filter_prompt", "")
    analysis_mode = data.get("analysis_mode", "ocr")
    
    if not file_path or not os.path.exists(file_path):
        return jsonify({"success": False, "error": "文件不存在"}), 400
    
    if not filter_prompt.strip():
        return jsonify({"success": False, "error": "请输入筛选条件"}), 400

    if analysis_mode not in ("ocr", "vision"):
        return jsonify({"success": False, "error": "分析方式无效"}), 400
    
    # 创建任务
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "total": 0,
        "current_link": "",
        "current_step": "等待开始",
        "results": [],
        "error": None,
        "output_file": None,
        "file_path": file_path,
        "filter_prompt": filter_prompt,
        "analysis_mode": analysis_mode,
        "login_confirmed": False
    }
    
    # 在后台线程中执行筛选任务
    thread = threading.Thread(
        target=run_async_task,
        args=(run_screening_task(task_id),)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": "任务已创建"
    })


@app.route('/api/confirm-login/<task_id>', methods=['POST'])
def api_confirm_login_for_task(task_id):
    """用户确认已完成小红书登录/认证，继续当前任务"""
    task = tasks.get(task_id)

    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    task["login_confirmed"] = True
    task["error"] = "已确认登录，正在继续处理当前链接"

    return jsonify({
        "success": True,
        "message": "已确认登录，任务将继续"
    })


async def run_screening_task(task_id: str):
    """执行筛选任务"""
    task = tasks.get(task_id)
    if not task:
        return
    
    try:
        task["status"] = "running"
        task["current_step"] = "读取Excel链接"
        
        # 读取固定格式链接；已经填写“是否合适”的行会跳过，用于断点续跑
        ensure_fixed_format_headers(task["file_path"])
        links = read_fixed_format_links(task["file_path"])
        task["total"] = len(links)
        
        if len(links) == 0:
            task["status"] = "completed"
            task["progress"] = 0
            task["current_step"] = "没有待处理链接"
            task["output_file"] = os.path.basename(task["file_path"])
            task["error"] = "没有待处理链接：可能已全部处理完成"
            return
        
        # 初始化浏览器
        task["current_step"] = "初始化浏览器"
        await init_browser()
        
        results = []
        
        for idx, link_info in enumerate(links):
            link = link_info["link"]
            task["current_link"] = link
            task["current_step"] = f"准备处理第 {idx + 1}/{len(links)} 条"
            task["progress"] = idx
            
            start_time = datetime.now()
            
            try:
                # 1. 截图
                screenshot_filename = f"{task_id}_row{link_info['row']}.png"
                screenshot_path = os.path.join(Config.SCREENSHOT_FOLDER, screenshot_filename)
                
                capture_result = await capture_homepage(
                    link,
                    screenshot_path,
                    lambda step, current_idx=idx: task.update({
                        "current_step": f"第 {current_idx + 1}/{len(links)} 条：{step}"
                    })
                )
                
                if not capture_result["success"]:
                    if capture_result.get("is_banned"):
                        # 账号被封禁或注销
                        results.append({
                            "link": link,
                            "matched": False,
                            "reason": "账号已封禁或注销",
                            "content_summary": "无法获取内容",
                            "account_analysis": "账号无法访问，无法分析主页内容",
                            "process_time": str(datetime.now() - start_time)
                        })
                        write_fixed_format_result(
                            task["file_path"],
                            link_info["row"],
                            "",
                            False,
                            "账号异常",
                            "账号已封禁或注销，无法分析主页内容"
                        )
                        continue
                    elif capture_result.get("need_login"):
                        # 需要登录
                        task["status"] = "need_login"
                        task["current_step"] = "等待登录/认证"
                        task["error"] = "需要登录/扫码认证。请在已打开的Chrome窗口完成后，点击“我已登录，继续运行”。"
                        
                        if await wait_for_user_login_confirmation(task):
                            task["status"] = "running"
                            task["current_step"] = "登录确认完成，重试截图"
                            # 重试截图
                            capture_result = await capture_homepage(
                                link,
                                screenshot_path,
                                lambda step, current_idx=idx: task.update({
                                    "current_step": f"第 {current_idx + 1}/{len(links)} 条：{step}"
                                })
                            )
                            if not capture_result.get("success"):
                                task["status"] = "need_login" if capture_result.get("need_login") else "running"
                                if capture_result.get("need_login"):
                                    task["error"] = "仍需扫码认证/登录，请完成后再次点击“我已登录，继续运行”。"
                                    if await wait_for_user_login_confirmation(task):
                                        task["status"] = "running"
                                        task["current_step"] = "再次确认完成，重试截图"
                                        capture_result = await capture_homepage(
                                            link,
                                            screenshot_path,
                                            lambda step, current_idx=idx: task.update({
                                                "current_step": f"第 {current_idx + 1}/{len(links)} 条：{step}"
                                            })
                                        )
                                    if not capture_result.get("success"):
                                        break
                                else:
                                    break
                        else:
                            task["status"] = "need_login"
                            task["error"] = "等待登录确认超时。请重新开始，系统会从当前未填写行继续。"
                            break
                    else:
                        error_msg = capture_result.get('error', '未知错误')
                        if is_rate_limited_error(error_msg):
                            task["status"] = "rate_limited"
                            task["current_step"] = "访问过于频繁，暂停3分钟"
                            task["error"] = "小红书提示操作过于频繁，已暂停3分钟后自动重试"
                            await asyncio.sleep(180)
                            task["status"] = "running"
                            task["current_step"] = "暂停结束，重试截图"
                            capture_result = await capture_homepage(
                                link,
                                screenshot_path,
                                lambda step, current_idx=idx: task.update({
                                    "current_step": f"第 {current_idx + 1}/{len(links)} 条：{step}"
                                })
                            )
                            if capture_result.get("success"):
                                pass
                            elif capture_result.get("need_login"):
                                task["status"] = "need_login"
                                task["error"] = "需要扫码认证/登录，请完成后点击“我已登录，继续运行”。"
                                if await wait_for_user_login_confirmation(task):
                                    task["status"] = "running"
                                    task["current_step"] = "登录确认完成，重试截图"
                                    capture_result = await capture_homepage(
                                        link,
                                        screenshot_path,
                                        lambda step, current_idx=idx: task.update({
                                            "current_step": f"第 {current_idx + 1}/{len(links)} 条：{step}"
                                        })
                                    )
                                if not capture_result.get("success"):
                                    break
                            else:
                                error_msg = capture_result.get('error', '未知错误')
                        if not capture_result.get("success"):
                            results.append({
                                "link": link,
                                "matched": False,
                                "reason": f"截图失败: {error_msg}",
                                "content_summary": "",
                                "account_analysis": "",
                                "process_time": str(datetime.now() - start_time)
                            })
                            write_fixed_format_result(
                                task["file_path"],
                                link_info["row"],
                                "",
                                False,
                                "截图失败",
                                error_msg
                            )
                            continue

                if not capture_result.get("success"):
                    error_msg = capture_result.get('error', '未知错误')
                    results.append({
                        "link": link,
                        "matched": False,
                        "reason": f"截图失败: {error_msg}",
                        "content_summary": "",
                        "account_analysis": "",
                        "process_time": str(datetime.now() - start_time)
                    })
                    write_fixed_format_result(
                        task["file_path"],
                        link_info["row"],
                        "",
                        False,
                        "截图失败",
                        error_msg
                    )
                    continue
                
                # 2. 根据用户选择的分析方式判断
                if task.get("analysis_mode") == "vision":
                    task["current_step"] = f"第 {idx + 1}/{len(links)} 条：大模型图片分析"
                    judge_result = judge_blogger_image(screenshot_path, task["filter_prompt"])
                else:
                    task["current_step"] = f"第 {idx + 1}/{len(links)} 条：OCR识别"
                    ocr_result = recognize_image(screenshot_path)

                    if not ocr_result["success"]:
                        results.append({
                            "link": link,
                            "matched": False,
                            "reason": f"OCR识别失败: {ocr_result.get('error', '未知错误')}",
                            "content_summary": "",
                            "account_analysis": "",
                            "analysis_mode": "ocr",
                            "process_time": str(datetime.now() - start_time)
                        })
                        continue

                    ocr_text = ocr_result.get("text", "")

                    if not ocr_text.strip():
                        results.append({
                            "link": link,
                            "matched": False,
                            "reason": "页面内容为空或无法识别",
                            "content_summary": "",
                            "account_analysis": "",
                            "analysis_mode": "ocr",
                            "process_time": str(datetime.now() - start_time)
                        })
                        continue

                    judge_result = judge_blogger(ocr_text, task["filter_prompt"])
                
                task["current_step"] = f"第 {idx + 1}/{len(links)} 条：判断完成，写回Excel"
                results.append({
                    "link": link,
                    "matched": judge_result.get("matched", False),
                    "reason": judge_result.get("reason", ""),
                    "content_summary": judge_result.get("content_summary", ""),
                    "account_analysis": judge_result.get("account_analysis", ""),
                    "analysis_mode": task.get("analysis_mode", "ocr"),
                    "process_time": str(datetime.now() - start_time)
                })
                write_fixed_format_result(
                    task["file_path"],
                    link_info["row"],
                    screenshot_path,
                    judge_result.get("matched", False),
                    judge_result.get("reason", ""),
                    judge_result.get("account_analysis", "") or judge_result.get("content_summary", "")
                )
                task["current_step"] = f"第 {idx + 1}/{len(links)} 条：写回完成"
                
            except Exception as e:
                if is_rate_limited_error(str(e)):
                    task["status"] = "rate_limited"
                    task["current_step"] = "访问过于频繁，暂停3分钟"
                    task["error"] = "小红书提示操作过于频繁，已暂停3分钟后自动重试"
                    await asyncio.sleep(180)
                    task["status"] = "running"
                    continue

                results.append({
                    "link": link,
                    "matched": False,
                    "reason": f"处理异常: {str(e)}",
                    "content_summary": "",
                    "account_analysis": "",
                    "process_time": str(datetime.now() - start_time)
                })
            
            task["progress"] = min(idx + 1, len(links))
            task["results"] = results
            
            # 降低访问频率，避免被小红书检测
            task["current_step"] = f"第 {idx + 1}/{len(links)} 条完成，等待下一条"
            await random_delay()

            if (idx + 1) % Config.COLLECT_BATCH_SIZE == 0 and idx + 1 < len(links):
                task["current_link"] = f"批次休息中... (已完成 {idx + 1}/{len(links)})"
                task["current_step"] = f"批次休息中：已完成 {idx + 1}/{len(links)} 条"
                await batch_rest()
        
        # 任务结束，仅关闭页面
        # await close_browser() 
        # 我们不再关闭浏览器连接，让它保持在后台，提升下次任务的速度
        if task.get("status") == "need_login":
            task["results"] = results
            return
        
        # 生成结果Excel
        original_filename = os.path.basename(task["file_path"])
        output_filename = generate_output_filename(original_filename)
        output_path = os.path.join(Config.OUTPUT_FOLDER, output_filename)
        
        create_result_excel(results, output_path)
        
        task["status"] = "completed"
        task["progress"] = len(links)
        task["current_step"] = "全部完成"
        task["output_file"] = os.path.basename(task["file_path"])
        task["results"] = results
        
    except Exception as e:
        task["status"] = "error"
        task["current_step"] = "任务出错"
        task["error"] = str(e)
        # 即使报错也不关闭浏览器进程
        # try:
        #     await close_browser()
        # except:
        #     pass


@app.route('/api/task-status/<task_id>', methods=['GET'])
def api_task_status(task_id):
    """获取任务状态"""
    task = tasks.get(task_id)
    
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    
    return jsonify({
        "success": True,
        "status": task["status"],
        "progress": task["progress"],
        "total": task["total"],
        "current_link": task["current_link"],
        "current_step": task.get("current_step", ""),
        "error": task["error"],
        "output_file": task["output_file"],
        "results": task["results"],
        "matched_count": sum(1 for r in task["results"] if r.get("matched", False)),
        "unmatched_count": sum(1 for r in task["results"] if not r.get("matched", False))
    })


@app.route('/api/download/<filename>', methods=['GET'])
def api_download(filename):
    """下载结果文件"""
    file_path = os.path.join(Config.OUTPUT_FOLDER, filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(Config.UPLOAD_FOLDER, filename)
    
    if not os.path.exists(file_path):
        return jsonify({"success": False, "error": "文件不存在"}), 404
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename
    )


@app.route('/api/open-browser', methods=['POST'])
def api_open_browser():
    """打开浏览器到小红书页面，让用户手动登录"""
    def do_open():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 重置当前线程的浏览器连接状态，确保建立新连接
            browser_controller.playwright = None
            browser_controller.browser = None
            browser_controller.context = None
            
            # 初始化浏览器并打开小红书
            loop.run_until_complete(init_browser())
            
            # 打开小红书页面
            async def open_page():
                # 检查 context 是否有效
                if not browser_controller.context:
                    await init_browser()
                page = await browser_controller.context.new_page()
                await page.goto("https://www.xiaohongshu.com/explore", timeout=30000, wait_until="domcontentloaded")
            
            loop.run_until_complete(open_page())
        except Exception as e:
            print(f"❌ 打开浏览器失败: {e}")
            raise
        finally:
            # 注意：这里不能立即关闭 loop，因为 playwright 的一些异步清理可能还在进行
            # 但在 Flask 同步路由中我们也无法一直等待
            # 这里的逻辑是：建立连接 -> 打开页面 -> 任务完成
            # 由于 Chrome 是独立进程，连接断开没关系，只要页面开在那就行
            loop.close()
    
    try:
        do_open()
        print("浏览器已打开小红书，等待用户登录...")
        return jsonify({
            "success": True,
            "message": "浏览器已打开，请在浏览器中登录小红书"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route('/api/start-collecting', methods=['POST'])
def api_start_collecting():
    """开始数据采集任务"""
    data = request.json
    
    if not data:
        return jsonify({"success": False, "error": "请求数据为空"}), 400
    
    file_path = data.get("file_path")
    
    if not file_path or not os.path.exists(file_path):
        return jsonify({"success": False, "error": "文件不存在"}), 400
    
    # 创建任务
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "total": 0,
        "current_link": "",
        "results": [],
        "error": None,
        "output_file": None,
        "file_path": file_path,
        "task_type": "collecting"
    }
    
    # 在后台线程中执行采集任务
    thread = threading.Thread(
        target=run_async_task,
        args=(run_collecting_task(task_id),)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": "采集任务已创建"
    })


async def run_collecting_task(task_id: str):
    """执行数据采集任务"""
    task = tasks.get(task_id)
    if not task:
        return
    
    page = None
    try:
        task["status"] = "running"
        
        # 读取链接
        links = read_excel_links(task["file_path"])
        task["total"] = len(links)
        
        if len(links) == 0:
            task["status"] = "error"
            task["error"] = "Excel中没有找到有效的小红书链接"
            return
        
        # 获取浏览器页面
        # get_page 内部会调用 init_browser，它会自动处理连接或启动
        page = await browser_controller.get_page()
        print(f"浏览器已就绪，开始采集 {len(links)} 个链接...")
        
        results = []
        
        for idx, link_info in enumerate(links):
            link = link_info["link"]
            task["current_link"] = link
            task["progress"] = idx
            
            try:
                # 采集数据
                print(f"[{idx+1}/{len(links)}] 正在采集: {link[:60]}...")
                collect_result = await data_collector.collect_profile(page, link)
                
                if not collect_result["success"]:
                    if collect_result.get("need_login"):
                        task["status"] = "need_login"
                        task["error"] = "需要登录小红书，请在弹出的浏览器中扫码登录"
                        
                        login_success = await wait_for_login(120)
                        
                        if login_success:
                            task["status"] = "running"
                            collect_result = await data_collector.collect_profile(page, link)
                        else:
                            results.append({
                                "link": link,
                                "status": "登录失败",
                            })
                            print(f"    ❌ 登录失败")
                            continue
                    else:
                        error_msg = collect_result.get('error', '未知错误')
                        results.append({
                            "link": link,
                            "status": f"失败: {error_msg}",
                        })
                        print(f"    ❌ 失败: {error_msg}")
                        continue
                
                # 将粉丝数转为纯数字格式（如 2.1万 -> 21000）
                fans_raw = collect_result.get("fans", "")
                if fans_raw and fans_raw != "被封禁":
                    fans_num = data_collector.parse_number(fans_raw)
                    fans_value = fans_num if fans_num > 0 else fans_raw
                else:
                    fans_value = fans_raw
                
                status = collect_result.get("status", "成功")
                results.append({
                    "link": link,
                    "nickname": collect_result.get("nickname", ""),
                    "fans": fans_value,
                    "following": collect_result.get("following", ""),
                    "likes_and_collects": collect_result.get("likes_and_collects", ""),
                    "desc": collect_result.get("desc", ""),
                    "ip_location": collect_result.get("ip_location", ""),
                    "red_id": collect_result.get("red_id", ""),
                    "status": status,
                })
                
                nickname = collect_result.get("nickname", "未知")
                if "封禁" in status or "注销" in status:
                    print(f"    🚫 {status}")
                else:
                    print(f"    ✅ {nickname} | 粉丝原始值={fans_raw} | 转换后={fans_value}")
                
            except Exception as e:
                results.append({
                    "link": link,
                    "status": f"异常: {str(e)}",
                })
            
            task["results"] = results
            
            # 反检测延迟
            await random_delay()
            
            # 每批次休息
            from config import Config
            if (idx + 1) % Config.COLLECT_BATCH_SIZE == 0 and idx + 1 < len(links):
                task["current_link"] = f"批次休息中... (已完成 {idx + 1}/{len(links)})"
                await batch_rest()
        
        # 关闭页面
        if page:
            await page.close()
        
        # 生成结果Excel
        original_filename = os.path.basename(task["file_path"])
        output_filename = generate_output_filename(original_filename).replace("筛选结果", "采集结果")
        output_path = os.path.join(Config.OUTPUT_FOLDER, output_filename)
        
        create_collection_excel(results, output_path)
        
        task["status"] = "completed"
        task["progress"] = len(links)
        task["output_file"] = output_filename
        task["results"] = results
        
    except Exception as e:
        print(f"❌ 采集任务发生严重错误: {e}")
        import traceback
        traceback.print_exc()
        task["status"] = "error"
        task["error"] = str(e)
        # 发生严重错误时尝试重置浏览器连接
        try:
            browser_controller.browser = None
            browser_controller.context = None
        except:
            pass
        if page:
            try:
                await page.close()
            except:
                pass


if __name__ == '__main__':
    # 优化启动速度：设置环境变量禁用耗时的 Paddle 网络检查
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
    
    # 确保目录存在
    Config.ensure_dirs()
    
    print("\n" + "=" * 50)
    print("   🎯 小红书博主筛选工具已启动！")
    print("=" * 50)
    print("\n📌 请访问: http://localhost:5001")
    print("\n💡 提示：首次使用需要扫码登录小红书\n")
    
    # 将 Playwright 检查改为按需触发，不在主进程启动时阻塞
    # 仅在实际需要浏览器时才通过 init_browser 完成检查
    
    app.run(debug=False, port=5001, threaded=True)
