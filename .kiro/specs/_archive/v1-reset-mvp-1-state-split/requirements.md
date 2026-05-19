# MVP-1 Requirements — A1 WorkflowState 业务/框架物理拆分

## 背景

graph_agent v1-reset 序列 MVP-1 (依据 docs/superpowers/specs/2026-04-28-v1-reset-direction.md)。MVP-0 (commit 5decd0a) 完成基石清创，MVP-1 处理 16-dim audit 的 A1 维度。

## 业务目标

把 `WorkflowState` 从单一 TypedDict（context: dict[str,Any] 混杂垃圾桶）拆为业务数据 + 框架元数据两个物理隔离的子结构，让 `_md_id`/`_finish_task_result` 等框架字段离开用户业务字段空间，根除"v3 SKILL 6 轮 smoke 修 9 个 bug"那条接口契约缺失链。

## EARS 需求

### Req 1 — 状态拆分模型存在
**WHEN** loader 创建 initial state，**THE SYSTEM SHALL** 暴露 `WorkflowState` 含 3 顶层字段：`data: BusinessData`、`flow: FrameworkState`、`messages: list[AnyMessage]`。`BusinessData` 是 Pydantic v2 BaseModel `extra="allow"`，`FrameworkState` 是 Pydantic v2 BaseModel `extra="forbid"`。

### Req 2 — 业务数据与框架元数据物理隔离
**WHEN** 任意运行时模块（middleware / phase_executor / finish_task / md_to_json）写状态，**THE SYSTEM SHALL** 强制：
- 业务字段（用户 SKILL schema 解析出的字段）只能写到 `state["data"]`
- 框架元字段（`_md_id` / `finish_task_result` / `hop_count` / `validation_warnings` 等）只能写到 `state["flow"]`
- `state["data"]` 内不允许任何以 `_` 开头的字段（invariant）
- `state["flow"]` 必须通过 `model_validate` 严格校验（extra=forbid）

### Req 3 — finish_task 数据通道改造
**WHEN** `finish_task` 工具被 LLM 调用，**THE SYSTEM SHALL** 把结果写到 `state["flow"].finish_task_result` 而非 `state["context"]["_finish_task_result"]`。`md_to_json` 不再向 `context` 注入 `_md_id`。

### Req 4 — middleware 适配
**WHEN** middleware（`ValidationMiddleware` / `ClarificationMiddleware` / `UnattendedClarificationMiddleware`）读写状态，**THE SYSTEM SHALL** 通过 `state["data"]` / `state["flow"]` 而非 `state["context"]` 访问；`state["data"].model_copy(update=...)` 进行不可变更新。

### Req 5 — Reducer 行为定义
**WHEN** LangGraph 触发 reducer 合并状态，**THE SYSTEM SHALL**：
- `messages` 用 `add_messages` reducer（保持 LangGraph 标准）
- `data` 用 replace 模式（框架统一 merge，跨 phase 不累积）
- `flow` 用字段级更新（部分字段如 `metrics`/`retry_counts` 累积，部分字段如 `finish_task_result` 覆盖）

### Req 6 — 序列化兼容
**WHEN** LangGraph checkpointer 持久化状态，**THE SYSTEM SHALL** 通过 Pydantic v2 `model_dump(mode="json")` 序列化 `data` 和 `flow`，反序列化时 `model_validate`。**放弃旧版 checkpoint 兼容**（A 维度破坏性升级，不提供 migration script）。

### Req 7 — SKILL 兼容
**WHEN** 编译现有 4 核心 SKILL（text-segmentation v0/v1/v2/v3 + md-patch + finish-validator + clarification 内置），**THE SYSTEM SHALL** 保持 compile 状态不变（WARN-only / 1 producer PASS），且 e2e smoke 跑 1 chapter 不破裂。

### Req 8 — Baseline diff 验证
**WHEN** MVP-1 收尾，**THE SYSTEM SHALL** 满足下列 baseline diff 指标：
- `state["data"]` 中 `_` 开头字段 = 0
- `state["flow"]` 通过 `model_validate(strict=True)` = pass
- 全工程 dict-mutation 站点数（`context["_*"] = ...` 模式）从 26+ 收拢至 ≤ 5
- pytest 全过（不退步），test_strict_v2 14 pre-existing failures 仍 isolated
- ContextBridge 演化为 `BusinessData` 的工厂类（不再触碰框架元数据）

### Req 9 — 隐藏耦合排查
**WHEN** 拆分实施，**THE SYSTEM SHALL** 显式排查 `**state` 解包模式的 callback / middleware（grep `\*\*state`），按拆分后 schema 改造或砍掉。

## Out of scope（MVP-1 不做）

- A5 SchemaEngine 抽出 → MVP-2
- A7 IOManager 抽出 → MVP-2
- A2 Loader 重画 / A9 启动 hack 清理 / B3 middleware 简化 → MVP-3
- A3 Phase Executor 重画 → MVP-4 (MVP-1 只做 phase_executor 的 state 读写适配，不重画整体)
- A4 finish_task 数据通道完全重画 → MVP-4 (MVP-1 只把元数据从 context 移到 flow，不改 finish_task 的整体接口)
- 跑全章 e2e smoke 全部断言 → MVP-5
