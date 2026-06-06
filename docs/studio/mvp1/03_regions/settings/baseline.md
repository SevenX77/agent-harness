---
module: 03_regions/settings
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；Settings shell live；前后端/界面仍有旧 `needs_setup` 与局部易失状态，Copilot tab 还有保存/role-key drift ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent · apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:SettingsPage · apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:ProviderCard · apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:RoleCardList · apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:CopilotTab · apps/studio/frontend/src/api/llm.ts:ProviderUiState
units: [settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity, i18n-error-code-ui-copy]
---

# settings — Baseline（当下代码实现逻辑）

> **Scope**: Settings region 的 General/API Keys/LLM Roles/Copilot tab、状态文案与运行时设置 UI。
> **现状一句话**: Settings shell live；前后端/界面仍有旧 `needs_setup` 与局部易失状态，Copilot tab 还有保存/role-key drift ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Shell | Settings page content renders tab nav and close button. | `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L37）`, `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L46）` |
| Tabs | General, API Keys, LLM Roles, and Copilot tabs are routed in the settings shell. | `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L48）`, `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L80）` |
| Save loops | Settings debounces credential and role saves and handles recoverable stale route errors. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:cached（L398）`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:cached（L401）` |
| Refresh | Settings refreshes credentials/roles on focus and registry websocket events. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:cached（L420）`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:handleFocus（L444）` |
| API Keys card | ProviderCard owns key visibility, endpoint, test, get-models, and route status display. | `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:tag（L907）`, `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:tag（L1001）` |
| Roles list | RoleCardList groups roles and supports add role flows. | `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:RoleCardList（L20）`, `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:roleGroups（L65）` |
| Copilot tab | CopilotTab builds copilot model cards from roles/model groups and runs route tests. | `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:realCopilotRoles（L116）`, `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:testRoleRoutes（L266）` |
| State drift | Frontend/backend state enum still uses `needs_setup`. | `apps/studio/frontend/src/api/llm.ts:llm（L3）`, `apps/studio/backend/app/services/llm_state_projection.py:llm_state_projection（L12）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Shell | Settings page content renders tab nav and close button. | `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L37）`, `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L46）` |
| Tabs | General, API Keys, LLM Roles, and Copilot tabs are routed in the settings shell. | `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L48）`, `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L80）` |
| Save loops | Settings debounces credential and role saves and handles recoverable stale route errors. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:cached（L398）`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:cached（L401）` |
| Refresh | Settings refreshes credentials/roles on focus and registry websocket events. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:cached（L420）`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:handleFocus（L444）` |
| API Keys card | ProviderCard owns key visibility, endpoint, test, get-models, and route status display. | `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:tag（L907）`, `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:tag（L1001）` |
| Roles list | RoleCardList groups roles and supports add role flows. | `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:RoleCardList（L20）`, `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:roleGroups（L65）` |
| Copilot tab | CopilotTab builds copilot model cards from roles/model groups and runs route tests. | `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:realCopilotRoles（L116）`, `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:testRoleRoutes（L266）` |
| State drift | Frontend/backend state enum still uses `needs_setup`. | `apps/studio/frontend/src/api/llm.ts:llm（L3）`, `apps/studio/backend/app/services/llm_state_projection.py:llm_state_projection（L12）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| State drift | Frontend/backend state enum still uses `needs_setup`. | `apps/studio/frontend/src/api/llm.ts:llm（L3）`, `apps/studio/backend/app/services/llm_state_projection.py:llm_state_projection（L12）` |

## 当前边界（settings 现在不是什么）
- 公共 materialize/6 态内核归 gateway ③b。
- Settings region 不拥有 copilot chat runtime。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 六态 | UI/API 仍有 `needs_setup` 旧态 ⚠️ | 六态标签和错误 copy 一致 |
| role materialization UI | 局部易失 routeStatus/role key 风险 ⚠️ | 显示来自 ③b/③a 单一投影，不本地猜真相 |
| Copilot settings | Copilot test/save 仍有路径差异 ⚠️ | 真实 SDK smoke 结果在 Copilot tab 可见 |
> **验"是否按目标改了"**：1. 六态；2. role materialization UI；3. Copilot settings。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent` → `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:SettingsPage` → `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:ProviderCard` → `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:RoleCardList` → `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:CopilotTab` → `apps/studio/frontend/src/api/llm.ts:ProviderUiState`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-settings)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `studio-settings` · `gateway` · `llm-copilot-http-api` · `i18n`
