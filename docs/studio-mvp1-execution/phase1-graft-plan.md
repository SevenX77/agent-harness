All load-bearing facts are confirmed:
- `main` `lib/tauri.ts` exports `openInCursor/openInTerminal/openInCodex/revealInFileManager/selectSkillDirectory` but **NOT** `writeWorkspaceFile` (confirms the api/client.ts RECONCILE hard-dependency).
- `isTauriRuntime` lives in `config/runtime.ts:24` (exists in main).
- `phase-frontmatter.ts` in main uses `mode` + `target_skill` + XML blocks (`python_callable`/`system_prompt`/`exit_contract`), and backend `skills.py:60` enforces `mode: Literal["logic","subgraph","skill"]` — confirms KEEP-MAIN over wave3's `path:` schema.
- main's `api/llm.ts` already declares `RoleThinkingPreference` (3-way), `RoleTokenIntentMode` (all 4 modes), and `target_context_tokens` — confirms the RoleSettingsDialog token-intent UI is contract-backed (not a contract change).

Everything checks out. Here is the execution plan.

---

# Phase 1 前端嫁接执行计划

> 基线分支：`feat/studio-mvp1-mainbased-2026-06-13`（= main #139，禁止回退其 `api/llm.ts` 三模块契约）
> 来源：wave3。共 8 个集群、约 60 个文件动作。
> 铁律：Studio 只渲染 gateway 事实；不得回退 #139 契约；不引入 Studio 自算 6 态 / mock。

---

## ① 按动作分组

### A. TAKE — 纯新增 / wave3 为唯一来源（可批量直接拷贝）

这些文件在 main 不存在，或 wave3 是 main 的严格超集且零契约冲突。逐字复制即可，但**必须连同各自的硬依赖一起落地**（见括注）。

| # | 文件 | 类别 | 硬依赖（必须同批） |
|---|------|------|---------------------|
| 1 | `src/i18n.ts` | i18n bootstrap（i18next 初始化 + localStorage 语言检测，key=`studio.language`） | 4 个 locale json + react-i18next.d.ts |
| 2 | `src/locales/en/errors.json` | 错误码→英文展示串查表（codes/httpStatus/status/fallbacks，**纯标签非状态推导**） | — |
| 3 | `src/locales/en/settings.json` | 设置面板 UI 串（含 copilot tab 标签，**是 i18n 标签非被删的 mock 模块**） | — |
| 4 | `src/locales/zh-CN/errors.json` | errors.json 简体中文镜像 | — |
| 5 | `src/locales/zh-CN/settings.json` | settings.json 简体中文镜像 | — |
| 6 | `src/@types/react-i18next.d.ts` | TS 模块增强（编译期类型安全翻译 key），从 `../i18n` 导入类型 | i18n.ts + 4 locale json（否则 tsc 报错） |
| 7 | `src/components/studio/settings/copilot/copilot-role-derivation.ts` | **替代 mock 的核心**：`deriveCopilotCandidateGroups` 读 gateway `ModelGroup.provider_models` 投影成预览，`pm.ui_state`→agentStatus（已核 main api/llm.ts 字段齐全） | 见②高风险说明（activeRouteIds 客户端重算需谨慎） |
| 8 | `src/components/studio/settings/copilot/CopilotModelGroupCard.tsx` | 纯渲染卡片；wave3 仅把 mock 导入改成 `./copilot-role-derivation` + 本地 `type CopilotAgentStatus = string` | copilot-role-derivation.ts |
| 9 | `src/components/studio/settings/copilot/copilot-role-test.ts` | 角色测试逻辑（已跑 main 真实 role-test job API）；wave3 仅第 8 行去 mock 导入 | copilot-role-derivation.ts |
| 10 | `src/types/copilot.ts` | wave3 是 main 纯超集：新增 `CopilotThinkingDeltaEvent`（thinking_delta）入联合 + normalizeCopilotEvent 分支 | 被 copilot-panel.tsx 的 thinking_delta 分支依赖 |
| 11 | `src/lib/llm-error-messages.ts` | 把硬编码英文目录重构为走 `i18n.t()` 读 errors 命名空间；签名/消费类型与 main 一致 | **硬依赖 i18n 集群**（否则编译断） |
| 12 | `src/components/ui/save-status-badge.tsx` | 纯展示 Badge（`useTranslation('settings')`），渲染传入 SaveStatus | i18n settings locales + `hooks/useDebouncedCredentialsSave`（main 已有） |
| 13 | `src/components/studio/workspace-identity.ts` | 纯前端工具：解析/构造 `local-workspace:<skillId>:<root>` 选择串 | 被 WelcomePage / Workspace 引用 |
| 14 | `src/components/studio/WorkspaceContext.tsx` | `OpenFile` 接口新增可选 `workspaceRoot?: string \| null`，向后兼容 | 下游 Workspace/LazyMonacoPanel/SplitEditor 已读该字段 |
| 15 | `src/components/studio/SplitEditor.tsx` | 加性：透传 `statusByNodeId`（main GraphCanvas 已支持）+ `file.workspaceRoot` | — |
| 16 | `src/components/studio/LazyMonacoPanel.tsx` | 加性：`workspaceRoot` 兜底 + 外部 value 同步 effect 真 bug 修复（lastPathRef/lastHashRef 防覆盖在途编辑） | — |
| 17 | `src/index.css` | 为 `[data-copilot-provider-card][data-agent-sdk-status=testing]` 追加 ::after 动画（main 卡片已用这俩 data 属性） | — |

