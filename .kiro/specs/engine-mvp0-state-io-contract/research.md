# Engine MVP0 — state-and-io-contract Research

## §1. 现状综述

当前 `state-and-io-contract` 模块主要通过 `BlackboardState` （定义于 `packages/graph-agent/src/graph_agent/runtime/state.py:35`）维护图的运行状态。状态包含 `data`（业务黑板）、`flow`（控制流）、`messages`（LLM对话）以及 `run_id`。其中，核心的业务黑板 `data` 采用 `shallow_dict_merge` 规约（`state.py:13`）。
在 V2.1 主线执行路径中，`run_skill(**inputs)` 会直接将所有 kwargs 原样放入 `dict(inputs)` 作为初始 `data`（`runner.py:471-477`）。后续的 LOGIC、SUBGRAPH 及 SKILL 节点都能看到并直接操作整个 `state.data`，缺乏阶段级的输入输出隔离。这种全量共享不仅导致节点间数据流向不清晰，而且使得子图调用（SUBGRAPH 和 agent-called graph）极易引发命名空间污染与合并冲突。

## §2. MVP0 目标拆分 — 已知 audit ID 一览

### P0-3 顺序覆盖冲突
`shallow_dict_merge` 不区分“并行冲突”和“顺序更新”。一旦某 key 已存在于 `data` 中，任何后续节点的正常覆盖都会触发 `[F-v21-state-conflict]`（`state.py:24-30`）。这是导致主干崩溃的致命问题。
### A1 runtime input funnel
缺少运行时输入漏斗验证。当前入口直接将所有外部参数放入 `data`，未根据根级 `io/inputs.json` 过滤非法、未声明字段，也未进行类型转换和必填项检查。
### A2 phase-level IO 契约
所有的 LOGIC/SUBGRAPH/SKILL 阶段都从全集 `state.data` 提取数据，目前 `SkillNodeAST` 与执行容器并没有实现局部的输入输出沙箱，导致节点读写边界模糊。
### A3 SUBGRAPH 父子冲突
`SUBGRAPH` 将父图的全量 `data` 传给子图（`graph_assembler.py:155`），并在子图执行完毕后进行差异计算。当子图对父图中已有 key 进行回写时，由于 P0-3 的限制，立即引发 fatal 冲突。
### A6 agent-called graph 黑板隔离
Subagent 工具调用子图时，初始输入被硬编码为 `{**before_data, **input_data}`（`graph_assembler.py:398`），子图隐式继承了全部父图黑板数据，破坏了作为独立工具的隔离性原则。
### StateMapper (新组件)
随 A2 与 A3/A6 引入，需要一种组件根据 PhaseIOSchema 从全局状态中分发局部的 `phase_input` 并在完成后提取隔离的 `phase_output`。

## §3. 各 audit ID 设计候选方案

### P0-3 顺序覆盖冲突
- **候选 A: smart_dict_reducer**
  - **Trade-off**: 允许跨 step 的顺序 `dict.update` 覆盖，仅拦截并行分支（super-step 内）同 key 写入冲突。能解决误伤，需改写 reducer 核心并引入 LangGraph 的 step context。
  - **冲击范围**: `state.py:13`，波及所有返回 state 的节点。
  - **兼容性**: 破坏性较小，但改变了旧有严格语义。
- **候选 B: 命名空间隔离 (phase_outputs)**
  - **Trade-off**: 将每个阶段的产出写入单独的 `data["phase_outputs"][phase_id]` 中。从根本上消灭顶层重名冲突，但调用方读取方式需全量重构。
  - **冲击范围**: 全局组装器 `graph_assembler.py`。
  - **兼容性**: 不兼容现有 fixture 的顶层直接读写。
- **候选 C: A + B 组合**
  - **Trade-off**: 短期内通过 A 缓解宕机，长远向 B 迁移。

### A1 runtime input funnel
- **候选 A: 显式 `filter_runtime_inputs` 漏斗 (jsonschema strict)**
  - **Trade-off**: 基于编译期提供的 schema 严格验证、过滤及补全默认值。彻底断绝外部脏数据，但如果上游系统传了多余参数会直接被静默丢弃或报错拦截。
  - **冲击范围**: `runner.py:471`，执行起点。
- **候选 B: 复用 legacy `IOManager.load_inputs`**
  - **Trade-off**: 将 V2.0 遗留代码接回 V2.1 主线。开发量小，但 `IOManager` 带有诸多 file/artifact 的复杂设定，可能弄脏 V2.1 极简的主流程。
- **候选 C: 不做漏斗，信任调用方**
  - **Trade-off**: 维持原样，完全依赖执行时的报错（最差设计）。

