# compile-lint Baseline

Status: live for lint/compile trigger and stage color; target error presentation is not implemented.

Source workflows: `01_workflows/03_compile.md`, `01_workflows/02_authoring.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Debounced lint | Editor markdown triggers `/lint` after 800ms and publishes status through sessionStorage/event. | `apps/studio/frontend/src/hooks/useDebouncedLint.ts:30`, `apps/studio/frontend/src/hooks/useDebouncedLint.ts:48` |
| Lint API | Lint hook posts to `/skills/{skill_id}/lint`. | `apps/studio/frontend/src/hooks/useDebouncedLint.ts:49` |
| Manual compile | Center Compile calls `compileSkill`, sets compile stages, stores errors, and toasts result. | `apps/studio/frontend/src/components/studio/Workspace.tsx:397`, `apps/studio/frontend/src/api/client.ts:83` |
| Stage derivation | Workspace derives stage from explicit compile state, otherwise reads lint status. | `apps/studio/frontend/src/components/studio/Workspace.tsx:429` |
| Center gate | Center action bar gates Compile, Predict, Run by stage. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:31`, `apps/studio/frontend/src/components/studio/center-action-bar.tsx:62` |
| Old error panel | Compile errors render in a bottom floating panel, not a drawer. | `apps/studio/frontend/src/components/studio/Workspace.tsx:531`, `apps/studio/frontend/src/components/studio/Workspace.tsx:571` |
| Backend compile | Skill router exposes compile and graph/lint routes through FastAPI. | `apps/studio/backend/app/routers/skills.py:109`, `apps/studio/backend/app/routers/lint.py:13` |
| Engine compile | Studio backend delegates compile to graph-agent compiler. | `apps/studio/backend/app/services/skills.py:313`, `packages/graph-agent/src/graph_agent/core/compiler.py:41` |

## Current Coverage

- live: 800ms lint, manual compile, compile-pass/fail stage, Predict gate from compile-pass.
- stale: bottom error panel still exists; no drawer; compile toasts still global.
- missing: canvas node marker, property-field marker, Monaco line marker, copyable compile drawer.

## Known Drift

- Workflow requires three contextual error locations plus a drawer; current UI only shows center button color/toast/floating panel (`apps/studio/frontend/src/components/studio/Workspace.tsx:571`).
- Predict-pass is never set because Predict is still a stub; Run remains unreachable through the intended gate (`apps/studio/frontend/src/components/studio/Workspace.tsx:537`).
