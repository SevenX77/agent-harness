# Public API Contract

> **Scope notice**: `docs/engine/skill-spec/` 是 Markdown 格式契约, 跟本 Python API 契约边界**独立**, 不混合. `docs/engine/` 下除 `skill-spec` 以外的其余讲解类子目录属于 Logic-Explained Docs, **不**属于本 PR 不可动摇契约基线.

PR1 originally froze a 65-symbol Python API surface. PR3 converges and refactors this boundary, rightsizing the contract to exactly **49** stable symbols. This was achieved by removing the 12 de facto internal `_predict_internal` debt symbols, clean cutting the legacy callback inheritance classes, and migrating `WorkflowResult` to `RunResult`.

## Coverage Summary

- 49 frozen symbols: `49`
- Top-level `graph_agent.__all__` stable symbols: `19`
- non-`__all__` external dependency symbols: `30`
- `_predict_internal` de facto contract symbols: `0`
- vendor-only symbols: `5`

## Exception Catalog Rightsizing

The stable public exception surface is exactly 5 classes exported from `graph_agent`: `GraphAgentError`, `GraphCompileError`, `GraphExecutionError`, `ModelProviderError`, and `ResourceNotFoundError`.

Internal implementation code may still raise leaf classes such as `SkillLoadError`, `SkillCompilationError`, `SkillCompileError`, `SkillResolutionError`, `ExecutionError`, and gateway-specific leaf errors. Those leaf classes are no longer top-level SDK exports. They are implementation details whose granularity is surfaced across public boundaries through `ErrorPayload.code` and `ERROR_REGISTRY` metadata. External callers should catch the public family and branch on `exc.payload.code` when they need the former leaf-level distinction.

Family mapping summary:

- `GraphCompileError`: compile, parse, schema, contract, template, and input-resource compile failures. Internal leaves include `LoaderError`, `SkillLoadError`, `SkillCompilationError`, `SkillCompileError`, `ValidationError`, and schema/contract/template leaves.
- `GraphExecutionError`: runtime execution, state transformation, tool, persistence, trace, artifact, retry, and fatal execution failures. Internal leaves include `ExecutionError`, `GraphAgentFatalError`, `ToolExecutionError`, `PersistenceError`, and persistence leaf classes.
- `ModelProviderError`: gateway/provider/role/model/fallback failures. `GatewayError` and gateway leaf errors inherit this family.
- `ResourceNotFoundError`: skill/resource/workspace path resolution failures. Engine `SkillResolutionError` is an internal leaf under this family; Studio may raise `ResourceNotFoundError` directly while preserving resolver detail in `ErrorPayload.code`.

## run_skill

- **Source module**: `graph_agent`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:11; apps/studio/backend/app/services/run_manager.py:20; apps/studio/tauri/vendor/backend/app/services/predictor.py:10; apps/studio/tauri/vendor/backend/app/services/run_manager.py:18; apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:14; apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:46; apps/studio/tauri/vendor/resources/skills/_v2_pending/story-deconstruction/script/orchestrator.py:167; scripts/run_e2e_test_enhanced.py:22
- **Contract status**: `@stable`
- **Signature**: `run_skill(skill_path: str | Path, *, workspace_dir: Path, thread_id: str | None = None, unattended: bool = False, event_subscriber: Callable[[CallbackEvent], None] | None = None, artifact_saver: Any | None = None, initial_context: dict[str, Any] | None = None, cleanup_checkpoints_on_finish: bool = True, skill_resolver: SkillResolverProtocol | None = None, model_resolver: Any | None = None, **inputs: Any) -> RunResult`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## predict_skill

