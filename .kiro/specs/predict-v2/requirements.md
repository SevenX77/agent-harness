# Predict V2 Requirements — 高保真业务流推演沙盒

## 背景

在 Skill Studio 的研发工作流中，`Predict` 功能的定位经过 2026-05-06 → 05-07 多轮辩论收敛为：**让 PM 在花钱真调 LLM 之前，把 Skill 在 graph_agent 上的真实业务执行路径全部跑出来、看清楚、解决干净**。

*   **现状与转向**：原有的 `docs/architecture/PREDICT_SPEC.md` (v1.0) 过度强调"节省 Token"，且把 Predict 错误定位为 mock 模式或静态扫描器，已被标记为 **OBSOLETE**。
*   **契约红线**：根据 `POST_PLAN_C_FINAL_DECISIONS.md` §1，必须严格遵守 SDK **13-export ABI** 锁定，严禁增加新的顶层 API。
*   **实施阶段**：作为 **V2 储备功能**，本规范定义的实现仅在满足 `v1-reset-direction.md` 中定义的基建完工条件（Tauri sidecar 稳定、Input Playground 重构完等）后方可启动。
*   **4 SKILL 红线**：即使引入 Predict，`v1-reset` 要求的 4 个核心 Skill（text-segmentation, event-extraction 等）的真 LLM e2e 测试依然是项目的最高优先级质量红线。Predict 不替代真 e2e CI。
*   **Predict ≠ Lint**：`compile_skill` 已经做严格的静态 lint。Predict **不重复**这层职责。Predict 是**运行时**工具，关注 skill 真实业务能力，不关注静态结构合规。
*   **确定性与随机性分离**：graph_agent 的非 LLM 节点（LogicPhase、路由、模板渲染、ContextBridge）按设计是 **pure function** (`packages/graph-agent/src/graph_agent/core/manifest.py:260-272`)，Same input → same output；只有 LLM Phase 引入随机性。本规范的回测策略基于这条分离——黄金用例只跟 LLM Phase 绑定，不跟整个 graph 拓扑绑定。
*   **Predict 不调任何 LLM 原则**：Predictor Service 自身**严禁**调用任何 LLM（含云端商用模型 + 本地小模型）。理由：小模型测不准会给出错误指引，"错误的指引比没有指引更危险"。所有"语义层判断"（例如"这个 prompt 能不能产生符合 io.outputs 期望的输出"）都由 Copilot 用其底层强推理模型完成；Predict 的职责是**真实跑通业务流 + 把执行路径白盒化**，不是做语义推断。
*   **Copilot 形态前提**：本规范引用的 "Copilot" 是 Skill Studio 内置的对话式 agent（定位类似 Cursor / Antigravity 等 agent IDE 的内嵌 agent），通过向其注入 graph_agent 规则边界 + 多种流程 skill（创建 skill / Predict 优化 / Compile 错误处理 等）实现。Copilot 用最强推理模型保证语义判断质量。Copilot 自身具体设计在另一份独立 Copilot spec 里展开，本规范只定义 Predict 跟 Copilot 之间的诊断接口契约。

## 业务目标

Predict V2 旨在通过"高保真业务流推演沙盒"达成以下业务价值：

1.  **业务流可视化**：让 PM 看到 Skill 在 graph_agent 上**真实执行**的完整流程——Logic 节点的输入/输出、路由判断的实际走向、Phase 之间的数据流转、LLM 节点最终拼装出的完整 Prompt。
2.  **业务问题前置**：在花钱真调 LLM 之前，把 Logic 部分的所有问题（数据流断裂、模板变量缺失、ContextBridge 传错、Logic 代码异常、副作用泄露）先暴露 + 解决，Predict 跑通了再去实测 LLM。
3.  **真值可见**：LLM 节点不真调 LLM，但**完整暴露**即将发送的 prompt + io.outputs schema 给 PM 和 Copilot 看，让他们能判断"这个 prompt 在这个 context 下到底能不能产生预期输出"。
4.  **Backtesting 闭环**：当 PM 真 Run 发现 LLM 输出错误并修正预期后，把修正后的 LLM 输出固定为"黄金用例 (Golden Case)"。后续 PM 改 Prompt 时可在 Predict 模式注入 Golden Case，跨越 LLM 节点验证下游 Logic 是否仍按预期跑通。
5.  **诊断切面**：把"完整业务执行路径 + 完整 Prompt + 期望 schema" 的高保真 trace 提供给下游消费者（如 Copilot），让 Copilot 用强模型扮演"虚拟 LLM"判断业务能力达成度。

## EARS 需求

### 1. 运行时业务流推演 (Runtime Business Flow Rehearsal)

*   **Requirement 1.1: 真实逻辑执行与上下文渲染 (Real Logic Execution & Context Rendering)**
    **While** 运行在 Predict 模式下，**the graph_agent SDK shall** 真实执行所有 `LogicPhase` 节点、路由判断机制与 `ContextBridge` 映射，并基于真实运行时数据动态渲染出每个 `LLMPhase` 的最终 Prompt 字符串与 `io.outputs` Schema 结构，以暴露潜在的运行时数据拼接和业务逻辑缺陷。

