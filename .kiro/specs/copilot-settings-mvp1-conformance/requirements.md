# Requirements — Copilot Settings MVP1 Conformance

## 项目输入

修复 `wf_559d9c51-59c` 深度审计确认的 22 条 Copilot 设置页缺陷（3 blocker + 8 major + 11 minor），使 Copilot 设置页符合 MVP1 + three-module 设计。审计原始产物在 `/private/tmp/claude-501/-Users-sevenx/fff22d92-0e2a-414d-852b-fc6be0a6fa95/tasks/wgdxxekpt.output`，对应 22 条需求按 F1–F22 编号对齐。

**Worktree**：`/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased`，分支 `feat/n0-settings-frontend`，HEAD `dbb0e7102088519f9b2a1ff34357735f4bcdbe5c`。

**核心契约锚点**：`docs/studio/mvp1/01_workflows/00_settings.md:48` "角色存 `model_groups[]`，后端物化成 gateway 平铺 `fallback_chain`。前端作者看 Group，引擎跑链"。

---

## 需求清单（EARS 格式）

### Blocker（3）

#### R-F1：Gateway 角色快照与 yaml 实时同步
**用户故事**：作为 Studio 用户，我希望保存或删除一个 copilot 角色后立刻能 Test 它，不应当因为 Studio 后端壳层的网关缓存 stale 而报 `no_available_route`。

**验收准则**：
1. WHEN `PUT /api/llm/roles` 或 `PUT /api/llm/roles/{name}` 或 `DELETE /api/llm/roles/{name}` 成功 THEN 系统 SHALL 在 return 之前用 `put_config(if_match=existing.etag)` 强写覆盖 `LocalGatewayConfigStore`，让 in-process resolver 读到的 snapshot 与磁盘 `llm_roles.yaml` 一致。
2. WHEN 同步失败 THEN 系统 SHALL 抛 5xx 给 FE 且 `logger.exception` 记录原因，不静默吞掉。
3. WHERE 磁盘上 `~/Library/Application Support/AgentStudio/default/roles.json` 被外部删除或损坏 THEN 系统 SHALL 在下次 `build_gateway_route_runtime` 时从 yaml 重建。
4. WHEN 集成测试启 sidecar → PUT 新增 `copilot_custom_test` 含 1 条 verified route → POST `/api/copilot/roles/copilot_custom_test/test-sdk` THEN job message SHALL NOT 包含 `no_available_route`。

#### R-F2：Vite proxy 与 client.ts 跟随 sidecar 动态端口
**用户故事**：作为开发者，我希望从 Tauri webview 或浏览器直开 `127.0.0.1:5173` 都能正常访问 sidecar，不应当因为 8787 死端口导致整页 502。

**验收准则**：
1. WHEN Tauri 启 sidecar 后通过环境变量 `STUDIO_SIDECAR_PORT` + `VITE_STUDIO_API_BASE_URL` 一并传给 vite 子进程 THEN vite proxy `/api` 与 `/ws` target SHALL 使用该端口而非写死 8787。
2. WHEN `import.meta.env.VITE_STUDIO_API_BASE_URL` 未设 且 `import.meta.env.DEV` 为 true THEN `apps/studio/frontend/src/api/client.ts` SHALL 抛 Error + `console.error` 提示，不静默 fallback 到死端口。
3. WHEN 浏览器开 `http://127.0.0.1:5173/api/settings` THEN HTTP SHALL 是 200（要么 sidecar 真返 200，要么 401/403，但不是 502 Bad Gateway）。
4. WHEN F2 修复完成 THEN console 三个错（settings 502、ws closed、LlmRolesTab 500）SHALL 同时消失（必要时 `rm -rf apps/studio/frontend/node_modules/.vite`）。

#### R-F3：Copilot 角色 Delete 走真 DELETE 端点
**用户故事**：作为 Studio 用户，我希望点 Copilot 第三方角色卡的垃圾桶 → toast 确认 → 该角色真从 yaml 删掉，不应当因后端 PUT additive merge 而永远删不掉。

