# V2.1 Engine Examples

此文档包含 V2.1 引擎的典型工作流范例，不涉及 V1 旧版适配。

## Example A: Minimal Chain (无 Subagent)
展示最基础的两阶段流转。

**目录结构**:
```text
skills/minimal-chain/
├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs.json
└── phases/
    ├── step_one/
    │   └── SKILL.md
    └── step_two/
        └── SKILL.md
```

**`GRAPH.md`**:
```xml
---
schema_version: "2.1"
name: minimal-chain
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />

<phase id="step_one" src="phases/step_one" depends_on="" />
<phase id="step_two" src="phases/step_two" depends_on="step_one" />
```
*注：没有任何并发，`step_two` 严格等待 `step_one` 完成。*

---

## Example B: Subagent Fan-out
展示父节点使用 `call_subagent` 工具，将任务并发委派给包含完整独立上下文的专家子技能。
*(此结构借鉴 `packages/graph-agent/tests/fixtures/subagent_minimal/` 实证用例)*

**目录结构**:
```text
skills/subagent-minimal/
├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs.json
└── phases/
    └── main/
        ├── SKILL.md
        └── subskills/
            └── echo_expert/
                ├── GRAPH.md
                ├── io/
                │   ├── inputs.json
                │   └── outputs.json
                └── phases/
                    └── echo/
                        └── SKILL.md
```

**`phases/main/SKILL.md` (父阶段)**:
```yaml
---
mode: skill
name: main
phase_config:
  subagents:
    - name: echo_expert
      path: subskills/echo_expert
      description: Echoes text using a child expert skill.
---
<system_prompt>
You must distribute the workloads. Use the `call_subagent_echo_expert` tool.
You should pass multiple items concurrently in the `inputs` array: [{"text": "A"}, {"text": "B"}].
</system_prompt>
<exit_contract>
Call finish_task when done.
</exit_contract>
```

**`phases/main/subskills/echo_expert/io/inputs.json` (子技能 Schema)**:
```json
{
  "type": "object",
  "properties": {
    "text": {
      "type": "string",
      "description": "Text to echo."
    }
  },
  "required": ["text"]
}
```

**执行流程透视**:
1. 编译期，引擎读取 `echo_expert` 下的 `inputs.json`，在父级生成严格校验的 `call_subagent_echo_expert(inputs: list[Model])` 工具。
2. 运行时，主大模型决定调用上述工具并传入两个字典项。
3. 引擎内部通过 Pydantic 校验后，使用 LangGraph API 并行拉起两次 `echo_expert` 执行子树，且子树的上下文 `messages: []` 是干净、绝对隔离的。
4. 两项执行汇聚为列表结果，返还给父阶段的大模型作为 ToolResponse 继续运行。

已生成三份文档（`GUIDE.md` / `RULES.md` / `EXAMPLE.md`），字数保持在 300-600 行规模，并采用一级大纲组织结构。主控请直接提取落地。 

## 1. 概念入门
V2.1 graph-agent 是一个结构化的 LLM Agent 执行 引擎。与 V1 阶段将所有 Prompt 和工具混杂在一个巨大的单一文件不同，V2.1 引入了 **图 (Graph)** 蓝图概念。它通过顶层 `GRAPH.md` 将复杂任务拓扑切分为多个专职的阶段  (Phase)，解决了大模型上下文污染、注意力涣散以及复杂逻辑不可控的问题。

## 2. 5 分钟 Quickstart : Hello World
创建一个极简的单阶段技能 (不包含子代理)。
**目录结构**：
```text
skills/hello -world/
├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs .json
└── phases/
    └── main/
        └── SKILL.md
```
**`GRAPH.md`**: 
```xml
---
schema_version: "2.1"
name: hello-world
---
 <input src="io/inputs.json" />
<output src="io/outputs.json" />
 <phase id="main" src="phases/main" depends_on="" />
```
**`phases/ main/SKILL.md`**:
```yaml
---
mode: skill
name: main
phase_ config:
  tools: []
---
<system_prompt>
You are a friendly greeter. Read  the input name and greet.
</system_prompt>
<exit_contract>
Call finish_task with the greeting message .
</exit_contract>
```

## 3. 核心概念详解
- **Skill**: 一个可独立编译 和运行的业务顶层单元，必须包含 `GRAPH.md` 和 `io/` 目录。
 - **Phase**: Skill 图谱的组成节点，每个 phase 对应一个独立目录。支持 3 种 mode:
  -  `logic` 纯 Python 执行 (不调用大模型)，适用于快速数据清洗。
  - `skill` LLM-driven agent ，根据 Prompt 自主思考并使用设定的 Tools。
  - `subgraph` Drill-down 静态 子图，将当前执行流穿透进入另一个 Skill 拓扑。
