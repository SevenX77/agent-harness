# Studio Request Audit

Status: Living

This document tracks the audit requested for every Studio frontend request and
backend route against the project rule:

**Server-authoritative state + event-driven revalidation.** Mutable truth is read
from the server-owned source on first need for a cache key, then revalidated only
after a successful canonical write, a precise backend domain event, or an
explicit user refresh/probe/test action. UI visibility or selection state is not
truth mutation.

## Decision Rules

Allowed request triggers:

- Cold load: the first consumer of a cache key may read it once and share the
  in-flight request/result.
- Successful write: the writer may use the returned canonical snapshot or
  invalidate the exact affected cache key.
- Backend event: a committed backend change may emit a precise domain event that
  invalidates the exact affected key.
- Explicit user action: refresh, test, probe, run, compile, save, delete, import,
  export, or similar commands may call the backend.
- Scoped job status: a long-running job may use its own status stream or scoped
  polling key. It must not refresh broad truth such as registry/roles/settings as
  a progress substitute.

Forbidden request triggers:

- Component mount/unmount after the cache key is already loaded.
- Opening or closing Settings, Copilot, sidebars, drawers, tabs, or panels.
- Canvas node/edge selection, hover, focus, scroll, resize, or tab switch.
- Window focus, timer polling, WebSocket connect/reconnect, or generic resync.
- Sending implicit UI state to the backend just because the user looked at or
  selected something.

## Test Strategy

Use a shared test when it protects an architectural boundary:

- Static guard tests for deleted/forbidden request channels, such as the removed
  Copilot auto-context endpoint.
- Network-silent interaction tests for UI-only actions after cold data is loaded,
  such as node selection, panel open/close, tab switch, and dialog reopen.
- API client cache tests for shared in-flight/cold-load semantics and precise
  invalidation.
- Backend route tests when an endpoint must not exist, or when a write/event must
  be the only source of a revalidation trigger.

Use per-request tests when a request has unique semantics:

- Autosave ordering and stale-response suppression.
- Job/probe lifecycle and scoped polling.
- File writes, hash conflicts, native-fs ownership, and destructive commands.
- Provider/role/registry writes that must return and project a canonical server
  snapshot.

## Audit Ledger

| Area | Request/route | Current trigger | Verdict | Guard |
| --- | --- | --- | --- | --- |
| Copilot canvas context | `POST /api/skills/{skill_id}/copilot/context` | Canvas selection/render sent selected node/edge/lint state | Removed. UI selection is not truth mutation and must not be sent implicitly. | `CopilotContext.network-side-effect.test.ts`, `test_copilot_context_endpoint_removed.py` |
| Properties node config | `GET /api/skills/{skill_id}/node-llm-params` | Properties panel cold load | OK if shared per skill and silent on node selection after load. | `PropertiesPanel.network-side-effect.test.tsx`, client cache tests |
| Properties compare candidates | `GET /api/skills/{skill_id}/compare-candidates` | Properties panel cold load | OK if shared per skill and silent on node selection after load. | `PropertiesPanel.network-side-effect.test.tsx`, client cache tests |
| Settings app settings | `GET/PUT /api/settings` | App settings initialization / user save | OK: the hook waits for authenticated API readiness before the first read, shares the cold-load request, and saves only after explicit settings edits. | `useAppSettings.test.ts` |
| LLM registry | `GET /api/llm/registry` | Settings/API Keys/roles consumers and domain events | Partial: client reads are cached/deduped; Settings open/close, tab switch, focus, and WebSocket connect/reconnect are guarded as non-triggers. Remaining audit: all registry write paths must keep returning/projecting exact canonical snapshots. | `llm.test.ts`, `SettingsPage.controller.test.tsx`, `useStudioEventStream.test.ts` |
| LLM roles | `GET/PUT /api/llm/roles` | Settings/Copilot role consumers and role writes/events | Partial: roles reads are cached/deduped; Settings open/close, tab switch, focus, and WebSocket connect/reconnect are guarded as non-triggers. Remaining audit: role write/test/job paths need route-by-route review. | `SettingsPage.controller.test.tsx`, `useStudioEventStream.test.ts` |
| Templates | `GET /api/templates` | Template UI | Pending audit: should load only when template UI is opened or a template is used. | Required if it is mounted globally |
| Studio event stream | `WS /ws/events` | App-level domain event stream | OK for the generic-resync risk: connect/reconnect do not dispatch data refresh callbacks; only precise backend events invoke the exact handlers. | `useStudioEventStream.test.ts` |
| Copilot chat | `WS /api/skills/{skill_id}/copilot/ws` | User sends a Copilot message | OK as explicit user action; future `@` mentions must travel with the message payload, not background UI state. | Required when `@` mention payload is implemented |

## Audit Procedure

1. Inventory requests with:
   `rg -n "api\\.(get|post|put|delete|patch)|useSWR\\(|new WebSocket|wsUrl\\(" apps/studio/frontend/src`
2. Inventory backend routes with:
   `rg -n "@(router|app)\\.(get|post|put|delete|patch|websocket)" apps/studio/backend/app/routers`
3. For each request, record the trigger, server-owned truth key, invalidation
   source, and whether it needs a shared or per-request test.
4. Any request triggered by UI visibility, selection, focus, timer, reconnect, or
   generic resync is a defect until redesigned or proven scoped to an explicit
   user command/job.