> 注意 #2/#3：`errors.json` 的 `status` 块（untested/unverified_manual/ok/error…）和 `settings.json` 的 `copilot` 块是**人类可读展示串**，不是被 wave3 删掉的 mock-copilot-data / copilot-role-state 状态机。保留它们安全。

### B. DELETE — wave3 已删，本次同步删除

| 文件 | 删除理由 | 触发的连锁 |
|------|----------|------------|
| `src/components/studio/settings/copilot/mock-copilot-data.ts` | 硬编码假 roles/routes/agentStatus + isClaudeAgentSdkCompatibleRoute 白名单 = 被禁的 Studio 自造真理；已被 copilot-role-derivation 取代 | 所有消费者（CopilotModelGroupCard/copilot-role-test/CopilotTab）改指向 derivation |
| `src/components/studio/settings/copilot/copilot-role-state.ts` | 平行的 Studio 自有角色状态机（建在 mock 之上），Studio 持有自算角色真理 = 禁止；wave3 已折叠进 CopilotTab 直接驱动 `data.roles` | 唯一消费者 `copilot-role-state.test.ts` 随之消失（grep 已确认无生产代码外部引用） |

> 删除前 grep 复核一次确保无新增外部引用。

### C. KEEP-MAIN — 保留 main，wave3 无可取（无需动作，仅登记）

这些文件 **main 是更优/超集，或 wave3 引用了 main 契约里不存在的旧 6 态枚举值（取 wave3 = 类型错误 + 回退契约）**。**不做任何嫁接动作**，列出仅供执行者跳过、并知道为何跳过。

