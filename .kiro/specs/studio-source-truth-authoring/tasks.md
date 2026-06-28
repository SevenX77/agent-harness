# Studio Source-Truth Authoring Tasks

Status: draft  
Date: 2026-06-27

## Phase 0: RED Tests

- [x] 0.1 Update Workspace tests so canvas edits no longer auto-compile.
  - Files: `apps/studio/frontend/src/components/studio/Workspace.test.tsx`
  - Required RED cases:
    - connect writes `GRAPH.md` and mutates detail without calling `compileSkill`
    - create phase writes source without calling `compileSkill`
    - delete phase writes/removes source without calling `compileSkill`
    - reconnect writes once without calling `compileSkill`
    - manual compile still calls `compileSkill`
  - Run: `cd apps/studio/frontend && npm test -- src/components/studio/Workspace.test.tsx`
  - _Requirements: R2, R10_

- [x] 0.2 Update GraphCanvas tests for best-effort invalid graph rendering.
  - Files: `apps/studio/frontend/src/components/GraphCanvas.test.tsx`
  - Required RED cases:
    - `CycleDetectedError` does not render the full-screen "cannot render graph" blocker
    - React Flow still receives nodes/edges after a layout cycle
    - reconnect can target Output and Input boundary nodes
  - Run: `cd apps/studio/frontend && npm test -- src/components/GraphCanvas.test.tsx`
  - _Requirements: R3, R4, R10_

- [x] 0.3 Update canvas authoring tests for source-shaped clean node creation.
  - Files: `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.test.ts`
  - Required RED cases:
    - new node phase refs remain `depends_on: []` and `output` absent
    - LOGIC scaffold includes `io` and `actions`
    - AGENT scaffold includes `io`, `<role>`, and `<goal>`
    - SUBGRAPH scaffold includes `path` and `io`
    - deprecated fields are not emitted
  - Run: `cd apps/studio/frontend && npm test -- src/components/GraphCanvas/canvas-authoring.test.ts`
  - _Requirements: R5, R10_

- [x] 0.4 Add editor dirty-buffer stability test.
  - Files: `apps/studio/frontend/src/components/studio/Workspace.test.tsx` or `LazyMonacoPanel.test.tsx`
  - Required RED case:
    - same-file `skill_changed` does not overwrite an open dirty buffer before autosave settles
  - Run: `cd apps/studio/frontend && npm test -- src/components/studio/Workspace.test.tsx src/components/studio/LazyMonacoPanel.test.tsx`
  - _Requirements: R6, R10_

- [x] 0.5 Add serializer tests for pre-compile invalid topology tolerance.
  - Files: existing backend/engine serializer tests, chosen after inspection
  - Required RED cases:
    - topology serialization can persist a self-dependency
    - topology serialization can persist a cycle
  - Run: targeted `uv run pytest ...`
  - _Requirements: R2, R3, R9, R10_

## Phase 1: Remove Auto Compile From Authoring

- [x] 1.1 Remove `compileSkillById` calls from source authoring write paths.
  - Files: `apps/studio/frontend/src/components/studio/Workspace.tsx`
  - Keep `clearStaleCompileProjection` after source writes.
  - Keep manual Compile unchanged.
  - Run: `cd apps/studio/frontend && npm test -- src/components/studio/Workspace.test.tsx`
  - _Requirements: R2_

- [x] 1.2 Re-evaluate build stage derivation from realtime lint.
  - Files: `apps/studio/frontend/src/components/studio/Workspace.tsx`
  - Ensure realtime lint pass does not masquerade as manual compile pass if it unlocks Compile/Predict incorrectly.
  - Run: `cd apps/studio/frontend && npm test -- src/components/studio/Workspace.test.tsx`
  - _Requirements: R2, R6_

## Phase 2: Make Canvas Render Invalid Source

