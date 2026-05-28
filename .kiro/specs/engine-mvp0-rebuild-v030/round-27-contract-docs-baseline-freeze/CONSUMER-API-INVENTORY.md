# Consumer API Inventory: graph_agent Imports in apps/ and scripts/

## Scope

- Scan roots: `apps/`, `scripts/`
- Included: non-test Python source files, including checked-in Studio Tauri `vendor/backend` and `vendor/resources` consumers.
- Excluded: `**/tests/**`, `test_*.py`, `__pycache__`, `node_modules`, virtualenv/cache directories, `apps/studio/tauri/target/**` generated build output, and vendored Python stdlib under `**/vendor/python/**`.
- Method: `rg --no-ignore` found candidate files containing `from graph_agent...` / `import graph_agent...`; AST parsing then expanded every imported symbol, including multi-line imports.
- Baseline contract set: `packages/graph-agent/src/graph_agent/__init__.py::__all__` 18 symbols.

Inventory result: 21 consumer files, 107 imported symbol occurrences, 53 unique `(symbol, source module)` pairs.

## Execution / Runner

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `compile_skill` | `graph_agent` | 是 | 否 | apps/studio/backend/app/services/skills.py:19；<br>apps/studio/tauri/vendor/backend/app/services/skills.py:13；<br>apps/studio/tauri/vendor/backend/app/services/validator.py:13 |
| `run_skill` | `graph_agent` | 是 | 否 | apps/studio/backend/app/services/predictor.py:11；<br>apps/studio/backend/app/services/run_manager.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:10；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:18 |
| `run_skill` | `graph_agent.core.runner` | 是 | 否 | apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:14；<br>apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:46；<br>apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:167；<br>scripts/run_e2e_test_enhanced.py:22 |

## Loader

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `CompiledSkill` | `graph_agent.core.loader` | 是 | 否 | apps/studio/backend/app/services/skills.py:22 |
| `SkillLoader` | `graph_agent.core.loader` | 否 | 否 | apps/studio/backend/app/services/predictor.py:27；<br>apps/studio/backend/app/services/skills.py:22；<br>apps/studio/backend/app/services/validator.py:14；<br>apps/studio/tauri/vendor/backend/app/services/skills.py:15；<br>apps/studio/tauri/vendor/backend/app/services/validator.py:14 |

## Manifest

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `AgentNodeAST` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/backend/app/services/skills.py:23 |
| `AgentSkillDef` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/tauri/vendor/backend/app/services/skills.py:16 |
| `GraphManifest` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/backend/app/services/skills.py:23；<br>apps/studio/backend/app/services/validator.py:15 |
| `GraphPhaseRef` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/backend/app/services/skills.py:23 |
| `GraphSkillDef` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/tauri/vendor/backend/app/services/skills.py:16；<br>apps/studio/tauri/vendor/backend/app/services/validator.py:15 |
| `IoInput` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/tauri/vendor/backend/app/services/validator.py:15 |
| `LogicNodeAST` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/backend/app/services/skills.py:23 |
| `PersonaSkillDef` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/tauri/vendor/backend/app/services/skills.py:16 |
| `SkillManifest` | `graph_agent.core.manifest` | 是 | 否 | apps/studio/backend/app/models/skills.py:8；<br>apps/studio/tauri/vendor/backend/app/models/skills.py:7；<br>apps/studio/tauri/vendor/backend/app/services/skills.py:16 |
| `SubgraphNodeAST` | `graph_agent.core.manifest` | 否 | 否 | apps/studio/backend/app/services/skills.py:23 |

## Compiler

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `CompileIssue` | `graph_agent.core.compiler` | 否 | 否 | apps/studio/tauri/vendor/backend/app/services/skills.py:14 |

## Parser

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `parse_skill_file` | `graph_agent.core.parser` | 否 | 否 | apps/studio/tauri/vendor/backend/app/services/skills.py:17；<br>apps/studio/tauri/vendor/backend/app/services/templates.py:8 |

