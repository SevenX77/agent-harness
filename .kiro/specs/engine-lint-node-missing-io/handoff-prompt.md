# Handoff Prompt — Engine lint: node missing input/output

Copy-paste the block below to the implementing agent.

---

You are picking up an **engine** feature in the `agent-harness` repo (a uv Python
workspace + a Tauri/React Studio). Task: make the engine emit a lint diagnostic
when a skill-graph phase node has **no input or no output**, and have it show on
the node badge and on `GRAPH.md`. This is a `packages/graph-agent` (engine) change
— NOT a frontend change — so the heavy, test-first flow applies, not the
frontend fast-path.

## Read first (in order)
1. `AGENTS.md` — baseline, CI Gates, three-module architecture, KEEP-MAIN, and
   "MVP1 design = source of truth".
2. The spec for this task: `.kiro/specs/engine-lint-node-missing-io/requirements.md`
   — especially the **OPEN DECISION (A connectivity vs B io-schema)** block.
3. Engine lint/compile source: `packages/graph-agent/src/graph_agent/core/loader.py`
   (search `code="[F-v3-`) to see how `CompileIssue` diagnostics are built, located,
   and severity-tagged. This is where the new rule goes.
4. How diagnostics reach the UI (display only — do not add logic here):
   - `apps/studio/frontend/src/components/studio/lint-monaco-markers.ts`
     ("Source of truth stays the engine lint payload — this never invents diagnostics").
   - Node badges via `compileErrorsByNodeId` / the node-error projection consumed by
     `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx`.

## Non-negotiable constraints
- **Evidence-first (项目铁律):** do NOT guess the definition of "no input/output".
  Resolve **(A) graph connectivity** vs **(B) declared io schema** in `design.md` by
  aligning to the MVP1 design source (`docs/engine/mvp1/`,
  `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/`), quoting file
  path + lines. This is a design-source decision — settle it from the design body,
  not by asking. (Signal: "show on `GRAPH.md`" leans toward (A), since topology
  lives in `GRAPH.md`; confirm against the design before committing to it.)
- **TDD:** write a FAILING engine test first (compile a graph with a no-input node
  and a no-output node; assert the new diagnostics), then the production code.
  Follow the `superpowers:test-driven-development` discipline.
- **KEEP-MAIN / boundary:** confine changes to `packages/graph-agent` (engine). The
  Studio frontend should need display-only wiring at most; it must not compute the
  diagnostic.
- **Spec flow:** this is a kiro spec. Produce `design.md` (resolve the open decision,
  pick code/severity/location, define subgraph behavior) and `tasks.md` next to
  `requirements.md` before implementing, and keep them in sync with the code.

## Definition of done (all green locally before any PR)
- New engine test passes; the rule fires for no-input and no-output nodes and is
  silent for a fully-connected graph; global INPUT/OUTPUT sentinels exempt.
- Diagnostic shows on the node badge and on `GRAPH.md` in Studio.
- Gates: `uv run pytest packages/graph-agent/tests` ·
  `uv run mypy --strict packages/graph-agent/src` ·
  `uv run pytest apps/studio/backend/tests` · and frontend gates if any wiring
  changed (`npm run lint && npm run typecheck && npm test && npm run build` in
  `apps/studio/frontend`).
- `packages/graph-agent/tests/test_public_api_contract.py` passes (update it
  deliberately if you add a code/enum).
- Land via PR to `main` (protected, auto-merge on green) per AGENTS.md "Workflow
  Pipeline". Do not push to `main` directly.

Deliver: the failing-then-passing test, the engine rule, the `design.md`/`tasks.md`,
and the minimal frontend display wiring if needed.
