#femCompiler/db_utils.py
"""
db_utils.py — 数据库基础查询与建库
====================================
提供对话记录、角色、用户信息的查询接口。
数据库文件位置：{get_user_dir()}/memory/chronica.wor
"""

import sqlite3
import os
import json
from typing import List, Dict, Optional, Any
from femCompiler.FEM_config import get_db_path



def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（自动创建目录）"""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ═══════════════════════════════════════════════════════
# 建库
# ═══════════════════════════════════════════════════════

def init_database():
    """创建所有表（如果不存在）"""
    conn = _get_conn()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id     INTEGER PRIMARY KEY,
            title          TEXT DEFAULT '',
            owner          TEXT DEFAULT '',
            participants   TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS dialog (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER,
            turn_id         INTEGER,
            oratio_idx      INTEGER DEFAULT 0,
            timestamp       INTEGER DEFAULT 0,
            has_user_files  INTEGER DEFAULT 0,
            ai_steps_count  INTEGER DEFAULT 0,
            user_prompt     TEXT DEFAULT '',
            user_id         TEXT DEFAULT '',
            soul_id         TEXT DEFAULT '',
            user_scope      TEXT DEFAULT '[]',
            soul_scope      TEXT DEFAULT '[]',
            work_mode       TEXT DEFAULT 'chat'
        );

        CREATE TABLE IF NOT EXISTS files (
            file_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER,
            turn_id         INTEGER,
            file_idx        INTEGER DEFAULT 0,
            file_name       TEXT DEFAULT '',
            file_content    TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS react_steps (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER,
            turn_id         INTEGER,
            step_idx        INTEGER DEFAULT 0,
            timestamp       INTEGER DEFAULT 0,
            cot             TEXT DEFAULT '',
            response        TEXT DEFAULT '',
            tool_call       TEXT DEFAULT '',
            tool_result     TEXT DEFAULT '',
            model_id        TEXT DEFAULT '',
            soul_id         TEXT DEFAULT '',
            user_scope      TEXT DEFAULT '[]',
            soul_scope      TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS souls (
            idx             INTEGER PRIMARY KEY,
            soul_id         TEXT,
            soul_name       TEXT DEFAULT '',
            description     TEXT DEFAULT '',
            user_id         TEXT,
            created_by      TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            idx             INTEGER PRIMARY KEY,
            user_id         TEXT,
            user_name       TEXT DEFAULT '',
            password        TEXT DEFAULT '',
            profile         TEXT DEFAULT ''
        );
    """)

    conn.commit()
    conn.close()
    print(f"[db_utils] ✅ 数据库初始化完成: {get_db_path()}")


# ═══════════════════════════════════════════════════════
# Session
# ═══════════════════════════════════════════════════════

def get_max_session_id() -> int:
    """获取当前最大的 session_id"""
    conn = _get_conn()
    row = conn.execute("SELECT MAX(session_id) FROM sessions").fetchone()
    conn.close()
    return row[0] if row[0] is not None else 0


def get_or_create_session(session_id: int = None, title: str = "",
                          participants: list = None) -> int:
    """
    获取或创建 session。返回 session_id。
    如果 session_id 为 None，自动分配一个新 session（max+1）。
    """
    conn = _get_conn()
    if session_id is not None:
        row = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if row:
            conn.close()
            return session_id

    if session_id is None:
        session_id = get_max_session_id() + 1

    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, title, participants) VALUES (?, ?, ?)",
        (session_id, title, json.dumps(participants or []))
    )
    conn.commit()
    conn.close()
    print(f"[db_utils] 📝 Session {session_id} 已就绪")
    return session_id


# ═══════════════════════════════════════════════════════
# Soul
# ═══════════════════════════════════════════════════════

def get_soul_by_id(soul_id: str) -> Optional[Dict[str, Any]]:
    """根据 soul_id 查询角色信息"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT soul_id, soul_name, description FROM souls WHERE soul_id = ?",
        (str(soul_id),)
    ).fetchone()
    conn.close()
    if row:
        return {
            "soul_id": row["soul_id"],
            "soul_name": row["soul_name"],
            "description": row["description"],
        }
    print(f"[db_utils] ⚠️ 未找到 soul_id={soul_id} 的角色")
    return None


def get_soul_system_prompt(soul_id: str) -> str:
    """
    获取角色的 description 作为 system prompt 片段。
    如果角色不存在，返回空字符串。
    """
    soul = get_soul_by_id(soul_id)
    if soul:
        return soul.get("description", "")
    return ""


# ═══════════════════════════════════════════════════════
# User
# ═══════════════════════════════════════════════════════

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """根据 user_id 查询用户信息"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT user_id, user_name, profile FROM users WHERE user_id = ?",
        (str(user_id),)
    ).fetchone()
    conn.close()
    if row:
        return {
            "user_id": row["user_id"],
            "user_name": row["user_name"],
            "profile": row["profile"],
        }
    print(f"[db_utils] ⚠️ 未找到 user_id={user_id} 的用户")
    return None


