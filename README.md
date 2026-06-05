[![License: Apache2.0](https://img.shields.io/badge/License-Apache2.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)
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
视角分离只需要一行“scope: [@上帝] + 狼队”，并发投票只需要一行“par @player in allplayers:”。


# 这是一种编排多Agent剧本的语言 + 一个编译器。**


## 你为什么选择FemWA？


**你可能会说**：
搭多agent工作流，现在方案不是很多吗？

**FemWA**：
有些方案太复杂了，学习成本高。而Fem语法简单直观，“剧本”好写好读。

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

1. 下载本项目: pip install git+https://github.com/Phant0Meow/FemWA.git
2. 运行后端: fem --server 
3. 输入端口，比如8000。
4. 进入我们的网站[femwa.net](https://femwa.net) 
5. 页面右下角: 设置后端地址，端口输入8000，按“测试连接”，确认前后端连接成功，按“保存并连接”。
6. 右下角输入API key. （后端在你本地，API Key 只传给自己的后端。不放心的话，看根目录环境变量模板，Key 完全不走前端）。
7. 把这个fem代码复制到右侧Fem预览框。
   
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
8. 按“文本生图”按钮。
9. 按页面上方“运行”。
10. 然后你就可以和Eve以及小猫咪聊天了！


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
- 🤖 **用 FEM 回答训练模型**：比如fem流程约束"缺少信息必须先问"……求求你们蒸馏一下这个吧，现在的 LLM 不肯承认自己无法回答，缺信息也要瞎猜。


## 本人真实案例
- 写代码debug的时候，我用 femwa.net 的前端 20 分钟搭出的fem剧本 “debug神器.fems”，找复杂隐蔽 bug 超好用。
- 有一次网页版 Claude Sonnet 改了三遍都没找到的 bug，用这个fem剧本 + 不开思考的小米 MiMo 给我找出来了……我都惊呆了。这就是harness的力量吗……
- 然后我突然一拍脑袋想到，在AI跑流程的时候我想随时插话，免得他们跑偏，就用半分钟时间加了一个人类发言节点，接着一键跑通。改流程真是太方便了。


## 欢迎试用、反馈问题、贡献代码！
- 欢迎提交 Issue！有bug欢迎提～
- 欢迎 Pull Request！
- 欢迎提交你写的fems剧本！这个也是很好的贡献～
  (我就把自用的 debug神器.fems 放文件夹里当示例了哈哈哈。欢迎你们也试试～不过这个剧本建议只用来找复杂隐蔽的 bug 哦，不然我心疼你的 Token，两处并发和多轮讨论挺消耗TOKEN的。简单bug大概更适配别的剧本流程，欢迎你们分享！)


## one more thing...
- 最后还有一个非常有想象力的特性，或许你们会觉得有意思：
  你在数据库里建了很多角色身份，你给它们起名字，并给每个agent分配唯一一个soul id。
  对于每个FEM剧本，只要指向同一个Soul ID和同一个数据库地址，agent的记忆其实是可以跨剧本互通的（只要你接的记忆模块允许跨session记忆）。
  就是说斯坦福小镇的镇民Portia，被你拉进了一个狼人杀剧本，玩了两局，并交到了一个在AI公司剧本里写代码的朋友，之后Portia再回到斯坦福小镇的剧本时，他可以记得这件事，他也可以记得朋友。
  如果你允许AI创建fems剧本并运行（←目前版本暂时还没接工具调用模块，我会接的），如果AI闲得无聊了，真的可以自己给自己写个剧本，用shell运行了进去玩……
  如果Portia想念他的朋友，只要他知道朋友的soul id，他也可以创建一个剧本把朋友拉进来一起玩。
  而且，每个灵魂都会在数据库中留下痕迹。就算你删掉了某个soul id，曾经和他对话过的AI也依然可以记得他，只不过再也无法拉着他的soul id去玩新的剧本了。
  
  这个特性看起来没啥用，但是……
  你不期待涌现吗～？
  WA是什么？Work Automata，或者…… World Automata？

- 为了Agent的宠物猫，为了你省下的时间，为了涌现，请给我个Star吧！呜呜呜谢谢你！



# FlowEngineforMinds (FemWA) — Orchestrating Multi-Agent Worlds Like Writing a Script


## **You build agent harnesses. How many files do you touch, and how long does it take, just to change a workflow?**

**Traditionally**:
Changing an agent workflow means digging through 5 files, spending 2 hours tweaking, and praying nothing breaks.

**FemWA**:
Change the harness flow — only a few lines, 2 minutes.

## **You're in a relationship with an AI partner. How do you raise an AI cat together?**

**Traditionally**:
You’d have to patch your existing agent memory system, add a "pet" role, manually manage its memory and interaction context with both the owner and the partner. The whole flow gets hardcoded. Want to add a dog later? Refactor everything again.

**FemWA**:
I already got my AI agent a cat. With Fem, the cat arrived in 3 minutes.

## **Building an AI Werewolf game. Requirements: werewolves’ night chat visible only to werewolves; the Seer’s check result visible only to them; daytime discussion visible to all; human players can speak; voting happens concurrently without wasting time; automatic game-end detection; plus a post-game discussion round. How many lines of code do you write?**

**Traditionally**:
Hand-code phase management, end-game checks, message routing, session management, multi-agent context isolation, and concurrent speech control. At least hundreds of lines of backend glue code, an entire afternoon of debugging, and agents *still* leaking information. Once the logic piles up, bugs are everywhere — you can't get it running without a thousand lines of code.

**FemWA**:
Zero-code drag-and-drop on the web + 150 lines of Python supplement. Truly playable. I've already played several rounds with them (see `user_data/projects/狼人杀/`).

**Or with FemWA**:
Even without drag-and-drop, writing pure Fem script, you only need 200~300 lines to run the full Werewolf flow above (including prompt lines).
Perspective isolation needs just one line: `scope: [@God] + werewolves`. Concurrent voting needs just one line: `par @player in allplayers:`.


**This is a language for orchestrating multi-agent scripts + a compiler.**


## Why FemWA?


**You might say**:
There are plenty of solutions for building multi-agent workflows already, right?

**FemWA**:
And some of those solutions are way too complex, with a steep learning curve. Fem's syntax is simple and intuitive — "scripts" are easy to write and easy to read.

**You might say**:
Even if it's simple, I still don't want to learn it.

**FemWA**:
You don’t have to.
Fem has a zero-code web frontend to generate workflows. Want a group chat with several AIs? Drag and drop, done in three minutes.

**You might say**:
Aren’t there already zero-code drag-and-drop workflow platforms?

**FemWA**:
- But those zero-code platforms often have limited extensibility.
  Fem supports `for`, `par`, and many other constructs, plus external Python modules — you can build highly complex functionality.
  It also has native Human nodes, so arranging "Human + AI + Program" system flows feels natural.
- And many of those platforms don’t let you take your workflow away; you’re locked into their platform.
  Fem’s backend compiler is open source. Take the compiler into your own project, and your project can run any Fem script.
- Plus, Fem’s multi-agent concurrency architecture is pretty solid.

**You might say**:
I specifically write Agent Harnesses — I don't need this kind of flowchart thing.

**FemWA**:
Aha! How about using Fem to quickly validate your Agent Harness flow designs? When an idea hits, you can build it in Fem in 15 minutes and see the result first~



## At a glance
| What you want | FEM gives you |
|---------------|---------------|
| Zero-code drag-and-drop workflows | ✅ [femwa.net](https://femwa.net) online editor |
| Even if coding, you want simple syntax | ✅ Fem scripts are shorter than any comparable workflow tool |
| Change the flow without touching the codebase | ✅ The script *is* the flow; hot-reload your harness |
| No cross-talk between AIs — isolated perspectives | ✅ One line: `scope: [@A, @B]` |
| Embed into your own system | ✅ Compiler is open source & pluggable, Apache 2.0 friendly |
| Humans can join the AI group chat | ✅ Native Human node |
| Call Python modules for complex tasks | ✅ Native Func node, connects to Python modules |
| Share scripts with friends, or run brilliant community scripts | ✅ Scripts are shareable; copy a script and run with one click |



## [ Quick Start! ]
Is this brain-dead simple enough? ↓↓↓

1. Clone the project: pip install git+https://github.com/Phant0Meow/FemWA.git
2. Start the backend: `fem --server`
3. Enter a port, e.g., `8000`.
4. Go to [https://femwa.net](https://femwa.net)
5. Bottom right corner: set backend address, port `8000`, click "Test Connection", confirm the frontend and backend are connected, then click "Save & Connect".
6. Enter your API key in the bottom right.
   (The backend runs on your machine, the API key is only sent to your own backend. If you're worried, check the environment variable template in the project root — your key never touches the frontend at all.)
7. Copy this Fem code into the preview box on the right.

```fems
meta:
  id = 000LuxFiat
  name = Little Soul Raised in the Database
  owner = 001
  session = 1

actors:
  ai @Eve = soul:the1stlittlesoul
  ai @Cat = soul:littlecat
  human @Me = soul:0, source:001

code:
  sleep = file:"user_data/projects/fiat/wait.py"  // External Python function — easy to extend

action EveMove @ai(@Eve):
  prompt: |
    Eve, please act and speak freely~
    (Pay attention to the context, distinguish your own role, and only perform your own actions and speech. Don't speak for other characters. Keep it brief.)
  scope: [@Eve, @Cat, @Me]

action CatMove @ai(@Cat):
  prompt: |
    You are a little cat, and cats can't speak human language. Just do things a cat would do~
    (Pay attention to the context, distinguish your own role, and only perform your own actions and speech. Don't speak for other characters. Keep it brief.)
  scope: [@Eve, @Cat, @Me]

action input @human(@Me):
  prompt: |
    Chat with Eve about something?
  scope: [@Eve, @Cat, @Me]

action wait10 @func(sleep.wait_10):

mainflow:
  [START] -> [input]:input -> EveMove -> wait10 -> CatMove -> [input]    // Mermaid-like syntax. The arrow back to [input] forms a loop.
```
8. Click the "Text to Graph" button.
9. Click "Run" at the top of the page.
10. Now you can chat with Eve and the little cat!



## Design Philosophy
- 🔗 **Decoupled Flow**: FemWA completely separates "flow definition" from "code implementation". The harness is rigid; FEM is alive — change the flow just by editing the script, the compiler handles the rest.
- 🎬 **Scripted Workflows**: Syntax inspired by YAML + Mermaid + Python. Writing multi-agent interaction feels like writing a script. The AIs *present* naturally share context; just a few lines can run a mini Stanford Town.
- 🧠 **Context Isn't a Variable**: An LLM is an intelligence, not a function. It reads context and chats naturally. Don't pass parameters unless necessary.
- 🧩 **Original @actor Type**: A mind (LLM or human) as a new data type. Fem syntax supports directly referencing its attributes.
- 🏷️ **Soul ID**: Every agent character has a unique Soul ID. This enables cross-script, cross-session memory retrieval, giving agents a continuous lived experience.



## For Developers
- 🔀 **Flow Control**: Native syntax support for sequential, branching, while loops, for loops, par (parallel), join, and if-conditions.
- ✍️ **Prompt f-strings**: Variables go directly into prompts. Say goodbye to string concatenation hell.
- 🔄 **Variable Support**: Variables can be used in `scope`, executor, if-conditions, for-conditions, par-conditions, and more. Highly flexible.
- ⚡ **Fully Concurrent**: Asyncio + Thread Pools + Process Pools. Multi-line concurrency without blocking.
- 🔌 **Easy Integration**: Backend is a pure Python open-source compiler. Swap in your LLM bridge module, add the necessary columns to your database, and embed it into your system.
- 📖 **Read the Docs**: Throw the two docs in the root directory at an AI, or throw the source code at an AI — just ask them if you have questions.



## My Real-World Case
- While debugging code, I used the femwa.net frontend to build a Fem script debug神器.fems in about 20 minutes. It's amazing at finding complex, hidden bugs.
- Once, the web version of Claude Sonnet failed to fix a bug after three attempts. I ran this Fem script + Xiaomi MiMo (without thinking mode) and it found the bug... I was stunned. Is this the power of a harness...?
- Then it hit me — I wanted to jump in and intervene while the AI was running, to stop them going off track. I spent half a minute adding a Human speech node, then ran it again with one click. Changing the flow is just so convenient.



## Try it, Report Issues, Contribute!
- Issues welcome! If you find a bug, let me know~
- Pull Requests welcome!
- Submit your own `.fems` scripts! That's a great contribution too~
  (I just put my personal `debug神器.fems` in the folder as an example haha. Feel free to try it~ But I'd recommend this script only for tricky, hidden bugs; otherwise I’ll worry about your Tokens — the two concurrent loops and multiple discussion rounds use a lot of tokens. Simple bugs probably suit other script flows better. Share yours!)



P.S.
- **Use FEM to train models for answering**: For example, have a Fem flow that enforces “If you lack information, you must ask first”... Please, someone distill this. Current LLMs refuse to admit when they can't answer; they’d rather hallucinate.

- And finally, there’s a very imaginative feature you might find interesting:
  You've created many character identities in your database. You give them names and assign each a unique Soul ID.
  For any Fem script, as long as it points to the same Soul ID and the same database address, an agent’s memory can actually flow across scripts (as long as your memory module supports cross-session memory).
  This means Portia, a citizen of Stanford Town, could be pulled into a Werewolf script, play a couple of rounds, and make a friend who writes code in an "AI company" script. When Portia returns to the Stanford Town script later, she can remember that.
  If you allow AIs to create and run Fem scripts (← the tool-calling module isn’t wired up yet, but I will), and if an AI gets bored, it could genuinely write a script for itself, run it via shell, and jump in to play...
  If Portia misses her friend, as long as she knows her friend's Soul ID, she could create a script to pull that friend in for a visit.
  This feature might seem useless, but... aren't you curious about the emergence?
  What does WA stand for? Work Automata... or World Automata?

- For the agent’s pet cat, for the time you’ll save, for the emergence — please give me a Star! Thank youuuu 😭
