# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件

使用方法:
    pyinstaller build.spec

注意:
    1. 首次打包前需要安装 pyinstaller: pip install pyinstaller
    2. 打包后的程序位于 dist/QMT自动调仓/ 目录
"""

import os
import sys

# 导入 PyInstaller 工具函数用于收集子模块和数据文件
try:
    from PyInstaller.utils.hooks import collect_submodules, collect_data_files
except ImportError:
    # 如果 PyInstaller 版本较旧，定义备用函数
    def collect_submodules(package_name):
        """备用函数：返回包名及其基本子模块"""
        return [package_name]
    
    def collect_data_files(package_name):
        """备用函数：返回空列表"""
        return []

# 项目根目录
project_root = os.path.dirname(os.path.abspath(SPEC))

# 分析模块
a = Analysis(
    ['main.py'],
    pathex=[project_root],
    binaries=[],
    datas=[
        # 静态资源文件
        ('assets', 'assets'),
        # akshare 数据文件（包含 calendar.json 等）
        *collect_data_files('akshare'),
    ],
    hiddenimports=[
        # PyWebView 依赖
        'webview',
        'clr',
        # pythonnet 相关模块
        'pythonnet',
        'pythonnet.load',
        'clr_loader',
        'clr_loader.ffi',
        'clr_loader.ffi.netfx',
        'clr_loader.types',
        # pandas 相关模块（QMT行情获取需要）
        'pandas',
        'pandas._libs',
        'pandas._libs.tslibs',
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.nattype',
        'pandas.io.formats.style',
        # 项目模块
        'src',
        'src.api',
        'src.api.api',
        'src.services',
        'src.services.factorcat_service',
        'src.services.qmt_service',
        'src.services.scheduler_service',
        'src.services.auto_trade_service',
        'src.services.notification_service',
        'src.services.update_service',
        'src.models',
        'src.models.database',
        'src.models.schemas',
        'src.utils',
        'src.utils.crypto',
        'src.utils.logger',
        # APScheduler
        'apscheduler.schedulers.background',
        'apscheduler.triggers.cron',
        'apscheduler.triggers.interval',
        # SQLAlchemy
        'sqlalchemy.dialects.sqlite',
        # akshare 及其所有子模块（用于获取行情数据）
        'akshare',
        *collect_submodules('akshare'),  # 收集 akshare 的所有子模块
    ],
    hookspath=['hooks'],  # 使用自定义 hooks 目录
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 与 PyQt5 二选一；环境中若同时安装两者会导致 PyInstaller 中止
        'PyQt6',
        # 排除不需要的大型库
        'matplotlib',
        # 注意：pandas 和 numpy 已移除，因为 QMT 行情获取需要
        'scipy',
        'tkinter',
        '_tkinter',
        # 注意：不在这里排除 'typing'，因为会同时排除内置模块
        # 使用 hook 文件来排除外部 typing 包，保留内置 typing 模块
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# 打包为 pyz
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 创建可执行文件
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QMT自动调仓',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)

# 收集所有文件
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QMT自动调仓',
)

