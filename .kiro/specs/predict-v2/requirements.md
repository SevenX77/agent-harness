# Predict V2 Requirements — 高保真业务流推演沙盒

## 背景

在 Skill Studio 的研发工作流中，`Predict` 功能的定位经过 2026-05-06 → 05-07 多轮辩论（含 User Round 8 翻转确认）收敛为：**"别废话，让流程跑起来" —— 跨越 LLM 节点，提前扫清并修复所有非 LLM 相关的 Logic 障碍。**

*   **现状与转向**：旧 framing 纠结于假数据的“语义危害”而导致 Predict 在遇到 LLM 节点时默认挂起，这严重阻碍了 PM 调试后续逻辑。**新 framing (Round 8)** 确立了 Predict 的核心价值是：在真调 LLM 前，通过自动化手段跨越 LLM 节点，把后续 Logic 部分的所有 bug（如 counter 没初始化、AttributeError、API 拼装错、Auth 失败、URL 拼接 bug 等）暴露并修复。
*   **启发式存根重新定位**：从被淘汰的 "Fallback" 模式提升为 **"Logic 压力测试基准 (Logic Baseline)"**。不追求语义正确，只追求“结构合法”以激活下游代码。推荐实现：结构化占位符 `{"text": "<mock_data>", ...}` —— 既能保证下游跑通，又能通过 `<mock_...>` 标签在 Trace 中保持清醒视觉反馈。
*   **填充优先级链条 (Priority Chain)**：
    | 优先级 | 来源 | 含义 |
    |---|---|---|
    | **P0** | Golden Case 回测 | 最优先，复用 PM 已确认的真实语义数据 |
    | **P1** | Copilot 高质量预测 | 次优先，提供较好的语义预测，支持下游复杂逻辑 |
    | **P2** | 启发式存根 (Minimal Stub) | 保底，确保流程不中断，继续扫描 Logic 风险 |
*   **契约红线**：根据 `POST_PLAN_C_FINAL_DECISIONS.md` §1，必须严格遵守 SDK **13-export ABI** 锁定，严禁增加新的顶层 API。
*   **实施阶段**：作为 **V2 储备功能**，本规范定义的实现仅在满足 `v1-reset-direction.md` 中定义的基建完工条件（Tauri sidecar 稳定、Input Playground 重构完等）后方可启动。
*   **4 SKILL 红线**：即使引入 Predict，`v1-reset` 要求的 4 个核心 Skill 的真 LLM e2e 测试依然是项目的最高优先级质量红线。Predict 不替代真 e2e CI。
*   **Predict ≠ Lint**：`compile_skill` 已经做严格的静态 lint。Predict **不重复**这层职责。Predict 是**运行时**工具，关注 skill 真实业务能力，不关注静态结构合规。
*   **确定性与随机性分离**：graph_agent 的非 LLM 节点（LogicPhase、路由、模板渲染、ContextBridge）按设计是 **pure function** (`packages/graph-agent/src/graph_agent/core/manifest.py:260-272`)，Same input → same output；只有 LLM Phase 引入随机性。本规范的回测策略基于这条分离——黄金用例只跟 LLM Phase 绑定，不跟整个 graph 拓扑绑定。
*   **Predict 不调任何 LLM 原则**：Predictor Service 自身**严禁**调用任何 LLM（含云端商用模型 + 本地小模型）。所有语义层判断或高质量预测 (P1) 都由 Copilot 用其底层强推理模型完成。
*   **Copilot 形态前提**：本规范引用的 "Copilot" 是 Skill Studio 内置的对话式 agent。本规范只定义 Predict 跟 Copilot 之间的诊断接口契约。

## 业务目标

Predict V2 旨在通过"高保真业务流推演沙盒"达成以下业务价值：

