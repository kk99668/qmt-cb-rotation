"""日期时间工具函数 - 统一使用上海时间"""
from datetime import datetime, timezone, timedelta
from loguru import logger

# 上海时区 (UTC+8)
SHANGHAI_TZ = timezone(timedelta(hours=8))

# 交易日缓存
_cached_trading_day_date: str | None = None
_cached_is_trading_day: bool | None = None


def now() -> datetime:
    """获取当前上海时间"""
    return datetime.now(SHANGHAI_TZ)


def now_str(fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    """获取当前上海时间的格式化字符串"""
    return now().strftime(fmt)


def is_trading_day(qmt_service=None) -> bool:
    """
    检查是否为交易日

    使用 xtdata.get_trading_dates() 查询上证指数的交易日历
    结果会缓存一天，避免重复调用 API

    Args:
        qmt_service: QMTService 实例，用于访问 xtdata

    Returns:
        是否为交易日
    """
    global _cached_trading_day_date, _cached_is_trading_day

    if qmt_service is None:
        # 降级处理：仅排除周末
        return now().weekday() < 5

    today = now().strftime('%Y%m%d')

    # 检查缓存（同一天直接返回缓存结果）
    if _cached_trading_day_date == today and _cached_is_trading_day is not None:
        return _cached_is_trading_day

    try:
        trading_dates = qmt_service.xtdata.get_trading_dates('SH', today, today)
        result = len(trading_dates) > 0

        # 更新缓存
        _cached_trading_day_date = today
        _cached_is_trading_day = result

        return result
    except Exception as e:
        # 异常时降级为周末判断
        logger.warning(f"获取交易日历失败，使用周末判断: {e}")
        return now().weekday() < 5
