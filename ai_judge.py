"""
AI判断模块 - 使用Ollama/OpenAI根据用户提示词判断博主是否符合条件
"""
import base64
import requests
import json
from config import Config
from prompt_settings import load_prompt_templates


class AIJudge:
    def __init__(self):
        self.ollama_url = Config.OLLAMA_BASE_URL
        self.model = Config.OLLAMA_MODEL
    
    def judge(self, ocr_text: str, filter_prompt: str) -> dict:
        """
        根据OCR识别的内容和用户筛选条件判断博主是否符合要求
        
        Args:
            ocr_text: OCR识别的文字内容
            filter_prompt: 用户自定义的筛选提示词
            
        Returns:
            判断结果字典
        """
        system_prompt = load_prompt_templates()["text_system_prompt"]

        # 构建用户消息
        user_message = f"""## 用户筛选条件：
{filter_prompt}

## 博主主页OCR识别内容：
{ocr_text}

请根据以上信息判断该博主是否符合筛选条件。"""

        try:
            # 调用Ollama API
            response = self._call_ollama(system_prompt, user_message)
            
            if response["success"]:
                # 解析AI返回的JSON
                result = self._parse_response(response["content"])
                return result
            else:
                return {
                    "matched": False,
                    "reason": f"AI调用失败: {response.get('error', '未知错误')}",
                    "content_summary": "",
                    "success": False
                }
                
        except Exception as e:
            return {
                "matched": False,
                "reason": f"处理异常: {str(e)}",
                "content_summary": "",
                "success": False
            }

    def judge_image(self, image_path: str, filter_prompt: str) -> dict:
        """
        根据主页截图和用户筛选条件判断博主是否符合要求。
        需要当前Ollama模型支持图片输入。
        """
        system_prompt = load_prompt_templates()["vision_system_prompt"]

        user_message = f"""## 用户筛选条件：
{filter_prompt}

请直接分析这张小红书主页截图，判断该博主是否符合筛选条件。"""

        try:
            response = self._call_ollama_with_image(system_prompt, user_message, image_path)

            if response["success"]:
                return self._parse_response(response["content"])
            else:
                return {
                    "matched": False,
                    "reason": f"视觉模型调用失败: {response.get('error', '未知错误')}",
                    "content_summary": "",
                    "success": False
                }

        except Exception as e:
            return {
                "matched": False,
                "reason": f"处理异常: {str(e)}",
                "content_summary": "",
                "success": False
            }
    
    def _call_ollama(self, system_prompt: str, user_message: str) -> dict:
        """调用Ollama API"""
        url = f"{self.ollama_url}/api/chat"
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3  # 降低随机性，使结果更稳定
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            content = result.get("message", {}).get("content", "")
            
            return {
                "success": True,
                "content": content
            }
            
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "请求超时，请检查Ollama服务是否正常运行"
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": f"无法连接到Ollama服务 ({self.ollama_url})，请确保服务已启动"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _call_ollama_with_image(self, system_prompt: str, user_message: str, image_path: str) -> dict:
        """调用支持图片输入的Ollama模型"""
        url = f"{self.ollama_url}/api/chat"

        with open(image_path, "rb") as image_file:
            image_base64 = base64.b64encode(image_file.read()).decode("utf-8")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_message,
                    "images": [image_base64]
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.2
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()

            result = response.json()
            content = result.get("message", {}).get("content", "")

            return {
                "success": True,
                "content": content
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "请求超时，请检查视觉模型是否可用或图片分析是否过慢"
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": f"无法连接到Ollama服务 ({self.ollama_url})，请确保服务已启动"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _parse_response(self, content: str) -> dict:
        """解析AI返回的内容"""
        try:
            # 尝试直接解析JSON
            # 有时AI可能会在JSON前后添加一些文字，尝试提取JSON部分
            content = content.strip()
            
            # 查找JSON块
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                result = json.loads(json_str)
                result["success"] = True
                return result
            else:
                return {
                    "matched": False,
                    "reason": "无法解析AI返回结果",
                    "content_summary": content[:200],
                    "success": False
                }
                
        except json.JSONDecodeError:
            return {
                "matched": False,
                "reason": "AI返回格式错误",
                "content_summary": content[:200] if content else "",
                "success": False
            }
    
    def test_connection(self) -> dict:
        """测试Ollama连接"""
        try:
            url = f"{self.ollama_url}/api/tags"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            return {
                "success": True,
                "available_models": model_names,
                "current_model": self.model,
                "model_available": self.model in model_names or any(self.model in m for m in model_names)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# 全局AI判断实例
ai_judge = AIJudge()


def judge_blogger(ocr_text: str, filter_prompt: str) -> dict:
    """判断博主是否符合条件"""
    return ai_judge.judge(ocr_text, filter_prompt)


def judge_blogger_image(image_path: str, filter_prompt: str) -> dict:
    """使用支持视觉输入的模型判断博主是否符合条件"""
    return ai_judge.judge_image(image_path, filter_prompt)


def test_ai_connection() -> dict:
    """测试AI连接"""
    return ai_judge.test_connection()
