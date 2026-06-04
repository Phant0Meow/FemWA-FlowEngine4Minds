#femCompiler/save_dialog.py
"""
SaveDialog.py — 对话存储模块
===============================
负责将人类发言和 AI 发言存入数据库，
自动处理 scope 注入、去重、turn 和 step_idx 管理。
"""

#from db_utils import insert_dialog_record, insert_ai_record
import threading
import queue
import json
import time

def _build_scope(action_scope, actor_info, meta_owner):
    """
    构建最终的 user_scope 和 soul_scope。
    自动注入发言者自己和 meta.owner，去重，删除 0。
    """
    user_scope = [str(x) for x in action_scope[0]] if action_scope else []
    soul_scope = [str(x) for x in action_scope[1]] if action_scope else []

    # 注入发言者自己（字符串）
    if 'user' in actor_info:
        uid = str(actor_info['user'])
        if uid not in user_scope:
            user_scope.append(uid)
    if 'soul' in actor_info and actor_info['soul'] is not None:
        sid = str(actor_info['soul'])
        if sid not in soul_scope:
            soul_scope.append(sid)

    # 注入 meta.owner（保持字符串）
    for uid in (meta_owner or []):
        uid_str = str(uid)
        if uid_str not in user_scope:
            user_scope.append(uid_str)

    # 删除无效值（空字符串、'0' 等）
    user_scope = [x for x in user_scope if x and x != '0']
    soul_scope = [x for x in soul_scope if x and x != '0']

    # 去重排序
    user_scope = sorted(set(user_scope))
    soul_scope = sorted(set(soul_scope))

    return user_scope, soul_scope
    
    
