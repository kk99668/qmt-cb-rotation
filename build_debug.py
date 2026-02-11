"""
打包脚本 - 处理 typing 包兼容性问题
"""
import os
import sys
import subprocess


def check_typing_package():
    """检查 typing 包是否存在"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "typing"],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        return result.returncode == 0
    except Exception:
        return False


def temporarily_rename_typing_package():
    """临时重命名 typing 包目录以避免 PyInstaller 检测"""
    import site
    site_packages = site.getsitepackages()
    renamed_paths = []
    
    for sp_dir in site_packages:
        typing_path = os.path.join(sp_dir, "typing")
        typing_backup = os.path.join(sp_dir, "typing.backup_for_pyinstaller")
        
        if os.path.exists(typing_path) and not os.path.exists(typing_backup):
            try:
                os.rename(typing_path, typing_backup)
                renamed_paths.append((typing_path, typing_backup))
                print(f"[信息] 临时重命名 typing 包: {typing_path} -> {typing_backup}")
            except (PermissionError, Exception) as e:
                print(f"[警告] 无法重命名 typing 包: {e}")
    
    return renamed_paths


def restore_typing_package(renamed_paths):
    """恢复 typing 包目录"""
    for original_path, backup_path in renamed_paths:
        if os.path.exists(backup_path):
            try:
                os.rename(backup_path, original_path)
                print(f"[信息] 恢复 typing 包: {backup_path} -> {original_path}")
            except Exception as e:
                print(f"[警告] 无法恢复 typing 包: {e}")


def run_pyinstaller():
    """执行 PyInstaller 打包"""
    project_root = os.path.dirname(os.path.abspath(__file__))
    build_spec = os.path.join(project_root, "build.spec")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", build_spec],
            cwd=project_root,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return result
    except Exception as e:
        print(f"[错误] PyInstaller 执行异常: {e}")
        return None


def main():
    """主函数"""
    print("=" * 50)
    print("QMT自动调仓 - 打包脚本")
    print("=" * 50)
    print()
    
    # 检查 typing 包
    typing_installed = check_typing_package()
    
    # 如果发现 typing 包，临时重命名以避免 PyInstaller 使用外部包
    renamed_paths = []
    if typing_installed:
        print("[信息] 检测到外部 typing 包，临时重命名以避免冲突...")
        renamed_paths = temporarily_rename_typing_package()
        if not renamed_paths:
            print("[警告] 无法重命名 typing 包，如果打包失败，请以管理员权限运行")
    
    # 执行 PyInstaller
    pyinstaller_result = None
    try:
        print("[信息] 开始打包...")
        pyinstaller_result = run_pyinstaller()
    finally:
        # 无论成功与否，都恢复 typing 包
        if renamed_paths:
            print("[信息] 恢复 typing 包...")
            restore_typing_package(renamed_paths)
    
    # 返回退出码
    if pyinstaller_result and pyinstaller_result.returncode == 0:
        print()
        print("=" * 50)
        print("打包完成！")
        print("=" * 50)
        sys.exit(0)
    else:
        print()
        print("=" * 50)
        print("打包失败，请检查错误信息")
        print("=" * 50)
        sys.exit(1)


if __name__ == "__main__":
    main()
