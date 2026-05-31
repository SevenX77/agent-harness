# Round 31 API Surface Rightsizing Research

## §1 18 → 65 演化机制溯源

从 18 个 `__all__` 导出激增至 65 个契约符号，并非正常的设计意图（“真膨胀”），而是一次典型的“Audit 招供”与事实冻结（De Facto Contract）。

根据历史文档溯源：`graph_agent.__all__` 在设计之初确实划定了 18 个核心 Public ABI，且明确声明 `core.*` 等属于内部 Helper。然而，随着引擎功能的增强，外部 Consumer（特别是 Studio backend 与 Gateway）在业务开发中直接越过了 `__all__` 边界，强依赖了底层的深层对象。

在 Round 27 (Contract Docs Baseline Freeze) 时，PM 的最高指令是“功能一个都不能少……API 接口也是，说好开放哪些接口，什么功能，一个都不能少，这是黄金原则，不可动摇”。为了在重构阶段保底不丢功能，Round 27 采取了基于消费者使用现状的逆向冻结策略：将 `CONSUMER-API-INVENTORY.md` 扫描到的**实际被消费的表面（Actual Consumption Surface）**全部列入契约保护。这 47 个灰色符号（加原有 18 个共 65 个）被迫从“实现细节”升格为“不可动摇的契约基线”，这是导致 API 表面在数字上发生所谓“膨胀”的真实演化机制。

## §2 18 不够的根因分析

为什么外部 Consumer 会觉得 18 个稳定导出“不够”？根本原因在于三个维度的结构性失调：

1. **Python 模块边界的 Enforcement 失灵**：Python 的 `__all__` 和 `_` 前缀仅仅是软约束（Linter 级别），不能物理阻断 import。例如 Gateway 直接 `from graph_agent.core._predict_internal.interception import PredictGatewayChatModel` 畅通无阻，导致私有协议轻易外泄。
2. **Consumer 依赖深度与强类型需求**：以 14 个 callback events 为例，Studio 里的 `run_manager.py` 需要从 `tracing.jsonl` 中反序列化出强类型的事件对象，因为原本缺乏统一的 Wire Format 门面，开发者直接 import 所有的 Pydantic event subclass (`PhaseStartEvent`、`LLMCallEvent` 等) 参与业务逻辑。
3. **Vendor 设计缺口 (Facade 的缺失)**：18 个基线缺少对高级复合生命周期的封装。例如，Predict (推演) 功能极其复杂，涉及到 Strategy 匹配、Path Diff 计算等，但并未暴露诸如 `predict_skill` 这样的 Facade，逼迫 Studio（如 `predictor.py`）必须像散装零件一样 import `HeuristicStubStrategy`、`compute_diff` 并在应用层自己组装这些核心逻辑。同样地，AST Parser 也缺少高层的 Opaque 容器封装。

## §3 47 个非 `__all__` 符号的分类必要性逐一审视

依据 Inventory 的 47 个唯一符号，严格梳理其分类如下：

1. **14 Callback events**：**极度不必要暴露**。事件流本质上是 Wire Format（例如发往 WebSocket 的 JSON），完全可以且应该收敛成 1 个 Root Union 类型（即现存的 `CallbackEvent` 或提供单独的 JSON 解析入口），Studio 不应该直接在业务层与另外 13 种子类强耦合。
2. **12 `_predict_internal`**：**设计漏洞与封装缺失**。这些都是带有 `_` 前缀的私有模型和函数。暴露它们把 Predict 的核心装配逻辑泄露给了下游。框架设计上应当将其回收，暴漏一个高层的 `predict_skill(...) -> PredictResult` 以及少量的配置枚举数据类。
3. **5 Manifest AST nodes** (已扣除 vendor-only 的重复项)：**应当封装**。外部消费 AST (`AgentNodeAST`, `LogicNodeAST`, `SubgraphNodeAST`, `GraphManifest`, `GraphPhaseRef`) 是典型的越权。应该用 1 个 `SkillManifest`（Opaque Container）暴露出如 `manifest.get_phase_schema()` 这样的访问器方法，对外部完全隐藏底层 AST 类型的存在。
4. **6 Vendor-only**：**死代码，该删**。`parse_skill_file`, `AgentSkillDef`, `GraphSkillDef`, `PersonaSkillDef`, `IoInput`, `CompileIssue` 仅仅因为曾经被 Tauri vendor 拷贝过去且没有被及时清理，完全没有保留到核心 API 契约的必要。
5. **10 个其他基础设施与异常**：
   - 异常类 (3个)：`ExecutionError` (gateway live), `SkillCompileError` (studio+vendor), `SkillResolutionError` (studio live)。**注意：`SkillCompileError` 和 `__all__` 里的 `SkillCompilationError` 是两个不同的符号，外部代码确实直接依赖了它们。**
   - LLM 配置与客户端 (4个)：`LLMClientManager`, `load_config`, `ProviderDef`, `ResolvedProvider`。属于模型配置与运行时环境的基础设施，应剥离到独立的 Config/LLM Provider 构建模块中作为单入口传入，不应零散暴露。
   - 辅助与扩展 (3个)：`to_jsonable_dict` (callback 序列化 helper, 应收回内部), `SkillLoader`, `serialize_graph` (属于有价值的编译/序列化扩展能力，可以考虑通过 Facade 接口提升到公开契约序列)。

