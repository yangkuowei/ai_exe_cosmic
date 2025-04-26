import logging
import os
import time
import threading
import random
import json
from typing import Callable, Tuple, Any, Optional, TypeVar
import openai
from openai import OpenAI
from ai_common import ModelConfig
from decorators import ai_processor

# 配置基础日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
base_logger = logging.getLogger(__name__)
T = TypeVar('T')


class ThreadLocalChatHistoryManager:
    """线程本地聊天历史管理类"""

    def __init__(self):
        self.local = threading.local()
        self._init_thread_logger()

    _logger_initialized = False
    _logger_lock = threading.Lock()

    def _init_thread_logger(self):
        """初始化线程特定日志"""
        if not hasattr(self.local, 'logger'):
            with ThreadLocalChatHistoryManager._logger_lock:
                if not ThreadLocalChatHistoryManager._logger_initialized:
                    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
                    os.makedirs(logs_dir, exist_ok=True)

                    hour_timestamp = time.strftime("%Y%m%d%H", time.localtime())
                    log_file = os.path.join(logs_dir, f'app_{hour_timestamp}.log')

                    logger = logging.getLogger(f'{__name__}.hourly')
                    logger.setLevel(logging.WARN)

                    if not logger.handlers:
                        file_handler = logging.FileHandler(log_file)
                        file_handler.setLevel(logging.WARN)
                        file_handler.setFormatter(logging.Formatter(
                            '%(asctime)s [Thread-%(thread)d] - %(levelname)s - %(message)s'
                        ))
                        logger.addHandler(file_handler)

                        console_handler = logging.StreamHandler()
                        console_handler.setLevel(logging.WARN)
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

    def get_session_history(self, session_id: str) -> list:
        """获取或创建线程本地会话历史"""
        self._ensure_logger()
        try:
            self.local.logger.debug(f"获取会话历史 session_id={session_id}")
            if not hasattr(self.local, 'store'):
                self.local.logger.debug("初始化线程本地存储")
                self.local.store = {}

            if session_id not in self.local.store:
                self.local.logger.debug(f"创建新的会话历史 session_id={session_id}")
                self.local.store[session_id] = []

            return self.local.store[session_id]
        except Exception as e:
            base_logger.error(f"处理会话历史时出错: {str(e)}")
            raise

    def get_chat_context(self, session_id: str) -> list:
        """获取完整聊天上下文"""
        self._ensure_logger()
        try:
            history = self.get_session_history(session_id)
            messages = []

            for msg in history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

            return messages
        except Exception as e:
            self.local.logger.error(f"获取聊天上下文失败: {str(e)}")
            return []

    def add_session_history(self, session_id: str, message: dict) -> None:
        """添加消息到会话历史"""
        self._ensure_logger()
        try:
            history = self.get_session_history(session_id)
            history.append(message)
            self.local.logger.debug(f"已添加消息到会话 {session_id}: {message}")
        except Exception as e:
            self.local.logger.error(f"添加会话历史失败: {str(e)}")
            raise

    def remove_session_history(self, session_id: str, index: int) -> None:
        """添加消息到会话历史"""
        self._ensure_logger()
        try:
            history = self.get_session_history(session_id)
            message = history.pop(index)
            self.local.logger.debug(f"已删除记忆 {session_id}: {message}")
        except Exception as e:
            self.local.logger.error(f"删除记忆失败: {str(e)}")
            raise


history_manager = ThreadLocalChatHistoryManager()


