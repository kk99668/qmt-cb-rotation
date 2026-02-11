"""
JWT token 解析工具 - 用于读取 token 过期时间
"""
import base64
import json
from datetime import datetime, timezone
from typing import Any, Optional


def parse_jwt_payload(token: str) -> Optional[dict[str, Any]]:
    """
    解析 JWT token，提取 payload（不验证签名）。

    Args:
        token: JWT token 字符串，格式为 header.payload.signature

    Returns:
        payload 字典，解析失败返回 None
    """
    if not token or not token.strip():
        return None
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1]
    try:
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def get_token_expiry_time(token: str) -> Optional[datetime]:
    """
    获取 token 的过期时间。

    Args:
        token: JWT token 字符串

    Returns:
        过期时间（UTC datetime），无 exp 或解析失败返回 None
    """
    payload = parse_jwt_payload(token)
    if not payload:
        return None
    exp = payload.get("exp")
    if exp is None:
        return None
    try:
        if isinstance(exp, (int, float)):
            return datetime.fromtimestamp(exp, tz=timezone.utc)
        return None
    except (ValueError, OSError):
        return None


def is_token_expiring_soon(
    token: str,
    threshold_seconds: int = 3600,
    now: Optional[datetime] = None,
) -> bool:
    """
    判断 token 是否即将过期。

    Args:
        token: JWT token 字符串
        threshold_seconds: 剩余时间小于等于该秒数时视为即将过期，默认 3600（1 小时）
        now: 当前时间，用于测试；默认使用当前 UTC 时间

    Returns:
        True 表示即将过期或已过期或无法解析，False 表示未即将过期
    """
    expiry = get_token_expiry_time(token)
    if expiry is None:
        return True
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    remaining = (expiry - now).total_seconds()
    return remaining <= threshold_seconds