*   **Requirement 1.2: LLM 请求拦截与默认挂起 (LLM Interception & Default Suspension)**
    **When** Predict 流程流转至 `LLMPhase` 时，**the graph_agent SDK shall** 拦截实际的外部 LLM 网络请求，把上一步动态渲染完毕的"完整请求载荷 (Fully Rendered Request Payload)" 完整记录到 Trace 树中。**Where** 没有提供 Golden Case、没有手动注入也没有 Copilot 预测，**the Predictor Service shall** 默认在该 LLM 节点处**挂起**当前 Predict 执行，只展示已渲染的 Prompt + io.outputs schema 给 PM 看，不再继续跑下游 Phase（避免假数据污染下游分析）。

*   **Requirement 1.3: 跨越 LLM 节点的可选机制 (Optional LLM Bridging)**
    **When** PM 需要验证 LLM 节点之后的下游 Logic 时，**the Skill Studio Backend shall** 提供以下机制让 Predict 跨越 LLM 节点继续执行（任选其一）：
    - (a) 注入已捕获的 Golden Case 中对应 Phase 的 expected output；
    - (b) 调用 Copilot 的"预测当前 LLM 节点合理输出"接口，由 Copilot 用其底层强推理模型生成一个合理的 LLM 响应占位；
    - (c) PM 在 UI 上手动输入预期 LLM 输出。
    **The Predictor Service shall NOT** 提供"无脑启发式存根 (schema-shaped 假数据)"作为主流程选项——这种数据无业务语义，会污染下游分析的可信度。

*   **Requirement 1.4: 副作用透明性 (Side-Effect Transparency)**
    **The graph_agent SDK shall NOT** 在 Predict 模式下拦截 LogicPhase 内的任何副作用 (网络调用 / 文件 IO / 数据库写入 等)。LogicPhase 按设计是 pure function (`manifest.py:260-272`)，PM 写出有副作用的代码本身就是设计 bug——**让副作用在 Predict 阶段真实暴露出来**正是 Predict 的核心价值之一，由 PM 自己负责修代码。

### 2. Golden 用例捕获与管理 (Golden Trace Lifecycle)

*   **Requirement 2.1: 真实运行轨迹的捕获与修正 (Real-Run Trace Capture)**
    **When** PM 在**真实 `run_skill` 执行后产生的 Trace 视图**中识别出某个 LLM Phase 的输出不符合业务预期，**the Skill Studio Backend shall** 允许 PM 在该节点上手动修改输出载荷（例如把误标的 A 改回 B），并提供"固定为黄金用例"按钮触发后续持久化。**This requirement does NOT apply to Predict 模式产出的 Trace** — Predict 输出（无论 Golden Case 注入 / Copilot 预测 / 手动输入）都不能作为黄金用例的源头，因为黄金用例的语义有效性必须来自真模型的真实输出 + PM 的人工修正。

*   **Requirement 2.2: 黄金用例持久化 (Golden Case Persistence)**
    **When** 触发固定动作，**the Skill Studio Backend shall** 将当前的 `inputs`、`metadata` 以及修正后的 `expected_traces`（各 LLM Phase 的期望载荷）持久化到技能目录下的 `.backtests/{case_name}.golden.json` 文件中。

*   **Requirement 2.3: LLM 节点锚定 (LLM-Node Anchoring)**
    **The system shall** 把 `.golden.json` 跟具体的 **LLM Phase** 绑定（**而非整个 Skill graph 拓扑**），`metadata` 字段含：该 LLM Phase 的 `phase_name` + `prompt_hash` + `io.outputs_schema_hash`。**When** Skill 的非 LLM 节点（LogicPhase / 路由 / 渲染）增删时，**the system shall NOT** 让 Golden Case 失效——这些节点按设计是 pure function（同输入同输出），不影响 LLM 输入输出契约。**When** LLM Phase 的 prompt 或 io.outputs schema 变更导致 hash 不匹配时，**the system shall** 在加载 Golden Case 时给出失效预警，提示 PM 重新捕获。

### 3. Golden 回测验证 (Backtest Replay)

*   **Requirement 3.1: 载荷注入执行 (Payload Injection Execution)**
    **When** PM 启动 Predict (Backtest 模式) 并指定某个黄金用例时，**the graph_agent SDK shall** 拦截所有外部 LLM 调用，并将其返回值替换为黄金用例中对应 Phase 的 `expected_output` 载荷，让流程可以跨越 LLM 节点继续执行下游 Logic。

*   **Requirement 3.2: 逻辑流转校验 (Logic Flow Verification)**
    **While** 在回测模式下运行，**the Predictor Service shall** 验证当前的 Graph 路由逻辑是否能按预期访问到黄金用例中定义的每一个节点；若发生路径偏离（例如 PM 改了路由导致原本走 LLM_1 的流量改走 LLM_2），则将运行结果标记为 `FAILED` 并展示 Diff。

