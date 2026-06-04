"""
femCompiler/FEM_normalizer.py — 脚本标准化器
将随意编写的 .fems 脚本转换为结构清晰、无语法糖的标准化文本，
供后续编译器（FEM_parser）直接解析，无需再处理裸动作、续行、控制流内嵌等复杂情况。

处理步骤：
  0. 去注释、空行，连接续行
  1. 识别 mainflow: 之后的流程区域
  2. 在流程区域内：
     a. 提取所有节点定义 [Name]: action/module，并移出流程区域
     b. 将裸动作、&module 替换为自动生成的节点引用并注册
     c. 分离链内嵌控制关键字（fork/for/par/join），插入临时网关节点
     d. 将 to 行与 join 同级化，拆分 to [X] -> [Y]
  3. 补充缺失的空节点定义（凡引用过的 [Node] 若未定义，则自动创建空定义）
  4. 收集所有节点定义，统一输出到 mainflow: 之前
  5. 重新输出整洁的流程区域
"""

import re
from typing import List, Dict


class FEMNormalizer:
    """FEM 脚本标准化器"""

    def __init__(self):
        self._gateway_counter = 0
        # 节点定义存储：key 为不带括号的节点名（普通动作名如 EveMove 或 &module）
        self._definitions: Dict[str, str] = {}

    def _next_gateway_id(self, prefix: str = "gw") -> str:
        """生成唯一的网关 ID，形如 __fork_1__, __join_2__"""
        self._gateway_counter += 1
        return f"__{prefix}_{self._gateway_counter}__"

    def _process_flow_block(self, inner_lines: List[str], base_indent: int) -> List[str]:
        """处理一个 flow 块的内部内容，返回标准化后的行列表（保持原缩进），
        并将本块产生的定义行输出在流程区之前。
        """
        if not inner_lines:
            return []

        # 记录已有定义，以便检测本块新增的定义
        old_def_keys = set(self._definitions.keys())

        # 1. 计算内部行的最小缩进
        min_indent = base_indent + 2
        for line in inner_lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                if indent < min_indent:
                    min_indent = indent

        # 2. 去除最小缩进
        dedented_lines = []
        for line in inner_lines:
            if line.strip():
                dedented_lines.append(line[min_indent:])
            else:
                dedented_lines.append('')

        # 3. 按 [START] 或 [IN] 分割声明区和流程区
        decl_lines = []
        flow_part = []
        flow_started = False
        for dline in dedented_lines:
            stripped = dline.strip()
            if not flow_started and re.search(r'\[(START|IN)\]', stripped):
                flow_started = True
            if not flow_started:
                decl_lines.append(dline)
            else:
                flow_part.append(dline)

        # 4. 从声明区提取定义
        local_defs = {}
        for line in decl_lines:
            modified = line
            while True:
                m = re.search(r'\[(\w+)\]\s*:\s*(\S.*?)(?=\s*->|\s*$)', modified)
                if not m:
                    break
                node_name = m.group(1)
                binding = m.group(2).strip()
                self._definitions[node_name] = binding
                local_defs[node_name] = binding
                start, end = m.span()
                modified = modified[:start] + f'[{node_name}]' + modified[end:]

        # 5. 流程区替换裸动作（同时可能产生内联定义）
        expanded_flow = []
        for line in flow_part:
            expanded_flow.append(self._replace_bare_actions(line))

        # 6. 补充缺失的节点定义
        self._fill_missing_node_definitions(expanded_flow)

        # 7. 收集本块新增的所有定义（包括内联产生的）
        new_def_keys = set(self._definitions.keys()) - old_def_keys
        for key in new_def_keys:
            if key not in local_defs:
                local_defs[key] = self._definitions[key]

        # 8. 构建输出行（带缩进）
        result = []
        for node, binding in local_defs.items():
            def_line = f"[{node}]: {binding}" if binding else f"[{node}]:"
            result.append(' ' * min_indent + def_line)
        for line in expanded_flow:
            result.append(' ' * min_indent + line)

        return result
        
        
    def normalize(self, text: str) -> str:
        lines = text.splitlines()
        # 去注释、空行
        clean_lines = []
        for raw_line in lines:
            line = self._remove_comment(raw_line)
            if line.strip() == '':
                continue
            clean_lines.append(line)

        # ★ 移除所有 sketch: 块（无论在顶层还是模块内）
        clean_lines = self._remove_sketch_blocks(clean_lines)

        # 收集所有 flow/mainflow 块的起止索引
        blocks = []
        i = 0
        while i < len(clean_lines):
            line = clean_lines[i]
            stripped = line.lstrip()
            if re.match(r'^(mainflow|flow)\s*:', stripped):
                indent = len(line) - len(line.lstrip())
                j = i + 1
                while j < len(clean_lines):
                    next_line = clean_lines[j]
                    if next_line.strip() == '':
                        j += 1
                        continue
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent <= indent:
                        break
                    j += 1
                blocks.append((i, j))
                i = j
            else:
                i += 1

        if not blocks:
            return '\n'.join(clean_lines)

        result = list(clean_lines)
        for start_idx, end_idx in reversed(blocks):
            header_line = result[start_idx]
            inner_lines = result[start_idx+1:end_idx]
            indent = len(header_line) - len(header_line.lstrip())
            processed_inner = self._process_flow_block(inner_lines, indent)
            result[start_idx+1:end_idx] = processed_inner

        return '\n'.join(result)
        
        
    def _remove_sketch_blocks(self, lines: List[str]) -> List[str]:
        """删除所有 sketch: 及其缩进块内容"""
        result = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            m = re.match(r'(\s*)sketch\s*:', line)
            if m:
                base_indent = len(m.group(1))
                i += 1  # 跳过 sketch: 行本身
                # 跳过所有缩进严格大于 base_indent 的行（块内容）
                while i < n and (len(lines[i]) - len(lines[i].lstrip())) > base_indent:
                    i += 1
                continue  # 不添加到结果中
            else:
                result.append(line)
                i += 1
        return result
        
        
    def _remove_comment(self, line: str) -> str:
        in_str = False
        quote_char = None
        for i, ch in enumerate(line):
            if in_str:
                if ch == '\\' and i + 1 < len(line):
                    pass
                elif ch == quote_char:
                    in_str = False
            else:
                if ch in ('"', "'"):
                    in_str = True
                    quote_char = ch
                elif ch == '#' or (ch == '/' and i + 1 < len(line) and line[i + 1] == '/'):
                    return line[:i].rstrip()
        return line

    def _replace_bare_actions(self, line: str) -> str:
        """将不在 [] 中的独立动作名或 &module 替换为 [自动节点]，但保护控制关键字片段"""
        # 按 '->' 分割，保留分隔符
        parts = re.split(r'(\s*->\s*)', line)
        new_parts = []
        for part in parts:
            if re.match(r'\s*->\s*', part):
                # 箭头本身，直接保留
                new_parts.append(part)
                continue
            stripped = part.strip()
            # 1) 先检查是否为内联节点定义：[node]: binding
            def_match = re.match(r'^\[(\w+)\]:\s*(.*)$', stripped)
            if def_match:
                node_name = def_match.group(1)
                binding = def_match.group(2).strip()
                # 记录定义（若同名已存在则覆盖，通常不会）
                self._definitions[node_name] = binding
                # 替换为仅 [node]，保留原有缩进空白
                leading = part[:len(part) - len(part.lstrip())]
                new_parts.append(leading + f'[{node_name}]')
                continue

            # 2) 检查是否为控制关键字片段（if, for, par, fork, join, to）
            if re.match(r'\b(if|for|par|fork|join|to)\b', stripped):
                new_parts.append(part)
                continue

            # 3) 普通片段：应用裸动作替换
            leading = part[:len(part) - len(part.lstrip())]
            content = part.lstrip()
            new_content = self._replace_bare_in_fragment(content)
            new_parts.append(leading + new_content)
        return ''.join(new_parts)

    def _replace_bare_in_fragment(self, fragment: str) -> str:
        """对不包含控制关键字的片段进行裸动作替换"""
        def replacer(m):
            token = m.group(1)
            # 关键字保护（作为兜底）
            keywords = {'fork', 'for', 'par', 'join', 'to', 'if', 'in', 'all', 'any', 'n'}
            if token.lower() in keywords:
                return token
            # 生成节点内部键
            node_key = token
            if token.startswith('&'):
                base = token[1:]
                node_key = f'&{base}'
            else:
                node_key = token
            original_key = node_key
            counter = 1
            while node_key in self._definitions:
                node_key = f'{original_key}_{counter}'
                counter += 1
            self._definitions[node_key] = token
            return f'[{node_key}]'

        # 处理普通单词（不含括号的）
        fragment = re.sub(r'(?<!\[)\b(&?\w+)\b(?!\])', replacer, fragment)
        # 处理带括号的模块引用 &mymodule(args)
        fragment = re.sub(
            r'(?<!\[)&(\w+)\(([^)]*)\)',
            lambda m: self._handle_module_ref(m.group(1), m.group(2)),
            fragment
        )
        return fragment

    def _handle_module_ref(self, mod_name: str, args: str) -> str:
        token = f'&{mod_name}({args})'
        node_key = f'&{mod_name}'
        counter = 1
        while node_key in self._definitions:
            node_key = f'&{mod_name}_{counter}'
            counter += 1
        self._definitions[node_key] = token
        return f'[{node_key}]'

    def _fill_missing_node_definitions(self, flow_lines: List[str]):
        """扫描所有 [...] 节点引用，若未定义则添加空定义（跳过保留字和内部网关）"""
        RESERVED = {'START', 'END', 'BREAK', 'IN', 'OUT'}
        for line in flow_lines:
            refs = re.findall(r'\[(\w+)\]', line)
            for name in refs:
                if name in RESERVED:
                    continue
                if name.startswith('__') and name.endswith('__'):
                    continue  # 内部网关节点不声明
                if name not in self._definitions:
                    self._definitions[name] = ''  # 空定义

# 测试入口
if __name__ == '__main__':
    print("请输入 FEM 流程文本（多行），输入完成后在新行输入 'END' 并回车，或按 Ctrl+D (Unix) / Ctrl+Z (Windows) 结束。")
    lines = []
    try:
        while True:
            line = input()
            if line.strip() == 'END':
                break
            lines.append(line)
    except EOFError:
        pass

    user_text = '\n'.join(lines)
    if 'mainflow:' not in user_text:
        user_text = 'mainflow:\n' + user_text

    norm = FEMNormalizer()
    result = norm.normalize(user_text)
    print("\n--- 标准化结果 ---")
    print(result)
