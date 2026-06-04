================================================================================
# Flow Engine for Minds - Work Automata (FemWA)
# 开发者技术参考 — 线程、存储、Block 收集与项目架构
================================================================================

本文档面向 FEM 剧本开发者、引擎维护者和后端接入人员，涵盖线程管理、
数据持久化、Prompt Block 收集机制以及项目文件结构。

-=-

0. 核心设计原则

- 变量和演员统一管理：VarManager 能同时查询 vars 和 actors，
  任何 @xxx 都可以直接 get，不区分"变量"和"演员"。
- @ 符号全程保留：Actor 名字永远带 @，代码中不添加、不删除。
- 不兜底：语法错误、配置缺失、变量未声明一律报错，不静默容错。
- 积木式架构：引擎只收集 block，不绑定任何 prompt 排版或 LLM 调用方式。

-=-

1. Prompt Block 收集清单

引擎在执行每个 action 前，自动收集以下标准 block，返回字典供外部 prompt 组装器使用。

| Block Key | 内容 | 来源 |
|-|-|-|
| basic_safety | 安全须知 | meta.system_safety |
| basic_output | 输出质量要求 | meta.output_style |
| soul | 角色描述（system prompt 片段） | 数据库 souls 表（根据当前 Actor 的 soul_id） |
| user_info | 用户信息 | 数据库 user 表（根据 meta.owner） |
| memory | 记忆检索结果 | 用户自定义 memory 函数返回 |
| context | 对话历史上下文 | 用户自定义 context 函数返回 / 内置默认实现 |
| user_input | 当前 prompt（已变量替换） | 当前 action 的 prompt |

引擎只负责收集 blocks 并返回字典，外部框架自行决定如何组装成 system/user prompt。


-=-

2. Session 与 Turn 管理

- meta.session 未指定或为 new → 新建 session（数据库最大 session_id + 1），turn = 1。
- meta.session 指定数字 → 继承该 session，turn 从该 session 的最大 turn + 1 开始。
- 指定的 session 不存在 → 报错退出。
- 每次人类发言后 turn_count += 1，step_idx = 0。
- 同一 turn 内每次 AI 发言 step_idx += 1。
- 新建 session 时，meta.name 自动写入 sessions.title 字段。


-=-

3. 对话存储规则

存储时机：
- 人类发言（@human 动作）→ 存入 dialog 表，然后 turn + 1。
- AI 回复（@ai 动作）→ 存入 react_steps 表，step_idx 递增。

Scope 自动注入：
每条记录自动注入发言者自己的 ID（AI 的 soul_id 或人类的 user_id）以及
meta.owner 中所有 user_id。注入后删除 0，去重，最终存入 user_scope 和 soul_scope 字段。

-=-


-=-

8. 数据库：
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
    profile         TEXT DEFAULT ''
);









《FEM 多 Agent 异步并发引擎 开发者指南》

### 1. 设计目标

FEM 多 Agent 异步并发引擎旨在为复杂 Agent 工作流提供高性能、可扩展的运行时支撑。核心设计目标：

- **支持大量并发**：单节点内可同时调度海量 Agent 分支，轻松应对 fork/for 等并发场景。
- **完全无锁调度**：基于 Python 原生异步机制实现任务切换，消除传统多线程方案中的锁竞争和死锁风险。
- **优雅的任务取消**：支持任意时刻取消任意分支，被取消的协程可安全释放资源。
- **混合任务统一编排**：将 I/O 密集型（LLM 调用）、CPU 密集型（本地 Python 计算）、人类输入等待三类负载纳入同一调度框架，开发者无需关心底层并发模型。

### 2. 核心架构：AsyncEngine

`AsyncEngine`（位于 `femCompiler/femAsync.py`）是整个并发系统的中枢，负责管理所有执行器、调度协程任务、并提供统一的异步原语。

#### 2.1 核心思想：调度与执行分离

引擎采用“单线程大脑 + 外派重活”模式：

- **asyncio 事件循环** 是唯一调度器，在单线程内运行，负责编排所有 Agent 协程，任何操作都不阻塞事件循环。
- **重任务（CPU 密集、同步 I/O、人类等待）** 一律外包给独立的执行池（进程池或线程池），主循环只等待结果。

