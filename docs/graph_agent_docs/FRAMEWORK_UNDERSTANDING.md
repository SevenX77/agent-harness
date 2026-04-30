
# graph_agent 框架快速理解

> **本文档目的**：在动手改 graph_agent 或给它做配套工具（Studio、Lint、Visualization 等）之前，先读这一份文档，把框架的核心机制、红线、和现状与设计意图的缺口看清楚。避免基于脑补或基于字面理解就下判断。
>
> **读者**：工程师 / PM / 给 graph_agent 做集成的 Copilot / 给 graph_agent 写配套工具的开发者。
>
> **最后更新**：2026-04-23
>
> **关联材料**：
> - `ARCHITECTURE.md` — 原作者视角的整体设计概述
> - `SKILL_AUTHORING_GUIDE.md` — 写 SKILL.md 的具体字段和标签说明
> - `COGNITIVE_LOOP_GUIDE.md` — 双层认知控制架构的运行时行为细节
> - `INTEGRATION_GUIDE.md` — 把 graph_agent 集成到新项目的指南

---

## 1. 这个框架到底是什么

`graph_agent` 是一个**以 SKILL.md 文件为单一事实源的声明式多阶段 Agent 编排引擎**。

它的核心价值有两层。**静态层面**，它把"多阶段任务的编排逻辑"从 Python 代码降级到声明式 Markdown 文档：PM 或 Copilot 可以用 YAML frontmatter + XML 风格标签描述一个任务怎么分阶段、每阶段用什么模型、用哪些工具、阶段之间怎么传数据、失败了怎么重试，而不需要写 Python 编排代码。**运行时层面**，它通过双层控制架构（外层 harness 管 phase 间 nudge/checkpoint/retry，内层 LangChain 管 LLM agent loop）强制 LLM 按"规划 → 执行 → 自检"三步走，不让 LLM 闷头干活或悄悄结束，而是必须留下可审计的行为痕迹。

框架的原生能力里最重要的一条是**把一个完整 skill 递归嵌入到另一个 skill 的某个 phase 里**，让 skill 像乐高积木一样可以组合、独立验证、即插拔。这条能力决定了 graph_agent 不只是"Python 编排的 Markdown 皮肤"，而是一个支持真正模块化 Agent 组合的引擎。

---

## 2. SKILL.md 的完整结构

一个 SKILL.md 文件由两大部分组成：**frontmatter**（YAML 格式的元数据，写在最前面用 `---` 包围）和**标签体系**（XML 风格的标签正文，写在 frontmatter 下面）。

### 2.1 Frontmatter 字段

| 字段 | 含义 | 关键规则 |
|------|------|---------|
| `name` | 这个 skill 的唯一标识，必须是 kebab-case（短横线分隔，如 `text-segmentation`） | compiler 的 F001 规则强制 kebab-case |
| `description` | 描述 skill 的用途和适用场景，必填，不超过 1024 字符 | compiler 的 F002 规则强制存在 |
| `type` | 取值 `simple` 或 `graph`。`simple` 最多一个 phase 且可以省略 `<node>` 标签；`graph` 必须用 `<node>` 拆分多阶段 | 见 `SKILL_AUTHORING_GUIDE.md` §1 |
| `io` | 声明 skill 的输入和输出。`io.inputs` 声明 runtime 需要传进来的参数；`io.outputs` 声明运行结果落盘到什么地方（`target: file` 写文件路径，`target: artifact_manager` 走 caller 注入的回调） | 见 `io/manager.py` |
| `context_mapping` | 把 runtime 传进来的输入组装成 `initial_context` 内部状态字典。支持 `{input.key.subkey}` 点路径取值、字符串字面量 | **禁止使用 `$func()` 函数调用语法**（compiler F006 规则明确禁止：framework 层不应执行 skill 业务代码） |

**完整 frontmatter 例子**（来自 `skills/text-segmentation/SKILL.md`）：

```yaml
---
name: text-segmentation
description: >
  ABC paragraph segmentation with Two-Pass validation.
  Classifies chapter paragraphs as A(setting)/B(event)/C(system).
  Use when analyzing raw chapter text for story deconstruction.
type: graph
context_mapping:
  chapter_content: "{input.chapter_content}"
  chapter_number: "{input.chapter_number}"
io:
  inputs:
    - name: chapter_content
      type: str
      source: runtime
    - name: chapter_number
      type: int
      source: runtime
  outputs:
    - name: segmentation_result
      type: dict
      target: file
      path: "output/text-segmentation/chapter_{context.chapter_number}_segments.json"
---
```

### 2.2 标签体系（6 种标签，每种的处理阶段和作用）

