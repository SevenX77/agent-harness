# Requirements: Subagent (V2.1 Extension)

> Spec owner: a2 Gemini (designer/analyst)
> 主控 PM facilitate IO. 内容 100% a2 reply, 主控只清 streaming spacing.

## 1. 背景与根本诉求

在构建复杂 Agent 系统时, 将所有能力堆叠在单一 prompt 中会导致模型注意力稀释和幻觉。

User 原话 (5/18):
> "现在的阶段性目标是调出一个标准化的 skill, 测试 v2.1 的各项功能, engine 的包括 backend, frontend 的功能"

User 原话 (5/14):
> "不要过度考虑向后兼容, 过去有不代表对, 原型阶段做错就推翻, 哪怕整个 app, 不是第一次重构. 思路就是 copy vs code 这种人家已经实现并且论证了的方案"

本 spec 为 V2.1 引擎引入动态调度子技能 (subagent) 的能力, 将子功能封装为 tool, 供主 agent 的循环 (agent loop) 自主决定何时调用以及如何组合, 建立真正具备复杂推演能力的生产级框架。

## 2. User Story

作为一名 PM 或 prompt 工程师, 我希望在定义一个 phase (`mode: skill`) 时, 能像添加普通 Python 函数工具一样, 直接声明其他的 skill 作为一个 subagent 工具。这样我就能让当前的大模型自主判断 "何时需要委派任务给子领域专家", 而不必让开发人员手写硬编码的 dispatcher 分发代码。如果大模型给子专家的传参格式错了, 我希望引擎能把子专家的 schema 抛给大模型让它自己重试, 而不是让任务直接崩溃。

User 原话 (5/18):
> "现在是不用 deerflow 的 subagent 模块, 而是在 agent loop 中自己调用一个 tool, 这个 tool 调用一个 subgraph, 这个 subgraph 加载一个单 agent phase 的 skill ... 这个调用 subgraph 的 tool 可以模块化, 因为与业务逻辑无关, pm 只需要编辑 subagent 中的 skill 文档就行了, 不要每个 subagent 都单独写一个 tool"

## 3. 功能性需求 (Functional Requirements)

- **FR-1 [Subagent 声明]**: 支持在 `mode: skill` 的 `phase_config` 内新增 `subagents:` 列表字段, 声明被引用的子技能即可。引擎无需新增 mode 类型。
- **FR-2 [运行时 Tool 注入]**: 引擎 loader 须在编译阶段读取 `subagents:` 声明, 自动把每一个子技能包装成一个标准的 tool (例: `call_subagent_xxx`) 注入到当前 phase 的运行时 tools 中。
- **FR-3 [并发 Fan-out 支持]**: `call_subagent` 工具必须接受数组类型 (Array) 的 inputs。主 agent 一次性下发一组输入, 引擎底层并发唤起并聚合返回。
- **FR-4 [Schema Validation & Informed Retry]**: 引擎层接管传参校验。当主 agent 调用的输入参数不符合子技能的 input schema 时, 引擎必须向主 agent 返回明确的错误信息和 expected schema, 引发 informed retry, 最大上限 10 次。
- **FR-5 [嵌套防线 Max Depth]**: 原型期硬限制嵌套深度: subagent 内部禁止再次派发二级 subagent (Max Depth = 1), 在 tool 执行层阻断。
- **FR-6 [Studio 视觉化]**: 声明了 subagent 的 canvas 节点需附带 "Toolbox" badge; 选中节点时, 右侧 Properties 面板增加 `Subagents` 只读列表 (各项目可点击以 nav 到子图谱)。

## 4. 非功能性需求 (Non-Functional Requirements)

- **NFR-1 [并发限流]**: 默认并发数上限硬设为 3 (沿用业界 DeerFlow/Claude code 安全阈值)。User 原话: "默认上限 3 个并发, 一次性发 3 个一组, 3 个一组, agent loop 自己循环做完所有的". 大模型通过自身 agent loop 循环发包 (3 个一组), 引擎不做跨轮 batch 切割。
- **NFR-2 [执行隔离性]**: 子技能执行必须切断上文污染。复用 V2.1 现有 subgraph 机制 (`_subgraph_node` 传 `messages: []` 已天然隔离)。
- **NFR-3 [可观测性]**: `call_subagent` 必须透明传递 trace ID, 支持父子 run 关联溯源。

## 5. Out of Scope

- 具体 tasks.md 任务拆解与 a1 排期 (a1 范畴)
- 极致引擎性能压测 (micro-benchmark)
- 跨 skill 调用的生产级 deployment 部署路由 (现仅聚焦 Studio 单机联调)
- subagent 之间的 memory 持久化 / A/B test 框架
- 嵌套 Max Depth > 1 的解锁条件 (留待非原型期)
