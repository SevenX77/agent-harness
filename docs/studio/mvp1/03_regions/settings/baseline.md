# settings Baseline

Status: broad live UI; canonical state model, Copilot role handling, and SDK test parity need alignment.

Source workflow: `01_workflows/00_settings-ux-spec.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Shell | Settings page content renders tab nav and close button. | `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:37`, `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:46` |
| Tabs | General, API Keys, LLM Roles, and Copilot tabs are routed in the settings shell. | `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:48`, `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:80` |
| Save loops | Settings debounces credential and role saves and handles recoverable stale route errors. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:398`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:401` |
| Refresh | Settings refreshes credentials/roles on focus and registry websocket events. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:420`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:444` |
| API Keys card | ProviderCard owns key visibility, endpoint, test, get-models, and route status display. | `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:907`, `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:1001` |
| Roles list | RoleCardList groups roles and supports add role flows. | `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:20`, `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:65` |
| Copilot tab | CopilotTab builds copilot model cards from roles/model groups and runs route tests. | `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:116`, `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:266` |
| State drift | Frontend/backend state enum still uses `needs_setup`. | `apps/studio/frontend/src/api/llm.ts:3`, `apps/studio/backend/app/services/llm_state_projection.py:12` |

## Current Region Ownership

- Owns: Settings shell, General, API Keys, LLM Roles, Copilot settings UI, save/error/loading states.
- Does not own: chat panel UI, gateway internals, predict/run behavior.

## Known Drift

- Canonical six-state model is not implemented in UI or backend projection (`apps/studio/backend/app/services/llm_state_projection.py:12`).
- CopilotTab ignores save status/error and can rekey role ids incorrectly (`apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:70`, `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:219`).
