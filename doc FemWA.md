# Flow Engine for Minds - Work Automata (FemWA)
# Syntax Specification & Playbook Authoring Guide (User Manual)

## Core Design Philosophy

1. **Scope = Space / Field of View (Physical compartment)**
   Only actors in the same scope share context (conversation history). Actors in different scopes are naturally isolated and invisible to each other.
2. **Vars = Control parameters**
   Used to control the direction of the flow diagram and the actors' field of view.
3. **Context is not a variable**
   What humans and AIs share is context. Unless you need programmatic variable manipulation, actors do not need to pass variables explicitly for dialogue—it is enough that they can see the same context.
   Do not require the AI to output variables unless necessary, so as not to interrupt its train of thought. Remember: **Context is not a variable**.

## Basic Conventions
- **File extension**: FEM language files use the extension `.fems` (s for script). The compiler reads `.fems` files and parses them according to the rules we have agreed upon.
- **Indentation**: Indentation‑sensitive. Indentation indicates subordination (which prompt belongs to which @agent, which branch belongs to which fork).
- **Line breaks**: Partially line‑break‑sensitive. In constructs such as `fork`, `for`, `par`, you must strictly follow the prescribed line‑break and indentation format.
- **Case**: Case‑sensitive. Variable names and action names are case‑sensitive.
- **Comments**: Inline comments can use `#` or `//`.
- **@ symbol**: Actor entity names always carry `@`. You must keep the `@` when defining, referencing, and passing parameters, otherwise the compiler will not recognise it as an @actor type.
- **File paths and text values**:
  All text fields (`system_safety`, `output_style`, `prompt`, `code` paths, etc.) follow these rules:
  - `file:"path/to/file"` → reads the file content (errors if the file does not exist)
  - bare text (no quotes or ordinary quotes) → literal string
  - `|` followed by a newline and indented block → multi‑line literal string

### Quick Symbol Reference

| Symbol | Semantics | Example | Mnemonic |
|---|---|---|---|
| `action` | Define an action | `action wolf_kill @ai(wolf)` | Like Python `def` |
| `@` | Reference / point to | `@wolfClaire`, `@ellis.type` | @someone |
| `()` | Action parameters / input | `@ai(wolf)`, `@func(sys.spawn)` | Function parameters |
| `[]` | Node label | `[A]`, `[START]` | Location marker |
| `{}` | Variable substitution | `{alive_players}` | Template interpolation |
| `<<>>` | Output signal | `<<VOTE: 3>>` | Signal flare |
| `&` | Module reference | `&CoderSandbox(...)` | Pack and bring |
| `->` | Flow connection | `[A] -> [B]` | Direction |

For the convenience of Chinese input, the following characters have the same grammatical effect in FEM:

| Convenience symbol | English symbol | Explanation |
|-|-|-|
| `：` | `:` | colon |
| `，` | `,` | comma |
| `“` `”` | `"` | quotation marks (recognised for file paths and text) |
| `（）` | `()` | parentheses |
| `【】` | `[]` | square brackets |
| `｜` | `|` | vertical bar |
| `--` | `->` | Flow link symbol |

Note:
- `--` is equivalent to `->` only within the flow region; it is not affected inside prompts.
- Other Chinese punctuation marks are globally equivalent to the corresponding English symbols in `.fems` playbook syntax.

## 1. Overall Playbook Structure

Organise in the following order:

meta:   # Playbook metadata area
vars:   # Global state variable area
code:   # External Python code area
actors: # Actor definition area
memory: # Memory retrieval method definition (optional)
context:# Context extraction method definition (optional)
action: # Action definitions (can be multiple)
module: # Module definitions (can be multiple)
mainflow:   # Main flow orchestration

## 2. Metadata (meta)

Defines basic playbook properties and the runtime environment.

meta:
    name = "My Werewolf"
    version = 1.0
    owner = [1, 2]
    database = file:"werewolf.db"
    session = new
    system_safety = |
    Do not delete the database.
    Do not violate laws or commit crimes, do not generate dangerous content, do not discriminate against women.
    output_style = "Please reply concisely and professionally"

Field descriptions:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | text | No | Playbook name, written to `sessions.title` when creating a new session |
| `version` | text | No | Version number |
| `owner` | array of integers | No | user_id list of the playbook owner(s) in the database, automatically injected into the user_scope of every memory record |
| `database` | file path | No | SQLite database path. Defaults to `./dialog.db` if not specified |
| `session` | integer / `new` | No | session_id to run. Automatically creates a new one (max+1) if not specified or set to `new`. Errors if the specified number does not exist |
| `system_safety` | text / file path | No | Safety notice, automatically injected into context |
| `output_style` | text / file path | No | Output quality requirement, automatically injected into context |

The `owner` information is read from the database's user table and the compiler generates `blocks['user_info']`, for example:

[User @Alice info]
Prefers concise answers, backend engineer.

[User @Claire info]
Prefers detailed explanations, frontend engineer.

## 3. Global Variable Pool (vars)

Global state that all nodes can read and write. Variables must be declared here first, otherwise assignment will cause an error.

vars:
    turn_count = 1
    alive_players = [@seer, @wolf]
    agent_locations = {@ellis: "Bedroom", @bob: "Park"}
    game_over = false
    @speaker = ""
    hp = {@wolfClaire: 100, @Seer: 100, @player: 100}

- **Necessity of declaration**: If an action uses a variable not declared in `vars`, the parser will report an error.
- **Dictionary default value**: When using `dict[key]` in a prompt and the key does not exist, it resolves to an empty string `""`, no error.
- **Actor type variables**: You can define an @actor‑type variable and assign it to a person. For example, `@speaker = @Seer`. Empty values use an empty string `""`.
  Note: actor‑type variables must always begin with `@`, otherwise they cannot be recognised as @actor type.

## 4. External Code (code)

Import Python files for use by `@func` and `resolve`.
FEM can declare external Python files in the `code:` region and then call them in actions:

**Paths must use the `file:"..."` format**. The following names are reserved and cannot be used as aliases:
`meta`, `vars`, `code`, `actors`, `action`, `module`, `flow`, `mainflow`, `memory`, `context`

