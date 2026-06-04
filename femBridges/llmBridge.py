"""
femBridge/llmBridge.py — FEM 与 MiMo API 的桥接（原 DeepSeek 版）
==============================================================
自动加载项目根目录的 .env 文件，调用 MiMo 模型并返回完整回答。
现改为调用同目录下的 mimo.py 中的 stream_chat，接口与 deepseek 版完全兼容。
"""

import os
import threading
import sys

# ── 0. 加载根目录的 .env ──
def _load_dotenv():
    """自动从项目根目录加载 .env（带简单降级）"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    dotenv_path = os.path.join(root_dir, ".env")

    if not os.path.exists(dotenv_path):
        print(f"[llmBridge] ⚠️ 未找到 .env 文件: {dotenv_path}")
        return

    # 先尝试 python-dotenv 库
    #try:
    #    from dotenv import load_dotenv
    #    load_dotenv(dotenv_path)
    #    return
    #except ImportError:
    #    print("[llmBridge] ℹ️ 未安装 python-dotenv，使用简易解析")

    # 简易解析器（兼容等号前后空格）
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                #if line and not line.startswith("#"):
                #    print(f"[llmBridge] ⚠️ 忽略格式不正确的行: {line}")
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value

    # 打印最终加载的关键变量（部分隐藏）
    if "MIMO_API_KEY" in os.environ:
        print("[llmBridge] 🏠 已从 .env 加载 MIMO_API_KEY")
    # 如果 .env 里没有，也不报错，因为可能通过浏览器传入

_load_dotenv()

def call_ai_with_blocks(
    blocks: dict,
    model: str = "default",
    stream_callback=None,
    user_api_key: str = None,
    user_api_provider: str = None,
    user_api_url: str = None,
    stop_event: threading.Event = None,
) -> str:
    """
    输入：blocks 字典
    输出：AI 完整回复文本，同时可通过 stream_callback 实现流式输出
    """

    # ── 0.5 确保当前线程有事件循环（线程池内需要）──
    import asyncio as _asyncio
    try:
        _asyncio.get_running_loop()
    except RuntimeError:
        _asyncio.set_event_loop(_asyncio.new_event_loop())

    # ── 1. 组装 prompt ──
    try:
        from prompt_assembler import assemble
        system_prompt, user_prompt = assemble(blocks)
    except ImportError:
        system_prompt = "\n\n".join(filter(None, [
            blocks.get('basic_safety', ''),
            blocks.get('basic_output', ''),
            blocks.get('soul', ''),
            blocks.get('user_info', ''),
        ]))
        context = blocks.get('context', '')
        prompt = blocks.get('prompt', '')
        memory = blocks.get('memory', '')

        parts = [context, prompt]
        if memory:
            parts.append("---\n[回忆]\n根据以上情况，你偶然回忆起了以下记忆，可能有用也可能无用：")
            parts.append(memory)
            parts.append(prompt)  # 提醒当前任务

        user_prompt = "\n\n".join(filter(None, parts))

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # ── 调试：打印发给 LLM 的完整内容 ──
    #print("\n" + "=" * 60)
    #print("📤 发送给 LLM 的完整消息：")
    #print("=" * 60)
    #print("--- SYSTEM ---")
    #print(messages[0]["content"])
    #print("--- USER ---")
    #print(messages[1]["content"])
    #print("=" * 60 + "\n")

    # ── 2. 确定 API 密钥与提供者 ──
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    if user_api_key:
        print("[llmBridge] 🌐 使用浏览器传入的 API Key")
        api_key = user_api_key
        provider = user_api_provider or 'mimo'
        
        # 1. 确定 api_url
        if user_api_url:
            api_url = user_api_url
        elif provider == 'deepseek':
            api_url = "https://api.deepseek.com/v1/chat/completions"
        else:
            api_url = "https://api.xiaomimimo.com/v1/chat/completions"
        
        # 2. 根据 provider 导入 stream_chat（确保一定被赋值）
        if provider == 'deepseek':
            try:
                from deepseek import stream_chat
            except ImportError:
                print("[llmBridge] ❌ 无法导入 deepseek.stream_chat")
                return None
        if provider == 'mimo':
            try:
                from mimo import stream_chat
            except ImportError:
                print("[llmBridge] ❌ 无法导入 mimo.stream_chat")
                return None
    else:
        api_key = os.environ.get("MIMO_API_KEY")
        if not api_key:
            print("[llmBridge] ❌ 未提供 API Key，且环境变量 MIMO_API_KEY 也为空")
            return None
        print("[llmBridge] 🏠 使用本地 .env 中的 API Key")
        api_url = os.environ.get(
            "MIMO_API_URL",
            "https://api.xiaomimimo.com/v1/chat/completions"
        )
        try:
            from mimo import stream_chat
        except ImportError:
            print("[llmBridge] ❌ 无法导入 mimo.stream_chat")
            return None

    # 深度思考开关逻辑：model 非 default 时开启
    native_params = {"deep_think": 1 if model != "default" else -1}

    # ── 4. 调用流式生成器 ──
    try:
        print(f"[llmBridge] 🔗 实际请求地址: {api_url}")
        generator = stream_chat(
            api_key=api_key,
            api_url=api_url,
            messages=messages,
            system_prompt=system_prompt,
            native_params=native_params,
            sampling_params={},
        )
    except Exception as e:
        print(f"[llmBridge] ❌ 启动流式请求失败: {e}")
        return None

    # ── 5. 流式接收并处理 ──
    answer = ""
    thinking = ""
    response_started = False

    try:
        for chunk in generator:
            # 检查停止信号
            if stop_event and stop_event.is_set():
                print("[llmBridge] 收到停止信号，中断流式输出")
                break

            if isinstance(chunk, dict):
                if chunk.get("type") == "response_start":
                    response_started = True
                continue

            if isinstance(chunk, str):
                if not response_started and chunk.strip():
                    response_started = True
                if response_started:
                    answer += chunk
                    if stream_callback:
                        stream_callback(chunk)
                else:
                    thinking += chunk

        # ── 6. 日志输出 ──
        soul_name = ""
        actor_info = blocks.get('_actor_info', {})
        if actor_info and 'soul' in actor_info:
            try:
                from femCompiler.db_utils import get_soul_by_id
                soul = get_soul_by_id(str(actor_info['soul']))
                if soul:
                    soul_name = soul.get('soul_name', '')
            except Exception:
                pass
        if not soul_name:
            soul_block = blocks.get('soul', '')
            import re
            match = re.search(r'名字[：:]\s*(\S+)', soul_block)
            if match:
                soul_name = match.group(1)
        tag = soul_name if soul_name else "AI"

        #print(f"[{tag}]:")
        #if thinking:
        #    print("-思考-:")
        #    print(thinking)
        #    print("-回答-:")
        #print(answer)

        return answer #等等这个不对啊，cot不return吗？

    except Exception as e:
        print(f"[llmBridge] ❌ 流式请求失败: {e}")
        return None
