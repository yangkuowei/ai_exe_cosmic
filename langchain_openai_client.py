import os

from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_community.chat_message_histories import ChatMessageHistory


from pydantic import BaseModel, ValidationError

class ModelProvider(BaseModel):
    """模型供应商基类"""
    model_name: str
    api_key_env: str
    base_url: str

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env)

# 加载配置文件
try:
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), 'configs/model_providers.yaml')
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
        
    # 构建供应商配置
    PROVIDERS = {
        name: ModelProvider(**values)
        for name, values in config['providers'].items()
    }
    
    # 获取默认厂商（环境变量优先）
    PROVIDER_NAME = os.getenv("LLM_PROVIDER", config['default_provider'])
    
except FileNotFoundError:
    raise RuntimeError(f"Config file not found: {config_path}")
except KeyError as e:
    raise RuntimeError(f"Missing required config section: {e}")
except Exception as e:
    raise RuntimeError(f"Error loading config: {str(e)}")

if PROVIDER_NAME not in PROVIDERS:
    raise ValueError(f"Unsupported provider: {PROVIDER_NAME}. Available: {', '.join(PROVIDERS.keys())}")

CURRENT_PROVIDER = PROVIDERS[PROVIDER_NAME]


class LangChainCosmicTableGenerator:
    def __init__(self, provider: ModelProvider = CURRENT_PROVIDER):
        """Initialize with provider configuration"""
        if not provider.api_key:
            raise ValueError(f"API key not found in env: {provider.api_key_env}")
            
        self.provider = provider
        self.chat = ChatOpenAI(
            openai_api_key=provider.api_key,
            openai_api_base=provider.base_url,
            model_name=provider.model_name,
            streaming=True,
            callbacks=[StreamingStdOutCallbackHandler()],
            temperature=0,
            max_tokens=8192
        )
        self.chat_history = ChatMessageHistory()


    def generate_table(
        self, 
        cosmic_ai_promote: str,
        requirement_content: str,
        extractor: callable,
        validator: callable,
        max_iterations: int = 3
    ) -> str:

        # 添加系统消息
        self.chat_history.add_message(SystemMessage(content=cosmic_ai_promote))
        # 添加初始用户消息
        self.chat_history.add_user_message(requirement_content)

        conversation_idx = 0

        while True:
            print("=" * 20 + f"第{conversation_idx + 1}轮对话" + "=" * 20)
            conversation_idx += 1

            # 使用 chat_history.messages 获取所有消息
            full_response = []
            # 创建自定义回调处理器
            class StreamCallback(StreamingStdOutCallbackHandler):
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    print(token, end='', flush=True)  # 实时流式输出
                    full_response.append(token)
            
            # 使用自定义回调重新初始化
            self.chat.callbacks = [StreamCallback()]
            
            response = self.chat.invoke(self.chat_history.messages)
            full_content = ''.join(full_response)
            
            # 记录完整响应到日志
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"完整响应内容: {full_content}")

            extracted_data = extractor(full_content)
            is_valid, error = validator(extracted_data)

            if is_valid:
                print("校验通过")
                final_answer = extracted_data
                break

            print(f"校验失败：{error}")
            # 添加 AI 消息和新的用户消息（错误信息）到 chat history
            self.chat_history.add_ai_message(response.content)
            self.chat_history.add_user_message(error)


            if conversation_idx >= max_iterations:
                final_answer = extracted_data
                break

        return final_answer


def call_ai(
    ai_prompt: str,
    requirement_content: str,
    extractor: callable,
    validator: callable,
    max_iterations: int = 2,
    provider: ModelProvider = CURRENT_PROVIDER
) -> str:
    """调用AI生成表格的统一入口
    
    Args:
        ai_prompt: AI系统提示语
        requirement_content: 需求内容文本
        extractor: 结果提取函数
        validator: 结果验证函数
        max_iterations: 最大对话轮次
        provider: 模型供应商配置
        
    Returns:
        经过验证的最终结果
    """
    generator = LangChainCosmicTableGenerator(provider=provider)
    return generator.generate_table(
        ai_prompt,
        requirement_content,
        extractor,
        validator,
        max_iterations
    )
