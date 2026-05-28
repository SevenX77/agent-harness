from __future__ import annotations

import dataclasses
import importlib
import inspect
import typing

from pydantic import BaseModel


EXPECTED_CONTRACT_SYMBOLS: dict[str, str] = {
    "run_skill": "graph_agent",
    "WorkflowResult": "graph_agent",
    "compile_skill": "graph_agent",
    "CompileResult": "graph_agent",
    "assemble_graph": "graph_agent",
    "CompiledSkill": "graph_agent",
    "CompiledStateGraph": "graph_agent",
    "BlackboardState": "graph_agent",
    "LocalWorkspaceResolver": "graph_agent",
    "SkillManifest": "graph_agent",
    "serialize_skill": "graph_agent",
    "Callback": "graph_agent",
    "LoggingCallback": "graph_agent",
    "MetricsCallback": "graph_agent",
    "TracingCallback": "graph_agent",
    "GraphAgentError": "graph_agent",
    "SkillLoadError": "graph_agent",
    "SkillCompilationError": "graph_agent",
    "AgentNodeAST": "graph_agent.core.manifest",
    "AgentSkillDef": "graph_agent.core.manifest",
    "AmbiguityReportEvent": "graph_agent.callbacks.events",
    "BaseMockStrategy": "graph_agent.core._predict_internal.strategy",
    "CallbackEvent": "graph_agent.callbacks.events",
    "CompactionEvent": "graph_agent.callbacks.events",
    "CompileIssue": "graph_agent.core.compiler",
    "DeadEndPrunedEvent": "graph_agent.callbacks.events",
    "ExecutionError": "graph_agent.core.exceptions",
    "FinishTaskEvent": "graph_agent.callbacks.events",
    "GoldenCase": "graph_agent.core._predict_internal.models",
    "GoldenCaseStrategy": "graph_agent.core._predict_internal.strategy",
    "GraphManifest": "graph_agent.core.manifest",
    "GraphPhaseRef": "graph_agent.core.manifest",
    "GraphSkillDef": "graph_agent.core.manifest",
    "HeuristicStubStrategy": "graph_agent.core._predict_internal.strategy",
    "IoInput": "graph_agent.core.manifest",
    "LLMCallEvent": "graph_agent.callbacks.events",
    "LLMClientManager": "graph_agent.models.llm_client_manager",
    "LLMFallbackEvent": "graph_agent.callbacks.events",
    "LogicNodeAST": "graph_agent.core.manifest",
    "MockStrategy": "graph_agent.core._predict_internal.strategy",
    "NudgeEvent": "graph_agent.callbacks.events",
    "PathDiff": "graph_agent.core._predict_internal.models",
    "PersonaSkillDef": "graph_agent.core.manifest",
    "PhaseEndEvent": "graph_agent.callbacks.events",
    "PhaseRecord": "graph_agent.core._predict_internal.models",
    "PhaseStartEvent": "graph_agent.callbacks.events",
    "PredictGatewayChatModel": "graph_agent.core._predict_internal.interception",
    "PredictResult": "graph_agent.core._predict_internal.models",
    "PredictTracingCallback": "graph_agent.core._predict_internal.tracing",
    "ProviderDef": "graph_agent.config.llm_config",
    "ResolvedProvider": "graph_agent.config.llm_config",
    "RetryEvent": "graph_agent.callbacks.events",
    "SkillCompileError": "graph_agent.core.exceptions",
    "SkillLoader": "graph_agent.core.loader",
    "SkillResolutionError": "graph_agent.core.skill_resolver_protocol",
    "SubgraphNodeAST": "graph_agent.core.manifest",
    "ToolCallEvent": "graph_agent.callbacks.events",
    "ValidationFailEvent": "graph_agent.callbacks.events",
    "WorkingMemoryUpdateEvent": "graph_agent.callbacks.events",
    "assemble_phase_record": "graph_agent.core._predict_internal.exporter",
    "compute_diff": "graph_agent.core._predict_internal.path_diff",
    "load_config": "graph_agent.config.llm_config",
    "parse_skill_file": "graph_agent.core.parser",
    "serialize_graph": "graph_agent.core.graph_serializer",
    "to_jsonable_dict": "graph_agent.callbacks.serialize",
}