code:
    game_logic = file:"utils/game.py"
    dev_ops = file:"utils/deploy.py"

## 5. Actor Definitions (actors) and @actor Type Variables

Uses a strongly‑typed declaration style `Type variable_name = properties`. Actor names always begin with `@`.

actors:
    ai hostgod = soul:0, source:deepseek
    ai wolfbob = soul:1, source:glm5.1, tools:[deep_think]
    ai Seer = soul:2, source:glm5
    human player = soul:9, source:0

Notes:
- You must write `actors:` with the next line indented.
**Actor entity names always carry `@`; never remove it anywhere in the code.**
  When defining: `ai @ellis = soul:1`
  When referencing: `@ai(@ellis)`, `scope: [@ellis]`
  When passing as a variable: `@speaker = @ellis`
  When assigning from AI output: if assigning to an @actor, the variable name must also begin with `@`, otherwise it cannot be recognised as an @actor type.
  You can think of `@` as part of the variable name, just as you wouldn’t write Alice as lice, you shouldn’t write @Alice as Alice.
- When defining an @actor entity, it must start with `ai` or `human`; these two are reserved words.
- Names support Chinese characters.
- `soul:ID` – a unique identifier used for scope location and database queries, corresponding to the character with the same soul id in the database’s souls table. The database also stores the character’s system prompt; the compiler will automatically retrieve it and generate `blocks['soul']`.
- `source`: For AI, write the model name (can be omitted for random assignment); for humans, write a number, corresponding to the specific person in the database’s user table.
- Special case: when a human source is 0, it represents a human user without an admin perspective, who only has the soul’s point of view.
  This is suitable for situations like being a werewolf game player who cannot open the admin view with any positive integer human source.
- `tools`: sets the tool list mounted for this AI character, e.g., `web_search`, `deep_think`.

Not yet implemented TODO: **Blueprint actors** (dynamically generated templates):
blueprint coder:
    source: ai-glm5
    tools: [code_interpreter]
Blueprints do not specify `soul`; they are dynamically allocated at runtime by `system.spawn`.

### Actor Type System and Entity Access

In FEM, an Actor is not just a character configuration; it is a **variable type**. It represents the "executor" entity, with identity and state.

**Assignment**
It can be assigned and passed around like a variable in `vars`:

vars:
    current_speaker = @seer           # Actor-type variable
    alive_players = [@seer, @wolf]    # Array of actors
    locations = {@ellis: "Bedroom"}   # Dictionary keyed by Actor

- In Flow and Action, you can use `@variable_name` to retrieve this Actor entity, or directly use `@character_name` to reference it.
- For example, if you have already assigned @ellis to @speaker, then:
action give_a_speech @ai(@speaker):
is equivalent to:
action give_a_speech @ai(@ellis):

@speaker.type 
is equivalent to 
@ellis.type

- f‑strings are supported:
prompt："The current speaker is {@speaker}."
The prompt the AI actually receives will be resolved to: The current speaker is @ellis.

**Entity property bidirectional access** (dictionary view vs. entity view):

FEM introduces a two‑way perspective similar to a database’s “row/column” view. Suppose we define a dictionary in `vars`:
vars:
    hp = {@wolfClaire: 100, @Seer: 100, @player: 100}
    salary = {}
When we want to read or modify @wolfClaire's hp, there are two completely equivalent ways to write it:
1. **Dictionary view (column lookup)**: `hp.@wolfClaire` — in the hp roster, flip to wolfClaire's page.
2. **Entity view (row lookup)**: `@wolfClaire.hp` — wolfClaire as a person, what is their hp.

**These two forms are completely equivalent in FEM and can be used freely depending on context**
- In prompts: `"Your current HP is {hp.@wolfClaire}"` has exactly the same effect as `"Your current HP is {@wolfClaire.hp}"`.
- In AI output signals: `<<hp.@wolfClaire: += 30>>` and `<<@wolfClaire.hp: -= 30>>` are both fine.
- In action assign statements: `salary.@ellis = 5000` and `@ellis.salary = 5000` are both fine.

#### Static properties vs. dynamic properties
Since `@entity.property` can access dictionaries, does it conflict with the properties defined at actor definition time (like `@wolfClaire.soul`)?
Rule: Static properties take priority; reserved words cannot be overridden. When resolving `@entity.property`, it first checks the following 5 reserved static properties; if none match, it looks up a dictionary with the same name in `vars`.
| Reserved property | Meaning | Example value |
|---|---|---|
| `type` | Character type | `"ai"` or `"human"` |
| `soul` | Character ID | `1` |
| `source` | Model / origin | `"glm5.1"` or `0` |
| `tools` | Mounted tools | `["deep_think"]` |
| `name` | Character name | `"wolfbob"` |
For example:
- `@wolfClaire.soul` -> soul hits a reserved word, returns the static property `1`
- `@wolfClaire.hp` -> hp is not a reserved word → automatically looks up the `hp` dictionary in vars, returning the value of `hp.@wolfClaire`
- `@ellis.salary` -> salary is not a reserved word → automatically looks up the `salary` dictionary in vars, returning the value of `salary.@ellis`

This design means:
**You don’t need to modify the actors definition to attach state to a character; just create the corresponding dictionary in vars, and you can access it intuitively via `@entity.property`.** The actor's identity is static, but its state is dynamic and infinitely extensible.

## 5. memory and context Definitions (sibling to action/module)
### 5.1 Defining Methods
memory method_name(module_alias.function_name):
    in: param1, param2, @actor
    out: return_variable(type)

context method_name(module_alias.function_name):
    in: session, @actor
    out: return_variable(type)

### 5.2 Parameter In/Out Conventions
Parameters declared in `in:` are passed by name when calling the user's Python function:
| Reserved field | Value |
|-|-|
| `prompt` | The current action's prompt (with variables already substituted) |
| `@actor` | The current speaker's actor_info dictionary, e.g., `{"soul": 1}` |
| `session` / `session_id` | Current session ID |
| `turn` / `turn_id` | Current turn ID |
| Others | Values taken from global `vars` |
* When `@actor` is passed to a Python function, the parameter name is automatically mapped to `actor_info`.
* The user‑defined function's `def` signature should match the `in:` declaration and the mapping above.
out:
The return value of the user‑provided context or memory function is blindly assigned to the variable declared in `out:` and placed into the corresponding block ("memory" or "context"), making it convenient for external code to call.
Therefore, the user‑provided function must return the context or memory text in a format (plain text or JSON) that can be sent directly to the AI.
If the return value is not set correctly, the context the AI sees will probably be strange—anyway, it is assigned blindly here without validation.
The variable must first be declared in `vars:`.