- **Source module**: `graph_agent`
- **Consumer files**: apps/studio/backend/app/services/predictor.py
- **Contract status**: `@stable`
- **Signature**: `predict_skill(skill_path: str | Path, *, workspace_dir: Path, thread_id: str | None = None, unattended: bool = True, event_subscriber: Callable[[CallbackEvent], None] | None = None, skill_resolver: SkillResolverProtocol | None = None, model_resolver: Any | None = None, copilot_predict: Callable | None = None, **inputs: Any) -> RunResult`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## RunResult

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; direct external import in Studio predictor/diagnostic services.
- **Contract status**: `@stable`
- **Fields**: `success: bool`, `run_id: str`, `skill_id: str`, `context: dict[str, Any]`, `metrics: WorkflowMetrics`, `trace_path: pathlib.Path | None`, `error: ErrorPayload | None`, `started_at: datetime | None`, `finished_at: datetime | None`, `wall_time_sec: float`, `source: Literal['run', 'predict']`, `phases: list[PhaseRecord] | None`, `path_diff: PathDiff | None`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## PathDiff

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; direct external import in Studio predictor/diagnostic services.
- **Contract status**: `@stable`
- **Fields**: `expected_path: list[str]`, `actual_path: list[str]`, `missing: list[str]`, `extra: list[str]`, `order_mismatch: bool`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Exposes comparison fields between expected and actual execution paths.
- **Drift risk notes**: Renaming, moving, deleting, changing fields breaks this contract.

## PhaseRecord

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; direct external import in Studio predictor/diagnostic services.
- **Contract status**: `@stable`
- **Fields**: `phase_name: str`, `type: Literal['logic', 'llm']`, `inputs: dict[str, Any]`, `outputs: dict[str, Any]`, `mocked_source: Literal['golden_case', 'copilot', 'heuristic_stub', 'manual'] | None`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Exposes audit log fields for a single executed phase.
- **Drift risk notes**: Renaming, moving, deleting, changing fields breaks this contract.

## compile_skill

- **Source module**: `graph_agent`
- **Consumer files**: apps/studio/backend/app/services/skills.py:19; apps/studio/tauri/vendor/backend/app/services/skills.py:13; apps/studio/tauri/vendor/backend/app/services/validator.py:13
- **Contract status**: `@stable`
- **Signature**: `compile_skill(root: str | Path, *, chat_model: Any = None, cache: bool = True, skill_resolver: SkillResolverProtocol | None = None) -> CompiledSkill`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## CompileResult

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; no direct external import occurrence in `CONSUMER-API-INVENTORY.md`.
- **Contract status**: `@stable`
- **Fields**: `issues: list[CompileIssue]`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## assemble_graph

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; no direct external import occurrence in `CONSUMER-API-INVENTORY.md`.
- **Contract status**: `@stable`
- **Signature**: `assemble_graph(compiled: CompiledSkill, *, chat_model: Any = None, model_resolver: Any = None, max_patch_attempts: int = 3, callbacks: list[Any] | None = None, skill_resolver: SkillResolverProtocol | None = None, _loading_stack: tuple[str, ...] = (), _compilation_cache: dict[str, graph_agent.core.loader.CompiledSkill] | None = None) -> CompiledStateGraph`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## CompiledSkill

- **Source module**: `graph_agent`
- **Consumer files**: apps/studio/backend/app/services/skills.py:22
- **Contract status**: `@stable`
- **Fields**: `raw: dict[str, Any]`, `manifest: GraphManifest`, `nodes: list[PhaseDocument]`, `actions: ActionRegistry`, `tools: ToolRegistry`, `subagents_by_phase: dict[str, list[CompiledSubagent]]`, `phase_tokens: dict[str, PhaseTokenInfo]`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## CompiledStateGraph

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; no direct external import occurrence in `CONSUMER-API-INVENTORY.md`.
- **Contract status**: `@stable`
- **Fields**: `graph: Any`, `compiled_skill: CompiledSkill`, `phase_ids: list[str]`, `edges: list[tuple[str, str]]`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## BlackboardState

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; no direct external import occurrence in `CONSUMER-API-INVENTORY.md`.
- **Contract status**: `@stable`
- **Fields**: `data: ForwardRef('Annotated[BlackboardData, blackboard_data_merge]', module='graph_agent.runtime.state')`, `flow: ForwardRef('dict[str, Any]', module='graph_agent.runtime.state')`, `messages: ForwardRef('Annotated[list[AnyMessage], add_messages]', module='graph_agent.runtime.state')`, `run_id: ForwardRef('str | None', module='graph_agent.runtime.state')`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## LocalWorkspaceResolver

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; no direct external import occurrence in `CONSUMER-API-INVENTORY.md`.
- **Contract status**: `@stable`
- **Signature**: `LocalWorkspaceResolver.__init__(self, search_paths: Iterable[str | Path] | None = None) -> None`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## SkillManifest