1.  **业务流可视化**：让 PM 看到 Skill 在 graph_agent 上**真实执行**的完整流程——Logic 节点的输入/输出、路由判断的实际走向、Phase 之间的数据流转、LLM 节点最终拼装出的完整 Prompt。
2.  **Logic 障碍提前扫清**：在真调 LLM 之前，强制跑通并修复 Logic 部分的所有问题——既包括**抽象类别**（数据流断裂、模板变量缺失、ContextBridge 传错、Logic 代码异常、副作用泄露），也包括**具体硬伤**（counter 没初始化、AttributeError、API 拼装错、Auth 失败、URL 拼接 bug 等）。**这是 Predict 的第一优先级红利**。
3.  **真值可见与诊断导出**：完整暴露即将发送的 prompt + io.outputs schema 供 Copilot 或 PM 进行静态/语义诊断，而不暗示在此处停下等待人工决策。
4.  **Backtesting 闭环**：当 PM 真 Run 发现 LLM 输出错误并修正预期后，把修正后的 LLM 输出固定为"黄金用例 (Golden Case)"。后续 PM 改 Prompt 时可在 Predict 模式注入 Golden Case，跨越 LLM 节点验证下游 Logic 是否仍按预期跑通。
5.  **诊断切面**：把"完整业务执行路径 + 完整 Prompt + 期望 schema" 的高保真 trace 提供给下游消费者（如 Copilot），让 Copilot 用强模型扮演"虚拟 LLM"判断业务能力达成度。

## EARS 需求

### 1. 运行时业务流推演 (Runtime Business Flow Rehearsal)

*   **Requirement 1.1: 真实逻辑执行与上下文渲染 (Real Logic Execution & Context Rendering)**
    **While** 运行在 Predict 模式下，**the graph_agent SDK shall** 真实执行所有 `LogicPhase` 节点、路由判断机制与 `ContextBridge` 映射，并基于真实运行时数据动态渲染出每个 `LLMPhase` 的最终 Prompt 字符串与 `io.outputs` Schema 结构，以暴露潜在的运行时数据拼接和业务逻辑缺陷。

*   **Requirement 1.2: 逻辑贯通执行 (End-to-End Logic Rehearsal)**
    **When** Predict 流程遇到 `LLMPhase` 且无黄金用例或 Copilot 参与时, **the Predictor Service shall** 自动生成结构合法的"启发式存根 (Heuristic Stub)"填充输出载荷, 以确保流程不中断并继续执行后续所有的 `LogicPhase` 节点。

*   **Requirement 1.3: 存根具象化标记 (Stub Visibility)**
    **The system shall** 在启发式存根中注入明显的占位符特征 (如 `{"text": "<mock_data>"}`), 使 PM 在 Trace 视图中能清晰识别该数据流非真实业务输出。

*   **Requirement 1.4: 副作用透明性 (Side-Effect Transparency)**
    **The graph_agent SDK shall NOT** 在 Predict 模式下拦截 LogicPhase 内的任何副作用 (网络调用 / 文件 IO / 数据库写入 等)。让副作用在 Predict 阶段真实暴露出来正是其扫清 Logic 障碍的核心价值，由 PM 自己负责修代码。

### 2. Golden 用例捕获与管理 (Golden Trace Lifecycle)

*   **Requirement 2.1: 真实运行轨迹的捕获与修正 (Real-Run Trace Capture)**
    **When** PM 在**真实 `run_skill` 执行后产生的 Trace 视图**中识别出某个 LLM Phase 的输出不符合业务预期，**the Skill Studio Backend shall** 允许 PM 在该节点上手动修改输出载荷，并提供"固定为黄金用例"按钮触发后续持久化。**This requirement does NOT apply to Predict 模式产出的 Trace** — Predict 输出（无论 Golden Case 注入 / Copilot 预测 / 启发式存根 / 手动输入）都不能作为黄金用例的源头，因为黄金用例的语义有效性必须来自真模型的真实输出 + PM 的人工修正。

*   **Requirement 2.2: 黄金用例持久化 (Golden Case Persistence)**
    **When** 触发固定动作，**the Skill Studio Backend shall** 将当前的 `inputs`、`metadata` 以及修正后的 `expected_traces` 持久化到技能目录下的 `.backtests/{case_name}.golden.json` 文件中。

*   **Requirement 2.3: LLM 节点锚定 (LLM-Node Anchoring)**
    **The system shall** 把 `.golden.json` 跟具体的 **LLM Phase** 绑定（**而非整个 Skill graph 拓扑**）。当非 LLM 节点增删时，Golden Case 不失效；当 LLM Phase 的 prompt 或 schema 变更导致 hash 不匹配时给出失效预警。