### 5.3 Referencing Methods in an Action
action speak @ai(@ellis):
    prompt: "Hello"
    memory: method_name
    context: method_name
* If an action does not specify `memory:`, the first defined memory method is used.
* If no memory method is defined at all, the `memory` block is empty.
* If an action does not specify `context:`, the first defined context method is used.
* If no context method is defined, the built‑in default implementation (extracting the current session context) is used.

## 6. Action Definitions (actions)

An Action is a behavioural unit describing "what to do". It has no location information itself.
Use the `action` keyword to define, format: `action action_name @executor_type(executor_parameter):`

### 6.1 AI Action
action wolf_kill @ai(@wolf):
    prompt: |
        It is night {day_count}, alive players: {alive_players}.
        You are a werewolf, please choose a target to kill. You may provide some analysis:
        After your analysis, you must output SET VARIABLE: << KILL = @player_name >> Replace @player_name with the @name of the player you want to kill.
    scope: [@hostgod, @wolf]
    out: wolf_target(string, "Kill target")
    resolve: game_logic.resolve_target(arg1, arg2)
    max_retries: 3
    fallback: host_emergency
    context: method_name
    memory: memory_method_name
    interrupt: human_interrupt_branch

Field descriptions:

- **`(actor_expr)`**: The actual executing role, can be a static character name or a dynamic variable (e.g., `@speaker`).
When the action's role uses a dynamic variable and is reused in a loop, the loop variable must match the identity inside the parentheses of the action definition.
For example, defining `action @ai(@wolf)`, then:
`for @wolf in [...]` is OK,
`for @speaker in [...]` is not OK and will error, because @speaker does not match @wolf.
This design exists because an action is not a function after all; it is an AI speech turn based on a prompt, and each action's prompt is fixed. So if someone other than @wolf, like @seer, comes in, using the wrong person could cause confusion.
If you really want greater flexibility, you can define `action .. @ai(@role)` and globally use `for @role in [...]` … but this reduces the clarity of role identity, and I personally think it is not beneficial for long‑term maintenance of your playbook microworld.

