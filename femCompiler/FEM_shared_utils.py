
import re
import contextvars
from typing import Any, Tuple, List, Optional, Dict

# ============================================================
# 0. 作用域管理：contextvars 解决并发问题
# ============================================================

_current_context = contextvars.ContextVar('exec_ctx', default=None)

class ExecutionContext:
    """进入模块时创建，退出时销毁。每个线程/协程自动隔离。"""
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.locals = {}

    def __enter__(self):
        self._token = _current_context.set(self)
        return self

    def __exit__(self, *args):
        _current_context.reset(self._token)


class VarManager:
    def __init__(self):
        self.globals = {}

    def get(self, name: str) -> Any:
        """读变量：先查当前模块 local，再查全局"""
        ctx = _current_context.get()
        if ctx and name in ctx.locals:
            return ctx.locals[name]
        if name in self.globals:
            return self.globals[name]
        raise KeyError(f"变量 '{name}' 不存在 (当前模块: {ctx.module_name if ctx else 'None'})")

    def set(self, name: str, value: Any, local: bool = False):
        """写变量"""
        ctx = _current_context.get()
        if local and ctx:
            ctx.locals[name] = value
        elif ctx and name in ctx.locals:
            ctx.locals[name] = value
        else:
            self.globals[name] = value

    def has(self, name: str) -> bool:
        ctx = _current_context.get()
        if ctx and name in ctx.locals:
            return True
        return name in self.globals

    def resolve_var(self, name: str) -> Tuple[dict, str]:
        """
        核心函数：找到此时此地的变量，返回 (container, key)
        调用方可以 container[key] 读，也可以 container[key] = val 写
        """
        ctx = _current_context.get()
        if ctx and name in ctx.locals:
            return ctx.locals, name
        return self.globals, name


# ============================================================
# 1. extract_ai_assignments(text)
# ============================================================

def extract_ai_assignments(text: str) -> List[Tuple[str, str]]:
    """
    从 AI 输出中提取 <<VAR: expr>> 格式的主动赋值语句。
    返回 [(var_name, expr), ...]
    
    例如：
      "我觉得3号可疑。<<VOTE_TARGET: 3>>"
      → [('VOTE_TARGET', '3')]
      
      "加血！<<player[blood]: ++10>>"
      → [('player[blood]', '++10')]
    """
    pattern = r'<<([^:>]+):\s*(.+?)>>'
    matches = re.findall(pattern, text)
    return [(m[0].strip(), m[1].strip()) for m in matches]


# ============================================================
# 2. parse_assign_syntax(expr, var_name)
# ============================================================

def parse_assign_syntax(expr: str, var_name: str = ''):
    """
    解析赋值意图，返回统一格式：
      ('set', value)       - 直接赋值
      ('increment', n)     - 加减数值
      ('add', item)        - 数组追加
      ('remove', item)     - 数组移除
    
    支持：
      <<VAR: value>>        → ('set', 'value')
      <<VAR: ++N>>          → ('increment', N)
      <<VAR: --N>>          → ('increment', -N)
      <<VAR: add(x)>>       → ('add', 'x')
      <<VAR: remove(x)>>    → ('remove', 'x')
    """
    expr = expr.strip()
    
    # ++N  / --N
    m = re.match(r'^\+\+\s*(.+)$', expr)
    if m:
        try:
            return ('increment', float(m.group(1)))
        except ValueError:
            return ('increment', m.group(1))
    
    m = re.match(r'^--\s*(.+)$', expr)
    if m:
        try:
            return ('increment', -float(m.group(1)))
        except ValueError:
