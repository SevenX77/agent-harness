# copilot Baseline

Status: live side panel chat with websocket and model picker; session isolation, disk persistence, and thinking block folding are fully active.

Source workflows: `01_workflows/00_settings-ux-spec.md`, `01_workflows/04_run-and-verify.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Shell mount | Workspace mounts CopilotPanel in a right resizable panel when open. | `apps/studio/frontend/src/components/studio/Workspace.tsx` |
| Skill prop context | CopilotPanel and hook context resolve workspace and skill identity properly using resolveWorkspaceIdentity. | `apps/studio/frontend/src/hooks/useCopilot.ts` |
| Panel | CopilotPanel shows connection status, active session messages, input box, model selector, and manages session switching. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx` |
| Registry role | Panel loads registry and resolves to selected model group (using `copilot_` prefix). | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx` |
| Send | Submit sends draft through `useCopilot` with selected route id. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx` |
| Websocket | `useCopilot` opens `/copilot/ws`, reconnects, queues text/thinking deltas, and appends events. | `apps/studio/frontend/src/hooks/useCopilot.ts` |
| View context | `useCopilotContext` debounces current view context to `/copilot/context`. | `apps/studio/frontend/src/hooks/useCopilotContext.ts` |
| Tool/diff bubbles | Tool calls and diff summaries render inside messages. | `apps/studio/frontend/src/components/copilot/tool-call-bubble.tsx`, `apps/studio/frontend/src/components/copilot/diff-bubble.tsx` |

## Current Region Ownership

- Owns: chat panel UI, message rendering, model picker in chat, tool/diff/thought bubbles, input composer, session store.
- Does not own: Settings Copilot tab, backend route/materializer, full capability decisions.

## Known Drift

- E2E Skill Card Selection: Welcoming screen skill card has a compound name preventing exact regex match, registered as deferred (blocked-on-engine-mvp1-baseline).
- Attach file and Add context buttons are visible but not wired to a real picker/context selection flow (`apps/studio/frontend/src/components/copilot/copilot-panel.tsx`).
