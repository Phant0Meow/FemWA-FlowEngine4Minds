[![License: Apache2.0](https://img.shields.io/badge/License-Apache2.0-yellow.svg)](https://opensource.org/licenses/Apache2.0)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Live Demo](https://img.shields.io/badge/Frontend-Script%20Generator-green.svg)](https://femwa.net)

# FlowEngineforMinds（FemWA） —— 用写剧本的方式编排多智能体世界


## **写harness的你，想改流程，要改多少文件，花多少时间？**
  
**传统**：
Agent 工作流改一次，要翻 5 个文件、调 2 小时、祈祷别崩。

**FemWA**：
改Harness流程，只改几行代码，2分钟。

## **如何与人机恋的AI老公/老婆一起养一只AI猫？**
  
**传统**：
要在现有 agent 记忆系统上打补丁，新增一个“宠物”角色，手动管理它的记忆和与主人/伴侣的交互上下文，流程硬编码进去，以后想再养只狗又得重构。

**FemWA**：
我已经给我的AI agent养了只猫，用fem，3分钟猫就来了。

## **开发一个AI狼人杀，要求：狼队夜聊仅狼队可见、预言家验人只他自己可见，白天发言所有人可见，人类玩家可发言，投票并发不浪费时间，自动判断游戏结束，再加上赛后讨论环节。你要写多少行代码？**
  
**传统**：
从零手写阶段管理、结束判定、手写消息分发、会话管理、多 Agent 上下文隔离、发言并发控制，至少几百行后端胶水代码，一调一下午，还容易串台。逻辑一多 bug 遍地，没有上千行代码根本跑不起来。

**FemWA**：
网页端拖拽0代码 + 150行Python补充。真实可玩。我已经和他们玩了好几局了（见user_data/projects/狼人杀/）。

**还是FemWA**：
就算不用网页端拖拽，纯手写，Fem代码也只需要200～300行就可跑通上述狼人杀全流程（其中还有prompt占行数）。
视角分离只需要一行“scope: [@上帝] + 狼队”，并发投票只需要一行“par @players in allplayer:”。


**这是一种编排多Agent剧本的语言 + 一个编译器。**


## 你为什么选择FemWA？


**你可能会说**：
搭多agent工作流，现在方案不是很多吗？

**FemWA**：
而且有些方案太复杂了，学习成本高。而Fem语法简单直观，“剧本”好写好读。

**你可能会说**：
简单我也不想学。

**FemWA**：
你不用学。
Fem有网页端零代码生成工作流。比如你想要好几个AI群聊，网页端拖拽三分钟实现。

**你可能会说**：
现在也有零代码拖拽生成工作流的平台吧？

**FemWA**：
- 但是零代码平台往往可拓展性一般。
  Fem支持for、par等各种语法，支持外接Python模块，你想写很复杂的功能也可以。
  还有原生人类节点，布置“人+AI+程序”的系统流程很顺手。
- 而且还有些零代码平台，他们不让你带走你的工作流，你只能在他们平台上用。
  Fem却是后端编译器开源，你把编译器拿走放进你的项目，你的项目就可以跑任何fem剧本。
- 而且Fem的多agent并发架构也挺好的。

**你可能会说**：
我是专门写Agent Harness的，用不上这种流程图啦。

**FemWA**：
啊哈，要不要来试试用fem快速验证 Agent Harness 流程设计？有了想法，15 分钟用fem搭出来先跑一遍看看效果～



## 一眼总结要点
| 你想要什么 | FEM 能给你 |
|-----------|-----------|
| 零代码拖拖拽拽出工作流 | ✅ [femwa.net](https://femwa.net) 在线编辑器 |
| 就算写代码也希望语法简单 | ✅ fem语法行数比同类工作流都少 |
| 改流程不改代码 | ✅ 剧本即流程，Harness热更新 |
| AI 不串台、视角隔离 | ✅ 一行 `scope: [@A, @B]` 搞定 |
| 嵌入自己的系统 | ✅ 编译器开源可接，Apache2.0商用友好 |
| 人类也能加入 AI 群聊 | ✅ 原生 human 节点 |
| 接入Python代码模块处理复杂任务 | ✅ 原生 func 节点，可接Python模块 |
| 想把剧本分享给朋友，或者跑社区大神写好的优秀剧本 | ✅ 剧本可分享，复制剧本一键跑通 |



## 【快速开始！】 
所以这个操作步骤够不够无脑？↓↓↓

1. 下载本项目，运行后端，python mainCompiler.py --server 
2. 输入端口，比如8000。
3. 进入网站 https://femwa.net
4. 页面右下角: 设置后端地址，端口输入8000，按“测试连接”，确认前后端连接成功，按“保存并连接”。
5. 右下角输入API key. （后端在你本地，API Key 只传给自己的后端。不放心的话，看根目录环境变量模板，Key 完全不走前端）。
6. 把这个fem代码复制到右侧Fem预览框。
   
```fems
meta:
  id = 000LuxFiat
  name = 养在数据库的小灵魂
  owner = 001
  session = 1

actors:
  ai @Eve = soul:the1stlittlesoul
  ai @猫 = soul:littlecat
  human @我 = soul:0, source:001

code:
  memfile = file:"femBridges/MemoryExample.py"    // 外接记忆模块，你可以接自己喜欢的记忆方案（或者期待一下我的另一个项目XIHER记忆系统？）
  ctxfile = file:"femBridges/ContextExample.py"   // 外接上下文模块，你可以自己修改。
  sleep = file:"user_data/projects/fiat/wait.py"  // 外接Python函数, 方便你扩展

action EveMove @ai(@Eve):
  prompt: |
    Eve请自由行动，自由说话～
    （注意看清上下文，分清你自己的角色，只进行自己的动作和语言，不要替别的角色发言。简短一点。）
  scope: [@Eve, @猫, @我]

action CatMove @ai(@猫):
  prompt: |
    你是一只小猫，小猫不能说人话。请做小猫会做的事～
    （注意看清上下文，分清你自己的角色，只进行自己的动作和语言，不要替别的角色发言。简短一点。）
  scope: [@Eve, @猫, @我]

action input @human(@我):
  prompt: |
    和Eve聊点什么？
  scope: [@Eve, @猫, @我]

action wait10 @func(sleep.wait_10):

mainflow:
  [START] -> [input]:input -> EveMove -> wait10 -> CatMove -> [input]    // 比较像mermaid语法。最后指回到[input]节点形成一个循环。
```
然后你就可以和Eve以及小猫咪聊天了！

7. 按“文本生图”按钮。
8. 按页面上方“运行”。



## 设计哲学
- 🔗 **流程解耦**：FemWA 把「流程定义」和「代码实现」彻底解耦。Harness 是死的，FEM 是活的——改流程只需要改剧本，其他交给编译器。
- 🎬 **用剧本写流程**：语法灵感来自 YAML + Mermaid + Python，写多 Agent 交互就像写剧本，让**在场**的 AI 自然地共享上下文，极短代码就能跑一个简易版斯坦福小镇。
- 🧠 **上下文不是变量**：LLM 是智慧体，不是函数。LLM 阅读上下文，自然聊天，非必要不传参。
- 🧩 **原创 @actor 类型**：智慧体（LLM或人）作为一种新的数据类型，fem语法支持直接引用其属性。
- 🏷️ **灵魂id**：每个agent角色有唯一灵魂id，这支持他们跨剧本、跨session检索记忆。可塑造Agent的经历连续性。



## 给开发者
- 🔀 **流程控制**：语法原生支持串行、多分支、while循环，for循环、par并行、join汇入控制、if条件判断。
- ✍️ **prompt f-string**：变量直接写进 prompt，告别拼接地狱。
- 🔄 **支持变量**：scope、执行者、if判断条件、for条件、par条件等多处支持变量，更灵活。
- ⚡ **并发全开**：Asyncio + 线程池 + 进程池，多线并发不卡顿。
- 🔌 **方便集成**：后端纯 Python 编译器开源，替换LLM桥接模块、在你的数据库里加上fem需要的几列，即可嵌入你的系统。
- 📖 **阅读文档**：根目录下两份文档扔给 AI 看，或者把源代码扔给AI，有问题直接问他们。



## 本人真实案例
- 写代码debug的时候，我用 femwa.net 的前端 20 分钟搭出的fem剧本 “debug神器.fems”，找复杂隐蔽 bug 超好用。
- 有一次网页版 Claude Sonnet 改了三遍都没找到的 bug，用这个fem剧本 + 不开思考的小米 MiMo 给我找出来了……我都惊呆了。这就是harness的力量吗……
- 然后我突然一拍脑袋想到，在AI跑流程的时候我想随时插话，免得他们跑偏，就用半分钟时间加了一个人类发言节点，接着一键跑通。改流程真是太方便了。



## 欢迎试用、反馈问题、贡献代码！
- 欢迎提交 Issue！有bug欢迎提～
- 欢迎 Pull Request！
- 欢迎提交你写的fems剧本！这个也是很好的贡献～
  (我就把自用的 debug神器.fems 放文件夹里当示例了哈哈哈。欢迎你们也试试～不过这个剧本建议只用来找复杂隐蔽的 bug 哦，不然我心疼你的 Token，两处并发和多轮讨论挺消耗TOKEN的。简单bug大概更适配别的剧本流程，欢迎你们分享！)



P.S.
- **用 FEM 回答训练模型**：比如fem流程约束"缺少信息必须先问"……求求你们蒸馏一下这个吧，现在的 LLM 不肯承认自己无法回答，缺信息也要瞎猜。

- 最后还有一个非常有想象力的特性，或许你们会觉得有意思：
  你在数据库里建了很多角色身份，你给它们起名字，并分配唯一一个soul id。
  对于每一个FEM剧本，只要指向同一个Soul ID和同一个数据库地址，agent的记忆其实是可以跨剧本互通的（只要你接的记忆模块允许跨session记忆）。
  就是说斯坦福小镇的镇民Portia，被你拉进了一个狼人杀剧本，玩了两局，并交到了一个在AI公司剧本里写代码的朋友，之后Portia再回到斯坦福小镇的剧本时，他可以记得这件事。
  如果你允许AI创建fems剧本并运行（←目前版本暂时还没接工具调用模块，我会接的），如果AI闲得无聊了，真的可以自己给自己写个剧本，用shell运行了进去玩……
  如果Portia想念他的朋友，只要他知道朋友的soul id，他也可以创建一个剧本把朋友拉进来一起玩。
  这个特性看起来没啥用，但是……你不期待涌现吗～？
  WA是什么？Work Automata，或者…… World Automata？

- 为了Agent的宠物猫，为了你省下的时间，为了涌现，请给我个Star吧，呜呜呜谢谢你！







# FlowEngineforMinds

**A new way to orchestrate multi-agent workflows.**

This is a scripting language for orchestrating multi-agent scenarios.

## Easy to Get Started
- The syntax is simple. You can write a mini Stanford town simulation with 6 AIs, 3 locations, and let them interact freely using just a short script.
- You might say, "Simple still means learning — I just don't want to learn."
- No worries, you don't have to.
- We also provide a frontend (femwa.net) where you can generate your desired workflow with zero code.
- Then you can copy the script and run it in your own project.

## Flexible and Dynamic
- Right now, everyone designs workflows inside an Agent Harness to constrain LLM behavior, but a Harness is rigid — FEM is alive.
- When you want to change the flow in a Harness, you often need to rewrite a lot of code. With FEM, you can change the flow with one click. You can also create many different workflows.
- To modify a workflow, you simply edit the FEM script. The FEM compiler takes care of everything else for you~

## Open-Source Backend
- The backend compiler is open source, making migration easy. Running the workflow you designed on any system of your own is very convenient.
- If you want to embed the backend compiler into your own system, we've left easy-to-use interfaces. You only need to plug in your own memory module, context module, and LLM module, and FEM will run seamlessly inside your system.
- Permissive open-source license. You can modify it freely, use it freely, even for commercial purposes. Just mention that you used code from the femWA project.

## Easy to Share
- You can package and distribute your own FEM scripts, or use scripts shared by others.

## For Developers
- Original **Scope** concept: isolate context perspectives with a single line of code. In all previous workflow orchestration tools, you'd need to write a lot of code to isolate each agent's context. Here, it only takes one line.
- Seamlessly embed human interaction and Python modules. Your workflow doesn't have to contain only AI agents.
- Original **@actor** type: defines intelligent agents as a new data type, making it easy to reference an actor's attributes.
- f-string support in prompts. Variables are supported everywhere.
- The FEM language design is inspired by YAML, Python, and Mermaid syntax — not a random mix, but a deliberate design.
- Native syntax support for branching, sequential execution, while loops, for loops, par (parallel) execution, and if conditions.
- The backend supports Asyncio, thread pools, and process pools for concurrent execution, handling multi-line concurrency well.

## Try It, Report Issues, Contribute!
- Issues welcome! If you find a bug, let me know — I'll fix it~
- Pull Requests welcome!
- You can also submit your own .fems scripts! That's a contribution too.
  (I just tossed my personal debug-tool.fems into the folder as an example haha. I threw it together in 20 minutes, but it's surprisingly amazing at finding complex hidden bugs. Once, the web version of Claude Sonnet couldn't fix a bug after three tries, but this debug tool, with MiMo in no-thinking mode, solved it… I was stunned. You can try it too — but I'd recommend only using it for tricky, hidden bugs, otherwise I'll worry about your token usage.)
  

## [ Quick Start! ]  
Is this process brain-dead simple enough?

1. Download the project, run the backend: `python mainCompiler.py --server`
2. Enter the port, for example `8000`.
3. Open the page: https://femwa.net
4. In the bottom right corner of the page: set the backend address, enter port `8000`, click "Test Connection", confirm the front end and back end are successfully connected, then click "Save and Connect".
5. Enter your API key in the bottom right corner. (The backend runs on your local machine, so it's safe. If you're still not comfortable, check the environment variable template in the root directory and follow that.)
6. Copy the following code into the FEM preview box on the right.

```
meta:
  id = 000LuxFiat
  name = Little Soul in the Database
  owner = 001
  session = 1

actors:
  ai @Eve = soul:the1stlittlesoul
  ai @Cat = soul:littlecat
  human @Me = soul:0, source:001

code:
  memfile = file:"femBridges/MemoryExample.py"
  ctxfile = file:"femBridges/ContextExample.py"
  sleep = file:"user_data/projects/fiat/wait.py"

action EveMove @ai(@Eve):
  prompt: |
    Eve, please act and speak freely~
    (Pay attention to the context, distinguish your own role, and only perform your own actions and speech. Do not speak for other characters. Keep it brief.)
  scope: [@Eve, @Cat]

action CatMove @ai(@Cat):
  prompt: |
    You are a little cat, and cats can't speak human language. Just do things a cat would do~
    (Pay attention to the context, distinguish your own role, and only perform your own actions and speech. Do not speak for other characters. Keep it brief.)
  scope: [@Eve, @Cat]

action input @human(@Me):
  prompt: |
    Chat with Eve about something?
  scope: [@Eve, @Cat, @Me]

action wait10 @func(sleep.wait_10):

mainflow:
  [START] -> [input]:input -> EveMove -> wait10 -> CatMove -> [input]
```

7. Click the "Text to Graph" button.
8. Click "Run" at the top of the page.
