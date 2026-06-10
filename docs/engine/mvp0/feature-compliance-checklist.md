---
status: FROZEN
source: packages/graph-agent/spec/features.yaml
---
<!-- DO NOT EDIT: Golden principle contract baseline. -->

# Feature Compliance Checklist

This checklist is generated from the Round 28 feature manifest. Each item names one independently reviewable business capability, its boundary, source anchors, core implementation paths, and one collectable pytest guard.

## Manifest Features

### F-public-api-surface: Expose the supported graph_agent import surface without silently adding or dropping public symbols.
- **Boundary**: public-method - graph_agent.__all__ and public-api contract
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/__main__.py, packages/graph-agent/src/graph_agent/settings.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/test_public_api_contract.py::test_top_level_all_remains_the_declared_symbol_surface]`

### F-vendor-contract-debt: Keep known vendor-only contract debt visible until compatibility shims or removals are approved.
- **Boundary**: externally-observable-behavior - vendor-only symbols in public-api contract
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/__init__.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/test_public_api_contract.py::test_known_missing_vendor_only_symbols_are_locked_as_external_consumer_debt]`

### F-md-frontmatter-parsing: Parse markdown frontmatter and body into stable skill metadata and diagnostics.
- **Boundary**: lifecycle-behavior - skill parser contract
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/parser.py, packages/graph-agent/src/graph_agent/core/skill_parser.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/core/test_parse_skill_file.py::test_parse_markdown_parts_returns_frontmatter_body_and_line_meta]`

### F-graph-skill-loading: Load GRAPH skills from disk, validate topology, and build the phase registry.
- **Boundary**: lifecycle-behavior - GRAPH skill spec
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/loader.py, packages/graph-agent/src/graph_agent/core/manifest.py
- **Primary contracts**: 21 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_valid_v030_graph_uses_frontmatter_phase_registry_and_body_phase_dag]`

### F-logic-action-execution: Run LOGIC action phases through registered Python actions and validators.
- **Boundary**: lifecycle-behavior - LOGIC skill spec
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/actions.py, packages/graph-agent/src/graph_agent/core/phase_nodes/code_phase_node.py
- **Primary contracts**: 15 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/core/test_phase_node.py::test_phase_node_execute_returns_updated_state]`

### F-subgraph-delegation: Compile and execute nested subgraphs while preserving parent-child IO boundaries.
- **Boundary**: lifecycle-behavior - SUBGRAPH skill spec
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py, packages/graph-agent/src/graph_agent/core/subagents.py
- **Primary contracts**: 8 error codes, 3 events
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_rejected_at_compile_time]`

### F-agent-phase-orchestration: Compile AGENT phases into prompt-driven execution with role, goal, tools, and finish contracts.
- **Boundary**: lifecycle-behavior - AGENT skill spec
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/__init__.py
- **Primary contracts**: 16 error codes, 1 events
- `[Covered By: packages/graph-agent/tests/fixtures/test_v030_agent_demo_compiles.py::test_v030_agent_demo_fixture_compiles_and_renders_template]`

### F-mention-resolution: Resolve @-mentions against tools, references, examples, subagents, and subgraphs before runtime.
- **Boundary**: lifecycle-behavior - mention syntax spec
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/mentions.py
- **Primary contracts**: 4 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_missing_mention_target_is_rejected]`

### F-resource-reference-access: Expose reference and example resources through safe builtin reader tools.
- **Boundary**: public-method - resource mechanisms and builtin modules specs
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/tools/builtin/read_example.py, packages/graph-agent/src/graph_agent/tools/builtin/read_reference.py
- **Primary contracts**: 14 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/tools/test_builtin_resource_tools.py::test_read_reference_returns_declared_current_phase_markdown]`

### F-skill-resolution: Resolve target skills through local workspace registries with deterministic errors for misses and ambiguity.
- **Boundary**: lifecycle-behavior - skill resolver protocol spec
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/local_workspace_resolver.py, packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py
- **Primary contracts**: 6 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/core/test_local_workspace_resolver.py::test_local_workspace_resolver_resolves_direct_directory]`

### F-compile-runtime-flow: Keep compile, template assembly, and runtime workflow boundaries explicit and ordered.
- **Boundary**: lifecycle-behavior - compile-runtime flow spec
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/compiler.py, packages/graph-agent/src/graph_agent/core/graph_builder.py
- **Primary contracts**: 2 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/core/test_compile_skill_v030_root_rejection.py::test_compile_skill_rejects_legacy_schema_20_file_path]`

