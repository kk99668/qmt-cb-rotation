# PyInstaller hook for pythonnet
# 确保pythonnet相关的模块和二进制文件被正确包含

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# 收集pythonnet的数据文件
datas = collect_data_files('pythonnet')

# 收集pythonnet的动态库（包括Python.Runtime.dll）
binaries = collect_dynamic_libs('pythonnet')

# 收集clr_loader的动态库
clr_loader_binaries = collect_dynamic_libs('clr_loader')
binaries += clr_loader_binaries

# 注意：collect_dynamic_libs 已经自动收集了所有必要的DLL文件，
# 包括 Python.Runtime.dll，所以不需要手动添加

