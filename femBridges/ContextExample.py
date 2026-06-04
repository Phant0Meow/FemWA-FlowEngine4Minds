"""
bridges/ContextExample.py — 默认上下文提取实现
===============================================
从数据库提取当前 session 的对话上下文，排除当前 prompt。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from femCompiler.db_utils import _get_conn
from femCompiler.FEM_scope_resolver import parse_scope_field, ids_match_scope
from typing import List, Optional, Dict, Any


def _get_records_visible_to(
    user_ids: List[str] = None,
    soul_ids: List[str] = None,
    session_id: int = None,
    include_ai: bool = True,
    max_turns: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """获取指定 user 或 soul 可见的对话记录（仅当前 session）"""
    user_ids = user_ids or []
    soul_ids = soul_ids or []
    conn = _get_conn()
    results = []

    query = """
        SELECT session_id, turn_id, oratio_idx, user_prompt AS content,
               timestamp, user_id, soul_id, user_scope, soul_scope,
               'human' AS source
        FROM dialog
    """
    conditions = []
    params = []

    if session_id is not None:
        conditions.append("session_id = ?")
        params.append(session_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY session_id, turn_id, oratio_idx DESC"

    cursor = conn.execute(query, params)
    for row in cursor:
        user_scope = parse_scope_field(row["user_scope"] or "[]")
        soul_scope = parse_scope_field(row["soul_scope"] or "[]")
        match_user = user_ids and ids_match_scope(user_scope, user_ids)
        match_soul = soul_ids and ids_match_scope(soul_scope, soul_ids)
        ##print(f"[DEBUG dialog row] source={row['source']}, turn={row['turn_id']}, "
        #      f"user_scope={user_scope}, soul_scope={soul_scope}, "
        #      f"match_user={match_user}, match_soul={match_soul}")
        if match_user or match_soul:
            results.append(dict(row))

    if include_ai:
        query2 = """
            SELECT session_id, turn_id, step_idx, response AS content,
                   timestamp, soul_id, user_scope, soul_scope,
                   'ai' AS source
            FROM react_steps
        """
        if conditions:
            query2 += " WHERE " + " AND ".join(conditions)
        query2 += " ORDER BY session_id, turn_id, step_idx DESC"

        cursor2 = conn.execute(query2, params)
        for row in cursor2:
            user_scope = parse_scope_field(row["user_scope"] or "[]")
            soul_scope = parse_scope_field(row["soul_scope"] or "[]")
            match_user = user_ids and ids_match_scope(user_scope, user_ids)
            match_soul = soul_ids and ids_match_scope(soul_scope, soul_ids)
            ##print(f"[DEBUG react row] source={row['source']}, turn={row['turn_id']}, "
            #      f"user_scope={user_scope}, soul_scope={soul_scope}, "
            #      f"match_user={match_user}, match_soul={match_soul}")
            if match_user or match_soul:
                results.append(dict(row))

    conn.close()

    # 按时间戳或 turn_id + idx 降序排列（最近的在前）
    results.sort(key=lambda r: (
        r.get("turn_id", 0),
        r.get("oratio_idx", 0) if r.get("source") == "human" else r.get("step_idx", 0)
    ), reverse=True)
    # 去重
    seen = set()
    unique = []
    for r in results:
        key = (r["session_id"], r["turn_id"], r.get("oratio_idx", -1) if r["source"] == "human" else r.get("step_idx", -1), r["source"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    # 截断到 max_turns
    return unique


def get_session_context(
    session_id: int,
    user_ids: List[str] = None,
    soul_ids: List[str] = None,
) -> str:
    """获取当前 session 的完整对话上下文"""
    records = _get_records_visible_to(
        user_ids=user_ids,
        soul_ids=soul_ids,
        session_id=session_id,
        include_ai=True,
        max_turns=999999,  # 足够大的数，取所有记录
    )
    ##print(f"[DEBUG context] 检索到 {len(records)} 条可见记录")
    #for r in records[:3]:
        ##print(f"  - source={r['source']}, turn={r.get('turn_id')}, content={r.get('content','')[:50]!r}")
    if not records:
        return ""

    # 按时间戳排序，保证真实的时间顺序；同一秒内用 turn_id + idx 做稳定排序
    records.sort(key=lambda r: (
        r.get("timestamp", 0),
        r.get("turn_id", 0),
        r.get("oratio_idx", 0) if r.get("source") == "human" else r.get("step_idx", 0)
    ))
    ##print(f"[DEBUG final records count] {len(records)}")
    #for r in records:
        ##print(f"  - source={r['source']}, turn={r.get('turn_id')}, content={r.get('content','')[:80]!r}")

    from femCompiler.db_utils import get_soul_by_id, get_user_by_id
    import json
    name_cache = {}

    def _parse_first_id(raw):
        """从可能是 JSON 数组的字段中提取第一个 ID 字符串"""
        if not raw:
            return ""
        if isinstance(raw, list):
            return str(raw[0]) if raw else ""
        if isinstance(raw, str):
            # 尝试 JSON 解析
            s = raw.strip()
            if s.startswith('[') and s.endswith(']'):
                try:
                    arr = json.loads(s)
                    if isinstance(arr, list) and arr:
                        return str(arr[0])
                except Exception:
                    pass
            return s
        return str(raw)

    def get_name(record):
        source = record.get("source")
        if source == "human":
            uid = _parse_first_id(record.get("user_id"))
            if not uid:
                return "用户"
            # 特殊处理：user_id 为 "0" 时，使用该记录 soul_id 对应的灵魂名称
            if uid == "0":
                sid = _parse_first_id(record.get("soul_id", ""))
                if sid:
                    if sid not in name_cache:
                        soul = get_soul_by_id(sid)
                        name_cache[sid] = soul.get("soul_name", sid) if soul else sid
                    return name_cache[sid]
                else:
                    return "AI"
            if uid.startswith('femshow-'):
                return "[节点提醒]"
            if uid.startswith('fems-'):
                return None
            if uid not in name_cache:
                user = get_user_by_id(uid)
                name_cache[uid] = user.get("user_name", uid) if user else uid
            return name_cache[uid]
        else:  # ai
            sid = _parse_first_id(record.get("soul_id"))
            if not sid:
                return "AI"
            if sid not in name_cache:
                soul = get_soul_by_id(sid)
                name_cache[sid] = soul.get("soul_name", sid) if soul else sid
            return name_cache[sid]

    lines = []
    for r in records:
        name = get_name(r)
        if name is None:
            continue
        content = r.get("content", "")
        lines.append(f"[{name}]：\n{content}")
    return "\n\n".join(lines)


def findThisSession(
    session: int,
    actor_info: dict,
) -> str:
    """默认 context 提取入口（返回全部上下文）"""
    ##print(f"[ContextExample] 📖 提取 session={session} 的完整上下文")
    user_ids = []
    soul_ids = []
    if "user" in actor_info:
        user_ids.append(str(actor_info["user"]))
    if "soul" in actor_info:
        soul_ids.append(str(actor_info["soul"]))

    #print(f"[ContextExample] 查询参数: session={session}, user_ids={user_ids}, soul_ids={soul_ids}")

    context = get_session_context(
        session_id=session,
        user_ids=user_ids if user_ids else None,
        soul_ids=soul_ids if soul_ids else None,
    )
    ##print(f"[ContextExample] ✅ 上下文提取完成，长度: {len(context)} 字符")
    #if context:
    #    #print(f"[ContextExample] 内容预览:\n{context[:500]}")
    return context
