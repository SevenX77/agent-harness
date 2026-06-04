---
module: 12-contracts
doc: baseline
status: drafted
last_verified: 2026-06-03
---

# 12-contracts — Baseline(现状)

共享词汇(类型 / 异常 / 错误码 / state schema / result / validator 契约),现**散在 `core/`**,是 L0 基础层:被几乎所有模块 import。理想性质 = 自身**不依赖任何内部模块**;现实是它埋在 `core/` 上帝包里,与上层(cognitive/middleware/tools/io/runtime)循环纠缠(见 00-overview §5)。

## 覆盖代码(file:line 已核)

| 契约 | 现状 | 证据 |
|---|---|---|
| Phase AST | `class Phase`,`__all__=["Phase"]` | `core/types.py:19,80` |
| result 类 | `WorkflowMetrics`/`PathDiff`/`PhaseRecord`/`RunResult`/`WorkflowResult` | `core/result.py:14,48,58,68,92` |
| 异常树 | `GraphAgentError`(基)→ `GraphCompileError`→`LoaderError`→`SkillParseError`;`GraphExecutionError`→`GraphAgentFatalError`;`ModelProviderError`;`ResourceNotFoundError` | `core/exceptions.py:82,103,107,111,115,119,126,135` |
| 错误契约 | `ErrorPayload`(code/level/stage/message/doc_link/skill_id/phase_id/field_path/source_path) | `core/exceptions.py:21` |
| 错误码注册 | `ErrorCodeMetadata`(含 level)+ `ERROR_REGISTRY` | `core/error_registry.py:8,15` |
| state schema | `BusinessData`/`FrameworkState`/`WorkflowState`;公开别名 `BlackboardState` | `core/state.py:79,156,203` |
| validator 契约 | `VALIDATOR_SIGNATURE`(`def validate(output, state_slice, **kwargs)->None|dict`)+ `VALIDATOR_ERROR_CODES`(agent/subgraph/logic,γ0 占位) | `core/validator_contract.py:9,11` |
| 公开 surface | `run_skill`/`predict_skill`/`RunResult`/`PathDiff`/`PhaseRecord`/`BlackboardState`/5 异常 | `__init__.py __all__` |

## Baseline / Alignment 差异(详见 mvp1-alignment)
- 物理上散在 `core/`、与上层循环 → 目标抽成 L0 叶模块(去环);
- `ErrorPayload` 无 `line` 轴、定位轴 emit 不全(Task3);
- `data` 通道无 delta reducer(state-checkpoint);
- 错误码 domain 枚举缺 golden/iterate(Task1)。