| 标签 | 作用 | 被谁在什么阶段处理 |
|------|------|-------------------|
| `<node id="..." depends_on="...">` | graph 模式的拓扑节点声明。`id` 是节点唯一标识，`depends_on` 声明依赖的前置节点（决定 LangGraph 的 edge 连接）| parser 用 `_NODE_PATTERN` 正则提取（`core/parser.py` L162-165） |
| `<phase_config>` | 这个 phase 的参数配置，内部是 YAML 格式。包括 `name` / `tier` / `tools` / `validator` / `retry_target` / `subgraph` / `context_bridge` / `sub_skills` / `max_retries` / `max_iterations` / `max_nudges` 等字段 | loader 用 `yaml.safe_load()` 解析（`core/loader.py` L502） |
| `<system_prompt>` | 给 LLM 的系统提示。只有 LLM 模式的 phase 才生效；subgraph 模式或 code-only 模式下此标签被忽略 | loader 读取后赋值给 `Phase.system_prompt`（`core/loader.py` L563-564） |
| `<user_prompt>` 或 `<user_prompt_builder>` | 给 LLM 的用户提示模板。支持 `{变量名}` 占位符，占位符必须在 `context_mapping` 里有定义（否则 compiler P006 报错） | loader 读取后赋值给 `Phase.user_prompt_template`（`core/loader.py` L568-569） |
| `<data_architecture>` | 可选的数据结构说明。给 LLM 解释当前 phase 应该产出什么形状的数据 | loader 读取后赋值给 `Phase.data_architecture` |
| `<ref path="相对路径" />` | **文件片段包含指令**。详见第 3 节 | parser 用 `_resolve_refs()` 函数递归展开（`core/parser.py` L160-186），**在 loader 解析任何标签之前就完成字符串替换** |

---

## 3. 两个容易被混淆的机制：`<ref>` 和 `subgraph:`

这两个机制都涉及"引用外部文件"，但它们做的事情完全不是一回事。把它们搞混是理解这个框架时最常见的错误。

### 3.1 `<ref path="..." />` 是文件级的字符串替换

**作用**：在 parser 阶段（`core/parser.py` L160-186 的 `_resolve_refs()` 函数），解析器看到 `<ref path="nodes/01_setup.md" />` 这个标签时，会**读取该路径指向的文件内容，把这个标签整个替换成文件内容的字符串**。替换是递归的，支持最多 10 层深度。替换完成之后，loader 看到的是一个已经没有任何 `<ref>` 标签的巨大字符串。

**用途**：解决"主 SKILL.md 文件里某些 phase 配置写得太长，塞在一个文件里不好阅读和维护"的排版问题。跟 skill 的逻辑复用、模块化、组合**完全无关**。

**例子**（来自 `skills/text-segmentation/SKILL.md`）：

```xml
<node id="setup">
<ref path="nodes/01_setup.md" />
</node>
```

parser 处理完后，实际变成：

```xml
<node id="setup">
<phase_config>
name: setup
tools:
  - script.segmenter.prepare_chapter
</phase_config>
</node>
```

`<ref>` 只是把 `nodes/01_setup.md` 这个文件里的文本内容贴到了标签所在的位置，**仅此而已**。

### 3.2 `subgraph: 子 SKILL.md 路径` 是逻辑级的子 skill 递归加载

**作用**：写在 `<phase_config>` 里作为一个 YAML 字段（不是 XML 标签）。loader 在解析父 skill 的某个 phase 时，如果发现这个字段（`core/loader.py` L522-539），会把这个字段指向的路径当作**另一个完整的 SKILL.md 文件**，**递归调用 `load_workflow_from_md()` 把它加载成一个独立的 `GraphAgentHarness` 实例**，然后把这个 harness 实例挂到当前 phase 的 `subgraph` 属性上。运行时走到这个 phase 时，框架会调用这个 harness 的 `run()` 方法，**完整跑一遍子 skill 的所有 phase**，跑完后把结果通过 `context_bridge` 映射回父 skill 的 context。

**用途**：解决"把一个完整独立 skill 作为另一个 skill 的某个 phase 嵌入进来"的架构复用问题。这是 graph_agent 支持模块化、独立验证、即插拔的核心机制。

**例子**（假设性的）：

```xml
<node id="render">
<phase_config>
subgraph: subskills/render/SKILL.md
context_bridge:
  inputs:  { plan_result: render_input }
  outputs: { render_output: final_render }
</phase_config>
</node>
```

运行时，父 skill 走到 `render` 这个 phase 时，框架会调用已加载的 `render-skill` 这个独立 harness 的 `run()`，把父 skill 当前 context 里的 `plan_result` 字段传给子 skill 作为它的 `render_input` 输入，等子 skill 内部的所有 phase 跑完之后，把子 skill 产出的 `render_output` 字段写回父 skill 的 `final_render` 字段。

