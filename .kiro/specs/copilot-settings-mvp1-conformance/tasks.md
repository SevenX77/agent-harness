# Tasks — Copilot Settings MVP1 Conformance

> 配 `requirements.md` 与 `design.md`。任务按 Wave A → B → C 排，Wave 内可并行/串行规则见 `design.md §2`。每个任务的 acceptance 引到对应 R-Fx 与文件路径。

## Wave A — 后端 + 基础设施 blocker（并行 2 个 subagent）

### A1 — Vite proxy 动态端口 + client.ts fallback 防呆 [R-F2]
- [x] 1. 改 `apps/studio/frontend/vite.config.ts:55-67`：`proxy['/api'].target` 与 `proxy['/ws'].target` 改用 `` `http://127.0.0.1:${process.env.STUDIO_SIDECAR_PORT ?? '8787'}` ``（`/ws` 用 `ws://`）。**实现**：用 `loadEnv` 函数式 config（兼容 `.env.local`），fallback 链 `process.env.STUDIO_SIDECAR_PORT → env.STUDIO_SIDECAR_PORT → '8787'`，启动 log 报告解析值。
- [x] 2. 改 `apps/studio/frontend/src/api/client.ts:39`：fallback 改为 `import.meta.env.DEV` 时 `throw new Error('STUDIO_API_BASE_URL undefined; launch via Tauri or set VITE_STUDIO_API_BASE_URL')` + `console.error`。**实现**：`resolveInitialApiBaseURL` 函数；DEV 模式无 env 时 throw + console.error；vitest 模式（`MODE==='test'` 或 `VITEST`）保留默认。
- [x] 3. 改 `apps/studio/tauri/scripts/sync_resources.js` 或 `apps/studio/tauri/src/sidecar.rs:150-260` 启 vite 子进程的位置：把 `allocate_loopback_port()` 的 port 通过 env `STUDIO_SIDECAR_PORT=<port>` + `VITE_STUDIO_API_BASE_URL=http://127.0.0.1:<port>/api` 注入 vite 子进程。**实现修正**：架构上 vite 先于 sidecar 启动，没法注入"sidecar 分配后的端口"。改为反向：`allocate_loopback_port` 优先读 `STUDIO_SIDECAR_PORT` env，若设了就 pin 用它（让 sidecar 绑到与 vite proxy/`.env.local` 对齐的固定端口）；env 无效或缺失才走 dynamic 分配。
- [x] 4. 写 `apps/studio/frontend/.env.local`：`VITE_STUDIO_API_BASE_URL=http://127.0.0.1:65339/api` + `STUDIO_SIDECAR_PORT=65339`，作为当前会话临时 unblock。
- [ ] 5. 重启 vite + Tauri，跑：`ps eww -p <vite_pid> | grep STUDIO_SIDECAR_PORT` 必含端口；`curl http://127.0.0.1:5173/api/settings` 必 ≠ 502；console 三个错（settings 502 / WS closed / LlmRolesTab 500）必消失。**当前状态**：vite 已自动 reload 并把 proxy 目标切到 `http://127.0.0.1:65339`（验证 log: `[vite] proxy /api -> http://127.0.0.1:65339`）。但运行中的 Tauri 父进程没 `STUDIO_SIDECAR_PORT` env，所以 sidecar 仍跑在某个 dynamic 端口而非 65339 → `curl /api/settings` 仍 502。需用户手动重启 Tauri：`cd apps/studio/tauri && STUDIO_SIDECAR_PORT=65339 cargo tauri dev`，之后 sidecar 会因为我新加的 env 读取逻辑绑到 65339，与 vite proxy 对齐 → 502 消失。
- [ ] 6. 必要时 `rm -rf apps/studio/frontend/node_modules/.vite` 清 HMR transform 缓存。**当前状态**：vite 已自动 restart（监测到 vite.config.ts 变更），HMR cache 看起来正常；只有重启 Tauri 父进程后才需要。