- **prompt**:
  Supports `{var}` variable substitution.
  The art of prompt engineering exists here: you can guide the AI in the prompt to produce better output that suits the flow.
  (For example, if you wrote a werewolf game but didn't bother to add an action to check whether the night‑speaking character is still alive, you could directly write in the prompt: You are {@speaker}, currently alive players are {alive}. If you are already dead, do not speak, do not output variable assignments.)
  However, AIs hallucinate; if you require precise flow control, it is better to use variable assignments and actions and write your own flow to control the process.

- **`memory`**: References a defined memory method, e.g., `rag10`. If not specified, the first defined memory method is used.
- **`context`**: References a defined context method; if not specified, the first defined context method is used. If no context method is defined, the FEM system's built‑in context method is used.

- **Context and scope**: [@character_name1, @soulname2]
  - Simple understanding:
  Defines the "room" where this action takes place. Only the soul:IDs appearing in this list can see the context of this round of conversation.
  Supports dynamic variables. For example, `scope: [{playersInPark}]` means all characters currently in the park can see this message.
  When writing a playbook and setting the scope, simply write the characters present in the room; it is a very intuitive way of writing.
  When the action executes, the variable `playersInPark` is resolved in real‑time to the current constant `[@agent1, @agent2]`, without retaining the variable reference.
  - Developer perspective:
  All chat records are generated by actions. When the system stores a chat record, it simultaneously stores the entities that joined the action's scope:
     The character's corresponding soul id is stored in the database's `soul_scope` field.
     The human user identity is stored in the record's `user_scope` field (except for source 0, which is not stored).
  This makes it convenient later to selectively display context and memory, and to easily isolate contexts.
  The "room" metaphor is only for easy understanding; it is actually equivalent. A more accurate metaphor is: God stores all of the world’s history onto the universe's hard drive, but only those who personally experienced a piece of history are qualified to retrieve it.
  The built‑in context method that comes with the FEM module supports retrieving context by scope by default. If you don't write a context method and run the FEM project directly, by default the character can only see chat records within its own scope.
  Furthermore, besides context, if you have long‑term memory retrieval needs, you can also use the scope field in the database within your memory retrieval algorithm to separate memories per character, so that each character only has their own memories and does not recall events that happened to other characters.

- **`in`** (explicit variable passing, optional):
  Determines which variables the action's prompt can access. There are two modes:
  1. **Automatic mode (default)**: The action does not write `in:`, and all `{var}` in the prompt are automatically replaced with the values of **global** variables.
  2. **Explicit mode**: The action writes `in:`, and only the variables listed in `in:` are passed into the prompt and substituted.
     Format: `in: display_name = global_variable_name`, for example:
       in: my_task = task_list[@coder_1]
     In the prompt, use `{my_task}` to reference it; the engine replaces it with the value of `task_list[@coder_1]`.
     Variables not listed in `in:` are not substituted, and `{var}` remains as literal text.
     This is to **control the scope of information exposure** and prevent the AI from seeing data it shouldn’t.
- **`out`** (AI output variable declaration):
  Declares the variables this action requires the AI to output. Format: `variable_name(type, "label")`.
  The AI must output the value of this variable in its response using the format `SET VARIABLE: <<variable_name = value>>`.
  The variable must have been pre‑declared in `vars:`, otherwise the engine will error upon assignment.
  `type` (e.g., `string`, `enum([a,b])`, `dropdown`) and `"label"` are reserved fields; in the current version they only serve as markers, without automatic validation or front‑end rendering.
  Dictionary keys can be written, e.g., `vote_results.@voter(string, "")`, to store the value into a specific key of a dictionary.

- **AI‑initiated variable assignment**
  If you need the AI to assign a value, you must instruct the AI in the prompt to output the variable assignment signal `SET VARIABLE: <<VARIABLE_NAME = value>>`.

- Assignment statement
  The AI outputs a signal via `SET VARIABLE: <<variable_name = value>>`; the parser extracts it and performs the assignment. The following operations are supported:
| Format | Meaning |
|---|---|
| `SET VARIABLE: <<VAR = value>>` | Direct assignment |
| `SET VARIABLE: <<VAR += N>>` | Add N |
| `SET VARIABLE: <<VAR -= N>>` | Subtract N |
| `SET VARIABLE: <<VAR = add(element)>>` | Append to list |
| `SET VARIABLE: <<VAR = remove(element)>>` | Remove from list |
- Output examples:
  I think player 3 is suspicious, I vote for player 3. SET VARIABLE: <<VOTE_TARGET = @player3>>
  I think this needs a price increase. SET VARIABLE: <<Price += 200>>
  My character is soul1, I also went to the park. SET VARIABLE: <<playersInPark = add(@soul1)>>
  I left the park. SET VARIABLE: <<playersInPark = remove(@soul1)>>
  I used a healing skill on a random person～ SET VARIABLE: <<@randomplayer.blood += 10 >>

- Chinese support
| Chinese support | English support | Description |
|-|-|-|
| `SET VARIABLE:` | `设定变量：`    | Assignment output from AI |
| `《` `〈` `《《` | `<<` | AI output assignment marker start |
| `》` `〉` `》》` | `>>` | AI output assignment marker end |
Correct examples:
    SET VARIABLE: <<KILL = @Olivia>>
    设定变量：<< KILL = @Olivia>>
    设定变量：《KILL = @Olivia》
    SET VARIABLE: <<SCORE += 1>>
    SET VARIABLE: <<TASKS = add(@Alice)>>
    SET VARIABLE: <<DEAD = remove(@Portia)>>
Notes:
- The prefix `SET VARIABLE:` or `设定变量：` are both acceptable.
- Inside the brackets, `=` , `+=`, `-=`, `= add()`, `= remove()` etc. are supported.
- The expression must end with a closing symbol like `>>` or `》`.
- `《》` is equivalent to `<<>>` only within AI output assignment recognition.
- The colon `：` after a Chinese prefix is equivalent to the English `:`, no distinction needed.

- **Assignment parsing flow**
  1. The engine scans the AI’s full response and finds all statements in the `SET VARIABLE: <<...>>` format.
  2. It attempts to parse the assignment expression inside `<<...>>` one by one.
  3. Those that parse successfully directly manipulate the variable value (same as `@assign`).
  4. Those that fail parsing are stored in order into a list named `SET_VARIABLE`.
  5. If the action did not declare a `resolve` function, the failed assignments are simply discarded and the engine prints a warning.
  6. If the action declared a `resolve` function, and the user wrote `SET_VARIABLE` in the parameters,
     the engine passes the `SET_VARIABLE` list as‑is to that function, allowing the user to parse and handle it themselves.
  7. The `resolve` function returns a list of triples; the engine decides whether to accept the assignment based on this.
  8. If `resolve` also fails to parse (returns `is_success = False`), the assignment fails, and the engine returns an error message.

  Rules for passing the `SET_VARIABLE` list:
  - Only when the user explicitly writes `SET_VARIABLE` in the parentheses of `resolve` does the engine pass the list.
  - If the user does not write it, even if there are items that failed to parse, they are not passed to the `resolve` function.
  - This allows the user to decide for themselves whether they need to handle the AI's non‑standard output format.

**`resolve`** (validation/parsing function):
- Optional. The FEM compiler can only perform the most basic format checks on variable assignments. If you have more complex assignment requirements,
  or you want to accommodate the AI's non‑standard output formats, you can set a function here to handle it.
- Call format: `resolve: module_alias.function_name` or `resolve: module_alias.function_name(param1, param2, ...)`
- The function is provided by the user in the `code:` area. Users should follow this standard when writing it.
- Explicit parameter mode (parameters inside parentheses):
    `resolve: game_logic.resolve_target(KILL, alive_players, SET_VARIABLE)`
    The parameter names inside the parentheses must be found in one of the following three places, otherwise the engine errors:
    - Global variables declared in `vars:`
    - Variables declared in the current action's `in:`
    - The special value `SET_VARIABLE` (the original text list of assignments that failed to parse)
    The engine passes the corresponding values as keyword arguments to the function in the order declared by the user.
    If the user writes `SET_VARIABLE`, the engine passes the list of failed parses; if they don’t, it is not passed.

- Automatic parameter mode (no parameters inside parentheses, compatible with older styles):
    `resolve: game_logic.resolve_target`
    The engine automatically passes the following keyword arguments:
    - `prompt`: the prompt text of the current action
    - `llm_output`: the full original text of the AI's response
    - `SET_VARIABLE`: the list of assignment original texts that failed to parse (if any)
    - plus all variables declared in `in:`

- The function return should be set as a **list of triples**, with each triple corresponding to one out variable:
    `[(is_success, show_to_ai, feedback), ...]`
    - `is_success`: whether this assignment is accepted (`True`/`False`)
    - `show_to_ai`: whether to show the feedback information to the AI (**reserved in current version, not yet effective**)
    - `feedback`: feedback text (**reserved in current version, not yet effective**)

- Example of a user‑provided function module:
    def resolve_target(KILL=None, alive_players=None, SET_VARIABLE=None, **kwargs):
        if KILL and KILL in alive_players: # first try the result from built‑in parsing
            return [(True, False, "")]
        if SET_VARIABLE: # built‑in parsing failed, search SET_VARIABLE myself
            import re
            for item in SET_VARIABLE:
                m = re.match(r'KILL\s*=\s*@(\w+)', item)
                if m and f"@{m.group(1)}" in alive_players:
                    return [(True, False, "")]
        return [(False, True, "Target not in alive players, please re‑select.")]

Not yet implemented · Planned TODO:
- `show_to_ai`: whether the result of this round is shown back to the AI.
  True = tells the AI whether the assignment result succeeded, which costs one extra round of LLM call; this turn's dialogue record is also stored in the conversation history.
  False = after the AI output, you do not plan to send the assignment result back to it, saving a round.
- `feedback`: feedback message. If you set an f‑string for feedback in the prompt, then if you send it to the AI again, it will see it.
  Suitable for situations where the assignment fails and you want to remind the AI how to assign correctly.
- In the current version, the return value of `resolve` is only used to decide whether to accept the assignment. **The retry mechanism has not yet been implemented.**
  The `max_retries` and `fallback` fields are reserved, but the engine will not automatically retry.
  It is planned that in a future version, after a validation failure the AI will be called again with the feedback.

- **`max_retries`**: Optional. Maximum number of retries when validation fails; after exhaustion, goes to `fallback`.
  `max_retries = 0` means no retry, directly go to fallback.
- **`fallback`**: Optional. The action or module to jump to after retries are exhausted; can be left unspecified (terminates with error).

Planned TODO:
- **`interrupt`** (interrupt condition, optional):
Declares under what conditions the current round of AI output can be interrupted.
Behaviour when interruption occurs: stop AI output → pending tool calls are not executed → mark [Interrupted] → inject into AI context.
Supports multiple trigger sources:
1. **Human interruption**: By default, any human speech interrupts.
2. **Variable condition**: Interrupt when a global variable satisfies a condition, e.g., `interrupt: night == true`
3. **External Python module**: Complex condition, executes a Python function; interrupts if it returns True: `interrupt: game_logic.check_interrupt`
4. Special parameter: To specify that certain humans do not interrupt: `interrupt: HUMAN_EXCEPT(@ellis, @bob, @1)`. If you write `interrupt: HUMAN_EXCEPT`, it means no human can speak to interrupt.

### 6.2 Human Action

action human_vote @human(@player):
    prompt: "Please vote:"
    scope: [@hostgod, {alive_players}]
    out: vote_target(dropdown, choices={alive_players}, label="Vote")
    resolve: game_logic.resolve_human_vote

- The syntax is basically the same as for @ai.
- `dropdown` in `out` maps to a front‑end UI component.
- A human action **may optionally** have resolve (e.g., if game rules require humans to make compliant moves too).
- Human actions **have** context; the context syntax is the same as for AI actions.
- Human actions do not need memory; humans come with their own powerful memory.

It also allows a human player to play a specific AI role, inheriting that role's field of view (scope):
action seer_act_human @human(@player) as (@Seer):
    prompt: "You are now the Seer. Who do you want to inspect?"
    scope: [@Seer, @hostgod]   # The player enters the Seer's private channel

### 6.3 Lightweight Assignment (@assign)
Supports `=` (direct assignment), `+=` (add), `-=` (subtract), `= add()` (list append), `= remove()` (list remove).
action next_turn @assign:
    out: day_count += 1

action reset_scene @assign:
    out: current_scene = "Tavern"

action add_player @assign:
    out: playerInPark = add(@Alice)
         playerInMarket = remove(@Alice)

Does not call the LLM.
Variables must have been declared in `vars:`, otherwise the engine errors.
assign only supports simple assignment operations; for function calls use `@func`.

### 6.4 Python Function Call (@func)

`@func` is used to call functions in the Python files declared by the user in the `code:` region.
#### 1. Basic Usage
First declare the module in the `code` area, then call using `module.function_name`:
code:
    my_utils = file:"utils/game.py"

action tick @func(my_utils.wait_and_tick):
    in: hour
    out: hour, mood

- `in` lists the variables to pass to the function. If the variable name matches the function parameter name, just write it directly; if they differ, use `param_name = variable_expression`.
- `out` declares the variables that receive the return values, automatically mapped according to the function’s return structure.
**Core principle**: Whatever `in` gives, the function receives; whatever the function returns, `out` receives. The compiler will blindly assign without conversion.

#### 2. Input Parameter Passing (in)

Supports two modes: explicit declaration and automatic inference.
**Explicit declaration**:
Write `in:` in the action; the engine strictly passes parameters according to the declaration.
action check @func(my_utils.check_soul):
    in:
        target_name = seer_check_target
        souls_dict = souls
    out: seer_check_result
On the left are the Python function's parameter names, on the right are FEM global variable expressions. The compiler first evaluates the expression on the right, then passes the value to the corresponding parameter on the left.

**Automatic inference**:
When an action does not write `in:`, at runtime, based on the Python function's parameter signature, the engine looks for variables with **the same name** in the global `vars` to pass in.
Fuzzy matching is not supported. If a variable with the same name cannot be found and the parameter has no default value, the engine errors and exits; if a default value exists, the parameter is skipped.

#### 3. Output Reception (out)
Regardless of what the function returns, the compiler stuffs the result into the variables declared in `out` according to the following rules.
**Function returns a dictionary**
If a Python function returns a `dict`, the compiler matches the variable names declared in `out` by key name and writes the corresponding values.
- Python function
def resolve_night(kill_target, save, ...):
    return {"dead_tonight": dead, "alive": new_alive}
- FEM playbook
action resolve @func(my_utils.resolve_night):
    in: kill_target, save
    out: dead_tonight, alive

- The keys of the returned dictionary must be **exactly identical** to the variable names declared in `out`, and the counts must be equal.
- If the returned dictionary contains a key not declared in `out`, the engine errors and exits.
- If a variable declared in `out` does not exist in the returned dictionary, the engine errors and exits.

**Function returns a single value (non‑dictionary)**
If the function returns a single value such as a string or number, and `out` declares **exactly one variable**, it is directly assigned.
- Python function
def collect_vote(voter_name, target):
    return target
- FEM playbook
action collect_vote @func(werewolf_utils.collect_vote):
    in:
        voter_name = @voter
        target = vote
    out: vote_results.@voter(string, "")
- The function returns `"p3"`, and the compiler automatically executes `vote_results["@p1"] = "p3"`.
- The function only needs to return the final value; do not assemble the dictionary yourself.
- If `out` declares multiple variables but the function returns only a single value, the engine errors and exits.

**Writing to a specific key of a dictionary**
When `out` is written in the form `dict.key`, the compiler directly writes the return value into the specified key of that dictionary.
Format: `out: dict_name.key_name(type, "label")`
- If the dictionary itself has been declared in `vars:`, the value returned by the function is written directly to the corresponding key.
- If the dictionary does not exist (not declared in `vars:`), the engine errors and exits.
- The function still only returns the final value; the compiler is responsible for writing to the dictionary.

#### Not yet implemented: Built‑in special function `system.spawn`
Used to dynamically create temporary characters:
action spawn_team @func(system.spawn):
    in: spawn_requests
    out: team_members
- The upstream agent outputs `spawn_requests`, e.g., `[{blueprint: coder_blueprint, count: 2}]`.
- `system.spawn` generates temporary characters based on the blueprint and returns a list like `[@coder_4, @coder_5]`.
- The returned list can be directly used for `par` iteration.
- Temporary characters are automatically recycled by the engine after the Flow ends.
- Complete example of dynamic team building
action plan @ai(hostgod):
out: spawn_requests(array, "Team building request"), task_list(object, "Tasks")

action spawn_team @func(system.spawn):
in: spawn_requests
out: team_members

flow:
[START] -> plan -> spawn_team
spawn_team -> par coder in team_members -> &CoderSandbox(coder, task_list[coder])
join(all) -> [END]

Workflow: manager plans → system.spawn generates characters according to blueprint → parallel task assignment → summarise and end.

#### Connecting @actor variables with Python functions
When a variable declared in `in:` is of type `@actor`, the engine will **automatically resolve it into a structured dictionary** before passing it to the Python function, because Python does not understand FEM’s `@actor` syntax.

Resolution rules:
Suppose the playbook contains:
vars:
    hp = {@ellis: 100, @bob: 80}
    location = {@ellis: "Tavern", @bob: "Park"}

1. When @ellis is passed to a Python function, the dictionary received is:
{
    "type": "ai",
    "name": "@ellis",
    "soul": 3,
    "hp": 100,
    "location": "Tavern"
}

2. When hp.@ellis is passed to a Python function, the value received is the current value of hp.@ellis.
In this example, that is 100.

**Example**:
- FEM playbook
action check @func(my_utils.check_soul):
    in: target = @ellis
    out: result
- Python function can directly access all properties:
def check_soul(actor):
    if actor.get("hp", 100) < 50:
        return {"result": f"{actor['name']} HP too low, unable to act"}
    if actor["soul"] == 3:
        return {"result": f"{actor['name']} is a werewolf, located at {actor.get('location', 'unknown')}"}
    return {"result": "Good guy"}
**Rule**: When an `@actor` type variable is passed into Python, it is always packaged as the character's **current complete state dictionary**, containing static properties (type/name/soul/user) and all dynamic properties keyed by that character in `vars`.

#### Common Mistakes
| Mistake | Correct | Explanation |
|------|------|------|
| Function returns a complete dictionary, but `out` specifies `dict.key` | The function returns only the final value; the compiler handles dictionary writing | When `out: dict.key`, the function should return a single value |
| The keys of the returned dictionary do not match the variables declared in `out` | Ensure that the returned dictionary’s keys match the `out` variables one‑to‑one | Extra or missing keys will cause an error |
| `out` declares multiple variables, but the function returns a single value | `out` declares only one variable, or the function returns a dict/tuple | Counts must match |
| Function returns a tuple, but the count does not match `out` | Ensure the tuple length equals the number of `out` variables | Each position corresponds to one variable |

## 7. Module Definitions (modules)

A module is a black box containing a sub‑flow, convenient for direct invocation without worrying about how it is written inside.
Inside a module is a complete sub‑flow, with internal vars, internal actions, entry, exit, and internal flow. Somewhat like a class in Python.

### Basic Syntax
module ModuleName(param1, param2):
    meta:
        max_steps: 100
    vars:
        local_var = initial_value
    action ...
    flow:
        [IN] -> ... -> [OUT]

module CoderSandbox(task_var):
    vars:
        finish = false
    action write_code @ai(@coder_actor):
        prompt: |
            Task: {task_var}
            Your code is saved in the folder; the code test results are also in the folder, please check them yourself.
            You can use shell tools. Please call the shell tool to write code.
        scope: [@coder_actor]

    action submit_code @ai(@coder_actor):
        prompt: |
            You need to test whether the code can run.
            Please use the shell tool for testing, and save the test results in the folder for later review.
            If you believe the code is fine, output the assignment variable:
            SET VARIABLE : <<finish = true>>
        out: finish(bool, "Is it finished")

    flow:
        [IN] -> write_code -> submit_code ->
        fork:
            -> (if finish == true)[OUT]
            -> (if finish == false)[IN]

module DevLoop(task_var):
    vars:
        submit = "discuss"
    action reviewer @ai(@CEO)
        prompt: |
             Review the code for task {task_var}. The code is in the folder; use tools to check it yourself.
             If you think there are problems with the code, you can now discuss with the AI that wrote the code. Do not output any variable assignments while the discussion is not over.
             If you feel the discussion is clear and you decide to let the coding AI make revisions, please output SET VARIABLE : <<submit = "revise">>
             If you think the discussion can end and the code is great, please output SET VARIABLE : <<submit = "goodjob">>
        scope: [@CEO，@coder_actor]
        out: submit

    action reviewer2 @ai(@coder_actor)
        prompt: "This is the CEO reviewing your code; you can discuss."
        scope: [@CEO, @coder_actor]

    flow:
        [IN] -> [A]:&CoderSandbox ->
             -> [B]:reviewer -> [C]:reviewr2 ->
        fork:
             -> (if submit == "goodjob") -> [OUT]
             -> (if submit == "revise") -> [IN]     # return to [IN], rewrite.
             -> (if submit == "discuss") -> [B]     # CEO didn't change assignment, return to [B], continue discussion loop.

- **Parameters and Variables**
  Parameters in parentheses can be directly referenced inside the module using `{param_name}`. If no parameters need to be passed in, you can directly write `module CoderSandbox:`.
  Internal vars are local variables and are cleared when leaving the module.
  Use `in` when you need to rename.

- **Internal anchors**:
  `[IN]`: Module entry. Data flows in from here.
  `[OUT]`: Module normal exit. Data flows out from here; subsequent nodes can be connected.
  `[BREAK]`: Module break exit. Exits the module and stops this branch; nothing follows it.

### Invocation Method
- In the internal flow of a module or in a project's mainflow, reference modules with the `&` prefix to distinguish them from actions. `&ModuleName`, or `&ModuleName(args)` are both fine.
- **Nesting**: Modules can call other modules inside, using `&moduleName` to reference other modules.
- Modules are allowed to call themselves recursively, but:
  **Warning**: After the module exits, local variables are cleared and will not be passed to the parent module. Therefore, global variables must be used to control the breakout.
  **Warning**: Do not set the `max_steps` parameter to prevent infinite loops. We have designed module‑internal steps and global steps to count separately, so a module’s internal steps always count as 1 from the global perspective. Sub‑module steps also count as 1 from the parent module’s perspective, which would lead to an infinite loop!
  So it’s better not to recurse.

## 8. Nodes and Flow Orchestration (flow)

**Key conceptual distinctions**:
- **Action**: Is a behaviour (what to do), without location information.
- **Module**: Is a black box (containing a sub‑flow), with entry and exit.
- **Node**: A node is a position marker and container; a Node can hold an action or a module.
- **Flow**: Strings Nodes together.

Conventions:
- Action references: No prefix (e.g., `action1`), for smooth writing.
- Module references: `&` prefix (e.g., `&small_module`), recognisable at a glance as a black box. Can be followed by `(arg)` or not.
- Nodes and positions: Square brackets denote a position. `[NodeName]`, `[IN]`, `[OUT]`, `[BREAK]`, `[START]`, `[END]` – square brackets cannot be omitted.

**8.1 Nodes and Actions**
A Node is a position marker in the Flow.
When it is just a simple chain, it is fine to lazily write just the action name.
However, when the flow has loops, you must use nodes to mark positions, to distinguish between "execute again" and "loop back":
- This is not a loop:
action1 -> action2 -> action3 -> action1 # just executes action1 again sequentially.
- This is a loop:
[A]:action1 -> [B]:action2 -> [C]:action3 -> [A] # returns to the **position** of A, and will then run B and C again.

**Defining node contents**:
The following definition methods are all supported:
[A]: myaction1
[B]: &modulename
[C]: &mymodule(arg)
[A] -> [D]:actionName2 -> [E]:&mymodule(arg) -> [B] -> [A]
- Nodes are allowed to have no bound action or module; an empty node can serve as a placeholder. When the compiler encounters an empty node, it continues running to the next node.

### 8.2 Sequential Chain

[START] -> action0 -> [B]:action1 -> &module1 -> [END]
- `[START]` and `[END]` are reserved keywords and must be uppercase.

When a single‑line chain is too long, we can split it across multiple lines. As long as the head and tail nodes can connect, it can be continued.
But note: only **nodes** can connect, because nodes represent positions. Action and module names cannot be used for continuation.
Example of line continuation:
[IN] -> wolf_discuss -> seer_check -> seer_result -> [A]:tell_seer
// You can even write other chains in between; the order is insensitive, similar to mermaid syntax.
[A] -> witch_save_ask -> witch_poison_ask -> resolve_night -> [OUT]

### 8.3 Advanced Syntax

#### Concurrent branches (fork):
Declare the presence of branches starting with `fork`. fork only manages branching, not merging.
Branches are concurrent; whenever a branch is encountered, the compiler runs all branches in new sub‑threads. Calling LLMs takes time, so branches are very suitable for calling multiple LLMs simultaneously.
The previous chain ends pointing to this node; on the next line, use this node as the parent, write `fork` followed by a colon to spawn branches.
The `->` under the indented branch refers to different paths diverging from the parent node.
[A] -> [B] -> [C] ->
fork:
    -> [visit]
    -> [solo]

Another way to write branches is multiple lines at the same indentation:
[A] -> [B] -> [C]
[C] -> [visit]
[C] -> [solo]

#### Conditional parallel branches (if):
When you need conditionals, you can simply add `if` on the edge.
The difference between no `if` and having `if`: without `if`, all pass unconditionally in parallel; with `if`, only those that evaluate to true will pass (still in parallel).
The compiler hands the `if` condition expression directly to Python for evaluation. Any valid Python expression is supported.
`@actor` type variables in the expression are automatically translated into a Python‑recognisable dictionary before evaluation, so you can freely use @actor types here.

[A] ->
fork:
    -> if (var == true) -> [B]
    -> if (score > 5 and level >= 3) -> [C]

#### Mixed parallel branches:
[A] ->
fork:
    -> [B]
    -> if (@Portia.hp == 0) -> [C]
    -> if (hp.@Portia >= 100) -> [C]

### Merging (join):
join(all):
    [B] ->
    [C] ->
to [next_node]

Join is defined at the receiving end, clearly declaring "I want to wait for whom".
Only write the immediately upstream node; no need to write nodes further back.
Parameters in parentheses:
- "all": Wait for all declared upstream nodes to arrive, then execute [next_node].
- some number N: As soon as N of the declared upstream nodes have arrived, execute [next_node]; the remaining tasks that haven't arrived are cancelled and closed.
**Regarding thread management**: The compiler plans tasks in advance when parsing the flow diagram. fork spawns multiple tasks for parallel execution; join merges them.
When `join(n)` prunes the other branches, it only prunes tasks belonging to this fork, and does not affect calls to the same action by other modules.
(This requires the compiler to generate a unique fork_id for each fork to track task ownership.)

### Sequential loop (for):
Meaning: Iterate over speaker_array, executing [C] serially for each element.
The loop variable @speaker is automatically bound to the action's @actor_expr (if the action's @actor_expr is a dynamic variable).
The line after the for loop ends must start with `->` to indicate where to go after the for loop finishes.
Example:
[A] -> [B] ->
for @speaker in speaker_array:
    -> [C] -> [D] ->
