# Studio Source-Truth Authoring Requirements

Status: draft  
Date: 2026-06-27  
Source of truth: MVP1 design docs listed in `research.md`

## Goal

Make Studio authoring behave like a faithful source editor:

- Canvas reflects and edits `GRAPH.md`.
- Properties reflects and edits phase frontmatter fields.
- Editor edits markdown freely.
- Compile/lint reports problems; authoring does not pre-block semantic invalid states.

## R1. Source Is The Authoring Truth

The Studio frontend must treat the skill source tree as the authoring truth before compile.

Acceptance:

- Canvas nodes derive from `GRAPH.md`, phase file existence, and phase frontmatter.
- Canvas edges derive only from explicit `depends_on` and explicit `output`.
- Canvas must not synthesize Input/Output edges for phases that do not declare them.
- Properties must not show immutable metadata as editable form controls.
- Editor content must not be rewritten from projected canvas/compiler state.

## R2. Compile Owns Semantic Validity

The compiler must be the final semantic validator for graph legality and phase legality.

Acceptance:

- Canvas save must not run compile automatically after create/delete/rename/connect/disconnect/reconnect.
- Manual Compile remains available and still opens/surfaces compiler diagnostics.
- Authoring should not block save solely because the graph is cyclic.
- Authoring should not block save solely because a phase depends on itself.
- Authoring should not block phase file save solely because required execution fields are incomplete.
- Existing lint diagnostics may be shown inline, but they must not make the editor uneditable.

Allowed pre-save checks:

- Missing React Flow endpoint.
- Endpoint cannot be mapped to any visible document node.
- Duplicate visual edge that would write an identical dependency/output marker.
- Filesystem safety such as path traversal or moving folders outside the workspace.
- Optimistic lock conflict.

## R3. Canvas Must Render Invalid Source Best-Effort

Canvas must remain usable even when the source graph is not compilable.

Acceptance:

- A layout cycle must not clear all nodes/edges.
- Cyclic or otherwise invalid topology may show non-blocking diagnostics or badges.
- The user can still select, move, edit, delete, and reconnect visible nodes after such diagnostics.
- Initial viewport fit still happens once when entering a skill, but not after normal authoring edits.

## R4. Boundary Edges Are First-Class Source Edits

Input and Output nodes are authoring affordances for source topology.

Acceptance:

- Connecting Input -> phase writes `depends_on="input"`.
- Connecting phase -> Output writes `output`.
- Reconnecting an existing edge to or from Input/Output must use the same source model.
- Disconnecting boundary edges removes the corresponding `input` dependency or `output` marker.
- Boundary edges must not be treated as non-editable fake edges.

## R5. New Nodes Are Topologically Clean But Source-Shaped

Creating a node must not invent dependencies or output links, but it should create the minimum known MVP1 source shape.

Acceptance:

- New phase refs have `depends_on: []`.
- New phase refs do not set `output`.
- New node creation must not auto-connect to selected nodes, Input, or Output.
- LOGIC scaffold includes `name`, `io.inputs`, `io.outputs`, and `actions`.
- SUBGRAPH scaffold includes `name`, `path`, `io.inputs`, and `io.outputs`; `path` may be empty if no child folder was selected yet.
- AGENT/SKILL scaffold includes `name`, `io.inputs`, `io.outputs`, and editable body placeholders for `<role>` and `<goal>`.
- No scaffold may emit deprecated fields such as `mode`, `system_prompt`, `exit_contract`, `python_callable`, `target_skill`, `sub_skill_ref`, `input`, or `output`.

## R6. Editor Buffer Must Be Free And Stable

The markdown editor must allow arbitrary text edits, including temporarily invalid YAML or XML-like body content.

Acceptance:

- Typing whitespace must not be rejected by lint, compile, canvas refresh, or file-change events.
- A dirty open editor buffer must not be overwritten by `skill_changed`.
- Autosave conflicts should surface a conflict state instead of silently replacing local content.
- Opening/closing the editor must not refit or reset the canvas viewport.

## R7. Properties Is A Field Editor, Not A Metadata Inspector

Properties must expose only fields the user can intentionally edit from that panel.

Acceptance:

- Agent fields: `llm_role`, `tools`, `subagents`, `allow_sequential_overwrite`, `iterate`.
- Logic fields: `actions`, `validator`, `allow_sequential_overwrite`, `iterate`.
- Subgraph fields: `name` through rename dialog, `path` through folder reconnect, `validator`, `allow_sequential_overwrite`, `iterate`.
- `phase id`, node type, file path, dependency list, and file kind must not appear as editable inputs.
- Graph-level properties are handled separately when no node is selected.

## R8. Graph Properties Exists For Empty Canvas Selection

Clicking empty canvas should switch Properties to graph-level frontmatter, not open the editor.

Acceptance:

- Empty canvas click clears selected node state in React and in Workspace.
- Properties panel renders `GRAPH.md` frontmatter fields when no node is selected.
- Graph property edits preserve `GRAPH.md` body phase tags.
- Double-click or explicit file actions may still open `GRAPH.md` in the editor.

## R9. Source Writes Preserve Author Intent

Frontend and backend source serialization should preserve unrelated source bytes where feasible.

Acceptance:

- Topology edits patch `phases:` and `<phase>` tags without rebuilding unrelated graph frontmatter.
- Phase property edits preserve body content and unknown frontmatter keys.
- Future work should move from whole-YAML dumping to field-level patching where comments/style matter.

## R10. TDD Gate

Implementation must follow red-green-refactor.

Acceptance:

- Each behavior change starts with a failing test.
- The failing test is run and observed red before production code changes for that behavior.
- The same test is run green after implementation.
- Existing tests that encode wrong behavior are updated as RED tests, not silently deleted.
