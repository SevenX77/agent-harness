# Research: Engine MVP0 Rebuild V0.3.0 Cutover

## 1. Research method

This spec does not duplicate detailed baseline analysis. It indexes the source documents that already describe current behavior, target behavior, and finalized decisions.

Primary baseline docs:

- `docs/engine/mvp0/skill-compilation/baseline.md`
- `docs/engine/mvp0/state-and-io-contract/baseline.md`
- `docs/engine/mvp0/execution-runtime/baseline.md`
- `docs/engine/mvp0/tracing-and-observability/baseline.md`
- `docs/engine/mvp0/skill-resolution/baseline.md`
- `docs/graph-agent-gateway/mvp0/baseline.md`

Primary alignment docs:

- `docs/engine/mvp0/skill-compilation/mvp0-alignment.md`
- `docs/engine/mvp0/state-and-io-contract/mvp0-alignment.md`
- `docs/engine/mvp0/execution-runtime/mvp0-alignment.md`
- `docs/engine/mvp0/tracing-and-observability/mvp0-alignment.md`
- `docs/engine/mvp0/skill-resolution/mvp0-alignment.md`
- `docs/graph-agent-gateway/mvp0/mvp0-alignment.md`

Normative field specs:

- `docs/engine/mvp0/skill-spec/01-physical-layout.md`
- `docs/engine/mvp0/skill-spec/02-graph-md-spec.md`
- `docs/engine/mvp0/skill-spec/03-logic-md-spec.md`
- `docs/engine/mvp0/skill-spec/04-subgraph-md-spec.md`
- `docs/engine/mvp0/skill-spec/05-agent-md-spec.md`
- `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md`
- `docs/engine/mvp0/skill-spec/07-mention-syntax-spec.md`
- `docs/engine/mvp0/skill-spec/08-resource-mechanisms-spec.md`
- `docs/engine/mvp0/skill-spec/09-builtin-modules-spec.md`
- `docs/engine/mvp0/skill-spec/10-skill-resolver-protocol-spec.md`
- `docs/engine/mvp0/skill-spec/11-error-code-spec.md`
- `docs/engine/mvp0/skill-spec/12-compile-runtime-flow-spec.md`

## 2. Current implementation findings

### Skill compilation

Current compiler still contains V2.1-era names and physical IO compatibility. Alignment docs require moving the truth source to V0.3.0 inline `GRAPH.md io.inputs` / `io.outputs`, Agent AST, phase-level IO, and `target_skill` resolver references.

Research conclusion: compilation must be the first cutover layer because runtime cannot enforce state or child graph isolation until AST fields are reliable.

### State and IO

Current state model uses a shared `BlackboardState.data` dict and `shallow_dict_merge`. Alignment requires three normalized data areas:

- `data.inputs`
- `data.phase_outputs`
- `data.scratch`

Research conclusion: T3 reducer and T5 namespace shape must be implemented together. Namespacing alone does not define nested merge semantics.

### Runtime execution

Current runtime path still has mixed concerns: prompt assembly, finish_task, child graph invocation, subagent tools, resolver behavior, and reference tooling. Alignment requires explicit DI boundaries:

- `SkillResolverProtocol`
- **[Completed via PR α]** `ModelResolverProtocol` injection for LLM roles (Gateway independent package and explicit DI via `run_skill`).
- StateMapper wrapper for all phase kinds

Research conclusion: execution-runtime should consume compiled AST only; no runtime Markdown reparsing.

### Tracing

Current trace/callback coverage is incomplete for V0.3.0 needs. Alignment requires explicit event kinds for ambiguity feedback and builtin reference reader fallback.

Research conclusion: tracing payload should be emitted at wrapper/tool/model boundaries and use already-filtered state slices.

## 3. Finalized decision research

### T11 scope

Cross-verification concluded that PM's 2026-05-23 principle removes the ambiguity: V2.1 main path (`_run_v21_skill_dict` and related compiler / graph assembler / runtime compatibility) is part of the V0.3.0 hard-cut cleanup scope. Cleanup also covers schema 2.0 residue, old parser stubs, legacy harness state, context_mapping, fixtures, and docs that advertise dead paths.

### Compiler line-location test

`test_compiler_line_locations.py` is tied to old V2.1 AST location extraction. It must be deleted during cutover, not skipped. V0.3.0 YAML/frontmatter source-span tests should be added with the V0.3.0 parser implementation.

### ContextResolver

`ContextResolver` is not part of the V0.3.0 route. `assemble_graph` and graph skill runtime use schema-driven state slicing. Maintaining context_mapping would create a second mental model with no active entry point.

### Docs frontmatter

Docs metadata is not part of the engine V0.3.0 cutover. The separate `.kiro/specs/docs-frontmatter-schema/` pseudo-spec is removed from this workstream.

## 4. Open items

Open Items: none. All audit items were finalized on 2026-05-23.

## 5. Finalized 2026-05-23

- T11 scope: hard cut V2.1 main path, codemod, schema 2.0 parser stub, V2.1 fixtures, context_mapping, and `python_callable`; no backward compatibility.
- #14 line-location test: delete `packages/graph-agent/tests/core/test_compiler_line_locations.py`; no `@pytest.mark.skip` defer.
- #28 context_mapping: delete full chain, including `ContextResolver`, harness entry points, validators, builtin md-patch / md_to_json dependency path, fixtures, and docs references.
- #29 docs frontmatter: remove `.kiro/specs/docs-frontmatter-schema/`; it is not an engine MVP0 blocker.
- #2 PR strategy: choose single atomic PR for engine src/tests plus Studio backend resolver/import, Studio frontend Assets Panel SUBGRAPH category, and Tauri folder picker. Splitting would require fallback or produce broken main, both against PM principle.
- Q2.1: do not expand body tags and do not rename `python_callable`; remove `python_callable` and use LOGIC `actions:` from `docs/engine/mvp0/skill-spec/03-logic-md-spec.md`.
- 4580dde cleanup docs: rewrite stale “protect V2.1 main path”, “keep codemod”, “defer line-location”, “split PR”, and “docs-frontmatter-schema” conclusions.