### F-runtime-execution: Run compiled graph skills and return stable workflow results to callers.
- **Boundary**: public-method - graph_agent.run_skill
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/cognitive/context_facade.py, packages/graph-agent/src/graph_agent/core/callback_bridge.py
- **Primary contracts**: 1 error codes, 8 events
- `[Covered By: packages/graph-agent/tests/core/test_run_skill_entrypoint_root_shape.py::test_run_skill_single_markdown_file_returns_v030_root_error]`

### F-state-blackboard: Map parent, child, and blackboard state without leaking unrelated execution state.
- **Boundary**: lifecycle-behavior - runtime state mapping
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/io_manager.py, packages/graph-agent/src/graph_agent/core/run_context.py
- **Primary contracts**: 1 error codes, 1 events
- `[Covered By: packages/graph-agent/tests/test_round28_invariant_guards.py::test_round28_blackboard_state_has_explicit_mapping_boundary]`

### F-checkpoint-persistence: Persist and restore runtime checkpoints across graph execution boundaries.
- **Boundary**: lifecycle-behavior - checkpointer runtime
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/cache.py, packages/graph-agent/src/graph_agent/core/checkpointer.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/core/test_v030_deltachannel_checkpoint.py::test_sqlite_deltachannel_checkpoint_size]`

### F-callback-event-stream: Emit typed callback events with stable discriminator and schema metadata.
- **Boundary**: externally-observable-behavior - CallbackEvent union
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/callbacks/base.py, packages/graph-agent/src/graph_agent/callbacks/emit.py
- **Primary contracts**: 0 error codes, 1 events
- `[Covered By: packages/graph-agent/tests/callbacks/test_events.py::TestUnionDiscriminator::test_unknown_event_type_rejected]`

### F-callback-tracing: Record execution traces and callback payloads for downstream observability.
- **Boundary**: externally-observable-behavior - TracingCallback contract
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/callbacks/tracing.py, packages/graph-agent/src/graph_agent/core/tracing_proxy.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/callbacks/test_v030_trace_events.py::test_tracing_callback_writes_v030_typed_events]`

### F-error-code-recovery: Attach stable F-v3 error metadata, severity, and recovery hints to failures.
- **Boundary**: externally-observable-behavior - error code spec
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/error_registry.py, packages/graph-agent/src/graph_agent/core/exceptions.py
- **Primary contracts**: 0 error codes, 6 events
- `[Covered By: packages/graph-agent/tests/test_round28_invariant_guards.py::test_round28_error_registry_keeps_f_v3_metadata_shape]`

### F-llm-prompt-assembly: Assemble the v0.3 cognitive prompt with the required eight business slots.
- **Boundary**: lifecycle-behavior - cognitive template spec
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/cognitive/critic.py, packages/graph-agent/src/graph_agent/cognitive/memory.py
- **Primary contracts**: 3 error codes, 2 events
- `[Covered By: packages/graph-agent/tests/test_round28_invariant_guards.py::test_round28_prompt_template_keeps_eight_named_slots]`

### F-llm-execution: Dispatch model calls through configured providers, fallbacks, and predictive gateways.
- **Boundary**: lifecycle-behavior - LLM client manager
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/models/__init__.py
- **Primary contracts**: 0 error codes, 4 events
- `[Covered By: packages/graph-agent/tests/models/test_predict_gateway_chat_model.py::test_generate_uses_p0_golden_before_p1_override_and_p2_stub]`

### F-tool-call-binding: Bind tools into LLM phases while preserving finish_task and provider call behavior.
- **Boundary**: lifecycle-behavior - tool binding runtime
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/skill_tool_factory.py
- **Primary contracts**: 1 error codes, 2 events
- `[Covered By: packages/graph-agent/tests/models/test_predict_gateway_chat_model.py::test_bind_tools_preserves_predict_gateway_and_mock_strategy]`

### F-finish-task-validation: Validate finish_task output schema and reject incomplete agent completion payloads.
- **Boundary**: externally-observable-behavior - finish_task contract
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/cognitive/finish.py, packages/graph-agent/src/graph_agent/cognitive/finish_task.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/runtime/test_exit_contract.py::test_v030_exit_contract_is_hardcoded_at_prompt_tail]`

### F-md-patch: Apply markdown patch tools and reasoning patches without corrupting structured output.
- **Boundary**: lifecycle-behavior - md patch tool contract
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/cognitive/md2json.py, packages/graph-agent/src/graph_agent/cognitive/md_patch.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/models/test_reasoning_patch.py::test_apply_reasoning_patch_is_idempotent]`

