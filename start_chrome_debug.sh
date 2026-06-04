#!/bin/bash
# 启动带调试端口的Chrome浏览器（参考 自动记录数据 项目逻辑）

echo "======================================"
echo "   启动小红书专用调试浏览器"
echo "======================================"
echo ""

# Mac路径
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
USER_DATA_DIR="$(dirname "$0")/browser_data"

if [ -d "/Applications/Google Chrome.app" ]; then
    echo "🚀 正在启动Chrome..."
    echo "📂 数据目录: $USER_DATA_DIR"
    echo "🔌 调试端口: 9222"
    
    # 使用与 Python 程序一致的 browser_data 目录，确保登录状态同步
    "$CHROME_PATH" \
        --remote-debugging-port=9222 \
        --user-data-dir="$USER_DATA_DIR" \
        --no-first-run \
        --no-default-browser-check \
        --new-window \
        "https://www.xiaohongshu.com" &
    
    echo ""
    echo "✅ 浏览器已启动！"
    echo "💡 请在浏览器中完成登录，然后回到网页版工具开始任务。"
else
    echo "❌ 错误：未找到 Google Chrome 浏览器"
    exit 1
fi
