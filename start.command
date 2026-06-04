#!/bin/bash

# 小红书博主筛选工具启动脚本

# 切换到脚本所在目录
cd "$(dirname "$0")"

echo "======================================"
echo "   小红书博主筛选工具"
echo "======================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到Python3，请先安装Python"
    echo ""
    echo "安装方式："
    echo "  brew install python3"
    echo ""
    read -p "按回车键退出..."
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 首次运行，正在创建虚拟环境..."
    python3 -m venv venv
    
    echo "📦 正在安装依赖（这可能需要几分钟）..."
    source venv/bin/activate
    pip install -r requirements.txt
    
    echo "🌐 正在安装Patchright浏览器环境..."
    patchright install chromium
else
    source venv/bin/activate
fi

# 复制环境配置（如果不存在）
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "📝 已创建 .env 配置文件，请根据需要修改"
fi

echo ""
echo "🚀 正在启动服务..."
echo ""
echo "请访问: http://localhost:5001"
echo ""
echo "提示: 如果服务已经在运行，会直接打开页面"
echo "按 Ctrl+C 停止服务"
echo ""

# 如果服务已运行，直接打开页面
if lsof -nP -iTCP:5001 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "✅ 服务已在运行，正在打开页面..."
    open http://localhost:5001
    echo ""
    echo "可以关闭这个窗口。"
    read -p "按回车键退出..."
    exit 0
fi

# 启动服务并自动打开浏览器
sleep 2 && open http://localhost:5001 &
python3 app.py
