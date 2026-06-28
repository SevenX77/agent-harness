# Studio Source-Truth Authoring Research

Status: draft  
Date: 2026-06-27  
Owner: Codex  
Scope: Studio canvas, editor, properties, graph serialization

## Source Documents Read

This spec is an implementation coordination file. It does not replace the MVP1 design.

Primary sources:

- `docs/design/productization-architecture-2026-06-11.md`
- `docs/development/FRONTEND_UI_SPEC.md`
- `docs/development/task-spec-standard.md`
- `docs/studio/mvp1/01_workflows/02_authoring.md`
- `docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md`
- `docs/studio/mvp1/02_capabilities/phase-editing/mvp1-alignment.md`
- `docs/studio/mvp1/02_capabilities/file-editing/mvp1-alignment.md`
- `docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md`
- `docs/studio/mvp1/03_regions/canvas/mvp1-alignment.md`
- `docs/studio/mvp1/03_regions/properties/mvp1-alignment.md`
- `docs/studio/mvp1/03_regions/editor/mvp1-alignment.md`
- `docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md`
- `docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md`
- `docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md`
- `docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md`
- `apps/studio/frontend/CLAUDE.md`

## MVP1 Principles Relevant Here

1. Studio canvas/editor/properties are source authoring surfaces. They read and write the skill source tree.
2. `GRAPH.md` and phase markdown files are the source of truth before compile.
3. The compiler is the semantic authority for validity. Studio should not invent a second compiler in the frontend.
4. Node kind comes from physical files: `LOGIC.md`, `SKILL.md`, `SUBGRAPH.md`.
5. Topology comes from `GRAPH.md` phase tags. Explicit `depends_on="input"` and `output` control graph boundary edges.
6. Properties edits only cover editable frontmatter fields. Immutable metadata should not appear as editable controls.
7. Per-phase `io.inputs` and `io.outputs` are part of engine MVP1 syntax; Studio may choose a dedicated I/O panel, but it must not hide the fact that they are source fields.
8. Subgraph resolution is path based. `path` is a child graph folder reference, not a registry id.

## Current Code Facts

Files inspected:

- `apps/studio/frontend/src/components/studio/Workspace.tsx`
- `apps/studio/frontend/src/components/studio/SplitEditor.tsx`
- `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx`
- `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx`
- `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts`
- `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx`
- `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts`
- `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts`
- `apps/studio/frontend/src/components/nodes/buildEdges.ts`
- `apps/studio/backend/app/services/skills.py`
- `packages/graph-agent/src/graph_agent/core/graph_serializer.py`
- existing frontend tests around Workspace, GraphCanvas, build nodes/edges, Properties, and frontmatter

### Correct Or Mostly Correct Existing Behavior

- `buildEdges` only renders declared dependencies and explicit boundary edges. There is already a test that an isolated phase gets no inferred Input/Output edges.
- `buildNodes` derives node kind from phase files before falling back to topology mode.
- `PropertiesPanel` already hides many immutable metadata fields and renders editable fields by node kind.
- `PropertiesPanel` has `iterate` controls for `batch` and `loop`.
- `SplitEditor` receives a `canvas` prop rather than constructing its own completely separate canvas instance internally.
- `GraphCanvas` hides the initial viewport until first fit is controlled.
- `GraphCanvas` already tests that empty pane click clears visual selection and opens the Properties panel.

### Drift / Failure Sources

1. Workspace auto-compiles after authoring writes:
   - `handleCreatePhase` writes a phase file, serializes `GRAPH.md`, writes `GRAPH.md`, then calls `compileSkillById`.
   - `handleDeletePhase` calls `compileSkillById`.
   - `handleRenamePhase` calls `compileSkillById`.
   - `writeGraphEdit` calls `compileSkillById` after connect/disconnect/reconnect.
   - This contradicts the current product direction: authoring should stay editable until the user clicks Compile.

2. Graph serializer rejects topology before compile:
   - `packages/graph-agent/src/graph_agent/core/graph_serializer.py` rejects self dependencies, unknown phase deps, and cycles while serializing topology.
   - Backend `serialize_skill_graph_markdown` maps these into canvas serializer fatal errors.
   - Cycle and self-dependency are semantic graph validity. They should be compiler diagnostics, not authoring save blockers.