-> [END]
This is equivalent to, for example:
[A] -> [B] -> [C] -> [D] -> [C] -> [D] -> [C] -> [D] -> [C] -> [D] -> [C] -> [D] -> [END]

for loops can be used together with if, achieving a certain fork effect: here is a werewolf example:
[B] ->
for @player in alive_players:
    -> if (@player.type == ai) -> ai_speak ->
    -> if (@player.type == human) -> human_speak ->
-> [D]
This is equivalent to, for example:
[B] -> ai_speak -> ai_speak -> ai_speak -> ai_speak -> human_speak -> ai_speak -> [D]
The compiler automatically binds `@player` to the parameter `(@player)` of the called action.

The internal content of a for loop can span multiple lines, with the same syntax as the external chain (similar to mermaid, order insensitive).
However, we especially need to know where the content of the for loop starts and where it ends to enter the next iteration.
Therefore, we additionally require:
Before the start node, add a `->` to mark the beginning of the loop here,
After the end node, add a `->` to mark that the current iteration ends here and either enters the next iteration or completes entirely.
Two lines starting with `->` in parallel indicate branches here. Inside for, you can use multiple start symbols `->` to create multiple branches, conveniently enabling slightly different loops under different if conditions. The branches are concurrent, similar to fork.

### Concurrency (par):

