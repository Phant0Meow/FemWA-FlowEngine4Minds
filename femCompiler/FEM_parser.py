"""
FEM Parser v5.0 — 两阶段解析器
阶段1: 缩进块切割 (Block Builder)
阶段2: 语义分发 (Block Evaluator) + Flow 子解析
所有解析结果数据类及条件求值工具均在此文件。

代码原则：所有代码不许写try静默兜底不报错，有错必须报错。
"""

import re
import ast
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from femCompiler.FEM_config import get_db_path
from femBridges.getDir.get_dir import get_user_dir

# ============================================================
# 1. 基础枚举与数据类（保持不变，从旧文件迁移）
# ============================================================

# ── 全局保留字段：用于解析时判断多行块结束 ──
_TOP_KEYWORDS = (
    'meta:', 'vars:', 'code:', 'actors:',
    'action ', 'module ', 'flow:', 'mainflow:',
    'memory ', 'context ',
)
_FIELD_KEYWORDS = (
    'prompt:', 'showprompt:', 'memory:', 'context:', 'scope:',
    'out:', 'in:', 'fallback:', 'resolve:',
    'interrupt:', 'timeout:', 'max_tries:',
)


class ExecutorType(Enum):
    AI = "ai"
    HUMAN = "human"
    FUNC = "func"
    ASSIGN = "assign"

class ActorType(Enum):
    AI = "ai"
    HUMAN = "human"
    BLUEPRINT = "blueprint"

class OutType(Enum):
    STRING = "string"
    TEXT = "text"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    ARRAY = "array"
    OBJECT = "object"
    DROPDOWN = "dropdown"
    ENUM = "enum"
    ACTOR = "actor"
    ASSIGN = "assign"

@dataclass(frozen=True)
class ActorRef:
    name: str
    attribute: Optional[str] = None
    def __repr__(self):
        return f"@{self.name}" + (f".{self.attribute}" if self.attribute else "")

@dataclass(frozen=True)
class VarRef:
    name: str
    def __repr__(self): return f"{{{self.name}}}"

@dataclass(frozen=True)
class DynamicActorRef:
    var_name: str
    def __repr__(self): return f"@{{{self.var_name}}}"

@dataclass
class ActorDef:
    type: ActorType
    ref: str
    name: str
    soul: Optional[str] = None
    source: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    is_blueprint: bool = False

@dataclass
class InMapping:
    local_name: str
    global_expr: str

@dataclass
class OutDef:
    var_name: str
    dynamic_key: Optional[str] = None
    out_type: OutType = OutType.STRING
    label: str = ""
    choices: Optional[str] = None

@dataclass
class ActionDef:
    name: str
    executor_type: ExecutorType
    executor_param: str
    as_actor: Optional[str] = None
    prompt: Optional[str] = None
    showprompt: Optional[str] = None
    scope: str = ""          # 现在存原始字符串，如 "[@God, @Diana] + my_list"
    in_mappings: List[InMapping] = field(default_factory=list)
    outs: List[OutDef] = field(default_factory=list)
    resolve: Optional[str] = None
    max_retries: int = 0
    fallback: Optional[str] = None
    memory: Optional[str] = None
    context: Optional[str] = None
    interrupt: Optional[Any] = None
    resolve_args: List[str] = field(default_factory=list)

@dataclass
class MethodDef:
    name: str
    module_alias: str
    func_name: str
    in_params: List[str] = field(default_factory=list)
    out_defs: List[OutDef] = field(default_factory=list)

@dataclass
class FlowNode:
    id: str
    type: str = "action"
    label: str = ""
    action_name: Optional[str] = None
    module_ref: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    extra_actions: List[str] = field(default_factory=list)
    def __post_init__(self):
        if not self.label:
            self.label = self.id

@dataclass
class FlowEdge:
    source: str
    target: str
    condition: str = ""

@dataclass
class FlowGraph:
    nodes: Dict[str, FlowNode] = field(default_factory=dict)
    edges: List[FlowEdge] = field(default_factory=list)

    @property
    def entry(self) -> str:
        # 优先使用 [START] 或 [IN] 节点
        for special in ('[START]', '[IN]'):
            if special in self.nodes:
                return special
        targets = {e.target for e in self.edges}
        for nid in self.nodes:
            if nid not in targets:
                return nid
        return ""

    def add_node(self, node: FlowNode):
        if node.id not in self.nodes:
            self.nodes[node.id] = node

    def add_edge(self, src, tgt, condition=""):
        if src and tgt and src != tgt:
            self.edges.append(FlowEdge(source=src, target=tgt, condition=condition))

@dataclass
class ModuleDef:
    name: str
    params: List[str] = field(default_factory=list)
    locals: Dict[str, Any] = field(default_factory=dict)
    actions: Dict[str, ActionDef] = field(default_factory=dict)
    modules: Dict[str, 'ModuleDef'] = field(default_factory=dict)   # 嵌套子模块
    memories: Dict[str, MethodDef] = field(default_factory=dict)
    contexts: Dict[str, MethodDef] = field(default_factory=dict)
    flow: Optional[FlowGraph] = None
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Script:
    meta: Dict[str, Any] = field(default_factory=dict)
    vars: Dict[str, Any] = field(default_factory=dict)
    code: Dict[str, str] = field(default_factory=dict)
    actors: Dict[str, ActorDef] = field(default_factory=dict)
    actions: Dict[str, ActionDef] = field(default_factory=dict)
    modules: Dict[str, ModuleDef] = field(default_factory=dict)
    memories: Dict[str, MethodDef] = field(default_factory=dict)
    contexts: Dict[str, MethodDef] = field(default_factory=dict)
    flow: Optional[FlowGraph] = None

# ============================================================
# 2. 块切割器 (Block Builder)
# ============================================================

@dataclass
class Block:
    type: str                  # 'meta', 'vars', 'action', 'module', 'flow', ...
    header: str                # 原始头行
    indent: int
    daughters: List['Block'] = field(default_factory=list)
    content_lines: List[str] = field(default_factory=list)  # 自身内容行（不含子块）

def _strip_comment(line: str) -> str:
    in_str, qc = False, None
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            if c == qc:
                in_str = False
        else:
            if c in ('"', "'"):
                in_str, qc = True, c
            elif c == '#':
                return line[:i].rstrip()
            elif line[i:i+2] == '//':
                return line[:i].rstrip()
        i += 1
    return line
    
def normalize_symbols(line: str) -> str:
    """只对 FEM 语法行替换中文符号，不影响文本内容"""
    line = line.replace('：', ':').replace('，', ',')
    line = line.replace('“', '"').replace('”', '"')
    line = line.replace('（', '(').replace('）', ')')
    line = line.replace('【', '[').replace('】', ']')
    line = line.replace('｜', '|')
    line = line.replace('--', '->')  # flow 链符号
    return line

def _is_blank_or_comment(line: str) -> bool:
    s = line.strip()
    return s == '' or s.startswith('#') or s.startswith('//')

def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())

