# Design — Copilot Settings MVP1 Conformance

> 配 `requirements.md`。22 条 finding 对应到 4 个设计领域 + 3 实施波。

## 1. 设计领域

### 1.1 后端契约同步层（R-F1 / R-F10）

**问题**：Studio 后端壳层用 `LocalGatewayConfigStore`（文件型，存 `~/Library/Application Support/AgentStudio/default/roles.json`）作为 in-process resolver 的 snapshot，但只在文件缺失时一次性 seed，PUT/DELETE roles 后不更新。导致网关 resolver 看到的 roles 跟磁盘 yaml 不一致 → `resolve_role('copilot_custom_1')` → None → 抛 `ResourceTerminalError`。

**设计**：
- 在 `apps/studio/backend/app/services/gateway_resolver.py` 新增 `_refresh_gateway_config_store(config_store, user_id, roles_path)`：每次都从磁盘 yaml + credentials 重读 → `put_config(if_match=existing.etag)` 强写覆盖 roles 和 credentials 两份 config。
- `build_gateway_route_runtime` / `build_gateway_model_resolver` 一律改调 refresh 而非 ensure。
- `apps/studio/backend/app/routers/llm.py:_save_roles_with_active_routes` 在 save_roles_file 之后追加一次 refresh，失败必抛 + `logger.exception`。
- 新增 `_publish_roles_changed()` helper，在 `put_llm_roles` / `put_llm_role` / `delete_llm_role` 三处 return 之前调，事件含 `{type, timestamp, source='http_api'}`，publish 失败 `logger.exception` 但不阻塞写盘成功 return。

**契约不变**：`PUT /api/llm/roles` 仍是 additive merge（LlmRolesTab 局部 save 依赖此语义），不动 R3 Pydantic schema。

### 1.2 基础设施层（R-F2 / R-F13 / R-F19）

**问题**：Tauri 启 sidecar 用 `allocate_loopback_port()` 拿动态端口（如 65339），但 Vite proxy `target` 写死 8787 + `client.ts` fallback 写死 `http://localhost:8787/api`。任何在 RuntimeGate `initializeRuntimeConfig` 完成前发出的请求 / 浏览器直开 5173 的场景 → 走 8787 → 502。

**设计**：
- 改 `apps/studio/tauri/scripts/sync_resources.js` 或 `apps/studio/tauri/src/sidecar.rs` 启 vite 前的位置，把 `STUDIO_SIDECAR_PORT=<port>` + `VITE_STUDIO_API_BASE_URL=http://127.0.0.1:<port>/api` 注入 vite 子进程 env。
- 改 `apps/studio/frontend/vite.config.ts:55-67`：`proxy['/api'].target` 与 `proxy['/ws'].target` 改用 `process.env.STUDIO_SIDECAR_PORT ?? '8787'` 模板。
- 改 `apps/studio/frontend/src/api/client.ts:39`：fallback 改为 `import.meta.env.DEV` 时 throw + `console.error`，禁止静默走死端口。
- 提供 `.env.local` 作为短期 unblock：`VITE_STUDIO_API_BASE_URL=http://127.0.0.1:65339/api` + `STUDIO_SIDECAR_PORT=65339`。
- **WS 重连**（R-F13）：`apps/studio/frontend/src/hooks/useStudioEventStream.ts` 每次 new WebSocket 前重新调 `getApiToken()`；连续 5 次 4401 失败 `toast.error` + 停止。
- **Quit flush**（R-F19）：`useDebouncedRolesSave.ts` cleanup 同步触发 `putFn(pendingPayloadRef.current)`；Tauri `WindowEvent::CloseRequested` 拦截 + emit `before-quit` → FE `await flushRolesSave()` → allow close。

### 1.3 前端 Copilot 派生与交互层（R-F3 / R-F4 / R-F5 / R-F6 / R-F7 / R-F8 / R-F12 / R-F14 / R-F15）

**问题**：CopilotTab 当前混合了多个违反 MVP1 的行为——预过滤 ready route、本地 mutate 删除、yaml key 用 modelGroupId 带连字符、addDraft length+1 collision、拖序清 runtime_settings、Test 不等 flushSave、按 endpoint protocol 启发式过滤候选组、空状态无引导。