- **Source module**: `graph_agent`
- **Consumer files**: apps/studio/backend/app/models/skills.py:8; apps/studio/tauri/vendor/backend/app/models/skills.py:7; apps/studio/tauri/vendor/backend/app/services/skills.py:16
- **Contract status**: `@stable`
- **Fields**: `schema_version: Literal['v0.3.0']`, `name: str`, `description: str`, `io: PhaseIOSchema`, `phases: list[str]`, `metadata: dict[str, Any]`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## serialize_skill

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; no direct external import occurrence in `CONSUMER-API-INVENTORY.md`.
- **Contract status**: `@stable`
- **Signature**: `serialize_skill(manifest: SkillManifest) -> str`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## GraphAgentError

- **Source module**: `graph_agent`
- **Consumer files**: apps/studio/backend/app/services/skills.py:20; apps/studio/backend/app/services/validator.py:13
- **Contract status**: `@stable`
- **Signature**: `GraphAgentError.__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## GraphCompileError

- **Source module**: `graph_agent`
- **Consumer files**: apps/studio/backend/app/core/exceptions.py:13; apps/studio/backend/app/services/skills.py:19
- **Contract status**: `@stable`
- **Signature**: `GraphCompileError.__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: External callers catch this family for compile/parse/schema/contract failures and inspect `payload.code` for former leaf-level detail.
- **Postconditions**: Internal compile leaves remain importable from `graph_agent.core.exceptions` and are `isinstance(..., GraphCompileError)`.
- **Drift risk notes**: De-exported leaves must not be re-added to `graph_agent.__all__`; new compile leaves should inherit this family.

## GraphExecutionError

- **Source module**: `graph_agent`
- **Consumer files**: `graph_agent.__all__` stable export; no direct external import occurrence in `CONSUMER-API-INVENTORY.md`.
- **Contract status**: `@stable`
- **Signature**: `GraphExecutionError.__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: External callers catch this family for runtime execution/state/tool/persistence failures and inspect `payload.code`.
- **Postconditions**: Internal execution leaves remain importable from `graph_agent.core.exceptions` and are `isinstance(..., GraphExecutionError)`.
- **Drift risk notes**: New runtime leaves should inherit this family.

## ModelProviderError

- **Source module**: `graph_agent`
- **Consumer files**: packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:8
- **Contract status**: `@stable`
- **Signature**: `ModelProviderError.__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: External callers catch this family for gateway/provider/role/model/fallback failures. Gateway leaves keep their gateway `code` and `context`.
- **Postconditions**: `graph_agent_gateway.exceptions.GatewayError` and its leaves are `isinstance(..., ModelProviderError)`.
- **Drift risk notes**: Gateway errors must not inherit `ExecutionError` as their public family.

## ResourceNotFoundError

- **Source module**: `graph_agent`
- **Consumer files**: apps/studio/backend/app/services/skill_resolver.py:8; apps/studio/backend/app/services/skills.py:19
- **Contract status**: `@stable`
- **Signature**: `ResourceNotFoundError.__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: External callers catch this family for skill/resource/workspace resolution failures and inspect `payload.code`.
- **Postconditions**: Engine `SkillResolutionError` is an internal leaf that is `isinstance(..., ResourceNotFoundError)` and not `isinstance(..., GraphCompileError)`.
- **Drift risk notes**: Resolver stage metadata lives in `ErrorPayload`; do not reintroduce multiple exception-family inheritance.

## SkillLoadError

- **Source module**: `graph_agent.core.exceptions`
- **Consumer files**: internal engine call sites only
- **Contract status**: internal implementation detail; de-exported from `graph_agent.__all__`
- **Signature**: `SkillLoadError.__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: Internal code may still raise this leaf. Public consumers should catch `GraphCompileError` and inspect `payload.code`.
- **Postconditions**: `SkillLoadError` is `isinstance(..., GraphCompileError)`.
- **Drift risk notes**: Do not re-add this leaf to the top-level SDK surface.