## Serialize / Graph Serializer

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `serialize_graph` | `graph_agent.core.graph_serializer` | 否 | 否 | apps/studio/backend/app/services/skills.py:21 |

## Callbacks / Events / Tracing

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `Callback` | `graph_agent.callbacks` | 是 | 否 | apps/studio/backend/app/services/run_manager.py:21；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:19 |
| `AmbiguityReportEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `CallbackEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/models/runs.py:8；<br>apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/models/runs.py:8；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `CompactionEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `DeadEndPrunedEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `FinishTaskEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `LLMCallEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `NudgeEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `PhaseEndEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `PhaseStartEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `RetryEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `ToolCallEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `ValidationFailEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `WorkingMemoryUpdateEvent` | `graph_agent.callbacks.events` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `to_jsonable_dict` | `graph_agent.callbacks.serialize` | 否 | 否 | apps/studio/backend/app/services/run_manager.py:37；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:35 |
| `TracingCallback` | `graph_agent.callbacks.tracing` | 是 | 否 | apps/studio/backend/app/services/run_manager.py:38；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:36 |

## Exceptions

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `GraphAgentError` | `graph_agent.core.exceptions` | 是 | 否 | apps/studio/backend/app/services/skills.py:20；<br>apps/studio/backend/app/services/validator.py:13 |
| `SkillCompilationError` | `graph_agent.core.exceptions` | 是 | 否 | apps/studio/backend/app/services/skills.py:20 |
| `SkillCompileError` | `graph_agent.core.exceptions` | 否 | 否 | apps/studio/backend/app/core/exceptions.py:13；<br>apps/studio/tauri/vendor/backend/app/core/exceptions.py:13 |
| `SkillLoadError` | `graph_agent.core.exceptions` | 是 | 否 | apps/studio/backend/app/services/skills.py:20 |

## Resolver / Skill Resolver Protocol

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `SkillResolutionError` | `graph_agent.core.skill_resolver_protocol` | 否 | 否 | apps/studio/backend/app/services/skill_resolver.py:8 |

## Config / LLM Config

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `ProviderDef` | `graph_agent.config.llm_config` | 否 | 否 | apps/studio/backend/app/services/copilot.py:36 |
| `ResolvedProvider` | `graph_agent.config.llm_config` | 否 | 否 | apps/studio/backend/app/services/copilot.py:36 |
| `load_config` | `graph_agent.config.llm_config` | 否 | 否 | apps/studio/backend/app/services/copilot.py:36 |

## Predict / `_predict_internal`

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者文件:行 |
|---|---|---|---|---|
| `assemble_phase_record` | `graph_agent.core._predict_internal.exporter` | 否 | 是 | apps/studio/backend/app/services/predictor.py:12；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:11 |
| `GoldenCase` | `graph_agent.core._predict_internal.models` | 否 | 是 | apps/studio/backend/app/services/predictor.py:13；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:12 |
| `PathDiff` | `graph_agent.core._predict_internal.models` | 否 | 是 | apps/studio/backend/app/models/runs.py:9；<br>apps/studio/backend/app/services/predictor.py:13；<br>apps/studio/tauri/vendor/backend/app/models/runs.py:9；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:12 |
| `PhaseRecord` | `graph_agent.core._predict_internal.models` | 否 | 是 | apps/studio/backend/app/models/runs.py:9；<br>apps/studio/backend/app/services/predictor.py:13；<br>apps/studio/tauri/vendor/backend/app/models/runs.py:9；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:12 |
| `PredictResult` | `graph_agent.core._predict_internal.models` | 否 | 是 | apps/studio/backend/app/services/diagnostic_export.py:7；<br>apps/studio/backend/app/services/predictor.py:13；<br>apps/studio/tauri/vendor/backend/app/services/diagnostic_export.py:7；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:12 |
| `compute_diff` | `graph_agent.core._predict_internal.path_diff` | 否 | 是 | apps/studio/backend/app/services/predictor.py:19；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:18 |
| `BaseMockStrategy` | `graph_agent.core._predict_internal.strategy` | 否 | 是 | apps/studio/backend/app/services/predictor.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:19 |
| `GoldenCaseStrategy` | `graph_agent.core._predict_internal.strategy` | 否 | 是 | apps/studio/backend/app/services/predictor.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:19 |
| `HeuristicStubStrategy` | `graph_agent.core._predict_internal.strategy` | 否 | 是 | apps/studio/backend/app/services/predictor.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:19 |
| `MockStrategy` | `graph_agent.core._predict_internal.strategy` | 否 | 是 | apps/studio/backend/app/services/predictor.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:19 |
| `PredictTracingCallback` | `graph_agent.core._predict_internal.tracing` | 否 | 是 | apps/studio/backend/app/services/predictor.py:26；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:25 |