这种分离使得主循环永远保持响应，即使某个分支在执行长时间计算或等待 LLM，其他分支照常推进。

#### 2.2 三大执行器

**进程池**：CPU 密集型任务隔离方案，大小自动适配 CPU 核数，任务自动排队。当所有 Worker 繁忙时，后续任务在池的内部队列等待，不会拒绝或丢失。

**通用 I/O 线程池**：负责处理同步阻塞 I/O（如 LLM API 调用）和 `@func` 用户代码。核心特性：通过自定义线程初始化器，每个线程创建时自动启动一个后台事件循环并永久运行，彻底根除 `no running event loop` 错误。无论是 HTTP 请求库还是 `stream_chat`，在线程中都能正常使用 `asyncio`。

**人类输入管理器**：基于 `threading.Event` 实现线程安全的异步等待。协程调用 `wait_for_input` 时挂起，外部通过 `provide_input` 唤醒，支持超时。在 FastAPI 模式下，输入由 HTTP 端点注入；在 CLI 模式下，多行读取被封装为同步函数提交到线程池执行，均不阻塞主循环。

#### 2.3 任务调度与协程管理

- **协程任务 `asyncio.Task`**：每个 Agent 分支（fork 分支）就是一个 `Task`。Fork 时调用 `engine.create_task()` 创建并自动追踪，Join 时统一等待或取消。
- **`gather_with_cancel`**：支持三种 Join 模式：
  - `all`：等待所有分支完成。
  - `any`：任一完成即取消其余。
  - `n`：指定数量完成后取消其余。
- 基于 `asyncio.wait` 的 `FIRST_COMPLETED` 策略，零轮询，完全事件驱动。

#### 2.4 上下文隔离

使用 Python 标准库 `contextvars` 为每个协程/线程自动隔离上下文变量。每个 Agent 分支拥有独立的 `ExecutionContext`，内部变量（如 `node_name`、循环变量）互不干扰。主流程、fork 分支、for 循环体内各自的上下文完全分离，无需手动加锁。

#### 2.5 引擎生命周期与优雅关闭

`AsyncEngine` 提供 `shutdown()` 方法，按顺序：取消所有活跃协程任务 → 等待取消完成 → 关闭线程池 → 关闭进程池。线程池关闭时会停止所有后台事件循环并等待线程退出，确保资源完全释放。

### 3. 引擎与 Runtime 的集成接口

`FEMRunner`（位于 `femCompiler/FEM_runtime.py`）是工作流执行器，通过持有 `AsyncEngine` 实例将所有并发需求委托给引擎。

#### 3.1 FEMRunner 如何持有并使用引擎

在 `FEMRunner.__init__` 中创建 `self.engine = AsyncEngine()`。所有需要异步执行的方法（`_exec_func`、`_exec_ai`、`_exec_human` 等）均通过 `self.engine` 的接口执行，不再直接使用 `asyncio`。

#### 3.2 节点执行的路由规则

每种节点类型对应固定的引擎接口：

- **`@func`**：调用 `self.engine.run_in_thread` 在线程池中执行。当前默认所有 `@func` 走线程池，但引擎提供了 `run_in_process` 方法，未来可根据用户标注或函数复杂度自动切换。
- **`@ai`**：LLM 调用通过 `self.engine.run_in_thread` 提交到线程池。流式回调通过 `engine.schedule_threadsafe` 将 token 安全推回事件循环，确保前端实时接收。
- **`@human`**：FastAPI 模式下调用 `self.engine.human_input.wait_for_input` 挂起协程；CLI 模式下将多行读取函数提交到线程池执行，避免阻塞事件循环。

#### 3.3 流程控制原语如何映射到引擎 API

- **Fork**：`_run_fork` 中为每个分支入口创建 `engine.create_task(branch_runner())`，任务存入 `self._join_tasks` 字典，返回 join 节点 ID。若没有 join，直接 `await engine.gather(*tasks)` 等待全部完成。
- **Join**：`_run_join` 从 `self._join_tasks` 取出任务列表，根据 `join_mode` 调用 `engine.gather_with_cancel`。
- **For 循环**：`_run_for_loop` 是普通的 `async` 方法，内部迭代时 `await` 节点执行，循环体末尾通过回边重新进入网关，无需引擎级别的特殊支持。

