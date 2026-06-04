"""
femCompiler/task_pause.py
异步任务暂停与恢复 — 基于 asyncio.Event 的新实现

功能：
- 暂停当前协程（分支），保存变量快照到文件，等待外部恢复信号
- 恢复指定任务
- 从快照文件恢复变量到 VarManager
"""

import json
import os
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio

# 项目根目录下的 .cache 文件夹
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PAUSE_DIR = os.path.join(_ROOT_DIR, ".cache")


def _serialize_var(value: Any) -> Any:
    """将变量值转换为可 JSON 序列化的格式，无法序列化时转成字符串"""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_var(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_var(v) for k, v in value.items()}
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def save_snapshot(vm, task_id: str = "", node_name: str = "", filepath: Optional[str] = None) -> str:
    """
    保存当前 vm 的全局变量到 JSON 文件，返回文件路径。
    
    参数：
    - vm: VarManager 实例
    - task_id: 任务/分支标识
    - node_name: 暂停的节点 ID
    - filepath: 指定保存路径，默认自动生成
    """
    from femCompiler.FEM_runtime import _current_context

    os.makedirs(DEFAULT_PAUSE_DIR, exist_ok=True)

    ctx = _current_context.get()
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "node_name": node_name,
        "globals": {k: _serialize_var(v) for k, v in vm.globals.items()},
        "locals": {k: _serialize_var(v) for k, v in ctx.locals.items()} if ctx else {},
    }

    if filepath is None:
        safe_name = f"pause_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        filepath = os.path.join(DEFAULT_PAUSE_DIR, safe_name)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"[task_pause] 变量快照已保存至: {filepath}")
    return filepath


def load_snapshot(filepath: str) -> Dict[str, Any]:
    """从 JSON 文件加载快照"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def restore_snapshot(vm, filepath: str) -> None:
    """
    从快照文件恢复变量到 vm 中。
    恢复 globals 和当前上下文的 locals。
    """
    data = load_snapshot(filepath)
    if 'globals' in data:
        for k, v in data['globals'].items():
            vm.globals[k] = v
    if 'locals' in data:
        from femCompiler.FEM_runtime import _current_context
        ctx = _current_context.get()
        if ctx:
            for k, v in data['locals'].items():
                ctx.locals[k] = v
    print(f"[task_pause] 变量已从 {filepath} 恢复")


class TaskPauseManager:
    """
    异步任务暂停管理器。
    
    用法：
        manager = TaskPauseManager()
        
        # 暂停当前协程
        await manager.pause(task_id, vm, node_name)
        
        # 从外部恢复
        manager.resume(task_id)
    """

    def __init__(self):
        self._events: Dict[str, asyncio.Event] = {}
        self._snapshots: Dict[str, str] = {}

    async def pause(self, task_id: str, vm, node_name: str = "") -> None:
        """
        暂停当前协程：
        1. 保存变量快照到文件
        2. 挂起协程，等待恢复信号
        3. 收到信号后，从快照恢复变量
        """
        # 1. 保存快照
        filepath = save_snapshot(vm, task_id=task_id, node_name=node_name)
        self._snapshots[task_id] = filepath

        # 2. 创建 Event 并挂起
        event = asyncio.Event()
        self._events[task_id] = event
        print(f"[task_pause] 任务 '{task_id}' 已暂停，等待恢复信号...")
        await event.wait()

        # 3. 收到恢复信号，加载快照
        restore_snapshot(vm, filepath)
        print(f"[task_pause] 任务 '{task_id}' 已恢复，继续执行。")

        # 清理
        del self._events[task_id]

    def resume(self, task_id: str) -> bool:
        """
        恢复暂停的任务。
        返回 True 表示成功发送恢复信号，False 表示任务不存在。
        """
        event = self._events.get(task_id)
        if event is None:
            print(f"[task_pause] 任务 '{task_id}' 不在暂停状态")
            return False
        event.set()
        return True

    def is_paused(self, task_id: str) -> bool:
        """检查任务是否处于暂停状态"""
        return task_id in self._events

    def get_snapshot_path(self, task_id: str) -> Optional[str]:
        """获取任务的快照文件路径"""
        return self._snapshots.get(task_id)