EXPECTED_KNOWN_MISSING_VENDOR_ONLY: dict[str, str] = {
    "AgentSkillDef": "graph_agent.core.manifest",
    "GraphSkillDef": "graph_agent.core.manifest",
    "IoInput": "graph_agent.core.manifest",
    "PersonaSkillDef": "graph_agent.core.manifest",
    "parse_skill_file": "graph_agent.core.parser",
}

EXPECTED_VENDOR_ONLY_SYMBOLS = {
    "AgentSkillDef",
    "GraphSkillDef",
    "IoInput",
    "PersonaSkillDef",
    "CompileIssue",
    "parse_skill_file",
}

EXPECTED_PREDICT_INTERNAL_SYMBOLS = {
    "assemble_phase_record",
    "PredictGatewayChatModel",
    "GoldenCase",
    "PathDiff",
    "PhaseRecord",
    "PredictResult",
    "compute_diff",
    "BaseMockStrategy",
    "GoldenCaseStrategy",
    "HeuristicStubStrategy",
    "MockStrategy",
    "PredictTracingCallback",
}

EXPECTED_SIGNATURES: dict[str, tuple[str, tuple[tuple[str, str, bool, str], ...], str]] = {
    "run_skill": (
        "graph_agent",
        (
            ("skill_path", "POSITIONAL_OR_KEYWORD", False, "str | Path"),
            ("mock_llm", "KEYWORD_ONLY", True, "Any"),
            ("trace_dir", "KEYWORD_ONLY", True, "str | Path | None"),
            ("thread_id", "KEYWORD_ONLY", True, "str | None"),
            ("unattended", "KEYWORD_ONLY", True, "bool"),
            ("callbacks", "KEYWORD_ONLY", True, "list[Any] | None"),
            ("artifact_saver", "KEYWORD_ONLY", True, "Any | None"),
            ("initial_context", "KEYWORD_ONLY", True, "dict[str, Any] | None"),
            ("cleanup_checkpoints_on_finish", "KEYWORD_ONLY", True, "bool"),
            ("skill_resolver", "KEYWORD_ONLY", False, "SkillResolverProtocol"),
            ("model_resolver", "KEYWORD_ONLY", True, "Any | None"),
            ("inputs", "VAR_KEYWORD", False, "Any"),
        ),
        "WorkflowResult",
    ),
    "compile_skill": (
        "graph_agent",
        (
            ("root", "POSITIONAL_OR_KEYWORD", False, "str | Path"),
            ("chat_model", "KEYWORD_ONLY", True, "Any"),
            ("cache", "KEYWORD_ONLY", True, "bool"),
            ("skill_resolver", "KEYWORD_ONLY", False, "SkillResolverProtocol"),
        ),
        "CompiledSkill",
    ),
    "assemble_graph": (
        "graph_agent",
        (
            ("compiled", "POSITIONAL_OR_KEYWORD", False, "graph_agent.core.loader.CompiledSkill"),
            ("chat_model", "KEYWORD_ONLY", True, "typing.Any"),
            ("max_patch_attempts", "KEYWORD_ONLY", True, "int"),
            ("callbacks", "KEYWORD_ONLY", True, "list[typing.Any] | None"),
            (
                "skill_resolver",
                "KEYWORD_ONLY",
                False,
                "graph_agent.core.skill_resolver_protocol.SkillResolverProtocol",
            ),
            ("_loading_stack", "KEYWORD_ONLY", True, "tuple[str, ...]"),
            (
                "_compilation_cache",
                "KEYWORD_ONLY",
                True,
                "dict[str, graph_agent.core.loader.CompiledSkill] | None",
            ),
        ),
        "graph_agent.core.graph_assembler.CompiledStateGraph",
    ),
    "serialize_skill": (
        "graph_agent",
        (("manifest", "POSITIONAL_OR_KEYWORD", False, "SkillManifest"),),
        "str",
    ),
    "serialize_graph": (
        "graph_agent.core.graph_serializer",
        (
            ("manifest", "POSITIONAL_OR_KEYWORD", False, "GraphManifest"),
            ("original_md", "POSITIONAL_OR_KEYWORD", True, "str | None"),
        ),
        "str",
    ),
    "assemble_phase_record": (
        "graph_agent.core._predict_internal.exporter",
        (
            ("raw_phase", "POSITIONAL_OR_KEYWORD", False, "dict[str, Any]"),
            ("max_field_chars", "KEYWORD_ONLY", True, "int"),
        ),
        "PhaseRecord",
    ),
    "compute_diff": (
        "graph_agent.core._predict_internal.path_diff",
        (
            ("expected_path", "POSITIONAL_OR_KEYWORD", False, "list[str]"),
            ("actual_path", "POSITIONAL_OR_KEYWORD", False, "list[str]"),
        ),
        "PathDiff",
    ),
    "load_config": (
        "graph_agent.config.llm_config",
        (("config_path", "POSITIONAL_OR_KEYWORD", True, "Path | None"),),
        "RoleConfigData",
    ),
    "PredictGatewayChatModel": (
        "graph_agent.core._predict_internal.interception",
        (
            ("role_name", "POSITIONAL_OR_KEYWORD", False, "str"),
            ("resolved_role", "POSITIONAL_OR_KEYWORD", False, "ResolvedRole"),
            ("mock_strategy", "KEYWORD_ONLY", False, "BaseMockStrategy"),
            ("max_tokens", "KEYWORD_ONLY", True, "int"),
            ("temperature", "KEYWORD_ONLY", True, "float"),
            ("callbacks", "KEYWORD_ONLY", True, "Sequence[Callback]"),
            ("phase_name", "KEYWORD_ONLY", True, "str | None"),
            ("probe_before_call", "KEYWORD_ONLY", True, "bool"),
            ("thinking_enabled", "KEYWORD_ONLY", True, "bool | None"),
            ("name", "KEYWORD_ONLY", True, "str | None"),
            ("cache", "KEYWORD_ONLY", True, "langchain_core.caches.BaseCache | bool | None"),
            ("verbose", "KEYWORD_ONLY", True, "bool"),
            ("tags", "KEYWORD_ONLY", True, "list[str] | None"),
            ("metadata", "KEYWORD_ONLY", True, "dict[str, typing.Any] | None"),
            (
                "custom_get_token_ids",
                "KEYWORD_ONLY",
                True,
                "collections.abc.Callable[[str], list[int]] | None",
            ),
            ("rate_limiter", "KEYWORD_ONLY", True, "langchain_core.rate_limiters.BaseRateLimiter | None"),
            ("disable_streaming", "KEYWORD_ONLY", True, "typing.Union[bool, typing.Literal['tool_calling']]"),
            ("output_version", "KEYWORD_ONLY", True, "str | None"),
            ("profile", "KEYWORD_ONLY", True, "langchain_core.language_models.model_profile.ModelProfile | None"),
            ("event_callbacks", "KEYWORD_ONLY", True, "tuple[typing.Any, ...]"),
            ("bound_tools", "KEYWORD_ONLY", True, "tuple[dict[str, object], ...]"),
            ("tool_choice", "KEYWORD_ONLY", True, "str | None"),
            ("tool_kwargs", "KEYWORD_ONLY", True, "dict[str, object]"),
            ("client_manager", "KEYWORD_ONLY", True, "typing.Any"),
        ),
        "None",
    ),
}

