"""
日志工具模块
"""
import os
import sys
from loguru import logger
from typing import Callable, Optional

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')

# 日志回调函数（用于将日志推送到前端）
_log_callback: Optional[Callable] = None


def setup_logger(log_dir: str = None, log_callback: Callable = None):
    """
    设置日志配置
    
    Args:
        log_dir: 日志目录，默认为项目 logs 目录
        log_callback: 日志回调函数，用于将日志推送到前端
    """
    global _log_callback
    _log_callback = log_callback
    
    # 创建日志目录
    log_path = log_dir or LOG_DIR
    os.makedirs(log_path, exist_ok=True)
    
    # 移除默认处理器
    logger.remove()
    
    # 添加控制台输出（仅在非服务器环境或调试模式下）
    # 在服务器环境下，如果没有控制台窗口，sys.stdout 可能不可用，所以使用 try-except
    try:
        # 检查是否有控制台（在 Windows Server 上可能没有）
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            logger.add(
                sys.stdout,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                level="DEBUG",
                colorize=True
            )
        else:
            # 没有控制台，但仍然尝试添加（可能会失败，但不影响文件日志）
            logger.add(
                sys.stdout,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                level="INFO",
                colorize=False
            )
    except Exception:
        # 如果控制台输出失败（例如在服务器环境下），忽略错误，继续使用文件日志
        pass
    
    # 添加文件输出（INFO及以上级别）
    log_file = os.path.join(log_path, "app_{time:YYYY-MM-DD}.log")
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO",
        rotation="00:00",  # 每天轮转
        retention="30 days",  # 保留30天
        compression="zip",  # 压缩旧日志
        encoding="utf-8",
        enqueue=True,  # 异步写入，提高性能
        backtrace=True,  # 记录堆栈跟踪
        diagnose=True  # 显示变量值
    )
    
    # 添加错误日志文件（ERROR及以上级别，包含完整堆栈信息）
    error_log_file = os.path.join(log_path, "error_{time:YYYY-MM-DD}.log")
    logger.add(
        error_log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
        level="ERROR",
        rotation="00:00",  # 每天轮转
        retention="90 days",  # 保留90天
        compression="zip",  # 压缩旧日志
        encoding="utf-8",
        enqueue=True,  # 异步写入
        backtrace=True,  # 记录堆栈跟踪
        diagnose=True  # 显示变量值
    )
    
    # 添加自定义处理器（用于推送到前端）
    if log_callback:
        logger.add(
            _frontend_sink,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            level="INFO"
        )
    
    logger.info("日志系统初始化完成")


def _frontend_sink(message):
    """将日志推送到前端的处理器"""
    if _log_callback:
        record = message.record
        log_entry = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S"),
            "level": record["level"].name,
            "message": record["message"]
        }
        try:
            _log_callback(log_entry)
        except Exception:
            pass  # 忽略回调错误


def get_logger(name: str = None):
    """
    获取 logger 实例
    
    Args:
        name: 日志名称
        
    Returns:
        logger 实例
    """
    if name:
        return logger.bind(name=name)
    return logger

