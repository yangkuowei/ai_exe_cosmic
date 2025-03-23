from typing import Callable, Tuple, Dict, List, Optional, TypeVar, Any
from openai import OpenAI, APIConnectionError, APIError
import os
import logging
from dataclasses import dataclass
import time
from pathlib import Path
import httpx

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

T = TypeVar('T')

class AIError(Exception):
    """Base exception for AI operations"""
    def __init__(self, message: str, max_retries: int = None):
        super().__init__(message)
        self.max_retries = max_retries

class ValidationError(AIError):
    """Data validation failed after max retries"""

class ConfigurationError(AIError):
    """Invalid configuration detected"""

@dataclass
class ModelConfig:
    """大模型配置类
    
    Attributes:
        provider: 服务提供商名称 (e.g. 'aliyun', 'openai')
        base_url: API基础地址
        model_name: 模型名称
        api_key: 认证密钥 (可选)
        temperature: 生成温度 (0.0~2.0)
        max_tokens: 最大生成token数
        timeout: 请求超时时间(秒)
        max_retries: 最大重试次数
    """
    provider: str
    base_url: str
    model_name: str
    api_key: Optional[str] = None
    temperature: float = 0.9
    max_tokens: int = 8192
    timeout: float = 30.0
    max_retries: int = 3

    def validate(self) -> None:
        """验证配置有效性
        
        Raises:
            ConfigurationError: 当配置不合法时抛出
        """
        errors = []
        if not self.base_url:
            errors.append(f"{self.provider}配置缺少base_url")
        if not self.model_name:
            errors.append(f"{self.provider}配置缺少model_name")
        if not self.api_key:
            logger.warning(f"{self.provider} API密钥未配置，将尝试使用环境变量")
        
        try:
            httpx.URL(self.base_url)
        except Exception as e:
            errors.append(f"无效的base_url: {str(e)}")
            
        if self.temperature < 0 or self.temperature > 2:
            errors.append("temperature必须在0~2之间")
            
        if errors:
            raise ConfigurationError("\n".join(errors))

def load_model_config(provider: str = None, config_dir: str = None) -> ModelConfig:
    """加载指定供应商的模型配置
    
    Args:
        provider: 服务商名称 (可选)
        config_dir: 配置文件目录路径 (可选)
        
    Returns:
        ModelConfig: 验证通过的配置对象
        
    Raises:
        ConfigurationError: 配置加载或验证失败时抛出
    """
    import yaml
    from typing import cast
    
    try:
        # 动态获取配置文件路径
        base_dir = Path(config_dir) if config_dir else Path(__file__).parent
        config_path = base_dir / "configs/model_providers.yaml"
        
        if not config_path.exists():
            raise ConfigurationError(f"配置文件不存在: {config_path}")
            
        with open(config_path, encoding='utf-8') as f:
            config_data = yaml.safe_load(f) or {}
        
        # 获取默认提供商
        default_provider = config_data.get('default_provider', 'aliyun')
        selected_provider = provider.lower() if provider else default_provider
        
        # 获取提供商配置
        provider_config = config_data.get('providers', {}).get(selected_provider)
        if not provider_config:
            available = ', '.join(config_data.get('providers', {}).keys())
            raise ConfigurationError(
                f"不支持的供应商: {selected_provider}，可用供应商: {available}"
            )
            
        # 类型安全的配置获取
        env_mapping = cast(dict, provider_config.get('env_mapping', {}))
        base_url = os.getenv(
            env_mapping.get('base_url', ''),
            provider_config.get('base_url', '')
        )
        model_name = os.getenv(
            env_mapping.get('model_name', ''),
            provider_config.get('model_name', '')
        )
        api_key = os.getenv(env_mapping.get('api_key', ''))
        
        # 构建配置对象
        config = ModelConfig(
            provider=selected_provider,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            temperature=provider_config.get('temperature', 0.9),
            max_tokens=provider_config.get('max_tokens', 8192),
            timeout=provider_config.get('timeout', 60.0),
            max_retries=provider_config.get('max_chat_cout', 3)
        )
        
        config.validate()
        return config
        
    except yaml.YAMLError as ye:
        raise ConfigurationError(f"配置文件解析失败: {str(ye)}") from ye
    except IOError as ioe:
        raise ConfigurationError(f"配置文件读取失败: {str(ioe)}") from ioe

