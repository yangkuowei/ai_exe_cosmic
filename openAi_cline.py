from typing import Callable, Tuple, Dict, List, Optional, TypeVar
from openai import OpenAI
import os
import logging
from dataclasses import dataclass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

T = TypeVar('T')

@dataclass
class ModelConfig:
    """大模型配置类"""
    provider: str
    base_url: str
    model_name: str
    api_key: Optional[str] = None
    temperature: float = 0.9
    max_tokens: int = 8192

    def validate(self) -> None:
        """验证配置有效性"""
        if not self.base_url:
            raise ValueError(f"{self.provider}配置缺少base_url")
        if not self.model_name:
            raise ValueError(f"{self.provider}配置缺少model_name")
        if not self.api_key:
            logger.warning(f"{self.provider} API密钥未配置，将尝试使用环境变量")

def load_model_config(provider: str = "LMStudio") -> ModelConfig:
    """加载指定供应商的模型配置"""
    configs = {
        "302": ModelConfig(
            provider="302",
            base_url=os.getenv("API_302_BASE_URL", "https://api.302.ai/v1/chat/completions"),
            model_name=os.getenv("API_302_MODEL", "gemini-2.0-pro-exp-02-05"),
            api_key=os.getenv("API_302_KEY")
        ),
        "deepseek": ModelConfig(
            provider="deepseek",
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            model_name=os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner"),
            api_key=os.getenv("DEEP_SEEK_API_KEY")
        ),
        "aliyun": ModelConfig(
            provider="aliyun",
            base_url=os.getenv("ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            model_name=os.getenv("ALIYUN_MODEL", "qwq-32b"),
            api_key=os.getenv("DASHSCOPE_API_KEY")
        ),
        "nvidia": ModelConfig(
            provider="nvidia",
            base_url=os.getenv("ALIYUN_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            model_name=os.getenv("ALIYUN_MODEL", "deepseek-ai/deepseek-r1"),
            api_key=os.getenv("NVIDIA_API_KEY")
        ),
        "lmstudio": ModelConfig(
            provider="lmstudio",
            base_url=os.getenv("BASE_URL", "http://127.0.0.1:1234/v1"),
            model_name=os.getenv("model_name", "qwen2.5-32b-instruct"),
            api_key=os.getenv("NVIDIA_API_KEY")
        )
    }

    config = configs.get(provider.lower())
    if not config:
        raise ValueError(f"不支持的供应商: {provider}")

    config.validate()
    return config

# 初始化客户端
current_config = load_model_config()
client = OpenAI(api_key=current_config.api_key, base_url=current_config.base_url)

def call_ai(
    ai_prompt: str,
    requirement_content: str,
    extractor: Callable[[str], T],
    validator: Callable[[T], Tuple[bool, str]],
    max_iterations: int = 1,
) -> T:
    """
    AI大模型调用与验证流程

    Args:
        ai_prompt: 系统提示词
        requirement_content: 需求内容
        extractor: 内容提取函数
        validator: 数据验证函数
        max_iterations: 最大重试次数

    Returns:
        验证通过后的结构化数据

    Raises:
        RuntimeError: 超过最大重试次数或通信失败
    """
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": ai_prompt},
        {"role": "user", "content": requirement_content}
    ]

    for attempt in range(1, max_iterations + 1):
        logger.info(f"开始第 {attempt}/{max_iterations} 次生成尝试")

        try:
            completion = client.chat.completions.create(
                model=current_config.model_name,
                messages=messages,
                stream=True,
                temperature=current_config.temperature,
                #max_tokens=current_config.max_tokens
            )

            # 处理流式响应
            reasoning, answer = process_stream_response(completion)
            messages.append({"role": "assistant", "content": answer})

            # 提取并验证数据
            extracted_data = extractor(answer)
            is_valid, error_msg = validator(extracted_data)

            if is_valid:
                logger.info("数据校验通过")
                return extracted_data
                
            logger.warning(f"校验未通过: {error_msg}")
            messages.append({"role": "user", "content": f"校验错误: {error_msg}"})

            if attempt == max_iterations:
                return extracted_data


        except Exception as e:
            logger.error(f"API请求失败: {str(e)}")
            if attempt == max_iterations:
                raise RuntimeError(f"超过最大重试次数({max_iterations})") from e

    #raise RuntimeError(f"无法生成有效数据，已达最大重试次数: {max_iterations}")

def process_stream_response(completion) -> Tuple[str, str]:
    """处理流式响应并返回推理过程和回答内容"""
    reasoning_content = []
    answer_content = []
    
    for chunk in completion:
        if not chunk.choices:
            continue
            
        delta = chunk.choices[0].delta
        
        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            reasoning_content.append(delta.reasoning_content)
            #logger.debug(f"推理内容: {delta.reasoning_content}")
            print(delta.reasoning_content, end='', flush=True)  # 实时流式输出到控制台
            
        if delta.content:
            answer_content.append(delta.content)
            print(delta.content, end='', flush=True)  # 实时流式输出到控制台
    
    return ''.join(reasoning_content), ''.join(answer_content)



# --- Example Calls ---

# Example 3:  Show how to change max_iterations
# ai_prompt_json = "You are a helpful assistant that generates JSON objects."
# requirement_json = "Create a JSON object with a field 'required_field'."
# final_answer_json = call_ai(
#     ai_prompt_json,
#     requirement_json,
#     extract_json_from_text,
#     validate_json_schema,
#     max_iterations=5,  # Override the default
# )
# print(f"Final Answer (JSON, with max_iterations=5):\n{final_answer_json}")
