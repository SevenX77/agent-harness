# state-engine Baseline

Status: front-end state exists as local hooks/stores/SWR/websocket pieces; there is no single formal state engine yet.

Source workflows: `01_workflows/01_init.md`, `01_workflows/03_compile.md`, `01_workflows/04_run-and-verify.md`, `01_workflows/05_debugging.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Runtime gate | RuntimeGate initializes runtime config and can block with splash/error. | `apps/studio/frontend/src/components/RuntimeGate.tsx:8`, `apps/studio/frontend/src/components/RuntimeGate.tsx:31` |
| Workspace state | Workspace owns selected panel, nav stack, copilot open, selected node/edge, compile stages, and open files. | `apps/studio/frontend/src/components/studio/Workspace.tsx:39`, `apps/studio/frontend/src/components/studio/Workspace.tsx:55` |
| Copilot context | Workspace sends selected node/edge/lint status into copilot context. | `apps/studio/frontend/src/components/studio/Workspace.tsx:69`, `apps/studio/frontend/src/hooks/useCopilotContext.ts:53` |
| Lint state | Lint status is published through sessionStorage and a custom event. | `apps/studio/frontend/src/hooks/useDebouncedLint.ts:6`, `apps/studio/frontend/src/hooks/useDebouncedLint.ts:12` |
| Run history state | `useRunHistory` uses SWR for run list/detail and local history. | `apps/studio/frontend/src/hooks/useRunHistory.ts:7`, `apps/studio/frontend/src/hooks/useRunHistory.ts:55` |
| Run stream state | `useRunStream` opens run websocket and buffers queue/connection state. | `apps/studio/frontend/src/hooks/useRunStream.ts:12`, `apps/studio/frontend/src/hooks/useRunStream.ts:49` |
| Copilot store | Copilot messages live in a small external store with subscribe/reset/update. | `apps/studio/frontend/src/store/copilotStore.ts:21`, `apps/studio/frontend/src/store/copilotStore.ts:27` |
| Settings events | Settings listens to `/ws/events` for registry/roles refresh. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:444` |
| Backend event channels | Backend exposes run websocket and global events websocket. | `apps/studio/backend/app/routers/websockets.py:27`, `apps/studio/backend/app/routers/websockets.py:50` |

## Current Coverage

- live: local Workspace state, SWR data, lint event bridge, run/copilot websockets, settings global event listener.
- missing: central event-to-node-state derivation, typed event bus, scoped sidecar failure model, run/debug state reducer.

## Known Drift

- Trace/debug require a shared event-to-node-state derivation; current node statuses are not driven from run events (`apps/studio/frontend/src/components/studio/Workspace.tsx:515`).
- RuntimeGate can still full-screen block the app shell (`apps/studio/frontend/src/components/RuntimeGate.tsx:31`).