def _detect_type(line: str) -> str:
    s = line.strip()
    s = s.replace('：', ':')  # 中文冒号等价
    if s.startswith('meta:'):      return 'meta'
    if s.startswith('vars:'):      return 'vars'
    if s.startswith('code:'):      return 'code'
    if s.startswith('actors:'):    return 'actors'
    if re.match(r'^module\s+\w+', s): return 'module'
    if re.match(r'^action\s+', s):    return 'action'
    if re.match(r'^memory\s+', s):    return 'memory'
    if re.match(r'^context\s+', s):   return 'context'
    if s.startswith('flow:') or s.startswith('mainflow:'): return 'flow'
    return 'unknown'

def build_blocks(text: str, base_indent: int = 0) -> List[Block]:
    """将脚本文本按缩进切分为块树，支持模块递归"""
    lines = []
    for raw in text.split('\n'):
        stripped = raw.rstrip()
        if _is_blank_or_comment(stripped):
            continue
        indent = len(raw) - len(raw.lstrip())
        content = _strip_comment(raw).strip()
        lines.append((indent, content))

    blocks: List[Block] = []
    i = 0
    while i < len(lines):
        indent, content = lines[i]
        if indent < base_indent:
            break
        btype = _detect_type(content)
        header = content
        block = Block(type=btype, header=header, indent=indent)

        if btype == 'module':
            inner_lines = []
            j = i + 1
            while j < len(lines) and lines[j][0] > indent:
                inner_lines.append(lines[j])
                j += 1
            if inner_lines:
                # 相对缩进：子行缩进 - 当前行缩进 - 1（保证至少1个空格）
                inner_text = '\n'.join(
                    ' ' * max(0, il[0] - indent - 1) + il[1]
                    for il in inner_lines
                )
                block.daughters = build_blocks(inner_text, base_indent=0)
            blocks.append(block)
            i = j
        else:
            j = i + 1
            while j < len(lines) and lines[j][0] > indent:
                # 保留原始缩进（空格 + 内容），多行文本依赖此缩进判断
                original_line = ' ' * lines[j][0] + lines[j][1]
                block.content_lines.append(original_line)
                j += 1
            blocks.append(block)
            i = j

    return blocks

# ============================================================
# 3. 语义分发器 (Block Evaluator) — 辅助函数
# ============================================================

def _parse_value(s: str) -> Any:
    s = s.strip()
    if s.startswith('[') and s.endswith(']'):
        inner = s[1:-1].strip()
        if not inner:
            return []
        items = _split_br(inner)
        return [_parse_value(it.strip()) for it in items]
    if s.startswith('{') and s.endswith('}'):
        inner = s[1:-1].strip()
        if not inner:
            return {}            # 空字典
        # 非空字典：逐个键值对解析
        d = {}
        for pair in _split_br(inner):
            if ':' in pair:
                k, v = pair.split(':', 1)
                key = _parse_dict_key(k.strip())
                d[key] = _parse_value(v.strip())
        return d
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s == 'true':
        return True
    if s == 'false':
        return False
    if s.startswith('@{') and s.endswith('}'):
        return s  # 动态引用原样保留
    if s.startswith('@'):
        return s  # ActorRef 字符串表示
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        return s

def _parse_dict_key(k: str) -> Any:
    if (k.startswith('"') and k.endswith('"')) or (k.startswith("'") and k.endswith("'")):
        k = k[1:-1]
    if k.startswith('@'):
        return ActorRef(k[1:].split('.')[0], k[1:].split('.')[1] if '.' in k[1:] else None)
    return k

def _split_br(s: str) -> List[str]:
    items, depth, cur = [], 0, []
    in_str, qc = False, None
    for c in s:
        if in_str:
            cur.append(c)
            if c == qc:
                in_str = False
        else:
            if c in ('"', "'"):
                in_str, qc = True, c
                cur.append(c)
            elif c in ('[', '{', '('):
                depth += 1
                cur.append(c)
            elif c in (']', '}', ')'):
                depth -= 1
                cur.append(c)
            elif c == ',' and depth == 0:
                items.append(''.join(cur))
                cur = []
            else:
                cur.append(c)
    if cur:
        items.append(''.join(cur))
    return items

def _eval_kv_block(lines: List[str]) -> Dict[str, Any]:
    d = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # 归一化当前行（可能影响等号、引号等），但保留原始行用于多行文本
        norm_line = normalize_symbols(line)
        if '=' in norm_line:
            k, v = norm_line.split('=', 1)
            k, v = k.strip(), v.strip()
            
            # ---- 特殊处理 owner 字段：始终保留为字符串列表 ----
            if k == 'owner':
                raw_v = v.strip()
                # 去掉外层方括号（如果有），否则保留原值
                if raw_v.startswith('[') and raw_v.endswith(']'):
                    inner = raw_v[1:-1].strip()
                else:
                    inner = raw_v
                if not inner:
                    d[k] = []
                else:
                    # 支持中文逗号、顿号，全部替换为英文逗号
                    inner = inner.replace('，', ',').replace('、', ',')
                    items = _split_br(inner)
                    d[k] = [it.strip().strip('"').strip("'") for it in items]
                i += 1
                continue
            # ---- 其他键正常处理 ----
            
            if v == '|':
                i += 1
                v_lines = []
                # 多行文本内容不进行符号归一化，保留原样
                while i < len(lines) and (lines[i].startswith(' ') or lines[i].startswith('\t')):
                    v_lines.append(lines[i].strip())
                    i += 1
                v = '\n'.join(v_lines)
                d[k] = v
                continue
            d[k] = _parse_value(v.strip())
        i += 1
    return d

def _parse_tools(s: str) -> List[str]:
    s = s.strip()
    if s.startswith('[') and s.endswith(']'):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [t.strip().strip('"').strip("'") for t in inner.split(',')]
    return []


def _parse_out_multi(s: str) -> List[OutDef]:
    s = s.strip().rstrip(',').strip()
    if not s:
        return []
    items = _split_br(s)
    result = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        # 赋值形式
        m = re.match(r'^([\w\[\].]+)\s*([+\-]?=)\s*(.+)$', item)
        if m:
            var_name = m.group(1)
            op = m.group(2)
            value = m.group(3).strip()
            result.append(OutDef(var_name=f"{var_name} {op} {value}", out_type=OutType.ASSIGN, label=""))
            continue
        # 函数调用形式
        pm = re.match(r'^([\w.{}@]+)\(([^)]*)\)', item)
        if pm:
            full_name, params_str = pm.group(1), pm.group(2)
            if '.' in full_name:
                parts = full_name.split('.', 1)
                var_name, dynamic_key = parts[0], parts[1]
            else:
                var_name, dynamic_key = full_name, None
            out_type, label, choices = OutType.STRING, "", None
            params = _split_br(params_str)
            positional_idx = 0
            for p in params:
                p = p.strip()
                if p.startswith('choices='):
                    choices = p[len('choices='):].strip()
                elif p.startswith('label='):
                    label = p[len('label='):].strip().strip('"').strip("'")
                else:
                    if positional_idx == 0:
                        try:
                            out_type = OutType(p.lower())
                        except:
                            pass
                    elif positional_idx == 1:
                        label = p.strip().strip('"').strip("'")
                    positional_idx += 1
            result.append(OutDef(var_name=var_name, dynamic_key=dynamic_key,
                                 out_type=out_type, label=label, choices=choices))
            continue
        # 纯变量名
        result.append(OutDef(var_name=item, out_type=OutType.STRING, label=""))
    return result
    