Meaning:
It is equivalent to first forking many lines, then joining at the same point. But when the actions on each path are the same or highly similar, we can use par to simplify the notation.
You can also understand it as the concurrent version of for. Concurrent, no ordering, e.g., making concurrent LLM requests, greatly improving execution speed.
If there are multiple nodes inside the par body, they are still executed serially.
The line after the par loop ends must start with `->` to indicate where to go after par finishes.
The scope of the concurrency parameter is only the current line and the parameters of the called module.
**Concurrency parameter passing**: The concurrency parameter of `par` (e.g., `coder`) can be passed as an argument into a module,
   and inside the module it can be directly referenced by variable name, or used as a dynamic actor `@ai({variable_name})`.

Example 1:
[A] ->
par @coder in coders:
    -> &CoderSandbox(@coder, task_list[@coder]) ->
-> [D]
This is equivalent to:
      |-> &CoderSandbox(@coder_1, task_list[@coder_1]) ->| 
[A] ->|-> &CoderSandbox(@coder_2, task_list[@coder_2]) ->|-> [D]
      |-> &CoderSandbox(@coder_3, task_list[@coder_3]) ->| 
        ... many, assuming coders are many, but you are too lazy to write them one by one with fork...
      |-> &CoderSandbox(@coder_n, task_list[@coder_n]) ->| 