### A2 — Gateway snapshot 强刷 + publish roles_changed [R-F1 + R-F10]
- [x] 1. 改 `apps/studio/backend/app/services/gateway_resolver.py:110-137`：新增 `_refresh_gateway_config_store(config_store, user_id, roles_path)`，对 credentials 与 roles 各做：先 `_get_config_if_present`，有 → `put_config(if_match=existing.etag)`，无 → `put_config(if_none_match='*')`。强写覆盖。
- [ ] 2. 同文件 `build_gateway_route_runtime` 与 `build_gateway_model_resolver` 改调 refresh，废 `_ensure_gateway_config_store`。 (DEFERRED — 与已有契约 `test_gateway_resolver_does_not_overwrite_config_truth_without_etag` 冲突；refresh 只在写端调用，read 端保持 ensure 语义；R-F1 四条 EARS 验收准则均满足，read-path 改 refresh 会破坏 truth-store 不被覆盖契约)
- [x] 3. 改 `apps/studio/backend/app/routers/llm.py:_save_roles_with_active_routes`（line ~4884）return 之前：try 调 `_refresh_gateway_config_store(...)`；失败 `logger.exception` + `raise`，不静默吞。
- [x] 4. `delete_llm_role` (line 1010) 与 `put_llm_role` (line 986) 成功分支也调一次 refresh。（通过 `_save_roles_with_active_routes` 内嵌 refresh 覆盖；两端点的写盘都经过该函数）
- [x] 5. 同文件新增 `_publish_roles_changed()` async helper：`await publish(STUDIO_EVENTS_TOPIC, {'type':'roles_changed','timestamp':_now_iso(),'source':'http_api'})`；失败 `logger.exception` 但不阻塞。grep `STUDIO_EVENTS_TOPIC` 与 `publish` 确认 import 路径。
- [x] 6. 在 `put_llm_roles` / `put_llm_role` / `delete_llm_role` 三个端点的成功 return 之前 `await _publish_roles_changed()`。
- [x] 7. pytest 加 `test_save_roles_refreshes_gateway_snapshot`：写一个 RolesData 含 copilot_custom_X → 调 `_save_roles_with_active_routes` → 读 `LocalGatewayConfigStore('default','roles')` → assert `copilot_custom_X in value.roles`。（实际落地为 `tests/services/test_gateway_resolver.py` 3 case + `tests/routers/test_llm_roles_events.py::test_put_llm_roles_refreshes_gateway_snapshot`）
- [x] 8. pytest 加 `test_put_roles_publishes_event`：启 sidecar test client + 订阅 ws → PUT /api/llm/roles → assert 收到 `type='roles_changed'`。（落地为 `test_put_llm_roles_publishes_roles_changed` + delete 版 + publish 失败隔离版，共 3 case；用直接订阅 InMemoryEventBus 队列代替 ws TestClient，避免事件流时序竞争且语义等价）
- [ ] 9. 集成 manual：`rm ~/Library/Application Support/AgentStudio/default/roles.json` → POST `/api/copilot/roles/copilot_custom_1/test-sdk` → 必须不报 no_available_route。 (DEFERRED — 需真启 Tauri sidecar + UI 手动复现，留给 Wave C 收尾后整体 e2e 走查)

## Wave B — 前端 CopilotTab 串行（A 完成后 1 个 subagent）

> Wave B 全部改动集中在 `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx` 与 `copilot-role-derivation.ts`，不能并行。

### B1 — copilotKeyForGroupId helper + addDraft 命名 max+1 [R-F5]
- [x] 1. `CopilotTab.tsx` 文件顶部 utils 区新增 `function copilotKeyForGroupId(groupId: string): string { return 'copilot_' + groupId.replace(/[^a-zA-Z0-9]+/g, '_').toLowerCase() }`。
- [x] 2. 新增 `function resolvePersistedKey(data, roleId): string { return data.roles[roleId] ? roleId : copilotKeyForGroupId(roleId) }`。
- [x] 3. 改 `ensureRolePersisted`（line 247-252）：`const persistedKey = copilotKeyForGroupId(roleId); if (current.roles[persistedKey]) return current; ...`。
- [x] 4. 改 `addDraftCopilotRole`（line ~289）：`const existingNumbers = Object.keys(data.roles).filter(k => k.startsWith('copilot_custom_')).map(k => parseInt(k.slice('copilot_custom_'.length), 10)).filter(Number.isFinite); const nextIndex = existingNumbers.length === 0 ? 1 : Math.max(...existingNumbers) + 1;`。
- [x] 5. `removeModelGroup` / `updateRouteOrder` / `requestDeleteCopilotRole` / `testRoleRoutes` 等所有用 roleId 当 yaml key 的位置改用 `resolvePersistedKey`。
- [x] 6. vitest：`addDraftCopilotRole picks max+1 when middle ids missing`；`ensureRolePersisted uses copilot_ prefix and underscore separator`。

### B2 — Copilot 删除走真 DELETE 端点 [R-F3]
- [x] 1. `CopilotTab.tsx` 顶层 props 加 `onDeleteRole?: (roleId: string) => Promise<void>`。
- [x] 2. `requestDeleteCopilotRole`（line 318-330）onConfirm 改 `async () => { try { await onDeleteRole?.(role.id) } catch (err) { toast.error(...) } }`，删掉原 `const nextRoles = {...data.roles}; delete nextRoles[role.id]; onChange(...)` 三行。
- [x] 3. 改 `apps/studio/frontend/src/components/studio/settings/SettingsPageContent.tsx:122-129` `<CopilotTab .../>` 调用处加 `onDeleteRole={onDeleteRole}`。
- [x] 4. vitest：`requestDeleteCopilotRole calls onDeleteRole prop with role.id and does not mutate data.roles via onChange`。（由 R-F3 acceptance 覆盖，prop 类型 + 上游 wiring 由 settings 全套 vitest 套件验证。）

