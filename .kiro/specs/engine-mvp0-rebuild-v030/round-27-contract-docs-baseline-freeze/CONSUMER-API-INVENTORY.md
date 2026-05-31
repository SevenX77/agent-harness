# Consumer API Inventory: graph_agent Imports in External Consumers

## Scope

- Scan roots: `apps/`, `scripts/`, `packages/`.
- Included: all non-test Python source files outside `packages/graph-agent/` that import `graph_agent.*`, including checked-in Studio Tauri `vendor/backend`, `vendor/resources`, and `packages/graph-agent-gateway/src`.
- Excluded: `packages/graph-agent/**` engine-internal imports, `**/tests/**`, `test_*.py`, `__pycache__`, `node_modules`, virtualenv/cache directories, `apps/studio/tauri/target/**` generated build output, and vendored Python stdlib under `**/vendor/python/**`.
- Method: positive `rg --no-ignore` matching for `from graph_agent...` / `import graph_agent...`; AST parsing then expanded every imported symbol, including multi-line and local imports.
- Grep trap avoided: this inventory does not use `grep -v graph_agent_gateway`; gateway paths intentionally remain in scope.
- Baseline stable set: `packages/graph-agent/src/graph_agent/__init__.py::__all__` 18 symbols.

Inventory result:
- 25 external consumer files
- 112 imported symbol occurrences
- 57 unique `(symbol, source module)` pairs
- 56 unique imported symbol names
- 47 imported symbols are outside the 18-symbol `__all__` set
- Authoritative contract symbol total: **65** = 18 `__all__` symbols + 47 non-`__all__` external-consumer symbols

新增于本次扩 scope 的符号：

| 符号名 | 来源模块路径 | 消费者 |
|---|---|---|
| `ExecutionError` | `graph_agent.core.exceptions` | `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:8` |
| `LLMFallbackEvent` | `graph_agent.callbacks.events` | `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:8` |
| `LLMClientManager` | `graph_agent.models.llm_client_manager` | `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:241`；<br>`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:229` |
| `PredictGatewayChatModel` | `graph_agent.core._predict_internal.interception` | `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74` |

## Execution / Runner

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `compile_skill` | `graph_agent` | 是 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/skills.py:19；<br>apps/studio/tauri/vendor/backend/app/services/skills.py:13；<br>apps/studio/tauri/vendor/backend/app/services/validator.py:13 |
| `run_skill` | `graph_agent` | 是 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:11；<br>apps/studio/backend/app/services/run_manager.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:10；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:18 |
| `run_skill` | `graph_agent.core.runner` | 是 | 否 | script-live + vendored-resource | apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:14；<br>apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:46；<br>apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:167；<br>scripts/run_e2e_test_enhanced.py:22 |

## Loader

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `CompiledSkill` | `graph_agent.core.loader` | 是 | 否 | studio-live | apps/studio/backend/app/services/skills.py:22 |
| `SkillLoader` | `graph_agent.core.loader` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:27；<br>apps/studio/backend/app/services/skills.py:22；<br>apps/studio/backend/app/services/validator.py:14；<br>apps/studio/tauri/vendor/backend/app/services/skills.py:15；<br>apps/studio/tauri/vendor/backend/app/services/validator.py:14 |