### 3. Golden 回测验证 (Backtest Replay)

*   **Requirement 3.1: 载荷注入执行 (Payload Injection Execution)**
    **When** PM 启动 Predict (Backtest 模式) 并指定某个黄金用例时，**the graph_agent SDK shall** 拦截所有外部 LLM 调用，并将其返回值替换为黄金用例中对应 Phase 的 `expected_output` 载荷（P0 优先级）。

*   **Requirement 3.2: 逻辑流转校验 (Logic Flow Verification)**
    **While** 在回测模式下运行，**the Predictor Service shall** 验证当前的 Graph 路由逻辑是否能按预期访问到黄金用例中定义的每一个节点；若发生路径偏离，则将运行结果标记为 `FAILED` 并展示 Diff。

### 4. SDK 接口演进与 ABI 稳定

*   **Requirement 4.1: 混合预测模式分发 (Hybrid Prediction Dispatching)**
    **The graph_agent SDK shall** 扩展 `run_skill` 的 `mock_llm` 参数以支持以下多级分发逻辑：
    - `None` (默认): 触发 **P2 启发式存根**，确保流程不中断，而不是默认挂起；
    - `dict` / `Path` / `List`: 触发 **P0 Golden Case** 注入路径；
    - 内部接口支持 **P1 Copilot 高质量预测**：当 Copilot 在线时，优先于 P2 使用其生成的语义占位。

*   **Requirement 4.2: 内部接入原则 (Internal Access Principle)**
    **The Predictor Service shall** 通过 `graph_agent.core` 内部子模块或现有的 13-export 公共接口与引擎交互，严禁为了实现 Predict 而向 `graph_agent` 顶层暴露新的类或方法。

### 5. 可观测性与集成

*   **Requirement 5.1: 预测模式烙印 (Predict Mode Marking)**
    **The TracingCallback shall** 在预测生成的 Trace Root 级增加 `is_predict: true` 标记。**When** 某个 LLM 节点是被跨越的，标注来源（`golden_case` / `copilot` / `heuristic_stub` / `manual`）。

*   **Requirement 5.2: 零成本计量覆盖 (Zero-Cost Metrics)**
    **The system shall** 强制将预测运行的 `input_tokens`、`output_tokens` 和 `total_cost` 设为 `0`。

*   **Requirement 5.3: 高保真诊断上下文协议 (High-Fidelity Diagnostic Protocol)**
    **The Skill Studio Backend shall** 暴露一个标准化的诊断导出接口 (Diagnostic Export API)，向外部消费者（如 Copilot Service）输出单次 Predict 运行的完整 Trace 快照。

### 6. 实施约束与共存

*   **Requirement 6.1: V2 启动门禁 (V2 Activation Gate)**
    **The system shall** 只有在 Tauri Python Sidecar 集成稳定、Input Playground 重构闭环且 monorepo 彻底拆分后，才允许启动本规范的开发实施。

*   **Requirement 6.2: 真实 e2e 优先权 (Real e2e Priority)**
    **While** 提供 Predict 功能，**the system shall** 维持现有 4 个核心 Skill 的真 LLM e2e 测试作为 CI 流程的唯一"最终通过标准"。

## Out of Scope

1.  **Copilot 自身设计**。
2.  **多进程并发预测**。
3.  **生产环境的副作用沙盒化**。

## Open Questions

### 已澄清

*   **Q1: 内置小模型部署成本** → 已解：Predict 不调任何 LLM，P1 语义判断由 Copilot 接管。
*   **Q3: Golden Case 可维护性** → 已解：Golden Case 只绑 LLM Phase 的 prompt + schema，跟 graph 拓扑解耦。
*   **Q4: Copilot 形态** → 已解：参照 Cursor / Antigravity 类对话式 agent。

### 仍待 design.md 拍板

*   **Q2: 独立 Service 的架构边界**：Predictor Service 作为 Studio 后端独立逻辑层，如何调用 SDK 内部的 `StateGraph` 而不导致循环依赖或破坏 13-export 的纯粹性？候选方案 (Studio 后端独立服务 / SDK 内部参数透传 / 混合方案) 三选一对比留待 `design.md` 给出 + user 拍板。