Example 2:
[START] ->
par @coder in workers:
    -> [A]:writecode -> [B]:trycode ->
-> [D]
This is equivalent to iterating over workers, each character starting concurrently, sequentially executing [A] and [B].
The concurrency parameter @coder is written into each thread's local context, and inside the action it directly takes the value via the variable name:
           coder1:|-> writecode -> trycode ->| 
[START] -> coder2:|-> writecode -> trycode ->| -> [D]
           coder3:|-> writecode -> trycode ->| 
          ... many, assuming coders are many, but you are too lazy to write them one by one with fork...
           codern:|-> writecode -> trycode ->| 
Note: @coder is a thread‑local variable; different threads have different values and do not interfere with each other.
Inside the action, just directly use `{c}` or @coder to reference it; no need to explicitly pass parameters in the flow.
The loop variable of for and the concurrency parameter of par must have the same name as the dynamic variable inside the parentheses of the action definition, otherwise the engine will directly error and prompt a variable name mismatch. This way there will be no silent misuse of the wrong person.

The internal content of par can span multiple lines, with the same syntax as the external chain (similar to mermaid, order insensitive).
However, we especially need to know where the content of par starts and where it ends to enter the next iteration.
Therefore, we additionally require:
Before the start node, add a `->` to mark the beginning of the loop here,
After the end node, add a `->` to mark that the current iteration ends here and either enters the next iteration or completes entirely.
Two lines starting with `->` in parallel indicate branches here. Inside par, you can use multiple start symbols `->` to create multiple branches, conveniently enabling slightly different loops under different if conditions. The branches are concurrent, similar to fork.

