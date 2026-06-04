"""
配置管理模块
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Ollama配置
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-vl:235b-cloud")
    
    # OpenAI配置（可选）
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    # 浏览器配置
    BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
    PAGE_LOAD_TIMEOUT = int(os.getenv("PAGE_LOAD_TIMEOUT", "30000"))
    
    # 数据采集 - 反检测配置
    COLLECT_MIN_DELAY = int(os.getenv("COLLECT_MIN_DELAY", "1"))       # 最小请求间隔（秒）
    COLLECT_MAX_DELAY = int(os.getenv("COLLECT_MAX_DELAY", "3"))       # 最大请求间隔（秒）
    COLLECT_BATCH_SIZE = int(os.getenv("COLLECT_BATCH_SIZE", "20"))    # 每批处理数量
    COLLECT_BATCH_REST_MIN = int(os.getenv("COLLECT_BATCH_REST_MIN", "10"))  # 批次间最小休息（秒）
    COLLECT_BATCH_REST_MAX = int(os.getenv("COLLECT_BATCH_REST_MAX", "20"))  # 批次间最大休息（秒）
    
    # 文件上传配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
    OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "outputs")
    SCREENSHOT_FOLDER = os.path.join(os.path.dirname(__file__), "screenshots")

    # 视觉模型输入图优化。Excel 仍保留原始截图，发给模型前单独压缩一份。
    VISION_IMAGE_MAX_WIDTH = int(os.getenv("VISION_IMAGE_MAX_WIDTH", "1024"))
    VISION_IMAGE_MAX_HEIGHT = int(os.getenv("VISION_IMAGE_MAX_HEIGHT", "1280"))
    VISION_IMAGE_JPEG_QUALITY = int(os.getenv("VISION_IMAGE_JPEG_QUALITY", "82"))
    
    # 确保目录存在
    @staticmethod
    def ensure_dirs():
        for folder in [Config.UPLOAD_FOLDER, Config.OUTPUT_FOLDER, Config.SCREENSHOT_FOLDER]:
            os.makedirs(folder, exist_ok=True)
