---
related:
  - KB-00-hub
  - KB-08-predict
  - KB-09-run-trace-checkpoint
---

> Distilled from: `docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md` & `01_workflows/06_eval.md`

# KB-10: Golden Baselines & Evaluation

Golden Baselines are reference outputs used to measure and evaluate the quality of agent node generations.

## 1. Directory Layout
Golden data is stored under the `.workspace/` runtime directory to decouple evaluation assertions from the core skill source code:
*   **Path**: `.workspace/golden/<baseline_id>/`
*   **Files**:
    *   `baseline.json`: Stores configuration, global inputs, and execution criteria.
    *   `cases/`: Contains input/output JSON payloads for individual test cases.
    *   `report.json`: Stores validation scores, field diffs, and execution logs.

## 2. Three-State Machine
Agent nodes transition through three evaluation stages:
1.  `untested` (Default): The node has not been run or evaluated.
2.  `logic_ok`: The node compiles and completes Predict dry-runs successfully.
3.  `has_golden`: The node possesses a valid golden reference file for comparison.

*Note: Logic nodes do not participate in golden evaluations since their outputs are deterministic.*

## 3. Seeding & Invalidation Rules
*   **Run Seeding**: Successful run outputs can seed a node's golden baseline. If no golden baseline exists, the system automatically uses the last execution output as the baseline template.
*   **Predict Exclusion**: Predict outputs contain mock values and placeholder shapes. You are strictly forbidden from seeding golden baselines with predict outcomes (`[[KB-08-predict]]`).
*   **Schema Invalidation**: If the output schema of an agent node is updated (e.g. adding required fields in `GRAPH.md`), existing golden baselines that lack these fields are instantly invalidated, raising validation warnings until they are updated to match the new schema.

## 4. Evaluation Diffing
During evaluation runs, the engine compares actual output values to the golden baseline at the field level, grading the accuracy and flagging:
*   Missing required fields.
*   Extraneous fields not defined in the schema.
*   Semantic value mismatches (scored using the evaluation agent).