3. Canvas layout blanks the graph on cycles:
   - `GraphCanvas` catches `CycleDetectedError` from `getAutoLayoutedElements` and returns empty nodes/edges.
   - The UI then overlays "cannot render graph".
   - A cyclic source graph is invalid for compile, but it is still source the user needs to edit. Canvas should render a best-effort graph.

4. Reconnect blocks graph boundary endpoints:
   - `GraphCanvas.onReconnect` rejects any old/new endpoint involving Input or Output with "Only phase nodes can be reconnected as dependencies".
   - `connectPhaseRefs` and `disconnectPhaseRefs` already understand Input -> phase and phase -> Output, so reconnect should support the same document model.

5. Authoring helpers still contain semantic guards:
   - `connectPhaseRefs`, `planEdgeReconnect`, and `reconnectPhaseRefs` reject self-dependency.
   - Some mechanical checks are still appropriate, such as missing endpoints, unknown visible endpoints, and duplicates. But semantic graph legality should be left to compile.

6. New phase scaffolds are too thin:
   - `defaultPhaseMarkdown` only writes `name`.
   - Engine MVP1 syntax says required frontmatter includes:
     - LOGIC: `name`, `io.inputs`, `io.outputs`, `actions`
     - SUBGRAPH: `name`, `path`, `io.inputs`, `io.outputs`
     - AGENT/SKILL: `name`, `io.inputs`, `io.outputs`; body needs `<role>` and `<goal>` for compile.
   - The current test explicitly asserts no `io:` in scaffold. That test is aligned to "clean stub" but not to engine MVP1 target syntax.

7. Monaco buffer can be overwritten by external refresh:
   - `Workspace` listens for `skill_changed` and replaces open editor content when not in-flight.
   - A local dirty buffer that has not yet autosaved is not the same as "safe to replace".
   - This can explain typing feeling blocked or losing spaces when file refreshes race with lint/save/canvas writes.

8. Properties frontmatter saves parse and dump the whole YAML object:
   - Unknown keys are preserved semantically, but comments, ordering details, quoting style, and some whitespace can be rewritten.
   - For an authoring surface that should faithfully reflect markdown, this should move toward local field patching.

9. Realtime lint/build stage is too close to compile state:
   - Workspace maps `readLintStatus() === passed` to `compile-pass`.
   - That can make the UI behave as if a compile succeeded when only realtime lint passed.
   - Manual compile should be the clear gate for Predict/Run.

10. Some tests encode the drift:
   - `GraphCanvas.test.tsx` expects a cycle warning overlay that prevents rendering.
   - `Workspace.test.tsx` expects compile after canvas connection/create/delete.
   - `canvas-authoring.test.ts` expects scaffolds to omit `io:`.

## Design Tensions To Resolve In This Spec

1. MVP1 graph-authoring docs mention some live prevention such as cycle blocking. The user's current product requirement is stronger and newer: do not block free editing before Compile. This spec follows the current requirement while keeping compiler diagnostics intact.
2. Some UI guardrails are still useful. This spec distinguishes:
   - Mechanical safety: preserve files, valid path writes, endpoint exists, no duplicate edge object.
   - Semantic validity: cycle, self dependency, missing role, missing action, missing path target, invalid dataflow. These belong to lint/compile diagnostics.
3. Phase scaffold should be helpful but not restrictive. New nodes should be clean in topology, but their files should include the minimal MVP1 source shape where that shape is known.

## First RED Test Targets

1. `Workspace.test.tsx`
   - Graph edits write source and refresh detail without calling `compileSkill`.
   - Manual Compile remains the only path that calls `compileSkill`.
   - `skill_changed` does not replace an open dirty editor buffer.

2. `GraphCanvas.test.tsx`
   - Cycle layout failure still renders nodes/edges with a non-blocking diagnostic.
   - Reconnect supports phase -> Output and Input -> phase.

3. `canvas-authoring.test.ts`
   - New node phase refs have no dependencies and no output marker.
   - Default phase markdown includes MVP1 minimum source fields for each node kind, without deprecated fields.

4. `graph_serializer` backend/engine tests
   - Topology serialization preserves cyclic/self-dependent `GRAPH.md` source instead of throwing pre-compile.
   - Unknown dependencies from manually edited `GRAPH.md` are preserved or surfaced as diagnostics without losing source.

5. `LazyMonacoPanel` / `Workspace` tests
   - Dirty content is not overwritten by a same-file `skill_changed` event.
