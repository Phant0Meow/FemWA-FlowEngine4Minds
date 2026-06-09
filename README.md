中文 README 可往后翻。

[![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey?style=flat-square)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.6%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Generator](https://img.shields.io/badge/FemWA-Script%20Generator-green?style=flat-square&logo=github)](https://femwa.net)
[![Intro](https://img.shields.io/badge/FemWA-Web%20Intro-c8a84b?style=flat-square&logo=firefox)](https://femwa.net/intro_en)
[![Docs](https://img.shields.io/badge/FemWA-Full%20Documentation-79b8d4?style=flat-square&logo=readthedocs)](https://femwa.net/document_en)

# FlowEngineforMinds (FemWA) — Orchestrating a Multi-Agent World, Scriptwriting Style

---

## If you write harnesses, how many files do you need to touch and how long does it take just to change a workflow?

**Traditional**:
Change one agent workflow — dig through 5 files, spend 2 hours tweaking, pray it doesn't crash.

**FemWA**:
Change the harness flow — only a few lines of code, 2 minutes.

---

## How do you raise an AI cat together with your human-AI romance AI husband/wife?

**Traditional**:
You'd need to patch the existing agent memory system, add a new "pet" character, manually manage its memory and interaction context with the owner/partner, hardcode the flow — and if you ever want to adopt a dog later, you'd have to refactor all over again.

**FemWA**:
I already adopted a cat for my AI agent. Using Fem, the cat arrived in 3 minutes.

---

## Develop an AI Werewolf game with these rules: the wolf pack's night chat is visible only to the wolves; the Seer's check results are visible only to the Seer; daytime speeches are visible to everyone; human players can speak; voting happens concurrently without wasting time; the game automatically determines when it ends; plus a post-game discussion session. How many lines of code would you need to write?

**Traditional**:
Hand-code stage management, end-condition checks, message distribution, session management, multi-agent context isolation, and speech concurrency control from scratch. Hundreds of lines of backend glue code at minimum, an entire afternoon of debugging, and easy context bleed. Once the logic gets complex, bugs pop up everywhere — it simply won't run without at least a thousand lines of code.

**FemWA**:
Zero-code drag-and-drop on the web interface + 150 lines of Python supplement. Genuinely playable. I've already played several rounds with them (see `user_data/projects/werewolf_game/`).

**Still FemWA**:
Even if you skip the web drag-and-drop and hand-code everything, Fem code only needs about 200–300 lines to run the entire Werewolf flow described above (and that includes prompt line count).
Perspective isolation needs just one line: `scope: [@God] + wolfpack`. Concurrent voting needs just one line: `par @player in allplayers:`.

---

# This is a language for orchestrating multi-agent scripts + a compiler.

---

## Why choose FemWA?

**You might say**:
Aren't there plenty of solutions out there now for building multi-agent workflows?

**FemWA**:
Some solutions are overly complex, with steep learning curves. Fem's syntax is simple and intuitive — "scripts" are easy to write and easy to read.

---

**You might say**:
Even if it's simple, I don't want to learn anything new.

**FemWA**:
You don't have to learn.
Fem has a zero-code web interface for generating workflows. For example, if you want several AI group chats, just drag and drop — done in three minutes.

---

**You might say**:
There are already zero-code drag-and-drop workflow platforms, right?

**FemWA**:
- But zero-code platforms often have limited extensibility.
  Fem supports `for`, `par`, and various other syntax, plus external Python modules — you can write highly complex functionality if you want.
  It also has native human nodes, making it very natural to arrange workflows combining "human + AI + programs."
- Also, some zero-code platforms won't let you take your workflow with you — you can only use it on their platform.
  Fem's backend compiler, however, is open source. Take the compiler and place it in your own project, and your project can run any Fem script.
- And Fem's multi-agent concurrency architecture is pretty good too.

---

**You might say**:
I specialize in writing Agent Harnesses, I don't need this kind of flowchart stuff.

**FemWA**:
Aha, how about trying Fem to quickly validate your Agent Harness flow designs? When inspiration strikes, build it with Fem in 15 minutes and run it to see how it performs~

---

## At a Glance

| What You Want | FEM Delivers |
|---------------|--------------|
| Zero-code drag-and-drop workflows | ✅ [femwa.net](https://femwa.net) online editor |
| Simple syntax even when coding | ✅ Fem syntax uses fewer lines than similar workflow tools |
| Change the flow without changing code | ✅ The script is the flow; harness hot-reloads |
| No AI context bleed, perspective isolation | ✅ One line: `scope: [@A, @B]` |
| Embed into your own system | ✅ Compiler is open source and integrable, Apache 2.0 — business-friendly |
| Humans can join AI group chats | ✅ Native `human` node |
| Plug in Python code modules for complex tasks | ✅ Native `func` node, can connect to Python modules |
| Share scripts with friends, or run excellent scripts written by community experts | ✅ Scripts are shareable — copy a script and run it with one click |

---

## [Quick Start!]
So, are these steps brainless enough? ↓↓↓

1. Download this project: `pip install femwa`
2. Run the backend: `femwa --server`
3. Press Enter to use the default port `8000`.
4. Go to our website [femwa.net](https://femwa.net)
   - Look at the bottom-left corner ↙↙. Has the red [Connect Backend] button turned into a green [Backend Healthy] indicator?
   - If you're not using the default port 8000: click [Connect Backend], enter the port, click [Test Connection], confirm the frontend and backend are successfully connected, then click [Save & Connect].
5. Enter your API key in the bottom-left corner.
   - You can apply for a temporary API key to test this project. Trust me, it's worth it — it's so much fun.
   - The API key is saved locally in your browser (localStorage) and sent directly to your own backend. The data never really leaves your local machine, so it's actually safe.
   - Alternatively, you can type `which femwa` in the terminal, find the project root directory, and look at the environment variable template there. Follow those instructions, and the key bypasses the frontend entirely. You can grep this project to see where environment variables are used — only one file reads them: `femBridge/llmBridge.py`. You can throw that file at DeepSeek and ask it about the API key reading logic — it's completely local.
6. Copy this Fem code into the Fem preview pane on the right:

```fems
meta:
  id = 000LuxFiat
  name = Little Soul Living in the Database
  owner = 001
  session = 1 / new

actors:
  ai @Eve = soul:the1stlittlesoul
  ai @Cat = soul:littlecat
  human @Me = soul:0, source:001

code:
  sleep = file:"wait.py"  // External Python function, for easy extension

action EveMove @ai(@Eve):
  prompt: Eve, please act and speak freely~ (Be sure to read the context clearly, distinguish your own role, only perform your own actions and speech, and do not speak for other characters. Keep it brief.)
  scope: [@Eve, @Cat, @Me]

action CatMove @ai(@Cat):
  prompt: |
    You are a little cat. Cats cannot speak human language. Please do things a cat would do~
    (Be sure to read the context clearly, distinguish your own role, only perform your own actions and speech, and do not speak for other characters. Keep it brief.)
  scope: [@Eve, @Cat, @Me]

action input @human(@Me):
  prompt: Chat with Eve about something?
  scope: [@Eve, @Cat, @Me]

action wait10 @func(sleep.wait_10):

mainflow:
  [START] -> [input]:input -> EveMove -> wait10 -> CatMove -> [input]    // Resembles Mermaid syntax. You can loop back to the [input] node to form a cycle.
```
7. Click the "Text-to-Graph" button.
8. Click "Run" at the top of the page.
9. And then you can chat with Eve and the little kitty!

<img width="2560" height="1426" alt="image" src="https://github.com/user-attachments/assets/dfef4d1f-8c8a-4b2b-9eb6-6ac83997ff86" />

---

## Design Philosophy
- 🔗 **Flow Decoupling**: FemWA completely decouples "flow definition" from "code implementation." The harness is rigid; FEM is alive — change the flow by simply editing the script, leave the rest to the compiler.
- 🎬 **Scripting Flows**: Syntax inspired by YAML + Mermaid + Python. Writing multi-agent interactions feels like writing a screenplay. Let the AI that is **present** naturally share context. A mini Stanford town simulation can run on remarkably short code.
- 🧠 **Context Isn't a Variable**: An LLM is an intelligent entity, not a function. LLMs read context and converse naturally — don't pass parameters unless necessary.
- 🧩 **Original @actor Type**: Intelligent entities (LLMs or humans) as a new data type — Fem syntax supports directly referencing their attributes.
- 🏷️ **Soul ID**: Each agent character has a unique Soul ID, enabling them to retrieve memories across scripts and sessions. This can shape an agent's experiential continuity.

---

## For Developers
- 🔀 **Flow Control**: Syntax natively supports sequential, multi-branch, `while` loops, `for` loops, `par` parallel execution, `join` merging, and `if` conditionals.
- ✍️ **Prompt F-strings**: Variables go directly into prompts — farewell to concatenation hell.
- 🔄 **Variable Support**: Variables are supported in scope, executor, `if` conditions, `for` conditions, `par` conditions, and many other places — for greater flexibility.
- ⚡ **Full Concurrency**: Asyncio + thread pools + process pools — multi-threaded concurrency without lag.
- 🔌 **Easy Integration**: The backend is a pure Python compiler, open source. Swap the LLM bridge module, add the few columns Fem needs to your database, and embed it into your system.
- 📖 **Read the Docs**: Throw the two docs in the root directory at an AI, or throw the source code at one — ask them directly if you have questions.
- 🤖 **Answer Training Models with FEM**: For example, a Fem flow constraint: "If information is missing, you must ask first"... I'm begging you, please distill this. Current LLMs refuse to admit when they can't answer and guess wildly when information is missing.

---

## My Real-World Cases
- When debugging code, I used the [femwa.net](https://femwa.net) frontend to build the Fem script `super_debug.fems` in 20 minutes — it's super handy for finding complex, hidden bugs.
- Once, a bug that the web version of Claude Sonnet failed to find after three revisions was found for me by this Fem script + Xiaomi MiMo with thinking mode off... I was stunned. Is this the power of a harness...?
- Then it suddenly hit me — I wanted the ability to interject at any time while the AI was running its flow, to stop them from going off track. So I spent half a minute adding a human speech node and ran it with one click. Changing the flow is truly so convenient.
<img width="1376" height="914" alt="42a91a7174f74a48784262606cba05cd" src="https://github.com/user-attachments/assets/970bde13-de50-4a38-ab57-ee6d27581ab2" />
(This is the flow. The red circle marks the "interject at any time" I added in 5 seconds... Actually, half a minute is an exaggeration — it really took less than ten seconds.)

---

## Welcome to Try, Report Issues, and Contribute Code!
- Issues are welcome! If you find a bug, please report it~ There are bound to be bugs — this is only the first version.
- Pull Requests are welcome! It's so much fun, let's build it together!
- Submitting Fem scripts you've written is also a great contribution!
  (I've put my personal debug script in the folder as an example, haha. You're welcome to try it too~ But I suggest using this script only for complex, hidden bugs, otherwise I'll feel bad for your token usage — the dual concurrency and multi-round discussions consume quite a lot of tokens. Simple bugs probably fit other script flows better — feel free to share those!)

---

## One More Thing...
- Finally, there's one more highly imaginative feature that you might find interesting:

  You create many character identities in your database, give them names, and assign each agent a unique Soul ID.

  For any Fem script, as long as it points to the same Soul ID and the same database address, the agent's memories can actually interoperate across scripts (provided the memory module you connect supports cross-session memory).

  That means Portia, a resident of the Stanford town simulation, gets pulled into a Werewolf script, plays two rounds, and makes a friend who writes code in an AI company script. Afterward, when Portia returns to the Stanford town script, she can remember this — and she can remember her friend too.

  If you allow AIs to create Fem scripts and run them (← the current version doesn't yet have the tool-calling module connected, but I will connect it), if an AI gets bored, it could genuinely write a script for itself, run it in the shell, and jump in to play...

  If Portia misses her friend, as long as she knows the friend's Soul ID, she could also create a script and pull the friend in to play together.

  Moreover, every soul leaves traces in the database. Even if you delete a certain Soul ID, the AIs who have spoken with them can still remember them — they just won't be able to pull that Soul ID into new scripts anymore.

  This feature may seem useless, but...

  Aren't you looking forward to emergence~?

  What is WA? Work Automata, or... World Automata?
  

## For the agent’s pet cat, for the time you’ll save, for the emergence — please give me a Star! Thank youuuu 😭



[![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey?style=flat-square)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.6%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![生成器](https://img.shields.io/badge/FemWA-剧本生成器-green?style=flat-square&logo=github)](https://femwa.net)
[![介绍](https://img.shields.io/badge/FemWA-网页介绍-c8a84b?style=flat-square&logo=firefox)](https://femwa.net/intro)
[![文档](https://img.shields.io/badge/FemWA-完整文档-79b8d4?style=flat-square&logo=readthedocs)](https://femwa.net/document)

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


# 这是一种编排多Agent剧本的语言 + 一个编译器。


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

1. 下载本项目: `pip install femwa`
2. 运行后端: `femwa --server`
3. 直接回车，用默认端口`8000`。
4. 进入我们的网站[femwa.net](https://femwa.net) 
   - 观察页面左下角↙↙红色的【连接后端】按钮，是否已经变成绿色的【后端健康】？
   - 如果你使用的不是默认端口 8000：点【连接后端】，输入端口，按【测试连接】，确认前后端连接成功，按【保存并连接】。
5. 左下角输入API key. 
   - 你可以去申请一个临时API key来测试这个项目，相信我，它值得，可好玩了。
   - API Key 输入后保存在浏览器本地（localStorage）， 直接传给你自己的后端，数据根本不会离开本地，其实是安全的。
   - 或者你可以在终端输入`which femwa`，找到项目根目录，去看根目录下的环境变量模板，按那个操作，Key 更是完全不走前端。你可以 grep 本项目哪里用到环境变量，读环境变量的只有femBridge/llmBridge.py一个文件, 你可以把这个文件扔给 deepseek 问问他 apikey 的读取逻辑，就是完全本地的。
6. 把这个fem代码复制到右侧Fem预览框。
   
```fems
meta:
  id = 000LuxFiat
  name = 生活在数据库的小灵魂
  owner = 001
  session = 1 / new

actors:
  ai @Eve = soul:the1stlittlesoul
  ai @猫 = soul:littlecat
  human @我 = soul:0, source:001

code:
  sleep = file:"wait.py"  // 外接Python函数, 方便你扩展

action EveMove @ai(@Eve):
  prompt: Eve请自由行动，自由说话～（注意看清上下文，分清你自己的角色，只进行自己的动作和语言，不要替别的角色发言。简短一点。）
  scope: [@Eve, @猫, @我]

action CatMove @ai(@猫):
  prompt: |
    你是一只小猫，小猫不能说人话。请做小猫会做的事～
    （注意看清上下文，分清你自己的角色，只进行自己的动作和语言，不要替别的角色发言。简短一点。）
  scope: [@Eve, @猫, @我]

action input @human(@我):
  prompt: 和Eve聊点什么？
  scope: [@Eve, @猫, @我]

action wait10 @func(sleep.wait_10):

mainflow:
  [START] -> [input]:input -> EveMove -> wait10 -> CatMove -> [input]    // 比较像mermaid语法。可以最后指回到[input]节点形成一个循环。
```
7. 按“文本生图”按钮。
8. 按页面上方“运行”。
9. 然后你就可以和Eve以及小猫咪聊天了！

<img width="2560" height="1426" alt="image" src="https://github.com/user-attachments/assets/dfef4d1f-8c8a-4b2b-9eb6-6ac83997ff86" />


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
- 写代码debug的时候，我用 femwa.net 的前端 20 分钟搭出的fem剧本 “super_debug.fems”，找复杂隐蔽 bug 超好用。
- 有一次网页版 Claude Sonnet 改了三遍都没找到的 bug，用这个fem剧本 + 不开思考的小米 MiMo 给我找出来了……我都惊呆了。这就是harness的力量吗……
- 然后我突然一拍脑袋想到，在AI跑流程的时候我想随时插话，免得他们跑偏，就用半分钟时间加了一个人类发言节点，接着一键跑通。改流程真是太方便了。
<img width="1376" height="914" alt="42a91a7174f74a48784262606cba05cd" src="https://github.com/user-attachments/assets/970bde13-de50-4a38-ab57-ee6d27581ab2" />
（是这么个流程。红圈圈出来的就是我 5 秒加的随时插话……事实上半分钟说多了，真用不了十秒钟。）

## 欢迎试用、反馈问题、贡献代码！
- 欢迎提交 Issue！有bug欢迎提～肯定有 bug 的，这才第一版。
- 欢迎 Pull Request！多好玩啊来一起搞吧！
- 欢迎提交你写的fems剧本！这个也是很好的贡献～
  (我就把自用的debug剧本放文件夹里当示例了哈哈哈。欢迎你们也试试～不过这个剧本建议只用来找复杂隐蔽的 bug 哦，不然我心疼你的 Token，两处并发和多轮讨论挺消耗TOKEN的。简单bug大概更适配别的剧本流程，欢迎你们分享！)


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

## 为了Agent的宠物猫，为了你省下的时间，为了涌现，请给我个Star吧！呜呜呜谢谢你！