| 文件 | 跳过理由（一句话） |
|------|---------------------|
| `api/types.ts` | main 严格超集（多 `NodeGoldenResult` + `CompareResult.node_results`），wave3 零新增 |
| `settings/llm-roles/RoleBadges.tsx` | main 含 wave3 的 ThinkingBadge + 额外 `RoleSaveStatusBadge`，取 wave3 会丢后者 |
| `settings/llm-roles/AdvancedModelBundlesSection.tsx` | 仅 `summarizeProviderStates()` 种子键不同；main 键匹配 main `status_summary` 契约，wave3 不过类型检查 |
| `settings/llm-roles/RoleTestResultPanel.tsx` | 仅 `providerUiStateLabel()` 分支不同；main 匹配 main 枚举，wave3 引用 historical_ready/failed（main 无） |
| `settings/llm-roles/role-route-status.tsx` | `deriveRoleRouteStatus` 是 gateway 事实的展示格式化；wave3 多 historical_ready/failed 分支需枚举先扩 |
| `settings/llm-roles/AvailableModelsSidebar.tsx` | 状态映射 helper 引用 historical_ready/failed（main 无），整文件不取；空 providers `.filter()` 守卫可选单独 cherry-pick（不带枚举） |
| `settings/provider-utils.ts` | 仅 `newProviderId()` 兜底（main 确定性计数器 > wave3 Math.random） |
| `settings/role-utils.ts` | `providerStateRank()` wave3 排 6 态含 historical_ready/failed（main 枚举已删），取 wave3 = 类型错误 + 回退旧 6 态 |
| `api-keys/AddProviderForm.tsx` | 仅 `newProviderCodeSuffix()` 兜底（main 计数器 > wave3 random） |
| `api-keys/ProviderCard.tsx` | 45 行差异全是状态枚举分歧；main 用 `RouteDisplayStatus=RouteStatus\|'unknown'\|'testing'` 直接映射 gateway RouteStatus（正确），wave3 按旧 ProviderUiState 派生 = 回退契约 |
| `panels/AssetsPanel.tsx` | 两版等价（仅 .sort 写法）；**main 自带 mock 兜底（硬编码 intent_classifier/translator_subgraph + 写死本地路径），登记为后续单独清理项，不在本次嫁接** |
| `panels/PropertiesPanel.tsx` | main 表单字段全且对齐后端（logic→python_callable / agent→system_prompt+exit_contract+tools / subgraph→target_skill）；wave3 表单退化（D8 旧字段残留） |
| `panels/panel-files.ts` | main `inputFiles()` 从 gateway `manifest.io` 派生 = 渲染事实；wave3 从 skillDetail.files 捞另一套来源 |
| `panels/phase-frontmatter.ts` | **D8 震中**。已核：main 用 `mode`+`target_skill`+XML 块，后端 `skills.py:60` 强制 `mode: Literal["logic","subgraph","skill"]`；wave3 的 `path:`/无 mode schema 连自己的 build-nodes 都对不上，整体丢弃 |
| `GraphCanvas/canvas-authoring.ts` | phase-frontmatter 的写盘侧同冲突；wave3 用废弃的 `io:`/`path:` schema，不能单独嫁接 |
| `components/nodes/SkillNode.tsx` | wave3 多传 `childGraph={data.childGraph}`，但 types.ts 无此字段、build-nodes 不写入 = 断头线 |
| `components/studio/SubgraphInline.tsx` | wave3 引入 `childGraph` 死分支（依赖不存在的字段）；main 虽硬编码 entry/execute/return 假行（登记后续清理），但不引入未接线字段 |
| `store/themeStore.ts` | 仅 sourceId 生成（main crypto 回退 > wave3 random） |
| `config/runtime.ts` | wave3 仅 Tauri 分支裸 try/catch（无日志，直接搬违反"禁止静默降级"）；main 是集成基线 |
| `hooks/useToasts.ts` | 仅 `newToastId` 兜底（main 计数器 > wave3 random） |
| `utils/presets.ts` | 仅 `newPresetId` 兜底（main 计数器 > wave3 random） |

---

### D. RECONCILE — 逐个手动合并（保 main 为基，叠 wave3 增量）

#### R1. `src/main.tsx` — i18n 集群 · 风险 low
- 单点合并。以 main 结构为基，插入两行：
  1. `import { i18nReady } from './i18n'`
  2. 在 `createRoot(...)` 前紧邻加 `await i18nReady`
- 保留 main 现有 import 顺序与 tunnel-token / configureApiToken bootstrap（两版一致）。
- 确认 Vite/esbuild target 允许顶层 await（wave3 已用）。

#### R2. `src/api/client.ts` — api-layer · 风险 low（**有硬依赖**）
- 以 main 为基（X-Studio-User-ID header、token 拦截器、所有 skill/golden/run 端点不动）。
- 重新加回 wave3 在 **`writeSkillFile` 上的 Tauri 分支**：`isTauriRuntime()` 时调 `writeWorkspaceFile` 并把 Tauri HashConflict 错误映射成合成 `AxiosError(409)`，使下游 hash-conflict UI 统一；否则走原 `api.post`。
- 补两个类型导入：`AxiosResponse`, `InternalAxiosRequestConfig`。
- **硬依赖（已核实）**：main `lib/tauri.ts` **不导出** `writeWorkspaceFile`（只有 openInCursor/openInTerminal/openInCodex/revealInFileManager/selectSkillDirectory）。**本文件不能单独落地——必须与 R10（lib/tauri.ts 合并加 writeWorkspaceFile）同批**，否则编译断链。`isTauriRuntime` 已在 `config/runtime.ts:24`（main 有）。

