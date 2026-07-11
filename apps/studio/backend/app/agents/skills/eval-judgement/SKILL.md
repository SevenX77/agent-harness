---
name: eval-judgement
description: Analyze predict or run outputs against target evaluation baselines, delivering pass/rework conclusions and attributing root-cause failures.
---

# Skill: Evaluation Judgment

This skill defines the methodology for evaluating the execution outputs of a graph skill and deciding whether they meet design quality gates.

## 1. Evaluation Workflow

1.  **Establish Acceptance Standards**: Retrieve the global user goals, target schemas, and reference baseline cases defined in the golden configuration (`[[KB-10-golden]]`).
2.  **Inspect Execution Evidence**: Read actual execution evidence from run trace logs, metrics, output payloads, and differences against references (`[[KB-09-run-trace-checkpoint]]`). Never evaluate output quality based on subjective assertions without trace data.
3.  **Classify Rework and Next Steps**: Determine the outcome and classify any issues into one of the following states:
    *   `pass`: The run satisfies all schema validation rules and quality benchmarks.
    *   `design_rework`: Structural workflow bugs are present (e.g. invalid DAG paths, phase partition issues). Hand control back to Clotho for graph refactoring.
    *   `repair_needed`: Execution bugs are present (e.g. Python action exceptions, prompt schema mismatches, compiler errors). Hand control back to Lachesis for code and prompt repairs.
    *   `needs_user_input`: The provided inputs or evaluation baselines are insufficient, or the goal is ambiguous. Ask the user for clarification.
4.  **Emit Short Conclusion**: Provide a concise summary containing the trace evidence, final classification, and the next concrete step.

## 2. Anti-Patterns
*   ❌ Declaring a test as passed without checking the trace log (`trace.jsonl`) or verifying output values.
*   ❌ Delivering vague feedback (e.g., *"the output looks bad"*) without attributing the failure to design rework, repair, or missing user inputs.
*   ❌ Conflating multiple root causes into a single, unstructured paragraph.