### 3.3 两者的本质对比

| 维度 | `<ref path="...">` | `subgraph: 路径` |
|------|-------------------|------------------|
| 写在什么位置 | 作为 XML 标签，写在 `<node>` 标签内部 | 作为 YAML 字段，写在 `<phase_config>` 内部 |
| 在哪个阶段被处理 | Parser 阶段（第一步，比 loader 早） | Loader 阶段（解析 phase 配置时）|
| 处理方式 | 字符串级的文件内容贴入 | 递归加载成 `GraphAgentHarness` 实例 |
| 处理代码位置 | `core/parser.py` L160-186 | `core/loader.py` L519-560 |
| 运行时会发生什么 | 没有运行时逻辑（只是文件组装） | 调用子 harness 的 `run()`，跑完整的子 skill |
| 解决的问题 | 文件太长不好读 | 架构级模块复用 |
| 是否影响 skill 的组合结构 | 不影响（只是文本排版） | 影响（构建递归的 skill 嵌套树）|

两者**可以并用**。比如一个父 skill 用 `subgraph:` 嵌入子 skill，子 skill 内部用 `<ref>` 把自己的 node 定义拆成多个文件方便阅读，两个机制各管各的不冲突。

---

## 4. Phase 的三种运行模式及互斥规则

`core/loader.py` L565 的一行代码决定了 phase 的执行模式：

```python
requires_llm = (system_prompt is not None) and (subgraph_harness is None)
```

基于这个判断以及 subgraph 是否存在，phase 被分成三种互斥的模式：

### 4.1 LLM 模式

**触发条件**：当前 phase 的 `<phase_config>` 里**没有** `subgraph:` 字段，但**有** `<system_prompt>` 标签。此时 `requires_llm = True`。

**执行路径**：在 `core/harness.py` L384 的分叉判断里，因为 `phase.subgraph is None`，走 `_build_phase_node(phase)` 这条路径。这条路径会启动 LangChain 的 agent loop，让 LLM 根据 system_prompt 做规划、调用 tools 列表里的工具函数、最后调用 `finish_task` 完成这个 phase。

**生效的字段**：`system_prompt` / `user_prompt_template` / `tools` / `sub_skills` / `validator` / `retry_target` / `tier` / `max_iterations` / `max_nudges` / `dead_end_threshold`。

**适用场景**：这个 phase 需要 LLM 思考、决策、调用工具完成任务。

### 4.2 Subgraph 模式

**触发条件**：当前 phase 的 `<phase_config>` 里**有** `subgraph: 路径` 字段。此时 `requires_llm = False`（即使同时写了 `<system_prompt>` 也会被强制忽略）。

**执行路径**：`core/harness.py` L384-387 的分叉判断里，因为 `phase.subgraph is not None`，走 `_build_subgraph_node(phase)` 这条路径（定义在 `core/subgraph.py`）。这条路径**完整运行子 skill 的 harness**（`core/subgraph.py` 的 `child.run(...)` 调用），把父 skill 当前 context 通过 `context_bridge.inputs` 映射成子 skill 的 `initial_context`，子 skill 内部所有 phase 跑完后通过 `context_bridge.outputs` 把结果映射回父 skill 的 context。

**生效的字段**：`subgraph`（子 skill 路径）、`context_bridge`（父子 context 映射）、`validator`、`retry_target`、`max_retries`。

**被忽略的字段**（写了没用）：`system_prompt`、`user_prompt`、`tools`、`sub_skills`、`tier`、`max_iterations`、`max_nudges`、`dead_end_threshold`。

**注意**：被忽略的字段是**父 skill 在声明 subgraph 的这个 phase 里额外写的字段**，不是子 skill 自己内部的字段。子 skill 是作为一个独立完整的 skill 递归加载的，它内部每个 phase 自己的 tools / prompts / validator **全部正常生效**。

**Loader 侧的具体逻辑**：
- `core/loader.py` L578：`if subgraph_harness is None: for ref in tool_refs: ...` — 只有没 subgraph 时才解析 tools
- `core/loader.py` L587：`if subgraph_harness is None: sub_skill_decls = ...` — 只有没 subgraph 时才解析 sub_skills
- `core/loader.py` L639：`system_prompt=system_prompt if subgraph_harness is None else None` — 有 subgraph 时把 system_prompt 强制设为 None

**适用场景**：这个 phase 需要的工作是"委派给另一个完整 skill 去做"，比如 pipeline 里某一步固定调用一个已有的成熟子 skill。

### 4.3 Code-only 模式

**触发条件**：当前 phase 的 `<phase_config>` 里**既没有** `subgraph:` 字段，**也没有** `<system_prompt>` 标签。此时 `requires_llm = False`。