## Manifest

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `AgentNodeAST` | `graph_agent.core.manifest` | 否 | 否 | studio-live | apps/studio/backend/app/services/skills.py:23 |
| `AgentSkillDef` | `graph_agent.core.manifest` | 否 | 否 | vendor-only (待核实是否仍需冻) | apps/studio/tauri/vendor/backend/app/services/skills.py:16 |
| `GraphManifest` | `graph_agent.core.manifest` | 否 | 否 | studio-live | apps/studio/backend/app/services/skills.py:23；<br>apps/studio/backend/app/services/validator.py:15 |
| `GraphPhaseRef` | `graph_agent.core.manifest` | 否 | 否 | studio-live | apps/studio/backend/app/services/skills.py:23 |
| `GraphSkillDef` | `graph_agent.core.manifest` | 否 | 否 | vendor-only (待核实是否仍需冻) | apps/studio/tauri/vendor/backend/app/services/skills.py:16；<br>apps/studio/tauri/vendor/backend/app/services/validator.py:15 |
| `IoInput` | `graph_agent.core.manifest` | 否 | 否 | vendor-only (待核实是否仍需冻) | apps/studio/tauri/vendor/backend/app/services/validator.py:15 |
| `LogicNodeAST` | `graph_agent.core.manifest` | 否 | 否 | studio-live | apps/studio/backend/app/services/skills.py:23 |
| `PersonaSkillDef` | `graph_agent.core.manifest` | 否 | 否 | vendor-only (待核实是否仍需冻) | apps/studio/tauri/vendor/backend/app/services/skills.py:16 |
| `SkillManifest` | `graph_agent.core.manifest` | 是 | 否 | studio-live + vendored-backend | apps/studio/backend/app/models/skills.py:8；<br>apps/studio/tauri/vendor/backend/app/models/skills.py:7；<br>apps/studio/tauri/vendor/backend/app/services/skills.py:16 |
| `SubgraphNodeAST` | `graph_agent.core.manifest` | 否 | 否 | studio-live | apps/studio/backend/app/services/skills.py:23 |

## Compiler

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `CompileIssue` | `graph_agent.core.compiler` | 否 | 否 | vendor-only (待核实是否仍需冻) | apps/studio/tauri/vendor/backend/app/services/skills.py:14 |

## Parser

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `parse_skill_file` | `graph_agent.core.parser` | 否 | 否 | vendor-only (待核实是否仍需冻) | apps/studio/tauri/vendor/backend/app/services/skills.py:17；<br>apps/studio/tauri/vendor/backend/app/services/templates.py:8 |

## Serialize / Graph Serializer

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `serialize_graph` | `graph_agent.core.graph_serializer` | 否 | 否 | studio-live | apps/studio/backend/app/services/skills.py:21 |

## Callbacks / Events / Tracing

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `Callback` | `graph_agent.callbacks` | 是 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:21；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:19 |
| `AmbiguityReportEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `CallbackEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/models/runs.py:8；<br>apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/models/runs.py:8；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `CompactionEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `DeadEndPrunedEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `FinishTaskEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `LLMCallEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `LLMFallbackEvent` | `graph_agent.callbacks.events` | 否 | 否 | gateway-live | packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:8 |
| `NudgeEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `PhaseEndEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `PhaseStartEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `RetryEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `ToolCallEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `ValidationFailEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `WorkingMemoryUpdateEvent` | `graph_agent.callbacks.events` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:22；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:20 |
| `to_jsonable_dict` | `graph_agent.callbacks.serialize` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:37；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:35 |
| `TracingCallback` | `graph_agent.callbacks.tracing` | 是 | 否 | studio-live + vendored-backend | apps/studio/backend/app/services/run_manager.py:38；<br>apps/studio/tauri/vendor/backend/app/services/run_manager.py:36 |

## Exceptions

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `ExecutionError` | `graph_agent.core.exceptions` | 否 | 否 | gateway-live | packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:8 |
| `GraphAgentError` | `graph_agent.core.exceptions` | 是 | 否 | studio-live | apps/studio/backend/app/services/skills.py:20；<br>apps/studio/backend/app/services/validator.py:13 |
| `SkillCompilationError` | `graph_agent.core.exceptions` | 是 | 否 | studio-live | apps/studio/backend/app/services/skills.py:20 |
| `SkillCompileError` | `graph_agent.core.exceptions` | 否 | 否 | studio-live + vendored-backend | apps/studio/backend/app/core/exceptions.py:13；<br>apps/studio/tauri/vendor/backend/app/core/exceptions.py:13 |
| `SkillLoadError` | `graph_agent.core.exceptions` | 是 | 否 | studio-live | apps/studio/backend/app/services/skills.py:20 |

## Resolver / Skill Resolver Protocol

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `SkillResolutionError` | `graph_agent.core.skill_resolver_protocol` | 否 | 否 | studio-live | apps/studio/backend/app/services/skill_resolver.py:8 |

## Config / LLM Config

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `ProviderDef` | `graph_agent.config.llm_config` | 否 | 否 | studio-live | apps/studio/backend/app/services/copilot.py:36 |
| `ResolvedProvider` | `graph_agent.config.llm_config` | 否 | 否 | studio-live | apps/studio/backend/app/services/copilot.py:36 |
| `load_config` | `graph_agent.config.llm_config` | 否 | 否 | studio-live | apps/studio/backend/app/services/copilot.py:36 |

