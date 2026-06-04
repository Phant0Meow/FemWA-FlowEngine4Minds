#femCompiler/FEM_runtime.py
"""
FEM Runtime - Scripting Host Engine 运行时 v4.0
负责: VarManager, PythonBridge, 流程执行, AI赋值处理
v4.0: 直接理解新格式 FlowGraph，不再依赖转换层
"""

import importlib.util
import sys
import os
import types
import json
import re
import time
import contextvars
from typing import Any, Dict, List, Optional, Tuple, Set
import threading
from femCompiler.thread_pause import pause_branch
from dataclasses import dataclass
from femBridges.getDir.get_dir import get_FEMroot_dir
from femCompiler.FEM_CLIrenderer import CLIRenderer, emit_step, emit_context_ready, emit_memory_ready

# ============================================================
#  ExecutionContext — 作用域管理 (contextvars 并发隔离)
# ============================================================
_current_context = contextvars.ContextVar('exec_ctx', default=None)
# 新导入 (数据类从 FEM_parser，其他从自身或保留)

from femCompiler.FEM_parser import (
    Script, ModuleDef, ActionDef, FlowGraph, FlowNode, FlowEdge,
    ExecutorType, OutType, ActorRef, DynamicActorRef, VarRef,
    ActorDef, OutDef, InMapping, MethodDef,
)
class FEMVariableError(Exception):
    """FEM 变量相关错误"""
    pass