EXPECTED_FIELD_SETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "WorkflowResult": (
        "graph_agent",
        (
            "success",
            "run_id",
            "skill_id",
            "context",
            "metrics",
            "trace_path",
            "error",
            "started_at",
            "finished_at",
            "wall_time_sec",
        ),
    ),
    "CompileResult": ("graph_agent", ("issues",)),
    "CompileIssue": (
        "graph_agent.core.compiler",
        ("rule_id", "severity", "location", "message"),
    ),
    "CompiledSkill": (
        "graph_agent",
        (
            "raw",
            "manifest",
            "nodes",
            "actions",
            "tools",
            "subagents_by_phase",
            "phase_tokens",
        ),
    ),
    "CompiledStateGraph": ("graph_agent", ("graph", "compiled_skill", "phase_ids", "edges")),
    "BlackboardState": ("graph_agent", ("data", "flow", "messages", "run_id")),
    "SkillManifest": (
        "graph_agent",
        ("schema_version", "name", "description", "io", "phases", "metadata"),
    ),
    "GraphManifest": (
        "graph_agent.core.manifest",
        ("schema_version", "name", "description", "io", "phases", "metadata"),
    ),
    "GraphPhaseRef": ("graph_agent.core.manifest", ("id", "src", "depends_on")),
    "AgentNodeAST": (
        "graph_agent.core.manifest",
        (
            "name",
            "raw_blocks",
            "metadata",
            "mode",
            "role",
            "goal",
            "steps",
            "protocols",
            "io",
            "validator",
            "tools",
            "subagents",
            "subgraphs",
            "references",
            "examples",
            "examples_inline",
            "max_iterations",
            "llm_role",
            "system_prompt",
        ),
    ),
    "LogicNodeAST": (
        "graph_agent.core.manifest",
        ("name", "raw_blocks", "metadata", "mode", "io", "actions", "validator"),
    ),
    "SubgraphNodeAST": (
        "graph_agent.core.manifest",
        ("name", "raw_blocks", "metadata", "mode", "target_skill", "io", "validator"),
    ),
    "AmbiguityReportEvent": (
        "graph_agent.callbacks.events",
        (
            "schema_version",
            "timestamp",
            "sub_run_id",
            "group_key",
            "event_type",
            "phase_name",
            "ambiguity_type",
            "question",
            "decision",
        ),
    ),
    "CompactionEvent": (
        "graph_agent.callbacks.events",
        (
            "schema_version",
            "timestamp",
            "sub_run_id",
            "group_key",
            "event_type",
            "phase_name",
            "removed_pairs",
            "removed_summary",
            "content_ref",
        ),
    ),
    "DeadEndPrunedEvent": (
        "graph_agent.callbacks.events",
        ("schema_version", "timestamp", "sub_run_id", "group_key", "event_type", "phase_name", "summary"),
    ),
    "FinishTaskEvent": (
        "graph_agent.callbacks.events",
        ("schema_version", "timestamp", "sub_run_id", "group_key", "event_type", "phase_name", "reasoning", "evidence"),
    ),
    "LLMCallEvent": (
        "graph_agent.callbacks.events",
        (
            "schema_version",
            "timestamp",
            "sub_run_id",
            "group_key",
            "event_type",
            "phase_name",
            "input_tokens",
            "output_tokens",
            "messages",
            "response_data",
        ),
    ),
    "LLMFallbackEvent": (
        "graph_agent.callbacks.events",
        (
            "schema_version",
            "timestamp",
            "sub_run_id",
            "group_key",
            "event_type",
            "phase_name",
            "from_provider",
            "to_provider",
            "reason",
            "code",
            "context",
        ),
    ),
    "NudgeEvent": (
        "graph_agent.callbacks.events",
        (
            "schema_version",
            "timestamp",
            "sub_run_id",
            "group_key",
            "event_type",
            "phase_name",
            "nudge_count",
            "nudge_type",
        ),
    ),
    "PhaseEndEvent": (
        "graph_agent.callbacks.events",
        ("schema_version", "timestamp", "sub_run_id", "group_key", "event_type", "phase_name", "context", "metrics"),
    ),
    "PhaseStartEvent": (
        "graph_agent.callbacks.events",
        ("schema_version", "timestamp", "sub_run_id", "group_key", "event_type", "phase_name", "context"),
    ),
    "RetryEvent": (
        "graph_agent.callbacks.events",
        (
            "schema_version",
            "timestamp",
            "sub_run_id",
            "group_key",
            "event_type",
            "phase_name",
            "target_phase",
            "feedback",
        ),
    ),
    "ToolCallEvent": (
        "graph_agent.callbacks.events",
        (
            "schema_version",
            "timestamp",
            "sub_run_id",
            "group_key",
            "event_type",
            "phase_name",
            "tool_name",
            "args",
            "result",
            "duration_ms",
        ),
    ),
    "ValidationFailEvent": (
        "graph_agent.callbacks.events",
        ("schema_version", "timestamp", "sub_run_id", "group_key", "event_type", "phase_name", "errors", "retry_count"),
    ),
    "WorkingMemoryUpdateEvent": (
        "graph_agent.callbacks.events",
        (
            "schema_version",
            "timestamp",
            "sub_run_id",
            "group_key",
            "event_type",
            "phase_name",
            "content_length",
            "content",
        ),
    ),
    "GoldenCase": (
        "graph_agent.core._predict_internal.models",
        ("inputs", "metadata", "expected_traces"),
    ),
    "PathDiff": (
        "graph_agent.core._predict_internal.models",
        ("expected_path", "actual_path", "missing", "extra", "order_mismatch"),
    ),
    "PhaseRecord": (
        "graph_agent.core._predict_internal.models",
        ("phase_name", "type", "inputs", "outputs", "mocked_source"),
    ),
    "PredictResult": (
        "graph_agent.core._predict_internal.models",
        ("status", "phases", "path_diff"),
    ),
    "PredictGatewayChatModel": (
        "graph_agent.core._predict_internal.interception",
        (
            "name",
            "cache",
            "verbose",
            "callbacks",
            "tags",
            "metadata",
            "custom_get_token_ids",
            "rate_limiter",
            "disable_streaming",
            "output_version",
            "profile",
            "role_name",
            "resolved_role",
            "max_tokens",
            "temperature",
            "phase_name",
            "event_callbacks",
            "probe_before_call",
            "thinking_enabled",
            "bound_tools",
            "tool_choice",
            "tool_kwargs",
            "client_manager",
            "mock_strategy",
        ),
    ),
    "ProviderDef": (
        "graph_agent.config.llm_config",
        (
            "code",
            "name",
            "type",
            "api_key_env",
            "api_key_env_fallback",
            "base_url",
            "llm_base_url",
            "proxy_env",
            "timeout",
            "trust_env",
            "retry_strategy",
        ),
    ),
    "ResolvedProvider": (
        "graph_agent.config.llm_config",
        ("provider_code", "provider_def", "model_name", "model_def", "provider_options"),
    ),
}