class OpenAIClient:
    def __init__(self, config: ModelConfig):
        """初始化OpenAI客户端"""
        self._validate_config(config)
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )

    def _validate_config(self, config: ModelConfig):
        """验证配置参数"""
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
        """生成并验证COSMIC表格内容"""
        session_id = f"session_{int(time.time())}_{random.randint(10000, 99999)}"
        # history = history_manager.get_session_history(session_id)
        # 初始化消息历史

        history_manager.add_session_history(session_id, {"role": "system", "content": cosmic_ai_prompt})
        history_manager.add_session_history(session_id, {"role": "user", "content": requirement_content})

        for attempt in range(max_chat_count + 1):
            try:
                history_manager._ensure_logger()
                history_manager.local.logger.info(f"session_id={session_id} 开始调用AI")

                # 调用OpenAI API（流式模式）
                response = self.client.chat.completions.create(
                    model=self.config.model_name,
                    messages=history_manager.get_session_history(session_id),
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    stream=True
                )

                # 收集流式响应内容并实时处理
                reasoning_content, full_answer = process_stream_response(response)
                history_manager.add_session_history(session_id, {"role": "assistant", "content": full_answer})

                history_manager.local.logger.info("收到AI响应 (长度: %d 字符)", len(full_answer))

                # 提取和验证结果
                extracted_data = extractor(full_answer)
                is_valid, error = validator(extracted_data)

                if is_valid:
                    history_manager.add_session_history(session_id, {"role": "user", "content": '本轮生成内容通过了校验，你真是太棒了！'})
                    history_manager.local.logger.info("本轮AI生成内容校验通过")
                    self._save_chat_history(session_id)
                    return extracted_data

                if attempt == max_chat_count:
                    history_manager.add_session_history(session_id, {"role": "user", "content": '本轮生成内容没有通过校验，你真是太蠢了！你还需要努力学习！'})
                    self._save_chat_history(session_id)
                    history_manager.local.logger.error("历史对话次数已达最大次数(%d)", max_chat_count)
                    raise ValueError(f"验证失败：{error}")

                # 构建重试提示
                retry_prompt = self._build_retry_prompt(error)

                history_manager.add_session_history(session_id, {"role": "user", "content": retry_prompt})

                history_manager.local.logger.info(retry_prompt)
                history_manager.local.logger.info(f"第{attempt + 1}次重试，更新请求内容")

                # 只保存最近的记忆，中间的不重要
                history = history_manager.get_session_history(session_id)
                if len(history) >= 8:
                    history_manager.remove_session_history(session_id, 2)
                    history_manager.remove_session_history(session_id, 2)


            except Exception as e:
                history_manager.local.logger.error("生成过程中发生异常：%s", str(e))
                raise RuntimeError("生成过程中发生异常") from e

        return None

    def _save_chat_history(self, session_id: str):
        """保存聊天历史到文件"""
        try:
            chat_history_dir = os.path.join(os.path.dirname(__file__), 'chat_history')
            os.makedirs(chat_history_dir, exist_ok=True)
            history_file = os.path.join(chat_history_dir, f'{session_id}.json')

            chat_context = history_manager.get_chat_context(session_id)
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(chat_context, f, ensure_ascii=False, indent=2)

            history_manager.local.logger.debug(f"聊天历史已保存到: {history_file}")
        except Exception as e:
            history_manager.local.logger.error(f"保存聊天历史失败: {str(e)}")

    def _build_retry_prompt(self, error: str) -> str:
        """构建重试提示模板"""
        return f"\n上次生成内容未通过验证：{error}\n请按提示逐点修改不通过内容，**其它内容不做改动**，然后输出完整的修改后的内容。"


def process_stream_response(completion) -> Tuple[str, str]:
    """处理流式响应并返回推理过程和回答内容"""
    reasoning_content = []
    answer_content = []

    for chunk in completion:
        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            reasoning_content.append(delta.reasoning_content)
            # logger.debug(f"推理内容: {delta.reasoning_content}")
            #print(delta.reasoning_content, end='', flush=True)  # 实时流式输出到控制台

        if delta.content:
            answer_content.append(delta.content)
            #print(delta.content, end='', flush=True)  # 实时流式输出到控制台

    return ''.join(reasoning_content), ''.join(answer_content)

@ai_processor(max_retries=3)
def call_ai(
        ai_prompt: str,
        requirement_content: str,
        extractor: Callable[[str], Any],
        validator: Callable[[Any], Tuple[bool, str]],
        config: ModelConfig,
        max_chat_count: int = 4
) -> str:
    """调用AI生成表格的统一入口"""
    client = OpenAIClient(config=config)
    return client.generate_table(
        ai_prompt,
        requirement_content,
        extractor,
        validator,
        max_chat_count
    )