## SkillCompilationError

- **Source module**: `graph_agent.core.exceptions`
- **Consumer files**: internal engine call sites only
- **Contract status**: internal implementation detail; de-exported from `graph_agent.__all__`
- **Signature**: `SkillCompilationError.__init__(self, message: str, compile_result: object = None, *, skill_path: Path | None = None, line: int | None = None, field_path: str | None = None, suggestion: str | None = None, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: Internal code may still raise this leaf. Public consumers should catch `GraphCompileError` and inspect `payload.code`.
- **Postconditions**: `SkillCompilationError` is `isinstance(..., GraphCompileError)`.
- **Drift risk notes**: Do not re-add this leaf to the top-level SDK surface.

## AgentNodeAST

- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/backend/app/services/skills.py:23
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `name: str | None`, `raw_blocks: dict[str, str]`, `metadata: dict[str, Any]`, `mode: Literal['agent']`, `role: str`, `goal: str`, `steps: list[graph_agent.core.manifest.AgentStep]`, `protocols: list[graph_agent.core.manifest.AgentProtocol]`, `io: graph_agent.core.manifest.PhaseIOSchema | None`, `validator: bool`, `tools: list[str]`, `subagents: list[graph_agent.core.manifest.SubagentSpec]`, `subgraphs: list[graph_agent.core.manifest.AgentRegistryItem]`, `references: list[graph_agent.core.manifest.ReferenceSpec]`, `examples: list[graph_agent.core.manifest.ExampleSpec]`, `examples_inline: list[graph_agent.core.manifest.AgentExample]`, `max_iterations: int`, `llm_role: str | None`, `context_access: list[Literal['working_memory', 'artifact']]`, `system_prompt: str`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## AgentSkillDef

- **vendor-only / 待核实是否仍需**
- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/tauri/vendor/backend/app/services/skills.py:16
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: No live exported definition named `AgentSkillDef` in `graph_agent.core.manifest` at PR1 baseline.
- **Preconditions**: Vendored consumers must treat this as PR1 baseline debt and must not assume live importability without a coordinated contract update.
- **Postconditions**: The symbol remains documented as vendor-only contract debt; PR1 freezes the observed consumer dependency without changing engine source.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is vendor-only, removing or reviving it requires explicit inventory and contract review.

## BaseMockStrategy

- **De Facto Contract / Known Debt** — PR1 only freezes current behavior; PR2 owns boundary cleanup.
- **Source module**: `graph_agent.core._predict_internal.strategy`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:20; apps/studio/tauri/vendor/backend/app/services/predictor.py:19
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `BaseMockStrategy.__init__(self, *args, **kwargs)`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is `_predict_internal`, PR1 freezes current cross-package use only; PR2 must clean the boundary deliberately.

## CallbackEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/models/runs.py:8; apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/models/runs.py:8; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `Union variants: AgentLoopIterationEvent, AmbiguityLoggedEvent, ArtifactSavedEvent, BlackboardReduceEvent, BuiltinSubagentEnterEvent, BuiltinSubagentExitEvent, BuiltinSubagentFallbackEvent, CompactionEvent, DeadEndPrunedEvent, FinishTaskVerdictEvent, InputDispatchEvent, InputFileInjectedEvent, InterruptedEvent, LLMCallEvent, LLMCallSettingsEvent, LLMDeltaEvent, LLMRouteDecisionEvent, LoopDetectedEvent, NudgeEvent, ParallelMapGroupEndedEvent, ParallelMapGroupStartedEvent, PhaseEndEvent, PhaseStartEvent, PredictChainStartEvent, PromptCapturedEvent, ProtocolViolationEvent, ResumedEvent, RunEndedEvent, RunStartedEvent, RuntimeInputInjectedEvent, ToolCallEvent, ToolCallStartedEvent, ToolErrorHandledEvent, ToolHistoryRepairedEvent, WorkingMemoryUpdateEvent`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## CompactionEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['1.0']`, `timestamp: str`, `sub_run_id: str | None`, `group_key: str | None`, `event_type: Literal['compaction']`, `phase_name: str`, `removed_message_count: int`, `removed_summary: str | None`, `content_ref: str | None`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## CompileIssue

