@echo off
setlocal enabledelayedexpansion

echo ======================================
echo    小红书博主筛选工具 (Windows)
echo ======================================
echo.

:: 检查Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未找到 Python，请先安装 Python 并添加到环境变量
    pause
    exit /b 1
)

:: 检查虚拟环境
if not exist "venv" (
    echo 📦 首次运行，正在创建虚拟环境...
    python -m venv venv
    
    echo 📦 正在安装依赖（这可能需要几分钟）...
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    
    echo 🌐 正在安装浏览器环境...
    patchright install chromium
) else (
    call venv\Scripts\activate.bat
)

:: 复制环境配置（如果不存在）
if not exist ".env" (
    copy .env.example .env >nul
    echo 📝 已创建 .env 配置文件，请根据需要修改
)

echo.
echo 🚀 正在启动服务...
echo.
echo 请访问: http://localhost:5001
echo.
echo 提示: 未登录时会自动尝试关闭登录提示卡；安全验证需要人工处理
echo 按 Ctrl+C 停止服务
echo.

:: 启动服务并自动打开浏览器
start http://localhost:5001
python app.py

pause
