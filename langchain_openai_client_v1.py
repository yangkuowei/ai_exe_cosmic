import logging
from typing import Callable, Tuple, Any, Dict, List, Optional, TypeVar
import time
import threading

from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.chat_history import (
    BaseChatMessageHistory,
    InMemoryChatMessageHistory,
)
from langchain_core.runnables.history import RunnableWithMessageHistory

from ai_common import ModelConfig

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
T = TypeVar('T')

class ThreadLocalChatHistoryManager:
    """线程本地聊天历史管理类，每个线程独立实例"""
    
    def __init__(self):
        self.local = threading.local()

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        """获取或创建线程本地会话历史"""
        if not hasattr(self.local, 'store'):
            self.local.store = {}
        
        if session_id not in self.local.store:
            self.local.store[session_id] = InMemoryChatMessageHistory()
        
        return self.local.store[session_id]

history_manager = ThreadLocalChatHistoryManager()

class LangChainCosmicTableGenerator:
    def __init__(self, config: ModelConfig):
        """初始化表格生成器，验证配置有效性"""
        self._validate_config(config)
        self.config = config
        
        self.chat = ChatOpenAI(
            openai_api_key=config.api_key,
            openai_api_base=config.base_url,
            model_name=config.model_name,
            streaming=True,
            callbacks=[BaseCallbackHandler()],
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )

    def _validate_config(self, config: ModelConfig):
        """验证配置参数有效性"""
        if not config.api_key:
            raise ValueError("OpenAI API key未配置")
        if not config.model_name:
            raise ValueError("模型名称未配置")
        if config.temperature < 0 or config.temperature > 2:
            raise ValueError("temperature参数需在0-2之间")
        if config.max_tokens < 100:
            logger.warning("max_tokens值(%d)可能过小", config.max_tokens)

    def generate_table(
            self,
            cosmic_ai_prompt: str,
            requirement_content: str,
            extractor: Callable[[str], T],
            validator: Callable[[T], Tuple[bool, str]],
            max_chat_count: int = 3
    ) -> Optional[T]:
        """生成并验证COSMIC表格内容
        
        Args:
            cosmic_ai_prompt: COSMIC提示模板
            requirement_content: 需求内容文本
            extractor: 结果提取函数
            validator: 结果验证函数
            max_chat_count: 最大重试次数
            
        Returns:
            验证通过的结果或None
        """
        # 转义提示词中的大括号
        formatted_prompt = cosmic_ai_prompt.replace("{", "{{").replace("}", "}}")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", formatted_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        chain = prompt | self.chat
        
        with_message_history = RunnableWithMessageHistory(
            chain,
            history_manager.get_session_history,
        )

        session_id = f"thread_{threading.get_ident()}_time{time.time()}"
        config = {"configurable": {"session_id": session_id}}

        answer_buffer: List[str] = []
        self.chat.callbacks = [self._create_stream_callback(answer_buffer)]

        for attempt in range(max_chat_count + 1):
            try:
                logger.info("(线程：%s) 开始调用AI", threading.get_ident())
                response = with_message_history.invoke(
                    [HumanMessage(content=requirement_content)],
                    config=config,
                )
                logger.info("收到AI响应 (长度: %d 字符)(线程：%s)", len(response.content),threading.get_ident())

                full_answer = response.content
                extracted_data = extractor(full_answer)
                is_valid, error = validator(extracted_data)

                if is_valid:
                    logger.info(f"\n校验通过")
                    return extracted_data
                    
                if attempt == max_chat_count:
                    logger.error("历史对话次数已达最大次数(%d)", max_chat_count)
                    raise ValueError(f"验证失败：{error}")

                requirement_content = self._build_retry_prompt(error)
                logger.info(requirement_content)
                logger.info("第%d次重试，更新请求内容", attempt+1)

            except Exception as e:
                logger.error("生成过程中发生异常：%s", str(e))
                raise RuntimeError("COSMIC表格生成失败") from e

        return None

    def _create_stream_callback(self, buffer: List[str]) -> BaseCallbackHandler:
        """创建流式回调处理器"""
        class StreamCallback(BaseCallbackHandler):
            def on_llm_new_token(self, token: str, **kwargs) -> None:
                if token:
                    print(token, end='', flush=True)  # 实时流式输出
                    buffer.append(token)

        return StreamCallback()

    def _build_retry_prompt(self, error: str) -> str:
        """构建重试提示模板"""
        return f"""\n上次生成内容未通过验证：{error}
        \n
## 请根据以下要求重新生成：

1.  请严格遵循 **COSMIC 规范** 进行内容组织，并使用 **Markdown 语法** 进行格式化输出。
2.  在本次生成中，请 **仅修改** 上一版本输出中未能通过校验的部分。对于已经通过校验的部分，请 **保持其内容与上一版本完全一致**，无需进行任何调整。
3.  对于已修改的内容，**无需** 添加任何关于修改位置或修改内容的备注信息。

"""

def call_ai(
        ai_prompt: str,
        requirement_content: str,
        extractor: Callable[[str], Any],
        validator: Callable[[Any], Tuple[bool, str]],
        config: ModelConfig,
        max_chat_count: int = 5
) -> str:
    """调用AI生成表格的统一入口
    
    Args:
        ai_prompt: AI系统提示语
        requirement_content: 需求内容文本
        extractor: 结果提取函数
        validator: 结果验证函数
        config: 模型配置
        max_chat_count: 最大重试次数
        
    Returns:
        经过验证的最终结果
    """
    generator = LangChainCosmicTableGenerator(config=config)
    return generator.generate_table(
        ai_prompt,
        requirement_content,
        extractor,
        validator,
        max_chat_count
    )
