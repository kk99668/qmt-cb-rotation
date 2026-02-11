"""
WebView2 Runtime 检测和安装工具模块

用于检测 Windows 系统是否安装了 Edge WebView2 Runtime，
如果未安装则自动下载并安装。
"""
import os
import sys
import tempfile
import subprocess
import ctypes
import winreg
from typing import Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# WebView2 Runtime 注册表路径
WEBVIEW2_REGISTRY_PATHS = [
    r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
]

# WebView2 Runtime Evergreen Bootstrapper 下载地址
WEBVIEW2_DOWNLOAD_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

# WebView2 Runtime 下载页面（用于手动安装提示）
WEBVIEW2_DOWNLOAD_PAGE = "https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/"


def is_admin() -> bool:
    """
    检测当前进程是否以管理员身份运行
    
    Returns:
        bool: 如果是管理员返回 True，否则返回 False
    """
    try:
        # 使用 ctypes 调用 Windows API 检测管理员权限
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        # 如果检测失败，假设不是管理员
        return False


def is_webview2_installed() -> bool:
    """
    检测 Edge WebView2 Runtime 是否已安装
    
    Returns:
        bool: 如果已安装返回 True，否则返回 False
    """
    if sys.platform != 'win32':
        return False
    
    # 检查多个可能的注册表路径
    for registry_path in WEBVIEW2_REGISTRY_PATHS:
        try:
            # 尝试打开注册表项
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                registry_path,
                0,
                winreg.KEY_READ
            )
            winreg.CloseKey(key)
            # 如果成功打开，说明已安装
            return True
        except (FileNotFoundError, OSError):
            # 注册表项不存在，继续检查下一个路径
            continue
        except Exception:
            # 其他错误，继续检查
            continue
    
    return False


def show_message_box(title: str, message: str, icon_type: int = 0) -> int:
    """
    显示 Windows 消息框
    
    Args:
        title: 标题
        message: 消息内容
        icon_type: 图标类型
            0 = 无图标
            16 = 错误图标
            32 = 问号图标
            48 = 警告图标
            64 = 信息图标
    
    Returns:
        int: 用户点击的按钮
            1 = OK
            2 = Cancel
    """
    try:
        # 使用 ctypes 调用 Windows MessageBoxW API
        result = ctypes.windll.user32.MessageBoxW(
            0,  # 父窗口句柄（0 表示无父窗口）
            message,
            title,
            0x00000001 | icon_type  # MB_OKCANCEL | icon_type
        )
        return result
    except Exception:
        # 如果 MessageBox 失败，尝试使用 print（作为后备）
        print(f"{title}: {message}")
        return 1