#### 3.4 事件发送与线程安全

AI 流式回调运行在线程池中，不能直接操作前端 SSE 连接。引擎提供 `schedule_threadsafe` 方法，将回调函数安全地“投递”到事件循环中执行。实现原理：`asyncio.get_running_loop().call_soon_threadsafe(callback, *args)`。

#### 3.5 主流程与 Web 服务器的配合

`FEMRunner.run()` 是同步入口，内部检测是否已有运行中的事件循环：

- 若无（CLI 模式），调用 `asyncio.run(self.run_async())` 启动新循环。
- 若有（FastAPI 模式），直接 `await runner.run_async()`。

`run_async` 为主流程创建顶层 `ExecutionContext("__main__")`，确保所有节点的 `node_name` 能正确获取，然后调用 `await self._execute_flow(flow)` 进入图遍历。

### 4. 开发者指南

#### 4.1 配置与调优

**线程池大小**

- 默认值：10 个工作线程
- 适用场景：同步 LLM 调用、`@func` 用户代码
- 调优建议：
  - 若工作流中同时有大量 LLM 调用和 `sleep` 类函数，可增大到 20~30，避免线程池饥饿。
  - 如果已拆出专用 AI 线程池（见下方扩展指南），则通用池可保持较小值。
- 自定义方式：在创建 `AsyncEngine` 时传入 `thread_workers` 参数。

**进程池大小**

- 默认值：自动检测 CPU 核心数
- 适用场景：CPU 密集的 `@func` 节点（尚未默认启用，需手动切换）
- 自定义方式：传入 `cpu_workers` 参数，或设置环境变量 `PROCESS_WORKERS`。

#### 4.2 如何新增一个执行器类型

假设你需要支持 `@gpu` 类型的节点，执行 GPU 推理任务。步骤如下：

1. **在 `AsyncEngine` 中添加专用执行器**（`femAsync.py`）：
```python
# 在 __init__ 中
self.gpu_pool = ThreadPoolExecutor(max_workers=2)  # GPU 并发需严格控制
self._gpu_semaphore = asyncio.Semaphore(2)

# 新增方法
async def run_gpu(self, func, *args, **kwargs):
    async with self._gpu_semaphore:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.gpu_pool, func, *args, **kwargs)
```

2. **在 `FEMRunner._exec_action_def` 中添加路由**（`FEM_runtime.py`）：
```python
elif etype == 'gpu':
    return await self._exec_gpu(ad, eparam)
```

3. **实现 `_exec_gpu` 方法**，参照 `_exec_func` 的模式，调用 `self.engine.run_gpu(...)`。

#### 4.3 人类输入的多模式支持

引擎的 `HumanInputManager` 同时支持两种模式，由 `FEMRunner._human_input_event` 是否为 `None` 决定：

- **FastAPI 模式**（`_human_input_event is not None`）：协程挂起在 `engine.human_input.wait_for_input(key)`，等待前端通过 `/api/run/{run_id}/human-input` 端点调用 `provide_input` 唤醒。
- **CLI 模式**（`_human_input_event is None`）：将多行读取逻辑封装为同步函数，通过 `engine.run_in_thread` 提交到线程池执行，主循环 `await` 其结果。

切换方式：在 `main.py` 的 `run_workflow` 函数中，FastAPI 模式会设置 `runner._human_input_event = threading.Event()`；CLI 模式则不设置，保持 `None`。

#### 4.4 常见问题排查

**问题 1：前端收不到节点信息（`node_name` 为空）**

原因：主流程没有创建顶层 `ExecutionContext`，导致 `_current_context.get()` 返回 `None`。  
解决：确保 `run_async` 方法中包裹了 `with ExecutionContext("__main__"):`。

**问题 2：流程静默退出，没有任何错误**

原因：入口推断失败（如 `flow.entry` 为空，且所有节点都有入边）。  
解决：检查工作流中是否显式声明了 `[START]` 节点，或是否有节点没有被任何边指向。

**问题 3：AI 调用报 `no running event loop`**

原因：LLM 库内部需要运行中的事件循环，但线程池的默认线程没有。  
解决：确认 `AsyncEngine` 的线程池已配置 `initializer`（为每个线程启动后台事件循环）。这是引擎的内置行为，无需额外配置。

