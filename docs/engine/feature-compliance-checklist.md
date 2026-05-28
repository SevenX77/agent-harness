# Feature Compliance Checklist

## Why This Matrix Exists

This matrix turns the engine feature surface into a reviewable contract. Each item names the concrete behavior, the code that implements it, the downstream relevance, and the existing test that keeps the behavior from being removed silently.

## How To Add Features

Add a new lifecycle item with code facts, consumer relevance, and one coverage tag that points to a real pytest test function. Keep the item specific enough that a reviewer can tell what behavior is protected.

## Loading & Parsing

### LP-01: Markdown frontmatter and body split preserve line metadata
- **Code facts**: `packages/graph-agent/src/graph_agent/core/parser.py::parse_markdown_parts`
- **Consumer relevance**: Studio compile diagnostics and vendored backend loaders depend on stable frontmatter/body parsing.
- `[Covered By: packages/graph-agent/tests/core/test_parse_skill_file.py::test_parse_markdown_parts_returns_frontmatter_body_and_line_meta]`

### LP-02: CRLF markdown files parse consistently on disk
- **Code facts**: `packages/graph-agent/src/graph_agent/core/parser.py::parse_markdown_parts`
- **Consumer relevance**: Studio and scripts can load skills edited on Windows without format drift.
- `[Covered By: packages/graph-agent/tests/core/test_parser_crlf_compat.py::test_parse_markdown_parts_accepts_crlf_on_disk]`

### LP-03: Missing frontmatter fails before AST construction
- **Code facts**: `packages/graph-agent/src/graph_agent/core/parser.py::parse_markdown_parts`
- **Consumer relevance**: Studio upload and validation paths receive deterministic loader errors for malformed skill files.
- `[Covered By: packages/graph-agent/tests/core/test_parse_skill_file.py::test_parse_markdown_parts_rejects_missing_frontmatter]`

### LP-04: GRAPH frontmatter phase registry and body DAG are parsed together
- **Code facts**: `packages/graph-agent/src/graph_agent/core/loader.py::SkillLoader.compile_skill`, `packages/graph-agent/src/graph_agent/core/manifest.py::GraphManifest`
- **Consumer relevance**: Studio skill details and graph serializer depend on registry entries matching body topology.
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_valid_v030_graph_uses_frontmatter_phase_registry_and_body_phase_dag]`

### LP-05: Physical phase directory ambiguity is rejected
- **Code facts**: `packages/graph-agent/src/graph_agent/core/loader.py::SkillLoader._load_phase_node`
- **Consumer relevance**: Studio validation must reject phase directories containing more than one node file.
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_phase_directory_with_multiple_node_files_uses_ambiguous_code]`

### LP-06: Agent body XML extracts inline examples for mention resolution
- **Code facts**: `packages/graph-agent/src/graph_agent/core/loader.py`, `packages/graph-agent/src/graph_agent/core/mentions.py`
- **Consumer relevance**: Studio preview and runtime prompt assembly need inline examples to remain reachable by `@example` mentions.
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_agent_body_extracts_inline_examples_for_mentions]`

## Compilation & Validation

### CV-01: Legacy schema roots are rejected by compile_skill
- **Code facts**: `packages/graph-agent/src/graph_agent/core/compiler.py::compile_skill`, `packages/graph-agent/src/graph_agent/core/loader.py::SkillLoader.compile_skill`
- **Consumer relevance**: Studio compile endpoints must not accept older single-file skill roots as V0.3.0 graphs.
- `[Covered By: packages/graph-agent/tests/core/test_compile_skill_v030_root_rejection.py::test_compile_skill_rejects_legacy_schema_20_file_path]`

### CV-02: Schema version must include the V0.3.0 marker
- **Code facts**: `packages/graph-agent/src/graph_agent/core/manifest.py::GraphManifest`, `packages/graph-agent/src/graph_agent/core/loader.py`
- **Consumer relevance**: Studio and vendored validators get a deterministic fatal result for mismatched graph versions.
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_schema_version_without_v_is_rejected]`

