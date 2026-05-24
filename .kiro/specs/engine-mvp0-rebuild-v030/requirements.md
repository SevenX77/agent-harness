# Requirements: Engine MVP0 Rebuild V0.3.0 Cutover

## 1. Purpose

V0.3.0 cutover turns the current graph-agent engine into a field-level graph skill runtime. The work replaces ambiguous V2.1-era contracts with explicit schemas for skill resolution, compilation, state / IO, runtime execution, tracing, and error payloads.

The cutover implementation lands as one atomic PR across `packages/graph-agent/src/`, `packages/graph-agent/tests/`, and the Studio backend/frontend/Tauri surfaces required by the V0.3.0 `SkillResolverProtocol` contract. Studio changes are limited to resolver injection, import flow, and Assets Panel SUBGRAPH visibility required by `docs/studio/V0.3.0-NEW-REQUIREMENTS--DO-NOT-DELETE-DURING-CLEANUP.md`.

## 2. Source decisions

This requirements document consolidates:

- `docs/engine/MVP0-PROGRESS-2026-05-21.md` 18 PM decision questions.
- `docs/engine/skill-spec/*.md` field-level V0.3.0 schema.
- `docs/engine/{skill-compilation,state-and-io-contract,execution-runtime,tracing-and-observability}/mvp0-alignment.md`.
- Finalized cleanup decisions from 2026-05-23: hard-cut T11 scope, direct deletion of the old compiler line-location test, context_mapping deletion, docs-frontmatter-schema removal, single-PR engine + Studio cutover, and python_callable cleanup.

## 3. Functional requirements

### R1. Skill identity and resolver

Engine MUST define `SkillResolverProtocol.resolve_skill(skill_id: str) -> Path`; the field-level contract is `docs/engine/skill-spec/10-skill-resolver-protocol-spec.md:24-35`.

Required behavior:

- reject invalid skill ids
- fail unregistered skills with `[F-v3-skill-not-registered]`
- fail invalid paths with `[F-v3-resolver-path-invalid]`
- require resolver injection when compiling / running graphs that reference child skills; missing resolver for child graph usage is FATAL, per `docs/engine/skill-spec/10-skill-resolver-protocol-spec.md:63-75`

### R2. V0.3.0 graph skill schema

Compiler MUST treat `GRAPH.md` as the graph root and parse:

- graph metadata
- inline root `io.inputs`
- inline root `io.outputs`
- `phases:` YAML list
- DAG dependencies

Compiler MUST reject physical `io/inputs.json`, physical `io/outputs.json`, `io_inputs_ref`, and `io_outputs_ref` with `[F-v3-graph-io-physical-file-deprecated]`, per `docs/engine/skill-spec/01-physical-layout.md:94-102` and `docs/engine/skill-spec/02-graph-md-spec.md:75-78`.

### R3. Phase node schema

Every phase MUST be one of:

- `agent`, backed by `SKILL.md`
- `logic`, backed by `LOGIC.md`
- `subgraph`, backed by `SUBGRAPH.md`

Each phase MUST declare `io.inputs` and `io.outputs` as JSON Schema object contracts; use the concrete field tables in `docs/engine/skill-spec/03-logic-md-spec.md:33-40`, `04-subgraph-md-spec.md`, and `05-agent-md-spec.md:11-18`.

### R4. Agent AST and cognitive template

Agent phases MUST parse body XML into the exact top-level tag allowlist in `docs/engine/skill-spec/05-agent-md-spec.md:41-52`:

- `role`
- `goal`
- repeated `step`
- repeated `protocol`

*Note: Exit contract is NOT written in SKILL.md. It is hardcoded in the cognitive template and automatically injected from the phase `io.outputs` schema.*

Runtime MUST render these fields into the V0.3.0 cognitive template and place `io.outputs` schema at the end of the exit contract.

### R5. Static mention and resource validation

Compiler MUST validate `@subagent`, `@subgraph`, `@tool`, `@protocol`, `@step`, `@reference`, and `@example` mentions against the current Agent registry and body fields.

Reference and example registries MUST be validated at compile time.

### R6. State and IO isolation

Runtime MUST use `StateMapper` / Phase Wrapper to:

- filter root runtime inputs by root `io.inputs`
- build phase input from declared `phase.io.inputs`
- validate phase output against declared `phase.io.outputs`
- store phase outputs in normalized `data.phase_outputs[phase_id]`
- keep `data.inputs`, `data.phase_outputs`, and `data.scratch` separate

### R7. Smart reducer

Runtime MUST implement reducer semantics that work with the normalized state shape:

- same super-step writes to the same effective key are conflicts
- sequential overwrite is allowed only where explicitly specified
- nested `phase_outputs[phase_id]` merge must not collapse into a single top-level `phase_outputs` conflict

T3 and T5 are both required: T5 defines key space; T3 defines merge semantics over that key space.

### R8. Child graph isolation

Subagent and SUBGRAPH child runs MUST:

- resolve target skill through `SkillResolverProtocol`, matching `docs/engine/skill-spec/04-subgraph-md-spec.md` and `docs/engine/skill-spec/10-skill-resolver-protocol-spec.md:47-61`
- start from explicit input filtered by target root `io.inputs`
- not inherit parent `data`
- start with empty `messages`
- deep copy allowed control `flow`
- write `subagent_depth + 1` into child flow

### R9. Builtin reference reader and tools

Runtime MUST support:

- assembly-time builtin reference reader sandbox
- WARN fallback `[F-v3-reference-reader-failed]`
- runtime `read_reference`
- runtime `read_example`

Reference reader failures MUST NOT block normal Agent execution unless the reference path itself is compile-invalid.

### R10. Tracing and observability

Runtime MUST emit structured events for:

- node start/end
- LLM call start/end
- tool call start/end
- user subagent enter/exit
- builtin subagent enter/exit/fallback
- ambiguity logged
- exception

Trace payloads MUST use StateMapper-filtered data, not full parent blackboards.

### R11. Error codes

Engine MUST remove unintended `[F-v21-*]` errors from active src/tests and expose `[F-v3-*]` codes with structured metadata.

### R12. Schema cleanup

Cutover MUST delete legacy V2.1 / schema 2.0 artifacts. Quarantine is not allowed for active src/tests because PM's 2026-05-23 principle is hard cutover with no backward compatibility.

- V2.1 main path including `_run_v21_skill_dict()` and dispatch references
- `codemod/v21_migrator.py`
- `parse_skill_file()` schema 2.0 stub and dead dependencies
- `GraphAgentHarness` legacy schema 2.0 path
- `BusinessData` / `WorkflowState` legacy runtime path
- callbacks tied only to legacy harness
- `ContextResolver` and context_mapping docs
- V2.1 fixtures, old line-location tests, and `python_callable` surfaces

## 4. Non-goals

- No Studio backend/frontend implementation outside the resolver/import/Assets Panel/Tauri surfaces required for the single atomic V0.3.0 cutover PR.
- No new graph skill fixture frontmatter outside the V0.3.0 schema.
- No context_mapping compatibility mode.

## 5. Acceptance criteria

- `pytest packages/graph-agent/tests/` passes after deleting `packages/graph-agent/tests/core/test_compiler_line_locations.py`; no skip/defer is allowed for the old V2.1 line-location test.
- `ruff check packages/graph-agent/src packages/graph-agent/tests` passes.
- `mypy packages/graph-agent/src` passes in project dependency environment.
- No unintended `[F-v21-*]` strings in active src/tests.
- New tests cover resolver, compilation schema, StateMapper, child graph isolation, builtin reader fallback, and trace events.