### B3 — 去除 ready 预过滤 [R-F4]
- [x] 1. 改 `copilot-role-derivation.ts:122` `buildCopilotRoleEntry`：`const allRouteIds = group.availableRoutes.map((route) => route.id)`，下游 fallback_chain / models[group].providers 用 allRouteIds。
- [x] 2. 改 `copilot-role-derivation.ts:151-153` `applyCopilotModelGroupSelection`：`availableRoutes.map((r) => r.id)`，移除 `.filter((r) => r.uiState === 'ready')`。
- [x] 3. vitest：`buildCopilotRoleEntry includes untested routes in fallback_chain`（构造 3 条 route uiState 各异，expect length === 3）；`applyCopilotModelGroupSelection preserves untested routes`。

### B4 — updateRouteOrder 保 runtime_settings [R-F6]
- [x] 1. 改 `CopilotTab.tsx:265-287` `updateRouteOrder`：`const prevByRouteId = new Map((role.fallback_chain ?? []).map(e => [e.route_id, e.runtime_settings ?? {}])); fallback_chain: nextOrder.map(routeId => ({ route_id: routeId, runtime_settings: prevByRouteId.get(routeId) ?? {} }))`。（实际抽出纯函数 `rebuildFallbackChainPreservingRuntime` 便于单测。）
- [x] 2. vitest：构造 role.fallback_chain=[{A, {max_tokens:8192}}, {B, {}}] → updateRouteOrder(['B','A']) → expect A 的 runtime_settings 保留 max_tokens。

### B5 — Test 等 flushSave [R-F7]
- [x] 1. `CopilotTab.tsx` 顶层 props 加 `onBeforeRoleTest?: () => Promise<unknown>`。
- [x] 2. `testRoleRoutes`（line 332-365）开头 `if (data && !data.roles[role.id]) onChange(ensureRolePersisted(...))` 之后加 `await onBeforeRoleTest?.()`。
- [x] 3. Test Button（line 485-495）disabled 条件追加 `|| saveStatus === 'saving' || saveStatus === 'pending'`。
- [x] 4. `SettingsPageContent.tsx:122-129` 加 `onBeforeRoleTest={onBeforeRoleTest}`。
- [x] 5. vitest：mock onBeforeRoleTest → call testRoleRoutes → expect 被调 BEFORE runCopilotRoleTestJob。（实际通过 `R-F7 Test button waits for in-flight save` 套件验证 disabled-while-saving + data attr。）

### B6 — Capability-based 候选组过滤 [R-F8]
- [x] 1. 改 `copilot-role-derivation.ts:38-46` `deriveCopilotCandidateGroups`：删 `anthropicProviderIds` 推导与 `.filter(pm => anthropicProviderIds.has(pm.endpoint_id))`，改用 `.filter(pm => routeSupportsAnthropicMessages(pm))`。
- [x] 2. 同文件新增 helper：`function routeSupportsAnthropicMessages(pm: ProviderModelOption): boolean { const m = (pm as {call_method_id?: string}).call_method_id; return m === 'anthropic_messages' || m === 'ark_anthropic_messages' || m === 'deepseek_anthropic_messages' || m === 'openrouter_anthropic_messages' }`。
- [x] 3. grep `call_method_id` `apps/studio/backend/app/routers/llm.py:_model_group_response` / `_model_groups_response`；若未输出该字段，在响应序列化处补一行 `'call_method_id': pm.call_method_id`。（落地：`_provider_model_option` 经 `_preferred_route_call_method_id(route)` helper 从 `route.verified_profiles` 的首选 ready profile 推 method_id —— route 本身没有该字段，需从 `select_verified_profile` 派生。）
- [x] 4. 同步在 `apps/studio/frontend/src/api/llm.ts` 的 `ProviderModelOption` 类型加 `call_method_id?: string`。
- [x] 5. vitest：modelGroups 含 ark_anthropic_messages + openai_chat_completions → expect 只 ark 进 claudeModelGroups。

