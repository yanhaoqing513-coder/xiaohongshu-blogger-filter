# 小红书博主筛选工具

根据小红书主页链接，自动打开页面截图，并根据自定义筛选条件判断博主是否符合要求。

## 功能特点

- 📊 **批量处理**：上传Excel文件，自动处理多个博主链接
- 🎯 **智能筛选**：自定义筛选条件，AI智能判断
- 🧠 **双分析模式**：支持大模型图片识别，或当前OCR+文本识别
- 📸 **自动截图**：真实浏览器自动访问页面、关闭登录提示卡并截图
- 🔍 **OCR识别**：PaddleOCR识别页面中的文字内容
- 💾 **结果写回**：按固定Excel格式写入主页截图、是否合适、理由和备注

## 快速开始

### 方式一：双击启动（推荐）

1. 双击 `start.command` 文件
2. 首次运行会自动安装依赖（可能需要几分钟）
3. 浏览器会自动打开 http://localhost:5001

### 方式二：手动启动

```bash
# 1. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装Patchright浏览器环境
patchright install chromium

# 4. 启动服务
python app.py
```

## 配置说明

复制 `.env.example` 为 `.env`，根据需要修改配置：

```env
# Ollama配置（默认）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3-vl:235b-cloud

# 浏览器配置
BROWSER_HEADLESS=false  # 设为true可隐藏浏览器窗口
```

## 使用步骤

1. **准备Excel文件**
   - 固定列顺序：昵称、主页链接、主页截图、是否合适、理由、备注
   - 程序会跳过已经填写“是否合适”的行，支持断点续跑

2. **上传文件**
   - 在界面中上传准备好的Excel文件

3. **输入筛选条件**
   - 用自然语言描述筛选要求
   - 例如："筛选美妆护肤类博主，内容以测评为主"
   - 可选择"大模型图片识别"或"OCR + 文本识别"

4. **开始筛选**
   - 点击"开始筛选"按钮
   - 未登录时会尝试自动关闭小红书登录提示卡后截图

5. **下载结果**
   - 筛选完成后下载结果Excel

## 筛选条件示例

```
筛选美妆护肤类博主：
• 主要发布护肤、化妆相关内容
• 笔记风格偏向测评或教程
• 排除纯广告账号
```

```
筛选穿搭博主：
• 主要发布穿搭、时尚相关内容
• 风格简约大方
• 有一定的互动量
```

## 项目结构

```
小红书博主筛选/
├── app.py              # Flask主应用
├── config.py           # 配置管理
├── excel_handler.py    # Excel处理
├── browser_controller.py # 浏览器控制
├── ocr_service.py      # OCR识别
├── ai_judge.py         # AI判断
├── requirements.txt    # Python依赖
├── start.command       # macOS启动脚本
├── .env.example        # 环境变量模板
└── static/             # 前端文件
    ├── index.html
    ├── style.css
    └── script.js
```

## 常见问题

### Q: AI服务未连接怎么办？
A: 确保Ollama服务已启动，并且模型可用。当前默认模型为 `qwen3-vl:235b-cloud`。

### Q: 小红书弹出登录提示卡怎么办？
A: 筛选流程会自动尝试点击关闭按钮或按 `Esc` 关闭提示卡。如果遇到安全验证/扫码认证，需要人工处理。

### Q: 筛选速度很慢？
A: 为降低触发风控概率，链接之间会随机间隔1-3秒，每20条会短暂休息。

## 注意事项

⚠️ 本工具仅供学习研究使用，请遵守小红书平台规则，不要频繁大量访问。