def get_user_profile(user_id: str) -> str:
    """
    获取用户的 profile 文本。
    如果用户不存在，返回空字符串。
    """
    user = get_user_by_id(str(user_id))
    if user:
        return user.get("profile", "")
    return ""


def get_user_password(user_id: str) -> Optional[str]:
    """根据 user_id 查询用户密码"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT password FROM users WHERE user_id = ?",
        (str(user_id),)
    ).fetchone()
    conn.close()
    if row:
        return row["password"]
    return None


def check_soul_id_exists(soul_id: str) -> bool:
    """检查 soul_id 是否已存在"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM souls WHERE soul_id = ?",
        (str(soul_id),)
    ).fetchone()
    conn.close()
    return row is not None


def check_user_id_exists(user_id: str) -> bool:
    """检查 user_id 是否已存在"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM users WHERE user_id = ?",
        (str(user_id),)
    ).fetchone()
    conn.close()
    return row is not None


def create_soul(soul_id: str, soul_name: str, description: str, user_id: str) -> None:
    """创建新的 soul 条目，created_by 自动填入 user_id"""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO souls (soul_id, soul_name, description, user_id, created_by) VALUES (?, ?, ?, ?, ?)",
        (soul_id, soul_name, description, user_id, user_id)
    )
    conn.commit()
    conn.close()
    print(f"[db_utils] ✅ 新建 soul: soul_id={soul_id}, soul_name={soul_name}, user_id={user_id}")


def create_user(user_id: str, password: str = "") -> None:
    """创建新的 user 条目（如果不存在）"""
    conn = _get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, password) VALUES (?, ?)",
        (user_id, password)
    )
    conn.commit()
    conn.close()
    print(f"[db_utils] ✅ 新建 user: user_id={user_id}")


# ═══════════════════════════════════════════════════════
# 对话记录查询（Scope 过滤）
# ═══════════════════════════════════════════════════════

def insert_dialog_record(
    session_id: int,
    turn_id: int,
    user_prompt: str = "",
    user_id: int = None,
    soul_id: int = None,
    user_scope: List[int] = None,
    soul_scope: List[int] = None,
    work_mode: str = "chat",
    **kwargs,
) -> None:
    """插入一条人类发言记录"""
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO dialog
        (session_id, turn_id, user_prompt, user_id, soul_id,
         user_scope, soul_scope, work_mode, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, turn_id, user_prompt,
        user_id, soul_id,
        json.dumps(user_scope or []),
        json.dumps(soul_scope or []),
        work_mode,
        int(__import__('time').time()),
    ))
    conn.commit()
    conn.close()


def insert_ai_record(
    session_id: int,
    turn_id: int,
    response: str = "",
    soul_id: int = None,
    user_scope: List[int] = None,
    soul_scope: List[int] = None,
    step_idx: int = 0,
    cot: str = "",
    model_id: str = "",
    **kwargs,
) -> None:
    """插入一条 AI 回复记录"""
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO react_steps
        (session_id, turn_id, step_idx, response, soul_id,
         user_scope, soul_scope, cot, model_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, turn_id, step_idx, response,
        soul_id,
        json.dumps(user_scope or []),
        json.dumps(soul_scope or []),
        cot, model_id,
    ))
    conn.commit()
    conn.close()


def get_next_turn_id(session_id: int) -> int:
    """获取指定 session 的下一个 turn_id"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT MAX(turn_id) FROM dialog WHERE session_id = ?",
        (session_id,)
    ).fetchone()
    conn.close()
    return (row[0] or 0) + 1


def session_exists(session_id: int) -> bool:
    """检查 session 是否存在"""
    conn = _get_conn()
    row = conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return row is not None
    
    
