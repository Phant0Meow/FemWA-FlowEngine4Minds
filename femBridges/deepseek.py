#femBridge/deepseek.py
import requests
import json

def stream_chat(
    api_key: str,
    api_url: str,
    messages,                 # 现在这是个 list，来自 chat_process.py 构建好的消息列表
    system_prompt: str = "",
    native_params: dict = None,         # 🆕 V2 统一参数字典
    sampling_params: dict = None,       # 🆕 采样参数字典（temperature / top_p / frequency_penalty）
    **kwargs,
):
    """
    使用 requests 调用 DeepSeek V4 pro API，流式输出，支持深度思考控制。
    
    Args:
        api_key: DeepSeek API 密钥
        api_url: DeepSeek API 端点 URL (如 https://api.deepseek.com/v1/chat/completions)
        messages: 上游已经组装好的消息列表 (list of dict)
                  格式: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        system_prompt: 备用系统提示词（通常 messages 中已包含）
        native_params: V2 统一参数字典，格式: {工具名: 1 或 -1}
                       DeepSeek V4 pro 原生支持的 key:
                       - deep_think: 1=开启思考模式, -1=关闭思考模式
                       其他 key (web_search 等) 不支持，将被忽略。
    """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🆕 V2 参数解析：从 native_params 提取 deep_think 开关
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if native_params is None:
        native_params = {}

    # 🆕 深度思考开关完全由 native_params["deep_think"] 控制，不再依赖旧参数
    _deepthink = False
    if "deep_think" in native_params:
        if native_params["deep_think"] == 1:
            _deepthink = True
            #print("[deepseek_v4pro.py] 🧠 深度思考模式: 开启")
        elif native_params["deep_think"] == -1:
            _deepthink = False
            #print("[deepseek_v4pro.py] 🧠 深度思考模式: 关闭")
    #else:
        #print("[deepseek_v4pro.py] 🧠 深度思考模式: 关闭 (默认)")

    # DeepSeek V4 pro 不支持的其他工具 (web_search, shell 等) — 直接忽略
    # 如果收到不支持的 key，只打日志不报错
    unsupported_keys = set(native_params.keys()) - {"deep_think"}
    #if unsupported_keys:
        #print(f"[deepseek_v4pro.py] ⚠️ 不支持的 native_params 键 (将忽略): {unsupported_keys}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # ✅ 关键修复：messages 已经是完整的列表，直接使用
    # 只需要确保每个消息都有 "type": "text"（DeepSeek V4 强制要求）
    formatted_messages = []
    for msg in messages:
        new_msg = msg.copy() if isinstance(msg, dict) else {"role": "user", "content": str(msg)}
        # DeepSeek V4 要求每个消息必须有 "type" 字段
        if "type" not in new_msg:
            new_msg["type"] = "text"
        formatted_messages.append(new_msg)

    # 确定模型名
    # DeepSeek V4 pro 只有一个模型 ID，不需要 reasoning_model
    # 但保留旧参数兼容性
    model = "deepseek-v4-pro"

    # 🆕 从显式参数 sampling_params 获取采样参数（由上游 chat_process 根据话题 + 模型偏移统一计算）
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

    # 只在开启深度思考时设置思考强度
    if _deepthink:
        data["reasoning_effort"] = "max"
        #print("> 深度思考模式已开启（思考强度：max）")
    #else:
        #print("> 非思考模式（thinking: disabled）")

    # 发送请求
    response = requests.post(api_url, headers=headers, json=data, stream=True)
    response.raise_for_status()

    #print("\n--- 流式回答 ---")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🆕 状态变量：用于向 stream_output 发送阶段标记
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    cot_started = False       # 是否已发送 cot_start
    cot_ended = False         # 是否已发送 cot_end
    response_started = False  # 是否已发送 response_start

    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: '):
                chunk_str = decoded[6:]
                if chunk_str == '[DONE]':
                    # 确保思考结束标记已发送（若未结束）
                    if cot_started and not cot_ended:
                        yield {"type": "cot_end"}
                        #print("\n[deepseek_v4pro.py] 🟡 补发 COT_END")
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
                            #print("\n[deepseek_v4pro.py] 🟢 发送 COT_START")
                            cot_started = True
                        yield reasoning
                        #print(reasoning, end='', flush=True)

                    # ── 处理正式回答 ──
                    if content:
                        # 如果思考刚结束，先发 cot_end 和 response_start
                        if cot_started and not cot_ended:
                            yield {"type": "cot_end"}
                            #print("\n[deepseek_v4pro.py] 🟡 发送 COT_END")
                            cot_ended = True
                            yield {"type": "response_start"}
                            #print("[deepseek_v4pro.py] 🟢 发送 RESPONSE_START")
                            response_started = True
                        elif not response_started:
                            yield {"type": "response_start"}
                            #print("[deepseek_v4pro.py] 🟢 发送 RESPONSE_START")
                            response_started = True
                        yield content
                        #print(content, end='', flush=True)

                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
    print()