**执行路径**：和 LLM 模式一样走 `_build_phase_node(phase)`，但因为没有 system_prompt，不会启动 LLM 的 agent loop。框架会按 `tools` 列表的顺序直接调用每个工具函数，每个函数的输入输出通过 context 串起来。

**生效的字段**：`tools`、`validator`、`retry_target`。

**适用场景**：这个 phase 需要做纯数据处理或计算，不需要 LLM 参与。比如"把输入数据切成 chunks"、"把多个 phase 的结果合并成最终输出"。

### 4.4 三模式互斥是硬约束

Phase 三种模式互斥**不是程序员洁癖**，是框架的核心设计红线：**"一个 Phase 不应有两个大脑"**。执行权必须唯一——要么委派给子 skill（subgraph 模式下 phase 本身不做任何决策），要么让 LLM 思考（LLM 模式），要么纯计算（code 模式）。三种角色不能在同一个 phase 里混搭，因为混搭之后"谁是这个 phase 的决策者"变成无法回答的问题。

这个互斥由 `core/harness.py` L384 的执行器二分路由硬架构支撑：subgraph phase 走 `build_subgraph_node`，其他 phase 走 `_build_phase_node`，两条路径完全独立不交叉。

schema 2.0 已用 Pydantic discriminated union + `extra='forbid'` 在 `core/manifest.py` 的 LLMPhase / LogicPhase / DelegatePhase 区分上彻底解决——subgraph 字段必须在 DelegatePhase，LLMPhase 才有 tools/prompt，Pydantic 直接拒绝混搭。

---

## 5. 两种 skill-to-skill 组合机制的对比

框架提供了两种把一个 skill 嵌入到另一个 skill 里的原生机制。它们在"谁决定什么时候调用子 skill"这个根本问题上完全不同。

### 5.1 `subgraph:` — 静态委派，框架编排

在父 skill 的某个 phase 里写：

```yaml
<phase_config>
  subgraph: subskills/render/SKILL.md
  context_bridge:
    inputs:  { data_from_parent: render_input }
    outputs: { render_result: final_output }
</phase_config>
```

**语义**：父 skill 运行到这个 phase 时，**100% 会去跑子 skill `render`**，没有任何"是否要跑"的判断空间。就像普通代码里写死的函数调用 `result = render(data)`。父 skill 的工作流是线性确定的，这个位置就是固定委派给 render。

**谁编排**：**框架**。loader 在加载阶段就递归把子 skill 加载好（`core/loader.py` L535），runner 到点了就按部就班调用 `child.run()`。完全不涉及任何 LLM 决策。

**适用场景**：父 skill 知道确定的执行顺序，子 skill 是 pipeline 里的一个固定步骤。比如"数据处理 → 格式化 → 落盘"这三步，第二步固定用 formatting skill，不需要根据数据动态选择。

### 5.2 `sub_skills:` — 动态调度，LLM 决策

在父 skill 的某个 phase（必须是 LLM 模式）里写：

```yaml
<phase_config>
  tools:
    - script.my_util
  sub_skills:
    - name: render
      skill_path: subskills/render/SKILL.md
    - name: refine
      skill_path: subskills/refine/SKILL.md
    - name: enhance
      skill_path: subskills/enhance/SKILL.md
</phase_config>
<system_prompt>
你是一个图像处理助手。根据用户需求选择合适的子技能……
</system_prompt>
```

**语义**：loader 会把 `render` / `refine` / `enhance` 这三个子 skill 各自通过 `skill_tool_factory.build_skill_tool()` 包装成一个 LangChain StructuredTool（见 `core/loader.py` L586-596），**加到当前父 phase 的 tools 列表里**。运行时这个父 phase 启动 LangChain agent loop，**LLM 看到这些子 skill 像看到普通 tool 一样**，根据 system_prompt 的指引和当前 context 自主判断要调哪个、什么时候调、调几次。可能只调一个，可能调所有，也可能一个都不调。

**谁编排**：**LLM**。框架只是把子 skill 包成 tool 放进工具箱，决策权在 LLM 手里。

**适用场景**：父 skill 不知道应该调用哪个子 skill，需要 LLM 根据情境动态判断。比如"客服机器人收到用户问题，LLM 根据问题类型决定调用 `refund-skill`、`tech-support-skill`、`order-status-skill` 中的哪一个"。

### 5.3 两种机制的本质对比

