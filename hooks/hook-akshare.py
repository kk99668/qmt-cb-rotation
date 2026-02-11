# PyInstaller hook for akshare
# 确保 akshare 相关的模块、数据文件和二进制文件被正确包含

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

# 收集 akshare 的所有子模块
hiddenimports = collect_submodules('akshare')

# 收集 akshare 的数据文件（包括 file_fold/calendar.json 等）
datas = collect_data_files('akshare')

# 收集 akshare 的动态库（如 mini_racer.dll 等）
binaries = collect_dynamic_libs('akshare')
