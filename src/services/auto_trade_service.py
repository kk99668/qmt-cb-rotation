"""
自动交易核心逻辑服务
"""
from datetime import datetime
from typing import Any, Callable

from loguru import logger

from src.models.database import Database
from src.models.schemas import AppConfig, BondInfo, Position, PositionRecord, StrategyConfig
from .factorcat_service import FactorCatService
from .qmt_service import QMTService
from .notification_service import NotificationService
from src.utils.datetime_helper import now


class AutoTradeService:
    """自动交易核心逻辑服务"""
    
    def __init__(
        self,
        factorcat: FactorCatService,
        qmt: QMTService,
        notification: NotificationService,
        database: Database | None = None
    ):
        self.factorcat = factorcat
        self.qmt = qmt
        self.notification = notification
        self.database = database
        
        # 配置
        self.app_config: AppConfig | None = None
        self.strategy_config: StrategyConfig | None = None

        # 日志回调
        self.log_callback: Callable[[str, str], None] | None = None
    
    def set_config(self, app_config: AppConfig, strategy_config: StrategyConfig) -> None:
        """设置配置"""
        self.app_config = app_config
        self.strategy_config = strategy_config
    
    def set_log_callback(self, callback: Callable) -> None:
        """设置日志回调"""
        self.log_callback = callback
    
    def _log(self, level: str, message: str) -> None:
        """记录日志并推送到前端"""
        if level == "INFO":
            logger.info(message)
        elif level == "SUCCESS":
            logger.success(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        
        if self.log_callback:
            self.log_callback(level, message)
    
    def execute_rebalance(self) -> None:
        """
        执行持仓调整（选债调仓）
        
        主要逻辑：
        1. 获取今日选债列表
        2. 获取当前持仓
        3. 卖出不在选债列表中的持仓
        4. 买入选债列表中但不在持仓中的可转债
        """
        if not self.strategy_config:
            self._log("ERROR", "未选择运行策略，无法执行调仓")
            return

        if not self.qmt.is_connected():
            self._log("ERROR", "QMT 未连接，无法执行交易")
            return

        # 在执行调仓前确保QMT连接健康(关键操作前的实时检查)
        self._log("INFO", "检查QMT连接状态...")
        if not self.qmt.ensure_connected(max_retries=2, retry_interval=1.0):
            self._log("ERROR", "QMT连接检查失败，无法执行调仓")
            return

        self._log("INFO", "开始执行选债调仓...")

        try:
            # 1. 获取今日选债列表
            self._log("INFO", "正在获取今日选债列表...")
            target_bonds = self.factorcat.get_today_bonds(self.strategy_config.history_id)
            target_codes = {bond.code for bond in target_bonds}
            self._log("SUCCESS", f"获取选债列表成功，共 {len(target_bonds)} 只可转债")
            
            if not target_bonds:
                self._log("WARNING", "今日选债列表为空，跳过调仓")
                return
            
            # 2. 获取当前持仓
            self._log("INFO", "正在获取当前持仓...")
            current_positions = self.qmt.get_positions()
            current_codes = {pos.stock_code for pos in current_positions}
            self._log("SUCCESS", f"当前持仓 {len(current_positions)} 只可转债")
            
            # 3. 获取项目持仓记录（只卖出项目买入的可转债）
            project_records = {}
            if self.database:
                records = self.database.get_position_records()
                project_records = {r.stock_code: r for r in records}
                self._log("INFO", f"项目持仓记录 {len(project_records)} 只可转债")
            
            # 4. 计算需要卖出和买入的
            # 待卖出 = 项目记录 ∩ (账户持仓 - 选债列表)
            to_sell_codes = set(project_records.keys()) & (current_codes - target_codes)
            to_buy = target_codes - current_codes   # 目标有，持仓无 -> 买入
            
            self._log("INFO", f"需要卖出: {len(to_sell_codes)} 只（仅项目买入的）, 需要买入: {len(to_buy)} 只")
            
            # 5. 执行卖出（只卖出项目记录中的可转债）
            for code in to_sell_codes:
                self._sell_bond(code, current_positions, project_records.get(code))
            
            # 6. 计算买入金额
            buy_amount = self._calculate_buy_amount(len(to_buy))
            self._log("INFO", f"单只买入金额: {buy_amount:.2f} 元")
            
            # 7. 执行买入
            for code in to_buy:
                self._buy_bond(code, buy_amount)
            
            self._log("SUCCESS", "选债调仓执行完成")
            
        except Exception as rebalance_error:
            error_msg = f"选债调仓执行失败: {str(rebalance_error)}"
            self._log("ERROR", error_msg)
            self.notification.send_trade_error_notification("选债调仓失败", error_msg)
    
    def execute_stop_profit_loss_check(self) -> None:
        """
        执行止盈止损检查

        主要逻辑：
        1. 获取当前持仓
        2. 获取每个持仓的实时价格和前收盘价
        3. 计算当日涨跌幅，判断是否触发止盈止损
        4. 触发时执行卖出
        5. 卖出成功后记录到待补仓队列（14:50 执行补仓）
        """
        if not self.strategy_config:
            return  # 静默返回，避免频繁日志

        if not self.qmt.is_connected():
            return

        try:
            # 获取项目持仓记录（只检查项目买入的可转债）
            if not self.database:
                return

            project_records = self.database.get_position_records()
            if not project_records:
                return

            # 获取账户当前持仓
            positions = self.qmt.get_positions()
            position_dict = {pos.stock_code: pos for pos in positions}

            # 获取止盈止损参数
            profit_ratio = self.strategy_config.stop_profit_ratio
            loss_ratio = self.strategy_config.stop_loss_ratio

            # 收集成功卖出的可转债信息
            sold_items: list[dict[str, Any]] = []

            # 只检查项目记录中的持仓
            for record in project_records:
                pos = position_dict.get(record.stock_code)
                if pos:
                    sold_info = self._check_single_position(pos, record, profit_ratio, loss_ratio)
                    if sold_info:
                        sold_items.append(sold_info)

            # 添加到待补仓队列
            if sold_items:
                self._add_to_refill_queue(sold_items)

        except Exception as check_error:
            logger.error(f"止盈止损检查失败: {str(check_error)}")
    
    def _check_single_position(
        self, pos: Position, record: PositionRecord, profit_ratio: float, loss_ratio: float
    ) -> dict[str, Any] | None:
        """
        检查单个持仓的止盈止损

        Args:
            pos: 账户持仓信息
            record: 项目持仓记录
            profit_ratio: 止盈比例
            loss_ratio: 止损比例

        Returns:
            卖出成功时返回卖出信息字典，否则返回 None
        """
        try:
            # 在获取行情前确保QMT连接健康
            if not self.qmt.ensure_connected(max_retries=1, retry_interval=0.5):
                logger.warning(f"{pos.stock_code} 获取价格前连接检查失败，跳过止盈止损检查")
                return None

            # 获取实时价格
            quote = self.qmt.get_quote(pos.stock_code)
            current_price = quote.get('lastPrice', 0)
            last_close = quote.get('lastClose', 0)

            if current_price <= 0:
                error_detail = quote.get('error', '未知错误')
                logger.warning(
                    f"止盈止损检查时获取 {pos.stock_code} 价格失败 - "
                    f"返回价格: {current_price}, "
                    f"quote数据: {quote}, "
                    f"失败原因: {error_detail}"
                )
                return None

            # 检查停牌
            if self.qmt.is_suspended(pos.stock_code):
                self._log("WARNING", f"{pos.stock_code} 停牌中，请手动处理")
                self.notification.send_suspended_notification(pos.stock_code, pos.stock_name)
                return None

            # 检查前收盘价是否有效
            if last_close <= 0:
                logger.warning(f"{pos.stock_code} 前收盘价无效，无法计算当日涨跌幅")
                return None

            # 使用当日涨跌幅进行判断
            pct_change = (current_price - last_close) / last_close

            logger.info(f"{pos.stock_code} 当日涨跌幅: {pct_change*100:.2f}%")

            logger.info(f"{pos.stock_code} 止盈比例: {profit_ratio}")
            logger.info(f"{pos.stock_code} 止损比例: {loss_ratio}")
            # 检查止盈
            if pct_change >= profit_ratio:
                self._log("INFO", f"{pos.stock_code} 触发止盈: 当日涨幅 {pct_change*100:.2f}%")
                return self._execute_stop_order(pos, record, current_price, "止盈")

            # 检查止损
            elif pct_change <= -loss_ratio:
                self._log("INFO", f"{pos.stock_code} 触发止损: 当日跌幅 {pct_change*100:.2f}%")
                return self._execute_stop_order(pos, record, current_price, "止损")

            return None

        except Exception as position_check_error:
            logger.error(f"检查 {pos.stock_code} 止盈止损失败: {str(position_check_error)}")
            return None
    
    def _execute_stop_order(self, pos: Position, record: PositionRecord, price: float, reason: str) -> dict[str, Any] | None:
        """
        执行止盈止损卖出

        Args:
            pos: 账户持仓信息
            record: 项目持仓记录
            price: 卖出价格
            reason: 卖出原因（止盈/止损）

        Returns:
            卖出成功时返回卖出信息字典，失败返回 None
        """
        try:
            # 卖出数量 = min(项目记录数量, 账户可用数量)
            sell_volume = min(record.volume, pos.can_use_volume)

            if sell_volume <= 0:
                self._log("WARNING", f"{pos.stock_code} 无可用数量，跳过{reason}卖出")
                return None

            order_type = self.app_config.order_type if self.app_config else "limit"

            order_id = self.qmt.sell_stock(
                stock_code=pos.stock_code,
                volume=sell_volume,
                price=price,
                price_type=order_type,
                strategy_name="止盈止损",
                remark=reason
            )

            if order_id > 0:
                self._log("SUCCESS", f"{pos.stock_code} {reason}卖出委托成功，数量: {sell_volume}")

                # 更新项目持仓记录
                if self.database:
                    self.database.update_position_record(pos.stock_code, sell_volume)

                self.notification.send_trade_success_notification(
                    f"{reason}卖出成功",
                    f"{pos.stock_code} {pos.stock_name}，数量: {sell_volume}，价格: {price}"
                )

                # 返回卖出信息
                return {
                    'stock_code': pos.stock_code,
                    'stock_name': pos.stock_name,
                    'volume': sell_volume,
                    'sell_price': price,
                    'reason': reason
                }
            else:
                self._log("ERROR", f"{pos.stock_code} {reason}卖出委托失败")
                self.notification.send_trade_error_notification(
                    f"{reason}卖出失败",
                    f"{pos.stock_code} {pos.stock_name}"
                )
                return None

        except Exception as stop_order_error:
            error_msg = f"{pos.stock_code} {reason}卖出失败: {str(stop_order_error)}"
            self._log("ERROR", error_msg)
            self.notification.send_trade_error_notification(f"{reason}卖出异常", error_msg)
            return None

    def _execute_refill_after_stop(self, sold_codes: list[str]) -> None:
        """
        止盈止损后执行补仓

        从选债列表中按顺序选取新的可转债进行补仓，补仓数量与卖出数量相同。

        Args:
            sold_codes: 已卖出的可转债代码列表
        """
        if not sold_codes:
            return

        self._log("INFO", f"开始执行补仓，需补仓 {len(sold_codes)} 只")

        try:
            # 1. 获取当前选债列表（按接口返回顺序）
            target_bonds = self.factorcat.get_today_bonds(self.strategy_config.history_id)
            if not target_bonds:
                self._log("WARNING", "选债列表为空，无法补仓")
                return

            # 2. 获取当前持仓
            positions = self.qmt.get_positions()
            current_codes = {pos.stock_code for pos in positions}

            # 3. 排除已卖出的代码（因为可能还在持仓列表中）
            current_codes -= set(sold_codes)

            # 4. 筛选候选：选债列表中不在持仓的，保持原顺序
            candidates = [bond for bond in target_bonds if bond.code not in current_codes]

            if not candidates:
                self._log("WARNING", "选债列表中无可补仓的可转债")
                return

            # 5. 取前 N 只（N = 卖出数量）
            refill_count = len(sold_codes)
            to_buy = candidates[:refill_count]

            self._log(
                "INFO",
                f"选债列表 {len(target_bonds)} 只，可补仓候选 {len(candidates)} 只，"
                f"本次补仓 {len(to_buy)} 只"
            )

            # 6. 计算买入金额
            buy_amount = self._calculate_buy_amount(len(to_buy))
            if buy_amount <= 0:
                self._log("WARNING", "计算买入金额为0，跳过补仓")
                return

            self._log("INFO", f"补仓单只金额: {buy_amount:.2f} 元")

            # 7. 执行买入
            for bond in to_buy:
                self._buy_bond(bond.code, buy_amount)

            self._log("SUCCESS", f"补仓执行完成，共补仓 {len(to_buy)} 只")

        except Exception as refill_error:
            error_msg = f"补仓执行失败: {str(refill_error)}"
            self._log("ERROR", error_msg)
            self.notification.send_trade_error_notification("补仓失败", error_msg)

    def _sell_bond(self, stock_code: str, positions: list[Position], record: PositionRecord | None = None) -> None:
        """
        卖出可转债

        Args:
            stock_code: 可转债代码
            positions: 账户持仓列表
            record: 项目持仓记录（如果为None，则卖出全部可用数量）
        """
        # 找到对应持仓
        pos = next((p for p in positions if p.stock_code == stock_code), None)
        if not pos or pos.can_use_volume <= 0:
            self._log("WARNING", f"{stock_code} 无可用持仓，跳过卖出")
            return

        try:
            # 确定卖出数量：如果有项目记录，只卖出项目记录的数量
            if record:
                sell_volume = min(record.volume, pos.can_use_volume)
            else:
                sell_volume = pos.can_use_volume

            if sell_volume <= 0:
                self._log("WARNING", f"{stock_code} 无可用数量，跳过卖出")
                return

            # 在获取行情前确保QMT连接健康
            if not self.qmt.ensure_connected(max_retries=1, retry_interval=0.5):
                self._log("ERROR", f"{stock_code} 获取价格前连接检查失败，跳过卖出")
                return

            # 获取当前价格
            quote = self.qmt.get_quote(stock_code)
            price = quote.get('lastPrice', 0)
            
            if price <= 0:
                error_detail = quote.get('error', '未知错误')
                error_msg = (
                    f"{stock_code} 获取价格失败，跳过卖出 - "
                    f"返回价格: {price}, "
                    f"quote数据: {quote}, "
                    f"失败原因: {error_detail}"
                )
                self._log("ERROR", error_msg)
                logger.error(f"调仓卖出时获取价格失败: {error_msg}")
                return
            
            # 检查停牌
            if self.qmt.is_suspended(stock_code):
                self._log("WARNING", f"{stock_code} 停牌中，跳过卖出，请手动处理")
                self.notification.send_suspended_notification(stock_code, pos.stock_name)
                return
            
            order_type = self.app_config.order_type if self.app_config else "limit"
            
            order_id = self.qmt.sell_stock(
                stock_code=stock_code,
                volume=sell_volume,
                price=price,
                price_type=order_type,
                strategy_name="调仓卖出"
            )
            
            if order_id > 0:
                self._log("SUCCESS", f"卖出 {stock_code} 委托成功，数量: {sell_volume}")
                
                # 更新项目持仓记录
                if self.database and record:
                    self.database.update_position_record(stock_code, sell_volume)
            else:
                self._log("ERROR", f"卖出 {stock_code} 委托失败")
                self.notification.send_trade_error_notification(
                    "调仓卖出失败",
                    f"{stock_code}，数量: {sell_volume}"
                )
                
        except Exception as sell_error:
            error_msg = f"卖出 {stock_code} 失败: {str(sell_error)}"
            self._log("ERROR", error_msg)
            self.notification.send_trade_error_notification("调仓卖出异常", error_msg)
    
    def _buy_bond(self, stock_code: str, amount: float) -> None:
        """买入可转债"""
        try:
            ensure_result = self.qmt.ensure_connected(max_retries=1, retry_interval=0.5)
            
            if not ensure_result:
                self._log("ERROR", f"{stock_code} 获取价格前连接检查失败，跳过买入")
                return

            quote = self.qmt.get_quote(stock_code)
            price = quote.get('lastPrice', 0)
            
            if price <= 0:
                error_detail = quote.get('error', '未知错误')
                error_msg = (
                    f"{stock_code} 获取价格失败，跳过买入 - "
                    f"返回价格: {price}, "
                    f"quote数据: {quote}, "
                    f"失败原因: {error_detail}"
                )
                self._log("ERROR", error_msg)
                logger.error(f"调仓买入时获取价格失败: {error_msg}")
                return
            
            # 计算买入数量（可转债10张为1手）
            volume = int(amount / price / 10) * 10
            if volume < 10:
                self._log("WARNING", f"{stock_code} 计算数量不足1手，跳过买入")
                return
            
            order_type = self.app_config.order_type if self.app_config else "limit"
            
            order_id = self.qmt.buy_stock(
                stock_code=stock_code,
                volume=volume,
                price=price,
                price_type=order_type,
                strategy_name="调仓买入"
            )
            
            if order_id > 0:
                self._log("SUCCESS", f"买入 {stock_code} 委托成功，数量: {volume}，价格: {price}")
                
                # 记录到项目持仓表
                if self.database:
                    try:
                        stock_name = self.qmt.get_stock_name(stock_code)
                        self.database.add_position_record(
                            stock_code=stock_code,
                            stock_name=stock_name,
                            volume=volume,
                            buy_price=price,
                            buy_time=now(),
                            strategy_name="调仓买入"
                        )
                        self._log("INFO", f"{stock_code} 持仓记录已保存")
                    except Exception as save_error:
                        logger.warning(f"保存持仓记录失败: {stock_code}, {str(save_error)}")
            else:
                self._log("ERROR", f"买入 {stock_code} 委托失败")
                self.notification.send_trade_error_notification(
                    "调仓买入失败",
                    f"{stock_code}，数量: {volume}"
                )
                
        except Exception as buy_error:
            error_msg = f"买入 {stock_code} 失败: {str(buy_error)}"
            self._log("ERROR", error_msg)
            self.notification.send_trade_error_notification("调仓买入异常", error_msg)
    
    def _calculate_buy_amount(self, bond_count: int) -> float:
        """
        计算单只买入金额
        
        Args:
            bond_count: 需要买入的可转债数量
            
        Returns:
            单只买入金额
        """
        if not self.app_config or bond_count <= 0:
            return 0
        
        if self.app_config.buy_amount_type == "fixed":
            return self.app_config.fixed_amount or 10000
        else:
            # 按可用余额平均分配
            try:
                asset = self.qmt.get_asset()
                available = asset.cash
                return available / bond_count
            except Exception:
                return 10000  # 默认1万
    
    def get_positions_with_quote(self) -> list[dict[str, Any]]:
        """
        获取持仓信息（包含实时行情）
        只返回自己买入的持仓，过滤掉无关的可转债、股票和ETF

        Returns:
            持仓列表（包含当前价格、盈亏等）
        """
        if not self.qmt.is_connected():
            return []

        # 在获取持仓和行情前确保QMT连接健康
        if not self.qmt.ensure_connected(max_retries=1, retry_interval=0.5):
            logger.warning("获取持仓前连接检查失败")
            return []

        # 获取项目持仓记录（只显示自己买入的）
        project_records = {}
        if self.database:
            records = self.database.get_position_records()
            project_records = {r.stock_code: r for r in records}
        
        # 如果没有项目记录，返回空列表
        if not project_records:
            return []
        
        positions = self.qmt.get_positions()
        result = []
        
        # 将持仓转换为字典，便于查找
        position_dict = {pos.stock_code: pos for pos in positions}
        
        # 只处理项目记录中的持仓
        for stock_code, record in project_records.items():
            pos = position_dict.get(stock_code)
            if not pos or pos.volume <= 0:
                # 如果账户中没有该持仓或持仓为0，跳过
                continue
            
            # 判断是否为可转债（代码以11或12开头）
            # 可转债代码：上海11开头，深圳12开头
            if not (stock_code.startswith('11') or stock_code.startswith('12')):
                # 不是可转债，跳过
                continue
            
            # 获取实时价格
            quote = self.qmt.get_quote(pos.stock_code)
            current_price = quote.get('lastPrice', 0)
            
            # 如果获取价格失败，记录日志
            if current_price <= 0:
                error_detail = quote.get('error', '未知错误')
                logger.warning(
                    f"获取持仓 {pos.stock_code} 实时价格失败 - "
                    f"返回价格: {current_price}, "
                    f"quote数据: {quote}, "
                    f"失败原因: {error_detail}"
                )
            
            # 计算盈亏
            profit_loss = (current_price - pos.avg_price) * pos.volume if current_price > 0 else 0
            profit_loss_ratio = (current_price - pos.avg_price) / pos.avg_price if pos.avg_price > 0 and current_price > 0 else 0
            
            # 计算止盈止损价（基于前收盘价，与实际触发判断逻辑一致）
            stop_profit_price = 0
            stop_loss_price = 0
            if self.strategy_config:
                last_close = quote.get('lastClose', 0)
                if last_close > 0:
                    stop_profit_price = last_close * (1 + self.strategy_config.stop_profit_ratio)
                    stop_loss_price = last_close * (1 - self.strategy_config.stop_loss_ratio)
            
            result.append({
                'stock_code': pos.stock_code,
                'stock_name': pos.stock_name,
                'volume': pos.volume,
                'can_use_volume': pos.can_use_volume,
                'avg_price': pos.avg_price,
                'current_price': current_price,
                'market_value': current_price * pos.volume if current_price > 0 else pos.market_value,
                'profit_loss': profit_loss,
                'profit_loss_ratio': profit_loss_ratio,
                'stop_profit_price': stop_profit_price,
                'stop_loss_price': stop_loss_price
            })

        return result

    def execute_scheduled_refill(self) -> None:
        """
        执行定时补仓（14:50 调用）

        从待补仓队列获取今日需要补仓的数量，执行补仓操作。
        """
        if not self.strategy_config:
            self._log("INFO", "未选择运行策略，跳过补仓")
            return

        if not self.qmt.is_connected():
            self._log("ERROR", "QMT 未连接，无法执行补仓")
            return

        if not self.database:
            self._log("ERROR", "数据库未初始化，无法获取待补仓队列")
            return

        self._log("INFO", "开始执行定时补仓...")

        try:
            # 1. 获取今天的待补仓队列
            refill_queue = self.database.get_refill_queue()

            if not refill_queue:
                self._log("INFO", "今日待补仓队列为空，无需补仓")
                return

            # 2. 显示待补仓信息
            self._log(
                "INFO",
                f"今日待补仓 {len(refill_queue)} 只："
                + ", ".join([f"{item['stock_code']}({item['volume']}张-{item['reason']})" for item in refill_queue])
            )

            # 3. 计算总补仓数量
            total_refill_count = len(refill_queue)

            # 4. 获取当前选债列表（按接口返回顺序）
            target_bonds = self.factorcat.get_today_bonds(self.strategy_config.history_id)
            if not target_bonds:
                self._log("WARNING", "选债列表为空，无法补仓")
                return

            # 5. 获取当前持仓
            positions = self.qmt.get_positions()
            current_codes = {pos.stock_code for pos in positions}

            # 6. 排除已卖出的代码（因为可能还在持仓列表中）
            current_codes -= {item['stock_code'] for item in refill_queue}

            # 7. 筛选候选：选债列表中不在持仓的，保持原顺序
            candidates = [bond for bond in target_bonds if bond.code not in current_codes]

            if not candidates:
                self._log("WARNING", "选债列表中无可补仓的可转债")
                return

            # 8. 取前 N 只（N = 卖出数量）
            to_buy = candidates[:total_refill_count]

            self._log(
                "INFO",
                f"选债列表 {len(target_bonds)} 只，可补仓候选 {len(candidates)} 只，"
                f"本次补仓 {len(to_buy)} 只"
            )

            # 9. 计算买入金额
            buy_amount = self._calculate_buy_amount(len(to_buy))
            if buy_amount <= 0:
                self._log("WARNING", "计算买入金额为0，跳过补仓")
                return

            self._log("INFO", f"补仓单只金额: {buy_amount:.2f} 元")

            # 10. 执行买入
            for bond in to_buy:
                self._buy_bond(bond.code, buy_amount)

            self._log("SUCCESS", f"补仓执行完成，共补仓 {len(to_buy)} 只")

            # 11. 清空待补仓队列
            self.database.clear_refill_queue()

        except Exception as refill_error:
            error_msg = f"补仓执行失败: {str(refill_error)}"
            self._log("ERROR", error_msg)
            self.notification.send_trade_error_notification("补仓失败", error_msg)

    def _add_to_refill_queue(self, sold_items: list[dict[str, Any]]) -> None:
        """
        将止盈止损卖出的可转债添加到待补仓队列

        Args:
            sold_items: 已卖出的可转债信息列表，每项包含代码、名称、数量、价格、原因
        """
        if not sold_items:
            return

        if not self.database:
            logger.warning("数据库未初始化，无法记录待补仓队列")
            return

        # 检查是否超过 14:50
        now_time = now()
        current_time = now_time.time()
        refill_deadline = datetime.strptime("14:50", "%H:%M").time()

        if current_time > refill_deadline:
            self._log(
                "WARNING",
                f"当前时间 {now_time.strftime('%H:%M')} 已超过补仓截止时间 14:50，"
                f"今日不再补仓（共 {len(sold_items)} 只）"
            )
            return

        self._log("INFO", f"将 {len(sold_items)} 只止盈止损卖出的可转债加入待补仓队列")

        for item in sold_items:
            self.database.add_refill_queue(
                stock_code=item['stock_code'],
                stock_name=item['stock_name'],
                volume=item['volume'],
                sell_price=item['sell_price'],
                reason=item['reason']
            )

        # 显示待补仓详情
        details = ", ".join([
            f"{item['stock_code']}({item['volume']}张-{item['reason']})"
            for item in sold_items
        ])
        self._log("INFO", f"待补仓队列: {details}")

