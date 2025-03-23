import os
from typing import Callable, Tuple, Dict, List, Optional, TypeVar

from langchain_openai import ChatOpenAI
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_community.chat_message_histories import ChatMessageHistory
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from langchain_core.chat_history import (
    BaseChatMessageHistory,
    InMemoryChatMessageHistory,
)
from langchain_core.runnables.history import RunnableWithMessageHistory

store = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]


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

        cosmic_ai_promote = cosmic_ai_promote.replace("{", "\{").replace("}", "\}")
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    cosmic_ai_promote,
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        chain = prompt | self.chat

        with_message_history = RunnableWithMessageHistory(chain, get_session_history)


        config = {"configurable": {"session_id": "abcd"}}

        conversation_idx = 0

        user_centent = requirement_content
        while True:

            answer_content = []

            class StreamCallback(StreamingStdOutCallbackHandler):
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    if token:
                        print(token, end='', flush=True)  # 实时流式输出
                        answer_content.append(token)

            # 使用自定义回调重新初始化
            self.chat.callbacks = [StreamCallback()]

            response = with_message_history.invoke(
                [HumanMessage(content=user_centent)],
                config=config,
            )
            answer_content = ''.join(answer_content)

            extracted_data = extractor(answer_content)
            is_valid, error = validator(extracted_data)

            if is_valid:
                print("校验通过")
                return extracted_data
            if conversation_idx > max_iterations:
                print("超过最大对话次数AI仍然未生成符合校验的内容，强制返回")
                return extracted_data

            user_centent = f"生成内容校验未通过: {error}\n**请严格按照cosmic编写规范重新输出完整内容**"
            print(user_centent)


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