def download_webview2_installer(download_url: str, save_path: str, progress_callback=None) -> bool:
    """
    下载 WebView2 Runtime 安装程序
    
    Args:
        download_url: 下载地址
        save_path: 保存路径
        progress_callback: 进度回调函数，接收 (downloaded, total) 参数
    
    Returns:
        bool: 下载成功返回 True，失败返回 False
    """
    try:
        # 创建请求
        req = Request(download_url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # 打开连接
        with urlopen(req, timeout=30) as response:
            # 获取文件大小
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 8192  # 8KB chunks
            
            # 下载文件
            with open(save_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # 调用进度回调
                    if progress_callback:
                        try:
                            progress_callback(downloaded, total_size)
                        except Exception:
                            pass
        
        # 验证文件是否存在且大小合理
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            return True
        else:
            return False
            
    except (URLError, HTTPError) as e:
        # 网络错误
        return False
    except Exception:
        # 其他错误
        return False


def install_webview2_runtime(installer_path: str) -> Tuple[bool, Optional[str]]:
    """
    安装 WebView2 Runtime
    
    Args:
        installer_path: 安装程序路径
    
    Returns:
        Tuple[bool, Optional[str]]: (是否成功, 错误信息)
    """
    if not os.path.exists(installer_path):
        return False, "安装程序文件不存在"
    
    try:
        # 使用 /install 参数运行安装程序（显示安装界面和进度）
        # 不使用 CREATE_NO_WINDOW，让安装程序显示自己的进度窗口
        process = subprocess.Popen(
            [installer_path, "/install"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待安装完成（最多等待 10 分钟）
        try:
            stdout, stderr = process.communicate(timeout=600)
            return_code = process.returncode
            
            if return_code == 0:
                return True, None
            else:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else f"安装失败，返回码: {return_code}"
                return False, error_msg
        except subprocess.TimeoutExpired:
            process.kill()
            return False, "安装超时（超过 10 分钟）"
            
    except Exception as e:
        return False, f"安装过程出错: {str(e)}"


def check_and_install_webview2() -> Tuple[bool, Optional[str]]:
    """
    检查并安装 WebView2 Runtime（主函数）
    
    流程：
    1. 检查是否已安装，如果已安装则返回成功
    2. 检查管理员权限，如果没有则提示用户以管理员身份运行并退出
    3. 下载安装程序
    4. 安装 WebView2 Runtime
    5. 验证安装是否成功
    
    Returns:
        Tuple[bool, Optional[str]]: (是否成功, 错误信息或提示信息)
            - 如果已安装或安装成功，返回 (True, None)
            - 如果需要用户操作，返回 (False, "提示信息")
            - 如果安装失败，返回 (False, "错误信息")
    """
    # 1. 检查是否已安装
    if is_webview2_installed():
        return True, None
    
    # 2. 检查管理员权限
    if not is_admin():
        message = (
            "检测到系统未安装 Microsoft Edge WebView2 Runtime。\n\n"
            "安装 WebView2 Runtime 需要管理员权限。\n\n"
            "请以管理员身份重新运行此程序，程序将自动下载并安装 WebView2 Runtime。\n\n"
            "或者您可以手动下载安装：\n"
            f"{WEBVIEW2_DOWNLOAD_PAGE}"
        )
        show_message_box(
            "需要管理员权限",
            message,
            icon_type=48  # 警告图标
        )
        return False, "需要管理员权限"
    
    # 3. 显示开始安装提示
    message = (
        "检测到系统未安装 Microsoft Edge WebView2 Runtime。\n\n"
        "程序将自动下载并安装 WebView2 Runtime，这可能需要几分钟时间。\n\n"
        "点击\"确定\"开始安装，点击\"取消\"退出程序。"
    )
    result = show_message_box(
        "安装 WebView2 Runtime",
        message,
        icon_type=64  # 信息图标
    )
    
    if result != 1:  # 用户点击了取消
        return False, "用户取消安装"
    
    # 4. 下载安装程序
    temp_dir = tempfile.gettempdir()
    installer_path = os.path.join(temp_dir, "MicrosoftEdgeWebView2RuntimeInstaller.exe")
    
    # 显示下载提示（非阻塞，使用日志）
    try:
        from loguru import logger
        logger.info("开始下载 WebView2 Runtime 安装程序...")
    except ImportError:
        print("开始下载 WebView2 Runtime 安装程序...")
    
    # 显示下载提示对话框（用户确认后开始下载）
    show_message_box(
        "正在下载",
        "正在下载 WebView2 Runtime 安装程序，请稍候...\n\n"
        "下载完成后将自动开始安装。",
        icon_type=64
    )
    
    download_success = download_webview2_installer(
        WEBVIEW2_DOWNLOAD_URL,
        installer_path,
        progress_callback=None  # 可以在这里添加进度显示
    )
    
    if not download_success:
        error_message = (
            "下载 WebView2 Runtime 安装程序失败。\n\n"
            "可能的原因：\n"
            "- 网络连接问题\n"
            "- 防火墙阻止\n"
            "- 下载服务器不可用\n\n"
            "请检查网络连接后重试，或手动下载安装：\n"
            f"{WEBVIEW2_DOWNLOAD_PAGE}\n\n"
            "程序将退出。"
        )
        show_message_box(
            "下载失败",
            error_message,
            icon_type=16  # 错误图标
        )
        return False, "下载失败"
    
    # 5. 安装 WebView2 Runtime
    try:
        from loguru import logger
        logger.info("开始安装 WebView2 Runtime...")
    except ImportError:
        print("开始安装 WebView2 Runtime...")
    
    # 安装程序会自己显示进度窗口（使用 /install 参数）
    install_success, install_error = install_webview2_runtime(installer_path)
    
    # 清理临时文件
    try:
        if os.path.exists(installer_path):
            os.remove(installer_path)
    except Exception:
        pass  # 忽略清理错误
    
    if not install_success:
        error_message = (
            f"安装 WebView2 Runtime 失败。\n\n"
            f"错误信息：{install_error or '未知错误'}\n\n"
            "请手动下载并安装 WebView2 Runtime：\n"
            f"{WEBVIEW2_DOWNLOAD_PAGE}\n\n"
            "程序将退出。"
        )
        show_message_box(
            "安装失败",
            error_message,
            icon_type=16  # 错误图标
        )
        return False, f"安装失败: {install_error}"
    
    # 6. 验证安装
    if is_webview2_installed():
        show_message_box(
            "安装成功",
            "WebView2 Runtime 安装成功！\n\n"
            "程序将重新启动以使用新的浏览器内核。",
            icon_type=64
        )
        return True, None
    else:
        error_message = (
            "WebView2 Runtime 安装完成，但检测不到安装状态。\n\n"
            "可能需要重启系统后才能生效。\n\n"
            "请重启系统后重新运行程序，或手动验证安装：\n"
            f"{WEBVIEW2_DOWNLOAD_PAGE}\n\n"
            "程序将退出。"
        )
        show_message_box(
            "安装验证失败",
            error_message,
            icon_type=48  # 警告图标
        )
        return False, "安装验证失败"

