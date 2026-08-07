---
related:
  - KB-00-hub
  - KB-08-predict
  - KB-10-golden
  - KB-11-workspace-runtime
---

> Distilled from: `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md` & `01_workflows/04_run-and-verify.md` & `05_debugging.md`

# KB-09: Run, Trace, & Checkpoint

This document details the telemetry, state persistence, and debugging overrides generated during a skill's actual execution.

## 1. Trace Telemetry (`trace.jsonl`)
*   **Execution Logs**: Every execution run writes detailed telemetry to a `trace.jsonl` file inside `.workspace/runs/<run_id>/`.
*   **Event Types**: The engine emits dozens of distinct structured event types. When debugging, analyze the following key events:
    *   `phase_start` / `phase_end`: Logs exact input/output payloads and metrics (time, token usage) for a phase.
    *   `tool_call` / `tool_response`: Logs arguments and outputs for tool interactions within agent nodes.
    *   `error`: Captures stack traces, schema violations, and API failures.

## 2. Checkpoint & Resume
*   **Superstep Persist**: The engine saves checkpoints at every DAG superstep. If a run fails or is paused, it can be resumed from the last valid checkpoint without losing prior progress.
*   **Namespace Structure**: Checkpoints are segmented to prevent state collisions:
    *   `""` (Empty String): The global graph execution scope.
    *   `agent:<phase_id>`: Checkpoints scoped to specific agent nodes.
    *   `iter{k}`: Checkpoints scoped to loop/iteration bounds.

## 3. State Manipulation & HitL
*   **Context Overrides**: Developers can inject temporary state overrides (`context_overrides`) into a checkpoint to test edge cases or bypass transient errors. This places the workspace in a `dirty-state` flag. State overrides are meant only for manual debugging and testing; they must never be committed.
*   **Human-in-the-Loop (HitL)**: The engine supports blocking user approval and input injection via `tool_call_responses` inside the checkpoint namespace.

## 4. Transition Points (Blackboard edge dot)
*   **Dot Double State**: The edges connecting phases represent state transitions (dot points).
    *   *Pre-run (Static)*: Shows static blackboard field inferences (what variables are predicted to exist at this transition).
    *   *Post-run (Dynamic)*: Displays actual blackboard values captured after the parent phase ends, including any reduction or file injections.

## 5. Bounded Trace Diagnostics with `query_run_trace`

A full `trace.jsonl` can reach ~250 KB per run — never pull it whole. Use
`query_run_trace(skill_id, run_id, phase?, event_types?, since_seq?, limit?)`:
slices are bounded, and every response carries per-phase aggregates (iteration
count, `llm_call` count, `tool_call` count, rejection count with top-N reasons).

The routine that converges fastest:

1. **Aggregates first** — call with no phase filter; the per-phase table tells
   you where the run spent iterations or got rejected.
2. **Zoom one phase** — re-query with `phase=` and `event_types=` narrowed to
   the suspicious class (e.g. validator rejections).
3. **Walk by sequence** — page with `since_seq`/`limit` instead of raising the
   limit; the sequence numbers are stable within a run.
4. For final-state questions prefer `get_run_detail`; for produced files use
   `list_run_artifacts` / `read_run_artifact` (`[[KB-14-artifacts-persistence]]`).

