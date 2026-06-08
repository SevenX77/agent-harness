---
ws_id: WS-5-copilot-workbench
doc: task (GREEN 交接)
depends_on: [WS-0, WS-1]
gate: RED 已先行失败 + PM 契约门通过 + 用户聊天窗口明确确认（2026-06-08）
red_baseline_verified: true
owns_files:
  - apps/studio/frontend/src/components/copilot/
  - apps/studio/frontend/src/store/copilotStore.ts
  - apps/studio/frontend/src/hooks/useCopilot.ts
  - apps/studio/backend/app/services/copilot.py
  - apps/studio/backend/app/routers/copilot.py
  - apps/studio/backend/app/routers/llm.py   # 仅 Copilot SDK test 段，与 WS-4 共享，排队
  - apps/studio/frontend/src/components/studio/settings/copilot/
forbidden_files:
  - apps/studio/tauri/src/lib.rs
  - apps/studio/tauri/src/native_fs.rs
  - packages/graph-agent/**
  - packages/graph-agent-gateway/**
spec_ssot:
  - docs/studio/mvp1/_impl/IMPL_PLAN.md §三/§六/§七
  - docs/studio/mvp1/01_workflows/00_settings-ux-spec.md §3
  - docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md
  - docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md
  - docs/development/FRONTEND_UI_SPEC.md §2
status: green-automated-verified
e2e_status: deferred-by-user; blocked-on-engine-mvp1-baseline
manual_app_restart_status: pending-before-final-manual-qa
---

# WS-5 Copilot 工作台 — Task（GREEN 交接）

> 本文是 RED 契约门通过后的执行交接。执行者（Gemini）只能把**已批准的 RED 实现到 GREEN**，
> 不得删改、弱化 RED，不得扩大到 WS-2/WS-3/WS-4/WS-6。需求契约见
> `requirements-ws5-copilot-workbench.md`，本文不复述需求，只给 GREEN 边界与指引。

## 0. 硬性前置（必须遵守，违反即作废）

1. **唯一真相源 = Studio MVP1 设计 / 需求文档**（见 frontmatter `spec_ssot`）。**禁止**按当前 MVP0 旧实现或旧测试反推"应该怎么做"；旧代码/旧测试只能当 drift 证据。
2. **已批准 RED 不得删除、弱化或改成 mock 绿**。断言只能保留或加强；不许通过 mock 掉 registry DTO / SDK probe / session writer / route fallback 制造假绿（no-fake 边界，需求书 §6.13）。
3. **GREEN 只允许改 `owns_files` 范围**。`apps/studio/tauri/src/lib.rs`、`native_fs.rs`、`packages/graph-agent/**`、`packages/graph-agent-gateway/**` 一律**禁止触碰**。`routers/llm.py` 只动 Copilot SDK test 段，碰到 WS-4 占用段先登记 deferred 或请求文件锁。
4. **session 冷启动恢复保持 `blocked-on-WS-1`**：Tauri 仅有 `write_workspace_file`，无 `read_workspace_file`/list（`lib.rs` 归 WS-1）。落盘只用 `writeWorkspaceFile` + `ensureWorkspaceSupportDirs`；**严禁 localStorage 假持久化**。冷启动恢复测试保持 `it.skip`，不要为了凑绿改成内存/localStorage 假恢复。
5. **fallback 链(#9) 和 role-key prefix(#5 后端侧) 是回归锁**：当前已 GREEN，保持 GREEN，**不许**为它们另造假 RED 或削弱现有断言。
6. **改后端 Python 后必须重启 Studio App / 重新 `cd apps/studio/tauri && cargo tauri dev` 再验**，确认加载的是新代码（需求书 §6.11 / §8）。
7. **实现前必须等用户在聊天窗口明确确认**；系统自动审批不算确认。本 task 进入 GREEN 编码前，按团队规则再次确认。

## 1. owns_files（并发锁）

见 frontmatter `owns_files`。`routers/llm.py` 与 WS-4 共享：WS-5 只处理 Copilot SDK test parity（`_probe_copilot_sdk_tool_call` 及其落地），不改 API Keys / LLM Roles / model registry materialization 公共逻辑。

## 2. 禁止触碰

- `apps/studio/tauri/src/lib.rs`、`apps/studio/tauri/src/native_fs.rs`（WS-1 锁）。
- `packages/graph-agent/**`、`packages/graph-agent-gateway/**`（不复制 gateway ③b 内核，只消费 `resolve_role("copilot_chat")` route handoff）。
- Canvas / authoring panels / run·golden·debug / 安全写全链路 / LLM Roles 核心编辑（范围锁定，需求书 §9）。

## 3. 已批准 RED 清单（实现到 GREEN 的目标）

> 这些 RED 已先行跑过、确认真失败。GREEN = 让它们变绿且不削弱断言。

### 后端（pytest，`apps/studio/backend`）
| RED | 文件 | GREEN 要做什么（指向 SSOT，不给完整代码） |
|---|---|---|
| SDK parity ×3 | `tests/routers/test_copilot_sdk_test.py` | 把 `_probe_copilot_sdk_tool_call`（`routers/llm.py`）从 `anthropic.AsyncAnthropic` 改成**真实 `ClaudeSDKClient` + per-session env 注入**路径（复用 `services/copilot.py` 的 `build_options`/`_session_factory`/route runtime 解析），发真工具调用 smoke；成功写回 `claude_sdk_tools` capability + evidence。依据 settings-ux-spec §3.4/§3.8、llm-copilot-http-api §6。 |
| ThinkingBlock | `tests/services/test_copilot_event_translator.py::test_translate_thinking_block_preserves_reasoning_stream` | `services/copilot.py` 的 `_translate_assistant_message` 处理 `ThinkingBlock`，产出 `type="thinking_delta"` 事件、`content` 保留推理文本；`models/copilot.py` 增 `CopilotEventThinking`（discriminator `thinking_delta`）并并入 `CopilotEvent` union。依据 copilot-assist F1。 |

### 前端（vitest，`apps/studio/frontend`）
| RED | 文件 | GREEN 要做什么 |
|---|---|---|
| session model ×5 | `src/store/copilotStore.session.red.test.ts` | `store/copilotStore.ts` 改为 session-aware：`setContext(workspaceId, skillId)`、`newSession()`、`switchSession(id)`、`appendMessage()`；session 按 (workspace, skill) 隔离、支持多 tab + new chat；`appendMessage` 经 `lib/tauri` 的 `ensureWorkspaceSupportDirs`+`writeWorkspaceFile` 落盘；写失败置 `persistenceError` 显式告警。依据 copilot-assist F2 / D8。`useCopilot.ts` 适配新 store。 |
| thinking 渲染 ×2 | `src/components/copilot/__tests__/copilot-thinking.red.test.tsx` | `types/copilot.ts` 的 `normalizeCopilotEvent` 识别 `thinking_delta`；`copilot-panel.tsx` 的 `ChatMessageItem` 把 thinking 渲染为可折叠 thought（`<details>`），保留机器码、不落 "Unknown Copilot event"。 |
| CopilotTab 去 mock ×2 | `src/components/studio/settings/copilot/CopilotTab.red.test.tsx` | `CopilotTab.tsx` 去掉对 `mock-copilot-data` 默认 props 的回退；无真 registry → 空态（不渲染 mock 内置卡）。 |
| derivation ×3 组 | `src/components/studio/settings/copilot/copilot-role-derivation.red.test.ts` | **新建** `copilot-role-derivation.ts`，导出：`deriveCopilotCandidateGroups`（按后端 capability/protocol，untested route 仍可见，不用名字启发式）、`pickDefaultCopilotGroupIds`（动态阶梯：Claude opus 4.8→4.7，DeepSeek V4 Pro→V3.2 Pro，缺 family 不造假）、`applyCopilotModelGroupSelection`（选组保留 `copilot_` role key，修 `selectModelGroup` 把 key 改成裸 `modelGroupId` 的 bug）。`CopilotTab.tsx` 改用该模块。 |

### GREEN 期连带产物
- **新建** `apps/studio/frontend/src/components/studio/settings/copilot/copilot-role-derivation.ts`。
- **删除死代码**：`mock-copilot-data.ts`（`mockCopilotRoles` / `defaultCopilotModelGroups` / `defaultCopilotCredentials` / `isClaudeAgentSdkCompatibleRoute`）与 `copilot-role-state.ts`（无人引用的死模块）。删除后修复所有 import（`CopilotTab.tsx`、`copilot-role-test.ts` 的类型 import、`CopilotModelGroupCard.tsx`、`SettingsPage.test.tsx`）。
- `models/copilot.py` 新增 `CopilotEventThinking`。

## 4. 回归锁（保持 GREEN，不造假 RED）

- **#9 Fallback 链**：`tests/routers/test_copilot_ws_endpoint.py` 的 `..._falls_back_to_second_copilot_route...` 与 `..._reports_clear_error_after_all_copilot_routes_fail`（已 2 passed）。`stream_query` 改动不得破坏多 route 顺序尝试 + 全链失败 scoped error。
- **#5 role-key 后端契约**：`tests/routers/test_copilot_role_key_contract.py`（`_is_copilot_role` 认 `copilot_` 前缀、拒裸 group id）。
- **#10 save status**：`CopilotTab` 已用 `SaveStatusBadge`、无静态 `Backend Integration` 徽章，保持。

## 5. deferred / blocked 登记

- **session 冷启动恢复**：`it.skip('restores sessions from disk on cold reopen (blocked-on-WS-1)')` 保持 skip，标 `blocked-on-WS-1`（缺 native `read_workspace_file`）。WS-1 补读命令后再单独开。**不许** localStorage 假恢复。
- **`SettingsPage.test.tsx`（≈800–833 行）copilot 断言**：断言 mock 内置卡，去 mock 后会变红。该文件在 `components/studio/`（非 WS-5 owns 目录，与 WS-4/共享）。GREEN 期需把这两个 copilot `it` 块迁入 WS-5 自有 copilot 测试，或与 WS-4 协调后更新；**不得**为保旧断言而恢复 mock 行为。处理结果写进收尾报告。

## 6. 旧 MVP0 测试处理台账（必须随 task/handoff 保留）

- **改写**：`backend/tests/routers/test_copilot_sdk_test.py` —— 删除对 `_probe_copilot_sdk_tool_call` 的 mock（假绿），改为 forbid `AsyncAnthropic` + 真实 `ClaudeSDKClient`/env 注入路径断言；保留 openapi 文档断言。
- **删除**：`frontend/.../settings/copilot/copilot-role-state.test.ts` —— 断言 `mockCopilotRoles`，测的是死模块 `copilot-role-state.ts`。
- **保留（MVP1 对齐、非假绿）**：`test_copilot_ws_endpoint.py`（fallback + env，真 seam）、`model-picker.test.tsx`（exact route_id + 真 registry）、`copilot-role-test.test.ts`（真 job 轮询 helper，仅类型 import）。
- **deferred / 迁移**：`SettingsPage.test.tsx` copilot 段（见 §5）。

## 7. 验证命令

```bash
# 后端（在 apps/studio/backend，使用 worktree root .venv）
../../../.venv/bin/python -m pytest tests/routers/test_copilot_sdk_test.py \
  tests/services/test_copilot_event_translator.py \
  tests/routers/test_copilot_ws_endpoint.py \
  tests/routers/test_copilot_role_key_contract.py -q

# 前端（在 apps/studio/frontend）
npx vitest run src/store/copilotStore.session.red.test.ts \
  src/components/copilot/__tests__/copilot-thinking.red.test.tsx \
  src/components/studio/settings/copilot/CopilotTab.red.test.tsx \
  src/components/studio/settings/copilot/copilot-role-derivation.red.test.ts \
  src/components/copilot/__tests__/model-picker.test.tsx \
  src/components/studio/settings/copilot/copilot-role-test.test.ts

# typecheck / build
npm run -s typecheck && npm run -s build
```

GREEN 退出 = 上述 RED 全绿、回归锁仍绿、typecheck/build 通过。

## 8. 后端重启验证（强制）

改 `services/copilot.py` / `routers/copilot.py` / `routers/llm.py` 后，**必须**重启 Studio App 或重新 `cd apps/studio/tauri && cargo tauri dev`，并实测 Copilot WS 或 `/api/copilot/roles/{role}/test-sdk` 端点加载的是新代码；把验证结果写进收尾报告。

## 9. 真实 e2e（deferred，§6.12）

用户已明确指示本批**不做 e2e**。Copilot 面板和 Settings Copilot 的真实浏览器 / Playwright
成功、失败、空态、窄宽度检查登记为 deferred，等待 engine/backend MVP1 baseline 稳定后再开。
本批验收不启动真后端 e2e、不改 `apps/studio/tests-e2e/**`，也不得宽泛 kill `cargo tauri dev` /
Vite / sidecar。

## 10. baseline 回写（§10 / IR6）

实现并验证后，按真实代码状态回写 `copilot-assist`、`03_regions/copilot`、`llm-copilot-http-api`、`settings`/`studio-settings` 中与 Copilot 相关的 `baseline.md`。只写已实现并验证的现状；brain、safe write、wizard、analysis bar 等未做项继续保留 target-design / deferred。

## 11. 退出标准

- [x] 已批准 RED 全绿，断言未削弱；回归锁仍绿（pytest 31 passed；vitest 24 passed / 1 skipped）。
- [x] Copilot SDK test 走真 `ClaudeSDKClient`（无 `AsyncAnthropic`）。
- [x] Settings Copilot 消费真 registry DTO，`copilot_` 前缀 / 单 model group / fallback / save status 通过。
- [x] chat event 渲染保留 Thinking / tool / result / error / done 结构。
- [x] session 多 tab / workspace·skill 隔离 / 写盘失败告警通过；冷启动恢复仍 deferred。
- [x] 死代码 `mock-copilot-data.ts` / `copilot-role-state.ts` 已删，import 修复。
- [~] typecheck / build 通过；后端改动的完整 Studio App 重启验证待最终手动 QA。
- [~] Playwright e2e 成功/失败/空态/窄宽度：deferred-by-user，blocked-on-engine-mvp1-baseline。
- [x] 未碰 `lib.rs` / `native_fs.rs` / gateway / engine packages。
- [ ] **Codex 审**（diff 对照 §3/§6/§11）→ **PM 终审**（baseline 诚实、gateway 边界未复制、后端重启已记录、旧测试台账齐全）。

## 12. Gemini GREEN Prompt（可直接投喂）

见同目录交接 prompt（本 task §0–§11 即其上下文）；Prompt 正文如下文聊天交付。
