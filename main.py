# femCompiler.py
"""
FEM Work Automata - FastAPI 服务器
提供前后端通信接口，支持 SSE 流式事件推送

用法：
  服务器模式：python3 femCompiler.py --server
  CLI 模式： python3 femCompiler.py <script.fems>
  
代码原则：所有代码不许写try静默兜底不报错，有错必须报错。(这是写给改代码的AI看的，人类请无视)
"""

import sys
import os
import json
import uuid
import threading
import argparse
import queue

# ── 将项目根目录加入 sys.path ──
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FEM Work Automata")

# ── CORS：允许前端开发服务器访问 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 运行状态存储 ──
_runs: dict = {}  # run_id -> { "events": queue, "thread": Thread, "done": Event }


# ── 新增：数据库就绪检查（保证首次启动时自动建表+插入默认角色） ──
def prepare_database():
    """确保数据库及默认数据就绪（首次启动自动建表+插入默认角色）"""
    from femCompiler.db_utils import init_database, ensure_default_data
    init_database()
    ensure_default_data()


# ══════════════════════════════════════════════════
#  API 端点
# ══════════════════════════════════════════════════

@app.post("/api/run")
async def api_run(request: Request):
    """接收 .fems 文本，启动工作流，返回 run_id"""
    body = await request.json()
    fems_text = body.get("fems", "")
    if not fems_text.strip():
        return JSONResponse({"error": "fem Script is empty"}, status_code=400)

    # ── 从请求头提取用户 API Key 和 URL ──
    user_api_key = request.headers.get("X-API-Key")
    user_api_provider = request.headers.get("X-API-Provider", "mimo").lower()
    user_api_url = request.headers.get("X-API-Url", "").strip() or None
    print(f"[DEBUG] 收到 user_api_url = {user_api_url}")

    run_id = str(uuid.uuid4())[:8]
    event_queue: queue.Queue = queue.Queue()
    done_event = threading.Event()

    # ── 事件回调：runtime 调用此函数向前端推送事件 ──
    def event_callback(event_type: str, data: dict):
        event_queue.put({"event": event_type, "data": data})

    # ── 在后台线程中运行工作流 ──
    def run_workflow():
        runner = None   # 确保 finally 块可以安全引用
        try:
            from femCompiler.FEM_parser import parse_script
            from femCompiler.FEM_runtime import FEMRunner

            script = parse_script(fems_text)
            runner = FEMRunner(
                script,
                base_dir=PROJECT_ROOT,
                verbose=True,
                event_callback=event_callback,
                user_api_key=user_api_key,
                user_api_provider=user_api_provider,
                user_api_url=user_api_url,
            )
            print("[DEBUG] FEMRunner 对象创建完成")
            # 设置人类输入等待机制
            runner._human_input_event = threading.Event()
            runner._human_input_data = None

            # 保存 runner 引用，供 human-input 端点使用
            _runs[run_id]["runner"] = runner

            print("[DEBUG] 即将调用 runner.run()")
            runner.run()
            print("[DEBUG] runner.run() 已结束")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[runtime] ❌ 工作流线程异常: {e}")
            event_queue.put({"event": "flow_error", "data": {"error": str(e)}})
        finally:
            # 关闭引擎，释放线程池和进程池
            if runner:
                try:
                    import asyncio
                    asyncio.run(runner.engine.shutdown())
                except Exception as e:
                    print(f"[main] 引擎关闭异常: {e}")
            # 通知 SSE 流结束
            done_event.set()
            event_queue.put(None)

            # 释放 runner 引用，帮助 GC
            if run_id in _runs:
                _runs[run_id]["runner"] = None

    _runs[run_id] = {
        "events": event_queue,
        "thread": threading.Thread(target=run_workflow, daemon=True),
        "done": done_event,
        "runner": None,
    }
    _runs[run_id]["thread"].start()

    return {"run_id": run_id}