### A2 phase-level IO 契约
- **候选 A: 强沙箱 (Wrapper Sandboxed Context)**
  - **Trade-off**: 在执行前将 `data` 根据 `io.inputs` 切片，仅暴露切片给执行节点。保证最高安全性，但会让缺乏 io 声明的现有节点立刻挂掉。
  - **冲击范围**: 必须在 `graph_assembler.py` 中引入统一的 phase wrapper 劫持上下文。
- **候选 B: 弱沙箱 (全量透传 + Trace 警告)**
  - **Trade-off**: 依然传 `data`，但利用 Trace 分析其实际访问的 key，若越权则记警报。安全较弱，但兼容性满分。
- **候选 C: 与 context_mapping 调和**
  - **Trade-off**: 通过 pending-questions 中的机制直接显式 map，代替 schema 隐式切片提取。

### A3 + A6 (合并讨论, 子图隔离)
- **候选 A: 彻底阻断，基于 Explicit Input 启动**
  - **Trade-off**: SUBGRAPH 与 agent-called graph 都不再继承父图 `data`，启动入参必须由 mapping 显式指定，返回结果仅供工具结果或映射写入。隔离最干净，但影响所有现有子图依赖父图的写法。
- **候选 B: 保留全量 data，但依赖 smart_reducer 缓解**
  - **Trade-off**: 依然混写，只解决表面抛错。隔离性差，隐患遗留。
- **候选 C: 强制挂载输入/输出 Mapping 字段**
  - **Trade-off**: 在 AST 新增 mapping 参数，在运行时拦截并翻译。

### StateMapper
- **候选 A: 独立工具类**
  - **Trade-off**: 将装载逻辑封装为 `StateMapper`，高内聚易测试，但会增加运行时栈的层级。
- **候选 B: 匿名闭包 / Phase Wrapper 函数实现**
  - **Trade-off**: 直接写在构建图的组装循环内部，简易直接，但难以复用至 CLI 或其他调试通道。

## §4. 不依赖 PM 拍板可独立推进的工作清单

1. **测试物料准备**: 在 `test_v21_graph_assembler.py` 中补充明确的并行冲突 vs 顺序覆盖 Fixture 测试例。
2. **State 结构扩容重构**: 在 `BlackboardState` 的 TypedDict 中内部安全增加 `inputs` 和 `phase_outputs` 键的空占位，不改变现有行为。

## §5. 必须 PM 拍板才能进 task 阶段的清单

- **Q-S-P0-3**: Reducer 冲突是否通过 `smart_dict_reducer` (候选A) 放行跨步顺序覆盖？ [BREAKING]
- **Q-S-A1**: Runtime Input Funnel 严格度是否采用 jsonschema strict (候选A) 直接丢弃/拒绝脏字段？ [BREAKING]
- **Q-S-A2**: 节点的上下文是否启用强沙箱隔离 (候选A) 仅暴露声明字段？ [BREAKING]
- **Q-S-A3-A6**: 所有的子图是否彻底掐断 `parent_data` 的自动继承 (候选A) 走向 Explicit Input 纯净启动？ [BREAKING]
- **Q-S-StateMapper**: 状态分发是通过独立工具类 (候选A) 还是内置组装器函数处理？

## §6. 跟 pending-questions §3 context_mapping 双模的关系

如果 PM 在 `pending-questions` §3 中选择了不同起点，本特性的设计也会产生不同的落实方式：
- **若选 A (从零设计双模)**: A1+A2+A3+A6 的隔离均依赖 PhaseIOSchema 提供默认切片，若出现同名需要用户额外提供显式的 JSON mapping 文件配置覆盖。
- **若选 B (复用 GraphAgentHarness)**: 则漏斗会倒退向旧的 `ContextResolver` 演化，A2 的沙箱将严重受制于旧表达式解析能力的缺陷。
- **若选 C (迁移 ContextResolver 概念至 V2.1主线)**: A2 和 A3/A6 可以结合其 `{dot.path}` 语法快速实现声明式的父子图数据挑选，解决隐式传递的脏乱差。

## §7. 跟其他 3 个 engine feature 的耦合点

- **与 skill-compilation**: A2 (沙箱) 极其依赖 Block 1 的 A7 提供合法的 `PhaseIOSchema` 作为执法依据。
- **与 execution-runtime**: A6 的子黑板屏蔽规则直接影响 runtime 里的 subagent 调度和 `call_subgraph` 装配函数 (`graph_assembler.py:374-505`)。
- **与 tracing-and-observability**: 节点 NODE_START/END 事件强依赖 state-and-io 的沙箱产生纯净的 `phase_input` 和 `phase_output` 切片，以此防止 Trace JSON 被全局黑板数据撑爆。