#### R3. `src/components/studio/settings/copilot/CopilotTab.tsx` — settings-copilot · 风险 low
- 取 wave3 为基（驱动 `deriveCopilotCandidateGroups(modelGroups, credentials)` 替代 mock；用 `applyCopilotModelGroupSelection`；写 `role.models` + `fallback_chain`；走 i18n `t()`）。
- 合并对账（对 main #139）：
  1. `RolesData`/`role.models`/`role.fallback_chain`/`intent.provider_preference` 形状仍匹配 main `api/llm.ts RoleDefinition`；wave3 写 `role.models[id].providers` 和 `fallback_chain[].route_id` 须对齐。
  2. **保留 `routeStatusOverrides`**——它仅由 `copilotRouteStatusesFromJob(job)`（真实后端 role-test 结果）填充，**非 mock 状态，合规**。
  3. `activeRoles` 从 `data.roles` 过滤 `role_kind==='copilot'`（gateway 真理）；确认 wave3 已删的 name-allowlist / `mockCopilotRoles.slice(0,2)` 兜底**没有**在合并中复活。
  4. i18n key `copilot.title/description/claudeAgentSdk`、`llmRoles.validationFailed` 须在 locales 中存在（i18n 集群已带）。

#### R4. `src/components/studio/settings/types.ts` — settings-apikeys-utils · 风险 low
- 在 main `types.ts` 第 54 行 `onBeforeRoleTest` 后补一行：`onAfterRoleTest: () => Promise<void> | void`
- 不动其余字段（CredentialsState/ModelGroup/RolesData 仍引用 main api/llm 契约）。
- 这是 LlmRoles 集群（SettingsPageContent/SettingsPage/LlmRolesTab）编译所需，且 gateway 安全（仅测试后 refetch 服务端投影）。

#### R5. `src/components/studio/settings/api-keys/ApiKeysTab.tsx` — settings-apikeys-utils · 风险 none
- 在 main UI 骨架上，把硬编码英文串换成 `t('apiKeys.*')`，引入 `useTranslation`。
- `SaveStatusBadge` 二选一：**推荐**带入共享 `@/components/ui/save-status-badge`（=A#12，i18n 感知）并删掉 main 内联版；或保留 main 内联版只改文案。前者更一致。
- 前置依赖：i18n 集群（locales `apiKeys.*` + `saveStatus.*`、i18n.ts、react-i18next）先 TAKE。

#### R6. `src/hooks/useCopilot.ts` — hooks-store · 风险 low（**依赖 R7+A#13**）
- 以 main 为基，叠 wave3 多会话 UI（`sessions/activeSessionId/newSession/switchSession/persistenceError`）+ workspace-identity 上下文。
- **不动 WS 协议**（两版一致：`wsUrl('/api/skills/:id/copilot/ws')` + `{user_message, model_override}` + `normalizeCopilotEvent`）。
- 冲突点：wave3 useEffect 调 `copilotStore.setContext+newSession`（基于 `resolveWorkspaceIdentity(skillId).workspaceRoot`），main 调 `copilotStore.reset(skillId)`。**保留 main 的 reset 路径供兜底**。
- `nextId` 保留 main 的 `crypto.randomUUID` 回退（优于 wave3 Math.random）。
- 返回值取并集：main 的 `messages/connectionStatus/.../clearMessages` + wave3 的 `sessions/activeSessionId/newSession/switchSession/persistenceError`。
- 须与 R7（copilotStore）、A#13（workspace-identity）同批落。

#### R7. `src/store/copilotStore.ts` — hooks-store · 风险 **high**（见②）→ 仅 native 强耦合，非契约红线
- wave3 = 多会话 + Tauri 文件系统持久化（写 `.gemini/copilot/sessions/<skill>/<session>.json`）；main = 扁平单消息。
- 会话历史是本地 UI 聊天记录，**非 gateway 事实，不违反红线**。
- 合并：把 main 的 `reset(skillId)` 与 wave3 的 `setContext/newSession/sessionsByContext` 并存。
- 持久化失败走 `persistenceError` 显式上报（合规：降级可观测）。
- **native 强耦合**：依赖 `lib/tauri.ts` 的 `writeWorkspaceFile/ensureWorkspaceSupportDirs`（R10）+ `workspace-identity.ts`（A#13）。**必须与 R10、A#13、R6 同批**，否则编译断链。