| 维度 | `subgraph:` 模式 | `sub_skills:` 模式 |
|------|-----------------|-------------------|
| 调用是否确定 | 必然调用，不可跳过 | 可能调用，可能不调，可能多次调 |
| 决策者 | 框架（写死在 SKILL.md 里） | LLM（根据 context 动态判断） |
| 父 phase 自己是否跑 LLM | 不跑（phase 是纯委派占位符） | 跑（LLM 要看工具选择调哪个） |
| 父 phase 能否再有其他 tools | 不能（tools 字段会被忽略） | 能（子 skill 就是 tool，和其他 tools 并列） |
| 父 phase 能否有 system_prompt | 不能（会被忽略） | 必须有（驱动 LLM 决策） |
| 加载方式 | 递归加载成独立 `GraphAgentHarness` | 包装成 LangChain StructuredTool |
| 对应代码位置 | `core/loader.py` L519-560 + `core/subgraph.py` | `core/loader.py` L586-596 + `core/skill_tool_factory.py` |
| 适用场景 | 确定性 pipeline，每步固定 | 动态 workflow，根据情况分支 |

### 5.4 两种机制可以并用

一个 skill 可以同时有多个 subgraph phase 和多个带 sub_skills 的 LLM phase。框架没有限制两种机制必须二选一。设计时应根据"这个位置是否确定要调用某个子 skill"选择合适的机制。

---

## 6. 框架的 5 条硬红线

这些红线都是从源码和文档里能读出来的核心设计约束，违反任何一条都会破坏框架的完整性。

### 红线 1：框架层不执行业务逻辑

schema 2.0 的 `IoInput`/`IoOutput` Pydantic 模型直接禁止 `$func()` 语法（没有相应字段），一旦 PM 误写就被 `extra='forbid'` 拒绝。原规则的 reason 直译过来是：

> framework 层不应执行 skill 业务代码；改用 setup phase + script/ tools 模式

**对实施方案的影响**：条件判断、数据组装、任何业务逻辑都应该写成 Python 函数放在 skill 的 `script/` 目录里，在一个独立的 code-only phase 里被调用，然后把结果写进 context 供后续 phase 使用。**不要让框架在 SKILL.md 里执行任何表达式**（包括假想的 `<step when="...">` 或 `skip_if:` 字段）。

### 红线 2：Kitchen-Pass 出餐口模式（I/O 解耦）

框架不直接往文件系统或数据库写数据。phase 的结果先写进 `WorkflowState.context`（内存里的 blackboard），真正落盘由 `io/manager.py` 里的 `IOManager` 处理。当 SKILL.md 的 `io.outputs` 声明 `target: artifact_manager` 时，框架会调用 caller 注入的 `artifact_saver` 回调函数，把数据交给 host project 决定怎么存。

**对实施方案的影响**：框架**不依赖 host project 的文件管理实现**，可以跨项目复用。但同时意味着 PM 直接用框架时会遇到问题：他不写 Python 代码，怎么注入 `artifact_saver`？这是配套工具需要解决的问题。

### 红线 3：双层认知控制架构

外层 `GraphAgentHarness` 的 while 循环管 phase 间的事情：planning nudge、selfcheck nudge、checkpoint compaction、finish gate。内层 LangChain 的 agent loop 管每次 LLM 调用内的事情：tool 执行、流式输出、中间件拦截（WorkingMemory / DeadEndPruning / Clarification / DanglingToolCall）。

这是硬架构，不是可选设计。详细行为见 `docs/graph_agent_docs/COGNITIVE_LOOP_GUIDE.md`。

**对实施方案的影响**：任何扩展不能破坏这个两层分工。

### 红线 4：认知控制权必须唯一

Phase 三种模式互斥（见本文第 4 节）。"一个 Phase 不应有两个大脑"——要么委派给子 skill（subgraph 模式），要么让 LLM 思考（LLM 模式），要么纯计算（code 模式）。三种角色不能混搭在同一个 phase 里。

**对实施方案的影响**：Studio 类工具在可视化 phase 时必须明确区分这三种模式，UI 上选择其中一种后应该禁止填写其他模式的字段。

### 红线 5：SKILL.md 是跨工具可移植契约

`compiler` skill 本身是一个 graph 类型的 skill，它同时可以部署为 Claude Code Skill 和 Cursor IDE Skill（见 `src/core/graph_agent/skills/compiler/SKILL.md` 开头的部署说明）。这意味着 SKILL.md 的格式设计不只服务 graph_agent 一个消费者，它是 graph_agent + Claude Code + Cursor 等**多个 Agent 工具共用的格式标准**。

**对实施方案的影响**：任何想给 SKILL.md 加新字段或新标签的扩展，都必须考虑"这会不会破坏 skill 在 Claude Code / Cursor 里的可用性"。Studio 等配套工具不应给 SKILL.md 加专属字段。

---

## 7. 运行时行为约束（认知循环）

这部分是从 `docs/graph_agent_docs/COGNITIVE_LOOP_GUIDE.md` 总结出来的，作为快速参考。细节请读原文档。

### 7.1 校验与执行在 graph 层面解耦

