from __future__ import annotations

import dataclasses
import importlib
import inspect
import re
import typing
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

EXEMPTIONS_PATH = Path(__file__).with_name("contract-exemptions.yaml")

EXPECTED_CONTRACT_SYMBOLS: dict[str, str] = {
    "run_skill": "graph_agent",
    "predict_skill": "graph_agent",
    "resume_skill": "graph_agent",
    "evaluate_golden_baseline": "graph_agent",
    "RunResult": "graph_agent",
    "compile_artifact": "graph_agent",
    "run_artifact": "graph_agent",
    "predict_artifact": "graph_agent",
    "compile_skill": "graph_agent",
    "CompileResult": "graph_agent",
    "assemble_graph": "graph_agent",
    "CompiledSkill": "graph_agent",
    "CompiledStateGraph": "graph_agent",
    "BlackboardState": "graph_agent",
    "LocalWorkspaceResolver": "graph_agent",
    "SkillManifest": "graph_agent",
    "serialize_skill": "graph_agent",
    "GraphAgentError": "graph_agent",
    "GraphCompileError": "graph_agent",
    "GraphExecutionError": "graph_agent",
    "ModelProviderError": "graph_agent",
    "ResourceNotFoundError": "graph_agent",
    "AgentNodeAST": "graph_agent.core.manifest",
    "AgentSkillDef": "graph_agent.core.manifest",
    "CallbackEvent": "graph_agent.callbacks.events",
    "CompileIssue": "graph_agent.core.compiler",
    "ExecutionError": "graph_agent.core.exceptions",
    "GraphManifest": "graph_agent.core.manifest",
    "GraphPhaseRef": "graph_agent.core.manifest",
    "GraphSkillDef": "graph_agent.core.manifest",
    "IoInput": "graph_agent.core.manifest",
    "LogicNodeAST": "graph_agent.core.manifest",
    "PathDiff": "graph_agent",
    "PersonaSkillDef": "graph_agent.core.manifest",
    "PhaseRecord": "graph_agent",
    "SkillCompileError": "graph_agent.core.exceptions",
    "SkillLoadError": "graph_agent.core.exceptions",
    "SkillCompilationError": "graph_agent.core.exceptions",
    "SkillLoader": "graph_agent.core.loader",
    "SkillResolutionError": "graph_agent.core.skill_resolver_protocol",
    "SubgraphNodeAST": "graph_agent.core.manifest",
}

EXPECTED_KNOWN_MISSING_VENDOR_ONLY: dict[str, str] = {
    "AgentSkillDef": "graph_agent.core.manifest",
    "GraphSkillDef": "graph_agent.core.manifest",
    "IoInput": "graph_agent.core.manifest",
    "PersonaSkillDef": "graph_agent.core.manifest",
}

EXPECTED_VENDOR_ONLY_SYMBOLS = {
    "AgentSkillDef",
    "GraphSkillDef",
    "IoInput",
    "PersonaSkillDef",
    "CompileIssue",
}


EXPECTED_ALL_18 = tuple(
    symbol for symbol, module_name in EXPECTED_CONTRACT_SYMBOLS.items() if module_name == "graph_agent"
)