**设计**：
- `copilot-role-derivation.ts`：
  - `buildCopilotRoleEntry(group)` line 122：`group.availableRoutes.map(r => r.id)`，不再 filter ready。
  - `applyCopilotModelGroupSelection(...)` line 151-153：同上。
  - `deriveCopilotCandidateGroups(...)` line 38-46：删 `anthropicProviderIds` 过滤，改用 `routeSupportsAnthropicMessages(pm)` helper，按 `call_method_id` 白名单 4 个值判定。
- 后端 `apps/studio/backend/app/routers/llm.py:_model_group_response` 输出 `call_method_id` 字段（grep 验证缺失则补）。
- `CopilotTab.tsx`：
  - 新增 `copilotKeyForGroupId(groupId)` helper → 用于 `ensureRolePersisted` 写 yaml + 用 `resolvePersistedKey(roleId)` 帮所有访问 `data.roles[roleId]` 的地方解析 key。
  - `addDraftCopilotRole` 用 `max(existing copilot_custom_N) + 1`。
  - `updateRouteOrder` 用 `prevByRouteId` Map 保 runtime_settings。
  - 顶层 props 加 `onDeleteRole?: (roleId) => Promise<void>` + `onBeforeRoleTest?: () => Promise<unknown>` + `onNavigateToApiKeys?: () => void`。
  - `requestDeleteCopilotRole` onConfirm 改 `await onDeleteRole?.(role.id)`。
  - `testRoleRoutes` 开头 `await onBeforeRoleTest?.()`；Test Button disabled 追加 `|| saveStatus in ['saving','pending']`。
  - `Add model` Button disabled 追加 `|| hasEmptyDraftCard`。
  - displayRoles 空时渲染 `EmptyCopilotState`；readyCount === 0 时挂引导链接。
  - 顶部插入共享 `<RolesSaveStatusBadge status={saveStatus} />`。
- `SettingsPageContent.tsx`：CopilotTab 处补 `onDeleteRole={onDeleteRole}`、`onBeforeRoleTest={onBeforeRoleTest}`、`onNavigateToApiKeys={() => setActiveTab('api-keys')}`。

### 1.4 反馈、a11y、i18n、手册（R-F9 / R-F11 / R-F16 / R-F17 / R-F18 / R-F20 / R-F21 / R-F22）

**设计**：
- **R-F9 错误码人话化**：后端 `_start_copilot_sdk_test_job` 新增 `_human_message_for_error_code` 映射表；前端 `copilot-role-test.ts` 镜像同表做兜底。
- **R-F11 6 态状态灯**：删 `CopilotModelGroupCard.tsx:279-298` 自实现，import `llm-roles/role-route-status.tsx` 共享组件；`copilot-role-test.ts` 扩 `copilotRouteStatusFromProviderStatus` 返回值类型，后端 `RoleTestProviderProgressStatus` 补 Literal。
- **R-F16 i18n**：`toast.success/warning/error` 改用 `t('copilot.testToast.*', { title })`；en/zh bundle 补齐。
- **R-F17 a11y**：Test Button `aria-busy`；CardAction 内加 `<span aria-live='polite' className='sr-only'>`；route lights `<div role='list' aria-live='polite'>` 包裹。
- **R-F18 键盘拖序**：`CopilotModelGroupCard.tsx` DndContext 注册 `useSensors(useSensor(PointerSensor, ...), useSensor(KeyboardSensor, {coordinateGetter: sortableKeyboardCoordinates}))`。
- **R-F20 手册同步**：跑 `grep -rn node_impl_status temp/` 找到生成器源，逐 atom 标 done/wip/todo；不写散 .md 计划（对齐 memory `feedback-studio-handbook-is-task-backbone`）。
- **R-F21 cooling_down**：`copilot_test.py` 捕 `anthropic.RateLimitError` → `provider_status='cooling_down'` + `retry_after_seconds`；FE 任意 route cooling_down 时 Test Button disabled + 倒计时显示。
- **R-F22 shell role roundtrip**：先跑 pytest `test_save_load_shell_copilot_role` 验后端 roundtrip；若 fail 则 `removeModelGroup` 改为 toast 让用户 Replace/Delete 二选一。

## 2. 三波实施顺序（Wave Plan）

### Wave A — 后端 + 基础设施 blocker（并行 2 个 subagent）
- **A1**: R-F2 vite proxy 动态端口（`vite.config.ts`, `client.ts`, `tauri/scripts/sync_resources.js`, `tauri/src/sidecar.rs`, `.env.local`）
- **A2**: R-F1 + R-F10 gateway snapshot refresh + roles_changed publish（`gateway_resolver.py`, `routers/llm.py`）

