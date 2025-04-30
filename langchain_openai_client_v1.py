import json
import logging
import os
import random
import threading
import time
from typing import Callable, Tuple, Any, Optional, TypeVar

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.chat_history import (
    BaseChatMessageHistory,
    InMemoryChatMessageHistory,
)
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI

from ai_common import ModelConfig
from decorators import ai_processor

# 配置基础控制台日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
base_logger = logging.getLogger(__name__)
T = TypeVar('T')

class ThreadLocalChatHistoryManager:
    """聊天历史管理类，每个实例独立"""
    
    def __init__(self):
        self.store = {}  # 存储会话历史
        self.logger = logging.getLogger(f'{__name__}.instance.{id(self)}')
        self.logger.setLevel(logging.DEBUG)
        
        # 配置日志handler
        if not self.logger.handlers:
            logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            
            hour_timestamp = time.strftime("%Y%m%d%H", time.localtime())
            log_file = os.path.join(logs_dir, f'app_{hour_timestamp}.log')
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(file_handler)
            
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(console_handler)
            
            self.logger.propagate = False
            self.logger.debug(f"实例 {id(self)} 已初始化")

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        try:
            self.logger.debug(f"获取会话历史 session_id={session_id}")
            
            if session_id not in self.store:
                self.logger.debug(f"创建新的会话历史 session_id={session_id}")
                self.store[session_id] = InMemoryChatMessageHistory()
            
            return self.store[session_id]
        except Exception as e:
            self.logger.error(f"处理会话历史时出错: {str(e)}")
            raise

    def get_chat_context(self, session_id: str, system_prompt: str = "") -> list:
        try:
            history = self.get_session_history(session_id)
            messages = []
            
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt,
                })
            
            for msg in history.messages:
                messages.append({
                    "role": msg.type,
                    "content": msg.content,
                })

            messages.append({
                "role": 'human',
                "content": '你真是太棒了！',
            })

            return messages
        except Exception as e:
            self.logger.error(f"获取聊天上下文失败: {str(e)}")
            return []

class StreamCallback(BaseCallbackHandler):
    def __init__(self, history_manager, session_id):
        self.token_count = 0
        self.history_manager = history_manager
        self.session_id = session_id

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.token_count += 1
        if self.token_count % 100 == 0:
            self.history_manager.logger.debug(f'{self.session_id}已处理{self.token_count}个token')

class LangChainCosmicTableGenerator:
    def __init__(self, config: ModelConfig):
        self._validate_config(config)
        self.config = config
        
        self.chat = ChatOpenAI(
            openai_api_key=config.api_key,
            openai_api_base=config.base_url,
            model_name=config.model_name,
            streaming=True,
            callbacks=[BaseCallbackHandler()],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            extra_body={"enable_thinking": True}
        )

    def _validate_config(self, config: ModelConfig):
        if not config.api_key:
            raise ValueError("OpenAI API key未配置")
        if not config.model_name:
            raise ValueError("模型名称未配置")
        if config.temperature < 0 or config.temperature > 2:
            raise ValueError("temperature参数需在0-2之间")
        if config.max_tokens < 100:
            base_logger.warning("max_tokens值(%d)可能过小", config.max_tokens)

    def generate_table(
            self,
            cosmic_ai_prompt: str,
            requirement_content: str,
            extractor: Callable[[str], T],
            validator: Callable[[T], Tuple[bool, str]],
            max_chat_count: int = 3,
            history_manager: Optional[ThreadLocalChatHistoryManager] = None
    ) -> Optional[T]:
        history_manager = history_manager or ThreadLocalChatHistoryManager()
        
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

        session_id = f"session_{int(time.time())}_{random.randint(10000, 99999)}"
        config = {"configurable": {"session_id": session_id}}

        self.chat.callbacks = [StreamCallback(history_manager, session_id)]

        for attempt in range(max_chat_count + 1):
            try:
                history_manager.logger.info(f"session_id={session_id} 开始调用AI")
                
                response = with_message_history.invoke(
                    [HumanMessage(content=requirement_content)],
                    config=config,
                )
                full_answer = response.content

                history_manager.logger.info("收到AI响应 (长度: %d 字符)", len(full_answer))
                history_manager.logger.info(f"收到AI响应内容 \n%s", full_answer)

                extracted_data = extractor(full_answer)
                
                is_valid, error = validator(extracted_data)
                if is_valid:
                    history_manager.logger.info(f"本轮AI生成内容校验通过")
                    chat_history_dir = os.path.join(os.path.dirname(__file__), 'chat_history')
                    os.makedirs(chat_history_dir, exist_ok=True)
                    history_file = os.path.join(chat_history_dir, f'{session_id}.json')

                    chat_context = history_manager.get_chat_context(session_id, cosmic_ai_prompt)
                    with open(history_file, 'w', encoding='utf-8') as f:
                        json.dump(chat_context, f, ensure_ascii=False, indent=2)

                    history_manager.logger.debug(f"聊天历史已保存到: {history_file}")
                    return extracted_data

                if attempt == max_chat_count:
                    raise ValueError(f"验证失败：{error}")

                requirement_content = self._build_retry_prompt(error)
                history_manager.logger.info(f"第{attempt+1}次重试，更新请求内容")
                history_manager.logger.info(requirement_content)

            except Exception as e:
                history_manager.logger.error("生成过程中发生异常：%s", str(e))
                raise RuntimeError("COSMIC表格生成失败") from e

        return None

    def _build_retry_prompt(self, error: str) -> str:
        return f"\n上次生成内容未通过验证：{error}\n请按提示逐点修改不通过内容，**其它内容不做改动**，然后输出完整的修改后的内容。"

@ai_processor(max_retries=3)
def call_ai(
        ai_prompt: str,
        requirement_content: str,
        extractor: Callable[[str], Any],
        validator: Callable[[Any], Tuple[bool, str]],
        config: ModelConfig,
        max_chat_count: int = 5
) -> str:
    history_manager = ThreadLocalChatHistoryManager()
    generator = LangChainCosmicTableGenerator(config=config)
    return generator.generate_table(
        ai_prompt,
        requirement_content,
        extractor,
        validator,
        max_chat_count,
        history_manager
    )