## 9. mainflow Main Flow
Each `.fems` playbook has a single mainflow block.
It must have `[START]` and `[END]`, marking the beginning and end of the flow diagram. When the compiler runs, it starts from `[START]` here.
The syntax is the same as previously described; you can call actions and modules.

## 10. Core Mechanisms

- Agents in the same scope:
  Context is automatically shared; they can see each other's chat records and then just chat directly.
  LLMs are not functions; they are intelligent agents, they chat directly.
- Agents across scopes:
  They did not experience that event together, so naturally their memories are not interoperable. However, they can still contact files stored by the other party through tool calls, etc.
  The FEM compiler also supports them transmitting global variables to each other, but it’s actually unnecessary; it’s better to use shell tools to read files.
  LLMs are not functions; they are intelligent agents, they invoke tools.
- FEM compiler variable assignment:
  It is not meant for AIs to pass information to each other.
  Variable assignment is mainly for controlling the direction of the flow diagram, as well as controlling scope, etc.
  LLM agents can actively, through variable assignment, decide their own next direction (as long as you tell them how in the prompt).
  Sometimes, to control the workflow’s flow, you can also require humans to assign values to certain variables in action.
- Module
  Internal parameters are automatically bound. If renaming is needed inside a Module, you can use `in` to map.
- The loop variable of for and the concurrency parameter of par
  are automatically bound to module parameters.

## 11. **FEM Compiler Error Messages**

- Variable not declared → error, points out the variable name
- File does not exist → error, points out the file path
- Method not defined → error, points out the method name
- Unresolvable element in Scope → error
- Database constraint violation → error (raises the original exception)

## 12. Complete Example

meta:
    name = Test Playbook
    database = file:"test.db"
    owner = [1]
    system_safety = This is a safety notice
    session = new

vars:
    memory_text = ""
    context_text = ""
    reply = ""

code:
    memfile = file:"utils/MemoryExample.py"
    ctxfile = file:"utils/ContextExample.py"

actors:
    ai @ellis = soul:1

memory rag10(memfile.retrieve_example):
    in: prompt, session_id, @actor
    out: memory_text

context thisSession(ctxfile.findThisSession):
    in: session, @actor
    out: context_text

action speak @ai(@ellis):
    prompt: "Hello, please say something random."
    memory: rag10
    context: thisSession
    out: reply

flow:
    [START] -> speak -> [END]