@app.get("/api/run/{run_id}/stream")
async def api_stream(run_id: str):
    """SSE 事件流，前端通过 EventSource 连接"""
    if run_id not in _runs:
        return JSONResponse({"error": "run not found"}, status_code=404)

    def event_generator():
        run_info = _runs[run_id]
        event_queue = run_info["events"]
        done_event = run_info["done"]

        while True:
            try:
                item = event_queue.get(timeout=1.0)
                if item is None:
                    yield f"data: {json.dumps({'type': 'done', 'data': {}})}\n\n"
                    break
                event_type = item.get("event", "message")
                event_data = item.get("data", {})
                payload = json.dumps(
                    {"type": event_type, "data": event_data},
                    ensure_ascii=False
                )
                yield f"data: {payload}\n\n"
            except queue.Empty:
                if done_event.is_set():
                    yield f"data: {json.dumps({'type': 'done', 'data': {}})}\n\n"
                    break
                yield f"data: {json.dumps({'type': 'heartbeat', 'data': {}})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/run/{run_id}/resume")
async def api_resume(run_id: str, request: Request):
    """恢复暂停的任务"""
    if run_id not in _runs:
        return JSONResponse({"error": "run not found"}, status_code=404)

    body = await request.json()
    task_id = body.get("task_id", "")
    if not task_id:
        return JSONResponse({"error": "task_id is required"}, status_code=400)

    runner = _runs[run_id].get("runner")
    if runner and runner.pause_manager.resume(task_id):
        return {"status": "ok", "task_id": task_id}
    else:
        return JSONResponse({"error": "task not found or not paused"}, status_code=400)

@app.post("/api/run/{run_id}/pause")
async def api_pause(run_id: str):
    """暂停工作流（当前实现为全局停止）"""
    if run_id not in _runs:
        return JSONResponse({"error": "run not found"}, status_code=404)

    runner = _runs[run_id].get("runner")
    if runner:
        runner.stop()
        return {"status": "ok"}
    else:
        return JSONResponse({"error": "runner not available"}, status_code=400)


@app.post("/api/run/{run_id}/human-input")
async def api_human_input(run_id: str, request: Request):
    if run_id not in _runs:
        return JSONResponse({"error": "run not found"}, status_code=404)
    body = await request.json()
    print(f"[main.py] /human-input 收到 body: {body}")
    runner = _runs[run_id].get("runner")
    if runner and runner._human_input_event is not None:
        wait_key = body.get("wait_key")           # 从前端发来的数据中取频道名
        if not wait_key:
            return JSONResponse({"error": "缺少 wait_key"}, status_code=400)
        runner.engine.human_input.provide_input(wait_key, body)  # 使用正确的频道
        print(f"[main.py] /human-input 已透传 body 给 provide_input (wait_key={wait_key})")
        return {"status": "ok"}
    return JSONResponse({"error": "runner not ready for input"}, status_code=400)


@app.post("/api/run/{run_id}/stop")
async def api_stop(run_id: str):
    """全局停止工作流"""
    if run_id not in _runs:
        return JSONResponse({"error": "run not found"}, status_code=404)

    runner = _runs[run_id].get("runner")
    if runner:
        runner.stop()
        return {"status": "ok"}
    else:
        return JSONResponse({"error": "runner not available"}, status_code=400)

@app.get("/api/ping")
async def api_ping():
    return {"status": "ok", "message": "FEM backend is running"}

