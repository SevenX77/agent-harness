# Decision: engine parallel fan-out must run — delta updates + reducer channels

Date: 2026-08-15
Status: approved (user directive 2026-08-15: "遇到 engine 问题就修引擎,第一性原理,模块化思维,高内聚低耦合")
Scope: `packages/graph-agent` only.

## Problem

The compiler accepts parallel fan-out topology (`<phase depends_on="a">b</phase>` +
`<phase depends_on="a">c</phase>`), but the runtime cannot execute it. Minimal
reproduction (4-node diamond of pure LOGIC nodes, no LLM):

```
InvalidUpdateError: At key 'data': Can receive only one value per step.
```

Root cause chain, from first principles:

1. `WorkflowState` declares `data: BusinessData` and `flow: FrameworkState`
   with **no reducer annotation** (`core/state.py`), so LangGraph gives each a
   LastValue channel that rejects two writes in one superstep.
2. Every phase node returns the **full state** — `StateMapper.wrap_phase_output`
   computes the phase's exact output delta (`updates_dict`, schema-validated),
   then merges it into a full `WorkflowState` and returns all three keys. Two
   parallel phases therefore both write `data` and `flow` in the same superstep
   even though their business fields are disjoint.
3. Field evidence that this bites in practice: middleware comments
   (`middleware/exit_control.py`, `middleware/cognitive_flow.py`) document
   InvalidUpdateError workarounds for the `flow` channel; the bundled
   story-deconstruction-v3 skill's `batch-analysis` subgraph declares a
   6-way parallel dimension fan-out that can never run.

The compiler promise and the runtime capability contradict each other. The fix
belongs in the engine state layer (module boundary: engine owns phase execution),
not in skills serializing their topology to dodge the bug.

## Decision

Make node updates **deltas**, and make the `data` / `flow` channels
**merge-reducer channels** that fold deltas field-wise.

1. **Nodes return deltas.** `wrap_phase_output` returns
   `{"data": <delta dict>, "flow": <flow delta dict>, "messages": [...]}` where
   the data delta contains only the phase's schema-validated output fields plus
   its `phase_outputs` entry. It stops returning the merged full state. The
   batch/loop/subgraph return paths (`_with_phase_outputs`,
   `_with_graph_iterate_signal`) delta-ize the same way.
2. **`data` channel reducer** (`core/state.py`): binary fold
   `merge_business(old, new)`:
   - `new` is a full `BusinessData` (graph input / legacy writer) → replace.
   - `new` is a delta dict → `old.model_copy(update=...)` with one special
     case: `phase_outputs` dict-merges per phase key instead of replacing.
   - Two parallel deltas writing the **same business field** raise a
     `GraphAgentFatalError` naming phase and field (runtime backstop; primary
     guard is the compile rule below).
3. **`flow` channel reducer**: same fold shape;
   dict-shaped counters (`retry_counts`, `metrics`, `critic_metrics`,
   `subagent_validation_retries`) merge per key, scalar metadata
   (`current_phase`, `last_output`, ...) is last-writer-wins — under
   parallelism these are display metadata with no single-value semantics, and
   superstep ordering is accepted as nondeterministic.
4. **Compile-time guard** (only if absent today — verify first): two phases
   with no dependency path between them declaring the same output field is a
   FATAL dataflow diagnostic. Makes the illegal state unrepresentable instead
   of failing at runtime.

## Non-goals

- No change to phase-internal agent loops, middleware, or messages channel
  (already `DeltaChannel`).
- No back-compat shims for old checkpoints (pre-release, disposable data).
- No studio-layer changes in this PR.

## Acceptance

- New engine test: 4-node pure-LOGIC diamond compiles, assembles, `invoke`s,
  and the join phase sees both branch outputs (currently raises
  InvalidUpdateError — this is the TDD RED case).
- New engine test: parallel same-field writers → compile FATAL (or runtime
  fatal if compile rule deferred with rationale).
- Existing gates green: `ruff`, `mypy --strict packages/graph-agent/src`,
  `pytest packages/graph-agent/tests`.
- Real-skill smoke: story-deconstruction-v3-lab's `batch-analysis` 6-way
  fan-out no longer dies on the state channel (verified after vendor rebuild
  on the desktop app, separate step per AGENTS.md Workflow Pipeline §7).
