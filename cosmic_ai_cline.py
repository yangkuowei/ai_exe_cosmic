from typing import Callable, Tuple, Optional, Any
from openai import OpenAI, APIConnectionError, APIError
import time
import httpx
from ai_common import ModelConfig, AIError, ValidationError, T, logger

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
    max_chat_count: int = 3,  # 原max_iterations参数已重命名为max_retries
) -> T:
    """AI大模型调用与验证流程
    
    Args:
        ai_prompt: 系统提示词
        requirement_content: 需求内容
        extractor: 内容提取函数
        validator: 数据验证函数
        config: 模型配置
        max_chat_count: 最大对话次数
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
    for attempt in range(1, max_chat_count + 1):
        try:
            logger.info(f"Attempt {attempt}/{max_chat_count}")
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
            last_error = ValidationError(f"验证失败: {error_msg}", max_retries=max_chat_count)

            if attempt >= max_chat_count:
                return extracted_data #强制返回，人工处理错误

        except APIConnectionError as e:
            logger.warning(f"连接失败 ({attempt}/{max_chat_count}): {str(e)}")
            last_error = e
            time.sleep(min(2 ** attempt, 10))  # 指数退避
        except APIError as e:
            logger.error(f"API错误 ({attempt}/{max_chat_count}): {str(e)}")
            last_error = e
            time.sleep(1)
        except Exception as e:
            logger.exception("未处理的异常")
            last_error = AIError(f"未知错误: {str(e)}")
            break

    if last_error:
        if isinstance(last_error, ValidationError):
            raise ValidationError(f"超过最大验证重试次数: {max_chat_count}") from last_error
        raise AIError(f"超过最大重试次数: {max_chat_count}") from last_error
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