def _parse_action_fields(block: Block) -> dict:
    f = {
        'prompt': None, 'showprompt': None,
        'scope': [], 'in_mappings': [], 'outs': [],
        'resolve': None, 'max_retries': 0, 'fallback': None,
        'memory': None, 'context': None, 'interrupt': None,
    }
    lines = block.content_lines
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 对语法行进行符号归一化，但保留原始行用于提取 prompt 文本
        normalized_line = normalize_symbols(line)
        if normalized_line.startswith('prompt:'):
            pv = normalized_line[len('prompt:'):].strip()
            # 支持中文竖线（｜）作为多行标志
            if pv in ('|', '｜'):
                base_indent = len(lines[i]) - len(lines[i].lstrip())
                j = i + 1
                plines = []
                while j < len(lines):
                    line_j = lines[j]
                    stripped = line_j.lstrip()
                    indent = len(line_j) - len(stripped)
                    # 同缩进 + 二级字段关键字 → 结束
                    if indent == base_indent and any(stripped.startswith(k) for k in _FIELD_KEYWORDS):
                        break
                    # 缩进小于等于当前缩进，且是一级关键字 → 结束
                    if indent <= base_indent and any(stripped.startswith(k) for k in _TOP_KEYWORDS):
                        break
                    # 否则属于 prompt 内容
                    plines.append(line_j.strip())
                    j += 1
                f['prompt'] = '\n'.join(plines)
                i = j
                continue
            else:
                f['prompt'] = pv.strip('"').strip("'")
        elif normalized_line.startswith('showprompt:'):
            pv = normalized_line[len('showprompt:'):].strip()
            # 支持中文竖线（｜）作为多行标志
            if pv in ('|', '｜'):
                base_indent = len(lines[i]) - len(lines[i].lstrip())
                j = i + 1
                plines = []
                while j < len(lines):
                    line_j = lines[j]
                    stripped = line_j.lstrip()
                    indent = len(line_j) - len(stripped)
                    # 同缩进 + 二级字段关键字 → 结束
                    if indent == base_indent and any(stripped.startswith(k) for k in _FIELD_KEYWORDS):
                        break
                    # 缩进小于等于当前缩进，且是一级关键字 → 结束
                    if indent <= base_indent and any(stripped.startswith(k) for k in _TOP_KEYWORDS):
                        break
                    # 否则属于 prompt 内容
                    plines.append(line_j.strip())
                    j += 1
                f['prompt'] = '\n'.join(plines)
                i = j
                continue
            else:
                f['prompt'] = pv.strip('"').strip("'")
        elif normalized_line.startswith('scope:'):
            # 保留原始 scope 字符串，去掉 'scope:' 前缀并去除两端空白
            raw_scope = line.strip()[len('scope:'):].strip()
            f['scope'] = raw_scope
        elif normalized_line.startswith('in:'):
            rest = normalized_line[len('in:'):].strip()
            if not rest:
                base_indent = len(lines[i]) - len(lines[i].lstrip())
                j = i + 1
                mappings = []
                while j < len(lines):
                    line_j = lines[j]
                    stripped = line_j.lstrip()
                    indent = len(line_j) - len(stripped)
                    # 同缩进 + 二级字段关键字 → 结束
                    if indent == base_indent and any(stripped.startswith(k) for k in _FIELD_KEYWORDS):
                        break
                    # 缩进小于等于当前缩进，且是一级关键字 → 结束
                    if indent <= base_indent and any(stripped.startswith(k) for k in _TOP_KEYWORDS):
                        break
                    # 处理映射行
                    mline = line_j.strip().rstrip(',')
                    if '=' in mline:
                        k, v = mline.split('=', 1)
                        mappings.append(InMapping(k.strip(), v.strip()))
                    else:
                        mappings.append(InMapping(mline, mline))
                    j += 1
                f['in_mappings'] = mappings
                i = j
                continue
            else:
                for mapping_str in rest.split(','):
                    mapping_str = mapping_str.strip()
                    if '=' in mapping_str:
                        k, v = mapping_str.split('=', 1)
                        f['in_mappings'].append(InMapping(k.strip(), v.strip()))
                    else:
                        f['in_mappings'].append(InMapping(mapping_str, mapping_str))
        elif normalized_line.startswith('out:'):
            out_rest = normalized_line[len('out:'):].strip()
            if not out_rest:
                # 多行 out：每行独立解析，用保留字段 + 缩进判断结束
                base_indent = len(lines[i]) - len(lines[i].lstrip())
                j = i + 1
                while j < len(lines):
                    line_j = lines[j]
                    stripped = line_j.lstrip()
                    indent = len(line_j) - len(stripped)
                    # 同缩进 + 二级字段关键字 → 结束
                    if indent == base_indent and any(stripped.startswith(k) for k in _FIELD_KEYWORDS):
                        break
                    # 缩进小于等于当前缩进，且是一级关键字 → 结束
                    if indent <= base_indent and any(stripped.startswith(k) for k in _TOP_KEYWORDS):
                        break
                    ol = normalize_symbols(lines[j].strip())
                    if ol:
                        f['outs'].extend(_parse_out_multi(ol))
                    j += 1
                i = j
                continue
            else:
                # 单行 out：直接解析（逗号分割）
                f['outs'] = _parse_out_multi(out_rest)
        elif line.startswith('resolve:'):
            raw = line[len('resolve:'):].strip()
            m = re.match(r'^(\S+)\(([^)]*)\)$', raw)
            if m:
                f['resolve'] = m.group(1).strip()
                f['resolve_args'] = [a.strip() for a in m.group(2).split(',') if a.strip()]
            else:
                f['resolve'] = raw
                f['resolve_args'] = []
        elif line.startswith('max_retries:'):
            try:
                f['max_retries'] = int(line[len('max_retries:'):].strip())
            except:
                pass
        elif line.startswith('fallback:'):
            f['fallback'] = line[len('fallback:'):].strip()
        elif line.startswith('memory:'):
            f['memory'] = line[len('memory:'):].strip()
        elif line.startswith('context:'):
            f['context'] = line[len('context:'):].strip()
        elif line.startswith('interrupt:'):
            f['interrupt'] = line[len('interrupt:'):].strip()
        i += 1
    return f

# ============================================================
# 语义分发器 — 各类型 evaluator
# ============================================================

def eval_meta(block: Block) -> Dict[str, Any]:
    return _eval_kv_block(block.content_lines)

def eval_vars(block: Block) -> Dict[str, Any]:
    # 临时调试：看清块的 content_lines 和 daughters
    print(f"[eval_vars DEBUG] type={block.type}, header={block.header!r}")
    print(f"[eval_vars DEBUG] content_lines({len(block.content_lines)}): {block.content_lines[:10]}")
    if block.daughters:
        for ch in block.daughters:
            print(f"[eval_vars DEBUG] daughter type={ch.type}, header={ch.header!r}, daughters={len(ch.daughters)}")
    d = _eval_kv_block(block.content_lines)
    def normalize(v):
        if isinstance(v, dict):
            return {normalize(k): normalize(val) for k, val in v.items()}
        if isinstance(v, list):
            return [normalize(item) for item in v]
        if isinstance(v, ActorRef):
            return str(v)
        return v
    result = {k: normalize(v) for k, v in d.items()}
    print(f"[eval_vars] 解析后键: {list(result.keys())}")
    return result