### CV-03: Duplicate phase registration fails compilation
- **Code facts**: `packages/graph-agent/src/graph_agent/core/loader.py::SkillLoader.compile_skill`
- **Consumer relevance**: Studio graph editing cannot silently overwrite duplicate phase ids.
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_duplicate_phase_registration_uses_dedicated_code]`

### CV-04: Graph cycles are rejected before execution
- **Code facts**: `packages/graph-agent/src/graph_agent/core/graph_builder.py`, `packages/graph-agent/src/graph_agent/core/loader.py`
- **Consumer relevance**: Studio validation prevents cyclic DAGs from reaching runtime.
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_graph_cycle_uses_dedicated_code]`

### CV-05: Subgraph input contracts are validated at compile time
- **Code facts**: `packages/graph-agent/src/graph_agent/core/graph_assembler.py::assemble_graph`, `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`
- **Consumer relevance**: Studio subgraph configuration catches parent/child IO mismatches before run start.
- `[Covered By: packages/graph-agent/tests/core/test_round14_skill_compilation_cutover.py::test_subgraph_io_input_mismatch_is_rejected_at_compile_time]`

### CV-06: compile_skill facade passes the injected skill resolver
- **Code facts**: `packages/graph-agent/src/graph_agent/core/compiler.py::compile_skill`, `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`
- **Consumer relevance**: Studio and scripts rely on dependency injection rather than global workspace lookup.
- `[Covered By: packages/graph-agent/tests/core/test_skill_resolver_protocol.py::test_compile_skill_facade_passes_skill_resolver]`

## Execution & Routing

### ER-01: run_skill rejects single-file roots with V0.3.0 root errors
- **Code facts**: `packages/graph-agent/src/graph_agent/core/runner.py::run_skill`
- **Consumer relevance**: Studio run endpoints return structured root-shape errors for invalid skill paths.
- `[Covered By: packages/graph-agent/tests/core/test_run_skill_entrypoint_root_shape.py::test_run_skill_single_markdown_file_returns_v030_root_error]`

### ER-02: PhaseNode execution returns updated runtime state
- **Code facts**: `packages/graph-agent/src/graph_agent/core/phase_node.py::PhaseNode`
- **Consumer relevance**: Internal phase dispatch depends on each node returning the next state snapshot.
- `[Covered By: packages/graph-agent/tests/core/test_phase_node.py::test_phase_node_execute_returns_updated_state]`

### ER-03: Non-LLM phases route to code nodes
- **Code facts**: `packages/graph-agent/src/graph_agent/core/phase_nodes/factory.py::build_llm_phase_node`
- **Consumer relevance**: Runtime dispatch keeps deterministic logic phases out of LLM execution.
- `[Covered By: packages/graph-agent/tests/core/test_phase_nodes_m6.py::test_build_llm_phase_node_routes_non_llm_phase_to_code_node]`

### ER-04: Validation nodes normalize legacy string errors
- **Code facts**: `packages/graph-agent/src/graph_agent/core/phase_nodes/validation_phase_node.py`
- **Consumer relevance**: Runtime validation remains compatible with validators that return string-shaped failures.
- `[Covered By: packages/graph-agent/tests/core/test_phase_nodes_m6.py::test_validation_node_coerces_legacy_str_errors]`

### ER-05: assemble_graph requires an injected resolver
- **Code facts**: `packages/graph-agent/src/graph_agent/core/graph_assembler.py::assemble_graph`
- **Consumer relevance**: Studio and runtime graph assembly fail fast when resolver wiring is absent.
- `[Covered By: packages/graph-agent/tests/core/test_delta_skill_resolution_red.py::test_delta1_assemble_graph_missing_resolver_raises_v3_code]`

### ER-06: Callback emission continues after callback failure
- **Code facts**: `packages/graph-agent/src/graph_agent/callbacks/emit.py::safe_emit_event`
- **Consumer relevance**: Studio run streaming remains resilient when one callback raises.
- `[Covered By: packages/graph-agent/tests/callbacks/test_emit.py::test_safe_emit_event_continues_after_callback_failure]`

## State & Blackboard

### SB-01: Blackboard reducer merges disjoint phase outputs
- **Code facts**: `packages/graph-agent/src/graph_agent/runtime/state.py::blackboard_data_merge`
- **Consumer relevance**: Runtime phase outputs accumulate without flattening into top-level state.
- `[Covered By: packages/graph-agent/tests/runtime/test_state_reducer.py::test_blackboard_data_merge_phase_outputs_disjoint_keys]`