class FEMException(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")

class FEMConcurrencyError(FEMException):
    def __init__(self, message: str):
        super().__init__("FEM-101", message)
        

class ExecutionContext:
    """进入模块时创建，退出时销毁。contextvars 保证多线程/协程自动隔离。"""
    def __init__(self, module_name: str, module_max_steps: int = 0):
        self.module_name = module_name
        self.locals: Dict[str, Any] = {}
        self.cancel_event: Optional[threading.Event] = None
        self.module_step = 0
        self.module_max_steps = module_max_steps
        self.current_loop_var: Optional[str] = None   # ← 新增
        self.current_node_id: str = ""                # 当前执行的节点 ID

    def __enter__(self):
        self._token = _current_context.set(self)
        return self

    def __exit__(self, *args):
        _current_context.reset(self._token)


# ============================================================
#  VarManager — 变量注册表 (支持 contextvars 作用域隔离)
# ============================================================
class VarManager:
    """管理脚本变量，支持嵌套访问 (dict key / list index)
       支持 contextvars 实现的模块作用域隔离"""

    def __init__(self, initial: Dict[str, Any] = None):
        self.globals: Dict[str, Any] = dict(initial) if initial else {}

    @property
    def vars(self):
        return self.globals

    def _has(self, name: str) -> bool:
        """检查变量名是否已声明（先查 local 再查 global）"""
        ctx = _current_context.get()
        if ctx and name in ctx.locals:
            return True
        return name in self.globals

    def get(self, path: str) -> Any:
        """获取变量值，支持 x, x.y, x[k] 形式，先查 local 再查 global"""
        if not path:
            return None
        tokens = self._tokenize(path)
        if tokens:
            root = tokens[0][0]
            if not self._has(root):
                # 如果 root 以 @ 开头，尝试查找演员
                if root.startswith('@') and hasattr(self, '_actors'):
                    actor = self._actors.get(root)
                    if actor:
                        return root
                # 不是演员，报错
                import traceback
                traceback.print_stack()
                raise FEMVariableError(
                    f"变量 '{root}' 未声明。所有变量必须在 vars: 中预先声明。"
                )
        return self._resolve(path, create=False)

    def set(self, path: str, value: Any, local: bool = False):
        """设置变量值，先查 local 再查 global。local=True 强制写入当前模块 local"""
        tokens = self._tokenize(path)
        if not tokens:
            return
        first = tokens[0][0]
        if not self._has(first):
            import traceback
            traceback.print_stack()
            raise FEMVariableError(
                f"变量 '{first}' 未声明，无法赋值。请在 vars: 中声明该变量。"
            )
        # 判断是否涉及字典键写入，需要加锁
        need_lock = len(tokens) > 1 or ('[' in path)
        lock = threading.Lock() if need_lock else None
        if lock:
            lock.acquire()
        try:
            if len(tokens) == 1:
                ctx = _current_context.get()
                if local and ctx:
                    ctx.locals[first] = value
                elif ctx and first in ctx.locals:
                    ctx.locals[first] = value
                else:
                    self.globals[first] = value
                return value
            else:
                return self._resolve(path, create=False, set_value=value)
        finally:
            if lock:
                lock.release()

    def has(self, name: str) -> bool:
        """检查变量是否存在"""
        ctx = _current_context.get()
        if ctx and name in ctx.locals:
            return True
        return name in self.globals

    def resolve_var(self, name: str) -> Tuple[dict, str]:
        """
        核心函数：找到此时此地的变量，返回 (container, key)，可读可写。
        调用方可以 container[key] 读，也可以 container[key] = val 写。
        """
        ctx = _current_context.get()
        if ctx and name in ctx.locals:
            return ctx.locals, name
        return self.globals, name

    def _resolve(self, path: str, create: bool = False, set_value=...) -> Any:
        """解析路径并取/设值，上下文感知"""
        tokens = self._tokenize(path)
        if not tokens:
            return None

        first = tokens[0][0]
        if set_value is not ... and len(tokens) == 1:
            ctx = _current_context.get()
            if ctx and first in ctx.locals:
                ctx.locals[first] = set_value
            else:
                self.globals[first] = set_value
            return set_value

        ctx = _current_context.get()
        if ctx and first in ctx.locals:
            obj = ctx.locals[first]
        else:
            obj = self.globals.get(first)

        if obj is None and create:
            self.globals[first] = {}
            obj = self.globals[first]

        for i, tok in enumerate(tokens[1:], 1):
            is_last = (i == len(tokens) - 1)
            key, is_attr = tok

            if is_attr:
                if key.startswith('@'):
                    # @ 开头的键一律视为字典键
                    if not isinstance(obj, dict):
                        raise FEMVariableError(f"无法通过 '@{key}' 访问非字典对象: {type(obj)}")
                    if is_last and set_value is not ...:
                        obj[key] = set_value
                        return set_value
                    obj = obj.get(key)
                else:
                    if is_last and set_value is not ...:
                        if isinstance(obj, dict):
                            obj[key] = set_value
                        else:
                            setattr(obj, key, set_value)
                        return set_value
                    if isinstance(obj, dict):
                        obj = obj.get(key)
                    else:
                        obj = getattr(obj, key, None)
            else:
                if is_last and set_value is not ...:
                    obj[key] = set_value
                    return set_value
                if isinstance(obj, dict):
                    obj = obj.get(key)
                elif isinstance(obj, (list, tuple)):
                    obj = obj[int(key)] if isinstance(key, int) or key.isdigit() else obj[key]
                else:
                    obj = None

            if obj is None:
                break

        return obj

    def _tokenize(self, path: str) -> List[Tuple[Any, bool]]:
        """将路径拆分为 token 列表: (key, is_attr)"""
        tokens = []
        i = 0
        current = []
        while i < len(path):
            c = path[i]
            if c == '[':
                if current:
                    tokens.append((''.join(current), True))
                    current = []
                j = path.index(']', i)
                key_str = path[i+1:j].strip()
                key_val = self._eval_key(key_str)
                tokens.append((key_val, False))
                i = j + 1
            elif c == '.':
                if current:
                    tokens.append((''.join(current), True))
                    current = []
                i += 1
            else:
                current.append(c)
                i += 1
        if current:
            tokens.append((''.join(current), True))
        return tokens

    def _eval_key(self, key_str: str) -> Any:
        """求值括号内的 key，可能是变量名或字面量"""
        key_str = key_str.strip().strip('"').strip("'")
        if key_str in self.globals:
            return self.globals[key_str]
        try:
            return int(key_str)
        except ValueError:
            pass
        return key_str

    def snapshot(self) -> Dict[str, Any]:
        """返回变量快照"""
        return dict(self.globals)

    def __repr__(self):
        lines = []
        for k, v in self.globals.items():
            lines.append(f"  {k} = {v!r}")
        ctx = _current_context.get()
        if ctx and ctx.locals:
            for k, v in ctx.locals.items():
                lines.append(f"  [{ctx.module_name}] {k} = {v!r}")
        return "VarManager:\n" + "\n".join(lines)


# ============================================================
#  工具函数
# ============================================================

def extract_ai_assignments(text: str) -> List[Tuple[str, str]]:
    """
    从 AI 输出中提取 SET VARIABLE: <<VAR = expr>> 格式的主动赋值语句。
    支持中英文等价符号：
      SET VARIABLE: <<KILL = @Alice>>
      设定变量：《KILL = @Alice》
      SET VARIABLE: <<KILL += 1>>
      SET VARIABLE: <<KILL = add(@Alice)>>
    """
    pattern = (
        r'(?:SET\s+VARIABLE|设定变量|设置变量)'
        r'\s*[:：]\s*'
        r'(?:<<|《|〈|《《)'
        r'\s*(@?\w+)\s*'      # 变量名，支持 @ 前缀
        r'([+\-]?=)\s*'       # 操作符 = / += / -=
        r'(.+?)'              # 表达式
        r'(?:>>|》|〉|》》)'
    )
    matches = re.findall(pattern, text)
    result = []
    for m in matches:
        var_name = m[0].strip()
        op = m[1].strip()
        value = m[2].strip()
        # 合并操作符和值，如 "= @Alice" 或 "+= 1"
        expr = f"{op} {value}"
        result.append((var_name, expr))
    return result


def parse_assign_syntax(expr: str, var_name: str = ''):
    """
    只支持文档规定的语法：
      = value
      += N
      -= N
      = add(x)
      = remove(x)
    支持中文括号、引号。
    """
    if not isinstance(expr, str):
        raise FEMVariableError(
            f"parse_assign_syntax 需要字符串，但收到了 {type(expr)}: {expr!r}"
        )
    expr = expr.strip()
    # 统一中文符号
    expr = expr.replace('（', '(').replace('）', ')').replace('“', '"').replace('”', '"')

    # 1. += N
    m = re.match(r'\+\=\s*(.+)$', expr)
    if m:
        val_str = m.group(1).strip()
        try:
            return ('increment', float(val_str))
        except ValueError:
            raise FEMVariableError(f"+= 右侧需要数字，得到: {val_str!r}")

    # 2. -= N
    m = re.match(r'\-\=\s*(.+)$', expr)
    if m:
        val_str = m.group(1).strip()
        try:
            return ('increment', -float(val_str))
        except ValueError:
            raise FEMVariableError(f"-= 右侧需要数字，得到: {val_str!r}")

    # 3. = add(...)
    m = re.match(r'=\s*add\((.+)\)$', expr)
    if m:
        return ('add', m.group(1).strip())

    # 4. = remove(...)
    m = re.match(r'=\s*remove\((.+)\)$', expr)
    if m:
        return ('remove', m.group(1).strip())

    # 5. = value
    m = re.match(r'=\s*(.+)$', expr)
    if m:
        value_str = m.group(1).strip()
        if value_str.lower() == 'true': return ('set', True)
        if value_str.lower() == 'false': return ('set', False)
        try:
            if '.' in value_str: return ('set', float(value_str))
            return ('set', int(value_str))
        except ValueError:
            pass
        # 去掉可能的外围引号
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            value_str = value_str[1:-1]
        return ('set', value_str)

    # 无法解析
    raise FEMVariableError(
        f"无法解析赋值表达式: {expr!r}。"
        f"支持的格式: = value, += N, -= N, = add(x), = remove(x)"
    )

def call_python(bridge, path: str, kwargs: dict = None) -> Any:
    """共用的外接 Python 模块调用"""
    kwargs = kwargs or {}
    return bridge.call(path, **kwargs)
    
def _resolve_val(val, vm):
    """递归解析变量值，直到不是 @ 开头的变量引用"""
    if isinstance(val, str) and val.startswith('@') and vm.has(val):
        actual = vm.get(val)
        return _resolve_val(actual, vm)
    return val


def process_ai_result(vm: VarManager, triplets: list, out_defs: list,
                      retry_info: dict = None) -> dict:
    """
    解析 AI 返回的三元组，综合决定：赋值 / 重试 / 报错 / 忽略。
    """
    retry_info = retry_info or {}
    retries_left = retry_info.get('retries_left', 0)
    on_error = retry_info.get('on_error', 'abort')

    ai_values = {}
    for t in triplets:
        if len(t) == 3:
            var_name, value, _ = t
            ai_values[var_name] = value
        elif len(t) == 2:
            var_name, value = t
            ai_values[var_name] = value

    assigned = {}
    missing_required = []

    for out_def in out_defs:
        var_name = getattr(out_def, 'global_name', None) or getattr(out_def, 'var_name', '')
        required = getattr(out_def, 'required', True)
        default = getattr(out_def, 'default', None)

        if var_name in ai_values:
            intent = parse_assign_syntax(str(ai_values[var_name]), var_name)
            op, val = intent
            if op in ('set', 'add', 'remove'):
                # 需要 vm 对应的 runner 来 eval_expr，但 process_ai_result 没有 runner
                # 这里简单处理：如果 val 是 @ 开头的变量，则尝试从 vm 中取最终值
                val = _resolve_val(val, vm)
            intent = (op, val)
            apply_assign(vm, var_name, intent)
            assigned[var_name] = ai_values[var_name]
        else:
            if required:
                missing_required.append(var_name)
            else:
                if default is not None:
                    apply_assign(vm, var_name, ('set', default))
                    assigned[var_name] = default

    if missing_required:
        if retries_left > 0 and on_error in ('retry', None):
            return {'status': 'retry', 'assigned': assigned,
                    'missing_required': missing_required,
                    'error_msg': f"必须变量缺失: {missing_required}，剩余重试 {retries_left-1} 次"}
        elif on_error == 'fallback':
            for var_name in missing_required:
                default = None
                for od in out_defs:
                    od_name = getattr(od, 'global_name', None) or getattr(od, 'var_name', '')
                    if od_name == var_name:
                        default = getattr(od, 'default', None)
                        break
                if default is not None:
                    apply_assign(vm, var_name, ('set', default))
                    assigned[var_name] = default
            return {'status': 'ok', 'assigned': assigned,
                    'missing_required': [],
                    'error_msg': f"必须变量缺失已用默认值兜底: {missing_required}"}
        else:
            return {'status': 'error', 'assigned': assigned,
                    'missing_required': missing_required,
                    'error_msg': f"必须变量缺失且无重试机会: {missing_required}"}

    return {'status': 'ok', 'assigned': assigned,
            'missing_required': [], 'error_msg': None}


def apply_assign(vm: VarManager, var_name: str, intent: tuple):
    """
    执行赋值意图。
    intent: ('set', val) | ('increment', n) | ('add', item) | ('remove', item)
    """
    op, val = intent

    if op == 'set':
        vm.set(var_name, val)

    elif op == 'increment':
        current = vm.get(var_name) or 0
        vm.set(var_name, current + val)

    elif op == 'add':
        current = vm.get(var_name) or []
        if not isinstance(current, list):
            current = [current]
        if val not in current:
            current.append(val)
        vm.set(var_name, current)

    elif op == 'remove':
        current = vm.get(var_name) or []
        if isinstance(current, list) and val in current:
            current.remove(val)
        vm.set(var_name, current)

    else:
        raise ValueError(f"apply_assign: 未知操作 '{op}'")


# ============================================================
#  PythonBridge — 动态加载 .py 并调用函数
# ============================================================
class PythonBridge:
    """加载外部 Python 文件，调用其中函数"""

    def __init__(self, base_dir: str = ""):
        # 不再使用传入的 base_dir，而是使用项目根目录
        self.base_dir = get_FEMroot_dir()
        self.modules: Dict[str, types.ModuleType] = {}

    def load(self, alias: str, filepath: str) -> types.ModuleType:
        """加载 .py 文件，注册为 alias"""
        # 使用项目根目录作为基准
        full_path = os.path.join(self.base_dir, filepath)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Python Bridge: 文件不存在 {full_path}")
        spec = importlib.util.spec_from_file_location(alias, full_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.modules[alias] = mod
        return mod

    def call(self, dotted_name: str, *args, **kwargs) -> Any:
        """调用 module.function 形式的函数"""
        if '.' not in dotted_name:
            raise ValueError(f"Python Bridge: 无效调用格式 '{dotted_name}'，需要 'module.function'")
        alias, func_name = dotted_name.split('.', 1)
        if alias not in self.modules:
            raise KeyError(f"Python Bridge: 模块 '{alias}' 未加载")
        mod = self.modules[alias]
        func = getattr(mod, func_name, None)
        if func is None:
            raise AttributeError(f"Python Bridge: 模块 '{alias}' 中没有函数 '{func_name}'")
        return func(*args, **kwargs)

    def has(self, dotted_name: str) -> bool:
        """检查函数是否存在"""
        if '.' not in dotted_name:
            return False
        alias, func_name = dotted_name.split('.', 1)
        if alias not in self.modules:
            return False
        return hasattr(self.modules[alias], func_name)



@dataclass
class ThreadInfo:
    thread: threading.Thread
    cancel_event: threading.Event
    source_node_id: str        # join等待的源节点
    fork_id: str               # 所属的顶层fork ID

# ============================================================
#  FEMRunner — 运行器 v4.0
# ============================================================
class FEMRunner:
    """执行解析后的 Script - 直接理解新格式 FlowGraph"""


    def __init__(self, script, base_dir: str = ".", verbose: bool = True, event_callback=None,
                 user_api_key: str = None, user_api_provider: str = None,
                 user_api_url: str = None):
        self.script = script
        self.verbose = verbose
        self.user_api_key = user_api_key
        self.user_api_provider = user_api_provider
        self.user_api_url = user_api_url
        self.vm = VarManager(script.vars)
        self.vm._actors = script.actors   # 让 VarManager 能查到演员
        self.base_dir = base_dir          # ← 新增这行
        self.bridge = PythonBridge(base_dir)
        self._func_cache = {}
        self._current_prompt = ""
        self._current_actor_info = {}
        self._current_session_id = 0
        self._current_turn_id = 0
        # ── 事件回调（用于前后端通信） ──
        self._event_callback = event_callback  # callable(event_type, data_dict)
        # ── 人类输入等待机制（FastAPI 模式） ──
        self._human_input_event = None  # threading.Event
        self._human_input_data = None   # str
        self._pause_events = []         # 存储暂停分支的 Event，供恢复使用

        # 发言人状态机
        self.speaker = {"current": None, "last": None}
        self._oratio_idx = 0
        self._step_idx = 0
        
        # ── Session 和 Turn 初始化 ──
        from femCompiler.db_utils import init_database, get_max_session_id, get_or_create_session, get_next_turn_id, session_exists
        init_database()

        session_meta = script.meta.get('session', None)
        if session_meta is None or str(session_meta).strip().lower() == 'new':
            self._current_session_id = get_max_session_id() + 1
            get_or_create_session(session_id=self._current_session_id, title=script.meta.get('name', ''))
            self._current_turn_id = 1
            print(f"[runtime]🆕 新建 session: {self._current_session_id}, turn: 1")
        else:
            try:
                declared_sid = int(session_meta)
            except (ValueError, TypeError):
                print(f"[runtime]❌ meta.session 值无效: {session_meta}")
                raise ValueError(f"meta.session 无效: {session_meta}")
            if not session_exists(declared_sid):
                print(f"[runtime]❌ 声明的 session {declared_sid} 不存在。请使用 session = new 新建。")
                raise ValueError(f"Session {declared_sid} 不存在")
            self._current_session_id = declared_sid
            self._current_turn_id = get_next_turn_id(declared_sid)
            print(f"[runtime]📂 继续 session: {self._current_session_id}, turn: {self._current_turn_id}")

        self.vm.globals['session_id'] = self._current_session_id
        self.vm.globals['turn_count'] = self._current_turn_id

        # 加载 code: 区域声明的 .py 文件
        for alias, filepath in script.code.items():
            # 处理 file: 前缀
            if filepath.startswith('file:"') and filepath.endswith('"'):
                filepath = filepath[6:-1]
            elif filepath.startswith("file:'") and filepath.endswith("'"):
                filepath = filepath[6:-1]
            self.bridge.load(alias, filepath)

        # 求值初始变量
        import ast
        for k in list(self.vm.globals.keys()):
            v = self.vm.globals[k]
            if isinstance(v, str):
                try:
                    evaled = ast.literal_eval(v)
                    self.vm.globals[k] = evaled
                except (ValueError, SyntaxError):
                    pass
                    
        # 线程管理
        self._thread_registry: Dict[str, Dict[str, ThreadInfo]] = {}  # fork_id -> {source_node: ThreadInfo}
        self._join_signins: Dict[str, Dict[str, Tuple[threading.Event, str]]] = {}  # join_node -> {source_node: (event, fork_id)}
        self._join_expected_branches: Dict[str, set] = {}  # join_node -> {fork_entry_node, ...}
        self._thread_lock = threading.Lock()
        self.global_step = 0
        self.global_max_steps = 0
        
        # ── CLI 渲染器（若未提供外部事件回调且非 FastAPI 模式） ──
        if self._event_callback is None and self._human_input_event is None:
            cli_renderer = CLIRenderer(verbose=self.verbose)
            self._event_callback = cli_renderer.handle_event
            self._cli_renderer = cli_renderer   # 保存引用，供清屏命令使用
        else:
            self._cli_renderer = None

        if self.verbose:
            print("\n🔧 Python Bridge 已加载模块:")
            for alias in self.bridge.modules:
                funcs = [name for name, obj in vars(self.bridge.modules[alias]).items()
                         if callable(obj) and not name.startswith('_')]
                print(f"[runtime]{alias}: {funcs}")

    def _emit_event(self, event_type: str, data: dict = None):
        """向前端发送事件"""
        if data:
            # 递归把所有非基础类型转成字符串，确保能安全序列化
            def _sanitize(obj):
                if isinstance(obj, dict):
                    return {k: _sanitize(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_sanitize(item) for item in obj]
                elif isinstance(obj, (str, int, float, bool, type(None))):
                    return obj
                else:
                    return str(obj)
            data = _sanitize(data)
        
        if self._event_callback:
            self._event_callback(event_type, data or {})

    def _parse_single_assignment(self, text: str) -> tuple:
        """
        解析单条赋值文本，返回 (变量名, 表达式)。
        支持格式：@KILL = @Ellis, KILL = @Alice, SCORE += 1, TASKS = add(@Alice)
        解析失败抛出 ValueError。
        """
        # 变量名支持 @ 前缀（如 @KILL）
        m = re.match(r'^\s*(@?\w+)\s*([+\-]?=)\s*(.+)$', text)
        if not m:
            raise ValueError(f"无法解析赋值语句: {text}")
        var_name = m.group(1).strip()
        op = m.group(2).strip()
        value = m.group(3).strip()
        expr = f"{op} {value}"
        #print(f"[runtime][DEBUG _parse_single] text={text!r}, var_name={var_name!r}, op={op!r}, value={value!r}, expr={expr!r}")
        return var_name, expr

    # ══════════════════════════════════════════════════
    #  边遍历辅助
    # ══════════════════════════════════════════════════

    def _follow_next_edge(self, node_id: str, flow) -> Optional[str]:
        """条件求值 + 找下一条边，返回目标节点 ID"""
        cond_edges = [e for e in flow.edges if e.source == node_id and e.condition]
        default_edges = [e for e in flow.edges if e.source == node_id and not e.condition]

        self._func_cache = {}
        for e in cond_edges:
            result = self._eval_condition(e.condition)
            print(f"[runtime]  🔍 此处有条件判断: 条件 = {e.condition}，结果 = {result}")
            if result:
                return e.target

        if default_edges:
            return default_edges[0].target
            
        print(f"[runtime]⚠️ 节点 {node_id} 没有任何符合条件的出边，流程将在此停止。")

        return None

    def _collect_loop_body(self, gateway_id: str, flow) -> Tuple[Set[str], Optional[str], Optional[str]]:
        """
        找出 for 循环体包含的节点，以及循环入口和出口。
        返回 (body_node_ids, body_entry_id, exit_node_id)
        """
        body = set()
        queue = []

        # 从 gateway 出发，所有非自环边的目标是候选入口
        for e in flow.edges:
            if e.source == gateway_id and e.target != gateway_id:
                queue.append(e.target)

        # BFS 收集 body 节点（不穿过 gateway）
        visited = set()
        while queue:
            nid = queue.pop(0)
            if nid in visited or nid == gateway_id:
                continue
            visited.add(nid)
            body.add(nid)

            for e in flow.edges:
                if e.source == nid and e.target != gateway_id and e.target not in visited:
                    queue.append(e.target)

        # body_entry: gateway 的第一条进入 body 的边
        body_entry = None
        for e in flow.edges:
            if e.source == gateway_id and e.target in body:
                body_entry = e.target
                break

        # exit_node: gateway 的边中，目标不在 body 里且不是 gateway 自身的
        exit_node = None
        for e in flow.edges:
            if e.source == gateway_id and e.target != gateway_id and e.target not in body:
                exit_node = e.target
                break

        return body, body_entry, exit_node


    # 线程管理 - 线程注册、取消、等待等方法
    def _register_thread(self, fork_id: str, source_node_id: str, thread: threading.Thread,
                         cancel_event: threading.Event, join_targets: Dict[str, str],
                         arrived_events: Dict[str, threading.Event] = None):
        """注册线程，并为每个join节点预先登记 cancel_event 和 arrived_event"""
        with self._thread_lock:
            if fork_id not in self._thread_registry:
                self._thread_registry[fork_id] = {}
            self._thread_registry[fork_id][source_node_id] = ThreadInfo(
                thread=thread, cancel_event=cancel_event,
                source_node_id=source_node_id, fork_id=fork_id
            )
            # 为每个对应的join节点预先登记（同时保存 arrived_event）
            for join_node, src in join_targets.items():
                if join_node not in self._join_signins:
                    self._join_signins[join_node] = {}
                arrived = arrived_events.get(join_node) if arrived_events else threading.Event()
                self._join_signins[join_node][src] = (cancel_event, fork_id, arrived)

    def _cancel_threads(self, fork_id: str, keep_source_ids: set = None):
        """取消指定fork下不需要保留的分支，并等待线程结束"""
        with self._thread_lock:
            if fork_id not in self._thread_registry:
                return
            infos = self._thread_registry[fork_id]
            for sid, info in list(infos.items()):
                if keep_source_ids and sid in keep_source_ids:
                    continue
                info.cancel_event.set()
        # 等待取消的线程退出
        for sid, info in list(infos.items()):
            if keep_source_ids and sid in keep_source_ids:
                continue
            info.thread.join(timeout=5)

    def _wait_threads(self, fork_id: str, mode: str, count: int = 0):
        """等待指定fork下的线程，支持 all / any / n"""
        with self._thread_lock:
            if fork_id not in self._thread_registry:
                return
            infos = self._thread_registry[fork_id]
            threads = {sid: info.thread for sid, info in infos.items()}
            cancel_events = {sid: info.cancel_event for sid, info in infos.items()}
        
        if mode == 'all':
            for t in threads.values():
                t.join()
        elif mode == 'any':
            while True:
                done = [sid for sid, t in threads.items() if not t.is_alive()]
                if done:
                    break
                time.sleep(0.1)
            self._cancel_threads(fork_id, keep_source_ids=set(done[:1]))
        elif mode == 'n':
            while True:
                done = [sid for sid, t in threads.items() if not t.is_alive()]
                if len(done) >= count:
                    break
                time.sleep(0.1)
            self._cancel_threads(fork_id, keep_source_ids=set(done[:count]))


    def _fork_branch_runner(self, fork_id, start_node, flow, extra_actions, stop_at, cancel_event,
                            arrived_event=None):
        ctx = ExecutionContext(f"{fork_id}_{start_node}")
        ctx.cancel_event = cancel_event
        with ctx:
            try:
                self._execute_path(flow, start_node, stop_at={stop_at} if stop_at else None,
                                   extra_actions=extra_actions)
            except InterruptedError:
                pass
            finally:
                if arrived_event:
                    arrived_event.set()      # 通知主线程：本分支已到达 join

    def _check_cancel(self):
        """检查当前线程是否被要求取消"""
        ctx = _current_context.get()
        if ctx and ctx.cancel_event and ctx.cancel_event.is_set():
            raise InterruptedError("线程被取消")
            
    def _run_join(self, join_id: str, node, flow, extra_actions=None, max_steps=0) -> Optional[str]:
        """处理 join 节点，等待或取消分支，然后走出口"""
        join_mode = node.meta.get('join_mode', 'all')
        join_count = int(node.meta.get('join_count', 1)) if join_mode == 'n' else 0

        # 收集 join 要求的源节点列表
        # 优先使用 fork 注册的分支入口，避免因图结构导致等待目标不匹配
        expected_sources = self._join_expected_branches.pop(join_id, None)
        if expected_sources is None:
            expected_sources = set()
            for e in flow.edges:
                if e.target == join_id:
                    expected_sources.add(e.source)

        # 等待签到表满足条件（等待各分支的 arrived_event 被设置）
        while True:
            with self._thread_lock:
                signins = self._join_signins.get(join_id, {})
                arrived_sources = {
                    src for src, (_, _, arrived) in signins.items() if arrived.is_set()
                }
            if join_mode == 'all' and arrived_sources == expected_sources:
                break
            elif join_mode == 'any' and arrived_sources:
                break
            elif join_mode == 'n' and len(arrived_sources) >= join_count:
                break
            time.sleep(0.1)

        # 根据模式取消多余分支
        if join_mode in ('any', 'n'):
            keep_count = 1 if join_mode == 'any' else join_count
            with self._thread_lock:
                signins = self._join_signins.get(join_id, {})
                keep_sources = list(signins.keys())[:keep_count]
            for src, (event, fork_id, arrived) in signins.items():
                if src not in keep_sources:
                    event.set()
            for src, (event, fork_id, arrived) in signins.items():
                if src in keep_sources:
                    continue
                with self._thread_lock:
                    info = self._thread_registry.get(fork_id, {}).get(src)
                if info:
                    info.thread.join(timeout=5)

        # 清理签到表
        with self._thread_lock:
            if join_id in self._join_signins:
                del self._join_signins[join_id]

        # 执行 join 节点自身绑定的动作
        self._execute_node_content(node, flow, extra_actions, max_steps, node_id=join_id)

        # 返回出口节点
        for e in flow.edges:
            if e.source == join_id:
                return e.target
        return None

    # ══════════════════════════════════════════════════
    #  统一的图遍历执行器
    # ══════════════════════════════════════════════════

    def _execute_flow(self, flow, start: str = None,
                      stop_at: Set[str] = None,
                      extra_actions: dict = None,
                      max_steps: int = 0) -> Optional[str]:
        """
        统一的 DFS 式图遍历执行器。
        - flow: FlowGraph 对象
        - start: 起始节点 ID
        - stop_at: 遇到这些节点就停下（不执行）
        - extra_actions: 额外的 action 字典（模块局部 action 优先查这里）
        - max_steps: 最大步数 (0=不限)
        返回: 停在哪个节点 ID
        """
        if not flow or not flow.nodes:
            return None

        stop_at = stop_at or set()
        
        # ★ 计算 start：优先参数 > flow.entry > 自动推断
        if start is None:
            start = getattr(flow, 'entry', None) or ''
        if not start:
            # 自动推断：不是任何边 target 的节点就是入口
            targets = {e.target for e in flow.edges}
            for nid in flow.nodes:
                if nid not in targets:
                    start = nid
                    break
        if not start:
            return None
        
        start = start or flow.entry
        if not start:
            return None

        current = start
        step = 0

        prev_node = '[START]' if start != '[START]' else '外部'
        while current:
            # 到达停止点
            if current in stop_at:
                return current

            if max_steps > 0 and step >= max_steps:
                print(f"[runtime]⚠️ 达到最大步数 {max_steps}")
                return current

            step += 1
            node = flow.nodes.get(current)
            if not node:
                raise FEMVariableError(f"节点未定义: {current}")

            # ── 获取节点类型 ──
            kind = node.type if node.type else 'empty'
            info = node.meta
            # ID 覆盖
            if current == '[END]':
                kind = 'end'
            elif current == '[BREAK]':
                kind = 'break'
            # 网关细化
            if kind == 'gateway':
                gw = node.meta.get('gw_kind', '')
                if gw in ('for', 'parfor', 'fork', 'join'):
                    kind = f'gateway_{gw}'
            # 动作 / 模块覆盖（保持原有逻辑，但注意 module_call 优先级）
            if node.module_ref:
                kind = 'module_call'
            elif node.action_name:
                kind = 'action'

            emit_step(self, step, prev_node, current, kind)

            if kind == 'end':
                print("🏁 到达 [END]")
                return current
            if kind == 'break':
                print("⛔ 到达 [BREAK]")
                return current

            # ── FOR / PARFOR 网关 ──
            if kind in ('gateway_for', 'gateway_parfor'):
                prev_node = current
                current = self._run_for_loop(current, node, info, flow,
                                            extra_actions, max_steps)
                continue

            # ── FORK 网关（可能由 parfor 展开） ──
            if kind == 'gateway_fork':
                prev_node = current
                if node.meta.get('is_parfor_fork'):
                    current = self._run_parfor_fork(current, node, flow, extra_actions, max_steps)
                else:
                    current = self._run_fork(current, node, flow,
                                            extra_actions, max_steps)
                continue

            # ── JOIN 网关 ──
            if kind == 'gateway_join':
                prev_node = current
                current = self._run_join(current, node, flow, extra_actions=extra_actions, max_steps=max_steps)
                continue


            # ── 统一执行节点内容（适用于 action / module_call / start / router 等） ──
            self._execute_node_content(node, flow, extra_actions, max_steps, node_id=current)

            # ── 走边进入下一个节点 ──
            next_node = self._follow_next_edge(current, flow)
            if next_node is None and current not in ('[END]', '[BREAK]', '[OUT]'):
                raise FEMVariableError(
                    f"流程在节点 {current} 后找不到下一个节点，且当前节点不是 [END]、[BREAK] 或 [OUT]。"
                )
            prev_node = current
            current = next_node

        # ... 循环结束
        if current is None and prev_node not in ('[END]', '[BREAK]', '[OUT]'):
            print(f"[runtime]⚠️ 流程在节点 {prev_node} 后没有可用的出边，已正常结束。")
        return None


        
        
    # TODO ： 注意：这里 parfor 的实现比较简化，假设循环体内会自然走到结束（没有复杂的回边）。完整实现需要构建独立的子图，但鉴于时间，先提供基本并发框架。
    """
    def _run_parfor(self, gateway_id: str, node, info: dict,
                    flow, extra_actions: dict, max_steps: int) -> Optional[str]:
        parfor 并发执行：为每个迭代生成一个分支，使用 fork + join(all)
        var_name = info.get('var_name', '')
        iterable_expr = info.get('iterable', '')
        iterable = self.eval_expr(iterable_expr)
        if not isinstance(iterable, (list, tuple)):
            return self._follow_next_edge(gateway_id, flow)

        # 找到循环体内的条件分支结构（沿用原解析的边）
        loop_edges = [e for e in flow.edges if e.source == gateway_id and e.condition]
        exit_edges = [e for e in flow.edges if e.source == gateway_id and not e.condition]
        if not loop_edges:
            return self._follow_next_edge(gateway_id, flow)

        # 创建临时 fork 网关和 join 网关
        fork_id = f"__parfor_fork_{gateway_id}__"
        join_id = f"__parfor_join_{gateway_id}__"
        
        # 为每个迭代元素创建一个分支线程
        for i, item in enumerate(iterable):
            # 保存循环变量到线程本地（直接在当前线程模拟？不，我们需要新线程）
            cancel_event = threading.Event()
            # 构建分支入口节点名（重用原有的条件目标节点）
            # 简单处理：所有分支共享同一组条件目标？但需要区分不同迭代变量。
            # 这里采用动态方式：为每个迭代分配一个分支执行函数
            t = threading.Thread(
                target=self._parfor_iter_runner,
                args=(fork_id, gateway_id, flow, extra_actions, max_steps,
                      var_name, item, loop_edges, cancel_event)
            )
            # 注册线程
            self._register_thread(fork_id, f"iter_{i}", t, cancel_event, {join_id: f"iter_{i}"})
            t.start()
        
        # 等待所有分支完成（模拟 join all）
        self._wait_threads(fork_id, 'all')
        # 清理临时 join 签到
        with self._thread_lock:
            if join_id in self._join_signins:
                del self._join_signins[join_id]
        # 返回 exit_node
        return exit_edges[0].target if exit_edges else None
    """

    def _parfor_iter_runner(self, fork_id, gateway_id, flow, extra_actions, max_steps,
                            var_name, item, loop_edges, cancel_event):
        """parfor 单个迭代的执行体"""
        ctx = ExecutionContext(f"parfor_{fork_id}_{item}")
        ctx.cancel_event = cancel_event
        with ctx:
            try:
                # 设置循环变量
                self.vm.set(var_name, item)
                #print(f"[runtime][DEBUG FOR] 设置 {var_name} = {item}, 验证取值: {self.vm.get(var_name)}")
                # 评估条件，选择分支入口
                target = None
                for e in loop_edges:
                    if self._eval_condition(e.condition):
                        target = e.target
                        break
                if target:
                    self._execute_path(flow, target,
                                       stop_at={gateway_id},  # 遇到回边立即停止
                                       extra_actions=extra_actions,
                                       max_steps=max_steps)
            except InterruptedError:
                pass
        
        
    def _execute_node_content(self, node, flow, extra_actions: dict, max_steps: int = 0, node_id: str = ""):
        """执行节点的：绑定的动作 → 绑定的模块 → extra_actions 序列"""
        # 记录当前节点 ID 到线程本地的上下文，避免多线程覆盖
        ctx = _current_context.get()
        if ctx:
            ctx.current_node_id = node_id
        # 0. 处理节点 prompt（视作人类发言）
        if hasattr(node, 'prompt') and node.prompt:
            prompt_text = self._replace_prompt_vars(node.prompt)
            if prompt_text:
                from .save_dialog import save_human_turn
                from .FEM_scope_resolver import resolve_scope
                meta_owner = self.script.meta.get('owner', [])
                fems_id = self.script.meta.get('id', 'unknown')
                actor_info = {'user': f'fems-{fems_id}'}
                # 尝试获取节点绑定的 action 的 scope
                action_scope = ([], [])
                ad = None
                if node.action_name:
                    ad = extra_actions.get(node.action_name) if extra_actions else None
                    if not ad:
                        ad = self.script.actions.get(node.action_name)
                    if ad and ad.scope:
                        action_scope = resolve_scope(ad.scope, self.script.actors, self.vm)
                turn_id, oratio_idx = self._update_speaker('node')
                #print(f"[DEBUG node_prompt] actor_info={actor_info}, meta_owner={meta_owner}, fems_id={self.script.meta.get('id', 'unknown')}")
                event = save_human_turn(
                    session_id=self._current_session_id,
                    turn_id=turn_id,
                    oratio_idx=oratio_idx,
                    user_input=prompt_text,
                    actor_info=actor_info,
                    meta_owner=meta_owner,
                    action_scope=action_scope,
                    is_node_prompt=True,
                    fems_id=self.script.meta.get('id', 'unknown'),
                )
                if event:
                    event.wait()
                print(f"[runtime]📄 节点 prompt 已存入: turn={turn_id}, oratio={oratio_idx}")
        elif self.speaker["current"] == 'ai':
            # 节点无 prompt 但当前为 AI 状态，step_idx 递增（作为内部步骤）
            self._step_idx += 1

        # 1. 执行节点绑定的动作
        if node.action_name:
            ad = extra_actions.get(node.action_name) if extra_actions else None
            if not ad:
                ad = self.script.actions.get(node.action_name)
            if ad:
                print(f"[runtime]⚡ 节点动作: {node.action_name}")
                # 保存当前节点名，供 AI 暂停时使用
                self._current_node_id = node.node_id if hasattr(node, 'node_id') else ''
                self._exec_action_def(ad)
            else:
                print(f"[runtime]⚠️ 动作未定义: {node.action_name}")

        # 2. 执行节点绑定的模块
        if node.module_ref:
            print(f"[runtime]📦 节点模块: &{node.module_ref}")
            self._run_module(node.module_ref)

        # 3. 执行额外的动作/模块序列
        """
        for act in node.extra_actions:
            if act.startswith('&'):
                mod_name = act[1:]
                print(f"[runtime]📦 extra 模块: &{mod_name}")
                self._run_module(mod_name)
            else:
                ad = extra_actions.get(act) if extra_actions else None
                if not ad:
                    ad = self.script.actions.get(act)
                if ad:
                    #print(f"[runtime]⚡ extra 动作: {act}")
                    self._exec_action_def(ad)
                else:
                    raise FEMVariableError(
                        f"未定义的动作(extra): {act}。"
                        f"请检查 flow 中的动作名或模块名是否正确。"
                    )
        """

    # ══════════════════════════════════════════════════
    #  FOR 循环执行
    # ══════════════════════════════════════════════════

    def _run_for_loop(self, gateway_id: str, node, info: dict,
                      flow, extra_actions: dict, max_steps: int) -> Optional[str]:
        """执行 for 循环，返回循环后的下一个节点 ID"""
        var_name = info.get('var_name', '')
        iterable_expr = info.get('iterable', '')
        
        # 求值迭代器
        iterable = self.eval_expr(iterable_expr)
        if not isinstance(iterable, (list, tuple)):
            if self.vm.has(iterable_expr):
                iterable = self.vm.get(iterable_expr)
            if not isinstance(iterable, (list, tuple)):
                print(f"[runtime]⚠️ 迭代器 '{iterable_expr}' 不是列表: {iterable}")
                iterable = []

        # 收集所有从 gateway 出发的边
        all_out_edges = [e for e in flow.edges if e.source == gateway_id]
        # 检查是否有条件边
        has_conditional = any(e.condition for e in all_out_edges)

        loop_entries = []   # 入口边列表
        exit_edge = None    # 出口边

        if has_conditional:
            # 有条件边：条件边是入口，无条件边是出口
            for e in all_out_edges:
                if e.condition:
                    loop_entries.append(e)
                else:
                    if exit_edge is not None:
                        raise ValueError(
                            f"For 循环节点 {gateway_id} 存在多条出口边: {exit_edge.target} 和 {e.target}"
                        )
                    exit_edge = e
        else:
            # 没有条件边：第一条是无条件入口边，如果只有一条出边就既是入口也是出口
            for e in all_out_edges:
                loop_entries.append(e)
            # 对于简单循环（for @wolf in wolves: -> wolf_discuss），
            # wolf_discuss 执行完后会继续沿 flow 走到下一个节点，没有显式回边。
            # 这种情况下没有单独的出口边，循环结束后自然走到 loop_entries 后的下一个节点。
            # 所以 exit_edge 可以保持 None，后续我们手动找出口。

        if not loop_entries:
            raise ValueError(
                f"For 循环节点 {gateway_id} 没有任何循环体入口边。"
                f"请检查 flow 中 for 循环的写法，确保循环体内部有节点。"
            )

        # 建立循环体内节点到其后继节点的边映射（不经过回边）
        edge_map = {}
        for e in flow.edges:
            if e.source != gateway_id:
                if e.source not in edge_map:
                    edge_map[e.source] = []
                edge_map[e.source].append(e)

        # 执行每次迭代
        for i, item in enumerate(iterable):
            if var_name:
                self.vm.set(var_name, item)
                ctx = _current_context.get()
                if ctx:
                    ctx.current_loop_var = var_name
            print(f"[runtime]🔄 For: {var_name} = {item} ({i+1}/{len(iterable)})")

            # 重新评估条件，找到匹配的入口边
            target_node = None
            for e in loop_entries:
                if not e.condition or self._eval_condition(e.condition):
                    target_node = e.target
                    break

            if target_node is None:
                print(f"[runtime]⏭️ For: 无匹配条件，跳过本轮")
                continue

            # 从入口节点出发，一路走到回边（回到 gateway_id）为止
            current = target_node
            ctx = _current_context.get()
            while current and current != gateway_id:
                # 步数检查
                if ctx is not None:
                    if ctx.module_max_steps > 0 and ctx.module_step >= ctx.module_max_steps:
                        print(f"[runtime]⚠️ 模块 '{ctx.module_name}' 达到最大步数 {ctx.module_max_steps}")
                        break
                    ctx.module_step += 1
                else:
                    if self.global_max_steps > 0 and self.global_step >= self.global_max_steps:
                        print(f"[runtime]⚠️ 主流程达到最大步数 {self.global_max_steps}")
                        break
                    self.global_step += 1

                node_obj = flow.nodes.get(current)
                if node_obj:
                    self._execute_node_content(node_obj, flow, extra_actions, 0, node_id=current)

                # 找下一个节点：排除回边（target == gateway_id）
                next_candidates = []
                for e in edge_map.get(current, []):
                    if e.target != gateway_id:
                        next_candidates.append(e)
                if not next_candidates:
                    break

                # 选择下一个节点：有条件的评估条件，否则走第一条
                next_target = None
                for e in next_candidates:
                    if e.condition and self._eval_condition(e.condition):
                        next_target = e.target
                        break
                if next_target is None:
                    next_target = next_candidates[0].target
                current = next_target

        print(f"[runtime]🔄 For: 迭代完毕，退出")

        # 返回出口边的目标节点，如果没有出口边则返回 None
        # 如果有显式出口边，走出口边；否则找循环体最后一个入口边的下一跳
        if exit_edge:
            return exit_edge.target
        if loop_entries:
            # 从第一个入口边开始，顺藤摸瓜找到不在循环体内的下一个节点
            visited = set()
            queue = [loop_entries[0].target]
            while queue:
                cur = queue.pop(0)
                if cur in visited:
                    continue
                visited.add(cur)
                if cur == gateway_id:
                    continue
                for e in flow.edges:
                    if e.source == cur and e.target != gateway_id:
                        queue.append(e.target)
                # 如果当前节点有边直接回到 gateway，说明还在循环体内，继续找
                # 如果没有，当前节点就是出口
            # 简化：找到从任何入口出发，第一条不在循环体内的边
            for e in flow.edges:
                if e.source in [le.target for le in loop_entries] and e.target != gateway_id:
                    # 检查 target 是否有边回到 gateway
                    has_back = any(be.source == e.target and be.target == gateway_id for be in flow.edges)
                    if not has_back:
                        return e.target
        return None


    def _execute_path(self, flow, start: str,
                      stop_at: Set[str] = None,
                      extra_actions: dict = None,
                      max_steps: int = 0):
        current = start
        ctx = _current_context.get()
        local_step = 0

        while current and current not in (stop_at or set()):
            # ── 分层步数检查 ──
            if ctx is not None:
                if ctx.module_max_steps > 0 and ctx.module_step >= ctx.module_max_steps:
                    print(f"[runtime]⚠️ 模块 '{ctx.module_name}' 达到最大步数 {ctx.module_max_steps}")
                    break
                ctx.module_step += 1
            else:
                if self.global_max_steps > 0 and self.global_step >= self.global_max_steps:
                    print(f"[runtime]⚠️ 主流程达到最大步数 {self.global_max_steps}")
                    break
                self.global_step += 1

            node = flow.nodes.get(current)
            if not node:
                break

            # ── 获取节点类型 ──
            kind = node.type if node.type else 'empty'
            info = node.meta
            if current == '[END]':
                kind = 'end'
            elif current == '[BREAK]':
                kind = 'break'
            if kind == 'gateway':
                gw = node.meta.get('gw_kind', '')
                if gw in ('for', 'parfor', 'fork', 'join'):
                    kind = f'gateway_{gw}'
            if node.module_ref:
                kind = 'module_call'
            elif node.action_name:
                kind = 'action'

            if kind == 'end' or kind == 'break':
                return

            if kind in ('gateway_for', 'gateway_parfor'):
                current = self._run_for_loop(current, node, info, flow,
                                            extra_actions, max_steps)
                continue

            if kind == 'gateway_fork':
                current = self._run_fork(current, node, flow,
                                        extra_actions, max_steps)
                continue

            if kind == 'gateway_join':
                current = self._follow_next_edge(current, flow)
                continue

            # 统一执行节点内容
            #print(f"[runtime]_execute_path 正在执行节点: {current}, 类型: {kind}, 动作: {getattr(node, 'action_name', '')}, 模块: {getattr(node, 'module_ref', '')}")
            self._execute_node_content(node, flow, extra_actions, max_steps, node_id=current)

            current = self._follow_next_edge(current, flow)


    # ══════════════════════════════════════════════════
    #  FORK 执行
    # ══════════════════════════════════════════════════

    def _run_fork(self, gateway_id: str, node, flow,
                  extra_actions: dict, max_steps: int = 0) -> Optional[str]:
        """并发执行 fork 分支"""
        # 收集分支入口
        branch_entries = []
        for e in flow.edges:
            if e.source == gateway_id:
                branch_entries.append((e.target, e.condition or ""))
        if not branch_entries:
            return None

        # 找到后续的 join 节点（若有）
        join_node = None
        for nid, n in flow.nodes.items():
            if n.type == 'gateway' and n.meta.get('gw_kind') == 'join':
                join_node = nid
                break

        threads = []
        for idx, (target, cond) in enumerate(branch_entries):
            cancel_event = threading.Event()
            arrived_event = threading.Event()          # 新增到达事件
            src_node = target
            join_targets = {}
            if join_node:
                join_targets[join_node] = src_node

            t = threading.Thread(
                target=self._fork_branch_runner,
                args=(gateway_id, target, flow, extra_actions, join_node, cancel_event, arrived_event)
            )
            threads.append((src_node, t, cancel_event))
            self._register_thread(gateway_id, src_node, t, cancel_event, join_targets,
                                  arrived_events={join_node: arrived_event})
        for _, t, _ in threads:
            t.start()

        if join_node:
            self._join_expected_branches[join_node] = {entry for entry, _ in branch_entries}
            return join_node
        else:
            # 没有 join 时，等待所有分支自然结束再退出
            self._wait_threads(gateway_id, 'all')
            return None
        
        
    def _parfor_instance_runner(self, fork_id, flow, extra_actions, join_id,
                                var_name, item, cancel_event):
        """parfor 单个迭代的执行体"""
        ctx = ExecutionContext(f"parfor_{fork_id}_{item}")
        ctx.cancel_event = cancel_event
        with ctx:
            ctx.locals[var_name] = item
            ctx.current_loop_var = var_name
            ctx.locals["vote"] = ""
            #print(f"[runtime]线程 {var_name}={item} 开始")
            try:
                target = None
                for e in flow.edges:
                    if e.source == fork_id and e.condition:
                        if self._eval_condition(e.condition):
                            target = e.target
                            break
                if target:
                    #print(f"[runtime]线程 {var_name}={item} 进入 target={target}")
                    self._execute_path(flow, target,
                                       stop_at={join_id},
                                       extra_actions=extra_actions)
                #print(f"[runtime]线程 {var_name}={item} 结束")
            except InterruptedError:
                print(f"[runtime]线程 {var_name}={item} 被中断")
        
    def _run_parfor_fork(self, fork_id: str, node, flow, extra_actions: dict, max_steps: int = 0) -> Optional[str]:
        """处理 parfor 展开的 fork：动态实例化分支，并调用 fork/join"""
        var_name = node.meta.get('parfor_var', '')
        iterable_expr = node.meta.get('parfor_iterable', '')
        iterable = self.eval_expr(iterable_expr)
        if not isinstance(iterable, (list, tuple)):
            if self.vm.has(iterable_expr):
                iterable = self.vm.get(iterable_expr)
            if not isinstance(iterable, (list, tuple)):
                print(f"[runtime]⚠️ parfor 迭代器 '{iterable_expr}' 不是列表: {iterable}")
                return self._follow_next_edge(fork_id, flow)

        # 在图中找到对应的 join 节点（通过遍历一条分支链的末端）
        join_id = None
        for e in flow.edges:
            if e.source == fork_id:
                target = e.target
                current = target
                visited = set()
                while current and current not in visited:
                    visited.add(current)
                    next_nodes = [ee.target for ee in flow.edges if ee.source == current]
                    if not next_nodes:
                        break
                    for nid in next_nodes:
                        if nid in flow.nodes:
                            n = flow.nodes[nid]
                            if n.type == 'gateway' and n.meta.get('gw_kind') == 'join':
                                join_id = nid
                                break
                    if join_id:
                        break
                    current = next_nodes[0]
                if join_id:
                    break

        if not join_id:
            return self._run_fork(fork_id, node, flow, extra_actions)

        # 为每个迭代项创建线程（复用 fork 的线程管理）
        threads = []
        for i, item in enumerate(iterable):
            cancel_event = threading.Event()
            t = threading.Thread(
                target=self._parfor_instance_runner,
                args=(fork_id, flow, extra_actions, join_id, var_name, item, cancel_event)
            )
            threads.append((f"iter_{i}", t, cancel_event))
            self._register_thread(fork_id, f"iter_{i}", t, cancel_event, {join_id: f"iter_{i}"})

        for _, t, _ in threads:
            t.start()

        # join all（等待所有分支完成）
        self._wait_threads(fork_id, 'all')

        with self._thread_lock:
            if join_id in self._join_signins:
                del self._join_signins[join_id]

        # ★ 执行 join 节点自身绑定的动作（如 tally、announce_vote、check_end）
        #print(f"[runtime]_run_parfor_fork: join_id={join_id}, has_node={join_id in flow.nodes if join_id else False}")
        if join_id and join_id in flow.nodes:
            join_node = flow.nodes[join_id]
            #print(f"[runtime]join_node extra_actions={join_node.extra_actions}, action_name={join_node.action_name}, module_ref={join_node.module_ref}")
            self._execute_node_content(join_node, flow, extra_actions, 0, node_id=join_id)
        else:
            print(f"[runtime]join_id not found or no node!")

        # 返回 join 出口
        exit_target = None
        for e in flow.edges:
            if e.source == join_id:
                exit_target = e.target
                break
        #print(f"[runtime]join exit target={exit_target}")
        return exit_target

    # ══════════════════════════════════════════════════
    #  Actor 类型查询
    # ══════════════════════════════════════════════════

    def _get_actor_type(self, actor_ref: str) -> Optional[str]:
        """根据 @xxx 引用查找 actor 类型，返回 'ai'/'human' 或 None"""
        if not isinstance(actor_ref, str) or not actor_ref.startswith('@'):
            return None
        name = actor_ref
        if name in self.script.actors:
            return self.script.actors[name].type.value
        return None

    # ══════════════════════════════════════════════════
    #  变量表达式求值
    # ══════════════════════════════════════════════════

    def eval_expr(self, expr: Any) -> Any:
        # 如果不是字符串，直接返回原值（数字、布尔、列表等）
        if not isinstance(expr, str):
            return expr
        expr = expr.strip()

        # ── .type 属性
        type_match = re.match(r'^(@?\w[\w.\[\]]*)\.type$', expr)
        if type_match:
            var_path = type_match.group(1)
            val = self.eval_expr(var_path)
            if isinstance(val, str) and val.startswith('@'):
                actor_type = self._get_actor_type(val)
                if actor_type is None:
                    raise FEMVariableError(f"'{val}' 不是有效的 actor 引用，无法访问 .type 属性")
                return actor_type
            else:
                raise FEMVariableError(f"变量 '{var_path}' 的值 '{val}' 不是 actor 引用")

        # ── @xxx 引用
        if expr.startswith('@'):
            if expr in self.script.actors:
                return expr
            if self.vm._has(expr):
                return self.vm.get(expr)
            if self.vm._has(name):
                return self.vm.get(name)
            raise FEMVariableError(f"未知的 actor 引用: {expr}")

        # 字符串字面量
        if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
            return expr[1:-1]

        # 布尔/None
        if expr in ('true', 'True'): return True
        if expr in ('false', 'False'): return False
        if expr == 'None': return None

        # 数字
        try:
            if '.' in expr: return float(expr)
            return int(expr)
        except ValueError: pass

        # 列表
        if expr.startswith('[') and expr.endswith(']'):
            inner = expr[1:-1].strip()
            if not inner: return []
            items = self._split_items(inner)
            return [self.eval_expr(it.strip()) for it in items]

        # 字典
        if expr.startswith('{') and expr.endswith('}'):
            inner = expr[1:-1].strip()
            if not inner: return {}
            return self._parse_dict_literal(inner)

        # 函数调用
        fc = re.match(r'^(\w+\.\w+)\(([^)]*)\)$', expr)
        if fc:
            return self._call_module_func(fc.group(1), fc.group(2))

        # 字典/列表访问
        dm = re.match(r'^(\w+)\[(.+)\]$', expr)
        if dm:
            container = self.vm.get(dm.group(1))
            if container is not None:
                key_str = dm.group(2).strip().strip('"').strip("'")
                key_val = self.vm.get(key_str)
                if key_val is None:
                    try: key_val = int(key_str)
                    except ValueError: key_val = key_str
                if isinstance(container, dict):
                    return container.get(key_val)
                elif isinstance(container, (list, tuple)):
                    return container[int(key_val)]

        # 点分/索引路径
        if re.match(r'^[A-Za-z_]\w*(\.\w+|\[.+\])*$', expr):
            val = self.vm.get(expr)
            if val is not None: return val

        # 简单变量名
        if re.match(r'^[A-Za-z_]\w*$', expr):
            val = self.vm.get(expr)
            if val is not None: return val

        return expr
        
    def _resolve_actor_path(self, path: str) -> Tuple[str, Optional[str]]:
        """
        解析形如 vote_results.@voter 或 @voter.salary 的路径。
        返回 (容器路径, 动态键值) 或 (原路径, None)。
        """
        if '.@' not in path and not path.startswith('@'):
            return path, None
        parts = path.split('.')
        resolved_parts = []
        dynamic_key = None
        for i, part in enumerate(parts):
            if part.startswith('@'):
                val = self.eval_expr(part)
                if val is None:
                    val = part
                resolved_parts.append(str(val))
                if i == len(parts) - 1:
                    dynamic_key = str(val)
            else:
                resolved_parts.append(part)
        container = '.'.join(resolved_parts[:-1]) if len(resolved_parts) > 1 else resolved_parts[0]
        return container, dynamic_key
        

    def _replace_prompt_vars(self, prompt: str) -> str:
        """替换 prompt 中所有 {expr} 为变量值，任何替换失败都会抛出明确异常"""
        if not isinstance(prompt, str):
            raise FEMVariableError(f"_replace_prompt_vars 需要字符串参数，收到 {type(prompt)}")

        def replacer(m):
            var_path = m.group(1)
            # 0. 先尝试实体视角翻译 @actor.attr
            translated = self._translate_actor_attr(var_path)
            if translated != var_path:
                try:
                    val = self.eval_expr(translated)
                    if val is None:
                        raise FEMVariableError(
                            f"Prompt 变量 {{{var_path}}} (翻译为 {translated}) 的值为 None，请检查变量是否已初始化。"
                        )
                    return str(val)
                except FEMVariableError:
                    raise
                except Exception as e:
                    raise FEMVariableError(
                        f"Prompt 变量替换失败: {{{var_path}}} (翻译为 {translated})，错误: {e}"
                    )

            # 1. 检查是否包含 .@ 动态键模式
            if '.@' in var_path:
                try:
                    container, dynamic_key = self._resolve_actor_path(var_path)
                    if dynamic_key:
                        val = self.vm.get(f"{container}[{dynamic_key}]")
                        if val is None:
                            raise FEMVariableError(
                                f"Prompt 动态键 {{{var_path}}} 的值为 None。"
                            )
                        return str(val)
                    else:
                        # 如果没有动态键，继续尝试其他路径
                        pass
                except FEMVariableError:
                    raise
                except Exception as e:
                    raise FEMVariableError(
                        f"Prompt 动态键替换失败: {{{var_path}}}，错误: {e}"
                    )

            # 2. 如果是以 @ 开头且不在 actors 里的变量，优先从 VarManager 取值
            if var_path.startswith('@') and var_path not in self.script.actors:
                if self.vm.has(var_path):
                    val = self.vm.get(var_path)
                    if val is None:
                        raise FEMVariableError(
                            f"Prompt 变量 {{{var_path}}} 的值为 None，请检查变量是否已赋值。"
                        )
                    return str(val)
                else:
                    raise FEMVariableError(
                        f"Prompt 变量 {{{var_path}}} 在 actors 和 vars 中均未找到。"
                    )

            # 3. 普通路径：直接求值
            try:
                val = self.eval_expr(var_path)
                if val is None:
                    raise FEMVariableError(
                        f"Prompt 变量 {{{var_path}}} 的值为 None，请检查变量是否已初始化。"
                    )
                return str(val)
            except FEMVariableError:
                raise
            except Exception as e:
                raise FEMVariableError(
                    f"Prompt 变量替换失败: {{{var_path}}}，错误: {e}"
                )

        result = re.sub(r'\{([^}]+)\}', replacer, prompt)
        if result is None:
            raise FEMVariableError("_replace_prompt_vars: re.sub 返回了 None")
        return result

    def _call_module_func(self, func_path: str, args_str: str) -> Any:
        cache_key = f"{func_path}({args_str})"
        if cache_key in self._func_cache:
            return self._func_cache[cache_key]
        parts = func_path.split('.', 1)
        if len(parts) != 2: return None
        mod_name, func_name = parts
        mod = self.bridge.modules.get(mod_name)
        if not mod or not hasattr(mod, func_name): return None
        func = getattr(mod, func_name)
        args = []
        if args_str.strip():
            for arg in args_str.split(','):
                arg = arg.strip()
                if not arg: continue
                args.append(self.eval_expr(arg))
        result = func(*args)
        self._func_cache[cache_key] = result
        return result

    # ══════════════════════════════════════════════════
    #  模块执行 — 使用 _execute_flow
    # ══════════════════════════════════════════════════

    def _run_module(self, mod_name: str, args: list = None, max_steps: int = 0):
        """执行子流程 Module，支持嵌套。模块步数从 module.meta.max_steps 读取，0 表示不限。"""
        mod = self.script.modules.get(mod_name)
        if not mod:
            print(f"[runtime]⚠️ 模块 {mod_name} 未定义")
            return

        # 模块自己的步数限制，如果 meta 中没有则不限步数
        mod_meta = getattr(mod, 'meta', None) or {}
        mod_max_steps = mod_meta.get('max_steps', 0)  # 默认 0 = 不限

        with ExecutionContext(mod_name, module_max_steps=mod_max_steps) as ctx:
            # 重置模块瞬态变量
            if mod.locals:
                for local_var, val in mod.locals.items():
                    self.vm.globals[local_var] = val

            print(f"[runtime]📦 进入子流程: &{mod_name}")

            if mod.flow:
                extra_actions = mod.actions if mod.actions else None
                final_node = self._execute_flow(mod.flow,
                                                stop_at={'[OUT]'},
                                                extra_actions=extra_actions)
                if final_node is not None and final_node not in ('[OUT]', '[BREAK]'):
                    raise FEMVariableError(
                        f"模块 {mod_name} 异常终止于节点 {final_node}，预期应到达 [OUT] 或 [BREAK]。"
                    )
                # 若 final_node 为 None，说明 _execute_flow 内部已处理（但根据我们的修改，此时应抛异常，因此不会为 None）
            print(f"[runtime]📦 退出子流程: &{mod_name}")

    def _split_items(self, s: str) -> List[str]:
        items, depth, cur, in_str, qc = [], 0, [], False, None
        for c in s:
            if in_str:
                cur.append(c)
                if c == qc: in_str = False
            else:
                if c in ('"', "'"): in_str, qc = True, c; cur.append(c)
                elif c in ('[', '{', '('): depth += 1; cur.append(c)
                elif c in (']', '}', ')'): depth -= 1; cur.append(c)
                elif c == ',' and depth == 0:
                    items.append(''.join(cur)); cur = []
                else: cur.append(c)
        if cur: items.append(''.join(cur))
        return items

    def _parse_dict_literal(self, inner: str) -> dict:
        result = {}
        items = self._split_items(inner)
        for item in items:
            if ':' in item:
                k, v = item.split(':', 1)
                k = k.strip().strip('"').strip("'")
                result[k] = self.eval_expr(v.strip())
        return result

    # ══════════════════════════════════════════════════
    #  Action 执行调度
    # ══════════════════════════════════════════════════

    def exec_action(self, action_name: str, local_vars: dict = None) -> Any:
        """执行一个 action（从全局 actions 查找）"""
        ad = self.script.actions.get(action_name)
        if ad is None:
            raise KeyError(f"Action '{action_name}' 未找到")
        return self._exec_action_def(ad)

    def _exec_action_def(self, ad) -> Any:
        """执行已找到的 action 定义，统一调度"""
        etype = str(ad.executor_type).split('.')[-1].lower() if ad.executor_type else ''
        eparam = ad.executor_param or ''

        print(f"[runtime]{'='*40}")
        print(f"[runtime]⚡ 执行 action (@{etype}({eparam}))")
        print(f"[runtime]{'='*40}")

        if etype == 'func': return self._exec_func(ad, eparam)
        elif etype == 'assign': return self._exec_assign(ad)
        elif etype == 'ai': return self._exec_ai(ad, eparam)
        elif etype == 'human': return self._exec_human(ad, eparam)
        else:
            print(f"[runtime]⚠️  未支持的执行类型: @{etype}")
            return None

    # ══════════════════════════════════════════════════
    #  @func 处理
    # ══════════════════════════════════════════════════

    def _exec_func(self, ad, eparam: str) -> Any:
        import inspect
        # ── 发送 node_start 事件 ──
        self._emit_event('node_start', {
            'node_name': self._get_current_node_id(),
            'node_type': 'func',
        })
        print(f"[DEBUG _exec_func] 发送 node_start 事件：{ad.name}")
        kwargs = {}
        #print(f"[runtime]_exec_func: action={ad.name}, in_mappings={[(im.local_name, im.global_expr) for im in ad.in_mappings]}")
        if ad.in_mappings:
            for im in ad.in_mappings:
                # 只有包含 .@ 时才尝试动态键
                if '.@' in im.global_expr:
                    container, dynamic_key = self._resolve_actor_path(im.global_expr)
                    if dynamic_key:
                        val = self.vm.get(f"{container}[{dynamic_key}]")
                    else:
                        val = self.eval_expr(im.global_expr)
                else:
                    val = self.eval_expr(im.global_expr)
                print(f"[runtime]📥 in: {im.local_name} = {val!r}")
                kwargs[im.local_name] = val
        else:
            parts = eparam.split('.', 1)
            if len(parts) == 2:
                mod_name, func_name = parts
                mod = self.bridge.modules.get(mod_name)
                if mod and hasattr(mod, func_name):
                    func = getattr(mod, func_name)
                    sig = inspect.signature(func)
                    for param_name, param in sig.parameters.items():
                        if param_name in ('self', 'cls'): continue
                        if self.vm.has(param_name):
                            val = self.vm.get(param_name)
                            kwargs[param_name] = val
                            print(f"[runtime]📥 in(auto): {param_name} = {val!r}")
                        elif param_name in ('dead_list', 'items', 'data', 'values'):
                            alias_map = {
                                'dead_list': 'dead_tonight', 'dead': 'dead_tonight',
                                'votes_dict': 'vote_results', 'votes': 'vote_results',
                                'souls_dict': 'souls',
                            }
                            alias = alias_map.get(param_name, param_name)
                            if self.vm.has(alias):
                                val = self.vm.get(alias)
                                kwargs[param_name] = val
                                print(f"[runtime]📥 in(auto-alias): {param_name} <- {alias} = {val!r}")
                            elif param.default is not inspect.Parameter.empty: pass
                            else:
                                if param.default is not inspect.Parameter.empty:
                                    pass
                                else:
                                    raise FEMVariableError(
                                        f"⚠️ in(auto): 参数 '{param_name}' "
                                        f"无对应变量且无默认值"
                                    )
                        elif param.default is not inspect.Parameter.empty: pass
                        else:
                            print(f"[runtime]⚠️ in(auto): 参数 '{param_name}' 无对应变量且无默认值")

        print(f"[runtime]📞 调用 {eparam}(**kwargs)")
        try:
            result = self.bridge.call(eparam, **kwargs)
            print(f"[runtime]✅ 函数 {eparam} 执行成功，返回值: {result!r}")
        except Exception as e:
            self._emit_event('flow_error', {'error': str(e)})
            print(f"[runtime]❌ 函数 {eparam} 执行失败: {e}")
            raise

        # Out 写回
        if ad.outs and result is not None:
            self._apply_outs(ad, result)

        # ── 发送 func 结果事件 ──
        func_output = {}
        for od in ad.outs:
            var_name = getattr(od, 'global_name', None) or getattr(od, 'var_name', '')
            if var_name:
                try:
                    func_output[var_name] = self.vm.get(var_name)
                except Exception:
                    pass
        self._emit_event('func_result', {
            'node_name': self._get_current_node_id(),
            'output': func_output if func_output else repr(result),
        })
        print(f"[DEBUG _exec_func] 发送 func_result 事件：{ad.name}, output={func_output}")

        return result

    # ══════════════════════════════════════════════════
    #  @assign 处理
    # ══════════════════════════════════════════════════
    def _exec_assign(self, ad) -> Any:
        print(f"[runtime]📝 Assign Action: {ad.name}")
        # ── 发送 node_start 事件 ──
        self._emit_event('node_start', {
            'node_name': self._get_current_node_id(),
            'node_type': 'assign',
        })
        #for i, od in enumerate(ad.outs):
            #print(f"[runtime][DEBUG ASSIGN] out[{i}]: var_name={od.var_name!r}")
        for od in ad.outs:
            expr = od.var_name
            #print(f"[runtime][DEBUG ASSIGN] 处理表达式: {expr!r}")

            # 匹配: path = value / path += N / path -= N / path = add(x) / path = remove(x)
            m = re.match(r'^([\w\[\]@]+)\s*([+\-]?=)\s*(.+)$', expr)
            if not m:
                raise FEMVariableError(
                    f"@assign 无法解析表达式: {expr!r}。"
                    f"请使用 'var = value', 'var += N', 'var -= N' 等格式。"
                )
            path = m.group(1)
            op_str = m.group(2)   # '=', '+=', '-='
            right_raw = m.group(3).strip()

            # 检查变量是否声明
            if not self.vm._has(path):
                raise FEMVariableError(
                    f"@assign 错误：变量 '{path}' 未声明。"
                    f"所有变量必须在 vars: 中预先声明。"
                )

            # 解析右侧值：引号字符串去引号，数字直接转，其他当作变量求值
            right_val = self._eval_right_value(right_raw)

            # 根据运算符构造 intent 并执行
            if op_str == '+=':
                if not isinstance(right_val, (int, float)):
                    raise FEMVariableError(f"@assign += 右侧需要数字，得到: {right_val!r}")
                intent = ('increment', right_val)
            elif op_str == '-=':
                if not isinstance(right_val, (int, float)):
                    raise FEMVariableError(f"@assign -= 右侧需要数字，得到: {right_val!r}")
                intent = ('increment', -right_val)
            elif op_str == '=':
                # 检查是否是 add() / remove() 形式
                add_m = re.match(r'^add\((.+)\)$', right_raw)
                if add_m:
                    item = self._eval_right_value(add_m.group(1).strip())
                    intent = ('add', item)
                else:
                    rem_m = re.match(r'^remove\((.+)\)$', right_raw)
                    if rem_m:
                        item = self._eval_right_value(rem_m.group(1).strip())
                        intent = ('remove', item)
                    else:
                        intent = ('set', right_val)
            else:
                raise FEMVariableError(f"@assign 不支持的运算符: {op_str!r}")

            #print(f"[runtime][DEBUG ASSIGN] intent={intent}")
            try:
                apply_assign(self.vm, path, intent)
                #print(f"[runtime]📤 out: {path} <- {right_val!r}")
            except Exception as e:
                raise FEMVariableError(f"@assign 执行失败：{path} <- {right_val!r}，错误: {e}")

            #print(f"[runtime][DEBUG ASSIGN] 赋值后 {path} = {self.vm.get(path)}")

        # ── 发送 assign 结果事件 ──
        assign_output = {}
        for od in ad.outs:
            expr = od.var_name
            m = re.match(r'^([\w\[\]@]+)\s*[+\-]?=\s*(.+)$', expr)
            if m:
                var_path = m.group(1)
                try:
                    assign_output[var_path] = self.vm.get(var_path)
                except Exception:
                    pass
        self._emit_event('assign_result', {
            'node_name': self._get_current_node_id(),
            'output': assign_output,
        })

        return None

    def _eval_right_value(self, raw: str) -> Any:
        """解析右侧值：引号字符串去引号，数字直接转，其他当作变量求值"""
        raw = raw.strip()
        # 1. 引号字符串（支持中英文单双引号）
        if (len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'", '“', '”')):
            return raw[1:-1]
        # 2. 布尔
        if raw.lower() == 'true':
            return True
        if raw.lower() == 'false':
            return False
        # 3. 数字
        try:
            if '.' in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            pass
        # 4. 列表/字典字面量 ([] 或 {})
        if (raw.startswith('[') and raw.endswith(']')) or (raw.startswith('{') and raw.endswith('}')):
            import ast
            try:
                return ast.literal_eval(raw)
            except (ValueError, SyntaxError) as e:
                raise FEMVariableError(f"无法解析字面量 {raw!r}: {e}")

        # 5. 变量表达式，求值
        return self.eval_expr(raw)
    # ══════════════════════════════════════════════════
    #  @ai 处理
    # ══════════════════════════════════════════════════

    def _exec_ai(self, ad, eparam: str) -> Any:
        print(f"[DEBUG _exec_ai] 进入 AI 动作: {ad.name}")
        self._check_cancel()
        if not eparam and not ad.as_actor:
            print(f"[runtime]🤖 AI Action（无身份信息，将调用裸 AI）")
        else:
            print(f"[runtime]🤖 AI Action")

        prompt = ad.prompt
        if prompt is None:
            raise FEMVariableError(f"AI Action '{ad.name}' 缺少 prompt 定义，请在剧本中提供 prompt 字段。")
        prompt = str(prompt)
        if ad.in_mappings:
            for im in ad.in_mappings:
                try:
                    val = self.eval_expr(im.global_expr)
                    prompt = prompt.replace('{' + im.local_name + '}', str(val))
                except: pass
        prompt = self._replace_prompt_vars(prompt)
        if prompt is None:
            raise FEMVariableError(f"AI Action '{ad.name}' 的 prompt 替换后变为 None，请检查 prompt 中的变量引用是否正确。")
        if not isinstance(prompt, str):
            prompt = str(prompt)

        # ── 发送 node_start 事件（必须在任何可能阻塞的操作之前）──
        scope_info = []
        if hasattr(ad, 'scope') and ad.scope:
            scope_info = ad.scope
        self._emit_event('node_start', {
            'node_name': self._get_current_node_id(),
            'node_type': 'ai',
            'prompt': prompt,
            'scope': scope_info,
        })

        if ad.interrupt: print(f"[runtime]🔔 Interrupt: {ad.interrupt}")
        for od in ad.outs:
            var_name = getattr(od, 'global_name', None) or getattr(od, 'var_name', '')
            print(f"[runtime]📤 out: {var_name}")

        # ── 收集 blocks 并调用 LLM ──
        from femCompiler.block_collector import collect_blocks
        from femBridges.llmBridge import call_ai_with_blocks

        self._current_prompt = prompt
        # 解析动态 actor（@voter → @Alice）
        resolved_eparam = eparam
        if eparam in self.vm.globals:
            resolved_eparam = self.vm.globals[eparam]
        self._current_actor_info = self._get_actor_info(ad, resolved_eparam)
        self._current_turn_id = self.vm.get('turn_count') or 1

        blocks = collect_blocks(
            action=ad,
            meta=self.script.meta,
            actors_def=self.script.actors,
            var_manager=self.vm,
            code_modules=self.bridge.modules,
            memory_defs=self.script.memories,
            context_defs=self.script.contexts,
            session_id=self._current_session_id,
            turn_id=self._current_turn_id,
            actor_info=self._current_actor_info,
            runner=self,
            base_dir=self.base_dir,
        )
        #print(f"[runtime][DEBUG USER_INPUT] {blocks.get('user_input')}")

        # ---- 存储 prompt 到 dialog（在收集 blocks 之后，避免 context 重复） ----
        from .save_dialog import save_human_turn
        from .FEM_scope_resolver import resolve_scope
        meta_owner = self.script.meta.get('owner', [])
        raw_scope = ([], [])
        if hasattr(ad, 'scope') and ad.scope:
            raw_scope = resolve_scope(ad.scope, self.script.actors, self.vm)

        actor_info = {}
        if ad.as_actor and ad.as_actor in self.script.actors:
            as_def = self.script.actors[ad.as_actor]
            if as_def.type.value == 'human':
                actor_info['user'] = str(as_def.source)
        if 'user' not in actor_info and meta_owner:
            actor_info['user'] = str(meta_owner[0])

        turn_id, oratio_idx = self._update_speaker('human')
        fems_id = self.script.meta.get('id', 'unknown')
        event = save_human_turn(
            session_id=self._current_session_id,
            turn_id=turn_id,
            oratio_idx=oratio_idx,
            user_input=prompt,
            actor_info=actor_info,
            meta_owner=meta_owner,
            action_scope=raw_scope,
            is_node_prompt=True,
            fems_id=fems_id,
            prompt_type='prompt',
        )
        if event:
            event.wait()

        if ad.showprompt:
            showprompt_text = str(ad.showprompt)
            if ad.in_mappings:
                for im in ad.in_mappings:
                    try:
                        val = self.eval_expr(im.global_expr)
                        showprompt_text = showprompt_text.replace('{' + im.local_name + '}', str(val))
                    except: pass
            showprompt_text = self._replace_prompt_vars(showprompt_text)
            save_human_turn(
                session_id=self._current_session_id,
                turn_id=turn_id,
                oratio_idx=oratio_idx,
                user_input=showprompt_text,
                actor_info=actor_info,
                meta_owner=meta_owner,
                action_scope=raw_scope,
                is_node_prompt=True,
                fems_id=fems_id,
                prompt_type='showprompt',
            )
            if event_show:
                event_show.wait()
        print(f"[runtime]💬 AI prompt 已存入 dialog: turn={turn_id}, oratio={oratio_idx}")

        # ── 发送上下文就绪事件（供前端气泡显示）──
        ai_name = None
        if self._current_actor_info and 'soul' in self._current_actor_info:
            try:
                from femCompiler.db_utils import get_soul_by_id
                soul_info = get_soul_by_id(str(self._current_actor_info['soul']))
                if soul_info:
                    ai_name = soul_info.get('soul_name', '')
            except Exception:
                pass
        if not ai_name:
            soul_block = blocks.get('soul', '')
            match = re.search(r'名字[：:]\s*(\S+)', soul_block)
            if match:
                ai_name = match.group(1)
        if not ai_name:
            ai_name = "AI"

        showprompt_for_frontend = None
        if hasattr(ad, 'showprompt') and ad.showprompt:
            showprompt_for_frontend = self._replace_prompt_vars(str(ad.showprompt))

        self._emit_event('context_ready', {
            'node_name': self._get_current_node_id(),
            'context': blocks.get('context', ''),
            'showprompt': showprompt_for_frontend,
            'ai_name': ai_name,
        })



        llm_output = call_ai_with_blocks(
            blocks,
            stream_callback=lambda token: self._emit_event('ai_token', {
                'node_name': self._get_current_node_id(),
                'token': token,
            }),
            user_api_key=getattr(self, 'user_api_key', None),
            user_api_provider=getattr(self, 'user_api_provider', None),
            user_api_url=getattr(self, 'user_api_url', None),
        )
        
        if llm_output:
            print(f"[runtime]🤖 AI 回复:\n{llm_output}")

        # 存储 AI 发言
        if llm_output:
            from .save_dialog import save_ai_turn
            from .FEM_scope_resolver import resolve_scope
            meta_owner = self.script.meta.get('owner', [])
            raw_scope = ([], [])
            if hasattr(ad, 'scope') and ad.scope:
                raw_scope = resolve_scope(ad.scope, self.script.actors, self.vm)



            turn_id, step_idx = self._update_speaker('ai')
            event = save_ai_turn(
                session_id=self._current_session_id,
                turn_id=turn_id,
                step_idx=step_idx,
                response=llm_output,
                actor_info=self._current_actor_info,
                meta_owner=meta_owner,
                action_scope=raw_scope,
            )
            if event:
                event.wait()   # 等待数据库写入完成
            print(f"[runtime]🔢 turn → {turn_id}, step → {step_idx}")

        # ── 发送 ai_done 事件 ──
        self._emit_event('ai_done', {
            'node_name': self._get_current_node_id(),
            'output': llm_output or '',
        })

        # 如果 LLM 调用返回 None（真正的失败：无 Key、网络错误等）
        if llm_output is None:
            if ad.interrupt == 'HUMAN':
                # 人工接管
                print(f"[runtime]🔔 等待人类输入...")
                try:
                    user_input = input("  ✏️  > ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("  ⏭️ 跳过")
                    user_input = ""

                if user_input:
                    print(f"[runtime]📝 人类输入: {user_input}")
                    if ad.outs:
                        for od in ad.outs:
                            var_name = getattr(od, 'global_name', None) or getattr(od, 'var_name', '')
                            if var_name:
                                apply_assign(self.vm, var_name, ('set', user_input))
                                print(f"[runtime]📤 out: {var_name} = {user_input!r}")
                    return user_input
                return None
            else:
                # 真正失败：保存快照并暂停分支
                ctx = _current_context.get()
                node_name = ctx.current_node_id if ctx else ''
                print(f"[runtime]⚠️ AI 调用失败（返回 None），保存变量并暂停分支（节点：{node_name}）…")
                self._emit_event('flow_error', {
                    'error': f'AI 调用失败，分支在节点 "{node_name}" 暂停，变量已保存',
                    'node_name': node_name,
                })
                pause_event = threading.Event()
                self._pause_events.append(pause_event)
                pause_branch(self.vm, pause_event, node_name=node_name)
                # 恢复后返回空字符串，流程继续
                return ""
        
        # 如果 llm_output 是空字符串，AI 主动沉默，正常继续
        if llm_output == "":
            print(f"[runtime]🤖 AI 选择了沉默，无输出，流程继续。")

        # 提取赋值：解析成功的直接执行，失败的存入 SET_VARIABLE 列表
        all_matches = re.findall(
            r'(?:SET\s+VARIABLE|设定变量)\s*[:：]\s*(?:<<|《|〈|《《)\s*(.+?)(?:>>|》|〉|》》)',
            llm_output
        )
        SET_VARIABLE = []
        for match in all_matches:
            try:
                var_name, expr = self._parse_single_assignment(match.strip())
                intent = parse_assign_syntax(expr, var_name)
                op, val = intent
                # 仅当 val 是字符串时才进行变量求值（数字、布尔等直接使用）
                if op in ('set', 'add', 'remove') and isinstance(val, str):
                    val = self.eval_expr(val)
                intent = (op, val)
                apply_assign(self.vm, var_name, intent)
                print(f"[runtime]📤 AI赋值: {var_name} {intent}")
            except Exception as e:
                print(f"[runtime]解析失败详情: match={match!r}, error={e}")
                SET_VARIABLE.append(match.strip())
        if SET_VARIABLE:
            print(f"[runtime]⚠️ 解析失败的赋值已存入 SET_VARIABLE 列表: {SET_VARIABLE}")

        if hasattr(ad, 'resolve') and ad.resolve:
            resolve_args = getattr(ad, 'resolve_args', [])
            if resolve_args:
                # 显式传参模式
                resolve_kwargs = {}
                for arg_name in resolve_args:
                    if arg_name == 'SET_VARIABLE':
                        resolve_kwargs['SET_VARIABLE'] = SET_VARIABLE
                    elif arg_name in self.vm.globals:
                        resolve_kwargs[arg_name] = self.vm.globals[arg_name]
                    elif hasattr(ad, 'in_mappings'):
                        found = False
                        for im in ad.in_mappings:
                            if im.local_name == arg_name:
                                try:
                                    resolve_kwargs[arg_name] = self.eval_expr(im.global_expr)
                                    found = True
                                except KeyError:
                                    pass
                                break
                        if not found:
                            raise FEMVariableError(
                                f"resolve 参数 '{arg_name}' 在全局变量和 in: 声明中均未找到。"
                            )
                    else:
                        raise FEMVariableError(
                            f"resolve 参数 '{arg_name}' 在全局变量中未找到。"
                        )
            else:
                # 自动传参模式（兼容旧写法 resolve: game_logic.func）
                resolve_kwargs = {
                    'prompt': prompt,
                    'llm_output': llm_output,
                }
                if SET_VARIABLE:
                    resolve_kwargs['SET_VARIABLE'] = SET_VARIABLE
                if hasattr(ad, 'in_mappings'):
                    for im in ad.in_mappings:
                        try:
                            resolve_kwargs[im.local_name] = self.eval_expr(im.global_expr)
                        except KeyError:
                            pass

            result = call_python(self.bridge, ad.resolve, resolve_kwargs)
            triplets = result if isinstance(result, list) else []
            retry_info = {
                'retries_left': getattr(ad, 'max_retries', 0) or 0,
                'on_error': getattr(ad, 'fallback', 'abort'),
            }
            return process_ai_result(self.vm, triplets, ad.outs, retry_info)

        else:
            return {'status': 'ok', 'assigned_pairs': []}

    # ══════════════════════════════════════════════════
    #  @human 桩
    # ══════════════════════════════════════════════════

    """
    这是不加线程锁的版本
    def _exec_human(self, ad, eparam: str) -> Any:
        print(f"[runtime]👤 Human Action")

        prompt = ad.prompt or ""
        if ad.in_mappings:
            for im in ad.in_mappings:
                try:
                    val = self.eval_expr(im.global_expr)
                    prompt = prompt.replace('{' + im.local_name + '}', str(val))
                except: pass
        prompt = self._replace_prompt_vars(prompt)

        if prompt: print(f"[runtime]📝 {prompt}")

        try:
            user_input = input("  ✏️  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("  ⏭️ 跳过")
            user_input = ""

        if user_input and ad.outs:
            for od in ad.outs:
                var_name = getattr(od, 'global_name', None) or getattr(od, 'var_name', '')
                if var_name:
                    apply_assign(self.vm, var_name, ('set', user_input))
                    print(f"[runtime]📤 out: {var_name} = {user_input!r}")

        # 存储人类发言
        if user_input:
            from save_dialog import save_human_turn
            meta_owner = self.script.meta.get('owner', [])
            save_human_turn(
                session_id=self._current_session_id,
                turn_id=self._current_turn_id,
                user_input=user_input,
                actor_info=self._current_actor_info,
                meta_owner=meta_owner,
            )
            # turn 递增，step 归零
            self._current_turn_id += 1
            self._current_step_idx = 0
            self.vm.set('turn_count', self._current_turn_id)
            print(f"[runtime]🔢 turn → {self._current_turn_id}, step → 0")

        return user_input
    """
    _human_input_lock = None


    def _update_speaker(self, new_speaker: str):
        """
        更新发言者状态，返回 (turn_id, idx)
        - new_speaker: 'human', 'node', 或 'ai'
        - 返回 tuple: (turn_id, idx) 其中 idx 是 oratio_idx 或 step_idx
        """
        last = self.speaker["current"]
        self.speaker["last"] = last
        self.speaker["current"] = new_speaker

        if last == 'ai' and new_speaker in ('human', 'node'):
            # AI → 人类/节点：turn++
            self._current_turn_id += 1
            self._oratio_idx = 0
            self._step_idx = 0
            # 更新 vm 中的 turn_count
            self.vm.set('turn_count', self._current_turn_id)
        elif new_speaker == 'ai':
            if last in ('human', 'node', None):
                self._step_idx = 0
            else:
                self._step_idx += 1
            # turn 不变
        else:  # new_speaker 是 'human' 或 'node'
            if last in ('human', 'node'):
                self._oratio_idx += 1
            else:  # last is None or 'ai'
                self._oratio_idx = 0
            # turn 不变

        if new_speaker == 'ai':
            return self._current_turn_id, self._step_idx
        else:
            return self._current_turn_id, self._oratio_idx


    def _exec_human(self, ad, eparam: str) -> Any:
        # 人类动作现在支持在并发分支(parfor/fork)中执行
        # 在服务器模式下，通过 _human_input_event 机制实现线程安全的输入等待
        # 在 CLI 模式下，并发分支中的人类输入会排队执行（使用锁保护 stdin）

        print(f"[runtime]👤 Human Action")
        # ── 发送 node_start 事件 ──
        self._emit_event('node_start', {
            'node_name': self._get_current_node_id(),
            'node_type': 'human',
        })

        try:
            prompt = ad.prompt or ""
            if ad.in_mappings:
                for im in ad.in_mappings:
                    try:
                        val = self.eval_expr(im.global_expr)
                        prompt = prompt.replace('{' + im.local_name + '}', str(val))
                    except: pass
            prompt = self._replace_prompt_vars(prompt)

            # ── 收集 context 和 memory（与 AI 节点完全相同的逻辑）──
            from femCompiler.block_collector import collect_blocks
            actor_info = self._get_actor_info(ad, eparam)
            self._current_actor_info = actor_info   # 让 _resolve_special_param 能取到正确值
            blocks = collect_blocks(
                action=ad,
                meta=self.script.meta,
                actors_def=self.script.actors,
                var_manager=self.vm,
                code_modules=self.bridge.modules,
                memory_defs=None,          # 人类节点不需要记忆
                context_defs=self.script.contexts,
                session_id=self._current_session_id,
                turn_id=self._current_turn_id,
                actor_info=actor_info,
                runner=self,
                base_dir=self.base_dir,
            )
            context_text = blocks.get('context', '')
            memory_text = blocks.get('memory', '')
            print(f"[human context] 获取到上下文，长度: {len(context_text)} 字符")
            if context_text:
                print(f"[human context] 内容预览:\n{context_text[:500]}")

            # ── 发送 human_wait 事件（带上上下文和记忆）──
            scope_info = []
            if hasattr(ad, 'scope') and ad.scope:
                scope_info = ad.scope
            #print(f"[DEBUG _exec_human] context_text={context_text!r}, memory_text={memory_text!r}, prompt={prompt!r}")
            self._emit_event('human_wait', {
                'node_name': self._get_current_node_id(),
                'prompt': prompt,
                'scope': scope_info,
                'context': context_text,
                'memory': memory_text,
            })

            if prompt:
                print(f"[runtime]📝 {prompt}")

                # ---- 将 human prompt 存入 dialog（修复 prompt 丢失） ----
                from .save_dialog import save_human_turn
                from .FEM_scope_resolver import resolve_scope
                meta_owner = self.script.meta.get('owner', [])
                raw_scope = ([], [])
                if hasattr(ad, 'scope') and ad.scope:
                    raw_scope = resolve_scope(ad.scope, self.script.actors, self.vm)

                actor_info = self._get_actor_info(ad, eparam)
                if 'user' not in actor_info:
                    owners = self.script.meta.get('owner', [])
                    if owners:
                        actor_info['user'] = str(owners[0])

                turn_id, oratio_idx = self._update_speaker('human')
                event = save_human_turn(
                    session_id=self._current_session_id,
                    turn_id=turn_id,
                    oratio_idx=oratio_idx,
                    user_input=prompt,
                    actor_info=actor_info,
                    meta_owner=meta_owner,
                    action_scope=raw_scope,
                    is_node_prompt=False,
                )
                if event:
                    event.wait()
                print(f"[runtime]💬 Human prompt 已存入 dialog: turn={turn_id}, oratio={oratio_idx}")

            # ── 获取人类输入：FastAPI 模式 or CLI 模式 ──
            if self._human_input_event is not None:
                # FastAPI 模式：阻塞等待前端提交输入
                print("[runtime]⏳ 等待前端人类输入...")
                self._human_input_event.clear()
                self._human_input_event.wait(timeout=3600)
                user_input = self._human_input_data or ''
                self._human_input_data = None
            else:
                # CLI 模式：从 stdin 读取，支持特殊命令
                print("（输入内容，按回车换行，输入空行或 /end 结束）")
                print("（命令：/godview 上帝视角 | /@角色名 切换视角）")
                lines = []
                while True:
                    try:
                        sys.stdout.flush()
                        line = sys.stdin.readline()
                        if not line:
                            break
                        line = line.rstrip('\n')
                        if line == '' or line.strip().lower() == '/end':
                            break
                        # ── 特殊命令处理 ──
                        if line.startswith('/'):
                            cmd = line[1:].strip()
                            if cmd == 'godview':
                                meta_owner = self.script.meta.get('owner', [])
                                _actor_info = {'user': str(meta_owner[0])} if meta_owner else {}
                                _blocks = collect_blocks(
                                    action=ad,
                                    meta=self.script.meta,
                                    actors_def=self.script.actors,
                                    var_manager=self.vm,
                                    code_modules=self.bridge.modules,
                                    memory_defs=None,
                                    context_defs=self.script.contexts,
                                    session_id=self._current_session_id,
                                    turn_id=self._current_turn_id,
                                    actor_info=_actor_info,
                                    runner=self,
                                    base_dir=self.base_dir,
                                )
                                if self._cli_renderer:
                                    self._cli_renderer.clear_and_show_context(
                                        "上帝视角（owner）",
                                        _blocks.get('context', '（暂无对话记录）')
                                    )
                            elif cmd.startswith('@'):
                                _actor_info = self._get_actor_info(ad, cmd)
                                self._current_actor_info = _actor_info
                                _blocks = collect_blocks(
                                    action=ad,
                                    meta=self.script.meta,
                                    actors_def=self.script.actors,
                                    var_manager=self.vm,
                                    code_modules=self.bridge.modules,
                                    memory_defs=None,
                                    context_defs=self.script.contexts,
                                    session_id=self._current_session_id,
                                    turn_id=self._current_turn_id,
                                    actor_info=_actor_info,
                                    runner=self,
                                    base_dir=self.base_dir,
                                )
                                name = cmd.lstrip('@')
                                if self._cli_renderer:
                                    self._cli_renderer.clear_and_show_context(
                                        f"{name} 的视角",
                                        _blocks.get('context', '（暂无对话记录）')
                                    )
                            else:
                                print(f"⚠️ 未知命令: /{cmd}")
                            continue
                        # ── 普通输入 ──
                        lines.append(line)
                    except (EOFError, KeyboardInterrupt):
                        break
                    except Exception as e:
                        print(f"[runtime]\n⚠️ 读取输入时出错: {e}，跳过本次输入")
                        break
                user_input = '\n'.join(lines)

            if user_input and ad.outs:
                for od in ad.outs:
                    var_name = getattr(od, 'global_name', None) or getattr(od, 'var_name', '')
                    if var_name:
                        apply_assign(self.vm, var_name, ('set', user_input))
                        print(f"[runtime]📤 out: {var_name} = {user_input!r}")

            if user_input:
                from .save_dialog import save_human_turn
                from .FEM_scope_resolver import resolve_scope
                meta_owner = self.script.meta.get('owner', [])
                raw_scope = ([], [])
                if hasattr(ad, 'scope') and ad.scope:
                    raw_scope = resolve_scope(ad.scope, self.script.actors, self.vm)

                turn_id, oratio_idx = self._update_speaker('human')
                event = save_human_turn(
                    session_id=self._current_session_id,
                    turn_id=turn_id,
                    oratio_idx=oratio_idx,
                    user_input=user_input,
                    actor_info=self._get_actor_info(ad, eparam),
                    meta_owner=meta_owner,
                    action_scope=raw_scope,
                    is_node_prompt=False,
                )
                if event:
                    #print("[DEBUG _exec_human] 等待数据库写入完成...")
                    event.wait()
                    #print("[DEBUG _exec_human] 数据库写入完成，继续执行")
                print(f"[runtime]🔢 turn → {turn_id}, oratio → {oratio_idx}")


                # ── 发送 human_done 事件 ──
                self._emit_event('human_done', {
                    'node_name': self._get_current_node_id(),
                    'input': user_input,
                })

            return user_input

        except Exception as e:
            print(f"[runtime]\n❌ 人类动作执行异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
    # ══════════════════════════════════════════════════
    #  Out 写回
    # ══════════════════════════════════════════════════

    def _apply_outs(self, ad, result: Any, local_vars: dict = None):
        if not ad.outs: return
        #print(f"[runtime]_apply_outs: result={result!r}, outs={[(o.var_name, getattr(o, 'dynamic_key', None)) for o in ad.outs]}")
        outs = ad.outs
        if isinstance(result, tuple):
            if len(result) != len(outs):
                raise FEMVariableError(
                    f"@func 返回值不匹配：out 声明了 {len(outs)} 个变量，但函数返回了 {len(result)} 个值。"
                )
            for i, od in enumerate(outs):
                self._set_out_var(od, result[i])
        elif isinstance(result, dict):
            # 检查 out 声明的变量和返回 dict 的 key 是否一一对应
            out_names = [self._extract_var_name(od.var_name) for od in outs]
            result_keys = list(result.keys())
            missing_in_result = [n for n in out_names if n not in result_keys]
            extra_in_result = [k for k in result_keys if k not in out_names]
            if missing_in_result:
                raise FEMVariableError(
                    f"@func 返回值不匹配：out 声明的变量 {missing_in_result} 在函数返回字典中不存在。"
                )
            if extra_in_result:
                raise FEMVariableError(
                    f"@func 返回值不匹配：函数返回字典中的 key {extra_in_result} 未在 out 中声明。"
                )
            for od in outs:
                var_name = self._extract_var_name(od.var_name)
                self._set_out_var(od, result[var_name])
        else:
            if len(outs) == 1:
                self._set_out_var(outs[0], result)
            else:
                raise FEMVariableError(
                    f"@func 返回值不匹配：out 声明了 {len(outs)} 个变量，但函数返回了单值。"
                )
            
            


    def _set_out_var(self, od, value: Any):
        expr = od.var_name
        dynamic_key = getattr(od, 'dynamic_key', None)
        if dynamic_key:
            # 明确指定了动态键：如 vote_results 配上 dynamic_key='@voter'
            # 构造字典写入路径
            container = expr
            resolved_key = self.eval_expr(dynamic_key)  # 求值 @voter → '@Cat' 等
            if not isinstance(resolved_key, str):
                raise FEMVariableError(f"动态键 {dynamic_key} 求值后不是字符串: {resolved_key!r}")
            path = f"{container}[{resolved_key}]"
            self.vm.set(path, value)
            print(f"[runtime]📤 out (dict): {path} = {value!r}")
            return

        # 没有 dynamic_key，检查 expr 本身是否包含 .@
        if '.@' in expr:
            container, dyn_key = self._resolve_actor_path(expr)
            if not dyn_key:
                raise FEMVariableError(f"无法解析动态键路径: {expr!r}")
            path = f"{container}[{dyn_key}]"
            self.vm.set(path, value)
            print(f"[runtime]📤 out (dict): {path} = {value!r}")
            return

        # 普通变量赋值：expr 应仅为变量名（可含索引），不包含运算符
        if re.match(r'^[A-Za-z_]\w*$', expr):
            self.vm.set(expr, value)
            print(f"[runtime]📤 out: {expr} = {value!r}")
            return
        # 支持简单索引如 var[key]
        if re.match(r'^[A-Za-z_]\w*\[.+\]$', expr):
            self.vm.set(expr, value)
            print(f"[runtime]📤 out: {expr} = {value!r}")
            return

        raise FEMVariableError(
            f"_set_out_var 无法处理表达式: {expr!r}。"
            f"请使用 'var_name' 或 'dict_name.@actor' 格式。"
        )



    def _extract_var_name(self, expr: str) -> str:
        m = re.match(r'^([\w]+)', expr)
        return m.group(1) if m else expr


    def _get_current_node_id(self) -> str:
        """获取当前线程所在的流图节点 ID，线程安全"""
        ctx = _current_context.get()
        return ctx.current_node_id if ctx else ""
        
    # ══════════════════════════════════════════════════
    #  主流程执行
    # ══════════════════════════════════════════════════

    def run(self, max_steps: int = None):
        """执行主流程"""
        if max_steps is None:
            global_meta = getattr(self.script, 'meta', None) or {}
            max_steps = global_meta.get('max_steps', 0)

        flow = self.script.flow
        if not flow:
            print("⚠️ 没有 flow 定义")
            return

        self._emit_event('flow_start', {'entry': flow.entry, 'max_steps': self.global_max_steps})

        self.global_max_steps = max_steps
        self.global_step = 0
        
        print("\n🚀 开始执行 Flow")
        print(f"[runtime] Entry: {flow.entry}")
        print(f"[DEBUG] flow.nodes count={len(flow.nodes)}, flow.edges count={len(flow.edges)}")
        print("[DEBUG] 进入 _execute_flow")
        self._execute_flow(flow)
        print("[DEBUG] 退出 _execute_flow")
        
        self._emit_event('flow_done', {})
        # 等待所有数据库写入完成
        from femCompiler.save_dialog import save_queue
        save_queue.wait_empty(timeout=10)
        #print(f"[runtime]📊 最终变量状态:")
        #print(self.vm)

        # ── 发送 flow_done 事件 ──
        self._emit_event('flow_done', {})

    # ══════════════════════════════════════════════════
    #  条件求值
    # ══════════════════════════════════════════════════
    
    def _translate_actor_attr(self, expr: str) -> str:
        """将 @actor.attr 翻译为 attr['@actor']，支持动态 actor 变量解析"""
        # 注意：现在 actor_name 会直接捕获 @ 符号，例如 @alice
        pattern = r'(@\w+)\.(\w+)(\.\w+)?'
        
        def replacer(m):
            actor_name = m.group(1)   # 例如 "@alice"
            attr_name = m.group(2)
            
            # ── 动态 actor 解析（最多追 10 层） ──
            depth = 0
            while depth < 10:
                if actor_name in self.script.actors:
                    break
                # 从 vars 中查找（actor_name 自带 @）
                val = self.vm.get(actor_name)
                if isinstance(val, str) and val.startswith('@') and len(val) > 1:
                    if val == actor_name:        # 自指，停止
                        break
                    actor_name = val
                    depth += 1
                else:
                    break
            
            # 检查最终解析结果
            if actor_name not in self.script.actors:
                print(f"[runtime]⚠️ 表达式中的 actor '{actor_name}' 未声明，保留原样")
                return m.group(0)
            
            # 保留字检查
            reserved = {'type', 'soul', 'source', 'tools', 'name'}
            if attr_name in reserved:
                return m.group(0)
            
            # 多级属性警告
            if m.group(3):
                suffix = m.group(3)
                print(f"[runtime]⚠️ 不支持多级实体属性访问，忽略后缀 '{suffix}'，只翻译第一级 {actor_name}.{attr_name}")
            
            # 翻译为字典索引：hp['@alice']
            return f"{attr_name}['{actor_name}']"
        
        return re.sub(pattern, replacer, expr)
        
        
    def _resolve_special_param(self, param_name: str) -> Any:
        """
        解析预留字段参数。
        prompt → 当前 action 的 prompt 文本
        @actor → actor_info 字典
        session/session_id → session ID
        turn/turn_id → turn ID
        """
        if param_name in ('prompt',):
            return self._current_prompt or ""
        if param_name in ('@actor',):
            return self._current_actor_info or {}
        if param_name in ('session', 'session_id'):
            return self._current_session_id or 0
        if param_name in ('turn', 'turn_id'):
            return self._current_turn_id or 0
        return None
        
        
    def _get_actor_info(self, action, executor_param: str) -> dict:
        """解析当前 action 的 actor 信息"""
        info = {}
        actor_name = executor_param
        #print(f"[DEBUG _get_actor_info] eparam={executor_param!r}, action.as_actor={getattr(action, 'as_actor', None)!r}")
        # ── 完整打印整个 actors 字典 ──
        #print(f"[runtime]=== full actors dict START ===")
        #for k, v in self.script.actors.items():
            #print(f"[runtime][RunTime - DEBUG]{k}: {v}")
            #print(f"[runtime][RunTime - DEBUG]__dict__: {v.__dict__}")
        #print(f"[runtime]=== full actors dict END ===")
        #print(f"[runtime]looking for actor_name: {repr(actor_name)}")
        
        # 如果是动态变量（如 @speaker），先解析为实际值
        if actor_name in self.vm.globals:
            actor_name = self.vm.globals[actor_name]
        # 如果解析后的值仍是 @xxx 变量引用，继续追
        if isinstance(actor_name, str) and actor_name.startswith('@'):
            if actor_name in self.vm.globals:
                actor_name = self.vm.globals[actor_name]
                
        # 如果 executor_param 是动态变量，检查是否与当前循环变量一致
        if executor_param.startswith('@') and executor_param not in self.script.actors:
            ctx = _current_context.get()
            if ctx and ctx.current_loop_var is not None:
                if executor_param != ctx.current_loop_var:
                    raise ValueError(
                        f"变量名不一致：for 循环使用 {ctx.current_loop_var}，"
                        f"但 action 定义使用 {executor_param}。请统一变量名。"
                    )
        
        if actor_name in self.script.actors:
            adef = self.script.actors[actor_name]
            adef_type = getattr(adef, 'type', None)
            atype = adef_type.value if adef_type else ''
            #print(f"[DEBUG _get_actor_info] 匹配到 actor: {actor_name}, type={atype}, soul={getattr(adef, 'soul', None)!r}, source={getattr(adef, 'source', None)!r}")
            #print(f"[runtime]found adef: {adef}")
            #print(f"[runtime]adef.__dict__: {adef.__dict__}")

            #print(f"[runtime]atype: {repr(atype)}")
            if atype == 'ai':
                soul_id = getattr(adef, 'soul', None)
                if soul_id is not None:
                    info['soul'] = str(soul_id)
            elif atype == 'human':
                source = getattr(adef, 'source', None)
                if source is not None:
                    info['user'] = str(source)
                soul_id = getattr(adef, 'soul', None)
                if soul_id is not None:
                    info['soul'] = str(soul_id)
                # 若 source 缺失，从 meta.owner 回退
                if 'user' not in info:
                    owners = self.script.meta.get('owner', [])
                    if owners:
                        info['user'] = str(owners[0])
        else:
            print(f"[runtime]actor_name NOT FOUND in actors!")
        # 处理 human as(@soul)
        if hasattr(action, 'as_actor') and action.as_actor:
            as_name = action.as_actor
            if as_name in self.script.actors:
                soul_id = getattr(self.script.actors[as_name], 'soul', None)
                if soul_id is not None:
                    info['soul'] = str(soul_id)
        # 收集动态属性：遍历 vars 中所有字典，提取以 actor_name 为键的条目
        for var_name, var_value in self.vm.globals.items():
            if isinstance(var_value, dict) and actor_name in var_value:
                if var_name not in info:
                    info[var_name] = var_value[actor_name]
        return info

    def _eval_condition(self, cond: str) -> bool:
        """评估条件表达式，支持 @actor.attr 和 @actor.type"""
        # 1. 先将 @actor.attr 全部求值为具体值
        cond_resolved = cond.strip()
        # 匹配 @xxx.xxx 形式并求值
        def replace_actor_attr(m):
            full = m.group(0)
            actor_name = m.group(1)   # 含 @
            attr = m.group(2)
            # 先解析 actor 实际是谁
            actor_val = self.eval_expr(actor_name)
            if isinstance(actor_val, str) and actor_val.startswith('@'):
                # 得到了实际 actor 名
                if attr == 'type':
                    actor_type = self._get_actor_type(actor_val)
                    if actor_type:
                        return repr(actor_type)  # 返回 'ai' 或 'human'
                else:
                    # 尝试从字典中取值
                    try:
                        # 通过字典视角：attr[actor_val]
                        container = self.vm.get(attr)
                        if isinstance(container, dict) and actor_val in container:
                            return repr(container[actor_val])
                    except:
                        pass
            return full  # 替换失败保留原样

        cond_resolved = re.sub(r'(@\w+)\.(\w+)', replace_actor_attr, cond_resolved)
        # 2. 尝试用安全求值器 eval_condition
        try:
            from FEM_parser import eval_condition
            return eval_condition(cond_resolved, self.vm.globals)
        except (ImportError, Exception):
            pass

        # 3. 回退：手动求值（兼容 or/and/not/比较）
        if ' or ' in cond_resolved:
            parts = cond_resolved.split(' or ', 1)
            return self._eval_condition(parts[0]) or self._eval_condition(parts[1])
        if ' and ' in cond_resolved:
            parts = cond_resolved.split(' and ', 1)
            return self._eval_condition(parts[0]) and self._eval_condition(parts[1])
        if cond_resolved.startswith('not '):
            return not self._eval_condition(cond_resolved[4:].strip())
        for op in ('!=', '！=', '==', '>=', '<=', '>', '<'):
            if op in cond_resolved:
                left, right = cond_resolved.split(op, 1)
                lv = self.eval_expr(left.strip())
                rv = self.eval_expr(right.strip())
                if isinstance(lv, str) and isinstance(rv, str):
                    pass
                elif isinstance(lv, (int, float)) and isinstance(rv, str):
                    try: rv = type(lv)(rv)
                    except: pass
                elif isinstance(rv, (int, float)) and isinstance(lv, str):
                    try: lv = type(rv)(lv)
                    except: pass
                if op == '==': return lv == rv
                if op == '!=': return lv != rv
                if op == '！=': return lv != rv
                if op == '>=': return lv >= rv
                if op == '<=': return lv <= rv
                if op == '>': return lv > rv
                if op == '<': return lv < rv
        # 最后的兜底
        val = self.eval_expr(cond_resolved)
        # 如果前面所有解析都失败，抛出明确的错误
        raise FEMVariableError(
            f"无法解析条件表达式: '{cond}' (解析后: '{cond_resolved}')。"
            f"请检查表达式语法是否正确。"
        )

# ============================================================
#  便捷入口
# ============================================================
def run_script(script, base_dir: str = ".", max_steps: int = 100, event_callback=None):
    """快捷函数：解析后直接运行"""
    runner = FEMRunner(script, base_dir=base_dir, verbose=True, event_callback=event_callback)
    try:
        runner.run(max_steps=max_steps)
    except FEMVariableError as e:
        print(f"[runtime]\n❌ 变量错误: {e}")
        if event_callback:
            event_callback('flow_error', {'error': str(e)})
        sys.exit(1)
    except Exception as e:
        print(f"[runtime]\n❌ 运行错误: {e}")
        if event_callback:
            event_callback('flow_error', {'error': str(e)})
        raise
    return runner