### 4. SDK 接口演进与 ABI 稳定

*   **Requirement 4.1: mock_llm 多模态参数 (Multi-Modal mock_llm Parameter)**
    **The graph_agent SDK shall** 扩展 `run_skill` 的 `mock_llm` 参数以支持以下输入：
    - `None`（默认 / 不传）：触发 Req 1.2 默认挂起行为，遇 LLM 节点停下；
    - `dict`：手动注入单 Phase 的 expected output（PM 临时单 Phase 验证）；
    - `Path`：加载磁盘上单个 `.golden.json` 文件（Backtest 单 case 模式）；
    - `List[GoldenCase]`：批量回测多 case（CI / pytest 场景）。
    **The graph_agent SDK shall NOT** 接受 `bool=True` 这种"启发式生成假数据"的语义——该模式已在 Req 1.3 淘汰。

*   **Requirement 4.2: 内部接入原则 (Internal Access Principle)**
    **The Predictor Service shall** 通过 `graph_agent.core` 内部子模块或现有的 13-export 公共接口与引擎交互，**the system shall** 严禁为了实现 Predict 而向 `graph_agent` 顶层暴露新的类或方法。

### 5. 可观测性与集成

*   **Requirement 5.1: 预测模式烙印 (Predict Mode Marking)**
    **The TracingCallback shall** 在预测生成的 Trace Root 级增加 `is_predict: true` 标记。**When** 某个 LLM 节点是被 Golden Case / Copilot / 手动输入跨越的，**the TracingCallback shall** 把该节点的 `mocked_response` 设为 `true` 并标注来源（`golden_case` / `copilot` / `manual`）。

*   **Requirement 5.2: 零成本计量覆盖 (Zero-Cost Metrics)**
    **The system shall** 强制将预测运行的 `input_tokens`、`output_tokens` 和 `total_cost` 设为 `0`，以防止模拟运行污染真实的生产监控指标。

*   **Requirement 5.3: 高保真诊断上下文协议 (High-Fidelity Diagnostic Protocol)**
    **The Skill Studio Backend shall** 暴露一个标准化的诊断导出接口 (Diagnostic Export API)，向外部消费者（如 Copilot Service）输出单次 Predict 运行的完整 Trace 快照，该快照必须包含：每个 LogicPhase 的真实流转数据、每个 LLMPhase 动态渲染的完整 Prompt 文本、对应的预期 `io.outputs` Schema、以及 Backtest 模式下期望 trace vs 实际 trace 的 path diff。**The system shall NOT** 在本接口规定 Copilot 如何消费这些素材——下游消费者的具体行为由 Copilot spec 自己定义。

### 6. 实施约束与共存

*   **Requirement 6.1: V2 启动门禁 (V2 Activation Gate)**
    **The system shall** 只有在 Tauri Python Sidecar 集成稳定、Input Playground 重构闭环且 monorepo 彻底拆分后，才允许启动本规范的开发实施。

*   **Requirement 6.2: 真实 e2e 优先权 (Real e2e Priority)**
    **While** 提供 Predict 功能作为研发加速工具，**the system shall** 维持现有 4 个核心 Skill 的真 LLM e2e 测试作为 CI 流程的唯一"最终通过标准"。Predict 不进入 CI 替代真 e2e。

## Out of Scope

1.  **Copilot 自身设计**：Copilot 的具体形态、模型选型、对话协议、修复建议生成算法等都属于 Copilot spec 范围，本规范只定义 Predict 跟 Copilot 之间的诊断接口契约。
2.  **多进程并发预测**：V2 阶段仅支持单次 Predict 执行，暂不考虑高并发场景下的资源抢占优化。
3.  **生产环境的副作用沙盒化**：本规范不为 LogicPhase 提供副作用拦截或沙盒化能力。PM 自己负责把 LogicPhase 写成 pure function。

## Open Questions

### 已澄清（保留以备后人查阅）

*   ~~Q1: 内置小模型部署成本~~ → **已解**：Predict 不调任何 LLM (含小模型)，所有语义判断由 Copilot 接管。详见 Background "Predict 不调任何 LLM 原则" + Req 1.3。
*   ~~Q3: Golden Case 可维护性~~ → **已解**：Golden Case 只绑 LLM Phase 的 prompt + io.outputs schema，跟 graph 拓扑解耦。详见 Background "确定性与随机性分离" + Req 2.3。
*   ~~Q4: Copilot 形态~~ → **已解**：参照 Cursor / Antigravity 类对话式 agent，由 Copilot spec 自己设计。详见 Background "Copilot 形态前提"。

### 仍待 design.md 拍板

*   **Q2: 独立 Service 的架构边界**：Predictor Service 作为 Studio 后端独立逻辑层，如何调用 SDK 内部的 `StateGraph` 而不导致循环依赖或破坏 13-export 的纯粹性？候选方案 (Studio 后端独立服务 / SDK 内部参数透传 / 混合方案) 三选一对比留待 `design.md` 给出 + user 拍板。