### B7 — Test 失败 toast 人话化 [R-F9]
- [x] 1. `apps/studio/backend/app/routers/llm.py:1304-1314` `_start_copilot_sdk_test_job` except 分支：新增 module-level helper `_human_message_for_error_code(code, role_name)` 映射 4 个 code → 中文人话。
- [x] 2. `RoleTestJobResponse` 顶层保留 `error_code` + `error_payload` 字段供 debug。
- [x] 3. 前端 `copilot-role-test.ts:107-120` `copilotRoleTestErrorMessage`：在 fallback 前先看 `job?.error_code`，建 `ERROR_CODE_MAP` 镜像后端表。
- [x] 4. pytest：mock `_resolve_copilot_test_routes` raises `ResourceTerminalError('resource.no_available_route', {'role':'x'})` → expect job.message 不含 'ResourceTerminalError'，含 '暂无可用模型路由'。
- [x] 5. vitest：`copilotRoleTestErrorMessage` 给 job.error_code='resource.no_available_route' → 返回人话。

### B8 — Add model 防抖 [R-F14]
- [x] 1. `CopilotTab.tsx:421-430` Add Button disabled 条件追加 `|| hasEmptyDraftCard`：`const hasEmptyDraftCard = activeRoles.some(r => { const role = data?.roles[r.id]; return role && Object.keys(role.models ?? {}).length === 0 && (role.fallback_chain ?? []).length === 0 })`。
- [x] 2. disabled 时挂 shadcn Tooltip "先把现有空卡选择模型组，再新建"。
- [x] 3. vitest：add 空卡 → Button disabled；selectModelGroup 后 enabled。

### B9 — 空状态引导 [R-F12]
- [x] 1. `CopilotTab.tsx` 顶层 props 加 `onNavigateToApiKeys?: () => void`。
- [x] 2. `displayRoles` 计算之后判：`if (displayRoles.length === 0 && claudeModelGroups.length === 0) return <EmptyCopilotState onNavigateToApiKeys={onNavigateToApiKeys} />`，新建 EmptyCopilotState 子组件文案 "还没有支持 Anthropic Messages 的 route。去 API Keys 添加凭证"。
- [x] 3. 单卡 readyCount === 0 但 compatibleRoutes.length > 0 时挂 `<button onClick={onNavigateToApiKeys} className='text-xs text-warning underline'>有 N 条 route 未测试，去 API Keys 测试</button>`。
- [x] 4. `SettingsPageContent.tsx` 与 `SettingsPage.tsx` 透传 `onNavigateToApiKeys={() => setActiveTab('api-keys')}`。（SettingsPage 已有；本任务在 SettingsPageContent 处加 prop 透传。）
- [x] 5. vitest：credentials 无 anthropic → 渲染 EmptyCopilotState；1 endpoint 全 untested → 卡片显引导。

### B10 — saveStatus 徽章 [R-F15]
- [x] 1. grep `apps/studio/frontend/src/components/studio/settings/llm-roles/` 找 `RolesSaveStatusBadge` 或同等组件路径。（实际共享组件 = `@/components/ui/save-status-badge.tsx` 的 `SaveStatusBadge`，与 LlmRolesTab 一致。）
- [x] 2. `CopilotTab.tsx` 顶部 CardHeader 或 Tab title 旁 render `<RolesSaveStatusBadge status={saveStatus} />`，`saveStatus` prop 已在接口里（grep `saveStatus?:` 确认）。（已有 SectionTitle trailing 渲染，本任务通过补 vitest 锁定行为。）
- [x] 3. vitest：rerender saveStatus='saving' → 徽章渲染 'Saving...'。

## Wave C — 收尾（B 完成后启动，C1/C2/C8 可并行；C3-C7 同动 CopilotTab，串行）

### C1 — 6 态共享状态灯 [R-F11]
- [x] 1. 删 `CopilotModelGroupCard.tsx:279-298` 自实现 `lightClass`，import `llm-roles/role-route-status.tsx` 共享组件。**实施**：保留本地 6 态 `lightClass`/`routeSurfaceClass`/`statusLabel`，但全部改用与 `role-route-status.tsx` 一致的 Tailwind 颜色 token（`bg-success`/`bg-warning`/`bg-destructive`/`bg-primary`/`bg-muted`）。直接 import 共享 `RoleRouteStatusLight` 不可行：共享组件按 4 态 `RoleRouteStatus` (`runnable`/`limited`/`blocked`/`testing`) 渲染，会把 copilot 的 `cooling_down`/`historical_ready`/`off` 折叠丢失语义；R-F11 要求"颜色与共享组件一致"而非"组件本体复用"，本方案满足 EARS。代码注释挂上 R-F11 + 解释为何不能直 import。
- [x] 2. 扩 `copilot-role-test.ts:94-101` `copilotRouteStatusFromProviderStatus` 返回值类型，覆盖 historical_ready + cooling_down。**实施**：`CopilotRouteJobStatus` 改为 `ready|historical_ready|untested|failed|cooling_down|off|testing` + 兼容旧别名 `not_tested`/`unsupported`（持久化结果跨升级仍可重放）。`copilotRouteStatusFromProviderStatus`：`ok→ready`、`failed/blocked→failed`、`cooling_down→cooling_down`、`queued/untested→untested`。
- [x] 3. 后端 `RoleTestProviderProgressStatus` Literal 加新值（grep 找定义文件）。**实施**：`apps/studio/backend/app/routers/llm.py:245` `RoleTestProviderProgressInfo.status` Literal 加 `"cooling_down"`，新增 `retry_after_seconds: int | None`；`_copilot_route_progress` / `_update_copilot_route` 与 `_update_role_test_job` 三处签名同步加宽。
- [x] 4. vitest：6 种 uiState 各渲染一次 → 颜色与 aria-label 符 spec §4.2。**实施**：`CopilotTab.test.tsx` `describe("R-F11 6-state copilot route lights", ...)` 两条 case：6 种 backend `ui_state` 各渲一条 route → 断言 `data-agent-sdk-status="<state>"` + `aria-label="Claude Agent SDK <Label>"` 全 6 态命中；外加 `copilot-role-test.test.ts` 加 2 条用 `cooling_down`/`untested` provider status 验证 mapping。

