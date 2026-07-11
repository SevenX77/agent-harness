---
related:
  - KB-00-hub
  - KB-01-skill-anatomy
  - KB-02-io-dataflow
  - KB-04-agent-nodes
---

> Distilled from: `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` §4 & §5

# KB-05: Subgraph Inclusion

A Subgraph phase (`SUBGRAPH.md`) allows a skill to embed and invoke another complete graph skill as a nested node. This provides a powerful mechanism for modularity and graph reuse.

## 1. SUBGRAPH.md Structure
Unlike LOGIC or Agent nodes, a subgraph node has no execution body. It acts as a structural pointer.

```yaml
# Example SUBGRAPH.md
name: run_sub_analysis
path: subgraph/sub_analyzer
io:
  inputs:
    type: object
    required: [segment_data]
    properties:
      segment_data: {type: array, items: {type: object}}
  outputs:
    type: object
    required: [final_score]
    properties:
      final_score: {type: number}
validator: false
```

### Key Field Specifications:
*   `name`: The display name of the node.
*   `path`: POSIX-style relative path pointing to the child skill root directory.
*   `io`: Declares the inputs passed from the parent blackboard and outputs merged back upon completion (`[[KB-02-io-dataflow]]`).
*   `validator`: Runs a `validator.py` at the subgraph node boundary if `true` (`[[KB-03-logic-actions]]`).
*   `allow_sequential_overwrite`: Authorizes output key collision with ancestor phases.

*Note: A SUBGRAPH.md file must not contain any body text or XML tags; the file body must remain empty.*

## 2. Path Resolution Rules
The compiler statically verifies child paths during build:
*   **POSIX Standards**: Paths must use forward slashes (`/`) and use only portable characters (`A-Z`, `a-z`, `0-9`, `.`, `_`, `-`, `/`).
*   **Boundary Restriction**: The path must resolve inside the current skill root. Escaping the skill root using directory traversal (e.g. `../`) is strictly prohibited.
*   **Child Validation**: The target directory pointed to by `path` must exist and contain a valid `GRAPH.md` file (`[[KB-01-skill-anatomy]]`).
*   **Prohibited Fields**: The field `target_skill` is disallowed inside `SUBGRAPH.md`.

## 3. Schema Mapping and Interface Flexibility
The input/output schemas of the parent subgraph node do not need to be a 1:1 identical match to the target child skill's root I/O schemas defined in the child's `GRAPH.md`. 
*   **Inputs**: The parent subgraph node acts as a translator, extracting fields from the parent blackboard and injecting them into the child graph run.
*   **Outputs**: The parent subgraph node defines which keys are extracted from the child graph final blackboard state and merged back into the parent blackboard.
*   The compiler verifies that all required inputs of the child graph can be mapped from the inputs declared on the subgraph node.