def eval_code(block: Block) -> Dict[str, str]:
    d = {}
    for line in block.content_lines:
        if '=' in line:
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            d[k] = v
    return d

def eval_actors(block: Block) -> Dict[str, ActorDef]:
    actors = {}
    lines = block.content_lines
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        bm = re.match(r'^(?:blueprint\s+|@)(\w+)\s*:\s*$', line)
        if bm:
            name = bm.group(1)
            attrs = {}
            j = i + 1
            while j < len(lines) and lines[j].startswith(' '):
                al = lines[j].strip()
                if '=' in al:
                    ak, av = al.split('=', 1)
                    ak, av = ak.strip(), av.strip().strip('"').strip("'")
                    if ak == 'tools':
                        attrs['tools'] = _parse_tools(av)
                    elif ak in ('soul', 'source'):
                        attrs[ak] = av  # 保持字符串，不转数字
                    else:
                        attrs[ak] = av
                j += 1
            actors[name] = ActorDef(type=ActorType.BLUEPRINT, ref=name, name=name,
                                    source=attrs.get('source'), tools=attrs.get('tools', []),
                                    is_blueprint=True)
            i = j
            continue
        if '=' in line:
            left, rest = line.split('=', 1)
            left_parts = left.strip().split()
            if len(left_parts) >= 2 and left_parts[0] in ('ai', 'human'):
                ats = left_parts[0]
                nm = left_parts[1]
                at = ActorType.AI if ats == 'ai' else ActorType.HUMAN
                soul, source, tools = None, None, []
                for p in _split_br(rest):
                    p = p.strip()
                    if p.startswith('soul:'):
                        raw_soul = p[5:].strip().strip('"').strip("'")
                        soul = raw_soul if raw_soul else None
                        #print(f"[DEBUG eval_actors] raw_soul={raw_soul!r}, final soul={soul!r}")
                    elif p.startswith('source:'):
                        source = p[7:].strip().strip('"').strip("'")
                        #print(f"[DEBUG eval_actors] source={source!r}")
                    elif p.startswith('tools:'):
                        tools = _parse_tools(p[6:])
                actors[nm] = ActorDef(type=at, ref=nm, name=nm, soul=soul, source=source, tools=tools)
                #print(f"[DEBUG eval_actors] 创建 human actor: {nm}, soul={soul!r}, source={source!r}")
        i += 1
    return actors

def eval_action(block: Block) -> ActionDef:
    header = normalize_symbols(block.header)
    m = re.match(r'^action\s+(\w+)\s+@(\w+)(?:\(([^)]*)\))?\s*(?:as\s*\(([^)]*)\))?\s*:\s*$', header)
    if not m:
        raise ValueError(f"无法解析 action 头部: {header}")
    name = m.group(1)
    etype = m.group(2)
    eparam = (m.group(3) or '').strip()
    as_actor = m.group(4)
    fields = _parse_action_fields(block)
    return ActionDef(
        name=name,
        executor_type=ExecutorType(etype),
        executor_param=eparam,
        as_actor=as_actor,
        **fields
    )

def eval_method(block: Block) -> MethodDef:
    header = normalize_symbols(block.header)
    m = re.match(r'^(memory|context)\s+(\w+)\s*\(\s*(\w+)\.(\w+)\s*\)\s*:\s*$', header)
    if not m:
        raise ValueError(f"无法解析 method 头部: {header}")
    name = m.group(2)
    module_alias = m.group(3)
    func_name = m.group(4)
    in_params = []
    out_defs = []
    lines = block.content_lines
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('in:'):
            rest = line[3:].strip()
            if rest:
                in_params = [p.strip() for p in rest.split(',') if p.strip()]
            else:
                i += 1
                while i < len(lines) and lines[i].startswith(' '):
                    pl = lines[i].strip().rstrip(',')
                    if pl:
                        in_params.append(pl)
                    i += 1
                continue
        elif line.startswith('out:'):
            rest = line[4:].strip()
            if rest:
                out_defs = _parse_out_multi(rest)
            else:
                i += 1
                out_lines = []
                while i < len(lines) and lines[i].startswith(' '):
                    out_lines.append(lines[i].strip())
                    i += 1
                if out_lines:
                    out_defs = _parse_out_multi(' '.join(out_lines))
                continue
        i += 1
    return MethodDef(name=name, module_alias=module_alias, func_name=func_name,
                     in_params=in_params, out_defs=out_defs)

# ============================================================
# 4. Flow 子解析 (原 FlowBuilder 完整移植)
# ============================================================

# ---- 缩进树构建 (为 flow 内部使用) ----
@dataclass
class IndentBlock:
    indent: int
    line: str
    daughters: List['IndentBlock'] = field(default_factory=list)

def build_indent_tree(text: str) -> List[IndentBlock]:
    """把 flow 文本按缩进解析成一棵树，忽略空行和注释"""
    lines = []
    for raw in text.split('\n'):
        stripped = raw.rstrip()
        if not stripped or stripped.lstrip().startswith('#') or stripped.lstrip().startswith('//'):
            continue
        indent = len(raw) - len(raw.lstrip())
        content = raw.strip()
        lines.append((indent, content))

    if not lines:
        return []

    root_blocks: List[IndentBlock] = []
    stack: List[Tuple[int, List[IndentBlock]]] = [(-1, root_blocks)]

    for indent, content in lines:
        block = IndentBlock(indent=indent, line=content)
        while stack[-1][0] >= indent:
            stack.pop()
        stack[-1][1].append(block)
        stack.append((indent, block.daughters))

    return root_blocks

# ---- Token 解析器 ----
def tokenize_chain(line: str) -> List[dict]:
    """解析一条 -> 链式行，支持 (if ...) 条件提取"""
    line = re.sub(r'(?<!\s)--(?!\s)', '->', line)
    content = re.sub(r'^->\s*', '', line)

    # 保护 if (...) 内部不被 -> 切割
    conds = []
    def save_cond(m):
        conds.append(m.group(1).strip())
        return f'__COND_{len(conds)-1}__'
    protected = re.sub(r'\bif\s*\((.+?)\)', save_cond, content)

    parts = re.split(r'\s*->\s*', protected)
    parts = [p.strip() for p in parts if p.strip()]

    tokens = []
    for part in parts:
        cond_match = re.match(r'^__COND_(\d+)__$', part)
        if cond_match:
            idx = int(cond_match.group(1))
            tokens.append({'type': 'cond', 'expr': conds[idx]})
        elif part == '[END]':
            tokens.append({'type': 'node', 'name': '[END]', 'ntype': 'end'})
        elif part == '[BREAK]':
            tokens.append({'type': 'node', 'name': '[BREAK]', 'ntype': 'break'})
        else:
            # 禁止控制关键字混入普通链
            if part in ('for', 'par', 'fork', 'join', 'to'):
                raise SyntaxError(f"控制关键字 '{part}' 不能出现在普通链中")
            tokens.append({'type': 'node', 'name': part, 'ntype': 'action'})
    return tokens