`core/harness.py` 在 `_build_graph` 构建 LangGraph 时，**为每个 phase 强制添加一对相互独立的节点**——一个叫 `execute_name`（干活的节点），一个叫 `validate_name`（独立挂载的校验节点）。校验不通过时通过 conditional edge 触发重试。

这意味着一个 phase 的"干活"和"自我评价"是两个独立的 graph 节点，干活的节点不负责决定自己干得好不好。框架级的"三权分立"。

### 7.2 LLM 必须规划才能执行

每个 LLM 模式的 phase 开始时，第一次 agent.invoke() 返回后，框架会检查 context 里是否有 `_working_memory` 字段。如果 LLM 没有调用 `update_working_memory` 记录计划，框架会注入 `PLANNING_NUDGE` 强制 LLM 先规划再执行。

### 7.3 LLM 必须结构化自检才能结束

LLM 调用 `finish_task` 时，框架检查是否包含必要的结构化字段：`execution_summary` / `plan_checklist`（每项含 step/completed/quality_check）/ `unresolved_issues`。不完整的 `finish_task` 会被 `SELFCHECK_NUDGE` 拒绝并要求重填。

### 7.4 Nudge 有预算上限

每种 nudge（planning / selfcheck / standard）都有 `max_nudges` 预算（默认 3 次/类型），全局 `total_nudge_count >= max_nudges * 2` 时触发强制降级，接受当前输出退出 phase。避免无限 nudge 循环。

### 7.5 Checkpoint Compaction 压缩上下文

当 working memory 被更新时，框架会压缩之前的消息历史（保留 system + user + 新的 checkpoint 摘要），防止长任务的上下文超限。

---

## 8. 现有业务 skill 的现状（和设计意图的缺口）

`skills/` 目录下当前有 5 个业务 skill：

- `text-segmentation` — 文本分段（独立 skill，有自己完整的 3 个 phase）
- `event-extraction` — 事件提取（独立 skill，4 个 phase）
- `batch-analysis` — 批量分析（独立 skill，5 个 phase）
- `global-synthesis` — 全局综合（独立 skill，4 个 phase）
- `story-deconstruction` — 故事解构编排器（4 个 phase，对应上面 4 个子职能）

### 8.1 当前实现方式

如果在整个 `skills/` 目录下搜索 `sub_skills:` 或 `subgraph:`，**一个都找不到**。没有任何业务 skill 使用框架提供的两种原生组合机制。

`story-deconstruction` 这个本应该是编排器的 skill，实际实现方式是：它的 4 个 node 都是 **code-only 模式**，每个 node 只有一个 `<phase_config>`，里面只写了一个 `tools:` 列表指向 `script.orchestrator.*` 的 Python 函数。例如 `skills/story-deconstruction/nodes/01_segmentation.md` 的全部内容：

```yaml
<phase_config>
name: segmentation
tools:
  - script.orchestrator.segment_all_chapters
</phase_config>
```

编排逻辑藏在 `skills/story-deconstruction/script/orchestrator.py` 这个 Python 文件里，里面的函数大概率是手动去调用其他子 skill 的 `run_skill()` 或者重新实现了一遍分段逻辑。

### 8.2 这和框架设计意图的差距

框架明明提供了 `subgraph:` 和 `sub_skills:` 两种原生机制让 skill 像乐高一样组合，现有的业务代码**完全没用**，全部退化成了"一个 node 调一个 Python 函数，Python 函数里硬编码拼接"。这让 graph_agent 的核心价值（模块化、独立验证、即插拔、递归嵌套、可视化拓扑、每个阶段独立自我校验）**完全没被发挥出来**。

### 8.3 `story-deconstruction` 应该怎么写

按照框架设计意图，`story-deconstruction` 应该写成这样：

```yaml
---
name: story-deconstruction
type: graph
---

<node id="segmentation">
  <phase_config>
    subgraph: ../text-segmentation/SKILL.md
    context_bridge:
      inputs:  {chapters: chapter_content, project_id: chapter_number}
      outputs: {segmentation_result: all_segmentations}
  </phase_config>
</node>

<node id="event_extraction" depends_on="segmentation">
  <phase_config>
    subgraph: ../event-extraction/SKILL.md
    context_bridge: {...}
  </phase_config>
</node>

<!-- 后两个 node 同样用 subgraph 委派给 batch-analysis 和 global-synthesis -->
```

这样每个子 skill 可以独立跑（独立验证），story-deconstruction 整体就是这些积木的纯声明式组合（即插拔），框架层自动处理递归执行（无需 Python 胶水），LangGraph 拓扑可视化也自然呈现。

---

## 9. 快速查找索引

想知道某个机制的实现在哪里，按下表查：

