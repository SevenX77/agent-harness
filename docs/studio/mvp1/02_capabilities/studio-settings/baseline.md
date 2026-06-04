# studio-settings Baseline

Status: broad UI/backend live, but the canonical MVP1 state model and Copilot role handling are not aligned yet.

Source workflow: `01_workflows/00_settings-ux-spec.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Settings shell | Settings content renders General, API Keys, LLM Roles, and Copilot tabs. | `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:37`, `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:62` |
| Settings overlay | Workspace mounts Settings over the center area when selected. | `apps/studio/frontend/src/components/studio/Workspace.tsx:496` |
| Load/save | Settings page loads credentials/roles, debounces saves, and listens to registry/roles websocket events. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:398`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:444` |
| Provider card | API Keys card owns key visibility, copy, endpoint, test, and get-models controls. | `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:907`, `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:1001` |
| Frontend state enum | Frontend provider state still uses `ready/untested/cooling_down/needs_setup/off`. | `apps/studio/frontend/src/api/llm.ts:3` |
| Backend state enum | Backend projection uses the same five-state enum with `needs_setup`. | `apps/studio/backend/app/services/llm_state_projection.py:12` |
| Role materializer | Materializer skips `needs_setup/off`, keeps cooling-down routes with warning, and builds fallback chains. | `apps/studio/backend/app/services/llm_role_materializer.py:51`, `apps/studio/backend/app/services/llm_role_materializer.py:85` |
| LLM HTTP API | Backend exposes registry, roles, endpoint tests, model groups, and role tests. | `apps/studio/backend/app/routers/llm.py:312`, `apps/studio/backend/app/routers/llm.py:899` |
| Copilot tab | Copilot tab derives roles from model groups, but ignores save status/error and can rekey role names incorrectly. | `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:70`, `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:219` |
| Copilot SDK test | Backend role test uses an Anthropic probe path distinct from the real Copilot service session path. | `apps/studio/backend/app/routers/llm.py:2150`, `apps/studio/backend/app/services/copilot.py:201` |

## Current Coverage

- live: settings shell, credential CRUD, endpoint/model tests, roles save, websocket refresh, copilot role tab.
- stale: five-state provider projection, fake/copilot test divergence, role key prefix bug.
- target gap: canonical six-state model and full role-fit/materializer projection in the visible UI.

## Known Drift

- MVP1 settings spec defines a six-state canonical state; current code still has `needs_setup` and lacks `historical_ready`/`failed(reason)` (`apps/studio/backend/app/services/llm_state_projection.py:12`).
- Copilot role save can lose the `copilot_` naming boundary, while backend split logic depends on it (`apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:219`, `apps/studio/backend/app/routers/llm.py:909`).