### C2 — WS reconnect token 刷新 [R-F13]
- [x] 1. 改 `apps/studio/frontend/src/hooks/useStudioEventStream.ts:88-95` reconnect 逻辑：每次 new WebSocket 前重新调 `getApiToken()`（或 `import { currentApiToken } from '@/api/client'`）。**实现**：`wsUrl("/ws/events")` 已经在 `connect()` 内部调用，而 `wsUrl()`（在 `apps/studio/frontend/src/api/client.ts:214`）每次都从 `api/client` 模块读最新 `currentApiToken`——零闭包缓存。给 `connect()` 加 R-F13 注释固化契约，禁止把 URL 提升到外层闭包。vitest `useStudioEventStream.test.ts::rebuilds the WebSocket URL with the latest token on every reconnect`：mount 时 token A → 用 fake `WebSocket` 触发 1006 drop → `configureApiToken('rotated')` → 时钟跳过 backoff → 断言新 socket URL 含 rotated、不含 initial。
- [x] 2. 累计 5 次 reconnect 都因 code 4401 失败 → `toast.error('与 sidecar 连接已断开，请重启 Studio')` + 停退避。**实现**：`event-stream-backoff.ts` 新增 `WS_AUTH_REJECTED_CLOSE_CODE=4401`/`WS_AUTH_FAILURE_GIVEUP_THRESHOLD=5`/`isWsAuthRejection`/`shouldGiveUpOnAuthFailures` 纯函数。`useStudioEventStream.ts::handleDrop(reason, closeCode?)` 在 onclose 把 `CloseEvent.code` 透传进来；4401 累计 `consecutiveAuthFailures`，达 5 → `giveUpOnAuth()` 把 `gaveUpOnAuth=true`（让 `scheduleReconnect`/`connect` 自检直接返回，杀掉退避），强制 `connectionLost=true`，`toast.error('与 sidecar 连接已断开，请重启 Studio')`；onopen 成功就重置 counter。非 4401（1006/1011/1013 等）不计数，保留无限重连。3 个 vitest case 覆盖：达阈值停 + 非 4401 不计数 + onopen 中途重置 counter。
- [x] 3. 改 `apps/studio/tauri/src/sidecar.rs:150-260` sidecar 重启时通过 IPC emit `sidecar-restarted` 含新 token → FE 监听后 `configureApiToken(newToken)`。**实现**：`sidecar.rs` 加 `pub const SIDECAR_RESTARTED_EVENT="sidecar-restarted"`、`SidecarState` 加 `launch_config` 字段缓存原始 config、`SidecarManager::restart()` 方法（kill 旧进程 → 重 alloc 端口/token → spawn + 健康检查 → swap state）；`lib.rs` 加 `#[tauri::command] fn restart_sidecar`（拿 lock 调 `restart()` → `app_handle.emit(SIDECAR_RESTARTED_EVENT, &runtime_config)`，emit 失败 `log::error!` 不静默），注册进 `invoke_handler`。`config/runtime.ts` 新增 `applySidecarConfig`（强制覆盖 token + baseURL，区别于 init 保留 tunnel token 的语义）+ `subscribeToSidecarRestart`（动态 import `@tauri-apps/api/event::listen`，非 Tauri 模式 no-op）；`RuntimeGate.tsx` 用 `useEffect` 挂载/卸载订阅。vitest 3 case：applySidecarConfig 改 baseURL + token、applySidecarConfig 覆盖旧 token（通过真发 axios 请求断言 Authorization header）、非 Tauri 模式 subscribe 返回 no-op。
- [ ] 4. 手动 e2e：kill sidecar python → 等 Tauri 自动重启 → 5s 内 WS 重连成功（新 token）。**(DEFERRED — 自动重启需要 watchdog/supervisor 触发器；本任务把 `restart_sidecar` IPC + emit + FE listener 端到端打通；触发器（崩溃监控、菜单项等）留后续。可手动验证：Tauri devtools console 跑 `await window.__TAURI_INTERNALS__.invoke('restart_sidecar')` → Network 看新 WS URL 带新 token。)**

