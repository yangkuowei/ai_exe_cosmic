import functools
import time
import logging
from typing import Callable, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

def ai_processor(max_retries: int = 3, initial_delay: float = 1.0, max_delay: float = 10.0):
    """AI处理核心装饰器，集成重试、退避、日志和性能监控
    
    Args:
        max_retries: 最大重试次数
        initial_delay: 初始延迟时间(秒)
        max_delay: 最大延迟时间(秒)
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            stream_callback = kwargs.get('stream_callback')
            last_error = None
            current_delay = initial_delay
            
            for attempt in range(1, max_retries + 1):
                try:
                    start_time = time.monotonic()
                    result = func(*args, **kwargs)
                    elapsed = time.monotonic() - start_time
                    
                    logger.info(f"Successfully processed {func.__name__} in {elapsed:.2f}s")
                    return result
                except Exception as e:
                    last_error = e
                    error_type = e.__class__.__name__
                    
                    # 流式回调通知
                    if stream_callback:
                        stream_callback(f"\n⚠️ Attempt {attempt} failed ({error_type}), retrying...\n")
                    
                    logger.warning(f"Attempt {attempt}/{max_retries} failed: {str(e)}")
                    
                    if attempt < max_retries:
                        # 指数退避算法
                        sleep_time = min(current_delay * (2 ** (attempt-1)), max_delay)
                        time.sleep(sleep_time)
                        current_delay *= 1.5
            # 所有重试失败后处理
            error_msg = f"Failed after {max_retries} attempts. Last error: {str(last_error)}"
            logger.error(error_msg)
            if stream_callback:
                stream_callback(f"\n❌ {error_msg}\n")
            raise last_error
        return wrapper
    return decorator