def chain_tokens(g: FlowGraph, tokens: List[dict], entry: str, reg_node_fn, reg_auto_fn) -> str:
    """处理一条 token 链，返回链尾节点ID"""
    current = entry if entry is not None else None
    pending_cond = None

    for tok in tokens:
        if tok['type'] == 'cond':
            pending_cond = tok['expr']
        elif tok['type'] == 'node':
            name = tok['name']
            if re.match(r'^\[.+\]', name):
                # 正式节点
                nid = reg_node_fn(g, name, tok.get('ntype', 'action'))
                g.add_edge(current, nid, condition=pending_cond or "")
                pending_cond = None
                current = nid
            else:
                raise SyntaxError(f"未声明的动作或模块 '{name}'，请在 flow 前用 [节点]: 语法定义。")

    return current

# ---- 安全条件求值 ----
def eval_condition(expr: str, context: dict) -> bool:
    """安全求值 Python 表达式，供运行时和流程图解析使用"""
    safe_expr = re.sub(r'@(\w+)', r'"@\1"', expr)
    try:
        tree = ast.parse(safe_expr, mode='eval')
    except SyntaxError:
        raise SyntaxError(f"条件表达式语法错误: {expr} -> 解析为 '{safe_expr}'")

    safe_builtins = {
        'True': True, 'False': False, 'None': None,
        'len': len, 'int': int, 'str': str, 'float': float,
        'bool': bool, 'abs': abs, 'min': min, 'max': max,
        'sum': sum, 'any': any, 'all': all,
        'isinstance': isinstance, 'hasattr': hasattr,
        'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
        'range': range, 'enumerate': enumerate,
    }

    namespace = {**safe_builtins, **context}
    try:
        result = eval(compile(tree, '<cond>', 'eval'), {"__builtins__": {}}, namespace)
        return bool(result)
    except Exception as e:
        raise RuntimeError(f"条件表达式求值失败: '{expr}', 上下文: {list(context.keys())}, 错误: {e}")

