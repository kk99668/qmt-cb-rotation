"""
数据库模块 - SQLite 本地存储
"""
import os
import json
from datetime import datetime, timedelta
from typing import Any
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, Float, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from .schemas import AppConfig, AuthInfo, StrategyConfig, TradeLog, PositionRecord
from src.utils.datetime_helper import now

# 数据库文件路径
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
DB_PATH = os.path.join(DB_DIR, 'config.db')

Base = declarative_base()


# ==================== 数据库表定义 ====================

class ConfigTable(Base):
    """配置表"""
    __tablename__ = 'app_config'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now)


class AuthTable(Base):
    """认证信息表"""
    __tablename__ = 'auth_info'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(100), default='')
    encrypted_password = Column(Text, default='')
    access_token = Column(Text, default='')
    remember_password = Column(Boolean, default=False)
    auto_login = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=now, onupdate=now)


class StrategyTable(Base):
    """当前策略配置表"""
    __tablename__ = 'current_strategy'
    
    id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, nullable=True)
    strategy_name = Column(String(200), default='')
    history_id = Column(Integer, nullable=True)
    history_note = Column(String(500), default='')
    stop_profit_ratio = Column(Float, default=0.1)
    stop_loss_ratio = Column(Float, default=0.05)
    execution_schedule = Column(Text, default='{}')  # JSON
    parameters = Column(Text, default='{}')  # JSON
    updated_at = Column(DateTime, default=now, onupdate=now)


class TradeLogTable(Base):
    """交易日志表"""
    __tablename__ = 'trade_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=now)
    level = Column(String(20), default='INFO')
    message = Column(Text, nullable=False)
    details = Column(Text, default='{}')  # JSON


class PositionRecordTable(Base):
    """项目持仓记录表"""
    __tablename__ = 'position_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False)  # 可转债代码
    stock_name = Column(String(100), default='')  # 可转债名称
    volume = Column(Integer, nullable=False)  # 持有数量
    buy_price = Column(Float, nullable=False)  # 买入价格
    buy_time = Column(DateTime, nullable=False)  # 买入时间
    strategy_name = Column(String(100), default='')  # 策略名称（调仓买入等）
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class RefillQueueTable(Base):
    """待补仓队列表"""
    __tablename__ = 'refill_queue'

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False)  # 日期 YYYY-MM-DD
    stock_code = Column(String(20), nullable=False)  # 卖出的可转债代码
    stock_name = Column(String(100), default='')  # 可转债名称
    volume = Column(Integer, nullable=False)  # 卖出数量
    sell_price = Column(Float, nullable=False)  # 卖出价格
    reason = Column(String(20), default='')  # 卖出原因（止盈/止损）
    created_at = Column(DateTime, default=now)


# ==================== 数据库操作类 ====================