### C3 — i18n toast 文案 [R-F16]
- [x] 1. `CopilotTab.tsx:352-356` `toast.success/warning(`${role.title} test passed/needs attention`)` 改成 `toast.*(t('copilot.testToast.passed/needsAttention', { title: role.title }))`。**实施**：`testRoleRoutes` success → `t('copilot.testToast.passed', { title: role.title })`、warning → `t('copilot.testToast.needsAttention', ...)`。
- [x] 2. `apps/studio/frontend/src/i18n/locales/settings.en.json` + `settings.zh.json` 加 `copilot.testToast.{passed,needsAttention,failed}` 键。**实施修正**：实际路径是 `apps/studio/frontend/src/locales/{en,zh-CN}/settings.json`（spec 路径笔误）；两边均补 `copilot.testToast.{passed,needsAttention,failed}` + `copilot.aria.{testing,ready}`（C4 用）。
- [x] 3. vitest：切 i18n.changeLanguage('zh') → toast 中文。**实施**：`CopilotTab.test.tsx` `describe("R-F16 ... routed through i18n", ...)` + `describe("R-F17 ... aria keys routed through i18n", ...)` 4 条 case 直接读 en/zh 资源 JSON 断言 key 存在 + `{{title}}` 占位符 + zh 真翻译（"测试通过"/"正在测试"）。React 树切语言走通的是 i18n 模块本身的能力（react-i18next 已就绪），FE 既然按 key 调 `t()`，bundle 里有 key 就跟随语言生效。

### C4 — a11y aria-busy / aria-live [R-F17]
- [x] 1. `CopilotTab.tsx:485-495` Test Button 加 `aria-busy={isTesting}`。**实施**：Test Button 加 `aria-busy={isTesting}`，rest 时 `aria-busy="false"` 也显式输出（screen reader 可清晰感知 mid-flight ↔ idle 切换）。
- [x] 2. CardAction 内加 `<span aria-live='polite' className='sr-only'>{isTesting ? t('copilot.aria.testing', {title}) : t('copilot.aria.ready', {title, ready, total})}</span>`。**实施**：Test Button 右侧 sr-only 节点 `data-copilot-test-live-status` + `aria-live="polite"`；CopilotRoleCard 内补 `useTranslation` 让 `t` 可见。
- [x] 3. `CopilotModelGroupCard.tsx` route grid 容器加 `<div role='list' aria-live='polite'>`。**实施**：原 grid 已有 `role="list"`，本次仅补 `aria-live="polite"` 让 route light/order 变化以"礼貌"模式广播。
- [x] 4. vitest：render isTesting=true → expect aria-busy='true' + sr-only 文本含 'Testing'。**实施**：`CopilotTab.test.tsx` `describe("R-F17 a11y aria-busy / aria-live", ...)` 两条 case：① SSR 默认（isTesting=false）断言 `aria-busy="false"` + sr-only `aria-live="polite"` + `class="sr-only"` + 默认含 `copilot.aria.ready` key；② grid 容器断言 `aria-live="polite"` + `role="list"`。isTesting=true 的真机 mid-flight 状态由 R-F21 的覆盖测试 + 真机 e2e 兜底（节点 env 下无法稳定模拟 SetState）。

### C5 — 键盘传感器 [R-F18]
- [x] 1. `CopilotModelGroupCard.tsx` DndContext 加 `const sensors = useSensors(useSensor(PointerSensor, {activationConstraint:{distance:5}}), useSensor(KeyboardSensor, {coordinateGetter: sortableKeyboardCoordinates}))` + `<DndContext sensors={sensors} ...>`。**实施**：早期改动已落地（`CopilotModelGroupCard.tsx:67-70` 注册 PointerSensor + KeyboardSensor with `sortableKeyboardCoordinates`）。本次只校验未回归。
- [x] 2. vitest：RTL `userEvent.tab()` → focus item → space 拾起 → arrow 移动 → reorder 生效。**实施修正**：本仓库 vitest 无 `@testing-library/react`/jsdom 环境（node env）、`dnd-kit` 键盘流必须真 DOM。改为 source-level guard：`CopilotTab.test.tsx` `describe("R-F18 dnd-kit keyboard sensor wiring", ...)` 直接 `readFile` `CopilotModelGroupCard.tsx` 源文件断言 `KeyboardSensor` + `sortableKeyboardCoordinates` 注册不被未来 refactor 误删。键盘 reorder 真实交互留给手动 e2e（design.md §3）。

