import os
import threading
import logging
import logging.handlers
import queue
from typing import Callable, Tuple, Any, Dict, List, Optional, TypeVar, Awaitable
from threading import Lock
import asyncio

# 配置线程安全的日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.handlers.QueueHandler(queue.Queue(-1))  # 无界队列
logger.addHandler(handler)

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

T = TypeVar('T')

class ChatHistoryManager:
    """线程安全的聊天历史管理类，支持LRU缓存"""
    
    def __init__(self, max_sessions: int = 100):
        self.store: Dict[str, BaseChatMessageHistory] = {}
        self.lock = Lock()
        self.max_sessions = max_sessions
        self.lru: List[str] = []

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        """获取或创建会话历史，自动清理最久未使用的会话"""
        with self.lock:
            # LRU缓存清理
            while len(self.store) >= self.max_sessions:
                oldest = self.lru.pop(0)
                del self.store[oldest]

            if session_id not in self.store:
                self.store[session_id] = InMemoryChatMessageHistory()
                self.lru.append(session_id)
            else:
                # 更新LRU顺序
                self.lru.remove(session_id)
                self.lru.append(session_id)
            return self.store[session_id]

history_manager = ChatHistoryManager()

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

        session_id = f"session_{os.getpid()}_{id(self)}"
        config = {"configurable": {"session_id": session_id}}

        answer_buffer: List[str] = []
        #self.chat.callbacks = [self._create_stream_callback(answer_buffer)]

        logger.info(f"开始调用AI模型 (线程ID: {threading.get_ident()})")
        #logger.debug(f"请求参数摘要:\n提示模板: {cosmic_ai_prompt[:100]}...\n需求内容: {requirement_content[:200]}...")
        
        for attempt in range(max_chat_count + 1):
            try:
                logger.info(f"第 {attempt + 1}/{max_chat_count + 1} 次尝试 (线程ID: {threading.get_ident()})")
                response =  with_message_history.invoke(
                    [HumanMessage(content=requirement_content)],
                    config=config,
                )
                logger.info("收到AI响应 (长度: %d 字符)", len(response.content))

                full_answer = response.content
                extracted_data = extractor(full_answer)
                is_valid, error = validator(extracted_data)

                if is_valid:
                    logger.info(f"校验通过 (线程ID: {threading.get_ident()})")
                    return extracted_data
                    
                if attempt == max_chat_count:
                    logger.error("历史对话次数已达最大次数(%d)", max_chat_count)
                    raise ValueError(f"验证失败：{error}")

                requirement_content = self._build_retry_prompt(error)
                logger.warning("验证未通过: %s", error)
                #logger.info("更新请求内容准备重试:\n%s", requirement_content[:300])

            except Exception as e:
                logger.error("生成过程中发生异常：%s", str(e))
                raise RuntimeError("COSMIC表格生成失败") from e
            finally:
                answer_buffer.clear()

        return None

    # def _create_stream_callback(self, buffer: List[str]) -> BaseCallbackHandler:
    #     """创建流式回调处理器"""
    #     class StreamCallback(BaseCallbackHandler):
    #         def on_llm_new_token(self, token: str, **kwargs) -> None:
    #             if token:
    #                 print(token, end='', flush=True)  # 实时流式输出
    #                 buffer.append(token)
    #
    #     return StreamCallback()

    def _build_retry_prompt(self, error: str) -> str:
        """构建重试提示模板"""
        return f"""\n上次生成内容未通过验证：{error}
请根据以下要求重新生成：
1. 严格遵循COSMIC规范，使用markdown语法输出
2. 仅修改校验不通过的内容，已通过的内容不再修改按照上个输出版本的内容输出
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