#### R8. `src/lib/tauri.ts` — hooks-store · 风险 low（**多文件硬依赖的根**）→ 列在②
- 两版功能集不重叠，取并集：
  - wave3 独有：`writeWorkspaceFile / addRecentWorkspace / listRecentWorkspaces / removeRecentWorkspace / ensureWorkspaceSupportDirs / RecentWorkspaceEntry`（copilot 会话持久化 + workspace 选择器所需）。
  - main 独有（已核）：`openInCursor / openInTerminal / openInCodex`（invokeShell 封装）+ `revealInFileManager` 的剪贴板回退。
- 冲突点：`revealInFileManager` 函数体两版不同——**保留 main 的**（含 `navigator.clipboard` 回退，web 更友好）。
- 所有新增裸 catch + `toast.error` 已显式可观测，可接受。
- **是 R2/R7 的硬依赖，必须先于或同批落地**。

#### R9. `src/components/copilot/copilot-panel.tsx` — misc-display · 风险 low
- 取 wave3，多渲染 `event.type==='thinking_delta'` 折叠块（思维链）。
- **冲突点**：该分支依赖 A#10（`types/copilot.ts` 带 thinking_delta type+parser）。**必须确认 A#10 同批**；否则去掉该分支再 TAKE（避免 TS 未知 type 死分支）。

#### R10. `src/components/studio/settings/SettingsPageContent.tsx` — misc-display · 风险 low
- 改动：(1) i18n 化（`useTranslation('settings')` 替硬编码，纯新增）；(2) 新增 `onAfterRoleTest` 回调并透传给 LlmRolesTab。
- 回调在 SettingsPage 接 `refreshRolesProjection`（测试后重拉 gateway 投影，合规）。
- **冲突点**：`onAfterRoleTest` 须存在于 `SettingsPageContentProps`（R4，settings/types.ts）与 SettingsPage（已含）。

#### R11. `src/components/studio/settings/GeneralTab.tsx` — misc-display · 风险 low
- 改动：(1) 删内联 `AppSettingsSaveStatusBadge`，改用共享 `SaveStatusBadge`（A#12）；(2) 全量 i18n 化；(3) 新增语言切换 `Select`（en / zh-CN，调 `i18n.changeLanguage`）。
- 全是展示/i18n，无 fallback/6 态/mock。
- **冲突点**：依赖 A#12（save-status-badge）、i18n locales、Select（main 已有）一起到位。

#### R12. `src/components/studio/Workspace.tsx` — misc-display · 风险 low
- 在 main 契约上叠 UI，无一处覆盖契约：
  1. predict/run 接线 `handlePredict→postPredictRun`、`handleRun→startRun`（main client 已有且签名一致）。
  2. `useRunStream`（main 已有）派生 `statusByNodeId` 喂 GraphCanvas（渲染 gateway run-stream 事件成节点状态，合规）。
  3. workspace-identity 路由 + Tauri `writeWorkspaceFile` 做本地文件夹编辑。
- **冲突待核**：(a) `statusByNodeId` 读 CallbackEvent 的 `phase_name/current_phase/event_type/status`，须确认这些字段在 main `useRunStream/CallbackEvent` 类型上存在；(b) `draft.extraFiles` 字段须在 build-draft 类型上存在；(c) `writeWorkspaceFile` 来自 R10。

---

### E. ADAPT — 必须改写而非直接合（三模块契约冲突）

#### AD1. `src/components/studio/settings/SettingsPage.tsx` — misc-display · 风险 **high**
- **不能直接 TAKE**：wave3 此文件按 wave3 自己的 `api/llm.ts` 写，`ModelInfo.status` 比较 `'ready'/'historical_ready'`（wave3 ProviderUiState 词汇）。但 **main #139 `ModelInfo.status` 是 `RouteStatus = 'verified'|'unverified_manual'|'disabled'|'failed'|'probe-verified'`**（已核 line 9，无 ready/historical_ready，新增 probe-verified）。直接 TAKE 会让 `modelInfoEvidenceRank`/`verifiedCount` 的判定在 main 契约下成死代码并漏判 probe-verified。
- **ADAPT 范围（仅 2 处）**：
  - `modelInfoEvidenceRank`（~第 80 行）：按 main `RouteStatus` 重写排序（`verified`/`probe-verified` 计入"已验证"，按 main 枚举排）。
  - `verifiedCount`（~第 155 行）：同上，`verified`+`probe-verified` 计数。