EXPECTED_CALLBACK_EVENT_VARIANTS = {
    "AmbiguityReportEvent",
    "CompactionEvent",
    "DeadEndPrunedEvent",
    "FinishTaskEvent",
    "LLMCallEvent",
    "LLMFallbackEvent",
    "NudgeEvent",
    "PhaseEndEvent",
    "PhaseStartEvent",
    "RetryEvent",
    "ToolCallEvent",
    "ValidationFailEvent",
    "WorkingMemoryUpdateEvent",
}


def _load_symbol(module_name: str, symbol_name: str) -> object:
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)


def _annotation_text(annotation: object) -> str:
    if annotation is inspect.Signature.empty:
        return ""
    if isinstance(annotation, str):
        return annotation
    text = str(annotation)
    return text.removeprefix("<class '").removesuffix("'>")


def _signature_contract(obj: object) -> tuple[tuple[tuple[str, str, bool, str], ...], str]:
    signature = inspect.signature(obj)
    params = tuple(
        (
            parameter.name,
            parameter.kind.name,
            parameter.default is not inspect.Parameter.empty,
            _annotation_text(parameter.annotation),
        )
        for parameter in signature.parameters.values()
    )
    return params, _annotation_text(signature.return_annotation)


def _field_names(obj: object) -> tuple[str, ...]:
    if isinstance(obj, type) and issubclass(obj, BaseModel):
        return tuple(obj.model_fields)
    if dataclasses.is_dataclass(obj):
        return tuple(field.name for field in dataclasses.fields(obj))
    annotations = getattr(obj, "__annotations__", None)
    if annotations:
        return tuple(annotations)
    raise AssertionError(f"{obj!r} does not expose a supported field contract")


