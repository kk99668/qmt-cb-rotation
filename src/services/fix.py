# 读取文件
with open("qfix.py", "r", encoding="utf-8") as f:
    content = f.read()

# 找到并删除所有从 get_quote 开始到 buy_stock 结束的内容
import re
old_pattern = r'    def get_quote\(self, stock_code: str\) -> Dict\[str, Any\]:.*?)(?=\n    def buy_stock\(self, stock_code: str\) -> int\):'

new_content = re.sub(old_pattern, "    def buy_stock(self, stock_code: str) -> int:", content)

# 然后插入新的 get_quote 方法
new_get_quote = '''    def get_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        获取行情数据（使用腾讯实时行情接口）

        使用腾讯实时行情接口获取单只股票的行情数据，避免获取全市场数据。

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
        if ak is None:
            logger.error("未安装 akshare，请运行: pip install akshare")
            return {'lastPrice': 0, 'stockStatus': 0}

        import requests

        try:
            # 提取代码部分和市场
            # 格式: 123456.SZ -> q=sz123456
            if '.' in stock_code:
                code_part, market = stock_code.split('.')
                market = market.upper()
                # 腾讯接口格式: q=sz123456 或 q=sh123456
                tencent_code = f'q={market.lower()}{code_part}'
            else:
                # 默认上海
                tencent_code = f'q=sh{stock_code}'

            # 方法1: 使用腾讯实时行情接口（高效）
            try:
                url = f'http://qt.gtimg.cn/{tencent_code}'
                response = requests.get(url, timeout=3)

                # 解析返回的数据
                # 格式: v_sh600000="1~浦发银行~600000~11.04~11.16~11.19~..."
                text = response.text.strip()
                if not text.startswith('v_'):
                    raise Exception("腾讯接口返回格式异常")

                # 提取数据部分并按 ~ 分割
                data_str = text.split('=')[1].strip('\').rstrip(';').strip()
                values = data_str.split('~')

                # 腾讯数据格式说明 (~ 分隔):
                # 0: 未知(1)
                # 1: 股票名称
                # 2: 代码
                # 3: 当前价
                # 4: 昨收
                # 5: 开盘
                # 6: 成交量
                # 7: 成交额
                # 8: 成交笔数
                # ...
                if len(values) >= 9:
                    current_price = float(values[3]) if values[3] else 0
                    last_close = float(values[4]) if values[4] else 0
                    open_price = float(values[5]) if values[5] else 0
                    volume = float(values[6]) if values[6] else 0
                    amount = float(values[7]) if values[7] else 0

                    logger.debug(f"使用腾讯接口获取行情: {stock_code} = {current_price}")
                    return {
                        'lastPrice': current_price,
                        'open': open_price,
                        'high': 0,  # 腾讯接口没返回最高价
                        'low': 0,   # 腾讯接口没返回最低价
                        'lastClose': last_close,
                        'volume': volume,
                        'amount': amount,
                        'stockStatus': 0,
                        'askPrice': [],
                        'bidPrice': []
                    }

            except requests.exceptions.Timeout:
                logger.warning(f"腾讯接口超时: {stock_code}")
            except Exception as e:
                logger.warning(f"腾讯接口失败: {stock_code}, 原因: {str(e)}")

            # 方法2: 备用方案 - 使用 akshare 获取 ETF 实时行情
            try:
                etf_df = ak.fund_etf_spot_em()
                # 使用列索引0（代码列）查找，列名可能是中文
                etf_row = etf_df[etf_df.iloc[:, 0].astype(str) == code_part]
                if etf_row.empty:
                    logger.warning(f"未找到股票/ETF: {stock_code} (代码: {code_part})")
                    return {'lastPrice': 0, 'stockStatus': 0}

                row = etf_row.iloc[0]
                # (索引访问数据（避免中文列名编码问题）
                # 索引: 0=代码, 1=名称, 2=昨收, 5=价格, 7=成交量, 8=成交额, 9=市价(最新), 10=最高, 11=最低
                last_close = float(row.iloc[2]) if len(row) > 2 else 0
                current_price = float(row.iloc[9]) if len(row) > 9 else last_close
                high_price = float(row.iloc[10]) if len(row) > 10 else current_price
                low_price = float(row.iloc[11]) if len(row) > 11 else current_price
                volume = float(row.iloc[7]) if len(row) > 7 else 0
                amount = float(row.iloc[8]) if len(row) > 8 else 0

                logger.debug(f"使用 akshare ETF 接口获取行情: {stock_code} = {current_price}")
                return {
                    'lastPrice': current_price,
                    'open': current_price,  # ETF接口没有今开数据
                    'high': high_price,
                    'low': low_price,
                    'lastClose': last_close,
                    'volume': volume,
                    'amount': amount,
                    'stockStatus': 0,
                    'askPrice': [],
                    'bidPrice': []
                }
            except Exception as etf_e:
                logger.warning(f"ETF行情获取失败: {stock_code}, 原因: {str(etf_e)}")

            return {'lastPrice': 0, 'stockStatus': 0}

        except Exception as e:
            logger.error(f"获取 {stock_code} 行情失败: {str(e)}")
            return {'lastPrice': 0, 'stockStatus': 0}
    
    def buy_stock'''

# 在 def buy_stock 之前插入新的 get_quote
insert_pos = new_content.find('    def buy_stock(self, stock_code: str) -> int:')
if insert_pos != -1:
    final_content = new_content[:insert_pos] + new_get_quote + new_content[insert_pos:]
    
    with open("qmt_service.py", "w", encoding="utf-8") as f:
        f.write(final_content)
    
    print("Successfully replaced get_quote method")
else:
    print("Could not find insert position")