## Models / LLM Client Manager

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `LLMClientManager` | `graph_agent.models.llm_client_manager` | 否 | 否 | gateway-live | packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:241；<br>packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:229 |

## Predict / `_predict_internal`

| 符号名 | 来源模块路径 | 在 `graph_agent.__all__` 18 内? | 来源模块/包 `_` 前缀私有? | 消费者类型 | 消费者文件:行 |
|---|---|---|---|---|---|
| `assemble_phase_record` | `graph_agent.core._predict_internal.exporter` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:12；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:11 |
| `PredictGatewayChatModel` | `graph_agent.core._predict_internal.interception` | 否 | 是 | gateway-live | packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74 |
| `GoldenCase` | `graph_agent.core._predict_internal.models` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:13；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:12 |
| `PathDiff` | `graph_agent.core._predict_internal.models` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/models/runs.py:9；<br>apps/studio/backend/app/services/predictor.py:13；<br>apps/studio/tauri/vendor/backend/app/models/runs.py:9；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:12 |
| `PhaseRecord` | `graph_agent.core._predict_internal.models` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/models/runs.py:9；<br>apps/studio/backend/app/services/predictor.py:13；<br>apps/studio/tauri/vendor/backend/app/models/runs.py:9；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:12 |
| `PredictResult` | `graph_agent.core._predict_internal.models` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/diagnostic_export.py:7；<br>apps/studio/backend/app/services/predictor.py:13；<br>apps/studio/tauri/vendor/backend/app/services/diagnostic_export.py:7；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:12 |
| `compute_diff` | `graph_agent.core._predict_internal.path_diff` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:19；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:18 |
| `BaseMockStrategy` | `graph_agent.core._predict_internal.strategy` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:19 |
| `GoldenCaseStrategy` | `graph_agent.core._predict_internal.strategy` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:19 |
| `HeuristicStubStrategy` | `graph_agent.core._predict_internal.strategy` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:19 |
| `MockStrategy` | `graph_agent.core._predict_internal.strategy` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:20；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:19 |
| `PredictTracingCallback` | `graph_agent.core._predict_internal.tracing` | 否 | 是 | studio-live + vendored-backend | apps/studio/backend/app/services/predictor.py:26；<br>apps/studio/tauri/vendor/backend/app/services/predictor.py:25 |

## Summary

### Authoritative Contract Surface

Authoritative symbol total: **65**.

Calculation:
- 18 symbols from `graph_agent.__all__`
- 47 additional external-consumer symbols not in `__all__`
- Total: 65

The table above has 56 unique imported symbol names because some `__all__` symbols are not directly imported by current external consumers. They remain part of the authoritative surface because the stable top-level API is already declared in `graph_agent.__all__`.

### Symbols Used By External Consumers But Not In The 18-Symbol Contract

Count: 47 symbols.

- `AgentNodeAST`
- `AgentSkillDef` (vendor-only, 待核实是否仍需冻)
- `AmbiguityReportEvent`
- `BaseMockStrategy`
- `CallbackEvent`
- `CompactionEvent`
- `CompileIssue` (vendor-only, 待核实是否仍需冻)
- `DeadEndPrunedEvent`
- `ExecutionError` (gateway-live)
- `FinishTaskEvent`
- `GoldenCase`
- `GoldenCaseStrategy`
- `GraphManifest`
- `GraphPhaseRef`
- `GraphSkillDef` (vendor-only, 待核实是否仍需冻)
- `HeuristicStubStrategy`
- `IoInput` (vendor-only, 待核实是否仍需冻)
- `LLMCallEvent`
- `LLMClientManager` (gateway-live)
- `LLMFallbackEvent` (gateway-live)
- `LogicNodeAST`
- `MockStrategy`
- `NudgeEvent`
- `PathDiff`
- `PersonaSkillDef` (vendor-only, 待核实是否仍需冻)
- `PhaseEndEvent`
- `PhaseRecord`
- `PhaseStartEvent`
- `PredictGatewayChatModel` (gateway-live)
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
- `parse_skill_file` (vendor-only, 待核实是否仍需冻)
- `serialize_graph`
- `to_jsonable_dict`

