"""
更新检查服务
"""
import os
import json
import requests
from typing import Optional, Dict, Any
from loguru import logger

from src.models.schemas import UpdateInfo


class UpdateService:
    """更新检查服务"""
    
    # 当前版本
    CURRENT_VERSION = "1.0.0"
    
    # 更新检查地址（如需启用更新检查，请配置实际的更新服务器地址）
    UPDATE_URL = ""
    
    def __init__(self):
        self.current_version = self.CURRENT_VERSION
        self.latest_info: Optional[UpdateInfo] = None
    
    def check_update(self) -> UpdateInfo:
        """
        检查更新

        Returns:
            更新信息
        """
        # 如果未配置更新 URL，直接返回无更新
        if not self.UPDATE_URL:
            logger.debug("更新检查未配置，跳过")
            return UpdateInfo(
                has_update=False,
                current_version=self.current_version,
                latest_version=self.current_version
            )

        logger.info("正在检查更新...")

        try:
            response = requests.get(self.UPDATE_URL, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get('version', self.current_version)
                
                # 比较版本
                has_update = self._compare_version(latest_version, self.current_version) > 0
                
                self.latest_info = UpdateInfo(
                    has_update=has_update,
                    current_version=self.current_version,
                    latest_version=latest_version,
                    download_url=data.get('download_url', ''),
                    release_notes=data.get('release_notes', '')
                )
                
                if has_update:
                    logger.info(f"发现新版本: {latest_version}")
                else:
                    logger.info("当前已是最新版本")
                
                return self.latest_info
            else:
                logger.warning(f"检查更新失败: HTTP {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.warning("检查更新超时")
        except requests.exceptions.ConnectionError:
            logger.warning("检查更新失败: 网络连接错误")
        except Exception as e:
            logger.warning(f"检查更新失败: {str(e)}")
        
        # 返回默认信息（无更新）
        return UpdateInfo(
            has_update=False,
            current_version=self.current_version,
            latest_version=self.current_version
        )
    
    def _compare_version(self, v1: str, v2: str) -> int:
        """
        比较版本号
        
        Args:
            v1: 版本1
            v2: 版本2
            
        Returns:
            1: v1 > v2
            0: v1 == v2
            -1: v1 < v2
        """
        try:
            parts1 = [int(x) for x in v1.split('.')]
            parts2 = [int(x) for x in v2.split('.')]
            
            # 补齐长度
            max_len = max(len(parts1), len(parts2))
            parts1.extend([0] * (max_len - len(parts1)))
            parts2.extend([0] * (max_len - len(parts2)))
            
            for p1, p2 in zip(parts1, parts2):
                if p1 > p2:
                    return 1
                elif p1 < p2:
                    return -1
            
            return 0
            
        except Exception:
            return 0
    
    def download_update(self, download_url: str, save_path: str) -> bool:
        """
        下载更新文件
        
        Args:
            download_url: 下载地址
            save_path: 保存路径
            
        Returns:
            是否下载成功
        """
        logger.info(f"开始下载更新: {download_url}")
        
        try:
            response = requests.get(download_url, stream=True, timeout=300)
            
            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # 计算进度
                            if total_size > 0:
                                progress = downloaded / total_size * 100
                                logger.debug(f"下载进度: {progress:.1f}%")
                
                logger.success(f"更新下载完成: {save_path}")
                return True
            else:
                logger.error(f"下载失败: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("下载超时")
            return False
        except requests.exceptions.ConnectionError:
            logger.error("下载失败: 网络连接错误")
            return False
        except Exception as e:
            logger.error(f"下载失败: {str(e)}")
            return False
    
    def get_current_version(self) -> str:
        """获取当前版本"""
        return self.current_version

