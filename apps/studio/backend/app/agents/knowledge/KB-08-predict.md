---
related:
  - KB-00-hub
  - KB-07-compile-diagnostics
  - KB-09-run-trace-checkpoint
  - KB-10-golden
---

> Distilled from: `docs/studio/mvp1/01_workflows/04_run-and-verify.md` & Predict capability unit documentation.

# KB-08: Predict (LLM-Free Dry Run)

Predict mode enables developers and agents to run a compiled skill without invoking remote LLM endpoints, validating runtime dataflow mappings and schema compatibility.

## 1. Core Mechanics
*   **LLM-Free Execution**: Predict runs deterministic code (Python actions inside LOGIC phases) as-is but mocks agent phases. No tokens are consumed.
*   **Dataflow Validation**: Verifies that variables propagated through the DAG match phase schemas and that blackboard slice/merge operations do not cause mapping exceptions.
*   **Hard Pre-Run Gate**: Predict-pass is a strict prerequisite for triggering a real Run. If a skill fails Predict, execution remains locked (`[[KB-13-studio-gates-tools]]`).

## 2. Automatic Mock Selection (P0-P2)
When an agent phase is executed in Predict, the system resolves mock outputs automatically using the following hierarchy (users cannot override this behavior manually):

| Mock Level | Condition | Execution Behavior |
|---|---|---|
| **P0: Golden Baseline** | Valid golden case exists for the node | Replays the exact output payload specified in the golden baseline (`[[KB-10-golden]]`). |
| **P1: Custom Mock Override** | No golden case; manual mock overrides are supplied | Replays custom-injected values specified in the test panel or copilot callbacks. |
| **P2: Heuristic Placeholder** | No golden or custom mocks exist | Auto-generates placeholder outputs conforming to the phase's output JSON schema. |

## 3. Errors Exposed in Predict
While Compile checks static structures, Predict detects dynamic schema mismatches and runtime state transitions:
*   `[F-v3-runtime-state-mapping-failed]`: When blackboard outputs fail to map to downstream inputs.
*   `[F-v3-iterate-over-not-list]`: Occurs when an iterate loop phase is supplied with a non-list variable.
*   **Mock Schema Invalidation**: Occurs when expected input types fail schema checks.

## 4. The 409 Conflict Guard
*   **No Mock Promotion**: Predict outputs are generated via mocks and placeholders. To prevent polluted data from entering baselines, a **409 Conflict Guard** blocks developers and agents from promoting or saving predict-run outputs as golden baselines (`[[KB-10-golden]]`). Only actual run results may seed a baseline.