### F-tool-sandbox-permission: Reject unsafe tool/module operations that escape the allowed execution surface.
- **Boundary**: externally-observable-behavior - module sandbox and purity guard
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/module_sandbox.py, packages/graph-agent/src/graph_agent/core/tool_wrapper.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/test_round28_invariant_guards.py::test_round28_tool_sandbox_blocks_write_and_escape_shapes]`

### F-tool-sandbox-isolation: Run builtin tools with isolated context access and predictable IO side effects.
- **Boundary**: lifecycle-behavior - tool runtime sandbox
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/tools/builtin/context_access.py, packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/tools/test_context_access.py::TestQueryWorkingMemory::test_returns_working_memory]`

### F-middleware-ordering: Mount cognitive middleware in the required observation-before-control order.
- **Boundary**: lifecycle-behavior - middleware ordering
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/cognitive/middlewares.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/test_round28_invariant_guards.py::test_round28_middleware_order_keeps_observation_before_control]`

### F-middleware-mounting: Enable and disable runtime middleware based on attended, unattended, and configuration modes.
- **Boundary**: lifecycle-behavior - middleware factory
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py, packages/graph-agent/src/graph_agent/middleware/execution_control.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/cognitive/test_middlewares.py::TestCreateCustomMiddlewaresPR5::test_clarification_enabled_by_default]`

### F-predict-internal-mocking: Provide deterministic prediction and golden-case mocks for offline execution and tests.
- **Boundary**: lifecycle-behavior - predict internal gateway
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py, packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/models/test_predict_gateway_chat_model.py::test_generate_sets_mock_metadata_and_zero_usage_without_provider_call]`

### F-serialization-output: Serialize manifests, callback payloads, and graph structures into stable JSON-safe output.
- **Boundary**: public-method - serialization public API
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/callbacks/serialize.py, packages/graph-agent/src/graph_agent/core/graph_serializer.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/callbacks/test_serialize.py::TestPrimitives::test_passthrough]`

### F-graph-assembly: Assemble phase nodes into executable graphs while preserving graph serialization contracts.
- **Boundary**: public-method - graph assembly public API
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/core/graph_assembler.py, packages/graph-agent/src/graph_agent/core/phase_nodes/_helpers.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_graph_serializer_fresh_render_uses_v030_dual_track_graph]`

### F-runtime-compatibility-patches: Apply runtime compatibility patches and compatibility hooks exactly through the central bootstrap path.
- **Boundary**: lifecycle-behavior - bootstrap patches and reasoning compatibility
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/bootstrap.py, packages/graph-agent/src/graph_agent/patches/__init__.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/test_bootstrap.py::test_apply_patches_calls_central_patch_entry_once]`

### F-observability-metrics: Expose logging and metrics callbacks for operational visibility without changing execution semantics.
- **Boundary**: externally-observable-behavior - logging and metrics callbacks
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/callbacks/logging_cb.py, packages/graph-agent/src/graph_agent/callbacks/metrics.py
- **Primary contracts**: 0 error codes, 0 events
- `[Covered By: packages/graph-agent/tests/callbacks/test_events.py::TestSchemaInvariants::test_every_class_stamps_schema_version_1_0[PhaseStartEvent]]`

### F-clarification-flow: Handle ambiguity and clarification workflows consistently in attended and unattended modes.
- **Boundary**: externally-observable-behavior - clarification middleware
- **Sources**: public-api, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/cognitive/ambiguity.py, packages/graph-agent/src/graph_agent/cognitive/clarification_middleware.py
- **Primary contracts**: 0 error codes, 2 events
- `[Covered By: packages/graph-agent/tests/cognitive/test_middlewares.py::TestUnattendedClarificationMiddleware::test_intercepts_ask_clarification_in_unattended_mode]`

### F-parallel-map-tools: Run parallel map and builtin tool providers through stable tool contracts.
- **Boundary**: lifecycle-behavior - parallel map builtin tool
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/tools/builtin/parallel_map.py
- **Primary contracts**: 0 error codes, 2 events
- `[Covered By: packages/graph-agent/tests/tools/test_parallel_map.py::test_parallel_map_runs_children_in_input_order_and_emits_group_events]`

### F-storage-io: Store, load, and analyze IO artifacts through graph-agent storage and analyzer helpers.
- **Boundary**: lifecycle-behavior - IO storage helpers
- **Sources**: skill-spec, source-file-map
- **Core paths**: packages/graph-agent/src/graph_agent/examples/hello_world/script/greet.py, packages/graph-agent/src/graph_agent/io/manager.py
- **Primary contracts**: 0 error codes, 1 events
- `[Covered By: packages/graph-agent/tests/io/test_storage.py::TestStorageManagerBasics::test_save_artifact_writes_str_bytes_and_json]`