### SB-02: State mapper rejects undeclared output keys
- **Code facts**: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py::StateMapper`
- **Consumer relevance**: Studio and runtime keep phase outputs inside declared IO contracts.
- `[Covered By: packages/graph-agent/tests/runtime/test_state_mapper.py::test_state_mapper_rejects_undeclared_output_keys]`

### SB-03: Phase wrapper maps declared inputs and outputs
- **Code facts**: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py::phase_wrapper`
- **Consumer relevance**: Internal execution wrappers bridge graph state and phase-local business payloads.
- `[Covered By: packages/graph-agent/tests/runtime/test_state_mapper.py::test_phase_wrapper_maps_input_and_output]`

### SB-04: Reference reader sandbox does not inherit parent blackboard
- **Code facts**: `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`, `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py`
- **Consumer relevance**: Builtin subagent runs keep parent state isolated from reader-only execution.
- `[Covered By: packages/graph-agent/tests/runtime/test_state_mapper.py::test_reader_sandbox_state_does_not_inherit_parent_blackboard]`

### SB-05: Cache round-trip preserves compiled subagents, tools, and phase tokens
- **Code facts**: `packages/graph-agent/src/graph_agent/core/cache.py`, `packages/graph-agent/src/graph_agent/core/loader.py::CompiledSkill`
- **Consumer relevance**: Studio predict and compile flows can reuse cached compilation artifacts without losing runtime metadata.
- `[Covered By: packages/graph-agent/tests/core/test_pr4_cache_roundtrip_red.py::test_pr4_cache_hit_preserves_subagents_tools_and_phase_tokens]`

### SB-06: IO manager resolves nested hoist paths
- **Code facts**: `packages/graph-agent/src/graph_agent/core/io_manager.py::IOManager`
- **Consumer relevance**: Runtime state mutation supports nested phase output wiring declared by graph IO specs.
- `[Covered By: packages/graph-agent/tests/core/test_io_manager.py::test_resolve_hoist_nested_path]`

## Observability & Errors

### OE-01: CallbackEvent union locks consumed event model variants
- **Code facts**: `packages/graph-agent/src/graph_agent/callbacks/events.py::CallbackEvent`
- **Consumer relevance**: Studio run history and gateway tracing deserialize the same discriminated callback event set.
- `[Covered By: packages/graph-agent/tests/test_public_api_contract.py::test_callback_event_union_contains_consumed_event_models]`

### OE-02: TracingCallback writes V0.3.0 typed events
- **Code facts**: `packages/graph-agent/src/graph_agent/callbacks/tracing.py::TracingCallback`
- **Consumer relevance**: Studio trace files and diagnostics consume typed JSONL event output.
- `[Covered By: packages/graph-agent/tests/callbacks/test_v030_trace_events.py::test_tracing_callback_writes_v030_typed_events]`

### OE-03: Error payloads autofill registry metadata
- **Code facts**: `packages/graph-agent/src/graph_agent/core/exceptions.py::ErrorPayload`, `packages/graph-agent/src/graph_agent/core/error_registry.py`
- **Consumer relevance**: Studio error responses include stable stage, severity, and registry metadata.
- `[Covered By: packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_payload_autofills_registry_metadata]`

### OE-04: Error registry matches the error-code spec key set
- **Code facts**: `packages/graph-agent/src/graph_agent/core/error_registry.py`
- **Consumer relevance**: Engine fatal and warning codes stay aligned with the frozen skill-spec error catalog.
- `[Covered By: packages/graph-agent/tests/core/test_error_payload_contract.py::test_error_registry_matches_error_code_spec_key_set]`

### OE-05: Trace save failures raise TraceWriteError
- **Code facts**: `packages/graph-agent/src/graph_agent/core/harness.py`, `packages/graph-agent/src/graph_agent/core/exceptions.py::TraceWriteError`
- **Consumer relevance**: Studio can distinguish trace persistence failures from business execution failures.
- `[Covered By: packages/graph-agent/tests/core/test_harness_state_machine_resources.py::test_trace_save_failure_raises_trace_write_error]`

### OE-06: LLM usage metrics accumulate by provider
- **Code facts**: `packages/graph-agent/src/graph_agent/models/llm_client_manager.py::LLMClientManager.record_usage`
- **Consumer relevance**: Gateway and Studio provider diagnostics rely on stable usage accounting.
- `[Covered By: packages/graph-agent/tests/models/test_llm_client_manager.py::test_record_usage_accumulates]`