def create_client(config: ModelConfig) -> OpenAI:
    """创建配置化的OpenAI客户端
    
    Args:
        config: 模型配置对象
        
    Returns:
        OpenAI: 配置好的客户端实例
    """
    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=httpx.Timeout(config.timeout),
        max_retries=config.max_retries
    )

def call_ai(
    ai_prompt: str,
    requirement_content: str,
    extractor: Callable[[str], T],
    validator: Callable[[T], Tuple[bool, str]],
    config: ModelConfig,
    max_chat_cout: int = 3,  # 原max_iterations参数已重命名为max_retries
) -> T:
    """AI大模型调用与验证流程
    
    Args:
        ai_prompt: 系统提示词
        requirement_content: 需求内容
        extractor: 内容提取函数
        validator: 数据验证函数
        config: 模型配置
        max_chat_cout: 最大对话次数
        stream_callback: 流式响应回调函数
        
    Returns:
        验证通过后的结构化数据
        
    Raises:
        ValidationError: 数据验证失败超过最大重试次数
        APIConnectionError: API连接失败超过最大重试次数
        APIError: API返回错误超过最大重试次数

    """

    def stream_callback(content: str):
        """流式响应回调示例"""
        print(content, end='', flush=True)

    client = create_client(config)
    messages = [
        {"role": "system", "content": ai_prompt},
        {"role": "user", "content": requirement_content}
    ]
    
    last_error = None
    for attempt in range(1, max_chat_cout + 1):
        try:
            logger.info(f"Attempt {attempt}/{max_chat_cout}")
            completion = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                stream=True,
                temperature=config.temperature,
                max_tokens=config.max_tokens
            )

            reasoning, answer = process_stream_response(
                completion,
                stream_callback
            )
            messages.append({"role": "assistant", "content": answer})

            extracted_data = extractor(answer)
            is_valid, error_msg = validator(extracted_data)

            if is_valid:
                logger.info("数据校验通过")
                return extracted_data
                
            logger.warning(f"校验未通过: {error_msg}")
            messages.append({"role": "user", "content": f"生成内容校验未通过: {error_msg}\n**请严格按照cosmic编写规范重新输出完整内容**"})
            last_error = ValidationError(f"验证失败: {error_msg}", max_retries=max_chat_cout)

            if attempt >= max_chat_cout:
                return extracted_data #强制返回，人工处理错误

        except APIConnectionError as e:
            logger.warning(f"连接失败 ({attempt}/{max_chat_cout}): {str(e)}")
            last_error = e
            time.sleep(min(2 ** attempt, 10))  # 指数退避
        except APIError as e:
            logger.error(f"API错误 ({attempt}/{max_chat_cout}): {str(e)}")
            last_error = e
            time.sleep(1)
        except Exception as e:
            logger.exception("未处理的异常")
            last_error = AIError(f"未知错误: {str(e)}")
            break

    if last_error:
        if isinstance(last_error, ValidationError):
            raise ValidationError(f"超过最大验证重试次数: {max_chat_cout}") from last_error
        raise AIError(f"超过最大重试次数: {max_chat_cout}") from last_error
    raise AIError("未知错误导致处理失败")

def process_stream_response(
    completion: Any,
    callback: Optional[Callable[[str], None]] = None
) -> Tuple[str, str]:
    """处理流式响应并返回推理过程和回答内容
    
    Args:
        completion: 流式响应对象
        callback: 实时内容回调函数
        
    Returns:
        Tuple[推理内容, 最终回答]
    """
    reasoning_content = []
    answer_content = []
    
    try:
        for chunk in completion:
            if not chunk.choices:
                continue
                
            delta = chunk.choices[0].delta
            
            # 处理推理内容
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                content = delta.reasoning_content
                reasoning_content.append(content)
                if callback:
                    callback(f"{content}")
                else:
                    logger.debug(f"{content}")
            
            # 处理回答内容
            if delta.content:
                content = delta.content
                answer_content.append(content)
                if callback:
                    callback(content)
                else:
                    logger.debug(f"{content}")
    
    except Exception as e:
        logger.error(f"流式响应处理失败: {str(e)}")
        raise
    
    return ''.join(reasoning_content), ''.join(answer_content)



def extract_json_from_text(text: str) -> dict:
    """从文本中提取JSON内容"""
    import json
    start = text.find('{')
    end = text.rfind('}') + 1
    return json.loads(text[start:end])

def validate_json_schema(data: dict) -> Tuple[bool, str]:
    """验证JSON包含required_field字段"""
    if 'required_field' in data:
        return True, ""
    return False, "缺少required_field字段"