# ---- FlowBuilder 主类 ----
class FlowBuilder:
    def __init__(self):
        self._counter = 0
        self.node_bindings: Dict[str, str] = {}   # 节点绑定表 {节点名: 动作或&模块}

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"__{prefix}_{self._counter}__"
        
    def _reg_auto_node(self, g: FlowGraph, action_ref: str) -> str:
        """为裸动作或模块引用自动创建节点，自动处理重名（后缀 _1, _2 ...）"""
        if action_ref.startswith('&'):
            base_label = action_ref          # e.g. "&MD"
            module_ref = action_ref[1:]
            action_name = None
        else:
            base_label = action_ref
            module_ref = None
            action_name = action_ref

        node_id = f'[{base_label}]'
        counter = 1
        while node_id in g.nodes:
            node_id = f'[{base_label}_{counter}]'
            counter += 1

        node = FlowNode(
            id=node_id, type='action', label=base_label,
            action_name=action_name, module_ref=module_ref,
        )
        g.add_node(node)
        return node_id

    def _reg_node(self, g: FlowGraph, name: str, ntype: str = "action") -> str:
        m = re.match(r'^\[([^\]]+)\]', name)
        if m:
            node_id = f'[{m.group(1)}]'
            label = m.group(1)
            rest = name[m.end():].lstrip(':')
        else:
            raise ValueError(f"不能将裸动作/模块注册为节点: {name}")

        if node_id in g.nodes:
            return node_id

        action_name = None
        module_ref = None
        # 优先从绑定字典获取（标准化器提供的声明区信息）
        node_key = m.group(1)   # 节点名（不含方括号）
        binding = self.node_bindings.get(node_key, '')
        if binding:
            if binding.startswith('&'):
                module_ref = binding[1:]
            else:
                action_name = binding
        elif rest:
            rest = rest.strip()
            if rest.startswith('&'):
                module_ref = rest[1:]
            else:
                action_name = rest

        if node_id in ('[START]', '[END]', '[BREAK]', '[IN]', '[OUT]'):
            special_map = {
                '[START]': 'start', '[END]': 'end', '[BREAK]': 'break',
                '[IN]': 'start', '[OUT]': 'end',
            }
            ntype = special_map.get(node_id, ntype)

        node = FlowNode(
            id=node_id, type=ntype, label=label,
            action_name=action_name, module_ref=module_ref,
        )
        g.add_node(node)
        return node_id

    def _reg_gateway(self, g: FlowGraph, prefix: str, ntype: str, meta: dict = None) -> str:
        gid = self._next_id(prefix)
        g.add_node(FlowNode(id=gid, type=ntype, meta=meta or {}))
        return gid


    def build_flow(self, text: str) -> FlowGraph:
        blocks = build_indent_tree(text)
        g = FlowGraph()
        self._pending_exit_candidates = {}  # 临时存储 for/par 的出口候选，供出口行连接
        self._parse_flow_blocks(blocks, g, None)
        return g

    def _parse_flow_blocks(self, blocks: List[IndentBlock], g: FlowGraph, pending_from: Optional[str]):
        """递归解析顶层或嵌套的流程块列表"""
        i = 0
        while i < len(blocks):
            block = blocks[i]
            line = block.line.strip()

            # ── 出口行 `-> Target` ──
            if line.startswith('->') and not re.search(r'\b(for|par|fork|join)\b', line):
                # 孤立出口行不允许，除非是由外部 for/par 消费
                raise SyntaxError(f"孤立的出口行，只能紧跟在 for/par 块之后消费: {line}")

            # ── join(...): 独立行（无前导链） ──
            if re.match(r'^join\s*(?:\((\w+)\))?\s*:\s*$', line):
                join_gw = self.parse_join(block, g)
                # 检查下一个同级块是否为 'to Target' 出口行
                if i + 1 < len(blocks):
                    next_line = blocks[i + 1].line.strip()
                    if next_line.startswith('to '):
                        target_str = next_line[3:].strip()
                        target_id = self._reg_node(g, target_str)
                        g.add_edge(join_gw, target_id)
                        pending_from = target_id
                        i += 2
                        continue
                pending_from = join_gw
                i += 1
                continue

            # ── 控制块首行 [Node] -> for/par/fork/join ──
            ctrl_match = re.match(r'^(.+?)\s*->\s*(for|par|fork|join)\b(.*):\s*$', line)
            if ctrl_match:
                ctrl_type = ctrl_match.group(2)
                if ctrl_type == 'for':
                    # 提取变量和迭代器
                    params = ctrl_match.group(3).strip()
                    var_m = re.match(r'(@?\w+)\s+in\s+(.+)', params)
                    if not var_m:
                        raise SyntaxError(f"for 语法错误: {line}")
                    var_name = var_m.group(1)
                    iterable = var_m.group(2)
                    loop_gw = self._reg_gateway(g, "for", "gateway",
                                                meta={"gw_kind": "for", "var_name": var_name, "iterable": iterable})
                    pre_tail = self.parse_single_chain(ctrl_match.group(1).strip(), None, g)
                    if pre_tail:
                        g.add_edge(pre_tail, loop_gw)
                    # 处理 for 体
                    nested, plain = self._separate_nested_blocks(block.daughters)
                    exit_candidates = self._process_inner_single_lines(plain, loop_gw, g)
                    for nest_block in nested:
                        self._process_nested_control_block(nest_block, g)
                    # 检查下一个同级块是否为出口行
                    target_id = None
                    if i + 1 < len(blocks):
                        next_line = blocks[i + 1].line.strip()
                        if next_line.startswith('->'):
                            target_id = self._reg_node(g, next_line[2:].strip())
                            i += 1  # 消费出口行
                    # 为每个出口候选节点添加回边到循环网关
                    for nid in exit_candidates:
                        g.add_edge(nid, loop_gw)
                    if target_id:
                        g.add_edge(loop_gw, target_id)      # 循环结束后的出口边
                        pending_from = target_id
                    else:
                        if not exit_candidates:
                            raise SyntaxError(
                                f"for 循环体缺少出口标记（行末 '->'），必须至少有一个出口，或者提供出口行 -> Target"
                            )
                        break_id = self._reg_node(g, "[BREAK]", "break")
                        g.add_edge(loop_gw, break_id)
                        pending_from = break_id

                elif ctrl_type == 'par':
                    join_gw = self.parse_par(block, g)
                    # 检查下一个同级块是否为出口行
                    target_id = None
                    if i + 1 < len(blocks):
                        next_line = blocks[i + 1].line.strip()
                        if next_line.startswith('->'):
                            target_id = self._reg_node(g, next_line[2:].strip())
                            i += 1
                    if target_id:
                        g.add_edge(join_gw, target_id)
                        pending_from = target_id
                    else:
                        # 如果没有出口行，默认连 [BREAK]
                        break_id = self._reg_node(g, "[BREAK]", "break")
                        g.add_edge(join_gw, break_id)
                        pending_from = break_id

                elif ctrl_type == 'fork':
                    fork_gw = self._reg_gateway(g, "fork", "gateway", meta={"gw_kind": "fork"})
                    pre_tail = self.parse_single_chain(ctrl_match.group(1).strip(), None, g)
                    if pre_tail:
                        g.add_edge(pre_tail, fork_gw)
                    for daughter in block.daughters:
                        cl = daughter.line.strip()
                        if not cl.startswith('->'):
                            raise SyntaxError(f"fork 体内行必须以 '->' 开头: {cl}")
                        if cl.rstrip().endswith('->'):
                            raise SyntaxError(f"fork 体内不允许使用出口标记 '->' : {cl}")
                        core = cl[2:].lstrip()
                        self.parse_single_chain(core, fork_gw, g)
                    pending_from = None  # fork 无统一出口

                elif ctrl_type == 'join':
                    # 带前导链的 join 实际上不允许，但根据要求不改 join，所以不支持前导链
                    raise SyntaxError("join 不支持前导链，请使用 'join(...):' 独立行")
                i += 1
                continue

            # ── 普通单链行（独立起点，不使用 pending_from）──
            if line.startswith('['):
                tail = self.parse_single_chain(line, None, g)
                # 普通链的末端作为新的 pending_from，供后续可能的控制块前导链或出口行使用
                pending_from = tail
                i += 1
                continue

            # 其他情况报错
            raise SyntaxError(f"无法识别的流程行: {line}")
        
        
    # ─── 控制块解析辅助 ────────────────────────────────────────────
    def _parse_control_head(self, line: str):
        """解析 [Node] -> for/par/fork/join(...) : 行，返回 (前导链文本, 控制类型, 参数字符串)"""
        m = re.match(r'^(.+?)\s*->\s*(for|par|fork|join)\b(.*):\s*$', line)
        if not m:
            raise SyntaxError(f"无法解析控制块首行: {line}")
        pre_chain = m.group(1).strip()
        ctrl_type = m.group(2)
        params = m.group(3).strip()
        return pre_chain, ctrl_type, params

    def _separate_nested_blocks(self, daughters: List[IndentBlock]):
        """将子块列表分为嵌套控制块和纯单链行"""
        nested = []
        plain = []
        for daughter in daughters:
            line = daughter.line.strip()
            # 嵌套控制块的首行模式：以 [Node] 开头，且包含 -> for/par/fork/join
            if re.match(r'^\[.+\]\s*->\s*(for|par|fork|join)\b', line):
                nested.append(daughter)
            else:
                plain.append(daughter)
        return nested, plain

    def parse_single_chain(self, line: str, entry: Optional[str], g: FlowGraph):
        """解析一条普通单链，返回链尾节点ID，entry可为None"""
        tokens = tokenize_chain(line)
        if not tokens:
            return entry
        return chain_tokens(g, tokens, entry, self._reg_node, self._reg_auto_node)

    def _process_inner_single_lines(self, plain_daughters: List[IndentBlock],
                                    gateway_id: str, g: FlowGraph) -> List[str]:
        """处理 for/par 体内的纯单链行，返回出口候选节点ID列表"""
        exit_candidates = []
        for daughter in plain_daughters:
            raw_line = daughter.line.strip()
            # 判断行首 -> 和行尾 ->
            starts_with_arrow = raw_line.startswith('->')
            ends_with_arrow = raw_line.rstrip().endswith('->')

            # 剥除首尾 ->
            core = raw_line
            if starts_with_arrow:
                core = core[2:].lstrip()  # 去掉开头的 '->'
            if ends_with_arrow:
                # 去掉末尾的 '->'，注意可能后面有空格
                core = re.sub(r'\s*->\s*$', '', core).rstrip()

            # 决定解析入口
            entry = gateway_id if starts_with_arrow else None
            tail = self.parse_single_chain(core, entry, g)
            if tail is None:
                continue

            if ends_with_arrow:
                exit_candidates.append(tail)
        return exit_candidates

    # ─── 具体控制块解析器 ─────────────────────────────────────────
    def parse_for(self, block: IndentBlock, g: FlowGraph) -> str:
        """解析 for 循环块，返回出口节点ID（或[BREAK]）"""
        pre_chain, _, params = self._parse_control_head(block.line.strip())
        # 提取变量和迭代对象
        m = re.match(r'(@?\w+)\s+in\s+(.+)', params)
        if not m:
            raise SyntaxError(f"for 语法错误: {block.line}")
        var_name = m.group(1)
        iterable = m.group(2)

        # 创建循环网关
        loop_gw = self._reg_gateway(g, "for", "gateway",
                                    meta={"gw_kind": "for", "var_name": var_name, "iterable": iterable})

        # 解析前导链，连接到循环网关
        pre_tail = self.parse_single_chain(pre_chain, None, g) if pre_chain else None
        if pre_tail:
            g.add_edge(pre_tail, loop_gw)

        # 分离嵌套块和单链行
        nested, plain = self._separate_nested_blocks(block.daughters)
        # 先处理单链行
        exit_candidates = self._process_inner_single_lines(plain, loop_gw, g)
        # 递归处理嵌套控制块（它们可能贡献更多的体内节点，也参与后续单链行的连接）
        for nest_block in nested:
            self._process_nested_control_block(nest_block, g)

        # 出口行处理 (由外层 parse_flow_blocks 调用时处理，这里先假设没有出口行，暂连[BREAK])
        # 为保持独立性，我们在此统一：如果没有出口行，连[BREAK]；出口行由外部消费，外部会调用 set_exit
        # 我们先收集 exit_candidates，并提供一个方法 set_for_exit(target) 来连接出口。
        # 但为了简化，我们把出口候选存在一个临时属性或返回出去？
        # 设计：parse_for 只处理内部并返回 (loop_gw, exit_candidates, <后续>)。由于出口行在外部被消费，我们需要让外部能访问这些信息。
        # 简便做法：在 FlowBuilder 实例上临时存储，或者返回三元组。这里我们让 parse_for 返回一个特殊对象，或者我们直接在这里连接一个默认出口（[BREAK]），外部可通过在消费出口行后修改边。
        # 更优雅：parse_for 处理完内部后，不处理出口，而是将 loop_gw 和 exit_candidates 存储，然后外部调用 connect_exit 方法。但阶段四才重写 build_flow，现在我们可以先让 parse_for 始终连到 [BREAK]，阶段四再由外部覆盖。
        # 现在我们按阶段三的要求，提供可用的函数，具体行为与阶段四配合。我们先假设默认连 [BREAK]。
        break_node_id = self._reg_node(g, "[BREAK]", "break")
        for nid in exit_candidates:
            g.add_edge(nid, break_node_id)
        return break_node_id   # for 块出口视为 [BREAK]，阶段四会用出口行覆盖

    def parse_par(self, block: IndentBlock, g: FlowGraph) -> str:
        """解析 par 并行循环块，返回出口节点ID（或[BREAK]）"""
        pre_chain, _, params = self._parse_control_head(block.line.strip())
        m = re.match(r'(@?\w+)\s+in\s+(.+)', params)
        if not m:
            raise SyntaxError(f"par 语法错误: {block.line}")
        var_name = m.group(1)
        iterable = m.group(2)

        join_gw = self._reg_gateway(g, "par_join", "gateway",
                                    meta={"gw_kind": "join", "join_mode": "all"})
        fork_gw = self._reg_gateway(g, "par_fork", "gateway",
                                    meta={"gw_kind": "fork", "is_par_fork": True,
                                          "par_var": var_name, "par_iterable": iterable,
                                          "join_target": join_gw})

        pre_tail = self.parse_single_chain(pre_chain, None, g) if pre_chain else None
        if pre_tail:
            g.add_edge(pre_tail, fork_gw)

        nested, plain = self._separate_nested_blocks(block.daughters)
        exit_candidates = self._process_inner_single_lines(plain, fork_gw, g)
        for nest_block in nested:
            self._process_nested_control_block(nest_block, g)

        for nid in exit_candidates:
            g.add_edge(nid, join_gw)

        # 返回 join_gw 给调用方，由调用方决定出口边（[BREAK] 或显式 -> Target）
        return join_gw

    def parse_fork(self, block: IndentBlock, g: FlowGraph) -> Optional[str]:
        """解析 fork 块，无统一出口，返回 None"""
        pre_chain, _, _ = self._parse_control_head(block.line.strip())
        fork_gw = self._reg_gateway(g, "fork", "gateway", meta={"gw_kind": "fork"})

        pre_tail = self.parse_single_chain(pre_chain, None, g) if pre_chain else None
        if pre_tail:
            g.add_edge(pre_tail, fork_gw)

        # fork 内部只允许 -> 开头的行
        for daughter in block.daughters:
            line = daughter.line.strip()
            if not line.startswith('->'):
                raise SyntaxError(f"fork 体内行必须以 '->' 开头: {line}")
            core = line[2:].lstrip()
            self.parse_single_chain(core, fork_gw, g)
        return None   # 无统一出口

    def parse_join(self, block: IndentBlock, g: FlowGraph) -> str:
        """解析 join 块（保留原逻辑，不支持前导链）"""
        # 仅当 join 独立行时使用，即首行不包含前导链
        m = re.match(r'^join\s*(?:\((\w+)\))?\s*:\s*$', block.line.strip())
        if not m:
            raise SyntaxError(f"join 语法错误: {block.line.strip()}")
        mode = m.group(1) if m.group(1) else 'all'
        join_gw = self._reg_gateway(g, "join", "gateway",
                                    meta={"gw_kind": "join", "join_mode": mode})
        # 处理子块中的入边声明（[Node] -> ）
        for daughter in block.daughters:
            cl = daughter.line.strip()
            if not cl.startswith('['):
                raise SyntaxError(f"join 内部只能有 [Node] -> 入边声明: {cl}")
            # 去掉可能的末尾 '->'
            source_str = re.sub(r'\s*->\s*$', '', cl)
            source_id = self._reg_node(g, source_str)
            g.add_edge(source_id, join_gw)
        return join_gw

    def _process_nested_control_block(self, block: IndentBlock, g: FlowGraph):
        """递归处理嵌套控制块"""
        line = block.line.strip()
        # 判断类型
        if re.search(r'\bfor\b', line):
            self.parse_for(block, g)
        elif re.search(r'\bpar\b', line):
            self.parse_par(block, g)
        elif re.search(r'\bfork\b', line):
            self.parse_fork(block, g)
        elif re.search(r'\bjoin\b', line):
            self.parse_join(block, g)
        else:
            raise SyntaxError(f"未知嵌套控制块: {line}")