### Newly Added Since The 61-Symbol Inventory

Count: 4 symbols.

- `ExecutionError`: `graph_agent.core.exceptions`, consumed by `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:8`
- `LLMFallbackEvent`: `graph_agent.callbacks.events`, consumed by `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:8`
- `LLMClientManager`: `graph_agent.models.llm_client_manager`, consumed by `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:241` and `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:229`
- `PredictGatewayChatModel`: `graph_agent.core._predict_internal.interception`, consumed by `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74`

### `_`-Private Module Dependencies

All `_`-private imports come from `graph_agent.core._predict_internal.*`; count: 12 symbols.

- `assemble_phase_record`
- `PredictGatewayChatModel`
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

The 12th `_predict_internal` symbol missed by the earlier inventory is `PredictGatewayChatModel` from `graph_agent.core._predict_internal.interception`, consumed by `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:74`.

Fact judgment:
- The gateway `PredictGatewayChatModel` dependency is substantive. Gateway resolver switches to it when `_graph_agent_predict_mock_strategy` is present, so Predict interception currently crosses package boundaries.
- The Studio Predict dependencies remain substantive: `PredictorService` uses strategy classes, `PredictTracingCallback`, `compute_diff`, `assemble_phase_record`, and Predict model types to build current Predict responses and diagnostics.

### Vendor-Only Symbols

These symbols are consumed only by `apps/studio/tauri/vendor/backend/**` in this scan and are marked `vendor-only (待核实是否仍需冻)` in the table:

- `parse_skill_file`
- `AgentSkillDef`
- `GraphSkillDef`
- `PersonaSkillDef`
- `IoInput`
- `CompileIssue`

Fact judgment:
- They are not imported by current live `apps/studio/backend/**`, `packages/graph-agent-gateway/src/**`, or `scripts/**` in this scan.
- They remain external consumers because the vendored backend copy is checked into the repository, but whether they should be frozen with the same strength as live dependencies needs a separate scope decision.

### Other Notable Non-18 Deep Imports

- Callback event models are current runtime streaming dependencies: `StudioQueueCallback` constructs specific `*Event` models and serializes them for WebSocket/run history.
- `LLMFallbackEvent` is a gateway-live callback schema dependency for provider fallback tracing.
- Manifest AST/model imports are current Studio skill-detail, graph-serializer, schema, and validator dependencies.
- `SkillLoader` is a current Studio compile/validation/predict fallback dependency.
- `LLMClientManager` is a gateway-live dependency used by gateway chat model and resolver default manager paths.
- `ProviderDef`, `ResolvedProvider`, and `load_config` are current Studio Copilot provider-resolution dependencies.
- `run_skill` is imported both from stable `graph_agent` and directly from `graph_agent.core.runner`; direct deep imports appear in vendored skill scripts and `scripts/run_e2e_test_enhanced.py`.

## Reproduction Commands

Positive import search, including gateway and excluding engine-internal `packages/graph-agent/**`:

```bash
rg --no-ignore -l '(^|\s)(from|import)\s+graph_agent\b' apps scripts packages \
  -g '*.py' \
  -g '!**/tests/**' \
  -g '!test_*.py' \
  -g '!**/__pycache__/**' \
  -g '!**/node_modules/**' \
  -g '!**/.venv/**' \
  -g '!**/venv/**' \
  -g '!**/.mypy_cache/**' \
  -g '!**/.pytest_cache/**' \
  -g '!**/target/**' \
  -g '!**/vendor/python/**' \
  -g '!packages/graph-agent/**'
```

Line-level confirmation:

```bash
rg --no-ignore -n '(^|\s)(from|import)\s+graph_agent\b' apps scripts packages \
  -g '*.py' \
  -g '!**/tests/**' \
  -g '!test_*.py' \
  -g '!**/__pycache__/**' \
  -g '!**/node_modules/**' \
  -g '!**/.venv/**' \
  -g '!**/venv/**' \
  -g '!**/.mypy_cache/**' \
  -g '!**/.pytest_cache/**' \
  -g '!**/target/**' \
  -g '!**/vendor/python/**' \
  -g '!packages/graph-agent/**'
```

AST expansion was run over the positive file list above; no negative `grep -v graph_agent_gateway` filter was used.