**验收准则**：
1. WHEN 用户点第三方 copilot 卡垃圾桶并在 toast 上确认 THEN 系统 SHALL 调 `deleteRole(roleId)` 命中 `DELETE /api/llm/roles/{roleId}`，不再走 `onChange(...delete localKey...)` + PUT。
2. WHEN DELETE 返回成功 THEN yaml 中该 key SHALL 真消失，FE 卡片 SHALL 消失。
3. WHERE 角色是 Built-in 浮出卡（`source==='built_in'`）THEN 垃圾桶 SHALL NOT 渲染（保留现有 MVP1 设计）。
4. WHEN 删除请求失败（401/500）THEN 系统 SHALL `toast.error` 显式告警，不静默吞。

### Major（8）

#### R-F4：派生函数不再按 ui_state 预过滤路由
**验收准则**：
1. WHEN `buildCopilotRoleEntry(group)` 或 `applyCopilotModelGroupSelection(...)` 生成 fallback_chain THEN 系统 SHALL 包含 `group.availableRoutes` 全部 route ID（即已通过 anthropic-messages capability 过滤的 eligible 集合），不再按 `route.uiState === 'ready'` 二次过滤。
2. WHEN 该组所有 route 均 `untested`/`failed` THEN fallback_chain SHALL 仍非空，使 Test 能真去跑 SDK 调它。
3. WHERE spec §3.2 #3（`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md:201-202`）规定"未测也显示、不预过滤" THEN 此行为 SHALL 一致。

#### R-F5：copilot 角色 yaml key 合法 + 防 collision
**验收准则**：
1. WHEN `ensureRolePersisted(state, roleId)` 把浮出 built-in 卡落盘 THEN yaml key SHALL 为 `copilot_<slug>`（`<slug>` 由 `roleId.replace(/[^a-zA-Z0-9]+/g, '_').toLowerCase()` 生成），不可包含连字符或其他非 `[a-z][a-z0-9_]*` 字符。
2. WHEN `addDraftCopilotRole(state)` 生成新草稿 id THEN 系统 SHALL 用 `max(existing copilot_custom_N) + 1`，不再用 `length + 1`，防止 collision 覆盖。
3. WHEN `removeModelGroup` / `updateRouteOrder` / `requestDeleteCopilotRole` / `testRoleRoutes` 访问 `data.roles[roleId]` THEN 系统 SHALL 通过同一 `resolvePersistedKey(roleId)` helper 解析 key，确保 UI 与 yaml 一致。

#### R-F6：拖序 updateRouteOrder 保 runtime_settings
**验收准则**：
1. WHEN `updateRouteOrder(roleId, nextOrder)` 重写 fallback_chain THEN 系统 SHALL 按 `route_id` 从旧 chain 查找并保留 `runtime_settings`（含 materializer 之前回写的 `max_tokens`、`model_id` 等），不再统一置 `{}`。
2. WHEN 新 chain 含旧 chain 不存在的 route_id THEN 该 entry `runtime_settings` SHALL 为 `{}`（首次出现无可保）。
3. WHERE `applyCopilotModelGroupSelection` 切组场景 THEN `runtime_settings` SHALL 保持 `{}`（切组后旧值无意义）。

#### R-F7：Test 按钮等 saveStatus flush 后再发请求
**验收准则**：
1. WHEN 用户点 Test Button 时 saveStatus 为 `pending` 或 `saving` THEN Button SHALL `disabled`。
2. WHEN `testRoleRoutes(role)` 执行 THEN 系统 SHALL 在 startJob 前 `await onBeforeRoleTest?.()`（沿用 LlmRolesTab 已有的 `flushRolesSave`）。
3. WHERE `SettingsPageContent` 调 `<CopilotTab>` THEN SHALL 透传 `onBeforeRoleTest`。