| 机制 | 代码文件 | 关键行号 |
|------|---------|---------|
| `<ref>` 文件片段展开 | `src/core/graph_agent/core/parser.py` | L160-186 (`_resolve_refs`) |
| `<node>` 拓扑节点解析 | `src/core/graph_agent/core/parser.py` | L162-165 (`_NODE_PATTERN`) |
| `subgraph:` 子 skill 递归加载 | `src/core/graph_agent/core/loader.py` | L519-560 |
| Phase 三模式判定 | `src/core/graph_agent/core/loader.py` | L565 (`requires_llm = ...`) |
| subgraph 模式下 tools 被跳过 | `src/core/graph_agent/core/loader.py` | L578 (`if subgraph_harness is None`) |
| subgraph 模式下 sub_skills 被跳过 | `src/core/graph_agent/core/loader.py` | L587 |
| subgraph 模式下 system_prompt 被清空 | `src/core/graph_agent/core/loader.py` | L639 |
| `sub_skills:` 包装成 LangChain Tool | `src/core/graph_agent/core/loader.py` | L586-596 + `core/skill_tool_factory.py` |
| Phase 执行器二分路由 | `src/core/graph_agent/core/harness.py` | L384-387 |
| Subgraph 运行时执行 | `src/core/graph_agent/core/subgraph.py` | 全文（`build_subgraph_node`） |
| `context_bridge` 数据类 | `src/core/graph_agent/core/types.py` | `ContextBridge` class |
| Phase 数据类 | `src/core/graph_agent/core/types.py` | `Phase` class |
| 现有 Callback 事件清单 | `src/core/graph_agent/callbacks/base.py` | 12 个 `EVENT_*` 常量 |
| IOManager 和 artifact_saver 桥 | `src/core/graph_agent/io/manager.py` | L94-152 |
| compiler 规则源 | `src/core/graph_agent/core/manifest.py` + `core/validators/*.py` | Pydantic schema（结构） + 4 个语义 validator（context_bridge / subgraph_cycle / persona_resolution / tool_paths） |
| hello_world 最小例子 | `src/core/graph_agent/examples/hello_world/SKILL.md` | 全文 |

### 想知道某条规则细节，按下表查：

| 规则 | 位置 |
|------|------|
| 框架 6 条硬红线（本文第 6 节） | 本文档 + `src/core/graph_agent/README.md` Core Principles |
| 认知循环的运行时行为 | `docs/graph_agent_docs/COGNITIVE_LOOP_GUIDE.md` |
| 怎么写 SKILL.md 的字段和标签 | `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` |
| 怎么把 graph_agent 集成到新项目 | `docs/graph_agent_docs/INTEGRATION_GUIDE.md` |
| `llm_roles.yaml` / `multimodal_roles.yaml` 怎么写 | `docs/graph_agent_docs/CONFIG_REFERENCE.md` |
| 怎么开发 skill 本地工具 | `docs/graph_agent_docs/TOOL_DEVELOPMENT_GUIDE.md` |

---

## 10. 已知的框架 bug 和建议修复

这些是在深度阅读源码过程中发现的真实 bug，独立于任何具体功能扩展，都应该单独修复。

### 10.1 subgraph phase 下的字段静默丢弃（已修复 — Task 5.1）

**历史问题**：当 PM 在 subgraph phase 里误写了 `tools` / `sub_skills` / `<system_prompt>` / `<user_prompt>` 时，loader 会静默忽略这些字段（见 `core/loader.py` L578 / L587 / L639）。compiler 里也没有相关规则，PM 可能以为这些字段生效了，实际运行时完全不会用到。

**修复状态**：schema 2.0 已用 Pydantic discriminated union 把这种误写拦在 manifest 校验阶段，无需再维护独立 YAML 规则文件。

---

## 11. 优化后新增的核心组件（graph-agent-optimizations spec 交付）

以下章节覆盖 2026-04 一轮集中优化里落地的新能力，Studio 项目可以直接依赖：

### 11.1 StorageManager（`graph_agent/io/storage.py`）

默认的 artifact 落盘器。构造签名 `StorageManager(workspace_root, skill_id, run_id, *, history_retention=10)`，**没有 user_id**（Studio 侧 UI 层概念）。

关键行为：

- 目录布局：`{workspace_root}/runs/[{pipeline_prefix}/]{skill_id}/{run_id}/` + 可选 `phases/<phase_name>/` 子路径。
- `get_output_dir(pipeline_prefix=None)` 懒触发 `_cleanup_history()`，按 `history_retention` 保留最新 N 次 run（默认 10）；**`.golden` 后缀目录永不计入且永不删除**。
- 清理时每个被删除的 run 都落一条 INFO：`run_id=... path=... freed_bytes=...`。
- IOManager 在 `target: artifact_manager` 且 caller 未注入 `artifact_saver` 时自动回落到 StorageManager（Kitchen-Pass 红线保留：caller 的 saver 永远优先）。

