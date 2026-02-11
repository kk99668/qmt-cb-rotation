"""
QMT自动调仓 - 程序入口

基于 PyWebView 的轻量级桌面应用
"""
import os
import sys
from datetime import datetime

# 在导入webview之前，先初始化pythonnet（Windows平台需要）
# 这可以解决打包后pythonnet加载失败的问题
# 注意：此时日志系统还未初始化，所以不记录日志
if sys.platform == 'win32':
    try:
        # 尝试导入并初始化pythonnet
        import pythonnet
        # 在打包后的环境中，需要先加载.NET运行时
        # 尝试使用.NET Framework运行时（Windows默认）
        try:
            pythonnet.load('netfx')
        except Exception:
            # 如果netfx失败，尝试coreclr（.NET Core）
            try:
                pythonnet.load('coreclr')
            except Exception:
                pass  # 初始化失败，但继续运行，webview可能使用其他后端
    except ImportError:
        pass  # pythonnet未安装，某些功能可能不可用，但不阻止程序运行
    except Exception:
        pass  # 初始化失败，但继续运行

import webview

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import Api
from src.utils.logger import setup_logger
from src.utils.webview2_checker import check_and_install_webview2
from loguru import logger

# 配置 PyWebView 使用 CEF (Chromium) 内核
# 这样可以避免使用系统默认的旧版浏览器（如 IE）
# 注意：这个配置需要在导入 webview 之后，但在使用之前
def configure_webview_backend():
    """配置 PyWebView 使用的浏览器内核"""
    if sys.platform == 'win32':
        try:
            # 尝试导入 CEF
            import cefpython3
            # 如果 CEF 可用，设置环境变量强制使用 CEF
            os.environ['PYWEBVIEW_GUI'] = 'cef'
            return 'cef'
        except ImportError:
            # CEF 不可用，尝试使用 Edge WebView2
            try:
                # 检查是否有 Edge WebView2
                import winreg
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")
                    winreg.CloseKey(key)
                    # Edge WebView2 已安装
                    os.environ['PYWEBVIEW_GUI'] = 'edgechromium'
                    return 'edgechromium'
                except:
                    # Edge WebView2 未安装，使用默认
                    return 'default'
            except:
                return 'default'
    return 'default'


def get_assets_path() -> str:
    """获取静态资源路径"""
    # 打包后的路径
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = PROJECT_ROOT
    
    return os.path.join(base_path, 'assets')