#### R-F8：Copilot 候选组按 call_method capability 判 eligible
**验收准则**：
1. WHEN `deriveCopilotCandidateGroups(modelGroups, credentials)` 过滤 `provider_models` THEN 系统 SHALL 按 `route.call_method_id ∈ {'anthropic_messages', 'ark_anthropic_messages', 'deepseek_anthropic_messages', 'openrouter_anthropic_messages'}` 判定 eligible，不再按 `endpoint.protocol === 'anthropic_compatible'` 启发式过滤。
2. WHEN 后端 `_model_group_response` 未输出 `call_method_id` THEN 系统 SHALL 在 `apps/studio/backend/app/routers/llm.py` 补上字段透传。
3. WHEN 用户磁盘配 ark-official 含 anthropic-messages call_method THEN CopilotTab Available Models SHALL 显示该 group（旧实现下被漏）。

#### R-F9：Test 失败 toast 人话化
**验收准则**：
1. WHEN `_start_copilot_sdk_test_job` 在 except 分支抛 `ResourceTerminalError` THEN 系统 SHALL 调 `_human_message_for_error_code(error_code, role_name)` 映射成人类可读文案（如 "{role_name} 暂无可用模型路由"），不再直接 `f'无法解析 copilot 路线: {exc}'`。
2. WHEN `RoleTestJobResponse` 返回 FE THEN 顶层 SHALL 仍含 `error_code` + `error_payload` 供 debug。
3. WHEN FE `copilotRoleTestErrorMessage` 处理 job 失败 THEN SHALL 优先用 `ERROR_CODE_MAP[job.error_code]` 兜底，不再透传 `error.message`。

#### R-F10：后端 PUT/DELETE roles 主动 publish roles_changed
**验收准则**：
1. WHEN `put_llm_roles` / `put_llm_role` / `delete_llm_role` 成功 return 之前 THEN 系统 SHALL `await publish(STUDIO_EVENTS_TOPIC, {'type':'roles_changed','timestamp':..., 'source':'http_api'})`。
2. WHEN publish 失败 THEN 系统 SHALL `logger.exception` 记录，端点本身仍正常 return（不让 publish 失败把成功的写盘搞砸）。
3. WHERE file_watcher 那条间接链路 THEN SHALL 保留（外部进程改 yaml 仍要推），不互斥。

#### R-F12：空状态引导
**验收准则**：
1. WHEN `claudeModelGroups.length === 0`（无任何 anthropic-messages eligible 候选）THEN CopilotTab SHALL 渲染 `EmptyCopilotState` 含 "去 API Keys 配置 anthropic-compatible 凭证" 链接。
2. WHEN 某 role 的 `readyCount === 0` 但 `compatibleRoutes.length > 0` THEN 卡片 SHALL 显示 "有 N 条 route 未测试，去 API Keys 测试" warning chip。
3. WHEN 用户点引导按钮 THEN SHALL 切到 API Keys tab（`onNavigateToApiKeys` 由 `SettingsPage` 提供）。

### Minor（11）

#### R-F11：Copilot route 状态灯支持 6 态
WHEN route 状态为 `ready`/`historical_ready`/`untested`/`failed`/`cooling_down`/`off` 之一 THEN 状态灯 SHALL 显示对应颜色（绿/蓝/灰/红/灰+倒计时/灰），与 `apps/studio/frontend/src/components/studio/settings/llm-roles/role-route-status.tsx` 一致。

#### R-F13：WS reconnect 拿新 token + 失败阈值告警
1. WHEN `useStudioEventStream` reconnect THEN SHALL 每次重新从 `client.ts` 取 `currentApiToken`，不用闭包缓存。
2. WHEN 连续 5 次 reconnect 都因 close code 4401 失败 THEN SHALL `toast.error('与 sidecar 连接已断开，请重启 Studio')` 并停止退避。

