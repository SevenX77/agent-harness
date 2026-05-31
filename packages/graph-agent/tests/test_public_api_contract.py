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

EXPECTED_ALL_18 = tuple(
    symbol for symbol, module_name in EXPECTED_CONTRACT_SYMBOLS.items() if module_name == "graph_agent"
)

EXPECTED_SIGNATURES: dict[str, tuple[str, tuple[tuple[str, str, str, str], ...], str]] = {'PredictGatewayChatModel': ('graph_agent.core._predict_internal.interception',
                             (('role_name', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                              ('resolved_role',
                               'POSITIONAL_OR_KEYWORD',
                               '<required>',
                               'ResolvedRole'),
                              ('mock_strategy', 'KEYWORD_ONLY', '<required>', 'BaseMockStrategy'),
                              ('max_tokens', 'KEYWORD_ONLY', '4096', 'int'),
                              ('temperature', 'KEYWORD_ONLY', '0.7', 'float'),
                              ('callbacks', 'KEYWORD_ONLY', '()', 'Sequence[Callback]'),
                              ('phase_name', 'KEYWORD_ONLY', 'None', 'str | None'),
                              ('probe_before_call', 'KEYWORD_ONLY', 'True', 'bool'),
                              ('thinking_enabled', 'KEYWORD_ONLY', 'None', 'bool | None'),
                              ('name', 'KEYWORD_ONLY', 'None', 'str | None'),
                              ('cache',
                               'KEYWORD_ONLY',
                               'None',
                               'langchain_core.caches.BaseCache | bool | None'),
                              ('verbose', 'KEYWORD_ONLY', '<factory>', 'bool'),
                              ('tags', 'KEYWORD_ONLY', 'None', 'list[str] | None'),
                              ('metadata', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None'),
                              ('custom_get_token_ids',
                               'KEYWORD_ONLY',
                               'None',
                               'collections.abc.Callable[[str], list[int]] | None'),
                              ('rate_limiter',
                               'KEYWORD_ONLY',
                               'None',
                               'langchain_core.rate_limiters.BaseRateLimiter | None'),
                              ('disable_streaming',
                               'KEYWORD_ONLY',
                               'False',
                               "Union[bool, Literal['tool_calling']]"),
                              ('output_version', 'KEYWORD_ONLY', '<factory>', 'str | None'),
                              ('profile',
                               'KEYWORD_ONLY',
                               'None',
                               'langchain_core.language_models.model_profile.ModelProfile | None'),
                              ('event_callbacks', 'KEYWORD_ONLY', '<factory>', 'tuple[Any, ...]'),
                              ('bound_tools',
                               'KEYWORD_ONLY',
                               '<factory>',
                               'tuple[dict[str, object], ...]'),
                              ('tool_choice', 'KEYWORD_ONLY', 'None', 'str | None'),
                              ('tool_kwargs', 'KEYWORD_ONLY', '<factory>', 'dict[str, object]'),
                              ('client_manager', 'KEYWORD_ONLY', 'None', 'Any')),
                             'None'),
 'assemble_graph': ('graph_agent',
                    (('compiled', 'POSITIONAL_OR_KEYWORD', '<required>', 'CompiledSkill'),
                     ('chat_model', 'KEYWORD_ONLY', 'None', 'Any'),
                     ('model_resolver', 'KEYWORD_ONLY', 'None', 'Any'),
                     ('max_patch_attempts', 'KEYWORD_ONLY', '3', 'int'),
                     ('callbacks', 'KEYWORD_ONLY', 'None', 'list[Any] | None'),
                     ('skill_resolver', 'KEYWORD_ONLY', '<required>', 'SkillResolverProtocol'),
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
 'run_skill': ('graph_agent',
               (('skill_path', 'POSITIONAL_OR_KEYWORD', '<required>', 'str | Path'),
                ('mock_llm', 'KEYWORD_ONLY', '<object object>', 'Any'),
                ('trace_dir', 'KEYWORD_ONLY', 'None', 'str | Path | None'),
                ('thread_id', 'KEYWORD_ONLY', 'None', 'str | None'),
                ('unattended', 'KEYWORD_ONLY', 'False', 'bool'),
                ('callbacks', 'KEYWORD_ONLY', 'None', 'list[Any] | None'),
                ('artifact_saver', 'KEYWORD_ONLY', 'None', 'Any | None'),
                ('initial_context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None'),
                ('cleanup_checkpoints_on_finish', 'KEYWORD_ONLY', 'True', 'bool'),
                ('skill_resolver', 'KEYWORD_ONLY', '<required>', 'SkillResolverProtocol'),
                ('model_resolver', 'KEYWORD_ONLY', 'None', 'Any | None'),
                ('inputs', 'VAR_KEYWORD', '<required>', 'Any')),
               'WorkflowResult'),
 'serialize_graph': ('graph_agent.core.graph_serializer',
                     (('manifest', 'POSITIONAL_OR_KEYWORD', '<required>', 'GraphManifest'),
                      ('original_md', 'POSITIONAL_OR_KEYWORD', 'None', 'str | None')),
                     'str'),
 'serialize_skill': ('graph_agent',
                     (('manifest', 'POSITIONAL_OR_KEYWORD', '<required>', 'SkillManifest'),),
                     'str')}

EXPECTED_CONSTRUCTOR_SIGNATURES: dict[str, tuple[str, tuple[tuple[str, str, str, str], ...], str]] = {'BaseMockStrategy': ('graph_agent.core._predict_internal.strategy',
                      (('self', 'POSITIONAL_ONLY', '<required>', ''),
                       ('args', 'VAR_POSITIONAL', '<required>', ''),
                       ('kwargs', 'VAR_KEYWORD', '<required>', '')),
                      ''),
 'Callback': ('graph_agent',
              (('self', 'POSITIONAL_ONLY', '<required>', ''),
               ('args', 'VAR_POSITIONAL', '<required>', ''),
               ('kwargs', 'VAR_KEYWORD', '<required>', '')),
              ''),
 'ExecutionError': ('graph_agent.core.exceptions',
                    (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                     ('message', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                     ('payload', 'KEYWORD_ONLY', 'None', 'ErrorPayload | None'),
                     ('context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None')),
                    'None'),
 'GoldenCaseStrategy': ('graph_agent.core._predict_internal.strategy',
                        (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                         ('golden_case', 'POSITIONAL_OR_KEYWORD', '<required>', 'GoldenCase'),
                         ('phase_schemas',
                          'KEYWORD_ONLY',
                          'None',
                          'dict[str, dict[str, Any]] | None')),
                        'None'),
 'GraphAgentError': ('graph_agent',
                     (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                      ('message', 'POSITIONAL_OR_KEYWORD', '<required>', 'str'),
                      ('payload', 'KEYWORD_ONLY', 'None', 'ErrorPayload | None'),
                      ('context', 'KEYWORD_ONLY', 'None', 'dict[str, Any] | None')),
                     'None'),
 'HeuristicStubStrategy': ('graph_agent.core._predict_internal.strategy',
                           (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                            ('phase_schemas',
                             'POSITIONAL_OR_KEYWORD',
                             'None',
                             'dict[str, dict[str, Any]] | None')),
                           'None'),
 'LocalWorkspaceResolver': ('graph_agent',
                            (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                             ('search_paths',
                              'POSITIONAL_OR_KEYWORD',
                              'None',
                              'Iterable[str | Path] | None')),
                            'None'),
 'LoggingCallback': ('graph_agent',
                     (('self', 'POSITIONAL_ONLY', '<required>', ''),
                      ('args', 'VAR_POSITIONAL', '<required>', ''),
                      ('kwargs', 'VAR_KEYWORD', '<required>', '')),
                     ''),
 'MetricsCallback': ('graph_agent', (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),), 'None'),
 'MockStrategy': ('graph_agent.core._predict_internal.strategy',
                  (('self', 'POSITIONAL_ONLY', '<required>', ''),
                   ('args', 'VAR_POSITIONAL', '<required>', ''),
                   ('kwargs', 'VAR_KEYWORD', '<required>', '')),
                  ''),
 'PredictTracingCallback': ('graph_agent.core._predict_internal.tracing',
                            (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                             ('args', 'VAR_POSITIONAL', '<required>', 'Any'),
                             ('source_cache',
                              'KEYWORD_ONLY',
                              'None',
                              'PredictMockSourceCache | None'),
                             ('kwargs', 'VAR_KEYWORD', '<required>', 'Any')),
                            ''),
 'SkillCompilationError': ('graph_agent',
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
 'SkillLoadError': ('graph_agent',
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
                          'None'),
 'TracingCallback': ('graph_agent',
                     (('self', 'POSITIONAL_OR_KEYWORD', '<required>', ''),
                      ('trace_dir', 'POSITIONAL_OR_KEYWORD', 'None', 'str | Path | None')),
                     'None')}

EXPECTED_FIELD_CONTRACTS: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {'AgentNodeAST': ('graph_agent.core.manifest',
                  (('name', 'str | None'),
                   ('raw_blocks', 'dict[str, str]'),
                   ('metadata', 'dict[str, Any]'),
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
 'AmbiguityReportEvent': ('graph_agent.callbacks.events',
                          (('schema_version', "Literal['1.0']"),
                           ('timestamp', 'str'),
                           ('sub_run_id', 'str | None'),
                           ('group_key', 'str | None'),
                           ('event_type', "Literal['ambiguity_report']"),
                           ('phase_name', 'str'),
                           ('ambiguity_type', 'str'),
                           ('question', 'str'),
                           ('decision', 'str'))),
 'BlackboardState': ('graph_agent',
                     (('data',
                       "ForwardRef('Annotated[BlackboardData, blackboard_data_merge]', "
                       "module='graph_agent.runtime.state')"),
                      ('flow', "ForwardRef('dict[str, Any]', module='graph_agent.runtime.state')"),
                      ('messages',
                       "ForwardRef('Annotated[list[AnyMessage], add_messages]', "
                       "module='graph_agent.runtime.state')"),
                      ('run_id', "ForwardRef('str | None', module='graph_agent.runtime.state')"))),
 'CompactionEvent': ('graph_agent.callbacks.events',
                     (('schema_version', "Literal['1.0']"),
                      ('timestamp', 'str'),
                      ('sub_run_id', 'str | None'),
                      ('group_key', 'str | None'),
                      ('event_type', "Literal['compaction']"),
                      ('phase_name', 'str'),
                      ('removed_pairs', 'int'),
                      ('removed_summary', 'str | None'),
                      ('content_ref', 'str | None'))),
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
 'DeadEndPrunedEvent': ('graph_agent.callbacks.events',
                        (('schema_version', "Literal['1.0']"),
                         ('timestamp', 'str'),
                         ('sub_run_id', 'str | None'),
                         ('group_key', 'str | None'),
                         ('event_type', "Literal['dead_end_pruned']"),
                         ('phase_name', 'str'),
                         ('summary', 'str'))),
 'FinishTaskEvent': ('graph_agent.callbacks.events',
                     (('schema_version', "Literal['1.0']"),
                      ('timestamp', 'str'),
                      ('sub_run_id', 'str | None'),
                      ('group_key', 'str | None'),
                      ('event_type', "Literal['finish_task']"),
                      ('phase_name', 'str'),
                      ('reasoning', 'str'),
                      ('evidence', 'list[str]'))),
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
                    ('metadata', 'dict[str, Any]'))),
 'GraphPhaseRef': ('graph_agent.core.manifest',
                   (('id', 'str'), ('src', 'str'), ('depends_on', 'list[str]'))),
 'LLMCallEvent': ('graph_agent.callbacks.events',
                  (('schema_version', "Literal['1.0']"),
                   ('timestamp', 'str'),
                   ('sub_run_id', 'str | None'),
                   ('group_key', 'str | None'),
                   ('event_type', "Literal['llm_call']"),
                   ('phase_name', 'str'),
                   ('input_tokens', 'int'),
                   ('output_tokens', 'int'),
                   ('messages', 'list[dict[str, Any]] | None'),
                   ('response_data', 'dict[str, Any] | None'))),
 'LLMFallbackEvent': ('graph_agent.callbacks.events',
                      (('schema_version', "Literal['1.0']"),
                       ('timestamp', 'str'),
                       ('sub_run_id', 'str | None'),
                       ('group_key', 'str | None'),
                       ('event_type', "Literal['llm_fallback']"),
                       ('phase_name', 'str'),
                       ('from_provider', 'str'),
                       ('to_provider', 'str'),
                       ('reason', 'str'),
                       ('code', 'str | None'),
                       ('context', 'dict[str, Any]'))),
 'LogicNodeAST': ('graph_agent.core.manifest',
                  (('name', 'str | None'),
                   ('raw_blocks', 'dict[str, str]'),
                   ('metadata', 'dict[str, Any]'),
                   ('mode', "Literal['logic']"),
                   ('io', 'PhaseIOSchema'),
                   ('actions', 'list[str]'),
                   ('validator', 'bool'))),
 'NudgeEvent': ('graph_agent.callbacks.events',
                (('schema_version', "Literal['1.0']"),
                 ('timestamp', 'str'),
                 ('sub_run_id', 'str | None'),
                 ('group_key', 'str | None'),
                 ('event_type', "Literal['nudge']"),
                 ('phase_name', 'str'),
                 ('nudge_count', 'int'),
                 ('nudge_type', 'str'))),
 'PathDiff': ('graph_agent.core._predict_internal.models',
              (('expected_path', 'list[str]'),
               ('actual_path', 'list[str]'),
               ('missing', 'list[str]'),
               ('extra', 'list[str]'),
               ('order_mismatch', 'bool'))),
 'PhaseEndEvent': ('graph_agent.callbacks.events',
                   (('schema_version', "Literal['1.0']"),
                    ('timestamp', 'str'),
                    ('sub_run_id', 'str | None'),
                    ('group_key', 'str | None'),
                    ('event_type', "Literal['phase_end']"),
                    ('phase_name', 'str'),
                    ('context', 'dict[str, Any]'),
                    ('metrics', 'dict[str, Any]'))),
 'PhaseRecord': ('graph_agent.core._predict_internal.models',
                 (('phase_name', 'str'),
                  ('type', "Literal['logic', 'llm']"),
                  ('inputs', 'dict[str, Any]'),
                  ('outputs', 'dict[str, Any]'),
                  ('mocked_source',
                   "Optional[Literal['golden_case', 'copilot', 'heuristic_stub', 'manual']]"))),
 'PhaseStartEvent': ('graph_agent.callbacks.events',
                     (('schema_version', "Literal['1.0']"),
                      ('timestamp', 'str'),
                      ('sub_run_id', 'str | None'),
                      ('group_key', 'str | None'),
                      ('event_type', "Literal['phase_start']"),
                      ('phase_name', 'str'),
                      ('context', 'dict[str, Any]'))),
 'PredictGatewayChatModel': ('graph_agent.core._predict_internal.interception',
                             (('name', 'str | None'),
                              ('cache', 'langchain_core.caches.BaseCache | bool | None'),
                              ('verbose', 'bool'),
                              ('callbacks',
                               'list[langchain_core.callbacks.base.BaseCallbackHandler] | '
                               'langchain_core.callbacks.base.BaseCallbackManager | None'),
                              ('tags', 'list[str] | None'),
                              ('metadata', 'dict[str, Any] | None'),
                              ('custom_get_token_ids',
                               'collections.abc.Callable[[str], list[int]] | None'),
                              ('rate_limiter',
                               'langchain_core.rate_limiters.BaseRateLimiter | None'),
                              ('disable_streaming', "Union[bool, Literal['tool_calling']]"),
                              ('output_version', 'str | None'),
                              ('profile',
                               'langchain_core.language_models.model_profile.ModelProfile | None'),
                              ('role_name', 'str'),
                              ('resolved_role', 'ResolvedRole'),
                              ('max_tokens', 'int'),
                              ('temperature', 'float'),
                              ('phase_name', 'str | None'),
                              ('event_callbacks', 'tuple[Any, ...]'),
                              ('probe_before_call', 'bool'),
                              ('thinking_enabled', 'bool | None'),
                              ('bound_tools', 'tuple[dict[str, object], ...]'),
                              ('tool_choice', 'str | None'),
                              ('tool_kwargs', 'dict[str, object]'),
                              ('client_manager', 'Any'),
                              ('mock_strategy', 'BaseMockStrategy'))),
 'PredictResult': ('graph_agent.core._predict_internal.models',
                   (('status', "Literal['success', 'failed']"),
                    ('phases', 'list[graph_agent.core._predict_internal.models.PhaseRecord]'),
                    ('path_diff', 'graph_agent.core._predict_internal.models.PathDiff | None'))),
 'RetryEvent': ('graph_agent.callbacks.events',
                (('schema_version', "Literal['1.0']"),
                 ('timestamp', 'str'),
                 ('sub_run_id', 'str | None'),
                 ('group_key', 'str | None'),
                 ('event_type', "Literal['retry']"),
                 ('phase_name', 'str'),
                 ('target_phase', 'str'),
                 ('feedback', 'list[str]'))),
 'SkillManifest': ('graph_agent',
                   (('schema_version', "Literal['v0.3.0']"),
                    ('name', 'str'),
                    ('description', 'str'),
                    ('io', 'PhaseIOSchema'),
                    ('phases', 'list[str]'),
                    ('metadata', 'dict[str, Any]'))),
 'SubgraphNodeAST': ('graph_agent.core.manifest',
                     (('name', 'str | None'),
                      ('raw_blocks', 'dict[str, str]'),
                      ('metadata', 'dict[str, Any]'),
                      ('mode', "Literal['subgraph']"),
                      ('target_skill', 'str'),
                      ('io', 'PhaseIOSchema'),
                      ('validator', 'bool'))),
 'ToolCallEvent': ('graph_agent.callbacks.events',
                   (('schema_version', "Literal['1.0']"),
                    ('timestamp', 'str'),
                    ('sub_run_id', 'str | None'),
                    ('group_key', 'str | None'),
                    ('event_type', "Literal['tool_call']"),
                    ('phase_name', 'str'),
                    ('tool_name', 'str'),
                    ('args', 'dict[str, Any]'),
                    ('result', 'str'),
                    ('duration_ms', 'float | None'))),
 'ValidationFailEvent': ('graph_agent.callbacks.events',
                         (('schema_version', "Literal['1.0']"),
                          ('timestamp', 'str'),
                          ('sub_run_id', 'str | None'),
                          ('group_key', 'str | None'),
                          ('event_type', "Literal['validation_fail']"),
                          ('phase_name', 'str'),
                          ('errors', 'list[str]'),
                          ('retry_count', 'int'))),
 'WorkflowResult': ('graph_agent',
                    (('success', 'bool'),
                     ('run_id', 'str'),
                     ('skill_id', 'str'),
                     ('context', 'dict[str, Any]'),
                     ('metrics', 'WorkflowMetrics'),
                     ('trace_path', 'Path | None'),
                     ('error', 'str | None'),
                     ('started_at', 'datetime'),
                     ('finished_at', 'datetime'),
                     ('wall_time_sec', 'float'))),
 'WorkingMemoryUpdateEvent': ('graph_agent.callbacks.events',
                              (('schema_version', "Literal['1.0']"),
                               ('timestamp', 'str'),
                               ('sub_run_id', 'str | None'),
                               ('group_key', 'str | None'),
                               ('event_type', "Literal['working_memory_update']"),
                               ('phase_name', 'str'),
                               ('content_length', 'int'),
                               ('content', 'str | None')))}

EXPECTED_CALLBACK_EVENT_VARIANTS = frozenset({'AgentLoopIterationEvent',
           'AmbiguityLoggedEvent',
           'AmbiguityReportEvent',
           'ArtifactSavedEvent',
           'BuiltinSubagentEnterEvent',
           'BuiltinSubagentExitEvent',
           'BuiltinSubagentFallbackEvent',
           'CompactionEvent',
           'DeadEndPrunedEvent',
           'FinishTaskEvent',
           'HeartbeatEvent',
           'InternalErrorEvent',
           'InterruptedEvent',
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

EXPECTED_CALLBACK_PROTOCOL_METHODS: dict[str, frozenset[str]] = {'Callback': frozenset({'on_ambiguity_report',
                        'on_compaction',
                        'on_dead_end_pruned',
                        'on_event',
                        'on_finish_task',
                        'on_llm_call',
                        'on_nudge',
                        'on_phase_end',
                        'on_phase_start',
                        'on_retry',
                        'on_tool_call',
                        'on_validation_fail',
                        'on_working_memory_update'}),
 'LoggingCallback': frozenset({'on_ambiguity_report',
                               'on_compaction',
                               'on_dead_end_pruned',
                               'on_event',
                               'on_finish_task',
                               'on_llm_call',
                               'on_nudge',
                               'on_phase_end',
                               'on_phase_start',
                               'on_retry',
                               'on_tool_call',
                               'on_validation_fail',
                               'on_working_memory_update'}),
 'MetricsCallback': frozenset({'on_ambiguity_report',
                               'on_compaction',
                               'on_dead_end_pruned',
                               'on_event',
                               'on_finish_task',
                               'on_llm_call',
                               'on_nudge',
                               'on_phase_end',
                               'on_phase_start',
                               'on_retry',
                               'on_tool_call',
                               'on_validation_fail',
                               'on_working_memory_update',
                               'summary'}),
 'TracingCallback': frozenset({'_active_phase',
                               '_write_event',
                               '_write_typed_event',
                               'on_ambiguity_report',
                               'on_compaction',
                               'on_dead_end_pruned',
                               'on_event',
                               'on_finish_task',
                               'on_llm_call',
                               'on_nudge',
                               'on_phase_end',
                               'on_phase_start',
                               'on_retry',
                               'on_tool_call',
                               'on_validation_fail',
                               'on_working_memory_update',
                               'save',
                               'set_trace_dir',
                               'summary'})}

EXPECTED_EXCEPTION_MRO: dict[str, tuple[str, ...]] = {'ExecutionError': ('ExecutionError', 'GraphAgentError', 'Exception', 'BaseException'),
 'GraphAgentError': ('GraphAgentError', 'Exception', 'BaseException', 'object'),
 'SkillCompilationError': ('SkillCompilationError',
                           'GraphAgentError',
                           'Exception',
                           'BaseException'),
 'SkillCompileError': ('SkillCompileError', 'LoaderError', 'GraphAgentError', 'Exception'),
 'SkillLoadError': ('SkillLoadError', 'LoaderError', 'GraphAgentError', 'Exception'),
 'SkillResolutionError': ('SkillResolutionError',
                          'SkillLoadError',
                          'LoaderError',
                          'GraphAgentError')}

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
    assert len(EXPECTED_CONTRACT_SYMBOLS) == 61
    assert len(EXPECTED_VENDOR_ONLY_SYMBOLS) == 6
    assert len(EXPECTED_PREDICT_INTERNAL_SYMBOLS) == 12
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


def test_top_level_all_remains_the_declared_18_symbol_surface() -> None:
    import graph_agent

    _assert_symbol_contract(graph_agent.__all__, list(EXPECTED_ALL_18), "__all__")


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


def test_callback_protocols_method_surface_is_stable() -> None:
    for symbol_name, expected_methods in EXPECTED_CALLBACK_PROTOCOL_METHODS.items():
        obj = _load_symbol(EXPECTED_CONTRACT_SYMBOLS[symbol_name], symbol_name)
        actual_methods = frozenset(
            name
            for name, value in inspect.getmembers(
                obj,
                lambda value: inspect.isroutine(value) or isinstance(value, property),
            )
            if not name.startswith("__")
        )
        _assert_symbol_contract(actual_methods, expected_methods, symbol_name)


def test_exception_inheritance_chain_is_stable() -> None:
    for symbol_name, expected_mro in EXPECTED_EXCEPTION_MRO.items():
        obj = _load_symbol(EXPECTED_CONTRACT_SYMBOLS[symbol_name], symbol_name)
        actual_mro = tuple(cls.__name__ for cls in obj.__mro__[: len(expected_mro)])
        _assert_symbol_contract(actual_mro, expected_mro, symbol_name)


def test_callback_event_union_contains_consumed_event_models() -> None:
    callback_event = _load_symbol("graph_agent.callbacks.events", "CallbackEvent")
    actual_variants = _callback_event_variant_names(callback_event)
    _assert_symbol_contract(actual_variants, EXPECTED_CALLBACK_EVENT_VARIANTS, "CallbackEvent")


def test_predict_internal_symbols_are_explicit_de_facto_contract_debt() -> None:
    for symbol_name in sorted(EXPECTED_PREDICT_INTERNAL_SYMBOLS):
        module_name = EXPECTED_CONTRACT_SYMBOLS[symbol_name]
        module = importlib.import_module(module_name)
        if not hasattr(module, symbol_name):
            if entry := _symbol_exemption_entry(symbol_name):
                _skip_for_exemption(entry)
            assert hasattr(module, symbol_name), f"{symbol_name} missing from known-debt module {module_name}"
