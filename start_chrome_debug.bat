@echo off
setlocal enabledelayedexpansion

echo ======================================
echo    启动小红书专用调试浏览器 (Windows)
echo ======================================
echo.

:: 设置 Chrome 路径和数据目录
set "CHROME_PATH_1=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
set "CHROME_PATH_2=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
set "CHROME_PATH_3=%LocalAppData%\Google\Chrome\Application\chrome.exe"
set "USER_DATA_DIR=%~dp0browser_data"

:: 检查 Chrome 路径并启动
if exist "!CHROME_PATH_1!" (
    set "CHROME_PATH=!CHROME_PATH_1!"
) else if exist "!CHROME_PATH_2!" (
    set "CHROME_PATH=!CHROME_PATH_2!"
) else if exist "!CHROME_PATH_3!" (
    set "CHROME_PATH=!CHROME_PATH_3!"
) else (
    set "CHROME_PATH=chrome.exe"
)

echo 🚀 正在启动 Chrome...
echo 📂 数据目录: !USER_DATA_DIR!
echo 🔌 调试端口: 9222
echo.

start "" "!CHROME_PATH!" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="!USER_DATA_DIR!" ^
    --no-first-run ^
    --no-default-browser-check ^
    --new-window ^
    "https://www.xiaohongshu.com"

if %errorlevel% neq 0 (
    echo ❌ 错误：无法启动 Chrome，请确保已安装 Google Chrome 浏览器。
) else (
    echo ✅ 浏览器已启动！
    echo 💡 请在浏览器中完成登录，然后回到网页版工具开始任务。
)

pause
