# local-history Baseline

Status: live for local git snapshot list and revert; README-era ownership of run detail/batch summary is not reflected in mounted code.

Source workflows: `01_workflows/06_eval.md`, `01_workflows/04_run-and-verify.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Panel route | Panels routes `activePanel === "local-history"` to `HistoryPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:40` |
| Re-export | Studio panel re-exports shared history component. | `apps/studio/frontend/src/components/studio/panels/HistoryPanel.tsx:1` |
| Local history view | View renders snapshot count, refresh, list, selected snapshot, and revert button. | `apps/studio/frontend/src/components/history/HistoryPanel.tsx:51`, `apps/studio/frontend/src/components/history/HistoryPanel.tsx:130` |
| Local history hook | Component uses `useLocalHistory` and calls revert with toast feedback. | `apps/studio/frontend/src/components/history/HistoryPanel.tsx:156`, `apps/studio/frontend/src/components/history/HistoryPanel.tsx:161` |
| Backend history | Backend exposes history and revert endpoints. | `apps/studio/backend/app/routers/skills.py:397`, `apps/studio/backend/app/services/skills.py:397` |
| Run detail orphan | RunDetailDrawer exists separately with Replay/Compare/Export but is not mounted here. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:27`, `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:54` |
| Batch summary orphan | BatchSummary exists separately and is not mounted here. | `apps/studio/frontend/src/components/history/BatchSummary.tsx:32`, `apps/studio/frontend/src/components/history/BatchSummary.tsx:64` |

## Current Region Ownership

- Owns: local git snapshot list, selection, revert, run-autocommit visibility.
- Ownership conflict: run detail and batch summary appear closer to `timeline`/`input` than local git history.

## Known Drift

- Workflow assigns successful-run autocommit to publish/save; Local History shows snapshots but does not explain git status (`apps/studio/frontend/src/components/history/HistoryPanel.tsx:67`).
- Run detail drawer has Compare/Replay/Export but no integration point (`apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:54`).