EXPECTED_SIGNATURES: dict[str, tuple[str, tuple[tuple[str, str, str, str], ...], str]] = {'PredictGatewayChatModel': ('graph_agent.core._predict_internal.interception',
                             (('role_name', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                              ('resolved_role',
                               'POSITIONAL_OR_KEYWORD',
                               '<required>',
                               'Any'),
                              ('mock_strategy', 'KEYWORD_ONLY', '<required>', 'BaseMockStrategy'),
                              ('max_tokens', 'KEYWORD_ONLY', '4096', 'int'),
                              ('temperature', 'KEYWORD_ONLY', '0.7', 'float'),
                              ('callbacks', 'KEYWORD_ONLY', '()', 'Sequence[Callback]'),
                              ('phase_name', 'KEYWORD_ONLY', 'None', 'str | None'),
                              ('probe_before_call', 'KEYWORD_ONLY', 'True', 'bool'),
                              ('thinking_enabled', 'KEYWORD_ONLY', 'None', 'bool | None'),
                              ('kwargs', 'VAR_KEYWORD', '<required>', 'Any')),
                             'None'),
 'assemble_graph': ('graph_agent',
                    (('compiled', 'POSITIONAL_OR_KEYWORD', '<required>', 'CompiledSkill'),
                     ('chat_model', 'KEYWORD_ONLY', 'None', 'Any'),
                     ('model_resolver', 'KEYWORD_ONLY', 'None', 'Any'),
                     ('max_patch_attempts', 'KEYWORD_ONLY', '3', 'int'),
                     ('callbacks', 'KEYWORD_ONLY', 'None', 'list[Any] | None'),
                     ('skill_resolver', 'KEYWORD_ONLY', '<required>', 'SkillResolverProtocol'),
                     ('llm_provider',
                      'KEYWORD_ONLY',
                      'None',
                      'graph_agent.core.llm_provider.LLMProvider | None'),
                     ('checkpointer', 'KEYWORD_ONLY', 'None', 'Any'),
                     ('predict_context', 'KEYWORD_ONLY', 'None', 'Any'),
                     ('_loading_stack', 'KEYWORD_ONLY', '()', 'tuple[str, ...]'),
                     ('_compilation_cache',
                      'KEYWORD_ONLY',
                      'None',
                      'dict[str, graph_agent.core.loader.CompiledSkill] | None')),
                    'CompiledStateGraph'),
 'assemble_phase_record': ('graph_agent.core._predict_internal.exporter',
                           (('raw_phase', 'POSITIONAL_OR_KEYWORD', '<required>', 'dict[str, Any]'),
                            ('max_field_chars', 'KEYWORD_ONLY', '4096', 'int')),
                           'PhaseRecord'),
 'compile_skill': ('graph_agent',
                   (('root', 'POSITIONAL_OR_KEYWORD', '<required>', 'str | Path'),
                    ('chat_model', 'KEYWORD_ONLY', 'None', 'Any'),
                    ('cache', 'KEYWORD_ONLY', 'True', 'bool'),
                    ('skill_resolver', 'KEYWORD_ONLY', '<required>', 'SkillResolverProtocol')),
                   'CompiledSkill'),
 'compute_diff': ('graph_agent.core._predict_internal.path_diff',
                  (('expected_path', 'POSITIONAL_OR_KEYWORD', '<required>', 'list[str]'),
                   ('actual_path', 'POSITIONAL_OR_KEYWORD', '<required>', 'list[str]')),
                  'PathDiff'),
  'evaluate_golden_baseline': ('graph_agent',
                               (('skill_path',
                                 'POSITIONAL_OR_KEYWORD',
                                 '<required>',
                                 'str | Path'),
                                ('workspace_dir', 'KEYWORD_ONLY', '<required>', 'Path'),
                                ('baseline_id', 'KEYWORD_ONLY', '<required>', 'str'),
                                ('skill_resolver',
                                 'KEYWORD_ONLY',
                                 '<required>',
                                 'SkillResolverProtocol'),
                                ('model_resolver', 'KEYWORD_ONLY', 'None', 'Any | None')),
                               'dict[str, Any]'),
  'predict_skill': ('graph_agent',
                    (('skill_path', 'POSITIONAL_OR_KEYWORD', '<required>', 'str | Path'),
                     ('workspace_dir', 'KEYWORD_ONLY', '<required>', 'Path'),
                     ('thread_id', 'KEYWORD_ONLY', 'None', 'str | None'),
                     ('unattended', 'KEYWORD_ONLY', 'True', 'bool'),
                     ('event_subscriber', 'KEYWORD_ONLY', 'None', 'Callable[[CallbackEvent], None] | None'),
                     ('skill_resolver', 'KEYWORD_ONLY', '<required>', 'SkillResolverProtocol'),
                     ('model_resolver', 'KEYWORD_ONLY', 'None', 'Any | None'),
                     ('llm_provider', 'KEYWORD_ONLY', 'None', 'LLMProvider | None'),
                     ('copilot_predict', 'KEYWORD_ONLY', 'None', 'Callable[..., Any] | None'),
                     ('inputs', 'VAR_KEYWORD', '<required>', 'Any')),
                    'RunResult'),
  'resume_skill': ('graph_agent',
                   (('skill_path', 'POSITIONAL_OR_KEYWORD', '<required>', 'str | Path'),
                    ('workspace_dir', 'KEYWORD_ONLY', '<required>', 'Path'),
                    ('run_id', 'KEYWORD_ONLY', '<required>', 'str'),
                    ('from_phase', 'KEYWORD_ONLY', 'None', 'str | None'),
                    ('checkpoint_id', 'KEYWORD_ONLY', 'None', 'str | None'),
                    ('checkpoint_ns', 'KEYWORD_ONLY', 'None', 'str | None'),
                    ('resume_from_node_id', 'KEYWORD_ONLY', 'None', 'str | None'),
                    ('resume_to_node_id', 'KEYWORD_ONLY', 'None', 'str | None'),
                    ('checkpointer', 'KEYWORD_ONLY', 'None', 'Any | None'),
                    ('context_overrides',
                     'KEYWORD_ONLY',
                     'None',
                     'dict[str, Any] | None'),
                    ('human_response',
                     'KEYWORD_ONLY',
                     'None',
                     'dict[str, Any] | None'),
                    ('skill_resolver',
                     'KEYWORD_ONLY',
                     '<required>',
                     'SkillResolverProtocol'),
                    ('model_resolver', 'KEYWORD_ONLY', 'None', 'Any | None'),
                    ('llm_provider', 'KEYWORD_ONLY', 'None', 'LLMProvider | None'),
                    ('event_subscriber',
                     'KEYWORD_ONLY',
                     'None',
                     'Callable[[CallbackEvent], None] | None')),
                   'RunResult'),
  'run_skill': ('graph_agent',
                (('skill_path', 'POSITIONAL_OR_KEYWORD', '<required>', 'str | Path'),
                 ('workspace_dir', 'KEYWORD_ONLY', '<required>', 'Path'),
                 ('thread_id', 'KEYWORD_ONLY', 'None', 'str | None'),
                 ('unattended', 'KEYWORD_ONLY', 'False', 'bool'),
                 ('event_subscriber', 'KEYWORD_ONLY', 'None', 'Callable[[CallbackEvent], None] | None'),
                 ('artifact_saver', 'KEYWORD_ONLY', 'None', 'Any | None'),
                 ('initial_context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None'),
                 ('cleanup_checkpoints_on_finish', 'KEYWORD_ONLY', 'True', 'bool'),
                 ('skill_resolver', 'KEYWORD_ONLY', '<required>', 'SkillResolverProtocol'),
                 ('model_resolver', 'KEYWORD_ONLY', 'None', 'Any | None'),
                 ('llm_provider', 'KEYWORD_ONLY', 'None', 'LLMProvider | None'),
                 ('inputs', 'VAR_KEYWORD', '<required>', 'Any')),
                'RunResult'),
 'serialize_graph': ('graph_agent.core.graph_serializer',
                     (('manifest', 'POSITIONAL_OR_KEYWORD', '<required>', 'GraphManifest'),
                      ('original_md', 'POSITIONAL_OR_KEYWORD', 'None', 'str | None')),
                     'str'),
 'serialize_skill': ('graph_agent',
                     (('manifest', 'POSITIONAL_OR_KEYWORD', '<required>', 'SkillManifest'),),
                     'str')}

EXPECTED_CONSTRUCTOR_SIGNATURES: dict[str, tuple[str, tuple[tuple[str, str, str, str], ...], str]] = {'ExecutionError': ('graph_agent.core.exceptions',
                    (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                     ('message', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                     ('payload', 'KEYWORD_ONLY', 'None', 'ErrorPayload | None'),
                     ('context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None')),
                    'None'),
 'GraphAgentError': ('graph_agent',
                     (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                      ('message', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                      ('payload', 'KEYWORD_ONLY', 'None', 'ErrorPayload | None'),
                      ('context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None')),
                     'None'),
 'LocalWorkspaceResolver': ('graph_agent',
                            (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                             ('search_paths',
                              'POSITIONAL_OR_KEYWORD',
                              'None',
                              'Iterable[str | Path] | None')),
                            'None'),
 'SkillCompilationError': ('graph_agent.core.exceptions',
                           (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                            ('message', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                            ('compile_result', 'POSITIONAL_OR_KEYWORD', 'None', 'object'),
                            ('skill_path', 'KEYWORD_ONLY', 'None', 'Path | None'),
                            ('line', 'KEYWORD_ONLY', 'None', 'int | None'),
                            ('field_path', 'KEYWORD_ONLY', 'None', 'str | None'),
                            ('suggestion', 'KEYWORD_ONLY', 'None', 'str | None'),
                            ('payload', 'KEYWORD_ONLY', 'None', 'ErrorPayload | None'),
                            ('context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None')),
                           'None'),
 'SkillCompileError': ('graph_agent.core.exceptions',
                       (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                        ('message', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                        ('payload', 'KEYWORD_ONLY', 'None', 'ErrorPayload | None'),
                        ('context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None')),
                       'None'),
 'SkillLoadError': ('graph_agent.core.exceptions',
                    (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                     ('message', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                     ('payload', 'KEYWORD_ONLY', 'None', 'ErrorPayload | None'),
                     ('context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None')),
                    'None'),
 'SkillLoader': ('graph_agent.core.loader',
                 (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                  ('args', 'VAR_POSITIONAL', '<required>', 'Any'),
                  ('validate_context_writes', 'KEYWORD_ONLY', 'True', 'bool'),
                  ('kwargs', 'VAR_KEYWORD', '<required>', 'Any')),
                 'None'),
 'SkillResolutionError': ('graph_agent.core.skill_resolver_protocol',
                          (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                           ('skill_id', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                           ('reason', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                           ('code', 'KEYWORD_ONLY', "'[F-v3-skill-not-registered]'", 'str')),
                          'None')}

EXPECTED_FIELD_CONTRACTS: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {'AgentNodeAST': ('graph_agent.core.manifest',
                  (('name', 'str | None'),
                   ('raw_blocks', 'dict[str, str]'),
                   ('metadata', 'dict[str, Any]'),
                   ('allow_sequential_overwrite', 'list[str]'),
                   ('batch', 'graph_agent.core.manifest.BatchSpec | None'),
                   ('iterate', 'graph_agent.core.manifest.IterateSpec | None'),
                   ('mode', "Literal['agent']"),
                   ('role', 'str'),
                   ('goal', 'str'),
                   ('steps', 'list[graph_agent.core.manifest.AgentStep]'),
                   ('protocols', 'list[graph_agent.core.manifest.AgentProtocol]'),
                   ('io', 'graph_agent.core.manifest.PhaseIOSchema | None'),
                   ('validator', 'bool'),
                   ('tools', 'list[str]'),
                   ('subagents', 'list[graph_agent.core.manifest.SubagentSpec]'),
                   ('subgraphs', 'list[graph_agent.core.manifest.AgentRegistryItem]'),
                   ('references', 'list[graph_agent.core.manifest.ReferenceSpec]'),
                   ('examples', 'list[graph_agent.core.manifest.ExampleSpec]'),
                   ('examples_inline', 'list[graph_agent.core.manifest.AgentExample]'),
                   ('max_iterations', 'int'),
                   ('llm_role', 'str | None'),
                   ('system_prompt', 'str'))),
 'BlackboardState': ('graph_agent',
                     (('data',
                       "ForwardRef('Annotated[BlackboardData, blackboard_data_merge]', "
                       "module='graph_agent.runtime.state')"),
                      ('flow', "ForwardRef('dict[str, Any]', module='graph_agent.runtime.state')"),
                      ('messages',
                       "ForwardRef('Annotated[list[AnyMessage], add_messages]', "
                       "module='graph_agent.runtime.state')"),
                      ('run_id', "ForwardRef('str | None', module='graph_agent.runtime.state')"))),
 'CompileIssue': ('graph_agent.core.compiler',
                  (('rule_id', 'str'),
                   ('severity', 'str'),
                   ('location', 'str'),
                   ('message', 'str'))),
 'CompileResult': ('graph_agent', (('issues', 'list[CompileIssue]'),)),
 'CompiledSkill': ('graph_agent',
                   (('raw', 'dict[str, Any]'),
                    ('manifest', 'GraphManifest'),
                    ('nodes', 'list[PhaseDocument]'),
                    ('actions', 'ActionRegistry'),
                    ('tools', 'ToolRegistry'),
                    ('subagents_by_phase', 'dict[str, list[CompiledSubagent]]'),
                    ('phase_tokens', 'dict[str, PhaseTokenInfo]'))),
 'CompiledStateGraph': ('graph_agent',
                        (('graph', 'Any'),
                         ('compiled_skill', 'CompiledSkill'),
                         ('phase_ids', 'list[str]'),
                         ('edges', 'list[tuple[str, str]]'))),
 'GoldenCase': ('graph_agent.core._predict_internal.models',
                (('inputs', 'dict[str, Any]'),
                 ('metadata', 'dict[str, Any]'),
                 ('expected_traces', 'dict[str, dict[str, Any]]'))),
 'GraphManifest': ('graph_agent.core.manifest',
                   (('schema_version', "Literal['v0.3.0']"),
                    ('name', 'str'),
                    ('description', 'str'),
                    ('io', 'PhaseIOSchema'),
                    ('phases', 'list[str]'),
                    ('metadata', 'dict[str, Any]'),
                    ('iterate', 'graph_agent.core.manifest.IterateSpec | None'))),
 'GraphPhaseRef': ('graph_agent.core.manifest',
                   (('id', 'str'), ('src', 'str'), ('depends_on', 'list[str]'))),
 'LogicNodeAST': ('graph_agent.core.manifest',
                  (('name', 'str | None'),
                   ('raw_blocks', 'dict[str, str]'),
                   ('metadata', 'dict[str, Any]'),
                   ('allow_sequential_overwrite', 'list[str]'),
                   ('batch', 'graph_agent.core.manifest.BatchSpec | None'),
                   ('iterate', 'graph_agent.core.manifest.IterateSpec | None'),
                   ('mode', "Literal['logic']"),
                   ('io', 'PhaseIOSchema'),
                   ('actions', 'list[str]'),
                   ('validator', 'bool'))),
 'PathDiff': ('graph_agent.core._predict_internal.models',
              (('expected_path', 'list[str]'),
               ('actual_path', 'list[str]'),
               ('missing', 'list[str]'),
               ('extra', 'list[str]'),
               ('order_mismatch', 'bool'))),
 'PhaseRecord': ('graph_agent',
                 (('phase_name', 'str'),
                  ('type', "Literal['logic', 'llm']"),
                  ('inputs', 'dict[str, Any]'),
                  ('outputs', 'dict[str, Any]'),
                  ('mocked_source',
                   "Optional[Literal['golden_case', 'copilot', 'heuristic_stub', 'manual']]"))),

 'SkillManifest': ('graph_agent',
                   (('schema_version', "Literal['v0.3.0']"),
                    ('name', 'str'),
                    ('description', 'str'),
                    ('io', 'PhaseIOSchema'),
                    ('phases', 'list[str]'),
                    ('metadata', 'dict[str, Any]'),
                    ('iterate', 'graph_agent.core.manifest.IterateSpec | None'))),
 'SubgraphNodeAST': ('graph_agent.core.manifest',
                     (('name', 'str | None'),
                      ('raw_blocks', 'dict[str, str]'),
                      ('metadata', 'dict[str, Any]'),
                      ('allow_sequential_overwrite', 'list[str]'),
                      ('batch', 'graph_agent.core.manifest.BatchSpec | None'),
                      ('iterate', 'graph_agent.core.manifest.IterateSpec | None'),
                      ('mode', "Literal['subgraph']"),
                      ('target_skill', 'str'),
                      ('io', 'PhaseIOSchema'),
                      ('validator', 'bool'))),
 'RunResult': ('graph_agent',
               (('success', 'bool'),
                ('run_id', 'str'),
                ('skill_id', 'str'),
                ('context', 'dict[str, Any]'),
                ('metrics', 'WorkflowMetrics'),
                ('trace_path', 'Path | None'),
                ('error', 'graph_agent.core.exceptions.ErrorPayload | None'),
                ('started_at', 'datetime.datetime | None'),
                ('finished_at', 'datetime.datetime | None'),
                ('wall_time_sec', 'float'),
                ('source', "Literal['run', 'predict']"),
                ('artifact_ref', 'dict[str, Any] | None'),
                ('source_map_ref', 'str | None'),
                ('execution_fingerprint', 'str | None'),
                ('phases', 'list[graph_agent.core.result.PhaseRecord] | None'),
                ('path_diff', 'graph_agent.core.result.PathDiff | None'),
                ('diagnostics', 'list[graph_agent.core.exceptions.ErrorPayload]'),
                ('diagnostics_limit', 'int'),
                ('diagnostics_truncated', 'bool'),
                ('diagnostic_counts', 'dict[str, Any]')))}

EXPECTED_CALLBACK_EVENT_VARIANTS = frozenset({'AgentLoopIterationEvent',
           'AmbiguityLoggedEvent',
           'AmbiguityReportEvent',
           'ArtifactSavedEvent',
           'BlackboardReduceEvent',
           'BuiltinSubagentEnterEvent',
           'BuiltinSubagentExitEvent',
           'BuiltinSubagentFallbackEvent',
           'CompactionEvent',
           'DeadEndPrunedEvent',
           'FinishTaskEvent',
           'HeartbeatEvent',
           'InternalErrorEvent',
           'InterruptedEvent',
           'InputDispatchEvent',
           'InputFileInjectedEvent',
           'LLMCallEvent',
           'LLMFallbackEvent',
           'ModelResolvedEvent',
           'NudgeEvent',
           'ParallelMapGroupEndedEvent',
           'ParallelMapGroupStartedEvent',
           'PhaseEndEvent',
           'PhaseStartEvent',
           'PredictChainStartEvent',
           'PromptCapturedEvent',
           'ResumedEvent',
           'RetryEvent',
           'RetryExhaustedEvent',
           'RunEndedEvent',
           'RunStartedEvent',
           'ThreadCleanedUpEvent',
           'ToolCallEvent',
           'ValidationFailEvent',
           'ValidationPassEvent',
           'WorkingMemoryUpdateEvent'})



EXPECTED_EXCEPTION_MRO: dict[str, tuple[str, ...]] = {'ExecutionError': ('ExecutionError',
                   'GraphExecutionError',
                   'GraphAgentError',
                   'Exception'),
 'GraphAgentError': ('GraphAgentError', 'Exception', 'BaseException', 'object'),
 'GraphCompileError': ('GraphCompileError', 'GraphAgentError', 'Exception', 'BaseException'),
 'GraphExecutionError': ('GraphExecutionError', 'GraphAgentError', 'Exception', 'BaseException'),
 'ModelProviderError': ('ModelProviderError', 'GraphAgentError', 'Exception', 'BaseException'),
 'ResourceNotFoundError': ('ResourceNotFoundError',
                           'GraphAgentError',
                           'Exception',
                           'BaseException'),
 'SkillCompilationError': ('SkillCompilationError',
                           'GraphCompileError',
                           'GraphAgentError',
                           'Exception',
                           'BaseException'),
 'SkillCompileError': ('SkillCompileError', 'LoaderError', 'GraphCompileError', 'GraphAgentError'),
 'SkillLoadError': ('SkillLoadError', 'LoaderError', 'GraphCompileError', 'GraphAgentError'),
 'SkillResolutionError': ('SkillResolutionError',
                          'ResourceNotFoundError',
                          'GraphAgentError',
                          'Exception',
                          'BaseException')}

REQUIRED_EXEMPTION_KEYS = frozenset(
    {
        "exemption_id",
        "pr",
        "pm_approval",
        "reason",
        "symbols",
        "fields",
        "hashes",
        "affected_features",
        "replacement_feature_ids",
        "expires_or_cleanup",
    }
)

EXEMPTION_ID_PATTERN = re.compile(r"^EX-[0-9]{4}-[a-z0-9-]+$")


def _load_contract_exemptions(path: Path = EXEMPTIONS_PATH) -> list[dict[str, object]]:
    data = yaml.safe_load(path.read_text()) or {}
    exemptions = data.get("exemptions", [])
    assert isinstance(exemptions, list), "contract exemptions must be a list"

    for index, entry in enumerate(exemptions):
        assert isinstance(entry, dict), f"exemption #{index} must be a mapping"
        missing_keys = REQUIRED_EXEMPTION_KEYS - entry.keys()
        assert not missing_keys, f"exemption #{index} missing required keys: {sorted(missing_keys)}"
        for key in ("pr", "pm_approval", "reason", "expires_or_cleanup"):
            assert isinstance(entry[key], str) and entry[key].strip(), f"exemption #{index} {key} must be non-empty"
        for key in ("symbols", "fields", "hashes"):
            assert isinstance(entry[key], list), f"exemption #{index} {key} must be a list"
            assert all(isinstance(item, str) and item.strip() for item in entry[key]), (
                f"exemption #{index} {key} entries must be non-empty strings"
            )
        assert isinstance(entry["exemption_id"], str) and EXEMPTION_ID_PATTERN.fullmatch(entry["exemption_id"]), (
            f"exemption #{index} exemption_id must match ^EX-[0-9]{{4}}-[a-z0-9-]+$"
        )
        for key in ("affected_features", "replacement_feature_ids"):
            assert isinstance(entry[key], list), f"exemption #{index} {key} must be a list"
            assert all(isinstance(item, str) and item.startswith("F-") for item in entry[key]), (
                f"exemption #{index} {key} entries must be feature ids"
            )
        assert entry["symbols"] or entry["fields"] or entry["hashes"], (
            f"exemption #{index} must name at least one symbol, field, or hash key"
        )
        assert entry["symbols"] or not entry["fields"] or all("." in field for field in entry["fields"]), (
            f"exemption #{index} field-only entries must use Symbol.field keys"
        )
    return exemptions


def _symbol_exemption_entry(symbol_name: str) -> dict[str, object] | None:
    for entry in _load_contract_exemptions():
        if symbol_name in entry["symbols"]:
            return entry
    return None


def _field_exemption_entry(symbol_name: str, field_name: str) -> dict[str, object] | None:
    qualified_field = f"{symbol_name}.{field_name}"
    for entry in _load_contract_exemptions():
        fields = entry["fields"]
        symbols = entry["symbols"]
        if qualified_field in fields or (symbol_name in symbols and field_name in fields):
            return entry
    return None


def is_symbol_exempted(symbol_name: str) -> bool:
    return _symbol_exemption_entry(symbol_name) is not None


def is_field_exempted(symbol_name: str, field_name: str) -> bool:
    return _field_exemption_entry(symbol_name, field_name) is not None


def _skip_for_exemption(entry: dict[str, object]) -> None:
    pytest.skip(f"Exempted by {entry['pr']}: {entry['reason']}")


def _assert_symbol_contract(actual: object, expected: object, symbol_name: str) -> None:
    if actual == expected:
        return
    if entry := _symbol_exemption_entry(symbol_name):
        _skip_for_exemption(entry)
    assert actual == expected, symbol_name


def _assert_field_contract(
    actual: tuple[tuple[str, str], ...], expected: tuple[tuple[str, str], ...], symbol_name: str
) -> None:
    if actual == expected:
        return

    actual_by_name = dict(actual)
    expected_by_name = dict(expected)
    drifted_fields = sorted(
        (set(actual_by_name) | set(expected_by_name))
        - {field_name for field_name in expected_by_name if actual_by_name.get(field_name) == expected_by_name[field_name]}
    )
    if drifted_fields and all(is_field_exempted(symbol_name, field_name) for field_name in drifted_fields):
        _skip_for_exemption(_field_exemption_entry(symbol_name, drifted_fields[0]) or {})
    if entry := _symbol_exemption_entry(symbol_name):
        _skip_for_exemption(entry)
    assert actual == expected, symbol_name


def _load_symbol(module_name: str, symbol_name: str) -> object:
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)


def _annotation_text(annotation: object) -> str:
    if annotation is inspect.Signature.empty:
        return ""
    if isinstance(annotation, str):
        return annotation
    if isinstance(annotation, type):
        return annotation.__name__
    text = (
        str(annotation)
        .replace("typing.", "")
        .replace("typing_extensions.", "")
        .replace("pathlib._local.Path", "Path")
        .replace("pathlib.Path", "Path")
    )
    return text.removeprefix("<class '").removesuffix("'>")


def _default_text(default: object) -> str:
    if default is inspect.Parameter.empty:
        return "<required>"
    if type(default) is object:
        return "<object object>"
    text = repr(default)
    if "factory" in text and (text.startswith("<factory") or text == "<factory>"):
        return "<factory>"
    return text


def _signature_contract(obj: object) -> tuple[tuple[tuple[str, str, str, str], ...], str]:
    signature = inspect.signature(obj)
    params = tuple(
        (
            parameter.name,
            parameter.kind.name,
            _default_text(parameter.default),
            _annotation_text(parameter.annotation),
        )
        for parameter in signature.parameters.values()
    )
    return params, _annotation_text(signature.return_annotation)


def _field_contract(obj: object) -> tuple[tuple[str, str], ...]:
    if isinstance(obj, type) and issubclass(obj, BaseModel):
        return tuple((name, _annotation_text(field.annotation)) for name, field in obj.model_fields.items())
    if dataclasses.is_dataclass(obj):
        return tuple((field.name, _annotation_text(field.type)) for field in dataclasses.fields(obj))
    annotations = getattr(obj, "__annotations__", None)
    if annotations:
        return tuple((name, _annotation_text(annotation)) for name, annotation in annotations.items())
    raise AssertionError(f"{obj!r} does not expose a supported field contract")


def _callback_event_variant_names(callback_event: object) -> set[str]:
    args = typing.get_args(callback_event)
    union_arg = args[0]
    return {getattr(arg, "__name__", str(arg)) for arg in typing.get_args(union_arg)}


def test_exemptions_yaml_schema_is_strict_when_populated(tmp_path: Path) -> None:
    broken_exemptions = tmp_path / "contract-exemptions.yaml"
    broken_exemptions.write_text(
        """
version: "1"
exemptions:
  - pm_approval: "approved"
    reason: "missing pr must fail"
    symbols: ["run_skill"]
    fields: []
    hashes: []
    expires_or_cleanup: "remove after migration"
""",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="missing required keys"):
        _load_contract_exemptions(broken_exemptions)


def test_exemptions_yaml_shape_is_valid() -> None:
    assert isinstance(_load_contract_exemptions(), list)


def test_exemptions_yaml_lookup_returns_false_for_unknown_symbols() -> None:
    assert not is_symbol_exempted("DefinitelyNotAContractSymbol")
    assert not is_field_exempted("DefinitelyNotAContractSymbol", "missing_field")


def test_contract_symbol_count_and_static_sets_are_authoritative() -> None:
    assert len(EXPECTED_CONTRACT_SYMBOLS) == 41
    assert len(EXPECTED_VENDOR_ONLY_SYMBOLS) == 5
    assert EXPECTED_KNOWN_MISSING_VENDOR_ONLY.keys() < EXPECTED_CONTRACT_SYMBOLS.keys()


def test_importable_contract_symbols_exist_at_canonical_source_modules() -> None:
    expected_importable = EXPECTED_CONTRACT_SYMBOLS.keys() - EXPECTED_KNOWN_MISSING_VENDOR_ONLY.keys()
    for symbol_name in sorted(expected_importable):
        module_name = EXPECTED_CONTRACT_SYMBOLS[symbol_name]
        module = importlib.import_module(module_name)
        if not hasattr(module, symbol_name):
            if entry := _symbol_exemption_entry(symbol_name):
                _skip_for_exemption(entry)
            assert hasattr(module, symbol_name), f"{symbol_name} missing from {module_name}"


def test_known_missing_vendor_only_symbols_are_locked_as_external_consumer_debt() -> None:
    for symbol_name, module_name in EXPECTED_KNOWN_MISSING_VENDOR_ONLY.items():
        module = importlib.import_module(module_name)
        if hasattr(module, symbol_name):
            if entry := _symbol_exemption_entry(symbol_name):
                _skip_for_exemption(entry)
            assert not hasattr(module, symbol_name), (
                f"{symbol_name} changed state in {module_name}; update the contract audit "
                "instead of silently drifting the vendor-only debt."
            )


def test_top_level_all_remains_the_declared_symbol_surface() -> None:
    import graph_agent

    _assert_symbol_contract(sorted(graph_agent.__all__), sorted(list(EXPECTED_ALL_18)), "__all__")


def test_function_signatures_are_stable() -> None:
    for symbol_name, (module_name, expected_params, expected_return) in EXPECTED_SIGNATURES.items():
        obj = _load_symbol(module_name, symbol_name)
        actual_params, actual_return = _signature_contract(obj)
        _assert_symbol_contract(actual_params, expected_params, symbol_name)
        _assert_symbol_contract(actual_return, expected_return, symbol_name)


def test_constructor_signatures_are_stable() -> None:
    for symbol_name, (module_name, expected_params, expected_return) in EXPECTED_CONSTRUCTOR_SIGNATURES.items():
        obj = _load_symbol(module_name, symbol_name)
        actual_params, actual_return = _signature_contract(obj.__init__)
        _assert_symbol_contract(actual_params, expected_params, symbol_name)
        _assert_symbol_contract(actual_return, expected_return, symbol_name)


def test_model_dataclass_and_typed_dict_field_names_and_types_are_stable() -> None:
    for symbol_name, (module_name, expected_fields) in EXPECTED_FIELD_CONTRACTS.items():
        obj = _load_symbol(module_name, symbol_name)
        _assert_field_contract(_field_contract(obj), expected_fields, symbol_name)




def test_exception_inheritance_chain_is_stable() -> None:
    for symbol_name, expected_mro in EXPECTED_EXCEPTION_MRO.items():
        obj = _load_symbol(EXPECTED_CONTRACT_SYMBOLS[symbol_name], symbol_name)
        actual_mro = tuple(cls.__name__ for cls in obj.__mro__[: len(expected_mro)])
        _assert_symbol_contract(actual_mro, expected_mro, symbol_name)


def test_callback_event_union_contains_consumed_event_models() -> None:
    callback_event = _load_symbol("graph_agent.callbacks.events", "CallbackEvent")
    actual_variants = _callback_event_variant_names(callback_event)
    _assert_symbol_contract(actual_variants, EXPECTED_CALLBACK_EVENT_VARIANTS, "CallbackEvent")
