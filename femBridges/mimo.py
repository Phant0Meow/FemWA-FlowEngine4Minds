"""
================================================================================
MiMo Provider - 小米 MiMo 模型流式输出适配器
（接口与 deepseek.py 完全对齐）
================================================================================
"""

import requests
import json


def stream_chat(
    api_key: str,
    api_url: str,
    messages,                 # 上游组装好的消息列表
    system_prompt: str = "",
    native_params: dict = None,         # V2 统一参数字典
    sampling_params: dict = None,       # 采样参数字典
    **kwargs,
):
    """
    使用 requests 调用 MiMo API，流式输出，支持深度思考控制。
    接口及流式输出协议与 deepseek.py 完全一致。

    Args:
        api_key: MiMo API 密钥
        api_url: MiMo API 端点
        messages: 上游已组装好的消息列表
        system_prompt: 备用系统提示词（通常 messages 中已包含）
        native_params: 仅支持 deep_think (1=开启, -1=关闭)
        sampling_params: temperature / top_p / frequency_penalty
    """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # V2 参数解析：仅提取 deep_think
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if native_params is None:
        native_params = {}

    _deepthink = False
    if "deep_think" in native_params:
        if native_params["deep_think"] == 1:
            _deepthink = True
            #print("[mimo.py] 🧠 深度思考模式: 开启")
        elif native_params["deep_think"] == -1:
            _deepthink = False
            #print("[mimo.py] 🧠 深度思考模式: 关闭")
    #else:
        #print("[mimo.py] 🧠 深度思考模式: 关闭 (默认)")

    unsupported_keys = set(native_params.keys()) - {"deep_think"}
    #if unsupported_keys:
        #print(f"[mimo.py] ⚠️ 不支持的 native_params 键 (将忽略): {unsupported_keys}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # ✅ 消息格式化：每个消息补全 "type": "text"（与 DeepSeek 一致）
    formatted_messages = []
    for msg in messages:
        new_msg = msg.copy() if isinstance(msg, dict) else {"role": "user", "content": str(msg)}
        if "type" not in new_msg:
            new_msg["type"] = "text"
        formatted_messages.append(new_msg)

    model = "mimo-v2.5-pro"

    # 🆕 采样参数（默认值与 DeepSeek 对齐）
    sp = sampling_params or {}
    temperature = sp.get("temperature", 1.0)
    top_p = sp.get("top_p", 1.0)
    frequency_penalty = sp.get("frequency_penalty", 0.0)

    # 构建请求体
    data = {
        "model": model,
        "messages": formatted_messages,
        "stream": True,
        "temperature": temperature,
        "top_p": top_p,
        "frequency_penalty": frequency_penalty,
        "thinking": {
            "type": "enabled" if _deepthink else "disabled"
        }
    }

    # 发送请求
    response = requests.post(api_url, headers=headers, json=data, stream=True)
    response.raise_for_status()

    #print("\n--- 流式回答 (MiMo) ---")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 状态变量：控制阶段标记
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    cot_started = False
    cot_ended = False
    response_started = False

    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: '):
                chunk_str = decoded[6:]
                if chunk_str == '[DONE]':
                    if cot_started and not cot_ended:
                        yield {"type": "cot_end"}
                        #print("\n[mimo.py] 🟡 补发 COT_END")
                    #print("\n--- 回答结束 ---")
                    break
                try:
                    chunk = json.loads(chunk_str)
                    delta = chunk['choices'][0].get('delta', {})

                    reasoning = delta.get('reasoning_content')
                    content = delta.get('content')

                    # ── 处理思考内容 ──
                    if reasoning:
                        if not cot_started:
                            yield {"type": "cot_start"}
                            #print("\n[mimo.py] 🟢 发送 COT_START")
                            cot_started = True
                        yield reasoning
                        #print(reasoning, end='', flush=True)

                    # ── 处理正式回答 ──
                    if content:
                        if cot_started and not cot_ended:
                            yield {"type": "cot_end"}
                            #print("\n[mimo.py] 🟡 发送 COT_END")
                            cot_ended = True
                            yield {"type": "response_start"}
                            #print("[mimo.py] 🟢 发送 RESPONSE_START")
                            response_started = True
                        elif not response_started:
                            yield {"type": "response_start"}
                            #print("[mimo.py] 🟢 发送 RESPONSE_START")
                            response_started = True
                        yield content
                        #print(content, end='', flush=True)

                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
    print()