- **vendor-only / 待核实是否仍需**
- **Source module**: `graph_agent.core.compiler`
- **Consumer files**: apps/studio/tauri/vendor/backend/app/services/skills.py:14
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `rule_id: str`, `severity: str`, `location: str`, `message: str`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is vendor-only, removing or reviving it requires explicit inventory and contract review.

## DeadEndPrunedEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['1.0']`, `timestamp: str`, `sub_run_id: str | None`, `group_key: str | None`, `event_type: Literal['dead_end_pruned']`, `phase_name: str`, `summary: str`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## ExecutionError

- **Source module**: `graph_agent.core.exceptions`
- **Consumer files**: internal engine call sites only. Gateway now consumes `ModelProviderError` instead.
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `ExecutionError.__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## GoldenCase

- **De Facto Contract / Known Debt** — PR1 only freezes current behavior; PR2 owns boundary cleanup.
- **Source module**: `graph_agent.core._predict_internal.models`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:13; apps/studio/tauri/vendor/backend/app/services/predictor.py:12
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `inputs: dict[str, Any]`, `metadata: dict[str, Any]`, `expected_traces: dict[str, dict[str, Any]]`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is `_predict_internal`, PR1 freezes current cross-package use only; PR2 must clean the boundary deliberately.

## GoldenCaseStrategy

- **De Facto Contract / Known Debt** — PR1 only freezes current behavior; PR2 owns boundary cleanup.
- **Source module**: `graph_agent.core._predict_internal.strategy`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:20; apps/studio/tauri/vendor/backend/app/services/predictor.py:19
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `GoldenCaseStrategy.__init__(self, golden_case: GoldenCase, *, phase_schemas: dict[str, dict[str, Any]] | None = None) -> None`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is `_predict_internal`, PR1 freezes current cross-package use only; PR2 must clean the boundary deliberately.

## GraphManifest

- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/backend/app/services/skills.py:23; apps/studio/backend/app/services/validator.py:15
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['v0.3.0']`, `name: str`, `description: str`, `io: PhaseIOSchema`, `phases: list[str]`, `metadata: dict[str, Any]`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## GraphPhaseRef

- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/backend/app/services/skills.py:23
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `id: str`, `src: str`, `depends_on: list[str]`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## GraphSkillDef

- **vendor-only / 待核实是否仍需**
- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/tauri/vendor/backend/app/services/skills.py:16; apps/studio/tauri/vendor/backend/app/services/validator.py:15
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: No live exported definition named `GraphSkillDef` in `graph_agent.core.manifest` at PR1 baseline.
- **Preconditions**: Vendored consumers must treat this as PR1 baseline debt and must not assume live importability without a coordinated contract update.
- **Postconditions**: The symbol remains documented as vendor-only contract debt; PR1 freezes the observed consumer dependency without changing engine source.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is vendor-only, removing or reviving it requires explicit inventory and contract review.

## HeuristicStubStrategy

- **De Facto Contract / Known Debt** — PR1 only freezes current behavior; PR2 owns boundary cleanup.
- **Source module**: `graph_agent.core._predict_internal.strategy`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:20; apps/studio/tauri/vendor/backend/app/services/predictor.py:19
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `HeuristicStubStrategy.__init__(self, phase_schemas: dict[str, dict[str, Any]] | None = None) -> None`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is `_predict_internal`, PR1 freezes current cross-package use only; PR2 must clean the boundary deliberately.

## IoInput

- **vendor-only / 待核实是否仍需**
- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/tauri/vendor/backend/app/services/validator.py:15
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: No live exported definition named `IoInput` in `graph_agent.core.manifest` at PR1 baseline.
- **Preconditions**: Vendored consumers must treat this as PR1 baseline debt and must not assume live importability without a coordinated contract update.
- **Postconditions**: The symbol remains documented as vendor-only contract debt; PR1 freezes the observed consumer dependency without changing engine source.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is vendor-only, removing or reviving it requires explicit inventory and contract review.

## LLMCallEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['1.0']`, `timestamp: str`, `sub_run_id: str | None`, `group_key: str | None`, `event_type: Literal['llm_call']`, `phase_name: str`, `input_tokens: int`, `output_tokens: int`, `messages: list[dict[str, Any]] | None`, `response_data: dict[str, Any] | None`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## LogicNodeAST

- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/backend/app/services/skills.py:23
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `name: str | None`, `raw_blocks: dict[str, str]`, `metadata: dict[str, Any]`, `mode: Literal['logic']`, `io: PhaseIOSchema`, `actions: list[str]`, `validator: bool`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## MockStrategy

- **De Facto Contract / Known Debt** — PR1 only freezes current behavior; PR2 owns boundary cleanup.
- **Source module**: `graph_agent.core._predict_internal.strategy`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:20; apps/studio/tauri/vendor/backend/app/services/predictor.py:19
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `MockStrategy.__init__(self, *args, **kwargs)`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is `_predict_internal`, PR1 freezes current cross-package use only; PR2 must clean the boundary deliberately.

## NudgeEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['1.0']`, `timestamp: str`, `sub_run_id: str | None`, `group_key: str | None`, `event_type: Literal['nudge']`, `phase_name: str`, `nudge_count: int`, `nudge_type: str`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## PersonaSkillDef

- **vendor-only / 待核实是否仍需**
- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/tauri/vendor/backend/app/services/skills.py:16
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: No live exported definition named `PersonaSkillDef` in `graph_agent.core.manifest` at PR1 baseline.
- **Preconditions**: Vendored consumers must treat this as PR1 baseline debt and must not assume live importability without a coordinated contract update.
- **Postconditions**: The symbol remains documented as vendor-only contract debt; PR1 freezes the observed consumer dependency without changing engine source.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is vendor-only, removing or reviving it requires explicit inventory and contract review.

## PhaseEndEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['1.0']`, `timestamp: str`, `sub_run_id: str | None`, `group_key: str | None`, `event_type: Literal['phase_end']`, `phase_name: str`, `context: dict[str, Any]`, `metrics: dict[str, Any]`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## PhaseStartEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['1.0']`, `timestamp: str`, `sub_run_id: str | None`, `group_key: str | None`, `event_type: Literal['phase_start']`, `phase_name: str`, `context: dict[str, Any]`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## SkillCompileError

- **Source module**: `graph_agent.core.exceptions`
- **Consumer files**: internal engine call sites only. Studio catches `GraphCompileError`.
- **Contract status**: internal implementation detail; non-`__all__`
- **Signature**: `SkillCompileError.__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None) -> None`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## SkillLoader

- **Source module**: `graph_agent.core.loader`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:27; apps/studio/backend/app/services/skills.py:22; apps/studio/backend/app/services/validator.py:14; apps/studio/tauri/vendor/backend/app/services/skills.py:15; apps/studio/tauri/vendor/backend/app/services/validator.py:14
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `SkillLoader.__init__(self, *args: Any, *, validate_context_writes: bool = True, **kwargs: Any) -> None`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## SkillResolutionError

- **Source module**: `graph_agent.core.skill_resolver_protocol`
- **Consumer files**: internal engine resolver paths. Studio raises `ResourceNotFoundError` directly.
- **Contract status**: internal implementation detail; non-`__all__`
- **Signature**: `SkillResolutionError.__init__(self, skill_id: str, reason: str, *, code: str = '[F-v3-skill-not-registered]') -> None`
- **Preconditions**: Internal engine resolver helpers may still raise this leaf. Public consumers should catch `ResourceNotFoundError`.
- **Postconditions**: `SkillResolutionError` is `isinstance(..., ResourceNotFoundError)` and not a `GraphCompileError`; compile-stage meaning is carried by `payload.stage` and `payload.code`.
- **Drift risk notes**: Do not reintroduce multiple inheritance across exception families.

## SubgraphNodeAST