def main():
    """主入口函数"""
    try:
        # 设置日志（优先设置，确保后续错误能被记录）
        log_dir = os.path.join(PROJECT_ROOT, 'logs')
        try:
            setup_logger(log_dir=log_dir)
        except Exception as log_err:
            # 如果日志初始化失败，尝试使用基本日志配置
            import logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s | %(levelname)-8s | %(message)s',
                handlers=[
                    logging.FileHandler(
                        os.path.join(log_dir, f'startup_error_{datetime.now().strftime("%Y%m%d")}.log'),
                        encoding='utf-8'
                    )
                ]
            )
            logging.error(f"日志系统初始化失败: {log_err}", exc_info=True)
        
        logger.info("=" * 50)
        logger.info("QMT自动调仓 启动中...")
        logger.info("=" * 50)
        
        # 检查并安装 WebView2 Runtime（仅在 Windows 平台）
        if sys.platform == 'win32':
            logger.info("检查 WebView2 Runtime 安装状态...")
            webview2_installed, error_msg = check_and_install_webview2()
            
            if not webview2_installed:
                if error_msg:
                    logger.error(f"WebView2 Runtime 检查失败: {error_msg}")
                    # 如果是需要管理员权限或用户取消，直接退出
                    if "需要管理员权限" in error_msg or "用户取消" in error_msg:
                        logger.info("程序退出")
                        sys.exit(1)
                    # 如果是安装失败，也退出
                    logger.error("程序退出，请手动安装 WebView2 Runtime 后重试")
                    sys.exit(1)
            else:
                logger.info("WebView2 Runtime 已安装或安装成功")
        
        # 配置浏览器内核
        backend = configure_webview_backend()
        if backend == 'cef':
            logger.info("已配置使用 CEF (Chromium) 内核")
        elif backend == 'edgechromium':
            logger.info("已配置使用 Edge WebView2 内核")
        else:
            logger.warning("将使用系统默认浏览器内核（可能不支持现代 JavaScript）")
            logger.warning("建议安装 Edge WebView2 Runtime 或 CEF 以获得更好的兼容性")
        
        # 创建 API 实例
        try:
            api = Api()
        except Exception as api_err:
            logger.exception(f"API 初始化失败: {api_err}")
            raise
        
        # 获取静态资源路径
        assets_path = get_assets_path()
        index_html = os.path.join(assets_path, 'index.html')
        
        # 检查 HTML 文件是否存在
        if not os.path.exists(index_html):
            error_msg = f"找不到界面文件: {index_html}"
            logger.error(error_msg)
            logger.info("请确保 assets/index.html 文件存在")
            return
        
        logger.info(f"加载界面: {index_html}")

        # 确保 webview 模块可用
        import webview as wv

        # 创建窗口
        try:
            window = wv.create_window(
                title='QMT自动调仓',
                url=index_html,
                width=1280,
                height=800,
                min_size=(1024, 700),
                js_api=api,  # 暴露 Python API 给前端
                confirm_close=True,  # 关闭时确认
                text_select=True,  # 允许选择文本
            )
        except Exception as window_err:
            logger.exception(f"创建窗口失败: {window_err}")
            raise
        
        # 窗口关闭事件
        def on_closing():
            logger.info("程序正在关闭...")
            try:
                # 停止自动交易
                if api._running:
                    api.stop_trading()
            except Exception as e:
                logger.exception(f"关闭时出错: {e}")
            return True
        
        window.events.closing += on_closing
        
        # 启动应用
        logger.info("启动 PyWebView 窗口...")
        try:
            # 获取当前使用的 GUI 后端
            try:
                gui_backend = os.environ.get('PYWEBVIEW_GUI', 'auto')
                logger.info(f"PyWebView GUI 后端: {gui_backend}")
                # 记录浏览器信息（如果可能）
                try:
                    import webview.platforms
                    logger.info(f"可用的 PyWebView 后端: {webview.platforms.__all__ if hasattr(webview.platforms, '__all__') else '未知'}")
                except:
                    pass
            except:
                pass
            
            # 在服务器环境下，启用调试模式可能会有帮助（但会显示控制台窗口）
            # 如果不需要控制台窗口，可以设为 False
            wv.start(
                debug=False,  # 生产环境设为 False（设为 True 可以显示调试控制台）
                http_server=True,  # 使用 HTTP 服务器（更好的兼容性）
            )
        except Exception as start_err:
            logger.exception(f"启动 PyWebView 失败: {start_err}")
            raise
        
        logger.info("程序已退出")
        
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        # 捕获所有未处理的异常
        error_msg = f"程序运行出现未处理的异常: {e}"
        logger.exception(error_msg)
        
        # 尝试将错误信息写入独立文件（防止日志系统本身有问题）
        try:
            error_file = os.path.join(PROJECT_ROOT, 'logs', f'critical_error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            os.makedirs(os.path.dirname(error_file), exist_ok=True)
            with open(error_file, 'w', encoding='utf-8') as f:
                from datetime import datetime
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"错误: {error_msg}\n")
                f.write(f"异常类型: {type(e).__name__}\n")
                import traceback
                f.write(f"\n完整堆栈跟踪:\n{traceback.format_exc()}\n")
        except Exception:
            pass  # 如果连错误文件都写不了，只能放弃
        
        raise  # 重新抛出异常，让系统知道程序异常退出


if __name__ == '__main__':
    main()

