"""
OCR识别模块 - 使用PaddleOCR识别截图中的文字
"""
import os

# PaddleX checks remote model hosts during import unless this is set early.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

# 延迟导入PaddleOCR，避免未安装时阻止应用启动
try:
    from paddleocr import PaddleOCR
    HAS_PADDLEOCR = True
except ImportError:
    HAS_PADDLEOCR = False
    PaddleOCR = None

try:
    from PIL import Image
except ImportError:
    Image = None


class OCRService:
    def __init__(self):
        self.ocr = None
        self._initialized = False
    
    def _init_ocr(self):
        """延迟初始化OCR引擎"""
        if not self._initialized:
            if not HAS_PADDLEOCR:
                raise ImportError("PaddleOCR未安装，请运行: pip install paddleocr paddlepaddle")
            # 使用中文识别模型
            try:
                self.ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang='ch',
                    use_gpu=False,  # PaddleOCR 2.x 参数
                    show_log=False
                )
            except ValueError as e:
                if "Unknown argument" not in str(e):
                    raise
                self.ocr = PaddleOCR(
                    lang='ch',
                    use_textline_orientation=True,  # PaddleOCR 3.x 参数
                )
            self._initialized = True
    
    def recognize(self, image_path: str) -> dict:
        """
        识别图片中的文字
        
        Args:
            image_path: 图片路径
            
        Returns:
            包含识别结果的字典
        """
        self._init_ocr()
        
        if not os.path.exists(image_path):
            return {
                "success": False,
                "error": f"图片不存在: {image_path}",
                "text": "",
                "details": []
            }
        
        try:
            # 执行OCR识别
            try:
                result = self.ocr.ocr(image_path, cls=True)
            except TypeError as e:
                if "unexpected keyword argument 'cls'" not in str(e):
                    raise
                result = self.ocr.ocr(image_path)
            
            if result is None or len(result) == 0:
                return {
                    "success": True,
                    "text": "",
                    "details": [],
                    "note": "未识别到文字"
                }

            # PaddleOCR 3.x 返回 OCRResult/dict，字段结构不同于 2.x。
            if isinstance(result[0], dict):
                all_text = []
                details = []

                for page in result:
                    texts = page.get("rec_texts", [])
                    scores = page.get("rec_scores", [])
                    polys = page.get("rec_polys", [])
                    boxes = page.get("rec_boxes", [])

                    texts = [] if texts is None else texts
                    scores = [] if scores is None else scores
                    polys = [] if polys is None else polys
                    boxes = [] if boxes is None else boxes

                    for idx, text in enumerate(texts):
                        confidence = scores[idx] if idx < len(scores) else 0
                        if idx < len(polys):
                            bbox = polys[idx].tolist() if hasattr(polys[idx], "tolist") else polys[idx]
                        elif idx < len(boxes):
                            box = boxes[idx].tolist() if hasattr(boxes[idx], "tolist") else boxes[idx]
                            x1, y1, x2, y2 = box
                            bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                        else:
                            bbox = [[0, 0], [0, 0], [0, 0], [0, 0]]

                        all_text.append(text)
                        details.append({
                            "text": text,
                            "confidence": round(float(confidence), 3),
                            "position": {
                                "top_left": bbox[0],
                                "top_right": bbox[1],
                                "bottom_right": bbox[2],
                                "bottom_left": bbox[3]
                            }
                        })

                details.sort(key=lambda x: (x["position"]["top_left"][1], x["position"]["top_left"][0]))

                return {
                    "success": True,
                    "text": "\n".join(item["text"] for item in details),
                    "details": details,
                    "total_items": len(details)
                }
            
            # 解析识别结果
            all_text = []
            details = []
            
            for line in result:
                if line is None:
                    continue
                for item in line:
                    if item is None:
                        continue
                    # item格式: [[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], (text, confidence)]
                    bbox = item[0]
                    text = item[1][0]
                    confidence = item[1][1]
                    
                    all_text.append(text)
                    details.append({
                        "text": text,
                        "confidence": round(confidence, 3),
                        "position": {
                            "top_left": bbox[0],
                            "top_right": bbox[1],
                            "bottom_right": bbox[2],
                            "bottom_left": bbox[3]
                        }
                    })
            
            # 按位置排序（从上到下，从左到右）
            details.sort(key=lambda x: (x["position"]["top_left"][1], x["position"]["top_left"][0]))
            
            # 合并成完整文本
            full_text = "\n".join(all_text)
            
            return {
                "success": True,
                "text": full_text,
                "details": details,
                "total_items": len(details)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "text": "",
                "details": []
            }
    
    def extract_structured_info(self, ocr_result: dict) -> dict:
        """
        从OCR结果中提取结构化信息
        
        Args:
            ocr_result: OCR识别结果
            
        Returns:
            结构化的信息
        """
        text = ocr_result.get("text", "")
        
        # 简单的信息提取（可以根据实际页面结构调整）
        info = {
            "raw_text": text,
            "possible_notes": [],  # 可能的笔记标题
            "numbers": [],  # 数字信息（可能是点赞、收藏等）
        }
        
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 提取数字
            import re
            numbers = re.findall(r'[\d.]+[万千]?', line)
            if numbers:
                info["numbers"].extend(numbers)
            
            # 较长的文本可能是笔记标题
            if len(line) > 5 and not line.isdigit():
                info["possible_notes"].append(line)
        
        return info


# 全局OCR服务实例
ocr_service = OCRService()


def recognize_image(image_path: str) -> dict:
    """识别图片中的文字"""
    return ocr_service.recognize(image_path)


def extract_info(ocr_result: dict) -> dict:
    """提取结构化信息"""
    return ocr_service.extract_structured_info(ocr_result)
