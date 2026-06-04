# copilot Baseline

Status: live side panel chat with websocket and model picker; current skill context has a Workspace prop mismatch risk.

Source workflows: `01_workflows/00_settings-ux-spec.md`, `01_workflows/04_run-and-verify.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Shell mount | Workspace mounts CopilotPanel in a right resizable panel when open. | `apps/studio/frontend/src/components/studio/Workspace.tsx:545` |
| Skill prop risk | CopilotPanel receives the outer `skillId` prop instead of `currentSkillId`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:554` |
| Panel | CopilotPanel shows connection status, messages, empty prompts, input box, attach/context buttons, and model picker. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:74`, `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:118` |
| Registry role | Panel loads registry and picks `copilot_chat` fallback route. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:83`, `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:90` |
| Send | Submit sends draft through `useCopilot` with selected route id. | `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:111` |
| Websocket | `useCopilot` opens `/copilot/ws`, reconnects, queues text deltas, and appends events. | `apps/studio/frontend/src/hooks/useCopilot.ts:96`, `apps/studio/frontend/src/hooks/useCopilot.ts:123` |
| View context | `useCopilotContext` debounces current view context to `/copilot/context`. | `apps/studio/frontend/src/hooks/useCopilotContext.ts:39`, `apps/studio/frontend/src/hooks/useCopilotContext.ts:53` |
| Tool/diff bubbles | Tool calls and diff summaries render inside messages. | `apps/studio/frontend/src/components/copilot/tool-call-bubble.tsx:18`, `apps/studio/frontend/src/components/copilot/diff-bubble.tsx:19` |

## Current Region Ownership

- Owns: chat panel UI, message rendering, model picker in chat, tool/diff bubbles, input composer.
- Does not own: Settings Copilot tab, backend route/materializer, full capability decisions.

## Known Drift

- Workspace prop mismatch can attach chat to stale skill when navigating subgraphs or switching current skill (`apps/studio/frontend/src/components/studio/Workspace.tsx:554`).
- Attach file and Add context buttons are visible but not wired to a real picker/context selection flow (`apps/studio/frontend/src/components/copilot/copilot-panel.tsx:200`).