class Database:
    """数据库操作类"""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.engine = create_engine(f'sqlite:///{self.db_path}', echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # 创建所有表（如果不存在）
        self._create_tables()

    def _create_tables(self) -> None:
        """创建所有必要的表"""
        inspector = inspect(self.engine)
        existing_tables = inspector.get_table_names()

        # 使用 create_all 创建所有不存在的表
        # 这会自动处理新表（如 refill_queue）和旧表
        Base.metadata.create_all(self.engine)

        # 检查新表是否已创建
        new_tables = [t for t in ['refill_queue'] if t not in existing_tables]
        if new_tables:
            logger.info(f"已创建新表: {', '.join(new_tables)}")

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()
    
    # ========== 配置操作 ==========
    
    def get_config(self) -> AppConfig:
        """获取应用配置"""
        with self.get_session() as session:
            config_dict = {}
            rows = session.query(ConfigTable).all()
            for row in rows:
                try:
                    config_dict[row.key] = json.loads(row.value)
                except json.JSONDecodeError:
                    config_dict[row.key] = row.value
            
            # 确保 account_id 是字符串类型（兼容旧数据中可能是整数的情况）
            if 'account_id' in config_dict and not isinstance(config_dict['account_id'], str):
                config_dict['account_id'] = str(config_dict['account_id'])
            
            return AppConfig(**config_dict) if config_dict else AppConfig()
    
    def save_config(self, config: AppConfig) -> None:
        """保存应用配置"""
        with self.get_session() as session:
            config_dict = config.model_dump()
            for key, value in config_dict.items():
                existing = session.query(ConfigTable).filter_by(key=key).first()
                value_str = json.dumps(value) if not isinstance(value, str) else value
                
                if existing:
                    existing.value = value_str
                    existing.updated_at = now()
                else:
                    session.add(ConfigTable(key=key, value=value_str))
            
            session.commit()
    
    # ========== 认证信息操作 ==========
    
    def get_auth_info(self) -> AuthInfo:
        """获取认证信息"""
        with self.get_session() as session:
            row = session.query(AuthTable).first()
            if row:
                return AuthInfo(
                    username=row.username or '',
                    encrypted_password=row.encrypted_password or '',
                    access_token=row.access_token or '',
                    remember_password=row.remember_password,
                    auto_login=row.auto_login
                )
            return AuthInfo()
    
    def save_auth_info(self, auth: AuthInfo) -> None:
        """保存认证信息"""
        with self.get_session() as session:
            existing = session.query(AuthTable).first()
            
            if existing:
                existing.username = auth.username
                existing.encrypted_password = auth.encrypted_password
                existing.access_token = auth.access_token
                existing.remember_password = auth.remember_password
                existing.auto_login = auth.auto_login
                existing.updated_at = now()
            else:
                session.add(AuthTable(
                    username=auth.username,
                    encrypted_password=auth.encrypted_password,
                    access_token=auth.access_token,
                    remember_password=auth.remember_password,
                    auto_login=auth.auto_login
                ))
            
            session.commit()
    
    def clear_auth_token(self) -> None:
        """清除访问令牌"""
        with self.get_session() as session:
            existing = session.query(AuthTable).first()
            if existing:
                existing.access_token = ''
                existing.updated_at = now()
                session.commit()
    
    # ========== 策略配置操作 ==========
    
    def get_strategy_config(self) -> StrategyConfig | None:
        """获取当前策略配置"""
        with self.get_session() as session:
            row = session.query(StrategyTable).first()
            if row and row.strategy_id:
                return StrategyConfig(
                    strategy_id=row.strategy_id,
                    strategy_name=row.strategy_name or '',
                    history_id=row.history_id or 0,
                    history_note=row.history_note or '',
                    stop_profit_ratio=row.stop_profit_ratio or 0.1,
                    stop_loss_ratio=row.stop_loss_ratio or 0.05,
                    execution_schedule=json.loads(row.execution_schedule or '{}'),
                    parameters=json.loads(row.parameters or '{}')
                )
            return None
    
    def save_strategy_config(self, strategy: StrategyConfig) -> None:
        """保存策略配置"""
        with self.get_session() as session:
            existing = session.query(StrategyTable).first()
            
            data = {
                'strategy_id': strategy.strategy_id,
                'strategy_name': strategy.strategy_name,
                'history_id': strategy.history_id,
                'history_note': strategy.history_note,
                'stop_profit_ratio': strategy.stop_profit_ratio,
                'stop_loss_ratio': strategy.stop_loss_ratio,
                'execution_schedule': json.dumps(strategy.execution_schedule),
                'parameters': json.dumps(strategy.parameters),
                'updated_at': now()
            }
            
            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
            else:
                session.add(StrategyTable(**data))
            
            session.commit()
    
    def clear_strategy_config(self) -> None:
        """清除策略配置"""
        with self.get_session() as session:
            session.query(StrategyTable).delete()
            session.commit()
    
    # ========== 日志操作 ==========
    
    def add_trade_log(self, level: str, message: str, details: dict[str, Any] | None = None) -> None:
        """添加交易日志"""
        with self.get_session() as session:
            session.add(TradeLogTable(
                level=level,
                message=message,
                details=json.dumps(details or {})
            ))
            session.commit()
    
    def get_trade_logs(self, limit: int = 100) -> list[TradeLog]:
        """获取交易日志"""
        with self.get_session() as session:
            rows = session.query(TradeLogTable).order_by(
                TradeLogTable.timestamp.desc()
            ).limit(limit).all()
            
            return [
                TradeLog(
                    id=row.id,
                    timestamp=row.timestamp,
                    level=row.level,
                    message=row.message,
                    details=json.loads(row.details or '{}')
                )
                for row in rows
            ]
    
    def clear_old_logs(self, days: int = 30) -> None:
        """清除旧日志"""
        with self.get_session() as session:
            cutoff = now() - timedelta(days=days)
            session.query(TradeLogTable).filter(
                TradeLogTable.timestamp < cutoff
            ).delete()
            session.commit()
    
    # ========== 持仓记录操作 ==========
    
    def add_position_record(self, stock_code: str, stock_name: str, volume: int, 
                           buy_price: float, buy_time: datetime, strategy_name: str = "") -> None:
        """
        添加持仓记录（买入时调用）
        
        Args:
            stock_code: 可转债代码
            stock_name: 可转债名称
            volume: 买入数量
            buy_price: 买入价格
            buy_time: 买入时间
            strategy_name: 策略名称
        """
        with self.get_session() as session:
            # 检查是否已存在该可转债的记录
            existing = session.query(PositionRecordTable).filter_by(
                stock_code=stock_code
            ).first()
            
            if existing:
                # 如果已存在，更新数量和买入价格（加权平均）
                total_value = existing.volume * existing.buy_price + volume * buy_price
                total_volume = existing.volume + volume
                existing.buy_price = total_value / total_volume if total_volume > 0 else buy_price
                existing.volume = total_volume
                existing.updated_at = now()
            else:
                # 如果不存在，创建新记录
                session.add(PositionRecordTable(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    volume=volume,
                    buy_price=buy_price,
                    buy_time=buy_time,
                    strategy_name=strategy_name
                ))
            
            session.commit()
    
    def get_position_records(self) -> list[PositionRecord]:
        """
        获取所有项目持仓记录
        
        Returns:
            持仓记录列表
        """
        with self.get_session() as session:
            rows = session.query(PositionRecordTable).all()
            
            return [
                PositionRecord(
                    id=row.id,
                    stock_code=row.stock_code,
                    stock_name=row.stock_name,
                    volume=row.volume,
                    buy_price=row.buy_price,
                    buy_time=row.buy_time,
                    strategy_name=row.strategy_name
                )
                for row in rows
            ]
    
    def get_position_record(self, stock_code: str) -> PositionRecord | None:
        """
        获取指定可转债的持仓记录
        
        Args:
            stock_code: 可转债代码
            
        Returns:
            持仓记录，如果不存在返回 None
        """
        with self.get_session() as session:
            row = session.query(PositionRecordTable).filter_by(
                stock_code=stock_code
            ).first()
            
            if row:
                return PositionRecord(
                    id=row.id,
                    stock_code=row.stock_code,
                    stock_name=row.stock_name,
                    volume=row.volume,
                    buy_price=row.buy_price,
                    buy_time=row.buy_time,
                    strategy_name=row.strategy_name
                )
            return None
    
    def update_position_record(self, stock_code: str, sold_volume: int) -> None:
        """
        更新持仓记录（卖出时调用）
        
        Args:
            stock_code: 可转债代码
            sold_volume: 卖出数量
        """
        with self.get_session() as session:
            record = session.query(PositionRecordTable).filter_by(
                stock_code=stock_code
            ).first()
            
            if record:
                # 更新数量
                record.volume = max(0, record.volume - sold_volume)
                record.updated_at = now()
                
                # 如果数量为0，删除记录
                if record.volume <= 0:
                    session.delete(record)
                
                session.commit()
    
    def delete_position_record(self, stock_code: str) -> None:
        """
        删除持仓记录（持仓清零时调用）

        Args:
            stock_code: 可转债代码
        """
        with self.get_session() as session:
            session.query(PositionRecordTable).filter_by(
                stock_code=stock_code
            ).delete()
            session.commit()

    # ========== 待补仓队列操作 ==========

    def add_refill_queue(
        self,
        stock_code: str,
        stock_name: str,
        volume: int,
        sell_price: float,
        reason: str,
        date: str | None = None
    ) -> None:
        """
        添加到待补仓队列

        Args:
            stock_code: 卖出的可转债代码
            stock_name: 可转债名称
            volume: 卖出数量
            sell_price: 卖出价格
            reason: 卖出原因（止盈/止损）
            date: 日期，格式 YYYY-MM-DD，默认为今天
        """
        if date is None:
            date = now().strftime('%Y-%m-%d')

        with self.get_session() as session:
            session.add(RefillQueueTable(
                date=date,
                stock_code=stock_code,
                stock_name=stock_name,
                volume=volume,
                sell_price=sell_price,
                reason=reason
            ))
            session.commit()

    def get_refill_queue(self, date: str | None = None) -> list[dict[str, Any]]:
        """
        获取待补仓队列

        Args:
            date: 日期，格式 YYYY-MM-DD，默认为今天

        Returns:
            待补仓列表，每项包含代码、名称、数量、价格、原因
        """
        if date is None:
            date = now().strftime('%Y-%m-%d')

        with self.get_session() as session:
            rows = session.query(RefillQueueTable).filter_by(
                date=date
            ).order_by(RefillQueueTable.created_at).all()

            return [
                {
                    'stock_code': row.stock_code,
                    'stock_name': row.stock_name,
                    'volume': row.volume,
                    'sell_price': row.sell_price,
                    'reason': row.reason,
                    'created_at': row.created_at
                }
                for row in rows
            ]

    def clear_refill_queue(self, date: str | None = None) -> None:
        """
        清空待补仓队列

        Args:
            date: 日期，格式 YYYY-MM-DD，默认为今天
        """
        if date is None:
            date = now().strftime('%Y-%m-%d')

        with self.get_session() as session:
            session.query(RefillQueueTable).filter_by(
                date=date
            ).delete()
            session.commit()

    def is_refill_queue_empty(self, date: str | None = None) -> bool:
        """
        检查待补仓队列是否为空

        Args:
            date: 日期，格式 YYYY-MM-DD，默认为今天

        Returns:
            队列是否为空
        """
        if date is None:
            date = now().strftime('%Y-%m-%d')

        with self.get_session() as session:
            count = session.query(RefillQueueTable).filter_by(
                date=date
            ).count()
            return count == 0


def init_db(db_path: str | None = None) -> Database:
    """初始化数据库"""
    return Database(db_path)