def _do_insert_dialog(session_id, turn_id, oratio_idx, user_prompt, user_id, soul_id,
                      user_scope, soul_scope, work_mode="chat", **kwargs):
    from femCompiler.db_utils import _get_conn
    conn = _get_conn()
    try:
        final_user_id_json = json.dumps(user_id) if isinstance(user_id, list) else (user_id or '[]')
        # 下行只为了调试打印，不要删除
        #print(f"[DEBUG _do_insert_dialog] final user_id={user_id!r}, json={json.dumps(user_id) if isinstance(user_id, list) else (user_id or '[]')}"),
        conn.execute("""
            INSERT INTO dialog
            (session_id, turn_id, oratio_idx, user_prompt, user_id, soul_id,
             user_scope, soul_scope, work_mode, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, turn_id, oratio_idx,
            user_prompt,
            json.dumps([str(x) for x in user_id]) if isinstance(user_id, list) else (str(user_id) if user_id else '[]'),
            soul_id or '',
            json.dumps([str(x) for x in (user_scope or [])]),
            json.dumps([str(x) for x in (soul_scope or [])]),
            work_mode,
            int(time.time()),
        ))
        conn.commit()
    finally:
        conn.close()

def _do_insert_ai(session_id, turn_id, step_idx, response, soul_id,
                  user_scope, soul_scope, model_id="", cot="", **kwargs):
    from femCompiler.db_utils import _get_conn
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO react_steps
            (session_id, turn_id, step_idx, timestamp, response, soul_id,
             user_scope, soul_scope, cot, model_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, turn_id, step_idx,
            int(time.time()),
            response,
            soul_id or '',
            json.dumps([str(x) for x in (user_scope or [])]),
            json.dumps([str(x) for x in (soul_scope or [])]),
            cot, model_id,
        ))
        conn.commit()
    finally:
        conn.close()
        
        


def save_human_turn(session_id, turn_id, oratio_idx, user_input, actor_info, meta_owner,
                    action_scope=None, is_node_prompt=False, fems_id: str = '', prompt_type='prompt'):
    """
    将人类发言或节点 prompt 入队（后台线程写入数据库）
    """
    user_scope, soul_scope = _build_scope(action_scope, actor_info, meta_owner)
    # 构建 user_id 列表
    if is_node_prompt and fems_id:
        if prompt_type == 'showprompt':
            user_id_list = [f'femshow-{fems_id}']
        else:
            user_id_list = [f'fems-{fems_id}']
        #print(f"[DEBUG save_human_turn] node mode, user_id_list={user_id_list}")
    else:
        raw_user = actor_info.get('user')
        user_id_list = [str(raw_user)] if raw_user else []
        #print(f"[DEBUG save_human_turn] normal mode, raw_user={raw_user!r}, user_id_list={user_id_list}")
    soul_id = str(actor_info['soul']) if actor_info.get('soul') and not is_node_prompt else ''


    event = save_queue.enqueue_human(
        session_id=session_id,
        turn_id=turn_id,
        oratio_idx=oratio_idx,
        user_prompt=user_input,
        user_id=user_id_list,
        soul_id=soul_id,
        user_scope=user_scope,
        soul_scope=soul_scope,
    )
    print(f"[SaveDialog] 💬 节点/人类发言已入队: session={session_id}, turn={turn_id}, oratio={oratio_idx}")
    return event


def save_ai_turn(session_id, turn_id, step_idx, response, actor_info, meta_owner,
                 model_id="", thinking="", action_scope=None):
    """
    将 AI 发言入队（后台线程写入数据库）
    """
    user_scope, soul_scope = _build_scope(action_scope, actor_info, meta_owner)
    soul_id = str(actor_info['soul']) if actor_info.get('soul') else ''

    event = save_queue.enqueue_ai(
        session_id=session_id,
        turn_id=turn_id,
        step_idx=step_idx,
        response=response,
        soul_id=soul_id,
        model_id=model_id,
        cot=thinking,
        user_scope=user_scope,
        soul_scope=soul_scope,
    )
    print(f"[SaveDialog] 🤖 AI 发言已入队: session={session_id}, turn={turn_id}, step={step_idx}")
    return event


class SaveQueue:
    def __init__(self):
        self._queue = queue.Queue()
        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _worker_loop(self):
        """不死循环：工作线程崩溃后自动重启"""
        while self._running:
            try:
                self._run()
            except Exception as e:
                import traceback
                traceback.print_exc()
                #print(f"[SaveQueue] 工作线程异常退出，3 秒后重启: {e}")
                time.sleep(3)
        
    def _enqueue_with_event(self, typ, kwargs):
        """入队一个任务，返回一个 threading.Event，任务处理完成后会 set"""
        event = threading.Event()
        self._queue.put((typ, kwargs, event))
        return event

    def _run(self):
        print("[SaveQueue] 后台线程已启动")
        while True:
            try:
                item = self._queue.get(timeout=0.1)

                if item is None:

                    break
                if len(item) == 2:
                    typ, kwargs = item
                    event = threading.Event()

                else:
                    typ, kwargs, event = item

                try:
                    self._process_item((typ, kwargs))
                except Exception as e:
                    print(f"[SaveQueue] 处理失败: {e}")
                finally:
                    event.set()

                self._queue.task_done()
            except queue.Empty:
                if not self._running:
                    break
                continue
            except Exception as e:
                print(f"[SaveQueue] 运行错误: {e}")
                import traceback
                traceback.print_exc()

    def _process_item(self, item):
        """实际写入数据库，item 是 (type, kwargs)"""
        typ, kwargs = item
        try:
            if typ == 'human':
                _do_insert_dialog(**kwargs)
            elif typ == 'ai':
                _do_insert_ai(**kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[SaveQueue] ❌ 写入失败: {e}")

    def enqueue_human(self, **kwargs):
        event = self._enqueue_with_event('human', kwargs)
        #print(f"[SaveQueue] enqueue_human: 任务已入队, event={event}")
        return event

    def enqueue_ai(self, **kwargs):
        event = self._enqueue_with_event('ai', kwargs)
        #print(f"[SaveQueue] enqueue_ai: 任务已入队, event={event}")
        return event

    def wait_empty(self, timeout=None):
        """等待队列清空后停止后台线程"""
        self._queue.join()  # 等待所有任务被处理
        self._running = False
        self._queue.put(None)  # 发送停止信号
        self._worker.join(timeout=timeout)
        #print("[SaveDialog] 所有数据已写入，后台线程已停止")

    def restart(self):
        """重新启动后台线程（用于连续运行多个任务）"""
        if not self._running:
            self._running = True
            self._worker = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker.start()

save_queue = SaveQueue()