- **其余 wave3 改动保留**：copilot tab 接 roles 加载/保存/投影路径、`refreshRolesProjection` 作为 `onAfterRoleTest`——`refreshLoadedLlmRolesProjection` 在 main 已存在（settings/index.ts 导出），合规。

---

## ② 所有 `ownerBoundaryRisk=high` 文件 + 具体怎么改

> 共 10 个 high。核心准则：**走 GatewayAdapter / 去 mock-自算 / 保 #139 契约**。下面按"是不是真契约冲突"分两类。

### 类 1：真三模块契约冲突 — 必须保 #139 契约，不得引入旧 6 态

**已核实事实（来自 api/llm.ts）**：main `ProviderUiState = 'ready'|'untested'|'cooling_down'|'needs_setup'|'off'`（line 12，**无** historical_ready/failed）；`RouteStatus` **含** `probe-verified`（line 9，wave3 无）。

| 文件 | 怎么改 |
|------|--------|
| **`api/llm.ts`**（api-layer，最高边界） | **本任务暂不单方面翻转。** 这是整个状态词汇的契约源。计划文档主张"gateway 词汇（historical_ready/failed、去 needs_setup）才权威，main 前端在镜像过渡期的 Studio-adapter 产物"——但**翻转前端到 6 态 gateway 词汇，需后端 adapter（`apps/studio/backend/app/core/adapters/gateway.py` + `routers/llm.py` status_summary）先收敛掉 needs_setup**，否则前后端 payload 运行时分叉。**→ FLAG 给后端协调，不在 Phase 1 前端嫁接里翻。** 当前 Phase 1：**KEEP main 的 api/llm.ts 不动**（含 probe-verified 超集），所有 UI 文件按 main 枚举对齐。`legacyProviderUiState/ReasonCode`（line 613+）是 main 已有的客户端自算 6 态兜底，**仅在 `registry.model_groups` 为空时降级触发**（line 536-539 优先 backend model_groups），主路径已渲染 gateway 真理——保留但登记为唯一残留自算路径。 |
| **`settings/llm-roles/provider-state-badge.tsx`**（RECONCILE） | 同形组件，仅 6 态 meta 映射 + reasonDetail 码不同。**按 main `@/api/llm ProviderUiState` 枚举重建 meta map**（main 键：ready/untested/cooling_down/needs_setup/off），保留 main 枚举支持的额外 reason-code 文案。**不要引入 wave3 的 historical_ready/failed 键**（main 契约无 = TS 断）。是否给规范枚举加 historical_ready/failed 是 gateway 契约 owner 的决定，不在本 UI 集群。 |
| **`settings/llm-roles/RoleSettingsDialog.tsx`**（RECONCILE） | **已核实 main api/llm.ts 已声明 `RoleTokenIntentMode`（4 模式）、`RoleThinkingPreference`（3-way）、`RoleIntent.target_context_tokens`（line 339/340/352）——所以这是 UI 升级，非契约改动**。取 wave3 的 `RoleSettingsPanel/RoleSettingsFields/draft` 形状（context+output token 双 intent、4-mode 下拉、3-way thinking radio），它发出的是 main `updateRoleIntent` 接受的合法 `RoleIntent`。**OUT-OF-CLUSTER 必须同批迁移**：`LlmRolesTab.tsx` re-export `{RoleSettingsPanel, RoleSettingsFields, roleIntentFromSettingsDraft}`；`LlmRolesTab.test.tsx` 用旧 `outputLimitSummary` prop + 旧 draft（outputTokens/useMaximumTokens）渲染 `<RoleSettingsFields>`——wave3 改 prop 为 `tokenLimitSummary:{context,output}`、draft 为 `contextTokenMode/contextTokens/outputTokenMode/outputTokens`，**这两个文件 + 测试须同批迁移否则编译/测试断**。 |

### 类 2：边界标 high 但**非契约冲突**（native 耦合 / UX 集群绑定 / gateway 渲染）— 走对的来源即可

