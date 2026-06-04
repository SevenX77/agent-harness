# conflict-overwrite Baseline

Status: partial live. Sequential output overwrite conflicts and file write conflicts both exist, but they are separate paths with different UX.

Source workflows: `01_workflows/02_authoring.md`, `01_workflows/03_compile.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Sequential overwrite scan | Canvas scans graph phases for sequential output overwrites and stores a pending conflict. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:104`, `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:237` |
| Allow overwrite | Confirming adds `allow_sequential_overwrite` to the phase file and saves it. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:134`, `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:339` |
| Cancel overwrite | Canceling marks the conflicting node red locally. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:168` |
| Node popover | Skill node can show sequential overwrite warning and allow/cancel actions. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:136` |
| File conflict | Workspace stores save conflicts and offers use-remote/view-diff style handlers. | `apps/studio/frontend/src/components/studio/Workspace.tsx:264` |
| Save conflict source | `LazyMonacoPanel` detects 409 response and passes conflict payload to Workspace. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:99` |
| Backend write guard | Backend single-file write checks expected content hash and raises conflict on mismatch. | `apps/studio/backend/app/services/skills.py:410` |
| Graph write guard | Graph serialization also returns 409 on stale writes. | `apps/studio/backend/app/routers/skills.py:122` |

## Current Coverage

- live: expected-hash file conflict, graph serialization conflict, sequential overwrite warning and opt-in.
- stale: overwrite marker is written to old frontmatter shape and not unified with compile diagnostics.
- missing: single conflict taxonomy shared by canvas, editor, and compile drawer.

## Known Drift

- Sequential overwrite is currently front-end detected; engine compile should be the durable authority for invalid data flow (`apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:237`).
- The UX has two conflict paths: graph overwrite popover and file conflict dialog (`apps/studio/frontend/src/components/studio/Workspace.tsx:264`).
