# Tasks: PR F2 Standard Error Payload

## Audit Conclusions

### 1. Coarse code replacement feasibility

Coarse code elimination is feasible, but not by a one-to-one helper rewrite.

Current coarse emitters:

- `packages/graph-agent/src/graph_agent/core/loader.py:264` `_fatal(...)` emits `[F-v3-route]`.
- `packages/graph-agent/src/graph_agent/core/loader.py:268` `_io_fatal(...)` emits `[F-v3-io]`.
- `packages/graph-agent/src/graph_agent/core/loader.py:272` `_graph_fatal(...)` emits `[F-v3-graph]`.
- `packages/graph-agent/src/graph_agent/core/loader.py:276` `_actions_fatal(...)` emits `[F-v3-actions]`.
- `packages/graph-agent/src/graph_agent/core/loader.py:286` `_purity_fatal(...)` emits `[F-v3-purity]`.
- `packages/graph-agent/src/graph_agent/core/parser.py:173` `_fatal(...)` emits `[F-v3-route]`.
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1005` `_graph_fatal(...)` emits `[F-v3-graph]`.

The existing helper names are implementation categories, not spec categories. For example, `loader.py:_fatal` is used for missing root `GRAPH.md`, nested `GRAPH.md`, unsupported document filenames, subgraph IO mismatch, phase validation failures, missing agent role/goal, mention failures, and other unrelated defects. `_actions_fatal` covers tool placement, action signature, duplicate actions, import failures, and some purity violations. Therefore a helper-only mapping would be lossy.

Engineering approach:

- Replace helper signatures with explicit code-aware helpers, e.g. `_skill_load_fatal(path, line, code, message, *, phase_id=None, field_path=None)`.
- At each call site, pass the 11-spec fine code directly and remove embedded `[F-v3-*]` text from message strings.
- Split helpers only where it removes ambiguity, e.g. resource path reads should accept `code`/`payload` explicitly because references and examples share the same file reader but require different codes.
- Keep message text human-readable and derive machine contract from `ErrorPayload.code`, not by parsing message.
- For existing behavior that has no clear 11-spec code, do not invent an implementation-only code in source. Either map to the closest existing spec code with a documented test case, or pause the implementation and report the missing spec coverage.

Known high-risk mapping spots:

- `loader.py:292-308` root shape errors should map to graph physical/layout codes such as `[F-v3-graph-root-missing]`, `[F-v3-graph-phases-dir-missing]`, and `[F-v3-graph-io-physical-file-deprecated]`.
- `loader.py:365-377`, `576-614`, `630-650` action/tool placement, duplicate ids, import failures, and signature errors cannot be inferred from `[F-v3-actions]`; each call site must choose from `logic-action-*` or `agent-tool-*` codes. If the behavior is signature/import specific and no existing code is defensible, pause.
- `loader.py:588-600` purity violations currently use `[F-v3-actions]` or `[F-v3-purity]`; `[F-v3-purity]` is not in 11-spec. This needs an explicit mapping decision during implementation.
- `parser.py:173`, `228`, `237` parser route failures are not all graph topology failures; they need call-site codes rather than a generic parser code.
- `graph_assembler.py:348` and `1006` use coarse `[F-v3-graph]` outside loader; these must be converted too.

### 2. Registry sync risk

`error_registry.py` should be checked in as a static registry for runtime reliability, but drift must be caught by tests.

Most pragmatic sync guard:

- Add `packages/graph-agent/src/graph_agent/core/error_registry.py` with typed static metadata for all 87 codes currently listed in `docs/engine/skill-spec/11-error-code-spec.md`.
- Add a test that parses `docs/engine/skill-spec/11-error-code-spec.md` with a narrow regex for `\[F-v3-[a-z0-9-]+\]` and asserts exact key-set equality with the registry.
- Add tests for representative metadata autofill: level, stage, and doc_link for compile-time, runtime, assembly-time, FATAL, and WARN examples.
- Keep doc parsing in tests only. Runtime should not parse markdown.

This catches added/removed spec codes without adding markdown parsing to production code. Stage and doc links should be explicit in the registry; level is not represented as a table column in the spec, so registry level choices need test coverage for known WARN/FATAL examples.

### 3. `SkillCompilationError` payload mechanism

Treat `SkillCompilationError` location-field migration as A-class charter work, not B-class PM work. The mechanism should be single-source payload delegation, not long-term double-write.

Chosen mechanism:

- `SkillCompilationError.__init__` accepts `payload: ErrorPayload | None`.
- If callers pass legacy `skill_path`, `line`, `field_path`, or `suggestion`, the constructor builds or enriches one `ErrorPayload` and stores `source_path`/`field_path` there.
- Keep legacy attributes as read-only compatibility mirrors during this PR only if tests/public imports require them, but the canonical data source is `exc.payload`.
- All new/changed call sites must assert and consume `exc.payload`, not `exc.skill_path` or regex text.

Reason: this gives external boundaries one JSON contract while reducing repeated state. Long-term double-write would preserve the inconsistency PR F is meant to remove.

## Implementation Tasks

### 1. Tests-first red suite for the payload contract

- File: `packages/graph-agent/tests/core/test_error_payload_contract.py` [NEW]
- WHAT: Add failing tests for Req1-Req5 before implementation:
  - `ErrorPayload(code="[F-v3-graph-phase-cycle]", message="cycle")` autofills `level`, `stage`, and `doc_link`.
  - unknown code is rejected.
  - every code parsed from `docs/engine/skill-spec/11-error-code-spec.md` exists in `error_registry.py`.
  - the three multi-stage codes preserve their exact stage lists, not a collapsed single value: `[F-v3-resource-reference-path-invalid]` -> `["编译期", "运行期"]`, `[F-v3-resource-example-path-invalid]` -> `["编译期", "运行期"]`, `[F-v3-skill-not-registered]` -> `["编译期", "装配期"]`.
  - `GraphAgentError` and concrete subclasses expose `exc.payload.model_dump()` with `code`, `level`, `stage`, `message`, `doc_link`.
  - `SkillCompilationError(skill_path=..., field_path=...)` exposes `payload.source_path` and `payload.field_path`.
  - representative loader/runtime/tool failures assert `exc_info.value.payload.code`, not `match=`.
- Depends on: none.
- Risk: intentionally red because `ErrorPayload` and `error_registry.py` do not exist yet.
- [BREAKING][A] Migration path: tests document the new exception contract before changing source.

### 2. Add `error_registry.py` static metadata

- File: `packages/graph-agent/src/graph_agent/core/error_registry.py` [NEW]
- WHAT: Define `ErrorCodeMetadata` and `ERROR_REGISTRY` for all 87 11-spec codes, with `code`, `level`, `stage`, `doc_link`, and optional reason/fix text if useful. Use `stage: tuple[str, ...]` in metadata so single-stage codes store one item and the three multi-stage spec rows store two items exactly: `[F-v3-resource-reference-path-invalid]` = `("编译期", "运行期")`, `[F-v3-resource-example-path-invalid]` = `("编译期", "运行期")`, `[F-v3-skill-not-registered]` = `("编译期", "装配期")`.
- Depends on: Task 1.
- Risk: manual transcription drift. Mitigate with the spec key-set test from Task 1 and explicit stage assertions for the three multi-stage codes.
- Doc link rule: `doc_link` for all 87 codes comes from the 11-spec rows, including the four a2-backfilled validator/runtime rows; no registry entry may have an empty doc_link.
- Acceptance: `rg -o "\[F-v3-[a-z0-9-]+\]" docs/engine/skill-spec/11-error-code-spec.md | sort -u` equals registry keys exactly.

### 3. Add `ErrorPayload` model and exports

- File: `packages/graph-agent/src/graph_agent/core/exceptions.py:13`
- WHAT: Add `ErrorPayload(BaseModel)` near the exception base, using registry lookup to autofill `level`, `stage`, and `doc_link` when only `code` and `message` are supplied. Include optional `skill_id`, `phase_id`, `field_path`, `source_path`.
- Depends on: Task 2.
- Risk: Pydantic import in exception module must not create circular imports. Keep registry independent from exception classes.
- Acceptance: Task 1 model tests pass.

### 4. Refactor `GraphAgentError` base constructor

- File: `packages/graph-agent/src/graph_agent/core/exceptions.py:13`
- WHAT: Change signature to `__init__(self, message: str, *, payload: ErrorPayload | None = None, context: dict[str, Any] | None = None)`. Store `self.payload`. If no payload is supplied, keep legacy behavior but do not invent a code.
- Depends on: Task 3.
- Risk: existing callers without codes still need to work while migration proceeds.
- [BREAKING][A] Migration path: source call sites move to payload in later tasks; compatibility permits incremental conversion.

### 5. Convert `SkillCompilationError` to payload-source location data

- File: `packages/graph-agent/src/graph_agent/core/exceptions.py:200`
- WHAT: Make `payload` canonical. Convert `skill_path` to `payload.source_path`, `field_path` to `payload.field_path`, and include line in message or context until a dedicated payload field exists.
- Depends on: Task 4.
- Risk: code may still inspect legacy attributes. Keep compatibility mirrors only as delegated values from payload.
- [BREAKING][A] Migration path: assertions and downstream consumers use `exc.payload.*`.

### 6. Introduce code-aware raise helpers

- Files:
  - `packages/graph-agent/src/graph_agent/core/loader.py:264`
  - `packages/graph-agent/src/graph_agent/core/parser.py:173`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:348`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1005`
- WHAT: Replace coarse helper implementations with explicit `code` parameters and `ErrorPayload` construction. Remove logic that embeds a coarse prefix in the message. Explicitly convert `graph_assembler.py:348` from bare `RuntimeError("[F-v3-graph] SKILL phase requires chat_model")` to an appropriate `GraphAgentError` subclass carrying `ErrorPayload`; this site requires both code replacement and exception type replacement.
- Depends on: Task 4.
- Risk: many call sites currently pass messages that already contain fine codes. Normalize to one code source.
- Acceptance: no helper emits `[F-v3-route]`, `[F-v3-io]`, `[F-v3-graph]`, `[F-v3-actions]`, or `[F-v3-purity]`.

### 7. Migrate loader/parser coarse call sites to fine codes

- Files:
  - `packages/graph-agent/src/graph_agent/core/loader.py:248-1366`
  - `packages/graph-agent/src/graph_agent/core/parser.py:228-237`
- WHAT: Update every call to `_fatal`, `_io_fatal`, `_graph_fatal`, `_actions_fatal`, `_purity_fatal`, and direct `SkillLoadError(f"[F-v3-*] ...")` to pass a 11-spec fine code payload.
- Depends on: Task 6.
- Risk: ambiguous action/purity/parser cases. If no existing 11-spec code is defensible, stop and report the exact call site instead of creating a new source-only code.
- [BREAKING][A] Migration path: tests that expected coarse prefixes migrate to structured fine-code assertions.

### 8. Migrate runtime/tool direct string raises

- Files:
  - `packages/graph-agent/src/graph_agent/runtime/state.py`
  - `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
  - `packages/graph-agent/src/graph_agent/tools/builtin/read_reference.py`
  - `packages/graph-agent/src/graph_agent/tools/builtin/read_example.py`
  - `packages/graph-agent/src/graph_agent/core/actions.py`
  - `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`
