# V2.1 Engine Guide: 核心概念与最佳实践

## 1. 概念入门
V2.1 graph-agent 是一个结构化的 LLM Agent 执行引擎。与 V1 阶段将所有 Prompt 和工具混杂在一个巨大的单一文件不同，V2.1 引入了**图 (Graph)** 蓝图概念。它通过顶层 `GRAPH.md` 将复杂任务拓扑切分为多个专职的阶段 (Phase)，解决了大模型上下文污染、注意力涣散以及复杂逻辑不可控的问题。

## 2. 5 分钟 Quickstart: Hello World
创建一个极简的单阶段技能 (不包含子代理)。
**目录结构**：
```text
skills/hello-world/
├── GRAPH.md
├── io/
│   ├── inputs.json
│   └── outputs.json
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
**`phases/main/SKILL.md`**:
```yaml
---
mode: skill
name: main
phase_config:
  tools: []
---
<system_prompt>
You are a friendly greeter. Read the input name and greet.
</system_prompt>
<exit_contract>
Call finish_task with the greeting message.
</exit_contract>
```

## 3. 核心概念详解
- **Skill**: 一个可独立编译和运行的业务顶层单元，必须包含 `GRAPH.md` 和 `io/` 目录。
- **Phase**: Skill 图谱的组成节点，每个 phase 对应一个独立目录。支持 3 种 mode:
  - `logic` 纯 Python 执行 (不调用大模型)，适用于快速数据清洗。
  - `skill` LLM-driven agent，根据 Prompt 自主思考并使用设定的 Tools。
  - `subgraph` Drill-down 静态子图，将当前执行流穿透进入另一个 Skill 拓扑。
- **GRAPH.md 拓扑声明**: 使用 `<phase depends_on="A, B" />` 定义有向无环图。没有依赖的优先运行，同级节点会被引擎并发执行 (Fan-out)。
- **数据流动 (Context/State)**: 数据入口由 `io/inputs.json` 强校验后写入全局 Context (黑板)。各 Phase 根据所需读写，最终输出经 `io/outputs.json` 校验。
- **SUBGRAPH vs Subagent (动态与静态)**:
  - `SUBGRAPH.md` 是**静态调度**，编译期决定，执行到该处必定发生图跳转穿透。
  - `Subagent` 是**动态调度**，它是被封装成 Tool 提供给主大模型使用，主大模型自己根据对话意图判断“是否调用”以及“传什么参数”。

## 4. 常用 Pattern
- **Chain (链式流)**: A -> B -> C。典型的如 `text-segmentation`：提取 -> 切分 -> 审阅。
- **DAG Fan-out/in**: 分发后汇聚。如 `batch-analysis`：一个阶段分发给三个独立的评估器，最后接一个 `logic` 或 `skill` phase 汇聚分值。
- **Subagent 动态调度**: 如 `adaptation` 场景：面对数量不定的输入列表，利用 subagent tool 动态拉起子专家并发处理。

## 5. 编写最佳实践 + 常见坑
- **何时用什么 Mode (决策树)**: 
  - 是确定性的 API 调用或 JSON 处理吗？ -> **选 `logic`**。
  - 需要模糊语义理解与自主使用外部工具吗？ -> **选 `skill`**。
  - 存在固定的业务长流程且其他模块也需要复用？ -> **选 `subgraph`**。
- **何时用 Subagent vs Subgraph**: 流程固定无条件跑选 Subgraph；由大模型动态评估意图、甚至根据不同输入并发不同数量的实例，选 Subagent。
- **Subagent Input Schema**: Pydantic 会做极严的类型验证。如果 Schema 定义过于深层嵌套，大模型生成 (Hallucination) 时极易传参失败，设计上务必保持输入结构扁平。
- **Max Depth = 1**: 原型期的引擎**硬锁**。绝对禁止在 Subagent 的内部配置再次调用下一级 Subagent，否则引擎立刻抛出 Fatal Error。
- **并发 Semaphore = 3**: 调用 Subagent 时，引擎底层并发阈值限流为 3。建议提示词告知大模型：对于大数据集需自己写 Agent Loop 循环（如一次发 3 个，收集完再发 3 个）。