- **GRAPH.md 拓扑声明**: 使用 `<phase  depends_on="A, B" />` 定义有向无环图。没有依赖的优先运行，同 级节点会被引擎并发执行 (Fan-out)。
- **数据流动 (Context/State)**: 数据入口 由 `io/inputs.json` 强校验后写入全局 Context (黑板)。各 Phase 根据所需读写，最终输出经  `io/outputs.json` 校验。
- **SUBGRAPH vs Subagent (动态与静态)**:
  - `SUBGRAPH. md` 是**静态调度**，编译期决定，执行到该处必定发生图跳转穿透。
  - `Subagent ` 是**动态调度**，它是被封装成 Tool 提供给主大模型使用，主大模型自己根据对话意图判断 “是否调用”以及“传什么参数”。

## 4. 常用 Pattern
- **Chain (链式流 )**: A -> B -> C。典型的如 `text-segmentation`：提取 -> 切分 -> 审阅。
- ** DAG Fan-out/in**: 分发后汇聚。如 `batch-analysis`：一个阶段分发给三个 独立的评估器，最后接一个 `logic` 或 `skill` phase 汇聚分值。
- **Subagent 动态 调度**: 如 `adaptation` 场景：面对数量不定的输入列表，利用 subagent tool 动态拉起子专家并发处理。

##  5. 编写最佳实践 + 常见坑
- **何时用什么 Mode (决策树)**: 
  -  是确定性的 API 调用或 JSON 处理吗？ -> **选 `logic`**。
  - 需要模糊语义 理解与自主使用外部工具吗？ -> **选 `skill`**。
  - 存在固定的业务长 流程且其他模块也需要复用？ -> **选 `subgraph`**。
- **何时用 Subagent vs Subgraph**:  流程固定无条件跑选 Subgraph；由大模型动态评估意图、甚至根据不同输入并发不同 数量的实例，选 Subagent。
- **Subagent Input Schema**: Pydantic 会做极严的 类型验证。如果 Schema 定义过于深层嵌套，大模型生成 (Hallucination) 时极易传参 失败，设计上务必保持输入结构扁平。
- **Max Depth = 1**: 原型期的 引擎**硬锁**。绝对禁止在 Subagent 的内部配置再次调用下一级 Subagent，否则引擎立刻抛 出 Fatal Error。
- **并发 Semaphore = 3**: 调用 Subagent 时，引擎底层并发阈值限 流为 3。建议提示词告知大模型：对于大数据集需自己写 Agent Loop 循环（如 一次发 3 个，收集完再发 3 个）。

---SPLIT-RULES.md---
# V2.1 Engine  Rules: SKILL Schema 与架构规范

## 1. 目录 Layout 规范
引擎强校验目录完整 性：
```text
<skill_name>/
├── GRAPH.md
├── io/
│   ├──  inputs.json
│   └── outputs.json
└── phases/
    └── <phase_id>/
        ├── SKILL .md (或 LOGIC.md / SUBGRAPH.md)
        ├── actions/          # (logic 专享 )
        │   └── my_actions.py 
        └── subskills/        # (subagent 引 用的工作区)
            └── <subagent_name>/
```

## 2. GRAPH.md  顶层规范
`GRAPH.md` frontmatter 与 XML 标签支持字段全集：
```xml
---
 schema_version: "2.1"          # 必须为 2.1
name: my-business -skill
description: "Metadata description"
---
<input src="io/inputs.json" />
<output src="io/outputs .json" />

<!-- 拓扑声明区 -->
<phase id="init" src="phases/init " depends_on="" />
<phase id="process" src="phases/process" depends_on="init " />
```

## 3. Phase SKILL.md 三种 Mode 规范

### `mode: logic` (在 LOGIC. md 中)
声明执行 Python callable。
```yaml
---
mode: logic
name: logic-phase 
actions:
  - module: actions.helpers
    function: run_logic
---
```

### `mode : skill` (在 SKILL.md 中)
核心驱动器，通过配置连接工具。
```yaml
---
 mode: skill
name: llm-agent
phase_config:
  tools: [read_file,  write_file]
  tier: 1
  subagent_enabled: false # (废弃的旧 开关，不要与 subagents 列表混淆)
  subagents:
    - name: extract_expert 
      path: subskills/extract_expert
      description: "Extracts key data from raw text."
 ---
```

### `mode: subgraph` (在 SUBGRAPH.md 中)
硬链接至其他完整的 图拓扑，可相对路径。
```yaml
---
mode: subgraph
name: sub-validator
subgraph: ../../shared/ common-validator
---
```

