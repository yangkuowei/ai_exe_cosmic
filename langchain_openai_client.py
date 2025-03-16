import os

from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_community.chat_message_histories import ChatMessageHistory

from ai_exe_cosmic.validate_cosmic_table import validate_cosmic_table, extract_table_from_text  # 保留原函数的导入

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
        )
        self.chat_history = ChatMessageHistory()  # 初始化 ChatMessageHistory


    def generate_table(self, cosmic_ai_promote, requirement_content):

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
            response = self.chat.invoke(self.chat_history.messages)

            #print("\n" + "=" * 20 + "思考过程" + "=" * 20 + "\n")
            #print(response.content)

            markdown_table_str = extract_table_from_text(response.content)
            is_valid, error = validate_cosmic_table(markdown_table_str)

            if is_valid:
                print("校验通过")
                final_answer = response.content
                break
            else:
                print(f"校验失败：{error}")
                # 添加 AI 消息和新的用户消息（错误信息）到 chat history
                self.chat_history.add_ai_message(response.content)
                self.chat_history.add_user_message(error)


            if conversation_idx >= 3:
                final_answer = response.content
                break

        return final_answer


def call_ai(cosmic_ai_promote, requirement_content):
    generator = LangChainCosmicTableGenerator()
    return generator.generate_table(cosmic_ai_promote, requirement_content)

