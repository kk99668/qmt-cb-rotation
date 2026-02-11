"""
因子猫 API 对接服务
"""
import requests
from typing import Optional, List, Dict, Any
from loguru import logger

from src.models.schemas import LoginResult, StrategyInfo, BacktestHistory, BondInfo
from src.services.update_service import UpdateService


class FactorCatService:
    """因子猫 API 对接服务"""
    
    # API 基础地址
    BASE_URL = "https://factor-cat.mzs2025.asia:8003"
    
    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or self.BASE_URL
        self.access_token: Optional[str] = None
        self.session = requests.Session()
        
        version = UpdateService.CURRENT_VERSION
        
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Client-Version': version
        })
    
    def set_token(self, token: str) -> None:
        """设置访问令牌"""
        self.access_token = token
        self.session.headers.update({
            'Authorization': f'Bearer {token}'
        })
    
    def clear_token(self) -> None:
        """清除访问令牌"""
        self.access_token = None
        if 'Authorization' in self.session.headers:
            del self.session.headers['Authorization']
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        发送请求
        
        Args:
            method: 请求方法 (GET, POST, PUT, DELETE)
            endpoint: API 端点
            **kwargs: 其他请求参数
            
        Returns:
            响应数据
            
        Raises:
            Exception: 请求失败时抛出异常
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            
            # 检查响应状态
            if response.status_code >= 400:
                # 尝试提取原始错误信息，优先使用API返回的详细错误
                error_detail = None
                try:
                    error_data = response.json()
                    # 尝试多种可能的错误字段
                    error_detail = (
                        error_data.get('detail') or 
                        error_data.get('message') or 
                        error_data.get('error') or 
                        error_data.get('msg') or
                        str(error_data) if error_data else None
                    )
                except Exception:
                    # 如果不是JSON，尝试获取原始文本
                    error_detail = response.text
                
                # 如果仍然没有错误信息，使用状态码
                if not error_detail or error_detail.strip() == '':
                    error_detail = f"HTTP {response.status_code}"
                
                # 直接抛出原始错误信息，不做二次封装
                raise Exception(error_detail)
            
            return response.json()
            
        except requests.exceptions.Timeout as timeout_error:
            logger.warning(f"API请求超时: {method} {endpoint}, 错误: {str(timeout_error)}")
            raise Exception(f"请求超时: {str(timeout_error)}")
        except requests.exceptions.ConnectionError as connection_error:
            logger.warning(f"API连接失败: {method} {endpoint}, 错误: {str(connection_error)}")
            raise Exception(f"网络连接失败: {str(connection_error)}")
        except requests.exceptions.RequestException as request_error:
            logger.error(f"API请求异常: {method} {endpoint}, 错误: {str(request_error)}")
            raise Exception(str(request_error))
        except Exception:
            # 重新抛出，保持原始异常信息
            raise
    
    def login(self, username: str, password: str) -> LoginResult:
        """
        用户登录
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            登录结果
        """
        logger.info(f"正在登录因子猫账号: {username}")
        
        try:
            data = {
                'username': username,
                'password': password
            }
            
            result = self._request('POST', '/auth/login', json=data)
            
            # 保存 token
            self.set_token(result['access_token'])
            
            logger.success(f"登录成功: {username}")
            
            return LoginResult(
                access_token=result['access_token'],
                token_type=result.get('token_type', 'bearer'),
                username=result.get('username', username),
                role_name=result.get('role_name')
            )
        except Exception as login_error:
            logger.error(f"登录请求失败 - 用户名: {username}, 错误: {str(login_error)}", exc_info=True)
            raise

    def refresh_token(self, username: str, password: str) -> LoginResult:
        """
        使用用户名和密码重新登录以刷新 token。

        Args:
            username: 用户名
            password: 密码

        Returns:
            登录结果（含新 access_token）
        """
        return self.login(username, password)

    def get_strategies(self, page: int = 1, limit: int = 10, search: str = None) -> Dict[str, Any]:
        """
        获取策略列表
        
        Args:
            page: 页码
            limit: 每页数量
            search: 搜索关键词
            
        Returns:
            策略列表数据（包含分页信息）
        """
        params = {
            'page': page,
            'limit': limit
        }
        if search:
            params['search'] = search
        
        result = self._request('GET', '/strategies/', params=params)
        
        # 转换为 StrategyInfo 列表
        items = []
        for item in result.get('items', []):
            strategy_info = StrategyInfo(
                id=item['id'],
                name=item['name'],
                description=item.get('description', ''),
                backtest_count=item.get('backtest_count', 0),
                created_at=item.get('created_at')
            )
            dumped = strategy_info.model_dump(mode='json')
            items.append(dumped)
        
        return {
            'total_count': result.get('total_count', 0),
            'total_pages': result.get('total_pages', 0),
            'page': result.get('page', page),
            'limit': result.get('limit', limit),
            'items': items
        }
    
    def get_backtest_histories(self, strategy_id: int, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """
        获取策略回测记录
        
        Args:
            strategy_id: 策略ID
            page: 页码
            limit: 每页数量
            
        Returns:
            回测记录列表数据（包含分页信息）
        """
        params = {
            'page': page,
            'limit': limit
        }
        
        result = self._request('GET', f'/strategies/{strategy_id}/histories', params=params)
        
        # 转换为 BacktestHistory 列表
        items = []
        for item in result.get('items', []):
            history = BacktestHistory(
                id=item['id'],
                backtest_time=item.get('backtest_time'),
                strategy_return=item.get('strategy_return'),
                win_rate=item.get('win_rate'),
                annualized_return=item.get('annualized_return'),
                max_drawdown=item.get('max_drawdown'),
                sharpe_ratio=item.get('sharpe_ratio')
            )
            dumped = history.model_dump(mode='json')
            items.append(dumped)
        
        return {
            'total_count': result.get('total_count', 0),
            'total_pages': result.get('total_pages', 0),
            'page': result.get('page', page),
            'limit': result.get('limit', limit),
            'items': items
        }
    
    def get_strategy_parameters(self, strategy_id: int, history_id: int) -> Dict[str, Any]:
        """
        获取策略参数
        
        Args:
            strategy_id: 策略ID
            history_id: 回测记录ID
            
        Returns:
            策略参数
        """
        result = self._request('GET', f'/strategies/{strategy_id}/histories/{history_id}/parameters')
        return result.get('parameters', {})
    
    def get_strategy_history_detail(self, strategy_id: int, history_id: int) -> Dict[str, Any]:
        """
        获取策略回测记录详情
        
        Args:
            strategy_id: 策略ID
            history_id: 回测记录ID
            
        Returns:
            回测记录详情
        """
        result = self._request('GET', f'/strategies/{strategy_id}/histories/{history_id}')
        return result
    
    def get_today_bonds(self, strategy_history_id: int) -> List[BondInfo]:
        """
        基于历史回测记录获取今日选债列表
        
        Args:
            strategy_history_id: 回测记录ID
            
        Returns:
            选债列表
        """
        logger.info(f"正在获取今日选债列表, history_id={strategy_history_id}")
        
        data = {
            'strategy_history_id': strategy_history_id
        }
        
        result = self._request('POST', '/bond-selection/today-bond-selection', json=data)
        
        # 解析选债结果
        bonds = []
        if isinstance(result, list) and len(result) > 0:
            selected_bonds = result[0].get('selected_bonds', [])
            for bond in selected_bonds:
                bonds.append(BondInfo(
                    code=bond.get('kzz_code', bond.get('code', '')),
                    name=bond.get('name', ''),
                    price=bond.get('price'),
                    trade_date=bond.get('trade_date')
                ))
        
        logger.success(f"获取选债列表成功，共 {len(bonds)} 只可转债")
        return bonds
    
    def generate_long_term_token(self) -> str:
        """
        生成长期访问令牌
        
        Returns:
            长期访问令牌
        """
        result = self._request('POST', '/auth/generate-long-term-token')
        token = result.get('access_token', '')
        if token:
            self.set_token(token)
        return token

