# femBridge/getDir/get_dir.py
"""
get_dir.py

提供 get_user_dir 函数，获取用户数据目录。
优先读取同目录下的 user_dir.txt，若不存在则自动使用项目根目录下的 user_data 文件夹。
"""

import os

def get_user_dir() -> str:
    """
    返回用户数据根目录路径。
    1. 优先从 user_dir.txt 第一行读取。
    2. 若文件不存在，使用 <项目根目录>/user_data，不存在则自动创建。
    """
    module_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(module_dir, "user_dir.txt")

    # 尝试从配置文件读取
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            path = f.readline().strip()
            if not path:
                raise ValueError(f"配置文件 {config_path} 为空")
            return path
    except FileNotFoundError:
        pass  # 文件不存在，使用回退逻辑

    # 回退：项目根目录下的 user_data 文件夹
    # get_dir.py 在 <项目根>/femBridge/getDir/ 下，向上两级即项目根
    project_root = os.path.dirname(os.path.dirname(module_dir))
    fallback = os.path.join(project_root, "user_data")
    os.makedirs(fallback, exist_ok=True)
    print(f"[get_dir] ⚠️ 未找到 user_dir.txt，自动使用回退路径: {fallback}")
    return fallback


def get_approot_dir() -> str:
    """从 approot_dir.txt 读取应用根目录（保留原逻辑不变）"""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(module_dir, "approot_dir.txt")
    with open(config_path, 'r', encoding='utf-8') as f:
        path = f.readline().strip()
        if not path:
            raise ValueError(f"配置文件 {config_path} 为空")
        return path


def get_FEMroot_dir() -> str:
    """从 FEMain_dir.txt 读取 FEM 根目录（保留原逻辑不变）"""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(module_dir, "FEMain_dir.txt")
    with open(config_path, 'r', encoding='utf-8') as f:
        path = f.readline().strip()
        if not path:
            raise ValueError(f"配置文件 {config_path} 为空")
        return path