def _callback_event_variant_names(callback_event: object) -> set[str]:
    args = typing.get_args(callback_event)
    union_arg = args[0]
    return {getattr(arg, "__name__", str(arg)) for arg in typing.get_args(union_arg)}


def test_contract_symbol_count_and_static_sets_are_authoritative() -> None:
    assert len(EXPECTED_CONTRACT_SYMBOLS) == 65
    assert len(EXPECTED_VENDOR_ONLY_SYMBOLS) == 6
    assert len(EXPECTED_PREDICT_INTERNAL_SYMBOLS) == 12
    assert EXPECTED_KNOWN_MISSING_VENDOR_ONLY.keys() < EXPECTED_CONTRACT_SYMBOLS.keys()


def test_importable_contract_symbols_exist_at_canonical_source_modules() -> None:
    expected_importable = EXPECTED_CONTRACT_SYMBOLS.keys() - EXPECTED_KNOWN_MISSING_VENDOR_ONLY.keys()
    for symbol_name in sorted(expected_importable):
        module_name = EXPECTED_CONTRACT_SYMBOLS[symbol_name]
        module = importlib.import_module(module_name)
        assert hasattr(module, symbol_name), f"{symbol_name} missing from {module_name}"


def test_known_missing_vendor_only_symbols_are_locked_as_external_consumer_debt() -> None:
    for symbol_name, module_name in EXPECTED_KNOWN_MISSING_VENDOR_ONLY.items():
        module = importlib.import_module(module_name)
        assert not hasattr(module, symbol_name), (
            f"{symbol_name} changed state in {module_name}; update the contract audit "
            "instead of silently drifting the vendor-only debt."
        )


