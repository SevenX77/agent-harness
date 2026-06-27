# Studio Source-Truth Authoring Design

Status: draft  
Date: 2026-06-27

## Architecture

Studio authoring should be split into four layers:

1. Source model
   - Markdown files on disk.
   - `GRAPH.md` owns graph frontmatter and topology tags.
   - Phase files own phase frontmatter and body.

2. Projection model
   - `SkillDetail`, `graph_topology`, and loaded file contents.
   - Used to render Canvas, Properties, Editor, and diagnostics.
   - Projection can be partial or invalid; invalid projection should still preserve source visibility.

3. Authoring mutations
   - File writes through Tauri native writer where available.
   - Graph topology serialization for `GRAPH.md`.
   - Phase property saves for phase markdown.
   - These mutations update source only. They do not compile automatically.

4. Compiler/lint diagnostics
   - Manual Compile is the semantic gate.
   - Realtime lint is advisory and inline.
   - Diagnostics are projected onto editor lines, Properties fields, and node badges.

## Data Flow

### Canvas Render

`SkillDetail` -> `buildNodes` -> `buildEdges` -> `getAutoLayoutedElements` -> React Flow.

Rules:

- `buildNodes` always includes graph Input and Output affordance nodes.
- `buildEdges` only emits declared edges.
- Layout errors must not destroy renderable nodes. Fallback should use the unlaid-out or last-known node positions.

### Canvas Edit

React Flow gesture -> pure authoring helper -> serialize `GRAPH.md` -> write `GRAPH.md` -> mutate detail.

No automatic compile in this path.

### Editor Edit

Monaco draft -> debounce save -> write file -> update open-file hash/content -> mutate detail.

Rules:

- Lint reads draft but does not control editability.
- A dirty editor buffer has priority over `skill_changed`.
- External same-file changes while dirty produce conflict or stale marker, not silent replacement.

### Properties Edit

Selected node -> phase file content -> parse frontmatter -> kind-specific form -> patch phase file -> write file.

Rules:

- The form edits known fields only.
- Unsupported fields are preserved.
- Body content is preserved.
- Field labels match YAML keys.

### Empty Canvas Selection

Pane click -> clear selected node -> active panel Properties -> graph frontmatter form.

Rules:

- This must not open the editor.
- It must clear both GraphCanvas internal selection override and Workspace selected-node state.

## Boundary Edge Reconnect

Boundary edges are source-backed:

- `Input -> phase`: `phase.depends_on` contains `input`.
- `phase -> Output`: phase tag carries `output`.

Reconnect is a composition of one disconnect and one connect operation. It should support:

- phase -> phase to phase -> Output
- phase -> Output to phase -> phase
- Input -> phase to phase -> phase
- phase -> phase to Input -> phase

The helper must still reject missing endpoints and duplicate resulting source markers.

## Cycle / Invalid Graph Render Fallback

If automatic layout cannot compute a DAG layout:

1. Keep raw nodes and declared edges.
2. Apply deterministic fallback positions if nodes have no measured positions.
3. Show a non-blocking diagnostic.
4. Do not overlay a full-screen blocker.

Compile remains responsible for telling the user that the graph cannot run.

## New Phase Scaffolds

Scaffolds should be clean in topology and useful in source.

Minimal shape:

```yaml
---
name: logic
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
actions: []
---
```

```yaml
---
name: agent
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<role></role>
<goal></goal>
```

```yaml
---
name: subgraph
path: ""
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
```

Notes:

- Empty `path` is an editable incomplete state; compile/lint will diagnose it.
- Empty `<role>` / `<goal>` are editable incomplete states; compile/lint will diagnose them.
- No dependency or output marker is created during node creation.

## Viewport Reset Policy

Allowed fit/reset:

- Entering a skill.
- Exiting a skill or returning to Welcome.
- Initial React Flow `onInit` fit after first layout.

Not allowed:

- Opening or closing editor.
- Saving editor.
- Saving Properties.
- Creating, deleting, renaming a phase.
- Connecting, disconnecting, reconnecting edges.
- Expanding/collapsing subgraph previews.
- Receiving lint/compile diagnostics.

Implementation direction:

- Keep `GraphCanvas key={currentSkillId}` only for skill identity changes.
- Do not key canvas by editor state, active file, layout signature, or compile result.
- Maintain `viewportReadyRef` across authoring edits.

## Test Strategy

Use narrow tests first:

- Pure helper tests for topology/source mutation.
- Component SSR tests for GraphCanvas event behavior.
- Workspace orchestration tests for no auto compile and editor buffer stability.
- Backend/engine serializer tests for no pre-compile cycle rejection.

Manual Tauri verification comes after green tests.
