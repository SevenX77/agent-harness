# timeline Baseline

Status: mounted panel lists run history; live trace/timeline UI exists separately but is not mounted here.

Source workflow: `01_workflows/04_run-and-verify.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Panel route | Panels routes `activePanel === "timeline"` to `TimelinePanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:37` |
| Run history | TimelinePanel reads current skill id and `useRunHistory`. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:32` |
| Header/refresh | Panel shows run count and refresh button. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:39`, `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:44` |
| States | Panel has loading, error, and empty states. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:56` |
| Run rows | Panel maps run rows with status, id, relative time, duration, and tokens. | `apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:71` |
| TracePanel orphan | TracePanel can render event streams and actions but is not mounted. | `apps/studio/frontend/src/components/TracePanel.tsx:22`, `apps/studio/frontend/src/components/TracePanel.tsx:50` |
| Prompt inspector orphan | PromptInspector exists for template/variables/rendered tabs. | `apps/studio/frontend/src/components/PromptInspector.tsx:20` |
| Run detail orphan | RunDetailDrawer exists but is not opened by Timeline rows. | `apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:27` |
| Stream hook orphan | `useRunStream` exists but no mounted timeline flow consumes it. | `apps/studio/frontend/src/hooks/useRunStream.ts:49` |

## Current Region Ownership

- Owns: run history list, live trace stream, run-after full trace timeline, prompt inspector entry, selected-run summary.
- Current mounted code owns only run list.

## Known Drift

- Workflow says run starts should auto-open live trace; current Timeline is manual history only (`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:71`).
- TracePanel uses one-off hardcoded palette classes and needs design-system cleanup before mounting (`apps/studio/frontend/src/components/TracePanel.tsx:50`).
