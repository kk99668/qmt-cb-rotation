"""
邮件通知服务
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from loguru import logger

from src.utils.datetime_helper import now_str


class NotificationService:
    """邮件通知服务"""
    
    # 默认 SMTP 配置（可通过环境变量覆盖）
    DEFAULT_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
    DEFAULT_SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
    DEFAULT_SMTP_USER = os.getenv("SMTP_USER", "")
    DEFAULT_SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    DEFAULT_SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
    
    def __init__(self):
        self.smtp_host: str = self.DEFAULT_SMTP_HOST
        self.smtp_port: int = self.DEFAULT_SMTP_PORT
        self.smtp_user: str = self.DEFAULT_SMTP_USER
        self.smtp_password: str = self.DEFAULT_SMTP_PASSWORD
        self.sender_email: str = self.DEFAULT_SENDER_EMAIL or self.DEFAULT_SMTP_USER
        self.receiver_email: str = ""
        self.enabled: bool = False
    
    def configure(self, receiver_email: str):
        """
        配置邮件服务（只配置接收邮箱，SMTP配置使用程序默认值）
        
        Args:
            receiver_email: 接收通知的邮箱
        """
        self.receiver_email = receiver_email
        
        # 如果有接收邮箱，则启用通知
        self.enabled = bool(receiver_email)
        
        if self.enabled:
            logger.info(f"邮件通知已配置，接收邮箱: {receiver_email}")
            if self.smtp_user and self.smtp_password:
                logger.info(f"SMTP服务器: {self.smtp_host}:{self.smtp_port}, 发送邮箱: {self.sender_email}")
            else:
                logger.warning("SMTP认证信息未配置，邮件将仅记录日志不会实际发送")
    
    def _send_email(self, subject: str, content: str, html: bool = False) -> bool:
        """
        发送邮件
        
        Args:
            subject: 邮件主题
            content: 邮件内容
            html: 是否为 HTML 格式
            
        Returns:
            是否发送成功
        """
        if not self.enabled:
            logger.debug("邮件通知未启用，跳过发送")
            return False
        
        if not self.receiver_email:
            logger.warning("未配置接收邮箱，无法发送通知")
            return False
        
        try:
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"【QMT】{subject}"
            msg['From'] = self.sender_email or "noreply@qmt-auto.local"
            msg['To'] = self.receiver_email
            
            # 邮件内容
            content_type = 'html' if html else 'plain'
            msg.attach(MIMEText(content, content_type, 'utf-8'))
            
            # 发送邮件
            if self.smtp_user and self.smtp_password:
                # 使用配置的 SMTP 服务器
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                # 仅记录日志，实际不发送（需要配置 SMTP）
                logger.info(f"邮件通知（未配置SMTP）: {subject}")
                logger.info(f"内容: {content}")
                return True
            
            logger.success(f"邮件发送成功: {subject}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            logger.error("邮件发送失败: SMTP 认证失败")
            return False
        except smtplib.SMTPConnectError:
            logger.error("邮件发送失败: 无法连接 SMTP 服务器")
            return False
        except Exception as e:
            logger.error(f"邮件发送失败: {str(e)}")
            return False
    
    def send_trade_success_notification(self, title: str, details: str):
        """
        发送交易成功通知
        
        Args:
            title: 通知标题
            details: 详细信息
        """
        now = now_str()
        content = f"""
        <h2>{title}</h2>
        <p><strong>时间:</strong> {now}</p>
        <p><strong>详情:</strong></p>
        <p>{details}</p>
        <hr>
        <p style="color: #888; font-size: 12px;">此邮件由QMT自动调仓程序发送</p>
        """
        self._send_email(title, content, html=True)
    
    def send_trade_error_notification(self, title: str, error_message: str):
        """
        发送交易失败通知
        
        Args:
            title: 通知标题
            error_message: 错误信息
        """
        now = now_str()
        content = f"""
        <h2 style="color: #e74c3c;">{title}</h2>
        <p><strong>时间:</strong> {now}</p>
        <p><strong>错误信息:</strong></p>
        <p style="color: #e74c3c;">{error_message}</p>
        <hr>
        <p style="color: #888; font-size: 12px;">此邮件由QMT自动调仓程序发送，请及时处理</p>
        """
        self._send_email(title, content, html=True)
    
    def send_suspended_notification(self, stock_code: str, stock_name: str = ""):
        """
        发送停牌通知（需要手动处理）
        
        Args:
            stock_code: 证券代码
            stock_name: 证券名称
        """
        now = now_str()
        name = f"({stock_name})" if stock_name else ""
        content = f"""
        <h2 style="color: #f39c12;">⚠️ 可转债停牌通知</h2>
        <p><strong>时间:</strong> {now}</p>
        <p><strong>证券代码:</strong> {stock_code} {name}</p>
        <p><strong>状态:</strong> 停牌中</p>
        <p style="color: #f39c12;"><strong>请您手动处理此持仓</strong></p>
        <hr>
        <p style="color: #888; font-size: 12px;">此邮件由QMT自动调仓程序发送</p>
        """
        self._send_email(f"停牌通知 - {stock_code}", content, html=True)
    
    def send_system_notification(self, title: str, message: str):
        """
        发送系统通知
        
        Args:
            title: 通知标题
            message: 消息内容
        """
        now = now_str()
        content = f"""
        <h2>{title}</h2>
        <p><strong>时间:</strong> {now}</p>
        <p>{message}</p>
        <hr>
        <p style="color: #888; font-size: 12px;">此邮件由QMT自动调仓程序发送</p>
        """
        self._send_email(title, content, html=True)
    
    def test_notification(self) -> bool:
        """
        测试邮件通知
        
        Returns:
            是否发送成功
        """
        return self._send_email(
            "测试通知",
            "<h2>测试邮件</h2><p>如果您收到此邮件，说明邮件通知配置正确。</p>",
            html=True
        )

