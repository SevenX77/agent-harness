# Requirements Document

## Introduction

Studio authors can build a skill graph in which a phase node ends up with **no
input or no output**. Today this produces no diagnostic, so a structurally broken
graph looks valid until it fails later. We want the **engine** to emit a lint
diagnostic for such nodes, and that diagnostic to surface on the node (canvas
badge) and on `GRAPH.md` (inline lint marker), reusing the existing lint pipeline.

**Authoritative-source constraint (evidence-first 铁律).** The lint logic lives in
the engine — the frontend never invents diagnostics ("Source of truth stays the
engine lint payload", `apps/studio/frontend/src/components/studio/lint-monaco-markers.ts:12`).
Engine diagnostics are emitted by the loader/compiler as `CompileIssue` records
with `[F-v3-*]` codes (`packages/graph-agent/src/graph_agent/core/loader.py`). This
is therefore an **engine change** under `packages/graph-agent`, which per AGENTS.md
KEEP-MAIN is allowed only when the change is explicitly scoped to the engine — it
is here — and must follow TDD (failing test first) and align to the MVP1 design,
not to current code.

### Precise definition — resolve in design.md against the MVP1 design source

"A node has no input or output" has two candidate readings. **design.md resolves
which (or both) by aligning to the MVP1 design source** (engine design body
`docs/engine/mvp1/` and `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/`),
quoting the governing design text — this is an evidence-first decision, not a
preference call. The requirement below is stated at the intent level so it holds
either way; the design phase pins the exact rule.

- **(A) Graph connectivity:** a phase node with **no incoming edge** (nothing flows
  in) and/or **no outgoing edge** (nothing flows out) in the compiled DAG — a
  dangling/orphan node. Global INPUT/OUTPUT sentinels exempt by definition. The
  "show on `GRAPH.md`" requirement fits this reading, since topology/edges live in
  `GRAPH.md`.
- **(B) Declared IO schema:** a node whose `io.inputs` and/or `io.outputs` declares
  **no properties** (the empty `properties: {}` case in a phase file). This reading
  is primarily a phase-file (`SKILL.md`/`LOGIC.md`) concern.

Acceptance criteria 1.1–1.3 below are phrased for **(A)**; if design picks **(B)**
(or both), restate them in terms of the node's `io` schema emptiness. Either way,
Requirement 2 (surface on node + `GRAPH.md`) and Requirements 3–4 hold unchanged.

## Requirements

### Requirement 1: Engine emits a lint diagnostic for a node missing input or output

**Objective:** As a skill author, I want the engine to flag a phase node that has
no input or no output, so that I catch a structurally broken graph at edit time
instead of at run time.

#### Acceptance Criteria
1. When a skill is compiled/linted and a non-sentinel phase node has **no incoming
   edge**, the engine shall emit one diagnostic for that node indicating it has no
   input.
2. When a skill is compiled/linted and a non-sentinel phase node has **no outgoing
   edge**, the engine shall emit one diagnostic for that node indicating it has no
   output.
3. When a node is missing both input and output, the engine shall emit a clear
   diagnostic for each missing side (or one combined diagnostic) — the exact
   shape to match existing `[F-v3-*]` conventions, decided in design.
4. The diagnostic shall carry a stable `[F-v3-*]`-style code, a human-readable
   message naming the node and the missing side, and a `location` consistent with
   how other node-scoped diagnostics in `loader.py` are located (so it maps onto a
   node id and onto `GRAPH.md`).
5. Where a skill graph is fully connected (every phase has at least one input and
   one output), the engine shall emit no such diagnostic.

### Requirement 2: Diagnostic surfaces on the node and on GRAPH.md

**Objective:** As a skill author, I want the missing-IO error shown on the node and
on `GRAPH.md`, so that I can see and fix it where I work.

#### Acceptance Criteria
1. When the engine emits the missing-IO diagnostic, the Studio node badge shall
   display the error for that node, via the existing
   `compileErrorsByNodeId`/node-error projection (no new frontend diagnostic
   invention).
2. When the diagnostic carries a `GRAPH.md` location, the realtime-lint markers
   shall render it inline on `GRAPH.md` via the existing
   `applyLintMarkers`/`lintErrorsForFile` pipeline.
3. Where the diagnostic is line-less, it shall still appear in the file-level
   diagnostics surface (consistent with current line-less handling).

### Requirement 3: Scope, exemptions, and severity

**Objective:** As a skill author, I do not want false positives on nodes that are
legitimately a source or a sink, so that the lint stays trustworthy.

#### Acceptance Criteria
1. The global INPUT and OUTPUT sentinel nodes shall be exempt from this rule.
2. The rule shall behave correctly for subgraph phase nodes and for nodes inside a
   drilled child graph (define expected behavior against the MVP1 subgraph IO
   contract during design).
3. The diagnostic severity (error vs warning) shall match the MVP1 design intent;
   absent explicit design, default to the same severity tier as comparable
   structural `[F-v3-*]` graph errors and record the choice in design.md.

### Requirement 4: TDD and non-regression (engine boundary discipline)

**Objective:** As a maintainer, I want this added test-first and without disturbing
the frozen engine surface, so that `main` stays green.

#### Acceptance Criteria
1. The change shall be implemented test-first: a failing engine test that compiles
   a graph with a no-input node and a no-output node and asserts the new
   diagnostics, added before the production code.
2. The change shall be confined to the engine lint/compile path
   (`packages/graph-agent`); the Studio frontend shall require no diagnostic-
   inventing logic (display only).
3. The change shall keep all existing engine and studio gates green:
   `uv run pytest packages/graph-agent/tests`,
   `uv run mypy --strict packages/graph-agent/src`,
   `uv run pytest apps/studio/backend/tests`, plus the frontend gates if any wiring
   changes.
4. The public API contract test (`packages/graph-agent/tests/test_public_api_contract.py`)
   shall pass — if a new code/enum is added, update the contract intentionally.