**问题 4：Fork 后所有分支无条件执行**

原因：`_run_fork` 未评估条件边。  
解决：确认分支入口收集逻辑中已调用 `self._eval_condition(e.condition)` 过滤条件为假的边。

#### 4.5 从单机到多机的扩展建议

当前架构天然支持分布式扩展，因为调度层（`FEMRunner` / `AsyncEngine`）与执行层（线程池、进程池）已经解耦。

**扩展点分析**

- **调度层**：`asyncio` 事件循环本身无状态（状态已外置到 `contextvars` 和 `VarManager`），可轻易复制到多台机器。
- **执行层**：线程池和进程池是单机资源，需要抽离为独立的 Worker 服务。

**推荐方案：引入消息队列拆分调度与执行**

1. **调度集群**：部署多个 `FEMRunner` 实例（无状态），通过负载均衡分发用户请求。每个实例仍运行 `asyncio` 主循环，负责任务编排和 I/O 等待。
2. **CPU Worker 集群**：将标记为 CPU 密集的 `@func` 节点通过 Redis Streams 或 RabbitMQ 投递到独立的 Python Worker 进程，Worker 执行完毕后将结果写回。
3. **GPU 推理集群**：GPU 推理节点直接通过 HTTP/gRPC 调用部署好的模型服务（如 vLLM），调度层异步等待响应。
4. **人类输入管理**：将 `HumanInputManager` 的后端切换为 Redis Pub/Sub，支持跨机器的输入等待与唤醒。

这样，单节点的 `AsyncEngine` 仍然保留作为核心调度单元，而重计算任务被水平扩展到独立集群，整体架构从单机超级办公室自然演化为分布式企业园区。

### 5. 附录

#### 5.1 `AsyncEngine` 完整接口速查表

| 方法 / 属性 | 用途 | 说明 |
|:---|:---|:---|
| `__init__(cpu_workers, thread_workers)` | 初始化引擎 | 创建进程池、线程池、人类输入管理器 |
| `run_in_process(func, *args, **kwargs)` | 执行 CPU 密集任务 | 提交到进程池，自动排队 |
| `run_in_thread(func, *args, **kwargs)` | 执行同步 I/O 或普通函数 | 提交到线程池（自带事件循环） |
| `create_task(coro)` | 创建协程任务 | 用于 fork 分支，自动追踪 |
| `gather_with_cancel(tasks, return_when, count)` | 等待多个任务 | 支持 `all` / `any` / `n` 模式 |
| `gather(*coros, return_exceptions)` | 并发等待多个协程 | 封装 `asyncio.gather` |
| `schedule_threadsafe(callback, *args)` | 线程安全回调 | 将回调从线程池推回事件循环 |
| `check_cancel()` | 检查当前协程是否被取消 | 若已取消则抛出 `CancelledError` |
| `shutdown()` | 优雅关闭 | 取消所有任务、关闭线程池和进程池 |
| `human_input` | 人类输入管理器实例 | 提供 `wait_for_input` 和 `provide_input` |

#### 5.2 工作流编写规范

**For 循环**

语法：
```fems
[Node] -> for @变量 in 迭代对象:
  -> [循环体节点1] -> [循环体节点2] ->   # 行末 -> 表示回边
-> [循环出口节点]                         # 无缩进的出口行
```
注意：
- 循环体内至少一行以 `->` 结尾，表示回边到 for 网关。
- 出口行必须顶格（与 for 同级缩进）。
- 循环变量会在每轮迭代开始时自动更新。

**Fork**

语法：
```fems
[Node] -> fork:
  -> [分支1]
  -> [分支2]
```
注意：
- 所有分支并行执行。
- 若存在条件（`if (...)`），引擎会在运行时评估，只创建条件为真的分支。
- Fork 后可接显式 `join(...)` 控制等待策略。

**Join**

语法：
```fems
join(all):     # 或 join(any)、join(n=2)
  [分支1] ->
  [分支2] ->
```
注意：
- `join` 不支持前导链，必须独立成行。
- `join(all)` 等待所有分支完成；`join(any)` 任一完成即取消其余；`join(n=2)` 完成 2 个后取消其余。
