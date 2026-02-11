"""
加密工具模块 - 用于密码加密存储
"""
import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 应用密钥（实际生产中应该从环境变量或配置文件读取）
APP_SECRET = b"qmt_auto_secret_key_2024"


def _get_fernet() -> Fernet:
    """获取 Fernet 加密器"""
    # 使用 PBKDF2 从密钥派生加密密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"qmt_salt",
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(APP_SECRET))
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
        return ""

