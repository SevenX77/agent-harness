---
related:
  - KB-00-hub
  - KB-01-skill-anatomy
  - KB-03-logic-actions
  - KB-07-compile-diagnostics
  - KB-11-workspace-runtime
---

> Distilled from: `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` §6 & §10 & §2 (Compile Gate)

# KB-02: Input/Output & Blackboard Dataflow

The execution engine uses a shared global data store called the **Blackboard** to pass data between phases. Declared I/O schemas define the strict data contracts at each node boundary.

## 1. Strict I/O Schema Rules
All `io.inputs` and `io.outputs` blocks in `GRAPH.md` (`[[KB-01-skill-anatomy]]`) and phase definition files must be valid Draft 2020-12 JSON Schema objects and conform to the following three strict rules:
1.  **Top-Level Type**: The top-level `type` must be explicitly declared as `"object"`.
2.  **Properties Block**: A `properties` block must exist.
3.  **Required List Integrity**: If a `required` list is present, every field named in it must be explicitly defined in the `properties` block.

*Note: Declaring external references like `io_inputs_ref` or referencing external files under an `io/` directory is strictly prohibited; all schemas must be inline.*

## 2. Blackboard Slicing & Merging
Before a phase executes, the engine creates a read-only local input snapshot (a slice) of the blackboard matching the keys defined in the phase's `io.inputs.properties`. 
Upon phase completion, the engine validates the phase's output dictionary against its `io.outputs` schema. If valid, the dictionary is merged back into the global blackboard. A phase is prohibited from writing keys that are not declared in its `io.outputs.properties`.

## 3. Sequential Overwrite Authorization
To protect data integrity, the engine blocks arbitrary overwrites of upstream data.

*   **Default Protection**: If a phase declares an output field that has already been written by an upstream ancestor phase (a parent, grandparent, etc., in the DAG), compilation will fail with error code `[F-v3-sequential-overwrite-unauthorized]` (`[[KB-07-compile-diagnostics]]`).
*   **The Overwrite Whitelist**: To bypass this gate, the duplicate field name must be explicitly added to the phase's `allow_sequential_overwrite` frontmatter list.

```yaml
# Example: authorizing an overwrite in a phase frontmatter
name: refine_phase
io:
  outputs:
    type: object
    required: [draft]
    properties:
      draft: {type: string}
allow_sequential_overwrite:
  - draft # Authorizes overwriting the 'draft' field written by an ancestor phase
```

### Evaluation Scope:
*   The check is only triggered for **upstream ancestors** (direct or indirect dependency path). 
*   Identical output keys in parallel phases do not trigger this error since their execution paths are disjoint.
*   Every key listed in `allow_sequential_overwrite` must exist in the phase's `io.outputs.properties`.
