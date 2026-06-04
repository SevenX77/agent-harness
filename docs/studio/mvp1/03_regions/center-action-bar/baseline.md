# center-action-bar Baseline

Status: live for stage gating visual; Predict/Run handlers are stubs and compile errors still use a bottom floating panel.

Source workflows: `01_workflows/03_compile.md`, `01_workflows/04_run-and-verify.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Stage type | Center action bar knows idle, compile, predict, and run stages. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:4` |
| Gate derivation | `deriveButtons` enables Compile, Predict, or Run based on stage. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:31` |
| Buttons | Component renders Compile, Predict, and Run buttons with lucide icons. | `apps/studio/frontend/src/components/studio/center-action-bar.tsx:62`, `apps/studio/frontend/src/components/studio/center-action-bar.tsx:73` |
| Stage source | Workspace derives stage from manual compile state or debounced lint status. | `apps/studio/frontend/src/components/studio/Workspace.tsx:429` |
| Compile handler | Compile invokes backend compile and sets compile-pass/fail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:397` |
| Predict/Run handlers | Predict and Run currently call `console.info`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:537`, `apps/studio/frontend/src/components/studio/Workspace.tsx:538` |
| Error panel | Current compile errors render as a bottom floating panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:531`, `apps/studio/frontend/src/components/studio/Workspace.tsx:571` |

## Current Region Ownership

- Owns: centered primary workflow controls, stage gate visualization, compile drawer target.
- Does not own: actual predict/run data config, compile engine rules, trace panel.

## Known Drift

- Workflow deletes the bottom floating compile error panel and replaces it with a drawer (`apps/studio/frontend/src/components/studio/Workspace.tsx:571`).
- Predict-pass is never set, so Run cannot become the intended next action (`apps/studio/frontend/src/components/studio/Workspace.tsx:537`).