- **Source module**: `graph_agent.core.manifest`
- **Consumer files**: apps/studio/backend/app/services/skills.py:23
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `name: str | None`, `raw_blocks: dict[str, str]`, `metadata: dict[str, Any]`, `mode: Literal['subgraph']`, `target_skill: str`, `io: PhaseIOSchema`, `validator: bool`
- **Preconditions**: Consumers must use the frozen field names, field types, constructor shape, and source module listed here.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## ToolCallEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['1.0']`, `timestamp: str`, `sub_run_id: str | None`, `group_key: str | None`, `event_type: Literal['tool_call']`, `phase_name: str`, `tool_name: str`, `args: dict[str, Any]`, `result: str`, `duration_ms: float | None`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## WorkingMemoryUpdateEvent

- **Source module**: `graph_agent.callbacks.events`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:22; apps/studio/tauri/vendor/backend/app/services/run_manager.py:20
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: `schema_version: Literal['1.0']`, `timestamp: str`, `sub_run_id: str | None`, `group_key: str | None`, `event_type: Literal['working_memory_update']`, `phase_name: str`, `content_length: int`, `content: str | None`
- **Preconditions**: Consumers must construct, validate, or serialize payloads using the frozen field names, field types, and event discriminator values.
- **Postconditions**: Instances and serialized payloads expose the frozen fields so Studio, gateway, scripts, and vendored consumers continue to deserialize them.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## assemble_phase_record

- **De Facto Contract / Known Debt** — PR1 only freezes current behavior; PR2 owns boundary cleanup.
- **Source module**: `graph_agent.core._predict_internal.exporter`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:12; apps/studio/tauri/vendor/backend/app/services/predictor.py:11
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `assemble_phase_record(raw_phase: dict[str, Any], *, max_field_chars: int = 4096) -> PhaseRecord`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is `_predict_internal`, PR1 freezes current cross-package use only; PR2 must clean the boundary deliberately.

## compute_diff

- **De Facto Contract / Known Debt** — PR1 only freezes current behavior; PR2 owns boundary cleanup.
- **Source module**: `graph_agent.core._predict_internal.path_diff`
- **Consumer files**: apps/studio/backend/app/services/predictor.py:19; apps/studio/tauri/vendor/backend/app/services/predictor.py:18
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `compute_diff(expected_path: list[str], actual_path: list[str]) -> PathDiff`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is `_predict_internal`, PR1 freezes current cross-package use only; PR2 must clean the boundary deliberately.

## parse_skill_file

- **vendor-only / 待核实是否仍需**
- **Source module**: `graph_agent.core.parser`
- **Consumer files**: apps/studio/tauri/vendor/backend/app/services/skills.py:17; apps/studio/tauri/vendor/backend/app/services/templates.py:8
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Fields**: No live exported definition named `parse_skill_file` in `graph_agent.core.parser` at PR1 baseline.
- **Preconditions**: Vendored consumers must treat this as PR1 baseline debt and must not assume live importability without a coordinated contract update.
- **Postconditions**: The symbol remains documented as vendor-only contract debt; PR1 freezes the observed consumer dependency without changing engine source.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract. Because this is vendor-only, removing or reviving it requires explicit inventory and contract review.

## serialize_graph

- **Source module**: `graph_agent.core.graph_serializer`
- **Consumer files**: apps/studio/backend/app/services/skills.py:21
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `serialize_graph(manifest: GraphManifest, original_md: str | None = None) -> str`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.

## to_jsonable_dict

- **Source module**: `graph_agent.callbacks.serialize`
- **Consumer files**: apps/studio/backend/app/services/run_manager.py:37; apps/studio/tauri/vendor/backend/app/services/run_manager.py:35
- **Contract status**: `@stable`; non-`__all__` external dep, locked at PR1 baseline
- **Signature**: `to_jsonable_dict(data: Any, *, _depth: int = 0) -> Any`
- **Preconditions**: Callers must provide the required parameters shown in the frozen signature and preserve keyword/default semantics.
- **Postconditions**: Successful calls return the annotated result or perform the documented serialization/loading side effect without changing parameter semantics.
- **Drift risk notes**: Renaming, moving, deleting, changing required parameters, defaults, field names, field types, return annotations, or inheritance breaks this contract.