| 文件 | 本质 | 怎么改 |
|------|------|--------|
| **`store/copilotStore.ts`**（R7） | native 强耦合，非红线 | 会话历史是本地 UI 记录非 gateway 事实。合并 main reset + wave3 多会话/持久化。**必须与 lib/tauri(R10)、workspace-identity(A#13)、Workspace 同批**。持久化失败走 persistenceError 显式上报。 |
| **`hooks/useRecentSkills.ts`**（RECONCILE） | 语义完全分叉，绑定 welcome UX | wave3=recent **workspaces**（路径选择器）；main=recent **skill ids**。**两版都纯 localStorage、无 gateway 契约、无自算 fallback**。决策与"采用哪个 WelcomePage"绑定，**不能孤立裁**——属 welcome/workspace-picker UX 集群。采 wave3 open-folder UX → TAKE wave3 版；保 main skill-id 模型 → KEEP-MAIN。**与 WelcomePage(R 下)统一定夺**。 |
| **`panels/phase-frontmatter.ts`**（KEEP-MAIN） | D8 旧 schema | **已核**：main `mode`+`target_skill`+XML 块是后端（`skills.py:60` mode 三态）能编译、build-nodes 能读回的唯一契约。**绝不能用 wave3 的 `path:`/无 mode schema 覆盖**，wave3 整版丢弃。 |
| **`GraphCanvas/canvas-authoring.ts`**（KEEP-MAIN） | D8 写盘侧同冲突 | wave3 的 `io:`/`path:` schema + extraFiles/.py 桩生成建在废弃 schema 上，不能单独嫁接。整体 KEEP-MAIN。若将来要"新建逻辑相位自动生成 action 桩" UX，须在 main 的 mode+XML schema 上**重写**，不搬 wave3。 |
| **`components/welcome/WelcomePage.tsx`**（RECONCILE） | UX 升级 + 漏渲两个 gateway 徽标 | 取 wave3 open-folder/recent-workspace UX，但 **wave3 删掉了 main #139 渲染的两个 gateway 真理徽标**：`config_mismatch` 的 'Config drift' + `has_golden` 的 'Golden'。这俩字段两版 SkillSummary 都在，wave3 的 `visibleWorkspaces` 已通过 matching(=SkillSummary)拿到只是没渲染。**必须用 matching 把这两个徽标重新挂回 wave3 工作区卡片**（保 #139 契约）。依赖 useRecentSkills workspace 版 + lib/tauri 新增函数 + workspace-identity + getRuntimeConfig。`effectiveDefaultSkillsDirectory` 取舍按 default-skills-dir 行为对齐，勿丢 main 兜底语义。 |

### 类 3：copilot 派生的 high 注意点（A#7 graft caveat）

`copilot-role-derivation.ts`（TAKE）虽边界标 low，但有一条须执行时盯：**`activeRouteIds` 被 wave3 在客户端按 `uiState==='ready'` 重算**。若 gateway 已返回 materialized active set，**优先用 gateway 的，不要客户端重算**——否则会变成 Studio 侧 materialize（红线）。`canonical_id` built_in 白名单（claude-opus-4.7/4.8、deepseek-v4-pro/v3.2-pro）是 label-only 来源标签，非 fallback/6 态决策，不违规。

---

## ③ 建议执行顺序

分 5 批，**每批落地后立即 `tsc -b --noEmit` 自检**，断链早暴露。

**批次 0 — i18n 基础设施（纯新增，零风险，先行）**
A#1–6（i18n.ts + 4 locales + react-i18next.d.ts）→ R1（main.tsx 插 i18nReady）。
理由：后续 llm-error-messages、save-status-badge、所有 i18n 化的 Tab 都硬依赖它，不先落会编译断。

**批次 1 — misc-display 纯新增/加性（低风险）**
A#11（llm-error-messages）、A#12（save-status-badge）、A#13（workspace-identity）、A#14（WorkspaceContext）、A#15（SplitEditor）、A#16（LazyMonacoPanel）、A#17（index.css）、A#10（types/copilot.ts）。
理由：都是加性或纯新增，给后面 RECONCILE 备好依赖件。

**批次 2 — native / copilot store 集群（一次性同批，避免断链）**
R8（lib/tauri 并集，加 writeWorkspaceFile）→ R7（copilotStore）→ R6（useCopilot）→ R2（api/client.ts Tauri 分支，依赖 R8 的 writeWorkspaceFile）。
理由：R2/R7 硬依赖 R8 的 writeWorkspaceFile（已核 main 不导出），workspace-identity 已在批次 1 就位。**这一批必须整批过 tsc 才算成功。**

**批次 3 — settings copilot（去 mock，gateway 渲染）**
A#7（copilot-role-derivation）→ B（DELETE mock-copilot-data + copilot-role-state）→ A#8（CopilotModelGroupCard）、A#9（copilot-role-test）→ R3（CopilotTab）。
执行盯点：A#7 的 activeRouteIds 客户端重算（见②类 3）；R3 的 routeStatusOverrides 来源核验、name-allowlist 兜底不复活。

**批次 4 — api-keys / settings types / 状态相关（最后小心做）**
R4（settings/types.ts 加 onAfterRoleTest）→ R5（ApiKeysTab i18n）→ R10（SettingsPageContent）→ R11（GeneralTab）→ R12（Workspace）→ R9（copilot-panel thinking_delta）→ **AD1（SettingsPage ADAPT，按 main RouteStatus 改 2 处）**。
理由：这批触及 onAfterRoleTest 跨文件链 + 状态枚举，最后做、逐个 tsc 验证。AD1 放最后，因它依赖前面 copilot/roles 接线全部就位。

**全程不做（FLAG 给后端协调，非 Phase 1）**：
- `api/llm.ts` 翻转到 6 态 gateway 词汇（去 needs_setup、加 historical_ready/failed）——须后端 adapter 先收敛，运行时才不分叉。
- `provider-state-badge / role-utils / role-route-status / AvailableModelsSidebar / RoleTestResultPanel / ProviderCard` 等所有按 6 态枚举的 wave3 版——**枚举翻转前一律 KEEP-MAIN**。

**登记为后续单独清理任务（非本次嫁接，不阻塞）**：
- `AssetsPanel.tsx` 的硬编码 mock 兜底（intent_classifier/translator_subgraph + 写死 `/Users/sevenx/.../subgraphs/{name}` 路径）。
- `SubgraphInline.tsx`（main 版）硬编码 entry/execute/return 假行。

---

## ④ 嫁接后门禁

按顺序跑，全绿才算 Phase 1 完成：

1. **类型门禁（每批后都跑，最终全量）**
   ```
   cd apps/studio/frontend && npx tsc -b --noEmit
   ```
   重点盯：RoleSettingsFields prop 迁移（tokenLimitSummary）、provider-state 枚举对齐 main、SettingsPage ADAPT 后无 ready/historical_ready 残留死码。

2. **前端单测**
   ```
   cd apps/studio/frontend && npx vitest run
   ```
   重点盯：`LlmRolesTab.test.tsx`（RoleSettingsFields 新 prop/draft 已迁移）、`copilot-role-test.test.ts`（去 mock 后仍跑真实 job API）、`ProviderCard.test.tsx`（跟 main RouteStatus）、确认 `copilot-role-state.test.ts` 已随 DELETE 移除不再被引用。

3. **后端无回归（契约面）**
   ```
   cd apps/studio/backend && uv run pytest tests/ -x
   ```
   重点盯：`test_compile_endpoint.py`（phase-frontmatter mode+target_skill 契约未被前端改动影响）、gateway adapter / routers/llm status_summary 仍发 main 词汇（因为 api/llm.ts 未翻转，前后端一致）。

4. **构建冒烟**
   ```
   cd apps/studio/frontend && npx vite build
   ```
   验证顶层 await（main.tsx 的 i18nReady）在生产 target 下通过。

> 任一门禁红：先回到对应批次定位（tsc 报错→看该批跨文件 prop/枚举对齐；vitest 红→看 RoleSettingsFields/copilot 测试迁移；后端红→几乎必是误动了 phase-frontmatter/api 契约，回滚该改动）。

---

### 关键文件路径（绝对）

- 契约源（**Phase 1 不翻转**）：`/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased/apps/studio/frontend/src/api/llm.ts`
- 后端 mode 契约（KEEP-MAIN 依据）：`/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased/apps/studio/backend/app/models/skills.py:60`
- native 并集根（批次 2 先落）：`/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased/apps/studio/frontend/src/lib/tauri.ts`
- ADAPT 唯一文件：`/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased/apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx`

**FLAG 给后端协调（非 Phase 1）**：`apps/studio/backend/app/core/adapters/gateway.py`（仍发 needs_setup/missing_key）+ `routers/llm.py` status_summary —— 若未来要让前端切到 6 态 gateway 词汇（historical_ready/failed、去 needs_setup），须这两处先收敛，否则前后端 payload 运行时分叉。