*(分类合计: 14 + 12 + 5 + 6 + 10 = 47 个非 `__all__` 符号，严格闭合无遗漏。)*

## §4 第一性原理: graph-agent SDK 应该暴露多少 symbol?

从第一性原理出发，一个类似于 "document-driven LLM agent harness SDK" 的底层框架，应当围绕**“指令入口 (Verbs)”**和**“黑盒载体 (Nouns)”**构建边界，而绝不应暴露其认知装配与执行引擎的内部零件。

**暴露原则 (Principles)**：
1. **Opaque Types (数据掩蔽/不透明)**：所有通过解析生成的数据结构（如 AST、CompiledGraph、Phase Records），对外部应该只是不可变的 Handle/Container。Consumer 只能传递它、调用其顶层方法，不能解构它。
2. **Wire Format over Class**：跨进程、跨域通信的事件（Callback Events）优先暴露 JSON/Dict 结构与统一校验入口，而非散落暴露内部的 Pydantic Class 类。
3. **Layered Facade (分层门面)**：预测 (Predict)、执行 (Run)、加载 (Load)、编译 (Compile) 只需要暴露少数几个入口函数和 Result 载体，拒绝下游组装内部 Strategy。

**合理数字范围：25 个符号**。
理由与构成：
- **Core Verbs (6)**: `run_skill`, `compile_skill`, `predict_skill` (新增 Facade), `assemble_graph`, `serialize_skill`, `serialize_graph`
- **Core Nouns/Containers (6)**: `WorkflowResult`, `CompileResult`, `PredictResult` (收敛后), `CompiledSkill`, `CompiledStateGraph`, `SkillManifest`
- **Context/Resolution (3)**: `BlackboardState`, `LocalWorkspaceResolver`, `SkillLoader` (可考虑提升)
- **Observability (4)**: `Callback` (基类), `LoggingCallback`, `TracingCallback`, `CallbackEvent` (唯一的事件类型入口)。*(注：现有 `__all__` 中的 `MetricsCallback` 实证无 live 消费者，应按策略废弃。)*
- **Errors (6)**: `GraphAgentError` 基类及核心相关的顶级 Errors (`SkillLoadError`, `SkillCompilationError`)，外加外部已强依赖的 3 个 live 异常 (`ExecutionError`, `SkillCompileError`, `SkillResolutionError`)。受制于业务使用现状，目前不能强删，需保留 6 个以满足黄金原则要求。

## §5 实操路径

将现有 65 契约收缩到最优雅目标的具体手法如下（包含三轴定性评估：证据度 High/Medium/Low × 影响度 High/Medium/Low × 方案置信度 A/B/C）：

1. **手法 1：Predict Facade 升级 (回收 11 个 `_predict_internal`，+1 个 Facade，净 -10 符号)**
   - **定性**: [证据: High | 影响: High | 置信度: B]
   - 在 `graph_agent.__init__` 新增 `predict_skill` 函数与 `PredictResult` 对象，作为独立的推演入口。
   - 删除下游（Studio `predictor.py` 与 Gateway）对 `GoldenCase`, `PathDiff`, `compute_diff`, `assemble_phase_record` 及各种 MockStrategy 的直接调用。下游迁移只需调用 `predict_skill` 并传入参数配置。
   - **Consumer 迁移成本：中等**（需修改 Studio backend 的 Predictor 架构装配，转交控制权。方向明确，但 Studio predictor.py 控制权转交 + Gateway interception 替代 + Studio schema 兼容细节有待进一步设计和验证）。
