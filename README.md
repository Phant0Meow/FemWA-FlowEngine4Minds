# FlowEngineforMinds

我们做了一个编排多智能体工作流的新方式。

这是一个编排多Agent剧本的语言。后端编译器开源，方便迁移。想把你设计的工作流跑在你自己写的任何系统里，都是非常方便的。

语法原生支持多分支，串行，while循环，for循环、par并行，If条件判断。

语法简单，可以用很短的代码写出一个简易版的斯坦福小镇，设置6个AI，3个地点，并让他们自由交互。

你可能会问，简单也得学呀，我就是不想学。没关系，我们还有一个前端（待上线），你可以零代码的直接生成你想要的工作流。
然后你可以把剧本复制走，交给你自己的后端软件运行。

现在大家都在Agent Harness里设计流程来约束LLM的表现，但是Harness是死的，FEM是活的。Harness写完，你想改流程，往往需要改很多代码。而FEM，想改流程，你只需要一键。你还可以创建各种不同的流程。

后端并发支持Asyncio和线程池、进程池，可以很好地处理多线并发的情况。

Scope概念，可以用一句代码隔离上下文视角。在以往的所有工作流编排工具中，你想要隔离各个Agent的上下文，都需要写很多代码，而这里只需要一句。

可以方便地无缝嵌入人类交互和Python模块，你的工作流里可以不只有AI Agent。

如果你想把后端编译器嵌入你自己的系统，我们留了很方便的接口，你只要接入自己的记忆模块，上下文模块和LLM模块，FEM就可以在你的系统里无缝跑起来。

当你想修改工作流流程，你只需要改改fem剧本，其他一切都交给fem编译器帮你解决～

你也可以把自己创建的fem剧本封装，分发。也可以把别人分享的fem剧本拿来用。

[快速开始！] 
所以这个操作步骤够不够无脑？
1. 下载本项目，运行后端，python mainCompiler.py --server 
2. 输入端口，比如8000。
3. 进入页面 https://femwa.net
4. 页面右下角: 设置后端地址，端口输入8000，按“测试连接”，确认前后端连接成功，按“保存并连接”。
5. 右下角输入API key. （后端在你本地，传给你自己的后端，是安全的。如果你实在不放心，就去看根目录下的环境变量模板，按那个操作）。
6. 把这个fem代码复制到右侧Fem预览框。
   
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
  memfile = file:"femBridges/MemoryExample.py"
  ctxfile = file:"femBridges/ContextExample.py"
  sleep = file:"user_data/projects/fiat/wait.py"

action EveMove @ai(@Eve):
  prompt: |
    Eve请自由行动，自由说话～
    （注意看清上下文，分清你自己的角色，只进行自己的动作和语言，不要替别的角色发言。简短一点。）
  scope: [@Eve, @猫]

action CatMove @ai(@猫):
  prompt: |
    你是一只小猫，小猫不能说人话。请做小猫会做的事～
    （注意看清上下文，分清你自己的角色，只进行自己的动作和语言，不要替别的角色发言。简短一点。）
  scope: [@Eve, @猫]

action input @human(@我):
  prompt: |
    和Eve聊点什么？
  scope: [@Eve, @猫, @我]

action wait10 @func(sleep.wait_10):

mainflow:
  [START] -> [input]:input -> EveMove -> wait10 -> CatMove -> [input]



7. 按“文本生图”按钮。
8. 按页面上方“运行”。



# FlowEngineforMinds

We’ve created a brand‑new way to orchestrate multi‑agent workflows.

It’s a language for scripting multi‑agent plays. The backend compiler is open‑source and easy to port. If you want to run the workflows you design inside any system you’ve built yourself, it’s incredibly convenient.

The syntax natively supports branching, sequential execution, while loops, for loops, parallel execution (par), and if‑conditionals.

The syntax is simple. You can write a simplified version of “Stanford Town” in very few lines of code – set up 6 AI agents, 3 locations, and let them interact freely.

You might ask: “Simple or not, I still have to learn it, and I just don’t want to.” That’s fine – we also have a frontend (coming soon) that lets you generate the workflow you want with zero code. Then you can copy the script, take it away, and run it on your own backend software.

Right now everyone designs processes inside Agent Harnesses to constrain LLM behaviour, but a Harness is rigid, while FEM is alive. After you write a Harness, if you want to change the process, you often need to change a lot of code. With FEM, to change the process, you only need one click. You can also create all kinds of different processes.

The backend supports concurrency through asyncio, thread pools, and process pools – it handles multi‑threaded concurrency smoothly.

The Scope concept lets you isolate contextual perspectives with a single line of code. In every previous workflow orchestration tool, isolating each agent’s context required writing a lot of code. Here, it only takes one line.

You can seamlessly embed human interaction and Python modules. Your workflows don’t have to contain only AI agents.

If you want to embed the backend compiler into your own system, we’ve left very convenient interfaces. Just plug in your own memory module, context module, and LLM module, and FEM will run seamlessly inside your system.

When you want to modify a workflow, you just edit the FEM script. Leave everything else to the FEM compiler 💪

You can also package and distribute the FEM scripts you create, or take scripts shared by others and use them directly.

[Quick Start!]  
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
