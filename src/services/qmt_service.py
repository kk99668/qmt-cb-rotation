"""
QMT 交易对接服务
"""
import os
import time
import sys
from typing import Optional, List, Dict, Any, Callable
from loguru import logger

from src.utils.datetime_helper import now

try:
    import numpy as np
except ImportError:
    np = None

# akshare 用于获取行情数据
try:
    import akshare as ak
except ImportError:
    ak = None
    logger.warning("未安装 akshare，请运行: pip install akshare")

try:
    import requests
except ImportError:
    requests = None

from src.models.schemas import Position, Asset

# QMT 相关常量
STOCK_BUY = 23  # 买入
STOCK_SELL = 24  # 卖出
FIX_PRICE = 11  # 限价
LATEST_PRICE = 5  # 最新价


class QMTService:
    """QMT 交易对接服务"""

    def __init__(self) -> None:
        self.qmt_path: Optional[str] = None
        self.session_id: int = 123456
        self.trader: Optional[Any] = None
        self.account: Optional[Any] = None
        self.account_id: Optional[str] = None
        self.connected: bool = False
        self.callback: Optional[Callable] = None

        # QMT 模块引用
        self.xttrader: Optional[Any] = None
        self.xttype: Optional[Any] = None
        self.xtconstant: Optional[Any] = None
        self.xtdata: Optional[Any] = None

        # 全推行情订阅号（用于获取全推数据）
        self._whole_quote_sub_id: Optional[int] = None
        # 单股订阅号字典（stock_code -> sub_id）
        self._stock_sub_ids: Dict[str, int] = {}
        # 可转债列表缓存（code -> name）
        self._bond_name_cache: Dict[str, str] = {}

    def _init_qmt_modules(self) -> bool:
        """初始化 QMT 模块"""
        if self.xttrader is not None:
            return True

        if not self.qmt_path:
            raise Exception("请先配置 MiniQMT 程序路径")

        if not os.path.exists(self.qmt_path):
            raise Exception(f"MiniQMT 路径不存在: {self.qmt_path}")

        if self.qmt_path not in sys.path:
            sys.path.insert(0, self.qmt_path)

        try:
            from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
            from xtquant.xttype import StockAccount
            from xtquant import xtconstant
            from xtquant import xtdata

            self.xttrader = XtQuantTrader
            self.XtQuantTraderCallback = XtQuantTraderCallback
            self.xttype = StockAccount
            self.xtconstant = xtconstant
            self.xtdata = xtdata

            logger.info("QMT 模块加载成功")
            return True

        except ImportError as import_error:
            raise Exception(f"加载 QMT 模块失败: {str(import_error)}，请确认 MiniQMT 路径配置正确")

    def _create_callback(self) -> Any:
        """创建交易回调类"""
        service = self

        class TraderCallback(self.XtQuantTraderCallback):
            def on_disconnected(self) -> None:
                logger.warning("QMT 连接断开")
                service.connected = False
                if service.callback:
                    service.callback('disconnected', None)

            def on_stock_order(self, order: Any) -> None:
                logger.info(f"委托回报: {order.stock_code}, 状态: {order.order_status}")
                if service.callback:
                    service.callback('order', order)

            def on_stock_trade(self, trade: Any) -> None:
                logger.info(f"成交回报: {trade.stock_code}, 数量: {trade.traded_volume}")
                if service.callback:
                    service.callback('trade', trade)

            def on_order_error(self, order_error: Any) -> None:
                logger.error(f"委托失败: {order_error.error_msg}")
                if service.callback:
                    service.callback('order_error', order_error)

            def on_cancel_error(self, cancel_error: Any) -> None:
                logger.error(f"撤单失败: {cancel_error.error_msg}")
                if service.callback:
                    service.callback('cancel_error', cancel_error)

            def on_account_status(self, status: Any) -> None:
                logger.info(f"账号状态: {status.account_id}, 状态: {status.status}")
                if service.callback:
                    service.callback('account_status', status)

        return TraderCallback()

    def connect(self, qmt_path: str, account_id: str, callback: Optional[Callable] = None) -> bool:
        """
        连接 QMT 并订阅账号

        Args:
            qmt_path: MiniQMT userdata_mini 路径
            account_id: 证券账号
            callback: 事件回调函数

        Returns:
            是否连接成功
        """
        self.qmt_path = qmt_path
        self.account_id = account_id
        self.callback = callback

        logger.info(f"正在连接 QMT, 路径: {qmt_path}, 账号: {account_id}")

        try:
            # 初始化模块
            self._init_qmt_modules()

            # 创建交易实例
            self.trader = self.xttrader(qmt_path, int(time.time()))

            # 创建账号对象
            self.account = self.xttype(account_id)

            # 注册回调
            trader_callback = self._create_callback()
            self.trader.register_callback(trader_callback)

            # 启动交易线程
            self.trader.start()

            # 连接
            connect_result = self.trader.connect()
            if connect_result != 0:
                raise Exception(f"连接 QMT 失败，错误码: {connect_result}")

            # 订阅账号
            subscribe_result = self.trader.subscribe(self.account)
            if subscribe_result != 0:
                raise Exception(f"订阅账号失败，错误码: {subscribe_result}")

            self.connected = True

            # 订阅全推行情以便获取实时数据
            try:
                if self.xtdata:
                    # 订阅全市场全推行情
                    self._whole_quote_sub_id = self.xtdata.subscribe_whole_quote(['SH', 'SZ'])
                    if self._whole_quote_sub_id > 0:
                        logger.info(f"订阅全推行情成功，订阅号: {self._whole_quote_sub_id}")
                    else:
                        logger.warning("订阅全推行情失败，可能影响实时价格获取")
            except Exception as subscribe_error:
                logger.warning(f"订阅全推行情时出错: {str(subscribe_error)}")

            logger.success(f"QMT 连接成功，账号: {account_id}")
            return True

        except Exception as connect_error:
            logger.error(f"连接 QMT 失败: {str(connect_error)}")
            self.connected = False
            raise

    def disconnect(self) -> None:
        """断开连接"""
        if self.trader:
            try:
                if self.account:
                    self.trader.unsubscribe(self.account)
                self.trader.stop()
            except Exception as disconnect_error:
                logger.warning(f"断开连接时出错: {str(disconnect_error)}")
            finally:
                self.trader = None
                self.account = None
                self.connected = False

                try:
                    if self._whole_quote_sub_id and self.xtdata:
                        self.xtdata.unsubscribe_quote(self._whole_quote_sub_id)
                        self._whole_quote_sub_id = None
                except Exception as unsubscribe_error:
                    logger.warning(f"取消全推行情订阅时出错: {str(unsubscribe_error)}")

                try:
                    if self.xtdata and self._stock_sub_ids:
                        for stock_code, sub_id in self._stock_sub_ids.items():
                            try:
                                self.xtdata.unsubscribe_quote(sub_id)
                            except Exception as stock_unsubscribe_error:
                                logger.warning(f"取消单股订阅失败: {stock_code}, {str(stock_unsubscribe_error)}")
                        self._stock_sub_ids.clear()
                except Exception as stock_subscribe_error:
                    logger.warning(f"取消单股订阅时出错: {str(stock_subscribe_error)}")

                logger.info("QMT 已断开连接")

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.connected and self.trader is not None

    def health_check_simple(self, timeout: float = 3.0) -> bool:
        """
        简单健康检查：只检查连接状态，不进行实际API调用

        Args:
            timeout: 超时时间（秒），暂未实现超时控制

        Returns:
            连接是否健康
        """
        return self.is_connected()

    def health_check(self, timeout: float = 3.0) -> bool:
        """
        健康检查：通过实际API调用验证连接是否真正可用

        Args:
            timeout: 超时时间（秒），暂未实现超时控制

        Returns:
            连接是否健康
        """
        if not self.is_connected():
            return False

        try:
            # 尝试查询资产（轻量级操作）
            asset = self.trader.query_stock_asset(self.account)
            if asset is None:
                logger.warning("QMT健康检查失败: 查询资产返回None")
                return False

            return True

        except Exception as health_check_error:
            logger.warning(f"QMT健康检查失败: {str(health_check_error)}")
            return False

    def ensure_connected(self, max_retries: int = 2, retry_interval: float = 1.0) -> bool:
        """
        确保QMT连接健康，失败时自动重试

        Args:
            max_retries: 最大重试次数（默认2次）
            retry_interval: 重试间隔秒数（默认1秒）

        Returns:
            连接是否健康
        """
        import time

        for attempt in range(max_retries):
            if self.health_check():
                return True

            if attempt < max_retries - 1:
                time.sleep(retry_interval)

        return False

    def get_asset(self) -> Asset:
        """
        查询账户资产

        Returns:
            账户资产信息
        """
        if not self.is_connected():
            raise Exception("QMT 未连接")

        asset = self.trader.query_stock_asset(self.account)
        if asset is None:
            raise Exception("查询资产失败")

        return Asset(
            cash=asset.cash,
            frozen_cash=asset.frozen_cash,
            market_value=asset.market_value,
            total_asset=asset.total_asset
        )

    def get_positions(self) -> List[Position]:
        """
        查询当前持仓

        Returns:
            持仓列表
        """
        if not self.is_connected():
            raise Exception("QMT 未连接")

        positions = self.trader.query_stock_positions(self.account)
        if positions is None:
            return []

        result = []
        for pos in positions:
            if pos.volume > 0:  # 只返回有持仓的
                # 查询股票名称
                stock_name = self.get_stock_name(pos.stock_code)

                result.append(Position(
                    stock_code=pos.stock_code,
                    stock_name=stock_name,  # 使用查询到的名称
                    volume=pos.volume,
                    can_use_volume=pos.can_use_volume,
                    avg_price=pos.avg_price,
                    current_price=0,  # 需要另外获取行情
                    market_value=pos.market_value
                ))

        return result

    def _get_bond_list(self) -> Dict[str, str]:
        """
        获取可转债列表并缓存

        Returns:
            可转债代码到名称的字典
        """
        # 如果缓存不为空，直接返回
        if self._bond_name_cache:
            return self._bond_name_cache

        if ak is None:
            logger.warning("未安装 akshare，无法获取可转债名称")
            return {}

        try:
            # 优先使用实时行情接口获取可转债列表
            df = ak.bond_zh_hs_cov_spot()
            if not df.empty:
                # 查找代码和名称字段（可能是 'code'/'名称' 或 '代码'/'name'）
                code_col = None
                name_col = None
                
                for col in df.columns:
                    col_lower = str(col).lower()
                    if col_lower in ['code', '代码', '债券代码', '转债代码']:
                        code_col = col
                    elif col_lower in ['name', '名称', '债券简称', '债券名称', '转债简称']:
                        name_col = col
                
                if code_col and name_col:
                    for _, row in df.iterrows():
                        code = str(row[code_col]).strip()
                        name = str(row[name_col]).strip()
                        if code and name:
                            # 处理代码格式：可能是纯数字或带后缀
                            code_clean = code.split('.')[0] if '.' in code else code
                            self._bond_name_cache[code_clean] = name
                    
                    logger.debug(f"从 akshare 获取可转债列表成功，共 {len(self._bond_name_cache)} 只")
                    return self._bond_name_cache
                else:
                    logger.warning(f"akshare 返回的 DataFrame 缺少必要字段，可用字段: {list(df.columns)}")
        except Exception as spot_error:
            logger.debug(f"使用 bond_zh_hs_cov_spot 获取可转债列表失败: {str(spot_error)}")

        # 备用方案：使用可转债一览表
        try:
            df = ak.bond_zh_cov()
            if not df.empty:
                code_col = None
                name_col = None
                
                for col in df.columns:
                    col_lower = str(col).lower()
                    if col_lower in ['code', '代码', '债券代码', '转债代码']:
                        code_col = col
                    elif col_lower in ['name', '名称', '债券简称', '债券名称', '转债简称']:
                        name_col = col
                
                if code_col and name_col:
                    for _, row in df.iterrows():
                        code = str(row[code_col]).strip()
                        name = str(row[name_col]).strip()
                        if code and name:
                            code_clean = code.split('.')[0] if '.' in code else code
                            self._bond_name_cache[code_clean] = name
                    
                    logger.debug(f"从 akshare bond_zh_cov 获取可转债列表成功，共 {len(self._bond_name_cache)} 只")
                    return self._bond_name_cache
        except Exception as cov_error:
            logger.debug(f"使用 bond_zh_cov 获取可转债列表失败: {str(cov_error)}")

        logger.warning("所有 akshare 接口都无法获取可转债列表")
        return {}

    def get_stock_name(self, stock_code: str) -> str:
        """
        获取可转债名称（本项目只交易可转债）

        Args:
            stock_code: 证券代码（格式: "123456.SZ" 或 "123456.SH"）

        Returns:
            可转债名称，如果不是可转债或获取失败则返回空字符串
        """
        # 提取纯代码部分（去掉市场后缀）
        code_part = stock_code.split('.')[0] if '.' in stock_code else stock_code
        
        # 判断是否为可转债（上海11开头，深圳12开头）
        is_bond = code_part.startswith('11') or code_part.startswith('12')
        
        # 本项目只交易可转债，如果不是可转债直接返回空
        if not is_bond:
            logger.debug(f"代码 {stock_code} 不是可转债，跳过名称获取")
            return ''
        
        # 可转债：使用 akshare 获取
        if ak is not None:
            try:
                bond_list = self._get_bond_list()
                if code_part in bond_list:
                    name = bond_list[code_part]
                    logger.debug(f"从缓存获取可转债名称: {stock_code} = {name}")
                    return name
                else:
                    logger.warning(f"可转债代码 {stock_code} 不在列表中，可能已退市或代码格式不正确")
            except Exception as bond_error:
                logger.warning(f"获取可转债名称失败: {stock_code}, {str(bond_error)}")
        else:
            logger.warning(f"未安装 akshare，无法获取可转债名称: {stock_code}")

        # 备用方案：尝试使用 QMT 接口
        if not self.xtdata:
            self._init_qmt_modules()

        try:
            detail = self.xtdata.get_instrument_detail(stock_code)
            if detail:
                name = detail.get('InstrumentName', '')
                if name:
                    logger.debug(f"从 QMT 获取可转债名称: {stock_code} = {name}")
                    return name
        except Exception as name_error:
            logger.debug(f"使用 QMT 获取可转债名称失败: {stock_code}, {str(name_error)}")

        return ''

    def get_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        获取行情数据（使用腾讯 API）

        使用腾讯行情 API 获取实时行情数据，只获取单只股票的数据。

        Args:
            stock_code: 证券代码 (格式: "123456.SZ" 或 "123456.SH")

        Returns:
            行情数据字典
            {
                'lastPrice': float,      # 最新价
                'open': float,           # 开盘价
                'high': float,           # 最高价
                'low': float,            # 最低价
                'lastClose': float,      # 昨收价
                'volume': float,         # 成交量
                'amount': float,         # 成交额
                'stockStatus': 0,        # 股票状态
                'askPrice': [],          # 卖价列表
                'bidPrice': []           # 买价列表
            }
        """
        if requests is None:
            logger.error("未安装 requests，请运行: pip install requests")
            return {'lastPrice': 0, 'stockStatus': 0}

        # 将 QMT 格式代码 (123456.SZ) 转换为腾讯 API 格式 (sh600000 或 sz000001)
        if '.' in stock_code:
            code_part, market = stock_code.split('.')
            if market.upper() == 'SZ':
                tencent_code = f'sz{code_part}'
            elif market.upper() == 'SH':
                tencent_code = f'sh{code_part}'
            else:
                tencent_code = stock_code
        else:
            tencent_code = stock_code

        # 方法1: 使用腾讯单股实时行情 API（优化方案，只获取单只股票）
        try:
            url = f"http://qt.gtimg.cn/q={tencent_code}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                content = response.text
                # 解析响应格式: v_sh600000="1~浦发银行~600000~11.04~11.16~11.19~..."
                if '~' in content:
                    start = content.find('"') + 1
                    end = content.rfind('"')
                    data_str = content[start:end]
                    fields = data_str.split('~')

                    # 字段说明:
                    # 0: 状态(1=正常)
                    # 1: 股票名称
                    # 2: 股票代码
                    # 3: 当前价
                    # 4: 昨收价
                    # 5: 今开价
                    # 6: 现价
                    # 7: 成交量(手)
                    # 8: 成交额
                    if len(fields) >= 9 and fields[0] and fields[0] != '0':
                        last_price = float(fields[3]) if fields[3] else 0
                        last_close = float(fields[4]) if fields[4] else 0
                        open_price = float(fields[5]) if fields[5] else 0
                        volume = float(fields[7]) if fields[7] else 0
                        amount = float(fields[8]) if fields[8] else 0

                        result = {
                            'lastPrice': last_price,
                            'open': open_price,
                            'high': 0,  # 腾讯 API 不提供最高价
                            'low': 0,   # 腾讯 API 不提供最低价
                            'lastClose': last_close,
                            'volume': volume * 100,  # 腾讯 API 返回的是手数，转换为股数
                            'amount': amount,
                            'stockStatus': 0,
                            'askPrice': [],
                            'bidPrice': []
                        }

                        logger.debug(f"使用腾讯 API 获取行情: {stock_code} = {result['lastPrice']}")
                        return result
        except Exception as tencent_error:
            logger.debug(f"使用腾讯 API 获取 {stock_code} 行情失败: {str(tencent_error)}")

        # 方法2: 尝试使用 akshare (备用方案，用于获取完整数据)
        if ak is not None:
            try:
                df = ak.stock_zh_a_spot()
                if not df.empty and '代码' in df.columns:
                    stock_row = df[df['代码'] == code_part]
                    if not stock_row.empty:
                        row = stock_row.iloc[0]
                        last_close = row.get('昨收', 0)

                        result = {
                            'lastPrice': float(row.get('最新价', 0)),
                            'open': float(row.get('今开', 0)),
                            'high': float(row.get('最高', 0)),
                            'low': float(row.get('最低', 0)),
                            'lastClose': float(last_close),
                            'volume': float(row.get('成交量', 0)),
                            'amount': float(row.get('成交额', 0)),
                            'stockStatus': 0,
                            'askPrice': [],
                            'bidPrice': []
                        }

                        logger.debug(f"使用 akshare 获取行情: {stock_code} = {result['lastPrice']}")
                        return result
            except Exception as akshare_error:
                logger.debug(f"使用 akshare 获取 {stock_code} 行情失败: {str(akshare_error)}")

        # 方法3: 尝试使用 QMT 的 get_full_tick (备用方案)
        try:
            if not self.xtdata:
                self._init_qmt_modules()

            tick_data = self.xtdata.get_full_tick([stock_code])
            if tick_data and stock_code in tick_data:
                data = tick_data[stock_code]
                last_price = data.get('lastPrice', 0)

                if last_price and last_price > 0:
                    logger.debug(f"使用 get_full_tick 获取实时价格: {stock_code} = {last_price}")

                    result = {
                        'lastPrice': float(last_price),
                        'open': float(data.get('open', 0)),
                        'high': float(data.get('high', 0)),
                        'low': float(data.get('low', 0)),
                        'lastClose': float(data.get('lastClose', 0)),
                        'volume': float(data.get('volume', 0)),
                        'amount': float(data.get('amount', 0)),
                        'askPrice': data.get('askPrice', []),
                        'bidPrice': data.get('bidPrice', []),
                        'askVol': data.get('askVol', []),
                        'bidVol': data.get('bidVol', []),
                        'stockStatus': data.get('stockStatus', 0)
                    }
                    return result
        except Exception as tick_error:
            logger.debug(f"使用 get_full_tick 获取行情失败: {stock_code}, 错误: {str(tick_error)}")

        # 方法4: 使用日K数据获取最新收盘价（备用方案）
        try:
            if not self.xtdata:
                self._init_qmt_modules()

            from datetime import datetime, timedelta
            import time

            end_date_str = now().strftime("%Y%m%d")
            start_date_str = (now() - timedelta(days=365)).strftime("%Y%m%d")

            # 先下载历史数据
            logger.debug(f"正在下载 {stock_code} 的日K数据...")
            self.xtdata.download_history_data(
                stock_code=stock_code,
                period='1d',
                start_time=start_date_str,
                end_time=end_date_str,
                incrementally=False
            )
            time.sleep(0.5)

            # 使用 get_market_data 获取最新数据
            market_data = self.xtdata.get_market_data(
                field_list=['time', 'open', 'high', 'low', 'close', 'volume', 'amount'],
                stock_list=[stock_code],
                period='1d',
                start_time=start_date_str,
                end_time=end_date_str,
                count=-1,
                fill_data=True
            )

            if market_data and 'close' in market_data and not market_data['close'].empty:
                res_df = market_data['close']
                if stock_code in res_df.columns:
                    close_series = res_df[stock_code].dropna()
                    if not close_series.empty:
                        last_price = float(close_series.iloc[-1])

                        open_price = float(market_data['open'][stock_code].iloc[-1]) if 'open' in market_data and stock_code in market_data['open'].columns else last_price
                        high_price = float(market_data['high'][stock_code].iloc[-1]) if 'high' in market_data and stock_code in market_data['high'].columns else last_price
                        low_price = float(market_data['low'][stock_code].iloc[-1]) if 'low' in market_data and stock_code in market_data['low'].columns else last_price
                        volume = float(market_data['volume'][stock_code].iloc[-1]) if 'volume' in market_data and stock_code in market_data['volume'].columns else 0
                        amount = float(market_data['amount'][stock_code].iloc[-1]) if 'amount' in market_data and stock_code in market_data['amount'].columns else 0

                        last_close = last_price
                        if len(close_series) > 1:
                            last_close = float(close_series.iloc[-2])

                        result = {
                            'lastPrice': last_price,
                            'open': open_price,
                            'high': high_price,
                            'low': low_price,
                            'lastClose': last_close,
                            'volume': volume,
                            'amount': amount,
                            'stockStatus': 0,
                            'askPrice': [],
                            'bidPrice': []
                        }
                        return result
        except Exception as kline_error:
            logger.debug(f"使用日K数据获取行情失败: {str(kline_error)}")

        logger.error(f"所有方法都无法获取 {stock_code} 的价格")
        return {'lastPrice': 0, 'stockStatus': 0}

    def buy_stock(self, stock_code: str, volume: int, price: float = 0,
                  price_type: str = "limit", strategy_name: str = "", remark: str = "") -> int:
        """
        买入股票/可转债

        Args:
            stock_code: 证券代码
            volume: 买入数量
            price: 委托价格（市价单时可为0）
            price_type: 价格类型 (limit/market)
            strategy_name: 策略名称
            remark: 备注

        Returns:
            订单编号，-1表示失败
        """
        if not self.is_connected():
            raise Exception("QMT 未连接")

        # 确定价格类型
        if price_type == "market":
            # 使用限价单模拟市价单
            pt = self.xtconstant.FIX_PRICE
            # 获取当前价格并乘以 1.01
            quote = self.get_quote(stock_code)
            current_price = quote.get('lastPrice', 0)
            if current_price <= 0:
                raise Exception(f"无法获取 {stock_code} 的当前价格")
            price = current_price * 1.01
        else:
            pt = self.xtconstant.FIX_PRICE

        logger.info(f"买入: {stock_code}, 数量: {volume}, 价格: {price}, 类型: {price_type}")

        order_id = self.trader.order_stock(
            self.account,
            stock_code,
            self.xtconstant.STOCK_BUY,
            volume,
            pt,
            price,
            strategy_name,
            remark
        )

        if order_id > 0:
            logger.success(f"买入委托成功: {stock_code}, 订单号: {order_id}")
        else:
            logger.error(f"买入委托失败: {stock_code}")

        return order_id

    def sell_stock(self, stock_code: str, volume: int, price: float = 0,
                   price_type: str = "limit", strategy_name: str = "", remark: str = "") -> int:
        """
        卖出股票/可转债

        Args:
            stock_code: 证券代码
            volume: 卖出数量
            price: 委托价格（市价单时可为0）
            price_type: 价格类型 (limit/market)
            strategy_name: 策略名称
            remark: 备注

        Returns:
            订单编号，-1表示失败
        """
        if not self.is_connected():
            raise Exception("QMT 未连接")

        # 确定价格类型
        if price_type == "market":
            # 使用限价单模拟市价单
            pt = self.xtconstant.FIX_PRICE
            # 获取当前价格并乘以 0.99
            quote = self.get_quote(stock_code)
            current_price = quote.get('lastPrice', 0)
            if current_price <= 0:
                raise Exception(f"无法获取 {stock_code} 的当前价格")
            price = current_price * 0.99
        else:
            pt = self.xtconstant.FIX_PRICE

        logger.info(f"卖出: {stock_code}, 数量: {volume}, 价格: {price}, 类型: {price_type}")

        order_id = self.trader.order_stock(
            self.account,
            stock_code,
            self.xtconstant.STOCK_SELL,
            volume,
            pt,
            price,
            strategy_name,
            remark
        )

        if order_id > 0:
            logger.success(f"卖出委托成功: {stock_code}, 订单号: {order_id}")
        else:
            logger.error(f"卖出委托失败: {stock_code}")

        return order_id

    def cancel_order(self, order_id: int) -> bool:
        """
        撤单

        Args:
            order_id: 订单编号

        Returns:
            是否成功
        """
        if not self.is_connected():
            raise Exception("QMT 未连接")

        result = self.trader.cancel_order_stock(self.account, order_id)
        return result == 0

    def get_orders(self, cancelable_only: bool = False) -> List[Dict[str, Any]]:
        """
        查询当日委托

        Args:
            cancelable_only: 是否只查询可撤委托

        Returns:
            委托列表
        """
        if not self.is_connected():
            raise Exception("QMT 未连接")

        orders = self.trader.query_stock_orders(self.account, cancelable_only)
        if orders is None:
            return []

        return [
            {
                'order_id': order.order_id,
                'stock_code': order.stock_code,
                'order_type': order.order_type,
                'order_volume': order.order_volume,
                'price': order.price,
                'traded_volume': order.traded_volume,
                'traded_price': order.traded_price,
                'order_status': order.order_status,
                'status_msg': order.status_msg,
                'order_time': order.order_time
            }
            for order in orders
        ]

    def get_trades(self) -> List[Dict[str, Any]]:
        """
        查询当日当日成交

        Returns:
            成交列表
        """
        if not self.is_connected():
            raise Exception("QMT 未连接")

        trades = self.trader.query_stock_trades(self.account)
        if trades is None:
            return []

        return [
            {
                'traded_id': trade.traded_id,
                'stock_code': trade.stock_code,
                'order_type': trade.order_type,
                'traded_volume': trade.traded_volume,
                'traded_price': trade.traded_price,
                'traded_amount': trade.traded_amount,
                'traded_time': trade.traded_time,
                'order_id': trade.order_id
            }
            for trade in trades
        ]

    def is_suspended(self, stock_code: str) -> bool:
        """
        检查股票是否停牌

        Args:
            stock_code: 证券代码

        Returns:
            是否停牌
        """
        quote = self.get_quote(stock_code)
        status = quote.get('stockStatus', 0)
        # 停牌状态码：17 - 临时停牌，20 - 暂停交易至闭市
        return status in [17, 20]

    def validate_path(self, qmt_path: str) -> bool:
        """
        验证 QMT 路径是否有效

        Args:
            qmt_path: MiniQMT 路径

        Returns:
            是否有效
        """
        if not os.path.exists(qmt_path):
            return False

        # 检查是否存在 xtquant 模块
        xtquant_path = os.path.join(qmt_path, 'xtquant')
        if os.path.exists(xtquant_path):
            return True

        # 检查父目录
        parent_path = os.path.dirname(qmt_path)
        xtquant_path = os.path.join(parent_path, 'xtquant')
        return os.path.exists(xtquant_path)