## Summary

### Symbols Used By Production Consumers But Not In The 18-Symbol Contract

Count: 43 symbols.

- `AgentNodeAST`
- `AgentSkillDef`
- `AmbiguityReportEvent`
- `BaseMockStrategy`
- `CallbackEvent`
- `CompactionEvent`
- `CompileIssue`
- `DeadEndPrunedEvent`
- `FinishTaskEvent`
- `GoldenCase`
- `GoldenCaseStrategy`
- `GraphManifest`
- `GraphPhaseRef`
- `GraphSkillDef`
- `HeuristicStubStrategy`
- `IoInput`
- `LLMCallEvent`
- `LogicNodeAST`
- `MockStrategy`
- `NudgeEvent`
- `PathDiff`
- `PersonaSkillDef`
- `PhaseEndEvent`
- `PhaseRecord`
- `PhaseStartEvent`
- `PredictResult`
- `PredictTracingCallback`
- `ProviderDef`
- `ResolvedProvider`
- `RetryEvent`
- `SkillCompileError`
- `SkillLoader`
- `SkillResolutionError`
- `SubgraphNodeAST`
- `ToolCallEvent`
- `ValidationFailEvent`
- `WorkingMemoryUpdateEvent`
- `assemble_phase_record`
- `compute_diff`
- `load_config`
- `parse_skill_file`
- `serialize_graph`
- `to_jsonable_dict`

### `_`-Private Module Dependencies

All `_`-private imports come from `graph_agent.core._predict_internal.*`; count: 11 symbols.

- `assemble_phase_record`
- `GoldenCase`
- `PathDiff`
- `PhaseRecord`
- `PredictResult`
- `compute_diff`
- `BaseMockStrategy`
- `GoldenCaseStrategy`
- `HeuristicStubStrategy`
- `MockStrategy`
- `PredictTracingCallback`

Fact judgment:
- These are substantive Studio Predict V2 dependencies, not incidental imports. `apps/studio/backend/app/services/predictor.py` uses the strategy classes to resolve mock behavior, `PredictTracingCallback` to collect in-process trace phases, `compute_diff` for expected-vs-actual route comparison, and `assemble_phase_record` / model types to construct `PredictResult`.
- `apps/studio/backend/app/models/runs.py` and `apps/studio/backend/app/services/diagnostic_export.py` expose `PhaseRecord`, `PathDiff`, and `PredictResult` through Studio response/diagnostic models, so the model imports are part of current Studio Predict data contracts.
- `apps/studio/tauri/vendor/backend/...` mirrors the same Predict dependency surface for the vendored Tauri backend copy.

### Other Notable Non-18 Deep Imports

- Callback event models are current runtime streaming dependencies: `StudioQueueCallback` constructs specific `*Event` models and serializes them for WebSocket/run history.
- Manifest AST/model imports are current Studio skill-detail, graph-serializer, schema, and validator dependencies.
- `SkillLoader` is a current Studio compile/validation/predict fallback dependency.
- `ProviderDef`, `ResolvedProvider`, and `load_config` are current Studio Copilot provider-resolution dependencies.
- `parse_skill_file` appears only in checked-in Tauri vendored backend code, not in the current `apps/studio/backend` source path scanned above.
- `run_skill` is imported both from stable `graph_agent` and directly from `graph_agent.core.runner`; direct deep imports appear in vendored skill scripts and `scripts/run_e2e_test_enhanced.py`.