'''
def _parse_scope_field(scope_str: str) -> List[int]:
    """解析数据库中存储的 scope 字段（JSON 数组字符串）"""
    try:
        return json.loads(scope_str) if scope_str else []
    except (json.JSONDecodeError, TypeError):
        return []


def _ids_match_scope(scope_list: List[int], target_ids: List[int]) -> bool:
    """
    检查 target_ids 中是否有任意一个 id 出现在 scope_list 中。
    scope_list 全部为正数。
    """
    if not scope_list or not target_ids:
        return False
    return bool(set(scope_list) & set(target_ids))


def get_records_visible_to(
    user_ids: List[int] = None,
    soul_ids: List[int] = None,
    session_id: int = None,
    include_ai: bool = True,
    max_turns: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    获取指定 user 或 soul 可见的对话记录。
    返回按 (session_id, turn_id) 排序的记录列表。
    
    参数：
        user_ids: 需要匹配的 user_id 列表（匹配 user_scope）
        soul_ids: 需要匹配的 soul_id 列表（匹配 soul_scope）
        session_id: 限定 session，None 表示所有 session
        include_ai: 是否包含 react_steps 记录
        max_turns: 最多返回多少轮
        offset: 偏移量
    """
    user_ids = user_ids or []
    soul_ids = soul_ids or []
    
    conn = _get_conn()
    results = []

    # 1. 查询 dialog 表
    query = """
        SELECT session_id, turn_id, user_prompt AS content, 
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
    query += " ORDER BY session_id, turn_id DESC"
    query += f" LIMIT {max_turns + offset}"

    cursor = conn.execute(query, params)
    for row in cursor:
        user_scope = _parse_scope_field(row["user_scope"])
        soul_scope = _parse_scope_field(row["soul_scope"])
        
        if user_ids and _ids_match_scope(user_scope, user_ids):
            results.append(dict(row))
        elif soul_ids and _ids_match_scope(soul_scope, soul_ids):
            results.append(dict(row))

    # 2. 查询 react_steps 表（如果需要）
    if include_ai:
        query2 = """
            SELECT session_id, turn_id, response AS content,
                   step_idx, soul_id, user_scope, soul_scope,
                   'ai' AS source
            FROM react_steps
        """
        if conditions:
            query2 += " WHERE " + " AND ".join(conditions)
        query2 += " ORDER BY session_id, turn_id, step_idx DESC"
        query2 += f" LIMIT {max_turns * 5 + offset}"  # AI 可能有多个 step

        cursor2 = conn.execute(query2, params)
        for row in cursor2:
            user_scope = _parse_scope_field(row["user_scope"])
            soul_scope = _parse_scope_field(row["soul_scope"])
            
            if user_ids and _ids_match_scope(user_scope, user_ids):
                results.append(dict(row))
            elif soul_ids and _ids_match_scope(soul_scope, soul_ids):
                results.append(dict(row))

    conn.close()

    # 去重并排序
    seen = set()
    unique_results = []
    for r in sorted(results, key=lambda x: (x.get("session_id", 0), x.get("turn_id", 0)), reverse=True):
        key = (r["session_id"], r.get("turn_id", 0), r.get("step_idx", -1), r["source"])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    # 分页
    return unique_results[offset:offset + max_turns]


def get_session_context(
    session_id: int,
    user_ids: List[str] = None,
    soul_ids: List[str] = None,
    max_turns: int = 20,
    exclude_turn_id: int = None,
    exclude_oratio_idx: int = None,
) -> str:
    records = get_records_visible_to(
        user_ids=user_ids,
        soul_ids=soul_ids,
        session_id=session_id,
        include_ai=True,
        max_turns=max_turns,
    )
    if not records:
        return "（暂无对话记录）"

    # 排除指定的当前 prompt 记录（精确匹配 session、turn、oratio）
    if exclude_turn_id is not None and exclude_oratio_idx is not None:
        records = [
            r for r in records
            if not (
                r.get("source") == "human"
                and r.get("session_id") == session_id
                and r.get("turn_id") == exclude_turn_id
                and r.get("oratio_idx") == exclude_oratio_idx
            )
        ]

    # 按时间排序：同 turn 内 human 在前，AI 在后
    records.sort(key=lambda r: (
        r.get("turn_id", 0),
        r.get("oratio_idx", 0) if r.get("source") == "human" else r.get("step_idx", 9999)
    ))

    lines = []
    for r in records:
        source = r.get("source", "?")
        content = r.get("content", "")
        turn = r.get("turn_id", "?")
        if source == "human":
            lines.append(f"[第{turn}轮 用户]: {content}")
        else:
            soul_id = r.get("soul_id", "?")
            lines.append(f"[第{turn}轮 AI(soul={soul_id})]: {content}")
    return "\n".join(lines)


'''
