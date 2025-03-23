import os
from typing import Callable, Tuple, Any

from langchain_openai import ChatOpenAI
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_community.chat_message_histories import ChatMessageHistory
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


from cosmic_ai_cline import load_model_config, ModelConfig, ConfigurationError

# 加载模型配置
try:
    config = load_model_config(config_dir=os.path.dirname(__file__))
except ConfigurationError as e:
    raise RuntimeError(f"配置加载失败: {str(e)}")


class LangChainCosmicTableGenerator:
    def __init__(self, config: ModelConfig = config):
        if not config.api_key:
            raise ValueError(f"API key not found in environment variables")

        self.config = config
        self.chat = ChatOpenAI(
            openai_api_key=config.api_key,
            openai_api_base=config.base_url,
            model_name=config.model_name,
            streaming=True,
            callbacks=[StreamingStdOutCallbackHandler()],
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )
        self.chat_history = ChatMessageHistory()

    def generate_table(
            self,
            cosmic_ai_promote: str,
            requirement_content: str,
            extractor: callable,
            validator: callable,
            max_chat_cout: int = 3
    ) -> str:

        cosmic_ai_promote = cosmic_ai_promote.replace("{", "{{").replace("}", "{{")

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
            if conversation_idx > max_chat_cout:
                print("超过最大对话次数AI仍然未生成符合校验的内容，强制返回")
                return extracted_data

            user_centent = f"生成内容校验未通过: {error}\n**请严格按照cosmic编写规范重新输出完整内容**"
            print(user_centent)


def call_ai(
        ai_prompt: str,
        requirement_content: str,
        extractor: Callable[[str], Any],
        validator: Callable[[Any], Tuple[bool, str]],
        config: ModelConfig,
        max_chat_cout: int = 3
) -> str:
    """调用AI生成表格的统一入口
    
    Args:
        ai_prompt: AI系统提示语
        requirement_content: 需求内容文本
        extractor: 结果提取函数
        validator: 结果验证函数
        config: 模型配置
        max_chat_cout: 最大重试次数(与AI对话次数)
        stream_callback: 流式响应回调函数
        
    Returns:
        经过验证的最终结果
    """
    generator = LangChainCosmicTableGenerator(config=config)
    return generator.generate_table(
        ai_prompt,
        requirement_content,
        extractor,
        validator,
        max_chat_cout
    )