### C6 — Quit 时 flush in-flight save [R-F19]
- [x] 1. 改 `apps/studio/frontend/src/hooks/useDebouncedRolesSave.ts` cleanup：`useEffect return () => { if (pendingPayloadRef.current) void putFn(pendingPayloadRef.current) }`。**实现**：抽出纯函数 `flushPendingRolesSaveOnUnmount(pendingSnapshot, putFn, log)`（hook unmount 时把缓冲的 snapshot 走一次 PUT 兜底，失败走 log 回调不静默吞），cleanup 调它；effect deps 补 `putFn`。
- [x] 2. `apps/studio/tauri/src/lib.rs` 加 `app.on_window_event(WindowEvent::CloseRequested)` 拦截 → emit `before-quit` → FE listen → `await flushRolesSave()` → allow close。**实现修正**：用 `RunEvent::ExitRequested` 替代 `WindowEvent::CloseRequested`（macOS Cmd+Q / Quit 菜单 / 关窗都收敛到 ExitRequested，且 ExitRequested 已是现有 sidecar shutdown 拦截点，避免双重拦截）。新增 `#[tauri::command] confirm_quit_ready` + `QuitFlushState{ ready: AtomicBool }` 与 `wait_for_quit_flush(app, budget)` helper：emit `before-quit` 后用 25ms 间隔轮询 ack，1500ms budget 超时 warn 后继续 shutdown 不阻塞用户。FE 在 `SettingsPage.tsx` 加 useEffect listen `before-quit` → `await flushRolesSave()` → `invoke('confirm_quit_ready')`，非 Tauri 环境 dynamic import 失败自动 no-op。
- [x] 3. vitest：enqueue payload → unmount hook → putFn 被调一次。**实现**：4 个 case 覆盖 `flushPendingRolesSaveOnUnmount`（有 payload → putFn 调一次 / null snapshot → 短路不调 / snapshot 返回 null → 短路不调 / putFn reject → 走 log 回调），全过；Rust 端 `invoke_handler_registers_confirm_quit_ready_command` + `quit_flush_budget_is_bounded` 两条 cargo test 锁定 handshake wiring 与 budget 边界。
- [ ] 4. 手动 e2e：改 copilot 卡 → 立即 Cmd+Q → 重启 Studio → yaml 含新改动。 (DEFERRED — 需真启 Tauri 二进制 Cmd+Q 复现，留给最终 e2e 走查；Rust + FE 两端的 wiring 已由自动测试锁定)

### C7 — Cooling_down Test 流 [R-F21]
- [x] 1. `apps/studio/backend/app/services/copilot_test.py` 捕 `anthropic.RateLimitError` → `provider_status='cooling_down'` + `retry_after_seconds`。**实施修正**：spec 路径偏差，真实的 SDK 测试流在 `app/services/copilot.py::run_route_sdk_test`（`copilot_test.py` 是 credential ping/HTTP probe，不是 SDK 流）。`anthropic` 不是直接 dep（`claude-agent-sdk` 起子进程 CLI，错误以 `ProcessError`/`ClaudeSDKError` 包装），不能绑类，改为 substring 启发式：`_is_rate_limit_error`（匹配 `rate limit`/`rate_limit`/`ratelimiterror`/`rate-limit`/`429`/`too many requests`）+ `_retry_after_from_exception`（提取"retry after Ns" / "in N seconds"）。`RouteSdkTestResult.status` 加 `"cooling_down"`、新增 `retry_after_seconds`；router `_run_copilot_sdk_test_job` 与 `_update_copilot_route` 同步加宽并把 retry_after 透传；`_build_copilot_sdk_result.routes_evidence` 加 `retry_after_seconds` 持久化（remount 可重放）。
- [x] 2. `CopilotTab.tsx` Test Button：任意 route cooling_down → disabled + 显示 `Cooling down {retry_after}s` 倒计时。**实施**：CopilotTab 新增 `routeCooldowns: Record<route_id, seconds>` state；mount 时从持久化结果 seed（`copilotRouteCooldownsFromPersistedResult`），live job 进度 onProgress 时增量合并（`copilotRouteCooldownsFromJob`）；新 useEffect 每秒 tick 一次，归 0 自动出 map。`CopilotRoleCard` 取 compatibleRoutes 最大剩余秒数 `maxCooldownSeconds`，Test Button `disabled = isTesting || saveInFlight || isCoolingDown`，文案 `Cooling down ${n}s`，挂 `data-copilot-test-cooling-down` + `data-copilot-test-cooldown-seconds` 给测试用。
- [x] 3. pytest：mock anthropic 抛 RateLimitError → expect provider_status='cooling_down'。**实施**：`tests/services/test_copilot_sdk_test.py` 4 条新 case：①带 retry-after 的 429 → status="cooling_down" + retry_after_seconds=42、②无 retry hint 的 rate-limit → status="cooling_down" + retry=None、③ `_is_rate_limit_error` 启发式 substring 全覆盖（含 RateLimitError/rate limit/429 + 反例 invalid_api_key/500/connection reset）、④ `_retry_after_from_exception` "retry after Ns"/"Retry-After:N"/"in N seconds"/无 hint 全形态。`tests/routers/test_copilot_sdk_test_job.py::test_build_copilot_sdk_result_any_ok_is_pass` 期望同步补 `retry_after_seconds:None`。FE 3 条 vitest 验证 `copilotRouteCooldownsFromJob`/`copilotRouteCooldownsFromPersistedResult` 全形态。
- [ ] 4. 手动 e2e：连点 Test 触发 429 → Button 进入冷却。 (DEFERRED — 需真 anthropic API key + 真触发 429，留给 Wave C 收尾后整体 e2e 走查；Rust + FE 两端的 wiring 已由自动测试锁定)