两者文件零重叠，可独立并行。

### Wave B — 前端 CopilotTab 串行（A 完成后 1 个 subagent，同文件不能并行）
顺序：R-F5（helper）→ R-F3（删除）→ R-F4（去 ready 过滤）→ R-F6（保 runtime_settings）→ R-F7（等 flushSave）→ R-F8（call_method capability）→ R-F9（toast 人话）→ R-F14（Add 防抖）→ R-F12（空状态引导）→ R-F15（saveStatus 徽章）。

### Wave C — 收尾（B 完成后 4-6 个 subagent 并行，文件分散）
- **C1**: R-F11 共享 6 态状态灯（`CopilotModelGroupCard.tsx`, `copilot-role-test.ts`）
- **C2**: R-F13 WS reconnect token（`useStudioEventStream.ts`, `tauri/src/sidecar.rs`）
- **C3**: R-F16 i18n（`CopilotTab.tsx`, `i18n/locales/settings.{en,zh}.json`）
- **C4**: R-F17 + R-F18 a11y + 键盘传感器（`CopilotTab.tsx`, `CopilotModelGroupCard.tsx`）
- **C5**: R-F19 quit flush（`useDebouncedRolesSave.ts`, `tauri/src/lib.rs`）
- **C6**: R-F21 cooling_down（`copilot_test.py`, `CopilotTab.tsx`）
- **C7**: R-F22 shell role roundtrip 先验证后决定（`backend/tests/services/test_llm_roles.py`, `CopilotTab.tsx`）
- **C8**: R-F20 手册 atom 状态对齐（`temp/handbook/...`）

C 内部冲突分析：C3+C4+C5+C6+C7 都可能动 `CopilotTab.tsx`——但每个改动行段不同（C3 改 toast 调用、C4 改 Button props、C5 改 hook cleanup、C6 改 Button disabled、C7 改 removeModelGroup）。可以用 git worktree 隔离 + 最后 cherry-pick / merge；或者改成 4-6 个串行小 task。**保守起见 C 内部 also serial**，但跟 B 完成后立刻开始。

## 3. 验收闸门

- **每 Wave 完成**：
  - 所有改动文件跑对应单元测试（vitest/pytest）必绿。
  - git diff HEAD 给一个 post-audit subagent 验是否符合 R-Fx 的 EARS 准则。
- **三 Wave 全部完成后**：
  - 跑完整 `apps/studio/frontend` vitest 套件 + `apps/studio/backend` pytest 套件。
  - 手动 e2e（顺序）：
    1. `rm ~/Library/Application Support/AgentStudio/default/roles.json`
    2. 重启 Tauri / Studio
    3. 切到 Settings → Copilot
    4. 选 Claude 3.5 Haiku → Test → 必须真去跑 SDK，不报 no_available_route
    5. 第三方卡垃圾桶 → 确认 → 卡片消失 + yaml 不含该 key
    6. 拖序 → Test → 后端日志 runtime_settings 仍含 max_tokens
    7. console 三个错全消失
    8. saveStatus 徽章按状态切换
    9. zh 模式 toast 中文显示
    10. 屏幕阅读器（VoiceOver）能通告 Testing 状态
  - 派最终 post-audit subagent 对照 `docs/studio/mvp1/01_workflows/00_settings*.md` 与前端实施手册 atom 清单做全量走查。

## 4. 风险与回滚

- **A1 风险**：`STUDIO_SIDECAR_PORT` env 没注入或被 vite 忽略 → fallback 仍打 8787。**缓解**：A1 完成后先 `ps eww -p <vite_pid> | grep STUDIO_SIDECAR_PORT` 验证 env 在场。
- **A2 风险**：强写 `LocalGatewayConfigStore` 引入 etag race（两个并发 PUT）。**缓解**：使用 `if_match=existing.etag`，conflict 时重试一次。
- **B 风险**：CopilotTab 改动面大（~10 处），可能引入回归。**缓解**：每 finding 一条 vitest case，B 串行做完后整套 vitest 必绿。
- **C 风险**：cooling_down + a11y + i18n 这种交叉切面改动可能跟 C7（shell role roundtrip）的 toast 决策冲突。**缓解**：C7 先做 pytest 验证，再决定改 UX。
- **回滚**：每 Wave 一个 commit；blocker（A）必须独立 commit 便于 revert；B 内部按 R-Fx 顺序拆 commit，C 各自 commit。
