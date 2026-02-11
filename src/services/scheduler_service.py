"""
定时任务调度服务
"""
from datetime import datetime, time
from typing import Any, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from loguru import logger

from src.utils.datetime_helper import now


class SchedulerService:
    """定时任务调度服务"""
    
    # 任务ID常量
    JOB_BOND_SELECTION = "bond_selection"
    JOB_STOP_PROFIT_LOSS = "stop_profit_loss"
    JOB_QMT_HEALTH_CHECK = "qmt_health_check"
    JOB_TOKEN_REFRESH = "token_refresh"
    JOB_REFILL = "refill"

    def __init__(self, qmt=None) -> None:
        self.scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
        self._running = False
        self._bond_selection_callback: Callable[[], None] | None = None
        self._stop_profit_loss_callback: Callable[[], None] | None = None
        self._qmt_health_check_callback: Callable[[], None] | None = None
        self._token_refresh_callback: Callable[[], None] | None = None
        self._refill_callback: Callable[[], None] | None = None
        # 调试日志时间跟踪（降低健康检查日志频率）
        self._last_health_log_time: datetime | None = None
        # QMT 服务，用于访问 xtdata
        self._qmt = qmt
    
    def start(self) -> None:
        """启动调度器"""
        if not self._running:
            # 添加事件监听器，用于调试定时任务执行情况
            def job_listener(event):
                if event.code == EVENT_JOB_EXECUTED:
                    logger.info(f"[APScheduler] 任务执行成功: {event.job_id}")
                elif event.code == EVENT_JOB_ERROR:
                    logger.error(f"[APScheduler] 任务执行出错: {event.job_id}, 异常: {event.exception}")
                elif event.code == EVENT_JOB_MISSED:
                    logger.warning(f"[APScheduler] 任务错过执行: {event.job_id}")

            self.scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
            logger.info("已添加 APScheduler 事件监听器")

            self.scheduler.start()
            self._running = True
            logger.info("定时任务调度器已启动")
    
    def stop(self) -> None:
        """停止调度器"""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("定时任务调度器已停止")
    
    def is_running(self) -> bool:
        """检查是否运行中"""
        return self._running
    
    def set_bond_selection_callback(self, callback: Callable) -> None:
        """设置选债任务回调"""
        self._bond_selection_callback = callback
    
    def set_stop_profit_loss_callback(self, callback: Callable) -> None:
        """设置止盈止损任务回调"""
        self._stop_profit_loss_callback = callback
    
    def set_qmt_health_check_callback(self, callback: Callable) -> None:
        """设置QMT健康检测任务回调"""
        self._qmt_health_check_callback = callback

    def set_token_refresh_callback(self, callback: Callable) -> None:
        """设置 token 刷新任务回调"""
        self._token_refresh_callback = callback

    def set_refill_callback(self, callback: Callable) -> None:
        """设置补仓任务回调"""
        self._refill_callback = callback

    def add_bond_selection_job(self, schedule_config: dict[str, Any]) -> None:
        """
        添加选债任务
        
        Args:
            schedule_config: 调度配置
                - type: 'daily' | 'weekly' | 'monthly'
                - time: '14:50' 执行时间（默认）
                - day_of_week: 0-6 (周一到周日，weekly时使用)
                - day_of_month: 1-31 (monthly时使用)
        """
        # 先移除旧任务
        self.remove_job(self.JOB_BOND_SELECTION)
        
        schedule_type = schedule_config.get('type', 'daily')
        execute_time = schedule_config.get('time', '14:50')
        
        # 解析时间
        hour, minute = map(int, execute_time.split(':'))
        
        # 构建 cron 表达式
        if schedule_type == 'daily':
            trigger = CronTrigger(hour=hour, minute=minute)
            logger.info(f"添加每日选债任务: {execute_time}")
            
        elif schedule_type == 'weekly':
            day_of_week = schedule_config.get('day_of_week', 0)  # 默认周一
            trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
            days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            logger.info(f"添加每周选债任务: {days[day_of_week]} {execute_time}")
            
        elif schedule_type == 'monthly':
            day_of_month = schedule_config.get('day_of_month', 1)  # 默认1号
            trigger = CronTrigger(day=day_of_month, hour=hour, minute=minute)
            logger.info(f"添加每月选债任务: {day_of_month}号 {execute_time}")
            
        else:
            logger.error(f"未知的调度类型: {schedule_type}")
            return
        
        self.scheduler.add_job(
            self._execute_bond_selection,
            trigger=trigger,
            id=self.JOB_BOND_SELECTION,
            name="选债调仓任务",
            replace_existing=True
        )
    
    def add_stop_profit_loss_job(self, interval_minutes: int = 1) -> None:
        """
        添加止盈止损检查任务
        
        Args:
            interval_minutes: 检查间隔（分钟）
        """
        # 先移除旧任务
        self.remove_job(self.JOB_STOP_PROFIT_LOSS)
        
        # 只在交易时间运行（9:30-11:30, 13:00-15:00）
        self.scheduler.add_job(
            self._execute_stop_profit_loss,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=self.JOB_STOP_PROFIT_LOSS,
            name="止盈止损检查任务",
            replace_existing=True
        )
        
        logger.info(f"添加止盈止损检查任务: 每 {interval_minutes} 分钟执行一次")
    
    def add_qmt_health_check_job(self, interval_seconds: int = 30) -> None:
        """
        添加QMT健康检测任务
        
        Args:
            interval_seconds: 检测间隔（秒），默认30秒
        """
        # 先移除旧任务
        self.remove_job(self.JOB_QMT_HEALTH_CHECK)
        
        self.scheduler.add_job(
            self._execute_qmt_health_check,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=self.JOB_QMT_HEALTH_CHECK,
            name="QMT健康检测任务",
            replace_existing=True
        )
        
        logger.info(f"添加QMT健康检测任务: 每 {interval_seconds} 秒执行一次")

    def add_token_refresh_job(self, interval_minutes: int = 30) -> None:
        """
        添加 token 刷新检查任务。

        Args:
            interval_minutes: 检查间隔（分钟），默认 30 分钟
        """
        self.remove_job(self.JOB_TOKEN_REFRESH)
        self.scheduler.add_job(
            self._execute_token_refresh,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=self.JOB_TOKEN_REFRESH,
            name="Token 刷新检查任务",
            replace_existing=True,
        )
        logger.info(f"添加 Token 刷新检查任务: 每 {interval_minutes} 分钟执行一次")

    def add_refill_job(self, execute_time: str = '14:50') -> None:
        """
        添加补仓任务（14:50 执行）

        Args:
            execute_time: 执行时间，默认 14:50
        """
        self.remove_job(self.JOB_REFILL)

        # 解析时间
        hour, minute = map(int, execute_time.split(':'))

        # 构建 cron 表达式
        trigger = CronTrigger(hour=hour, minute=minute)

        self.scheduler.add_job(
            self._execute_refill,
            trigger=trigger,
            id=self.JOB_REFILL,
            name="补仓任务",
            replace_existing=True
        )

        logger.info(f"添加补仓任务: 每天 {execute_time}")

    def remove_job(self, job_id: str) -> None:
        """移除任务"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"移除任务: {job_id}")
        except Exception as remove_error:
            logger.debug("移除任务失败（可能不存在）: %s, %s", job_id, remove_error)
    
    def remove_all_jobs(self) -> None:
        """移除所有任务"""
        self.scheduler.remove_all_jobs()
        logger.info("移除所有定时任务")
    
    def get_jobs(self) -> list[dict[str, Any]]:
        """获取所有任务"""
        jobs = self.scheduler.get_jobs()
        return [
            {
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else None
            }
            for job in jobs
        ]
    
    def _execute_bond_selection(self) -> None:
        """执行选债任务"""
        logger.info("开始执行选债调仓任务")

        if not self._is_trading_day():
            logger.info("[选债] 非交易日，跳过选债调仓")
            return

        if self._bond_selection_callback:
            try:
                self._bond_selection_callback()
            except Exception as bond_selection_error:
                logger.error(f"选债任务执行失败: {str(bond_selection_error)}")
        else:
            logger.warning("选债回调未设置")
    
    def _execute_stop_profit_loss(self) -> None:
        """执行止盈止损检查"""
        logger.info("[调度器触发] 止盈止损检查任务开始执行")

        if not self._is_trading_time():
            logger.debug("[止盈止损] 非交易时间，跳过检查")
            return

        if self._stop_profit_loss_callback:
            try:
                self._stop_profit_loss_callback()
            except Exception as stop_profit_loss_error:
                logger.error(f"止盈止损检查失败: {str(stop_profit_loss_error)}")
    
    def _execute_qmt_health_check(self) -> None:
        """执行QMT健康检测"""
        # 添加日志（降低频率，每5分钟输出一次）
        now = now()
        if self._last_health_log_time is None:
            self._last_health_log_time = now
        if (now - self._last_health_log_time).total_seconds() >= 300:  # 5分钟
            logger.info("[调度器触发] QMT健康检测任务运行中")
            self._last_health_log_time = now

        if self._qmt_health_check_callback:
            try:
                self._qmt_health_check_callback()
            except Exception as health_check_error:
                logger.error(f"QMT健康检测失败: {str(health_check_error)}")

    def _execute_token_refresh(self) -> None:
        """执行 token 刷新检查"""
        logger.debug("[调度器触发] Token刷新检查任务开始执行")

        if self._token_refresh_callback:
            try:
                self._token_refresh_callback()
            except Exception as token_refresh_error:
                logger.error(f"Token 刷新检查失败: {str(token_refresh_error)}")

    def _execute_refill(self) -> None:
        """执行补仓任务"""
        logger.info("[调度器触发] 补仓任务开始执行")

        if not self._is_trading_day():
            logger.info("[补仓] 非交易日，跳过补仓")
            return

        if self._refill_callback:
            try:
                self._refill_callback()
            except Exception as refill_error:
                logger.error(f"补仓任务执行失败: {str(refill_error)}")
        else:
            logger.warning("补仓回调未设置")

    def _is_trading_day(self) -> bool:
        """
        检查是否为交易日

        Returns:
            是否为交易日
        """
        from src.utils.datetime_helper import is_trading_day
        return is_trading_day(self._qmt)
    
    def _is_trading_time(self) -> bool:
        """
        检查是否在交易时间
        
        Returns:
            是否在交易时间
        """
        if not self._is_trading_day():
            return False
        
        now = now().time()
        
        # 上午交易时间: 9:30 - 11:30
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        
        # 下午交易时间: 13:00 - 15:00
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)
        
        return (morning_start <= now <= morning_end or 
                afternoon_start <= now <= afternoon_end)
    
    def trigger_bond_selection_now(self) -> None:
        """立即触发选债任务（用于测试）"""
        logger.info("手动触发选债任务")
        self._execute_bond_selection()
    
    def trigger_stop_profit_loss_now(self) -> None:
        """立即触发止盈止损检查（用于测试）"""
        logger.info("手动触发止盈止损检查")
        self._execute_stop_profit_loss()

    def get_scheduler_status(self) -> dict[str, Any]:
        """获取调度器详细状态（用于调试定时任务问题）"""
        jobs = self.scheduler.get_jobs()
        now = now()

        return {
            'running': self._running,
            'scheduler_state': self.scheduler.state if hasattr(self.scheduler, 'state') else 'unknown',
            'job_count': len(jobs),
            'jobs': [
                {
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else None,
                    'trigger': str(job.trigger),
                }
                for job in jobs
            ],
            'current_time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'timezone': str(self.scheduler.timezone),
        }