# ============================================================
# 5. 顶层解析入口
# ============================================================

def eval_flow(block: Block) -> FlowGraph:
    # 标准化器已经把声明区提取到 mainflow 之前，此处 flow 文本只包含流程描述。
    flow_lines = block.content_lines
    flow_text = '\n'.join(flow_lines)
    flow_text = normalize_symbols(flow_text)

    # 节点绑定已由标准化器处理，不再需要从 flow 内部解析。
    # 但标准化器生成的节点定义放在 mainflow 之前，解析器不会读到它们。
    # 我们需要一个方式将节点绑定传递给 FlowBuilder。
    # 暂时留空，因为我们的新语法中所有节点引用都必须已在流程中注册（通过 [Node] -> 形式出现）。
    # 事实上，标准化器生成的 [Node]: binding 被移到了脚本顶部，不属于 flow 文本。
    # 所以此时无需绑定表，流程图中的节点引用会自动通过 reg_node 注册。
    builder = FlowBuilder()
    # 忽略旧绑定表传递
    return builder.build_flow(flow_text)

def eval_module(block: Block) -> ModuleDef:
    header = normalize_symbols(block.header)
    m = re.match(r'^module\s+(\w+)(?:\s*\(([^)]*)\))?\s*:?\s*$', header)
    if not m:
        raise ValueError(f"无法解析 module 头部: {header}")
    name = m.group(1)
    params = [p.strip() for p in m.group(2).split(',') if p.strip()] if m.group(2) else []
    mod = ModuleDef(name=name, params=params)

    for daughter in block.daughters:
        t = daughter.type
        if t == 'meta':
            mod.meta = eval_meta(daughter)
        elif t == 'vars':
            mod.locals = eval_vars(daughter)
        elif t == 'action':
            act = eval_action(daughter)
            mod.actions[act.name] = act
        elif t == 'module':
            sub = eval_module(daughter)
            mod.modules[sub.name] = sub
        elif t == 'memory':
            mem = eval_method(daughter)
            mod.memories[mem.name] = mem
        elif t == 'context':
            ctx = eval_method(daughter)
            mod.contexts[ctx.name] = ctx
        elif t == 'flow':
            mod.flow = eval_flow(daughter)
    return mod

