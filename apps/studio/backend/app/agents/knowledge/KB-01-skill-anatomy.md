---
related:
  - KB-00-hub
  - KB-02-io-dataflow
  - KB-04-agent-nodes
  - KB-05-subgraph
  - KB-11-workspace-runtime
---

> Distilled from: `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` §1 & §2

# KB-01: Skill Physical Layout & Anatomy

A skill is defined by a strict physical folder structure and file grammar. The layout maps the source definitions of a skill to the execution engine.

## 1. Directory Structure

Every skill directory must conform to the following directory layout:

```text
<skill_root>/
  GRAPH.md                        # Skill topology, root metadata, and I/O boundary
  phases/
    <phase_id>/
      LOGIC.md | SUBGRAPH.md | SKILL.md   # Only one of these files may exist per phase
      actions/                    # Only for LOGIC.md phases with local Python actions
        <action_name>.py
      validator.py                # Optional phase output validation script
  subgraph/                       # Optional nested child skills
    <child_skill_name>/
      GRAPH.md
      phases/
        ...
  references/                     # Static markdown reference files
  examples/                       # Static markdown example files
  .workspace/                     # Standard runtime workspace directory (git-ignored)
    runtime_config.json
    runs/
    golden/
    import_files/
    copilot/
```

### Key Layout Rules:
*   **The `.workspace/` Directory**: Standard runtime directory (lowercase). It is not part of the skill source code and must be git-ignored. Static compiling reads only `runtime_config.json` (`[[KB-11-workspace-runtime]]`) from it.
*   **Exclusive Phase Types**: A phase directory `phases/<phase_id>/` must contain exactly one definition file: `LOGIC.md` (`[[KB-03-logic-actions]]`), `SUBGRAPH.md` (`[[KB-05-subgraph]]`), or `SKILL.md` (`[[KB-04-agent-nodes]]`).

## 2. Three-Name Consistency Rule
To pass compilation (`[[KB-07-compile-diagnostics]]`), the following three identifiers must match exactly:
1.  The folder name under `phases/` (the `<phase_id>`).
2.  The frontmatter name or body XML tag matching the registration.
3.  The registered entry under the `phases` list in `GRAPH.md`.

## 3. GRAPH.md Grammar

The `GRAPH.md` file defines the skill's global boundaries and phase execution topology.

```yaml
---
schema_version: "v0.3.0"
name: story_deconstruction
description: Recursive story deconstruction pipeline.
llm_role: analyst

io:
  inputs:
    type: object
    required: [chapters]
    properties:
      chapters:
        type: array
        items: {type: object}
  outputs:
    type: object
    required: [report]
    properties:
      report: {type: string}

phases:
  - segmentation
  - event_timeline
  - story_analysis
  - global_synthesis

iterate:
  mode: batch
  over: chapters
  item_var: chapter
  range: [1, 1]
  concurrency: 4
---

<phase depends_on="input">segmentation</phase>
<phase depends_on="segmentation">event_timeline</phase>
<phase depends_on="event_timeline">story_analysis</phase>
<phase depends_on="story_analysis" output>global_synthesis</phase>
```

### Valid Fields in GRAPH.md:
*   `schema_version`: Must be exactly `"v0.3.0"`.
*   `name`: The unique name of the skill.
*   `description`: Human-readable description.
*   `llm_role`: Default LLM role for the entire graph (`[[KB-12-llm-roles]]`).
*   `io`: The blackboard I/O boundaries (`[[KB-02-io-dataflow]]`).
*   `phases`: List of registered phase IDs.
*   `iterate`: Global loop/iteration specifier (`[[KB-06-iterate]]`).

### DAG Body Tags:
*   `<phase depends_on="input">phase_id</phase>`: Entry phase connected to root inputs.
*   `<phase depends_on="upstream">phase_id</phase>`: Normal dependency edge. Multiple dependencies are comma-separated (e.g., `depends_on="a,b"`).
*   `<phase depends_on="upstream" output>phase_id</phase>`: Identifies a terminal node feeding the root output.

## 4. Prohibited and Deprecated Fields
The following fields are strictly prohibited in any skill or phase file:
*   `batch:` (Use `iterate:` block instead).
*   `iterator:` (Use `over` inside the `iterate:` block).
*   `mode:` or `phase_id:` in phase frontmatter (derived from file names).
*   `phase_config:` or `node_type:` in phase frontmatter.
*   `io_inputs_ref` or `io_outputs_ref` (schemas must be inline).
*   `target_skill` inside `SUBGRAPH.md` (must use `path`).