def test_top_level_all_remains_the_declared_18_symbol_surface() -> None:
    import graph_agent

    expected_all = [
        "run_skill",
        "WorkflowResult",
        "compile_skill",
        "CompileResult",
        "assemble_graph",
        "CompiledSkill",
        "CompiledStateGraph",
        "BlackboardState",
        "LocalWorkspaceResolver",
        "SkillManifest",
        "serialize_skill",
        "Callback",
        "LoggingCallback",
        "MetricsCallback",
        "TracingCallback",
        "GraphAgentError",
        "SkillLoadError",
        "SkillCompilationError",
    ]
    assert graph_agent.__all__ == expected_all


def test_function_and_constructor_signatures_are_stable() -> None:
    for symbol_name, (module_name, expected_params, expected_return) in EXPECTED_SIGNATURES.items():
        obj = _load_symbol(module_name, symbol_name)
        actual_params, actual_return = _signature_contract(obj)
        assert actual_params == expected_params, symbol_name
        assert actual_return == expected_return, symbol_name


def test_model_dataclass_and_typed_dict_fields_are_stable() -> None:
    for symbol_name, (module_name, expected_fields) in EXPECTED_FIELD_SETS.items():
        obj = _load_symbol(module_name, symbol_name)
        assert _field_names(obj) == expected_fields, symbol_name


def test_callback_event_union_contains_consumed_event_models() -> None:
    callback_event = _load_symbol("graph_agent.callbacks.events", "CallbackEvent")
    actual_variants = _callback_event_variant_names(callback_event)
    assert EXPECTED_CALLBACK_EVENT_VARIANTS <= actual_variants


def test_predict_internal_symbols_are_explicit_de_facto_contract_debt() -> None:
    for symbol_name in sorted(EXPECTED_PREDICT_INTERNAL_SYMBOLS):
        module_name = EXPECTED_CONTRACT_SYMBOLS[symbol_name]
        module = importlib.import_module(module_name)
        assert hasattr(module, symbol_name), f"{symbol_name} missing from known-debt module {module_name}"
