import os

from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_community.chat_message_histories import ChatMessageHistory

# 这个不能输出思考过程，暂时不用
def get_config(key, default=None):
    return os.getenv(key, default)

MODEL_NAME = get_config("MODEL_NAME", 'qwq-32b')
BASE_URL = get_config("BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
API_KEY = get_config("DASHSCOPE_API_KEY")


class LangChainCosmicTableGenerator:
    def __init__(self, model_name=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.chat = ChatOpenAI(
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
            model_name=self.model_name,
            streaming=True,
            callbacks=[StreamingStdOutCallbackHandler()],
            temperature=0,
            max_tokens=8192
        )
        self.chat_history = ChatMessageHistory()  # 初始化 ChatMessageHistory


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
        final_answer = ""

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
    max_iterations: int = 2
) -> str:
    generator = LangChainCosmicTableGenerator()
    return generator.generate_table(
        ai_prompt,
        requirement_content,
        extractor,
        validator,
        max_iterations
    )
