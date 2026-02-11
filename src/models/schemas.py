"""
数据模型定义 - 使用 Pydantic
"""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ==================== 配置相关 ====================

class AppConfig(BaseModel):
    """应用配置"""
    qmt_path: str = Field(default="", description="MiniQMT程序路径")
    account_id: str = Field(default="", description="证券账号")
    buy_amount_type: Literal["fixed", "average"] = Field(default="average", description="买入金额方式")
    fixed_amount: Optional[float] = Field(default=10000.0, description="固定金额（元）")
    order_type: Literal["limit", "market"] = Field(default="limit", description="交易单类型")
    notification_email: str = Field(default="", description="通知邮箱")


class AuthInfo(BaseModel):
    """登录认证信息"""
    username: str = Field(default="", description="用户名")
    encrypted_password: str = Field(default="", description="加密后的密码")
    access_token: str = Field(default="", description="访问令牌")
    remember_password: bool = Field(default=False, description="记住密码")
    auto_login: bool = Field(default=False, description="自动登录")


class StrategyConfig(BaseModel):
    """当前运行的策略配置"""
    strategy_id: int = Field(description="策略ID")
    strategy_name: str = Field(description="策略名称")
    history_id: int = Field(description="回测记录ID")
    history_note: str = Field(default="", description="回测记录备注")
    stop_profit_ratio: float = Field(default=0.1, description="止盈比例")
    stop_loss_ratio: float = Field(default=0.05, description="止损比例")
    execution_schedule: dict = Field(default_factory=dict, description="执行时间配置")
    parameters: dict = Field(default_factory=dict, description="策略参数")


# ==================== 交易相关 ====================

class Position(BaseModel):
    """持仓信息"""
    stock_code: str = Field(description="证券代码")
    stock_name: str = Field(default="", description="证券名称")
    volume: int = Field(description="持仓数量")
    can_use_volume: int = Field(default=0, description="可用数量")
    avg_price: float = Field(description="成本价")
    current_price: float = Field(default=0.0, description="当前价")
    market_value: float = Field(default=0.0, description="市值")
    profit_loss: float = Field(default=0.0, description="盈亏")
    profit_loss_ratio: float = Field(default=0.0, description="盈亏比例")
    stop_profit_price: float = Field(default=0.0, description="止盈价")
    stop_loss_price: float = Field(default=0.0, description="止损价")


class Asset(BaseModel):
    """账户资产"""
    cash: float = Field(default=0.0, description="可用资金")
    frozen_cash: float = Field(default=0.0, description="冻结资金")
    market_value: float = Field(default=0.0, description="持仓市值")
    total_asset: float = Field(default=0.0, description="总资产")


class TradeLog(BaseModel):
    """交易日志"""
    id: Optional[int] = Field(default=None, description="日志ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    level: Literal["INFO", "SUCCESS", "WARNING", "ERROR"] = Field(default="INFO", description="日志级别")
    message: str = Field(description="日志消息")
    details: Optional[dict] = Field(default=None, description="详细信息")


# ==================== 策略平台API相关 ====================

class LoginResult(BaseModel):
    """登录结果"""
    access_token: str = Field(description="访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    username: str = Field(description="用户名")
    role_name: Optional[str] = Field(default=None, description="角色名")


class StrategyInfo(BaseModel):
    """策略信息"""
    id: int = Field(description="策略ID")
    name: str = Field(description="策略名称")
    description: Optional[str] = Field(default="", description="策略描述")
    backtest_count: int = Field(default=0, description="回测次数")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")


class BacktestHistory(BaseModel):
    """回测历史记录"""
    id: int = Field(description="记录ID")
    backtest_time: Optional[datetime] = Field(default=None, description="回测时间")
    strategy_return: Optional[float] = Field(default=None, description="策略收益率")
    win_rate: Optional[float] = Field(default=None, description="胜率")
    annualized_return: Optional[float] = Field(default=None, description="年化收益率")
    max_drawdown: Optional[float] = Field(default=None, description="最大回撤")
    sharpe_ratio: Optional[float] = Field(default=None, description="夏普比率")


class BondInfo(BaseModel):
    """可转债信息"""
    code: str = Field(description="可转债代码")
    name: str = Field(default="", description="可转债名称")
    price: Optional[float] = Field(default=None, description="当前价格")
    trade_date: Optional[str] = Field(default=None, description="交易日期")


# ==================== 更新相关 ====================

class UpdateInfo(BaseModel):
    """更新信息"""
    has_update: bool = Field(default=False, description="是否有更新")
    current_version: str = Field(description="当前版本")
    latest_version: str = Field(default="", description="最新版本")
    download_url: str = Field(default="", description="下载地址")
    release_notes: str = Field(default="", description="更新说明")


class PositionRecord(BaseModel):
    """项目持仓记录"""
    id: Optional[int] = Field(default=None, description="记录ID")
    stock_code: str = Field(description="可转债代码")
    stock_name: str = Field(default="", description="可转债名称")
    volume: int = Field(description="持有数量")
    buy_price: float = Field(description="买入价格")
    buy_time: datetime = Field(description="买入时间")
    strategy_name: str = Field(default="", description="策略名称")
