---
module: 01-contract/04-data-contracts
doc: baseline
status: drafted（迁自 _migration-src/12-contracts + 代码实证）
---

# 04-data-contracts — Baseline(现状)

> 现状来源(迁移时逐行复核 `file:line`):
> - 迁移源:`_migration-src/12-contracts/{baseline,mvp1-alignment}.md`(已 drafted)
> - `packages/graph-agent/src/graph_agent/core/state.py`(`BusinessData:79`/`FrameworkState:156`/`WorkflowState:203`;langgraph `DeltaChannel` 导入 `:21`)
> - `core/result.py`(RunResult/PhaseRecord/PathDiff)· `core/exceptions.py:21`(ErrorPayload)· `core/validator_contract.py`
> - langgraph 底座:`StateGraph` state / `AgentState.messages` / `DeltaChannel` / checkpointer(引用不复述)

待迁:各形状当前定义 + 埋在 `core/` 的位置 + 与"抽成 L0 叶"的差异。