def _node_is_ai_action(node: FlowNode, actions: Dict[str, ActionDef]) -> bool:
    """
    判断 FlowNode 绑定的 Action 是否为 AI 类型。
    仅当节点有 action_name 且 ActionDef.executor_type == AI 时返回 True。
    gateway、start、end、module_call 等节点返回 False。
    """
    if not node or not node.action_name:
        return False
    action = actions.get(node.action_name)
    is_ai = action.executor_type == ExecutorType.AI
    print(f"[parser] 🔍 节点 {node.id}: action_name={node.action_name}, executor_type={action.executor_type}, is_ai={is_ai}")
    return is_ai


def inject_delay_nodes(flow: FlowGraph, actions: Dict[str, ActionDef], delay_seconds: int) -> None:
    """
    遍历 flow 所有边，若 source 和 target 节点都绑定 AI Action，
    在中间插入一个 delay 节点。

    原始边: A --(cond)--> B
    变成:   A --(cond)--> [delay_X] --()--> B

    delay 节点 type='delay'，meta 内存 is_delay_node=True 和 delay_seconds。
    原边 condition 跟第一段走（A→delay），第二段（delay→B）无条件。
    """
    print(f"[parser] ⏱️ inject_delay_nodes: 开始, delay={delay_seconds}s, 边数={len(flow.edges)}, 节点数={len(flow.nodes)}")

    new_edges = []
    delay_counter = 0

    for edge in flow.edges:
        source_node = flow.nodes.get(edge.source)
        target_node = flow.nodes.get(edge.target)

        source_is_ai = _node_is_ai_action(source_node, actions) if source_node else False
        target_is_ai = _node_is_ai_action(target_node, actions) if target_node else False

        if source_is_ai and target_is_ai:
            delay_counter += 1
            delay_id = f"[__delay_{edge.source}_{edge.target}_{delay_counter}__]"

            delay_node = FlowNode(
                id=delay_id,
                type='delay',
                label=f'delay({delay_seconds}s)',
                meta={'is_delay_node': True, 'delay_seconds': delay_seconds},
            )
            flow.add_node(delay_node)

            # 第一段: source -> delay, 保留原 condition
            new_edges.append(FlowEdge(
                source=edge.source,
                target=delay_id,
                condition=edge.condition,
            ))
            # 第二段: delay -> target, 无条件
            new_edges.append(FlowEdge(
                source=delay_id,
                target=edge.target,
                condition="",
            ))
            print(f"[parser] ⏱️ 注入 delay: {edge.source} --({edge.condition or '无条件'})--> {delay_id} --()--> {edge.target}")
        else:
            new_edges.append(edge)

    flow.edges = new_edges
    print(f"[parser] ⏱️ inject_delay_nodes: 完成, 注入 {delay_counter} 个 delay 节点, 新边数={len(flow.edges)}")


def parse_script(text: str, base_dir: str = ".") -> Script:
    """主解析入口：文本 → Script 对象"""

    # ── 前置标准化：消除语法糖、续行、裸动作等 ──
    from femCompiler.FEM_normalizer import FEMNormalizer
    normalizer = FEMNormalizer()
    text = normalizer.normalize(text)

    # 临时：把标准化后的文本写入文件，方便对比
    with open("debug_normalized_output.fems", "w", encoding="utf-8") as f:
        f.write(text)

    blocks = build_blocks(text)
    script = Script()

    for block in blocks:
        t = block.type
        if t == 'meta':
            script.meta = eval_meta(block)
        elif t == 'vars':
            script.vars = eval_vars(block)
        elif t == 'code':
            script.code = eval_code(block)
        elif t == 'actors':
            script.actors = eval_actors(block)
        elif t == 'action':
            act = eval_action(block)
            script.actions[act.name] = act
        elif t == 'module':
            mod = eval_module(block)
            script.modules[mod.name] = mod
        elif t == 'memory':
            mem = eval_method(block)
            script.memories[mem.name] = mem
        elif t == 'context':
            ctx = eval_method(block)
            script.contexts[ctx.name] = ctx
        elif t == 'flow':
            script.flow = eval_flow(block)

    # 处理 database 路径 —— 基于 user_dir，避免重复拼接
    if 'database' in script.meta:
        from femCompiler.FEM_config import get_user_dir   # 可移到文件顶部
        db_path = script.meta['database']
        if db_path.startswith('file:"') and db_path.endswith('"'):
            db_path = db_path[6:-1]
        elif db_path.startswith("file:'") and db_path.endswith("'"):
            db_path = db_path[6:-1]

        if not os.path.isabs(db_path):
            user_dir = get_user_dir()
            # 防止重复拼接 user_dir 的最后一级目录名
            last_component = os.path.basename(user_dir.rstrip('/\\'))
            if last_component and db_path.startswith(last_component + os.sep):
                db_path = db_path[len(last_component) + 1:]
            db_path = os.path.join(user_dir, db_path)

        script.meta['database'] = db_path
        
    owner_val = script.meta.get('owner')
    if owner_val is not None:
        if isinstance(owner_val, (int, float)):
            script.meta['owner'] = [str(owner_val)]
        elif isinstance(owner_val, str):
            script.meta['owner'] = [owner_val]
        elif isinstance(owner_val, list):
            script.meta['owner'] = [str(x) for x in owner_val]

    # ── Delay 注入：在连续 AI Action 之间插入等待节点 ──
    delay_seconds = script.meta.get('delay', 0)
    print(f"[parser] ⏱️ 读取 meta.delay = {delay_seconds!r} (type={type(delay_seconds).__name__})")
    if isinstance(delay_seconds, str):
        try:
            delay_seconds = int(delay_seconds)
        except (ValueError, TypeError):
            print(f"[parser] ⚠️ meta.delay 不是有效整数: {delay_seconds!r}")
            delay_seconds = 0
    if delay_seconds > 0:
        print(f"[parser] ⏱️ meta.delay = {delay_seconds}，开始注入 delay 节点...")

        # 主 flow
        if script.flow:
            print(f"[parser] ⏱️ 处理主 flow: 节点数={len(script.flow.nodes)}, 边数={len(script.flow.edges)}")
            inject_delay_nodes(script.flow, script.actions, delay_seconds)
        else:
            print(f"[parser] ⏱️ 主 flow 为空，跳过")

        # 递归注入所有模块的 flow（含嵌套子模块）
        def _inject_all_modules(modules: Dict[str, ModuleDef], global_actions: Dict[str, ActionDef]):
            for mod_name, mod in modules.items():
                print(f"[parser] ⏱️ 处理模块: {mod_name}, 局部 actions={list(mod.actions.keys())}")
                merged_actions = dict(global_actions)
                merged_actions.update(mod.actions)
                if mod.flow:
                    print(f"[parser] ⏱️ 模块 {mod_name} flow: 节点数={len(mod.flow.nodes)}, 边数={len(mod.flow.edges)}")
                    inject_delay_nodes(mod.flow, merged_actions, delay_seconds)
                else:
                    print(f"[parser] ⏱️ 模块 {mod_name} 无 flow，跳过")
                if mod.modules:
                    print(f"[parser] ⏱️ 模块 {mod_name} 有 {len(mod.modules)} 个嵌套子模块，递归...")
                    _inject_all_modules(mod.modules, merged_actions)

        _inject_all_modules(script.modules, script.actions)
        print(f"[parser] ⏱️ delay 注入全部完成。")
    else:
        print(f"[parser] ⏱️ delay <= 0 或未设置，跳过注入")

    return script
