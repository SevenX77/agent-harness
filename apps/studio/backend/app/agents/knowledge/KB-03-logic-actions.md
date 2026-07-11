---
related:
  - KB-00-hub
  - KB-01-skill-anatomy
  - KB-02-io-dataflow
  - KB-07-compile-diagnostics
---

> Distilled from: `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` §3 & §5 (Validator)

# KB-03: LOGIC Phases & Actions

A LOGIC phase executes deterministic Python code. It is designed to perform text manipulation, validation, and data formatting without relying on LLM reasoning.

## 1. LOGIC.md Structure
The `LOGIC.md` file defines the input/output boundaries, lists the actions to run, and dictates their execution order.

```yaml
# Example LOGIC.md frontmatter
name: format_report
io:
  inputs:
    type: object
    required: [raw_metrics]
    properties:
      raw_metrics: {type: object}
  outputs:
    type: object
    required: [formatted_markdown]
    properties:
      formatted_markdown: {type: string}
actions:
  - clean_metrics
  - render_markdown
validator: true
```

The body of the file must list `<action>` XML tags in the precise order of execution, matching the frontmatter `actions` list exactly:
```markdown
<action>clean_metrics</action>
<action>render_markdown</action>
```

## 2. Python Action Specification
All actions are implemented as standalone Python scripts.

*   **Location**: An action script must live at `phases/<phase_id>/actions/<action_name>.py`.
*   **Signature**: The file must export a function named `<action_name>` with the exact signature:
    ```python
    def <action_name>(inputs: dict) -> dict:
        # Purity and read-only constraints apply
        return {"output_key": "processed_value"}
    ```

### Strict Action Constraints:
1.  **Read-Only Inputs**: The `inputs` dictionary is a read-only local snapshot. Actions must not modify `inputs` or any global context object.
2.  **Explicit Returns**: Output values must be returned in a dictionary. The returned keys must exist in the phase's `io.outputs.properties` block (`[[KB-02-io-dataflow]]`).
3.  **Compilation Hygiene**: The compilation pipeline prevents the creation of `__pycache__` directories in the skill source folder.
4.  **Action Purity**: Actions must avoid unsafe imports, external network requests, or dynamic scripting.

## 3. Validator Runtime Contract
If a phase (LOGIC, SUBGRAPH, or SKILL) specifies `validator: true`, the engine will run a validator script immediately after the phase execution completes.

*   **Location**: The script must live at `phases/<phase_id>/validator.py`.
*   **Signature**: It must export a function named `validate` with the signature:
    ```python
    def validate(output: dict, state_slice: dict, **kwargs) -> None | dict:
        # Custom validation logic
        return None
    ```

### Validator Output Rules:
*   **Success (No Change)**: Return `None` to accept the output as-is.
*   **Success (Enriched)**: Return a modified `dict` to enrich or correct the output. This returned dictionary must conform strictly to the phase's `io.outputs` schema.
*   **Failure**: If the validator raises an exception, returns an invalid type, or returns a dictionary that fails the schema gate, execution halts with a fatal code of type `[F-v3-*-validator-failed]` (`[[KB-07-compile-diagnostics]]`).