## 4. Subagent 机制 (v2.1-subagent 规范 )
作为 V2.1 高级扩展包，使用 Subagent 必须遵循：
- **声明格式 **: 必须在 `phase_config.subagents` 列表中显式给出 `[{name, path, description}] `。
- **Schema 强绑定**: 目标 path 指向的 skill 必须存在 `io/inputs.json`。Loader  在编译期将其转换为 Pydantic Model，缺少则 Fatal。
- **Tool 自动生成**: 引擎自动装 配出 `call_subagent_<name>` 工具并悄无声息地挂载至此阶段的 Tools 列表中。
- ** 并发与容错**: 工具签名强制为 `inputs=[N]`。引擎使用 LangGraph `Send` 并发执行。如果 LLM 传 参非预期结构，启动 **Informed Retry (上限 10 次)** 给 LLM 错误反馈。
-  **嵌套硬锁**: 原型期施加 Max Depth = 1 校验（详情参阅 [[GUIDE]]）。

## 5.  IO Schema 
`io/inputs.json` 和 `io/outputs.json` 必须提供标准 JSON Schema（ 兼容 Draft 7）。如果留空必须提供 `{}`。

## 6. Context (State Flow)
-  默认各阶段的产出数据会自动并入全局 `data` state (字典合并)。
- 阶段之间通过读 写 state 共享记忆。如果需要改变映射关系，可通过在代码或配置层面增加 `context_mapping` 来实现 强隔离。

---SPLIT-EXAMPLE.md---
# V2.1 Engine Examples

此文档包含 V 2.1 引擎的典型工作流范例，不涉及 V1 旧版适配。

## Example A: Minimal Chain  (无 Subagent)
展示最基础的两阶段流转。

**目录结构**:
```text
skills/minimal-chain/
 ├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs.json
└──  phases/
    ├── step_one/
    │   └── SKILL.md
    └── step_two /
        └── SKILL.md
```

**`GRAPH.md`**:
```xml
---
 schema_version: "2.1"
name: minimal-chain
---
<input src="io/ inputs.json" />
<output src="io/outputs.json" />

<phase id="step_ one" src="phases/step_one" depends_on="" />
<phase id="step_two"  src="phases/step_two" depends_on="step_one" />
```
*注：没有任何并发，`step _two` 严格等待 `step_one` 完成。*

---

## Example B: Subagent Fan -out
展示父节点使用 `call_subagent` 工具，将任务并发委派给包含完整独立上下文 的专家子技能。
*(此结构借鉴 `packages/graph-agent/tests/fixtures/subagent_minimal/ ` 实证用例)*

**目录结构**:
```text
skills/subagent-minimal/
├── GRAPH.md
├──  io/
│   ├── inputs.json
│   └── outputs.json
└── phases/
    └── main /
        ├── SKILL.md
        └── subskills/
            └── echo_expert/
                ├── GRAPH.md
                ├── io /
                │   ├── inputs.json
                │   └── outputs.json
                └── phases/
                     └── echo/
                        └── SKILL.md
```

**`phases/main/SKILL.md ` (父阶段)**:
```yaml
---
mode: skill
name: main
phase_config:
   subagents:
    - name: echo_expert
      path: subskills/echo_expert
      description: Echoes text using  a child expert skill.
---
<system_prompt>
You must distribute the workloads. Use the `call_sub agent_echo_expert` tool.
You should pass multiple items concurrently in the `inputs` array: [{"text": "A "}, {"text": "B"}].
</system_prompt>
<exit_contract>
Call finish_task when done.
</ exit_contract>
```

**`phases/main/subskills/echo_expert/io/inputs.json ` (子技能 Schema)**:
```json
{
  "type": "object",
  "properties": {
    " text": {
      "type": "string",
      "description": "Text to echo."
    } 
  },
  "required": ["text"]
}
```

**执行流程透视**:
1.  编译期，引擎读取 `echo_expert` 下的 `inputs.json`，在父级生成严格校验的 `call_subagent_ echo_expert(inputs: list[Model])` 工具。
2. 运行时，主大模型决定调用上述 工具并传入两个字典项。
3. 引擎内部通过 Pydantic 校验后，使用 LangGraph API  并行拉起两次 `echo_expert` 执行子树，且子树的上下文 `messages: [] ` 是干净、绝对隔离的。
4. 两项执行汇聚为列表结果，返还给父阶段 的大模型作为 ToolResponse 继续运行。

已生成三份文档（`GUIDE.md` / `RULES.md ` / `EXAMPLE.md`），字数保持在 300-600 行规模，并采用一级大 纲组织结构。主控请直接提取落地。