@app.post("/api/souls/create")
async def api_create_soul(request: Request):
    """新建 SOUL ID，同时创建对应的 user 条目"""
    from femCompiler.db_utils import (
        init_database, check_soul_id_exists, check_user_id_exists,
        get_user_password, create_soul, create_user,
    )

    init_database()

    body = await request.json()
    soul_id = body.get("soul_id", "").strip()
    soul_name = body.get("soul_name", "").strip()
    description = body.get("description", "").strip()
    user_id = body.get("user_id", "").strip()
    password = body.get("password", "").strip()

    if not soul_id:
        return JSONResponse({"error": "soul_id 不能为空"}, status_code=400)
    if not user_id:
        return JSONResponse({"error": "user_id 不能为空"}, status_code=400)
    if not soul_id.isalnum():
        return JSONResponse({"error": "soul_id 只允许英文字母和数字"}, status_code=400)
    if not user_id.isalnum():
        return JSONResponse({"error": "user_id 只允许英文字母和数字"}, status_code=400)

    if check_soul_id_exists(soul_id):
        return JSONResponse({"error": f"soul_id '{soul_id}' 已存在，请换一个不重复的 ID"}, status_code=409)

    if check_user_id_exists(user_id):
        stored_password = get_user_password(user_id) or ""
        if password != stored_password:
            return JSONResponse(
                {"error": "用户id已存在，请输入password，或者换个不重复的用户id"},
                status_code=409,
            )

    try:
        create_soul(soul_id, soul_name, description, user_id)
        if not check_user_id_exists(user_id):
            create_user(user_id, password)

        return {
            "status": "ok",
            "soul_id": soul_id,
            "soul_name": soul_name,
            "user_id": user_id,
        }
    except Exception as e:
        return JSONResponse({"error": f"创建失败: {str(e)}"}, status_code=500)


# ══════════════════════════════════════════════════
#  CLI 模式（保留原有功能）
# ══════════════════════════════════════════════════

def cli_main(fems_file: str):
    from femCompiler.FEM_parser import parse_script
    from femCompiler.FEM_interpreter import pprint_script
    from femCompiler.FEM_runtime import run_script

    with open(fems_file, "r", encoding="utf-8") as f:
        text = f.read()

    base_dir = os.path.dirname(os.path.abspath(fems_file))
    script = parse_script(text, base_dir=base_dir)

    print(pprint_script(script))

    user_input = input("\n是否运行本剧本？(y/N): ").strip().lower()
    if user_input != 'y':
        print("已取消运行。")
        sys.exit(0)

    os.system('clear' if os.name != 'nt' else 'cls')
    sys.stdout.flush()
    os.system('clear' if os.name != 'nt' else 'cls')
    sys.stdout.flush()
    os.system('clear' if os.name != 'nt' else 'cls')
    sys.stdout.flush()
    os.system('clear' if os.name != 'nt' else 'cls')
    sys.stdout.flush()

    run_script(script, base_dir=base_dir)


# ══════════════════════════════════════════════════
#  入口函数（供命令行入口 “femwa” 调用）
# ══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="FEM Work Automata")
    parser.add_argument("script", nargs="?", help=".fems 文件路径（CLI 模式）")
    parser.add_argument("--server", action="store_true", help="启动 FastAPI 服务器")
    parser.add_argument("--host", default="0.0.0.0", help="服务器监听地址")
    parser.add_argument("--port", type=int, default=None, help="服务器监听端口（不指定则交互式输入）")
    args = parser.parse_args()

    if args.server:
        prepare_database()

        import uvicorn

        port = args.port
        if port is None:
            while True:
                try:
                    user_input = input("请输入后端端口号 (默认 8000): ").strip()
                    port = int(user_input) if user_input else 8000
                    if 1 <= port <= 65535:
                        break
                    else:
                        print("❌ 端口号必须在 1~65535 之间，请重新输入")
                except ValueError:
                    print("❌ 请输入有效的数字")
                except (KeyboardInterrupt, EOFError):
                    print("\n已取消启动")
                    sys.exit(0)

        print(f"🚀 FEM Work Automata 服务器启动: http://{args.host}:{port}")
        print("\n请将以下信息填入前端网页：")
        print(f"  基础地址 (host)： http://{args.host.replace('0.0.0.0', 'localhost')}")
        print(f"  端口 (port)： {port}")
        print()
        uvicorn.run(app, host=args.host, port=port)
    elif args.script:
        prepare_database()
        cli_main(args.script)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