- WHAT: Replace direct `GraphAgentFatalError("[F-v3-*] ...")` and resolver `code=` storage with `payload=ErrorPayload(...)`.
- Depends on: Task 4.
- Risk: `SkillResolutionError.code` may be used by callers; keep delegated `.code` property to `payload.code` during migration.

### 9. Collapse `error_code=` kwargs into payload/code objects

- Files:
  - `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:121-154, 898-926`
  - `packages/graph-agent/src/graph_agent/core/builtin_subagents/reference_reader.py:57`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py:610,693`
  - `packages/graph-agent/src/graph_agent/tools/builtin/read_reference.py:27,31`
  - `packages/graph-agent/src/graph_agent/tools/builtin/read_example.py:27`
- WHAT: Replace scattered `error_code=` kwargs with `ErrorPayload` or a small `ErrorPayload`-carrying result type. For non-exception result objects, keep public `error_code` as a compatibility property backed by `payload.code` if needed.
- Depends on: Task 3.
- Risk: middleware tests currently assert `result.error_code`; migrate to `result.payload.code` where the result shape is part of PR F.
- [BREAKING][A] Migration path: one structured payload replaces string-only result fields.

### 10. Migrate reference-reader warnings and fallback strings

- File: `packages/graph-agent/src/graph_agent/core/graph_assembler.py:523-605`
- WHAT: Keep human fallback markdown if required, but introduce structured payload for `[F-v3-reference-reader-failed]` warnings where they cross boundaries. Do not rely on string containment for control flow where exception payload is available.
- Depends on: Task 9.
- Risk: some warning paths are intentionally non-fatal. Preserve WARN semantics in registry and tests.

### 11. Migrate all F-v3 test assertions

- Files: all 24 files under `packages/graph-agent/tests` that currently contain `F-v3-`.
- WHAT: Replace 41 `pytest.raises(..., match=.*F-v3-)` sites with `as exc_info` and `exc_info.value.payload.code == ...`. Migrate other coarse-string assertions to structured payload checks where an exception is involved.
- Depends on: Tasks 6-10.
- Risk: tests that intentionally inspect user-facing fallback markdown may still assert text, but exception code assertions must be payload-based.
- Acceptance counts from audit:
  - `rg -n "match=.*F-v3-" packages/graph-agent/tests | wc -l` -> `0`
  - `rg -n "\[F-v3-(route|io|graph|actions|purity)\]" packages/graph-agent/tests packages/graph-agent/src/graph_agent | wc -l` -> `0`

### 12. Remove coarse code source remnants

- Files:
  - `packages/graph-agent/src/graph_agent/core/loader.py`
  - `packages/graph-agent/src/graph_agent/core/parser.py`
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- WHAT: Delete coarse helpers or rename them after all call sites pass fine codes. Ensure no `[F-v3-route]`, `[F-v3-io]`, `[F-v3-graph]`, `[F-v3-actions]`, `[F-v3-purity]` literals remain in engine source/tests.
- Depends on: Task 11.
- Risk: `graph` is both a valid domain and the removed coarse literal. The grep must target exact `[F-v3-graph]`, not `[F-v3-graph-*]`.

### 13. Final verification

- Commands:
  - `pytest packages/graph-agent/tests/ -q`
  - `rg -n "\[F-v3-(route|io|graph|actions|purity)\]" packages/graph-agent/src/graph_agent packages/graph-agent/tests`
  - `rg -n "match=.*F-v3-" packages/graph-agent/tests`
  - `rg -n "error_code=" packages/graph-agent/src/graph_agent`
  - registry/spec key-set test from Task 1
- Expected:
  - Full graph-agent test suite green.
  - 11-spec and registry code sets match.
  - coarse code literals have 0 engine source/test occurrences.
  - `error_code=` kwargs are gone or explicitly documented as non-error compatibility shims backed by payload.

## Scope Notes

- Studio `[F-v21-*]` remnants are out of PR F engine scope and should not be touched here:
  - `apps/studio/backend/app/services/skills.py:1450`
  - `apps/studio/frontend/src/components/welcome/WelcomePage.test.tsx:207`
- This task list intentionally does not modify source or tests. It defines the implementation sequence for the next PR step.