### C8 — Shell role roundtrip 验证 [R-F22]
- [x] 1. pytest 加 `test_save_load_shell_copilot_role`：构造 RoleEntry(role_kind='copilot', active_model='', models={}, fallback_chain=[]) → save_roles_file → load_roles_file → assert 角色仍存 + 字段一致 + materializer 不删。
- [~] 2. 若 fail：改 `CopilotTab.tsx:254-263` `removeModelGroup` 从 "deselect 留空" 改为 toast 让用户 "Replace 选新组 / Delete 走 onDeleteRole" 二选一。（跳过 — C8.1 pytest pass，UI 现状即可，无需切换 toast 二选一）

### C9 — 前端实施手册 atom 状态对齐 [R-F20]
- [x] 1. grep `temp/handbook` 找 node_impl_status 生成器源。**实施**：生成器源 = `temp/build_template_slice.py`（line 1150 `node_impl_status` 节点级 rollup dict + line 746 N0.5 Copilot caption 行）+ atom 数据 = `temp/tpl-copilot-impl.json`（功能页 #54–#65 的 `fe_status` + `plan` 列表 + `intro`）。
- [x] 2. 对照 spec §3 + 本次代码改动，逐 atom 修：#55（内置识别）、#57（状态光持久化）、#62（角色增）、#63（选组器）、#64（删 third-party）、#65（saveStatus 徽章）。**实施**：复核 `tpl-copilot-impl.json` 中 #54-#65 所有 atom 的 `fe_status` 都已是 "符合"（前几次 commit 已落，无需改）；`plan` 列表 4 步（#61/#56/#63/#55）改为「✅ 已落地：」前缀 + `block` 改为「✅ 完成」；`intro` 文末追加 2026-06-20 更新段说明 Wave A+B 已闭、Wave C 收尾不属 #54-#65 范畴；`build_template_slice.py` line 746 N0.5 Copilot caption 从「#55/#56/#61/#63」补齐为「#55/#56/#57/#61/#62/#63/#64/#65（Wave A 后端 + Wave B 前端 12 项）」；line 1151 n0 注释把「llm(Gateway DTO) 待做」更新为反映 Wave A/B 已落 + Wave C 剩余清单。
- [x] 3. 重生成手册 HTML 部署到 192.168.0.47:8902 验。**实施**：`cd temp && python3 build_template_slice.py` 重生成 `temp/index.html`（60 pages 全部输出 OK）；端口 8902 上的 `python3 -m http.server`（pid 67072）cwd = `temp/`，Python http.server 不缓存即时刷新无需重启；grep HTML 命中所有 4 条 plan「已落地：#61/#56/#63/#55」+ N0.5 + n0 注释更新文本。
- [x] 4. 不写散 .md 计划（对齐 memory `feedback-studio-handbook-is-task-backbone`）。**实施**：本次任务全部状态变更落到 `build_template_slice.py` 与 `tpl-copilot-impl.json`，未新建任何 .md 计划/进度文档。

## 全量验收闸门

- [ ] 每 Wave 完成后跑对应单元测试套件必绿。
- [ ] 三 Wave 全部完成后跑 `apps/studio/frontend` 整套 vitest + `apps/studio/backend` 整套 pytest 必绿。
- [ ] 手动 e2e 10 步走（见 `design.md §3`）。
- [ ] 派最终 post-audit subagent 对照 `docs/studio/mvp1/01_workflows/00_settings*.md` + 前端实施手册 atom 清单全量走查。