- [x] 2.1 Change layout cycle handling to fallback render.
  - Files: `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx`
  - Keep nodes/edges visible.
  - Replace blocking overlay with non-blocking diagnostic.
  - Run: `cd apps/studio/frontend && npm test -- src/components/GraphCanvas.test.tsx`
  - _Requirements: R3_

- [x] 2.2 Allow boundary edge reconnect.
  - Files:
    - `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx`
    - `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts`
  - Reuse boundary semantics from connect/disconnect.
  - Run: `cd apps/studio/frontend && npm test -- src/components/GraphCanvas.test.tsx src/components/GraphCanvas/canvas-authoring.test.ts`
  - _Requirements: R4_

## Phase 3: Fix Source-Shaped Scaffolds

- [x] 3.1 Update default phase markdown.
  - File: `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts`
  - Add required MVP1 source fields while keeping topology clean.
  - Run: `cd apps/studio/frontend && npm test -- src/components/GraphCanvas/canvas-authoring.test.ts`
  - _Requirements: R5_

- [x] 3.2 Confirm new node creation never auto-connects.
  - Files:
    - `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts`
    - `apps/studio/frontend/src/components/studio/Workspace.test.tsx`
  - Run: `cd apps/studio/frontend && npm test -- src/components/GraphCanvas/canvas-authoring.test.ts src/components/studio/Workspace.test.tsx`
  - _Requirements: R5_

## Phase 4: Stabilize Editor And Selection

- [x] 4.1 Protect dirty editor buffers from same-file refresh.
  - Files:
    - `apps/studio/frontend/src/components/studio/Workspace.tsx`
    - possibly `apps/studio/frontend/src/components/studio/WorkspaceContext.ts`
  - Track dirty state separately from in-flight save state.
  - Run: `cd apps/studio/frontend && npm test -- src/components/studio/Workspace.test.tsx src/components/studio/LazyMonacoPanel.test.tsx`
  - _Requirements: R6_

- [x] 4.2 Ensure empty canvas selection is graph Properties, not editor open.
  - Files:
    - `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx`
    - `apps/studio/frontend/src/components/studio/Workspace.tsx`
    - `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx`
  - Run: `cd apps/studio/frontend && npm test -- src/components/GraphCanvas.test.tsx src/components/studio/Workspace.test.tsx`
  - _Requirements: R8_

## Phase 5: Relax Serializer Pre-Compile Semantics

- [x] 5.1 Remove cycle/self-dependency rejection from graph topology serialization.
  - Files:
    - `packages/graph-agent/src/graph_agent/core/graph_serializer.py`
    - `apps/studio/backend/app/services/skills.py` if error mapping changes
  - Keep optimistic hash and path safety checks.
  - Run: targeted backend/engine serializer tests.
  - _Requirements: R2, R3, R9_

## Phase 6: Verification

- [x] 6.1 Run focused frontend tests.
  - Run: `cd apps/studio/frontend && npm test -- src/components/GraphCanvas.test.tsx src/components/GraphCanvas/canvas-authoring.test.ts src/components/studio/Workspace.test.tsx src/components/studio/panels/phase-frontmatter.test.ts src/components/studio/panels/PropertiesPanel.fields.test.tsx src/components/nodes/buildEdges.test.ts`

- [x] 6.2 Run frontend gates.
  - Run: `cd apps/studio/frontend && npm run lint`
  - Run: `cd apps/studio/frontend && npm run typecheck`
  - Run: `cd apps/studio/frontend && npm test`
  - Run: `cd apps/studio/frontend && npm run build`

- [ ] 6.3 Manually verify in the existing Tauri app session if present.
  - Do not start a duplicate Tauri app if one is already running.
  - Check:
    - editor typing including spaces
    - create node has no auto edges
    - connect/reconnect to Output
    - cyclic graph remains visible before Compile
    - manual Compile reports diagnostics
    - opening/closing editor does not refit canvas

- [x] 6.4 Update `docs/development/FRONTEND_UI_SPEC.md` only if the implementation introduces a reusable frontend rule not already present.
  - _Requirements: project frontend SOP_
