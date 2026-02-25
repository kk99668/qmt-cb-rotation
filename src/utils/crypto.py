"""
加密工具模块 - 用于密码加密存储
"""
import base64
import hashlib
import os
import platform
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger


def _get_machine_secret() -> bytes:
    """
    基于机器特征生成密钥种子

    使用机器名 + 用户名 + 应用名称的哈希值作为密钥种子，
    确保每台机器的密钥不同。
    """
    machine_name = platform.node()
    username = os.getlogin()
    app_identifier = "qmt-cb-rotation"

    # 组合特征并哈希
    combined = f"{machine_name}|{username}|{app_identifier}".encode('utf-8')
    return hashlib.sha256(combined).digest()


def _get_machine_salt() -> bytes:
    """基于机器特征生成 salt"""
    machine_name = platform.node()
    username = os.getlogin()
    combined = f"salt|{machine_name}|{username}".encode('utf-8')
    return hashlib.sha256(combined).digest()[:16]  # 取前16字节作为 salt


def _get_fernet() -> Fernet:
    """获取 Fernet 加密器"""
    # 使用机器特征作为密钥种子
    secret = _get_machine_secret()

    # 使用 PBKDF2 从密钥派生加密密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_get_machine_salt(),
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret))
    return Fernet(key)


def encrypt_password(password: str) -> str:
    """
    加密密码
    
    Args:
        password: 明文密码
        
    Returns:
        加密后的密码（base64编码）
    """
    if not password:
        return ""
    
    fernet = _get_fernet()
    encrypted = fernet.encrypt(password.encode('utf-8'))
    return base64.urlsafe_b64encode(encrypted).decode('utf-8')


def decrypt_password(encrypted_password: str) -> str:
    """
    解密密码
    
    Args:
        encrypted_password: 加密后的密码
        
    Returns:
        明文密码
    """
    if not encrypted_password:
        return ""
    
    try:
        fernet = _get_fernet()
        encrypted = base64.urlsafe_b64decode(encrypted_password.encode('utf-8'))
        decrypted = fernet.decrypt(encrypted)
        return decrypted.decode('utf-8')
    except Exception:
        # 解密失败可能是由于密钥变更，记录日志
        logger.warning("密码解密失败，可能是由于加密密钥变更（版本升级），请重新登录")
        return ""

