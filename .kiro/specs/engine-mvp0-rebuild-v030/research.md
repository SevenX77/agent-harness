# Research: Engine MVP0 Rebuild V0.3.0 Cutover

## 1. Research method

This spec does not duplicate detailed baseline analysis. It indexes the source documents that already describe current behavior, target behavior, and finalized decisions.

Primary baseline docs:

- `docs/engine/skill-compilation/baseline.md`
- `docs/engine/state-and-io-contract/baseline.md`
- `docs/engine/execution-runtime/baseline.md`
- `docs/engine/tracing-and-observability/baseline.md`
- `docs/engine/skill-resolution/baseline.md`
- `docs/engine/graph-agent-gateway/baseline.md`

Primary alignment docs:

- `docs/engine/skill-compilation/mvp0-alignment.md`
- `docs/engine/state-and-io-contract/mvp0-alignment.md`
- `docs/engine/execution-runtime/mvp0-alignment.md`
- `docs/engine/tracing-and-observability/mvp0-alignment.md`
- `docs/engine/skill-resolution/mvp0-alignment.md`
- `docs/engine/graph-agent-gateway/mvp0-alignment.md`

Normative field specs:

- `docs/engine/skill-spec/01-physical-layout.md`
- `docs/engine/skill-spec/02-graph-md-spec.md`
- `docs/engine/skill-spec/03-logic-md-spec.md`
- `docs/engine/skill-spec/04-subgraph-md-spec.md`
- `docs/engine/skill-spec/05-agent-md-spec.md`
- `docs/engine/skill-spec/06-cognitive-template-spec.md`
- `docs/engine/skill-spec/07-mention-syntax-spec.md`
- `docs/engine/skill-spec/08-resource-mechanisms-spec.md`
- `docs/engine/skill-spec/09-builtin-modules-spec.md`
- `docs/engine/skill-spec/10-skill-resolver-protocol-spec.md`
- `docs/engine/skill-spec/11-error-code-spec.md`
- `docs/engine/skill-spec/12-compile-runtime-flow-spec.md`

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
- ModelResolver-like injection for LLM roles
- StateMapper wrapper for all phase kinds

Research conclusion: execution-runtime should consume compiled AST only; no runtime Markdown reparsing.

### Tracing

Current trace/callback coverage is incomplete for V0.3.0 needs. Alignment requires explicit event kinds for ambiguity feedback and builtin reference reader fallback.

Research conclusion: tracing payload should be emitted at wrapper/tool/model boundaries and use already-filtered state slices.

## 3. Finalized decision research

### T11 scope

Cross-verification concluded that “V2.1 compatibility code” is ambiguous. Current graph skill main path is not cleanup target. Cleanup target is legacy schema 2.0 residue: old parser stubs, legacy harness state, context_mapping, and docs that advertise dead paths.

### Compiler line-location test

`test_compiler_line_locations.py` failure is tied to old AST location extraction. It should be skipped until V0.3.0 parser cutover rewrites YAML/frontmatter source spans.

### ContextResolver

`ContextResolver` is not part of the V0.3.0 route. `assemble_graph` and graph skill runtime use schema-driven state slicing. Maintaining context_mapping would create a second mental model with no active entry point.

### Docs frontmatter

Docs metadata is a separate Kiro spec. It applies to docs prose, not graph skill markdown.

## 4. Open items

The following were intentionally not settled here:

- PR strategy conflict involving Studio #50 and engine cutover.
- Q2.1 rename scope E all-change decision.

They require PM direction before task updates.
