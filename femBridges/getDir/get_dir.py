#femBridge/getDir/get_dir.py
"""
get_dir.py

提供 get_user_dir 函数，从当前模块所在目录的 user_dir.txt 文件中读取用户目录路径。
"""

import os

def get_user_dir() -> str:
    """
    从与当前模块同目录的 user_dir.txt 文件中读取第一行作为用户目录路径。

    返回:
        str: 读取到的路径（去除首尾空白）。

    异常:
        FileNotFoundError: 如果 user_dir.txt 文件不存在。
        ValueError: 如果文件为空或未包含有效路径。
    """
    # 获取当前模块所在的目录
    module_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建配置文件的完整路径
    config_path = os.path.join(module_dir, "user_dir.txt")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            path = f.readline().strip()
            if not path:
                raise ValueError(f"配置文件 {config_path} 为空，无法读取有效路径。")
            return path
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件未找到: {config_path}") from None
        
        
def get_approot_dir() -> str:
    """
    从与当前模块同目录的 approot_dir.txt 文件中读取第一行作为用户目录路径。

    返回:
        str: 读取到的路径（去除首尾空白）。

    异常:
        FileNotFoundError: 如果 user_dir.txt 文件不存在。
        ValueError: 如果文件为空或未包含有效路径。
    """
    # 获取当前模块所在的目录
    module_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建配置文件的完整路径
    config_path = os.path.join(module_dir, "approot_dir.txt")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            path = f.readline().strip()
            if not path:
                raise ValueError(f"配置文件 {config_path} 为空，无法读取有效路径。")
            return path
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件未找到: {config_path}") from None



def get_FEMroot_dir() -> str:
    """
    从与当前模块同目录的 approot_dir.txt 文件中读取第一行作为用户目录路径。

    返回:
        str: 读取到的路径（去除首尾空白）。

    异常:
        FileNotFoundError: 如果 user_dir.txt 文件不存在。
        ValueError: 如果文件为空或未包含有效路径。
    """
    # 获取当前模块所在的目录
    module_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建配置文件的完整路径
    config_path = os.path.join(module_dir, "FEMain_dir.txt")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            path = f.readline().strip()
            if not path:
                raise ValueError(f"配置文件 {config_path} 为空，无法读取有效路径。")
            return path
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件未找到: {config_path}") from None
