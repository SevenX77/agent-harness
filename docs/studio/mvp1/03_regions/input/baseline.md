# input Baseline

Status: current panel is a small Input panel with fake/static file projection and schema inference; MVP1 target is broader i/o panel.

Source workflows: `01_workflows/02_authoring.md`, `01_workflows/04_run-and-verify.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Panel route | `Panels` routes `activePanel === "input"` to `InputPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:34` |
| Title | Panel title is still "Input". | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:72`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:78` |
| File rows | Panel projects `input/sample.json` and `input/schema.json` through `inputFiles`. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:73`, `apps/studio/frontend/src/components/studio/panels/panel-files.ts:70` |
| Schema inference | User can paste/drop JSON and see inferred schema, but there is no writeback. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:18`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:28` |
| File open | Input file rows open editor through `onFileOpen`. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:83`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:86` |
| Backend validation | Backend validates input data/file against schema. | `apps/studio/backend/app/routers/skills.py:454` |
| Predict/run gap | Predict/Run buttons do not consume selected input from this panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:537`, `apps/studio/frontend/src/components/studio/Workspace.tsx:538` |
| Batch orphan | BatchRunner can list inputs and run batch but is not mounted here. | `apps/studio/frontend/src/components/playground/BatchRunner.tsx:33`, `apps/studio/frontend/src/hooks/useBatchRun.ts:73` |

## Current Region Ownership

- Owns: target i/o panel for test input files, schema, per-node i/o config, output artifacts, golden JSON/settings, single/batch run input selection.
- Current code only owns: input file rows and local schema inference demo.

## Known Drift

- Workflow renames/expands this to i/o panel; current UI still says "Input" and lacks output/golden settings (`apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:78`).
- Input/predict/run should use configured files; current buttons ignore the panel (`apps/studio/frontend/src/components/studio/Workspace.tsx:537`).
