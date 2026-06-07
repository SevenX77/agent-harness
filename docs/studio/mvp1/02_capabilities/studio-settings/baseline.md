---
module: 02_capabilities/studio-settings
doc: baseline
status: FROZEN（WS-4 更新后现状；Settings UI/API 大体 live；provider/model health 已使用六态，Role Test/能力证据仍有部分 ③b 内核逻辑留在 Studio 后端巨型路由中 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:SettingsPage · apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:ProviderCard · apps/studio/frontend/src/api/llm.ts:ProviderUiState · apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState · apps/studio/backend/app/routers/llm.py:router
units: [settings-six-state-provider-health, model-group-role-materialization, node-properties-role-test, copilot-sdk-test-parity]
---

# studio-settings — Baseline（当下代码实现逻辑）

> **Scope**: Settings 运行底座：provider credentials、model groups、LLM roles、Copilot route 配置与状态投影消费。
> **现状一句话**: Settings UI/API 大体 live；provider/model health 已统一为六态，Role Settings 可表达 Thinking 三态与 context/output token intent；部分 ③b 内核逻辑仍在 Studio 后端巨型路由中 ⚠️。

## UI/UX
Settings 运行底座：provider credentials、model groups、LLM roles、Copilot route 配置与状态投影消费。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Settings shell | Settings content renders General, API Keys, LLM Roles, and Copilot tabs. | `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L37）`, `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:SettingsPageContent（L62）` |
| Settings overlay | Workspace mounts Settings over the center area when selected. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L496）` |
| Load/save | Settings page loads credentials/roles, debounces saves, and listens to registry/roles websocket events. | `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:cached（L398）`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:handleFocus（L444）` |
| Provider card | API Keys card owns key visibility, copy, endpoint, test, and get-models controls. | `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:tag（L907）`, `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:tag（L1001）` |
| Frontend state enum | Frontend provider state uses canonical `ready/historical_ready/untested/failed/cooling_down/off`;旧 `needs_setup` 不再是 API/UI state。 | `apps/studio/frontend/src/api/llm.ts:ProviderUiState` |
| Role Settings intent | Role header inline settings use local `Switch`/`RadioGroup`/`Select`/`InputGroup` to save model fallback, Thinking `off/preferred/required`, and context/output token intent. | `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleSettingsDialog.tsx:RoleSettingsPanel`, `apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCard.tsx:roleTokenLimitSummary` |
| Role Test refresh | LLM Roles flushes pending role autosave before persisted Role Test job and refreshes backend role/model-group projection after completion. | `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx:runPersistedRoleTestJob`, `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:refreshLoadedLlmRolesProjection` |
| Copilot tab | Copilot tab derives roles from model groups, but ignores save status/error and can rekey role names incorrectly — 后端分流逻辑依赖 `copilot_` 前缀边界。 | `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:CopilotTab（L70）`, `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:selectModelGroup（L219）`, `apps/studio/backend/app/routers/llm.py:_is_copilot_role（L909）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend state enum | Backend projection uses canonical `ready/historical_ready/untested/failed/cooling_down/off` and keeps reason codes separate from state labels. | `apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState` |
| Capability evidence | Registry provider routes expose availability state separately from four-state capability evidence completeness: `unknown/callable_only/partial/known`; model-group summaries include tools/structured-output support. | `apps/studio/backend/app/routers/llm.py:_capability_state`, `apps/studio/backend/app/routers/llm.py:_capability_summary` |
| Role materializer | Materializer skips `failed/off`, keeps cooling-down routes with warning, and builds fallback chains. | `apps/studio/backend/app/services/llm_role_materializer.py:materialize_role` |
| LLM HTTP API | Backend exposes registry, roles, endpoint tests, model groups, and role tests. | `apps/studio/backend/app/routers/llm.py:EndpointModelTestResponse（L312）`, `apps/studio/backend/app/routers/llm.py:apply_import_draft（L899）` |
| Role Test persistence | Persisted Role Test covers all configured model-group provider candidates, reports `failed/off` as blocked without probing, and writes third-party probe failures to route metadata/evidence for registry projection. | `apps/studio/backend/app/routers/llm.py:_role_test_entries`, `apps/studio/backend/app/routers/llm.py:_persist_third_party_role_test_failure` |
| Copilot SDK test | Backend role test uses an Anthropic probe path distinct from the real Copilot service session path. | `apps/studio/backend/app/routers/llm.py:_probe_copilot_sdk_tool_call（L2150）`, `apps/studio/backend/app/services/copilot.py:stream_query（L201）` |

## 当前边界（studio-settings 现在不是什么）
- gateway ③b 公共内核不在 Studio 复制，只引用。
- Settings 不拥有真实 copilot chat 行为；chat 归 `copilot-assist`。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 六态 | 前后端已使用 ready/historical_ready/untested/failed/cooling_down/off；`needs_setup` 不再作为状态。 | ready/historical_ready/untested/failed/cooling_down/off 六态投影 |
| capability state | Registry 已分离 availability state 与 `unknown/callable_only/partial/known` capability evidence state。 | capability evidence 与 provider/model availability 分离 |
| Role Settings / Test | Role Settings 已覆盖 Thinking 三态与 context/output token intent；Role Test 已 flush autosave、覆盖全候选并在完成后刷新后端投影。 | Role Settings intent 与 Role Test 以后端 registry/evidence 为最终事实 |
| materialize 边界 | `llm.py` 混 HTTP glue/probe/materialize/draft ⚠️ | ③b graph-agent-gateway 负责公共内核，Studio 只做 UI/策略/适配 |
| Copilot test | 探测路径与真实 chat 不等价 ⚠️ | 短 smoke 走真实 SDK session |
| Properties role shortcut | WS-4 已提供同一后端状态/测试契约；Properties 文件仍受 WS-2 文件锁约束，未在本次接入。 | Properties role 行复用同一投影与 persisted Role Test |
| 设置不挡壳 | Settings 不完整时仍可 edit/compile | predict/run/copilot/publish 显示局部 setup error |
> **验"是否按目标改了"**：1. 六态；2. capability state；3. Role Settings/Test；4. materialize 边界；5. Copilot test；6. Properties shortcut。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:SettingsPage` → `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:ProviderCard` → `apps/studio/frontend/src/api/llm.ts:ProviderUiState` → `apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState` → `apps/studio/backend/app/routers/llm.py:router`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-studio-settings)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `settings` region · `gateway` · `llm-copilot-http-api` · `copilot-assist` · `i18n`