#### R-F14：Add model 按钮防抖
WHEN `activeRoles` 中已存在一张空草稿卡（`models={}` 且 `fallback_chain=[]`）THEN Add model Button SHALL `disabled` + Tooltip "先把现有空卡选好模型组再新建"。

#### R-F15：CopilotTab 渲染 saveStatus 徽章
WHEN `saveStatus` prop 变化 THEN CopilotTab 顶部 SHALL 渲染 `<RolesSaveStatusBadge status={saveStatus} />`（与 LlmRolesTab 共用），idle 静默，pending/saving 转圈，saved 打勾，error 三角警告。

#### R-F16：toast 文案走 i18n
WHEN `toast.success/warning/error` 显示 Test 结果 THEN 文案 SHALL 经 `t('copilot.testToast.passed', { title })` 等 i18n key 拿取，en/zh 两个 bundle 都补齐。

#### R-F17：Test Button 与 route lights a11y
1. WHEN `isTesting` THEN Test Button SHALL 含 `aria-busy='true'`，并有 `<span aria-live='polite' class='sr-only'>Testing {title}...</span>` 通告。
2. WHEN route lights grid 状态变 THEN 容器 SHALL `aria-live='polite'`。

#### R-F18：拖序支持键盘
WHEN 用户用 Tab 聚焦 sortable route item，按 Space 拾起，方向键移动 THEN dnd-kit SHALL 触发 reorder（注册 `KeyboardSensor` 与 `sortableKeyboardCoordinates`）。

#### R-F19：Quit 时 flush in-flight save
1. WHEN `useDebouncedRolesSave` unmount 但 `pendingPayloadRef` 非空 THEN cleanup SHALL 同步触发 `putFn(pendingPayloadRef.current)` best-effort。
2. WHEN Tauri 收到 `WindowEvent::CloseRequested` THEN SHALL emit `before-quit` → FE 监听后 `await flushRolesSave()` → allow close（防 yaml 残缺）。

#### R-F20：前端实施手册 atom 状态与代码对齐
WHEN F1–F22 全部 verified 后 THEN 前端实施手册（`http://192.168.0.47:8902/#copilot_design`）的 atom #55/#57/#62/#63/#64/#65 `node_impl_status` SHALL 反映实际代码状态（done/wip/todo），通过修改 temp 生成器源（`temp/handbook/...` 中标记的 `node_impl_status` 字段）实现。

#### R-F21：Copilot Test 感知 429 cooling_down
1. WHEN `apps/studio/backend/app/services/copilot_test.py` 调 SDK 捕到 `anthropic.RateLimitError` THEN `RoleTestProviderProgressStatus` SHALL 含 `'cooling_down'` 状态 + `retry_after_seconds` 字段。
2. WHEN 任意 route 处于 cooling_down THEN Test Button SHALL `disabled` 并显示 `Cooling down {retry_after}s` 倒计时。

#### R-F22：removeModelGroup 后空壳 role roundtrip
WHEN 用户对一张卡 removeModelGroup（清空 `models`/`fallback_chain`/`active_model`）后保存 → 重启 Studio THEN 该卡 SHALL 仍存在且字段一致（不被 `_reject_legacy_roles` 或 materializer 误删）。若 roundtrip 失败，则 `removeModelGroup` 改为 toast 让用户选 "Replace 选新组 / Delete 走 onDeleteRole" 二选一。

---

## 跨需求约束

- **后端先于前端**（CLAUDE.md 铁律）：R-F1/R-F2/R-F10 必须先于 R-F3–R-F9 实施落地。
- **不动 LlmRolesTab / graph_agent**：除非 R-F1/R-F10 间接影响（仅追加同步逻辑，不改 PUT additive 语义）。
- **零容忍静默失败**（rules/logging.md）：所有降级 / 容错路径必须 `logger.warning` 或 `logger.error` + 上下文。
- **每条 finding 修完跑对应 vitest/pytest**；最终跑一遍完整 `apps/studio/frontend` 与 `apps/studio/backend` 套件。