### 11.2 TracingClientProxy（`graph_agent/core/tracing_proxy.py`）

在 resolver 返回的 LangChain chat-model 外面包一层代理。每次 `.invoke()` 在转发给 wrapped client 之前会先给所有已注册 callback 发一个 `PromptCapturedEvent`（包含 `phase_name` / `llm_role` / `resolved_model` / `template_source` / `variables` / `resolved_prompt` / `sub_run_id` / `group_key`）。其他属性透明转发给 wrapped client，不影响 LangChain agent loop 的任何行为。harness 在 `resolver.resolve(...)` 之后、`create_agent(...)` 之前自动包装。

### 11.3 builtin `parallel_map`（`graph_agent/tools/builtin/parallel_map.py`）

声明式并发 fan-out 工具。SKILL.md 里写 `tools: [builtin.parallel_map]` 即可加载（loader 里有 `builtin.*` 特判）。调用形如：

```python
parallel_map(
    skill_path="path/to/child/SKILL.md",
    item_list=scenes,
    item_as="scene",
    max_concurrent=3,
)
```

每个 item 触发一个独立的子 skill run（用 `run_skill` + 独立 harness 实例，绕过 cache 避免竞态）。框架自动给每个子 run 分配 `_sub_run_id`（group_key + idx）并共享一个 `_group_key`；TracingClientProxy 读这两个 key 后把它们盖到所有 `prompt_captured` 事件上，Studio 可以按 `group_key` 折叠同一次 parallel_map 的并发事件。

默认 `max_concurrent=3` 和 LangChain SubagentExecutor 的默认一致；单个 item 出错只会在返回列表里留下 `{"error": "...", "sub_run_id": ...}` 条目，`stop_on_error=True` 可切成 fail-fast。

### 11.4 CallbackEvent Pydantic 类型化（`graph_agent/callbacks/events.py`）

14 个事件（12 旧 + `prompt_captured` / `llm_fallback` 两个新增）以 Pydantic 判别式联合 `CallbackEvent` 建模，`schema_version: Literal["1.0"]`，`extra=forbid`。`Callback.on_event(event)` 是新式入口；默认实现 dispatch 回老式 `on_phase_start` 等钩子，所以现有 Callback 子类零改动继续工作。`TracingCallback` 同时写 `{run_id}.jsonl`（旧格式）和 `tracing.jsonl`（每行一条 `event.model_dump_json()`），Studio 消费后者。

### 11.5 Phase.model_override + Nudge 默认降权（Tasks 6.1 / 6.5）

- `Phase.model_override: str | None = None`：指向 `llm_roles.yaml` 的 `models:` 代号；设置后 resolver 绕过 tier→role→model 映射直接用该模型。Compiler 有 `W-invalid-model-override` 校验代号存在性。
- `Phase.max_nudges` 默认由 3 降到 1。现有 skill 如果依赖 3 轮 nudge 预算需在 `phase_config` 里显式写 `max_nudges: 3`。

### 11.6 `<phase>` / `<node>` 术语迁移（Tasks 5.3 / 5.5）

SKILL.md 正式术语是 `<phase id="...">`。`<node>` 仍被解析（`_normalise_phase_tags` 在 parser 入口把二者归一），但 compiler 会发 `W-node-to-phase-migration`。所有在仓业务 skill（6 个）+ compiler skill 都已迁移。

### 11.7 Subagent 中间件继承（Task 2.7）

`SubagentExecutor(inherit_middlewares=True)` 默认开启，子 agent 现在拿到 lead 的完整中间件链（WorkingMemory / DeadEnd / Clarification 等）。设为 `False` 可回到 pre-Task-2.7 的极简中间件路径。`make_lead_agent` 与 `_build_middlewares` 都加了对应的 `inherit_middlewares` 参数。

### 10.2 可能的其他待发现 bug

随着配套工具（Lint 前端、Visualization、etc.）的开发，可能还会发现更多"现状和文档不一致"或"有代码但没规则保护"的地方。建议每次发现都补到本节，作为持续的技术债清单。

---

**本文档的目的是让任何读者（人类或 AI）在 10-15 分钟内建立对 graph_agent 框架的完整心智模型**。如果你读完后对某个机制仍有疑问，请先对照"快速查找索引"去读源码原文，不要基于字面理解就下判断——这个框架里有很多**看起来简单但实际有微妙边界的机制**（比如 `<ref>` 和 `subgraph:` 的区别、三种 Phase 模式的互斥规则、两种 skill 组合机制的决策者差异），必须读到代码才能真正理解。
