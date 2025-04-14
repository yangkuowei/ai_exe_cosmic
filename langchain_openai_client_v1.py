import logging
import os
from typing import Callable, Tuple, Any, Dict, List, Optional, TypeVar
import time
import threading
import random
import json

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

# 配置基础控制台日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
base_logger = logging.getLogger(__name__)
T = TypeVar('T')

class ThreadLocalChatHistoryManager:
    """线程本地聊天历史管理类，每个线程独立实例"""
    
    def __init__(self):
        self.local = threading.local()
        self._init_thread_logger()

    _logger_initialized = False
    _logger_lock = threading.Lock()

    def _init_thread_logger(self):
        """初始化线程特定日志，每小时一个日志文件"""
        if not hasattr(self.local, 'logger'):
            with ThreadLocalChatHistoryManager._logger_lock:
                if not ThreadLocalChatHistoryManager._logger_initialized:
                    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
                    os.makedirs(logs_dir, exist_ok=True)
                    
                    # 按小时生成日志文件名
                    hour_timestamp = time.strftime("%Y%m%d%H", time.localtime())
                    log_file = os.path.join(logs_dir, f'app_{hour_timestamp}.log')
                    
                    # 创建全局logger并设置DEBUG级别
                    logger = logging.getLogger(f'{__name__}.hourly')
                    logger.setLevel(logging.DEBUG)
                    
                    # 避免重复添加handler
                    if not logger.handlers:
                        # 文件handler
                        file_handler = logging.FileHandler(log_file)
                        file_handler.setLevel(logging.DEBUG)
                        file_handler.setFormatter(logging.Formatter(
                            '%(asctime)s [Thread-%(thread)d] - %(levelname)s - %(message)s'
                        ))
                        logger.addHandler(file_handler)
                        
                        # 控制台handler
                        console_handler = logging.StreamHandler()
                        console_handler.setLevel(logging.DEBUG)
                        console_handler.setFormatter(logging.Formatter(
                            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                        ))
                        logger.addHandler(console_handler)
                    
                    logger.propagate = False
                    ThreadLocalChatHistoryManager._logger_initialized = True
                
                self.local.logger = logging.getLogger(f'{__name__}.hourly')
                self.local.logger.debug(f"线程 {threading.get_ident()} 已连接日志系统")

    def _ensure_logger(self):
        """确保logger已初始化"""
        if not hasattr(self.local, 'logger'):
            self._init_thread_logger()

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        """获取或创建线程本地会话历史"""
        self._ensure_logger()
        try:
            self.local.logger.debug(f"获取会话历史 session_id={session_id}")
            if not hasattr(self.local, 'store'):
                self.local.logger.debug(f"初始化线程本地存储")
                self.local.store = {}
            
            if session_id not in self.local.store:
                self.local.logger.debug(f"创建新的会话历史 session_id={session_id}")
                self.local.store[session_id] = InMemoryChatMessageHistory()
            
            self.local.logger.debug(f"返回会话历史 session_id={session_id}")
            return self.local.store[session_id]
        except Exception as e:
            base_logger.error(f"处理会话历史时出错: {str(e)}")
            raise

    def get_chat_context(self, session_id: str, system_prompt: str = "", is_valid: bool = True) -> list:
        """获取指定session_id的完整聊天上下文
        
        Args:
            session_id: 会话ID
            system_prompt: 系统提示词
            is_valid: 是否校验通过
            
        Returns:
            包含所有消息的列表，每个消息为dict格式:
            {
                "role": "human|ai|system",
                "content": str,
                "timestamp": str
            }
        """
        self._ensure_logger()
        try:
            history = self.get_session_history(session_id)
            messages = []
            
            # 添加系统提示词
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt,
                })
            
            # 添加聊天历史
            for msg in history.messages:
                messages.append({
                    "role": msg.type,  # human/ai/system
                    "content": msg.content,
                })
            
            # 只有校验通过时才添加校验通过标记
            if is_valid:
                messages.append({
                    "role": 'human',
                    "content":'校验通过',
                })
            return messages
        except Exception as e:
            self.local.logger.error(f"获取聊天上下文失败: {str(e)}")
            return []

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
            try:
                history_manager._ensure_logger()
                history_manager.local.logger.warning("max_tokens值(%d)可能过小", config.max_tokens)
            except:
                base_logger.warning("max_tokens值(%d)可能过小", config.max_tokens)

    def generate_table(
            self,
            cosmic_ai_prompt: str,
            requirement_content: str,
            extractor: Callable[[str], T],
            validator: Callable[[T], Tuple[bool, str]],
            max_chat_count: int = 3
    ) -> Optional[T]:
        """生成并验证COSMIC表格内容
        history_manager.local.logger.info(f"开始生成表格")
        
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

        session_id = f"session_{int(time.time())}_{random.randint(10000, 99999)}"
        config = {"configurable": {"session_id": session_id}}

        self.chat.callbacks = [self._create_stream_callback(session_id)]

        for attempt in range(max_chat_count + 1):
            try:
                try:
                    history_manager._ensure_logger()
                    history_manager.local.logger.info(f"session_id={session_id} 开始调用AI")
                except:
                    base_logger.info("开始调用AI")
                response = with_message_history.invoke(
                    [HumanMessage(content=requirement_content)],
                    config=config,
                )
                full_answer = response.content

                history_manager.local.logger.info("收到AI响应 (长度: %d 字符)", len(full_answer))
                history_manager.local.logger.info(f"收到AI响应内容 \n%s", full_answer)

                extracted_data = extractor(full_answer)
                history_manager.local.logger.info(f"开始验证数据")
                is_valid, error = validator(extracted_data)
 
                if is_valid:
                    history_manager.local.logger.info(f"本轮AI生成内容校验通过")
                    # 保存聊天历史（校验成功时）
                    try:
                        chat_history_dir = os.path.join(os.path.dirname(__file__), 'chat_history')
                        os.makedirs(chat_history_dir, exist_ok=True)
                        history_file = os.path.join(chat_history_dir, f'{session_id}.json')

                        chat_context = history_manager.get_chat_context(session_id, cosmic_ai_prompt, is_valid=True)
                        with open(history_file, 'w', encoding='utf-8') as f:
                            json.dump(chat_context, f, ensure_ascii=False, indent=2)
                        
                        history_manager.local.logger.debug(f"聊天历史已保存到: {history_file}")
                    except Exception as e:
                        history_manager.local.logger.error(f"保存聊天历史失败: {str(e)}")
                    
                    return extracted_data

                if attempt == max_chat_count:
                    # 保存聊天历史（达到最大尝试次数时）
                    try:
                        chat_history_dir = os.path.join(os.path.dirname(__file__), 'chat_history')
                        os.makedirs(chat_history_dir, exist_ok=True)
                        history_file = os.path.join(chat_history_dir, f'{session_id}.json')

                        chat_context = history_manager.get_chat_context(session_id, cosmic_ai_prompt, is_valid=False)
                        with open(history_file, 'w', encoding='utf-8') as f:
                            json.dump(chat_context, f, ensure_ascii=False, indent=2)
                        
                        history_manager.local.logger.debug(f"聊天历史已保存到: {history_file}")
                    except Exception as e:
                        history_manager.local.logger.error(f"保存聊天历史失败: {str(e)}")
                    
                if attempt == max_chat_count:
                    history_manager.local.logger.error("历史对话次数已达最大次数(%d)", max_chat_count)
                    raise ValueError(f"验证失败：{error}")

                requirement_content = self._build_retry_prompt(error)
                history_manager.local.logger.info(f"构建重试提示")
                history_manager.local.logger.info(requirement_content)
                history_manager.local.logger.info(f"第{attempt+1}次重试，更新请求内容")

            except Exception as e:
                history_manager.local.logger.error("生成过程中发生异常：%s", str(e))
                raise RuntimeError("COSMIC表格生成失败") from e

        return None

    def _create_stream_callback(self,session_id) -> BaseCallbackHandler:
        """创建流式回调处理器"""
        class StreamCallback(BaseCallbackHandler):
            def __init__(self):
                self.token_count = 0

            def on_llm_new_token(self, token: str, **kwargs) -> None:
                self.token_count += 1
                if self.token_count % 100 == 0:
                    history_manager.local.logger.debug(f'{session_id}已处理{self.token_count}个token')



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
