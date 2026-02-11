"""
PyWebView API 模块 - 暴露给前端调用的接口
"""
import json
import os
import threading
import time
from datetime import datetime
from typing import Any

from loguru import logger

from src.models.database import Database
from src.models.schemas import AppConfig, AuthInfo, StrategyConfig
from src.services.factorcat_service import FactorCatService
from src.services.qmt_service import QMTService
from src.services.scheduler_service import SchedulerService
from src.services.auto_trade_service import AutoTradeService
from src.services.notification_service import NotificationService
from src.services.update_service import UpdateService
from src.utils.crypto import decrypt_password, encrypt_password
from src.utils.logger import setup_logger
from src.utils.token_utils import is_token_expiring_soon
from src.utils.datetime_helper import now


class Api:
    """PyWebView API 类 - 所有方法都会暴露给前端 JavaScript 调用"""
    
    def __init__(self) -> None:
        try:
            # 初始化数据库
            logger.debug("正在初始化数据库...")
            self.db = Database()
            logger.debug("数据库初始化完成")
            
            # 初始化服务
            logger.debug("正在初始化服务...")
            try:
                self.factorcat = FactorCatService()
                logger.debug("FactorCatService 初始化完成")
            except Exception as factorcat_init_error:
                logger.exception(f"FactorCatService 初始化失败: {factorcat_init_error}")
                raise
            
            try:
                self.qmt = QMTService()
                logger.debug("QMTService 初始化完成")
            except Exception as qmt_init_error:
                logger.exception(f"QMTService 初始化失败: {qmt_init_error}")
                raise
            
            try:
                self.notification = NotificationService()
                logger.debug("NotificationService 初始化完成")
            except Exception as notification_init_error:
                logger.exception(f"NotificationService 初始化失败: {notification_init_error}")
                raise
            
            try:
                self.scheduler = SchedulerService(qmt=self.qmt)
                logger.debug("SchedulerService 初始化完成")
            except Exception as scheduler_init_error:
                logger.exception(f"SchedulerService 初始化失败: {scheduler_init_error}")
                raise
            
            try:
                self.update_service = UpdateService()
                logger.debug("UpdateService 初始化完成")
            except Exception as update_init_error:
                logger.exception(f"UpdateService 初始化失败: {update_init_error}")
                raise
            
            logger.debug("正在初始化自动交易服务...")
            try:
                self.auto_trade = AutoTradeService(
                    factorcat=self.factorcat,
                    qmt=self.qmt,
                    notification=self.notification,
                    database=self.db
                )
                logger.debug("AutoTradeService 初始化完成")
            except Exception as auto_trade_init_error:
                logger.exception(f"AutoTradeService 初始化失败: {auto_trade_init_error}")
                raise
            
            # 状态
            self._running = False
            self._log_entries: list[dict[str, Any]] = []

            # QMT健康检测和重连相关状态
            self._qmt_reconnect_count = 0  # 连续重连失败次数
            self._qmt_max_reconnect_attempts = 3  # 最大重连尝试次数
            self._qmt_last_health_check_time: datetime | None = None
            self._qmt_last_reconnect_time: datetime | None = None
            
            # 设置日志（如果之前没有设置）
            try:
                setup_logger()
            except Exception as logger_setup_error:
                logger.warning(f"日志设置失败（可能已设置）: {logger_setup_error}")
            
            try:
                self.scheduler.set_bond_selection_callback(self.auto_trade.execute_rebalance)
                self.scheduler.set_stop_profit_loss_callback(self.auto_trade.execute_stop_profit_loss_check)
                self.scheduler.set_qmt_health_check_callback(self._qmt_health_check_callback)
                self.scheduler.set_token_refresh_callback(self._refresh_token_if_needed)
                self.scheduler.set_refill_callback(self.auto_trade.execute_scheduled_refill)
                logger.debug("定时任务回调设置完成")
            except Exception as callback_setup_error:
                logger.exception(f"设置定时任务回调失败: {callback_setup_error}")
                raise
            
            try:
                self.auto_trade.set_log_callback(self._add_log)
                logger.debug("日志回调设置完成")
            except Exception as log_callback_error:
                logger.warning(f"设置日志回调失败: {log_callback_error}")
            
            logger.info("API 初始化完成")
            
        except Exception as init_error:
            logger.exception(f"API 初始化过程中发生异常: {init_error}")
            raise
    
    def _add_log(self, level: str, message: str) -> None:
        """添加日志条目"""
        entry = {
            'time': now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': level,
            'message': message
        }
        self._log_entries.insert(0, entry)
        # 限制日志条数
        if len(self._log_entries) > 200:
            self._log_entries = self._log_entries[:200]
    
    def _success(self, data: Any = None, message: str = "") -> dict[str, Any]:
        """返回成功结果"""
        return {'success': True, 'data': data, 'message': message}

    def _error(self, error: str) -> dict[str, Any]:
        """返回错误结果"""
        return {'success': False, 'error': error}
    
    # ==================== 登录相关 ====================
    
    def login(self, username: str, password: str, remember: bool = False, auto_login: bool = False) -> dict[str, Any]:
        """
        登录因子猫
        
        Args:
            username: 用户名
            password: 密码
            remember: 记住密码
            auto_login: 自动登录
        """
        try:
            logger.info(f"[登录] 收到登录请求 - 用户名: {username if username else '(空)'}, remember: {remember}, auto_login: {auto_login}")
            
            # 参数验证
            if not username or not username.strip():
                error_msg = "用户名不能为空"
                logger.warning(f"[登录失败] {error_msg}")
                self._add_log("ERROR", error_msg)
                return self._error(error_msg)
            
            if not password:
                error_msg = "密码不能为空"
                logger.warning(f"[登录失败] {error_msg}")
                self._add_log("ERROR", error_msg)
                return self._error(error_msg)
            
            username = username.strip()
            logger.info(f"[登录] 开始登录 - 用户名: {username}")
            
            try:
                logger.debug("[登录] 调用 FactorCatService.login")
                result = self.factorcat.login(username, password)
                logger.debug("[登录] FactorCatService.login 成功")
            except Exception as login_err:
                # 登录请求失败
                error_msg = str(login_err)
                logger.error(f"[登录失败] 用户名: {username}, 错误: {error_msg}", exc_info=True)
                self._add_log("ERROR", f"登录失败: {error_msg}")
                return self._error(error_msg)
            
            # 保存认证信息
            try:
                logger.debug(f"[登录] 保存认证信息 - remember: {remember}, auto_login: {auto_login}")
                auth_info = AuthInfo(
                    username=username,
                    encrypted_password=encrypt_password(password) if remember else '',
                    access_token=result.access_token,
                    remember_password=remember,
                    auto_login=auto_login
                )
                self.db.save_auth_info(auth_info)
                logger.debug(f"[登录] 认证信息保存成功")
                if auto_login:
                    self.scheduler.start()
                    self.scheduler.add_token_refresh_job(interval_minutes=30)
            except Exception as save_err:
                logger.warning(f"[登录] 保存认证信息失败: {save_err}，但登录成功", exc_info=True)
            
            self._add_log("SUCCESS", f"登录成功: {username}")
            logger.info(f"[登录成功] 用户名: {username}, 角色: {result.role_name}")
            
            return self._success({
                'username': result.username,
                'role_name': result.role_name
            })
            
        except Exception as login_error:
            error_msg = str(login_error)
            username_str = username if 'username' in locals() and username else '未知'
            logger.exception(f"[登录异常] 用户名: {username_str}, 错误: {error_msg}")
            self._add_log("ERROR", f"登录失败: {error_msg}")
            return self._error(f"登录失败: {error_msg}")
    
    def logout(self) -> dict[str, Any]:
        """登出"""
        try:
            self.factorcat.clear_token()
            self.db.clear_auth_token()
            
            # 停止自动交易
            if self._running:
                self.stop_trading()
            
            self._add_log("INFO", "已登出")
            return self._success()
            
        except Exception as api_error:
            return self._error(str(api_error))
    
    def get_saved_auth(self) -> dict[str, Any]:
        """获取保存的认证信息（用于记住密码和自动登录）"""
        try:
            auth = self.db.get_auth_info()
            
            if auth.remember_password and auth.username:
                password = decrypt_password(auth.encrypted_password) if auth.encrypted_password else ''
                return self._success({
                    'username': auth.username,
                    'password': password,
                    'remember_password': auth.remember_password,
                    'auto_login': auth.auto_login,
                    'has_token': bool(auth.access_token)
                })
            
            return self._success({
                'username': '',
                'password': '',
                'remember_password': False,
                'auto_login': False,
                'has_token': False
            })
            
        except Exception as api_error:
            return self._error(str(api_error))
    
    def auto_login_with_token(self) -> dict[str, Any]:
        """使用保存的 token 自动登录"""
        try:
            auth = self.db.get_auth_info()
            
            if auth.auto_login and auth.access_token:
                # 设置 token
                self.factorcat.set_token(auth.access_token)
                
                # 验证 token 是否有效（尝试获取策略列表）
                try:
                    self.factorcat.get_strategies(1, 1)
                    self.scheduler.start()
                    self.scheduler.add_token_refresh_job(interval_minutes=30)
                    self._add_log("SUCCESS", f"自动登录成功: {auth.username}")
                    return self._success({
                        'username': auth.username,
                        'success': True
                    })
                except Exception:
                    # Token 无效，清除
                    self.db.clear_auth_token()
                    self.factorcat.clear_token()
                    return self._success({'success': False})
            
            return self._success({'success': False})
            
        except Exception as api_error:
            return self._error(str(api_error))

    def _refresh_token_if_needed(self) -> None:
        """
        检查 token 是否即将过期，若是且已保存密码则自动重新登录刷新 token。
        仅供调度器回调使用，失败只打日志不抛异常。
        """
        try:
            auth = self.db.get_auth_info()
            if not auth.auto_login or not auth.access_token or not auth.remember_password:
                return
            password = decrypt_password(auth.encrypted_password) if auth.encrypted_password else ""
            if not auth.username or not password:
                return
            if not is_token_expiring_soon(auth.access_token, threshold_seconds=3600):
                return
            logger.info(f"[Token刷新] token 即将过期，正在重新登录: {auth.username}")
            result = self.factorcat.refresh_token(auth.username, password)
            new_auth = AuthInfo(
                username=auth.username,
                encrypted_password=auth.encrypted_password,
                access_token=result.access_token,
                remember_password=auth.remember_password,
                auto_login=auth.auto_login,
            )
            self.db.save_auth_info(new_auth)
            self._add_log("SUCCESS", f"Token 已自动刷新: {auth.username}")
            logger.info(f"[Token刷新] 成功: {auth.username}")
        except Exception as refresh_error:
            logger.warning(f"[Token刷新] 失败: {refresh_error}", exc_info=True)

    # ==================== 策略相关 ====================
    
    def get_strategies(self, page: int = 1, limit: int = 10, search: str | None = None) -> dict[str, Any]:
        """获取策略列表"""
        try:
            result = self.factorcat.get_strategies(page, limit, search)
            return self._success(result)
        except Exception as api_error:
            return self._error(str(api_error))
    
    def get_backtest_histories(self, strategy_id: int, page: int = 1, limit: int = 10) -> dict[str, Any]:
        """获取回测记录"""
        try:
            result = self.factorcat.get_backtest_histories(strategy_id, page, limit)
            return self._success(result)
        except Exception as api_error:
            return self._error(str(api_error))
    
    def select_strategy(self, strategy_id: int, strategy_name: str, history_id: int, history_note: str, execution_schedule: dict[str, Any] | None = None) -> dict[str, Any]:
        """选择运行策略"""
        try:
            # 获取策略参数
            params = self.factorcat.get_strategy_parameters(strategy_id, history_id)
            
            # 提取止盈止损参数（API返回驼峰命名：profitTargetRatio, stopLossRatio）
            stop_profit_ratio = params.get('profitTargetRatio', 0.1)
            stop_loss_ratio = params.get('stopLossRatio', 0.05)
            
            logger.info(f"策略参数 - 止盈比例: {stop_profit_ratio}, 止损比例: {stop_loss_ratio}")
            
            # 如果没有传入调度配置，使用默认值或从现有配置中获取
            if execution_schedule is None:
                existing_strategy = self.db.get_strategy_config()
                if existing_strategy and existing_strategy.execution_schedule:
                    execution_schedule = existing_strategy.execution_schedule
                else:
                    execution_schedule = {'type': 'daily', 'time': '14:50'}
            
            # 保存策略配置
            strategy_config = StrategyConfig(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                history_id=history_id,
                history_note=history_note,
                stop_profit_ratio=stop_profit_ratio,
                stop_loss_ratio=stop_loss_ratio,
                execution_schedule=execution_schedule,
                parameters=params
            )
            self.db.save_strategy_config(strategy_config)
            
            # 更新自动交易服务配置
            self.auto_trade.strategy_config = strategy_config
            
            self._add_log("SUCCESS", f"已选择策略: {strategy_name}")
            
            return self._success({
                'strategy_id': strategy_id,
                'strategy_name': strategy_name,
                'history_id': history_id,
                'history_note': history_note,
                'stop_profit_ratio': stop_profit_ratio,
                'stop_loss_ratio': stop_loss_ratio,
                'execution_schedule': execution_schedule
            })
            
        except Exception as strategy_error:
            self._add_log("ERROR", f"选择策略失败: {str(strategy_error)}")
            return self._error(str(strategy_error))
    
    def get_current_strategy(self) -> dict[str, Any]:
        """获取当前选择的策略"""
        try:
            strategy = self.db.get_strategy_config()
            if strategy:
                return self._success(strategy.model_dump())
            return self._success(None)
        except Exception as api_error:
            return self._error(str(api_error))
    
    def clear_strategy(self) -> dict[str, Any]:
        """清除当前策略"""
        try:
            self.db.clear_strategy_config()
            self.auto_trade.strategy_config = None
            self._add_log("INFO", "已清除策略选择")
            return self._success()
        except Exception as api_error:
            return self._error(str(api_error))
    
    def update_execution_schedule(self, execution_schedule: dict[str, Any]) -> dict[str, Any]:
        """更新选债调仓调度配置"""
        try:
            strategy = self.db.get_strategy_config()
            if not strategy:
                return self._error("请先选择运行策略")
            
            # 更新调度配置
            strategy.execution_schedule = execution_schedule
            self.db.save_strategy_config(strategy)
            
            # 更新自动交易服务配置
            self.auto_trade.strategy_config = strategy
            
            # 如果正在运行，更新调度任务
            if self._running and self.scheduler.is_running():
                self.scheduler.add_bond_selection_job(execution_schedule)
            
            self._add_log("SUCCESS", "调度配置已更新")
            return self._success()
            
        except Exception as schedule_error:
            self._add_log("ERROR", f"更新调度配置失败: {str(schedule_error)}")
            return self._error(str(schedule_error))
    
    # ==================== 配置相关 ====================
    
    def get_config(self) -> dict[str, Any]:
        """获取应用配置"""
        try:
            config = self.db.get_config()
            return self._success(config.model_dump())
        except Exception as api_error:
            return self._error(str(api_error))
    
    def save_config(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """保存应用配置"""
        try:
            config = AppConfig(**config_data)
            self.db.save_config(config)
            
            # 更新自动交易服务配置
            self.auto_trade.app_config = config
            
            # 配置邮件通知（只传递接收邮箱，SMTP配置使用程序默认值）
            if config.notification_email:
                self.notification.configure(receiver_email=config.notification_email)
            
            self._add_log("SUCCESS", "配置已保存")
            return self._success()
            
        except Exception as config_error:
            self._add_log("ERROR", f"保存配置失败: {str(config_error)}")
            return self._error(str(config_error))
    
    def validate_qmt_path(self, path: str) -> dict[str, Any]:
        """验证 QMT 路径"""
        try:
            is_valid = self.qmt.validate_path(path)
            return self._success({'valid': is_valid})
        except Exception as api_error:
            return self._error(str(api_error))
    
    # ==================== 交易相关 ====================
    
    def start_trading(self) -> dict[str, Any]:
        """启动自动交易"""
        try:
            # 检查策略
            strategy = self.db.get_strategy_config()
            if not strategy:
                return self._error("请先选择运行策略")
            
            # 检查配置
            config = self.db.get_config()
            if not config.qmt_path:
                return self._error("请先配置 MiniQMT 程序路径")
            if not config.account_id:
                return self._error("请先配置证券账号")
            
            # 验证 QMT 路径
            if not os.path.exists(config.qmt_path):
                return self._error(f"MiniQMT 路径不存在: {config.qmt_path}")
            
            # 连接 QMT
            self._add_log("INFO", "正在连接 QMT...")
            try:
                self.qmt.connect(config.qmt_path, config.account_id)
            except Exception as connect_error:
                error_msg = str(connect_error)
                # 提供更友好的错误提示
                if "xtquant" in error_msg.lower() or "import" in error_msg.lower():
                    return self._error(
                        f"QMT 模块加载失败: {error_msg}\n"
                        "请确认 MiniQMT 路径配置正确，路径应指向包含 xtquant 文件夹的目录"
                    )
                elif "连接" in error_msg or "connect" in error_msg.lower():
                    return self._error(
                        f"QMT 连接失败: {error_msg}\n"
                        "请确认：\n"
                        "1. MiniQMT 程序已启动并登录\n"
                        "2. 证券账号配置正确\n"
                        "3. MiniQMT 路径配置正确（应指向 userdata_mini 目录）"
                    )
                else:
                    raise
            
            # 更新配置
            self.auto_trade.set_config(config, strategy)
            
            # 配置邮件通知（只传递接收邮箱，SMTP配置使用程序默认值）
            if config.notification_email:
                self.notification.configure(receiver_email=config.notification_email)
            
            # 启动定时任务
            self.scheduler.start()

            # 添加止盈止损检查任务（每分钟）
            self.scheduler.add_stop_profit_loss_job(interval_minutes=1)

            # 添加选债任务（默认每天 9:30）
            schedule_config = strategy.execution_schedule or {'type': 'daily', 'time': '14:50'}
            self.scheduler.add_bond_selection_job(schedule_config)

            # 添加补仓任务（14:50）
            self.scheduler.add_refill_job(execute_time='14:50')

            # 添加QMT健康检测任务（每30秒）
            self.scheduler.add_qmt_health_check_job(interval_seconds=30)

            # 添加 token 刷新检查任务（每30分钟）
            self.scheduler.add_token_refresh_job(interval_minutes=30)

            # 重置重连计数器
            self._qmt_reconnect_count = 0
            
            self._running = True
            self._add_log("SUCCESS", "自动交易已启动")
            
            return self._success()
            
        except Exception as start_error:
            self._add_log("ERROR", f"启动失败: {str(start_error)}")
            return self._error(str(start_error))
    
    def stop_trading(self) -> dict[str, Any]:
        """停止自动交易"""
        try:
            # 停止定时任务
            self.scheduler.stop()
            
            # 断开 QMT
            self.qmt.disconnect()
            
            # 重置重连状态
            self._qmt_reconnect_count = 0
            self._qmt_last_health_check_time = None
            self._qmt_last_reconnect_time = None
            
            self._running = False
            self._add_log("INFO", "自动交易已停止")
            
            return self._success()
            
        except Exception as stop_error:
            self._add_log("ERROR", f"停止失败: {str(stop_error)}")
            return self._error(str(stop_error))

    def get_trading_status(self) -> dict[str, Any]:
        """获取交易状态"""
        try:
            return self._success({
                'running': self._running,
                'qmt_connected': self.qmt.is_connected(),
                'scheduler_running': self.scheduler.is_running(),
                'jobs': self.scheduler.get_jobs() if self.scheduler.is_running() else [],
                'qmt_reconnect_count': self._qmt_reconnect_count
            })
        except Exception as api_error:
            return self._error(str(api_error))

    def get_scheduler_status(self) -> dict[str, Any]:
        """获取调度器详细状态（用于调试定时任务问题）"""
        try:
            status = self.scheduler.get_scheduler_status()
            return self._success(status)
        except Exception as api_error:
            return self._error(str(api_error))

    def _qmt_health_check_callback(self) -> None:
        """QMT健康检测回调"""
        if not self._running:
            return
        
        try:
            self._qmt_last_health_check_time = now()
            
            # 执行健康检查（使用简单检查方法以保持向后兼容）
            is_healthy = self.qmt.health_check_simple(timeout=3.0)
            
            if not is_healthy:
                logger.warning("QMT健康检查失败，连接可能异常")
                self._add_log("WARNING", "QMT连接异常，尝试重连...")
                
                # 尝试重连
                self._reconnect_qmt()
            else:
                # 连接正常，重置重连计数器
                if self._qmt_reconnect_count > 0:
                    logger.info("QMT连接已恢复正常")
                    self._add_log("SUCCESS", "QMT连接已恢复正常")
                    self._qmt_reconnect_count = 0
                    
        except Exception as health_check_error:
            logger.error(f"QMT健康检测异常: {str(health_check_error)}")
            self._reconnect_qmt()
    
    def _reconnect_qmt(self) -> None:
        """尝试重连QMT"""
        try:
            # 检查是否超过最大重连次数
            if self._qmt_reconnect_count >= self._qmt_max_reconnect_attempts:
                error_msg = f"QMT重连失败次数已达上限({self._qmt_max_reconnect_attempts}次)，停止自动重连"
                logger.error(error_msg)
                self._add_log("ERROR", error_msg)
                
                # 发送通知
                try:
                    self.notification.send_trade_error_notification(
                        "QMT连接异常",
                        f"QMT连接异常且重连失败{self._qmt_max_reconnect_attempts}次，请手动检查QMT程序状态"
                    )
                except Exception as notify_error:
                    logger.warning(f"发送通知失败: {str(notify_error)}")
                
                return
            
            # 检查距离上次重连的时间（避免频繁重连）
            if self._qmt_last_reconnect_time:
                time_since_last_reconnect = (now() - self._qmt_last_reconnect_time).total_seconds()
                if time_since_last_reconnect < 60:  # 至少间隔60秒
                    return
            
            self._qmt_last_reconnect_time = now()
            self._qmt_reconnect_count += 1
            
            logger.info(f"尝试重连QMT (第{self._qmt_reconnect_count}次)...")
            self._add_log("INFO", f"尝试重连QMT (第{self._qmt_reconnect_count}次)...")
            
            # 获取配置
            config = self.db.get_config()
            if not config.qmt_path or not config.account_id:
                logger.error("QMT配置不完整，无法重连")
                return
            
            # 先断开旧连接
            try:
                self.qmt.disconnect()
            except Exception as disconnect_error:
                logger.warning(f"断开旧连接时出错: {str(disconnect_error)}")
            
            # 等待一下再重连
            time.sleep(2)
            
            # 尝试重连
            self.qmt.connect(config.qmt_path, config.account_id)
            
            # 验证连接是否成功
            if self.qmt.is_connected() and self.qmt.health_check():
                reconnect_attempts = self._qmt_reconnect_count  # 保存重连次数
                logger.success("QMT重连成功")
                self._add_log("SUCCESS", "QMT重连成功")
                self._qmt_reconnect_count = 0  # 重置计数器
                
                # 发送重连成功通知
                try:
                    self.notification.send_trade_success_notification(
                        "QMT重连成功",
                        f"QMT连接已恢复，重连次数: {reconnect_attempts}"
                    )
                except Exception as notify_error:
                    logger.warning(f"发送通知失败: {str(notify_error)}")
            else:
                raise Exception("重连后健康检查失败")
                
        except Exception as reconnect_error:
            error_msg = f"QMT重连失败: {str(reconnect_error)}"
            logger.error(error_msg)
            self._add_log("ERROR", error_msg)
            
            if self._qmt_reconnect_count >= self._qmt_max_reconnect_attempts:
                try:
                    self.notification.send_trade_error_notification(
                        "QMT重连失败",
                        f"QMT重连失败{self._qmt_max_reconnect_attempts}次: {str(reconnect_error)}，请手动检查QMT程序状态"
                    )
                except Exception as notify_error:
                    logger.warning(f"发送通知失败: {str(notify_error)}")
    
    def get_asset(self) -> dict[str, Any]:
        """获取账户资产"""
        try:
            if not self.qmt.is_connected():
                return self._success({
                    'cash': 0,
                    'frozen_cash': 0,
                    'market_value': 0,
                    'total_asset': 0
                })
            
            asset = self.qmt.get_asset()
            return self._success(asset.model_dump())
            
        except Exception as api_error:
            return self._error(str(api_error))
    
    def get_positions(self) -> dict[str, Any]:
        """获取持仓信息"""
        try:
            if not self.qmt.is_connected():
                return self._success([])
            
            positions = self.auto_trade.get_positions_with_quote()
            return self._success(positions)
            
        except Exception as api_error:
            return self._error(str(api_error))
    
    def get_logs(self, limit: int = 50) -> dict[str, Any]:
        """获取交易日志"""
        try:
            logs = self._log_entries[:limit]
            return self._success(logs)
        except Exception as api_error:
            return self._error(str(api_error))
    
    def trigger_rebalance(self) -> dict[str, Any]:
        """手动触发调仓（用于测试）"""
        try:
            if not self._running:
                return self._error("请先启动自动交易")
            
            # 在后台线程执行
            thread = threading.Thread(target=self.auto_trade.execute_rebalance)
            thread.start()
            
            return self._success(message="调仓任务已触发")
            
        except Exception as api_error:
            return self._error(str(api_error))
    
    # ==================== 更新相关 ====================
    
    def check_update(self) -> dict[str, Any]:
        """检查更新"""
        try:
            info = self.update_service.check_update()
            return self._success(info.model_dump())
        except Exception as api_error:
            return self._error(str(api_error))
    
    def get_version(self) -> dict[str, Any]:
        """获取当前版本"""
        return self._success({
            'version': self.update_service.get_current_version()
        })
    
    # ==================== 帮助相关 ====================
    
    def open_help_url(self) -> dict[str, Any]:
        """打开帮助链接（已移除外部链接）"""
        # 外部帮助链接已移除，如需帮助请查看本地文档
        return self._success({
            'message': '外部帮助链接已移除，请查看本地文档或联系技术支持'
        })
    
    def log_js_error(
        self,
        message: str,
        source: str = '',
        lineno: int = 0,
        colno: int = 0,
        error: str = '',
        stack: str | None = None,
    ) -> dict[str, Any]:
        """
        记录 JavaScript 错误到日志
        
        Args:
            message: 错误消息
            source: 错误来源文件
            lineno: 行号
            colno: 列号
            error: 错误对象字符串
            stack: 堆栈跟踪
        """
        try:
            error_details = {
                'message': message,
                'source': source,
                'line': lineno,
                'column': colno,
                'error': error,
                'stack': stack
            }
            
            # 构建详细的错误信息
            error_msg = f"[前端错误] {message}"
            if source:
                error_msg += f" | 文件: {source}"
            if lineno > 0:
                error_msg += f" | 位置: {lineno}:{colno}"
            if error and error != message:
                error_msg += f" | 详情: {error}"
            if stack:
                error_msg += f"\n堆栈跟踪:\n{stack}"
            
            # 记录到日志（使用 ERROR 级别，确保写入错误日志文件）
            logger.error(error_msg)
            self._add_log("ERROR", f"页面错误: {message}")
            
            return self._success()
        except Exception as log_error:
            logger.warning(f"记录 JavaScript 错误失败: {log_error}")
            return self._success()
    
    def log_js_debug(self, message: str, data: str | None = None) -> dict[str, Any]:
        """
        记录 JavaScript 调试信息到日志

        Args:
            message: 调试消息
            data: 附加数据（JSON 字符串）
        """
        try:
            debug_msg = f"[前端调试] {message}"
            if data:
                try:
                    data_obj = json.loads(data) if isinstance(data, str) else data
                    debug_msg += f" | 数据: {json.dumps(data_obj, ensure_ascii=False)}"
                except (json.JSONDecodeError, TypeError):
                    debug_msg += f" | 数据: {data}"
            
            # 记录到日志（使用 DEBUG 级别）
            logger.debug(debug_msg)
            
            return self._success()
        except Exception as debug_log_error:
            logger.warning(f"记录 JavaScript 调试信息失败: {debug_log_error}")
            return self._success()

