"""
重试装饰器 - 为不稳定的方法添加自动重试能力
"""
import time
from functools import wraps
from typing import Callable, Tuple, Type
from loguru import logger


def retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    重试装饰器

    Args:
        max_attempts: 最大尝试次数（包括第一次调用）
        initial_delay: 初始重试间隔（秒）
        backoff_factor: 退避系数，每次重试间隔 = 上次间隔 * backoff_factor
        exceptions: 需要重试的异常类型

    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # 检查是否是最后一次尝试
                    if attempt == max_attempts - 1:
                        break

                    # 检查异常类型是否需要重试
                    if not isinstance(e, exceptions):
                        break

                    # 计算重试间隔
                    delay = initial_delay * (backoff_factor ** attempt)

                    logger.warning(
                        f"{func.__name__} 调用失败 (第 {attempt + 1}/{max_attempts} 次): {e}"
                        f"，{delay:.1f} 秒后重试..."
                    )

                    time.sleep(delay)

            # 所有重试都失败，抛出最后一次异常
            logger.error(f"{func.__name__} 调用失败，已达最大重试次数 ({max_attempts})")
            raise last_exception

        return wrapper
    return decorator
