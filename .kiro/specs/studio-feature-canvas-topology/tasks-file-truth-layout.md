---
status: Implementing
created: 2026-06-27
owner: Studio Frontend
scope: GraphCanvas file-truth layout and viewport contract
---

# Canvas File-Truth Layout Tasks

## Requirements

R1. Canvas is a projection of `GRAPH.md` and phase files before compile.
Frontend may render nodes, edges, panels, badges, and optimistic write feedback,
but it must not invent execution rules or block document states that the compiler
is responsible for validating.

R2. Functional edges come only from document topology:
`depends_on` creates upstream edges, `depends_on="input"` creates the graph input
edge, and `output` creates the graph output edge. Isolated phases stay isolated.

R3. Layout is a one-time projection for a visible node set, not a continuous
topology reaction. Dependency edges, output markers, runtime/status decoration
such as trace payloads, compile/lint badges, golden state, selected state,
resume state, and error messages must not rerun dagre or move existing nodes.
After the first projection, edges are drawn from the document and existing node
positions remain stable. When the visible node set changes, only newly visible
nodes may receive freshly projected positions; existing nodes keep their current
canvas positions. A graph-scope change may start a new first projection.

R4. Viewport fit is a one-time entry action for a mounted skill canvas after real
layout nodes and the React Flow instance are both available. Opening/closing the
editor, saving, renaming, compiling, running, expanding inline subgraphs, and
normal panel resizing must not refit or recenter the canvas.

## Tasks

- [x] Add pure tests for file-truth layout signatures, dependency topology
      exclusion, trace/status decoration exclusion, merge-layout-position
      behavior, compact-only canvas height, and single initial viewport fit.
      _Requirements: R2, R3, R4_
      _Verification: `vitest run canvas-projection.test.ts`_

- [x] Wire `GraphCanvas` layout through the visible-node signature cache and
      merge cached layout positions back into fresh render nodes.
      _Requirements: R3_
      _Verification: `vitest run GraphCanvas.test.tsx canvas-projection.test.ts`_

- [x] Replace scattered fit calls with one initial-fit guard.
      _Requirements: R4_
      _Verification: `vitest run GraphCanvas.test.tsx canvas-projection.test.ts`_

- [x] Keep edge rendering file-truth-only and preserve the existing no-synthesized
      input/output edge tests.
      _Requirements: R2_
      _Verification: `vitest run buildEdges.test.ts`_

- [x] Remove the unused run-focus-follow helper so no dormant code path suggests
      compile/run should recenter the canvas.
      _Requirements: R4_
      _Verification: `rg "nodeToFocus|canvas-focus" apps/studio/frontend/src` returns no matches_