2. **手法 2：Event Wire Format 收口 (回收 13 个 event variants，净 -13 符号)**
   - **定性**: [证据: High | 影响: Medium | 置信度: A]
   - 仅导出 `CallbackEvent` (Root Union Type) 作为类型校验和反序列化入口。
   - Studio 移除对 `PhaseStartEvent`、`LLMCallEvent` 等子类的直接 import，改为基于字典结构或 `CallbackEvent.model_validate_json()` 的结果字段进行分支判定。
   - **Consumer 迁移成本：低**（仅需更改 `run_manager.py` 和 gateway tracing 的反序列化与导入方式，代码即可直接落地）。
3. **手法 3：Manifest AST 掩蔽 (回收 5 个 AST，净 -5 符号)**
   - **定性**: [证据: High | 影响: Medium | 置信度: B]
   - 取消公开导出具体的 AST 节点 (`AgentNodeAST`, `LogicNodeAST`, `SubgraphNodeAST`, `GraphManifest`, `GraphPhaseRef`)。为 `SkillManifest` 与 `CompiledSkill` 增加对外封装好的数据访问器方法（例如针对 Studio 序列化所需的图提取）。
   - **Consumer 迁移成本：中等**（Studio 解析节点部分需重构，但整体逻辑变动不深）。
4. **手法 4：清理死代码与多余内部依赖 (回收 6 vendor-only + 4 Config + 1 Helper，净 -11 符号)**
   - **定性**: [证据: High | 影响: Low | 置信度: A (Vendor删) / B (基建)]
   - 从契约中立即剔除 6 个 Tauri vendor 死代码符号，清理相关历史引入。回收 `to_jsonable_dict`。
   - 重构 `load_config` 与内部 Provider 模型 (`ProviderDef`, `ResolvedProvider`, `LLMClientManager`)，改为更高层次的构建器传参，不向外部暴露 Definition 模型。
   - **Consumer 迁移成本：零至极低**（Vendor死代码直接删，基础设施改 Builder）。
5. **手法 5：废弃 MetricsCallback (净 -1 符号)**
   - **定性**: [证据: High | 影响: Low | 置信度: A]
   - 经审查 `MetricsCallback` 确实无 live 消费者（仅在 target/debug 构建产物中），降级到 deprecated alias 一个 round 后彻底删除，因属 API 变更应按规范显式标记 [BREAKING]。

*(算术闭合核验：65 个初始符号 - 10 (手法1) - 13 (手法2) - 5 (手法3) - 11 (手法4) - 1 (手法5) = 25 个最终符号。)*

## §6 你的最终推荐

**最终推荐数字：25 个符号**。
**定性**: [证据: High | 影响: High | 置信度: B (整体路径明确，但局部细节如 Error 收敛和 Predict 权柄交接需进一步 Design 验证，不可无设计直接落地)]

**配套手法：**
彻底实行**“单向门面（Facade-Only）”架构**。放弃目前“按消费现状点名冻结”的妥协做法。具体实施：
- 新增 `predict_skill` 统一取代零碎的推演逻辑导入；
- 将 14 个事件类降维成 1 个泛型 Root 解析器（`CallbackEvent`）；
- AST 和 Graph 模型全部转为无对外公共属性的 Opaque Handle；
- 彻底删除 Vendor 的僵尸依赖；
- 隐式废弃无消费者的 `MetricsCallback`，标记 [BREAKING] 后下线。

通过重塑这几大类入口，可以将庞杂的 65 个被动契约精准瘦身到符合第一性原理的 **25 个**（算术严密闭合），既保全所有系统功能（坚守黄金原则），又完美地封堵了跨越模块边界越权调用的漏洞。对于目前散落的 6 个 Error 异常体系（由于有真实 live 依赖），目前建议作为基线直接保留，若需进一步收敛为 4 个，则属于置信度 C 的探索项，须单独立项重新设计 Error Facade。