# tasks.md — 大模型凭证、角色与 Copilot 交互心智对齐实施任务单

本任务单用于追踪 `.kiro/specs/studio-llm-copilot-reconciliation/` 规范的落地实施工作，严格遵循 TDD 先行和物理路由无 Mock 架构要求。

---

## 1. 物理凭证层（API Keys）与角色状态回写 (已完成部分)
- [x] 1.1 `ProviderCard.tsx` 对 `"unverified_manual"` checkmark 状态支持
- [x] 1.2 `TestMessage` 支持 `"unverified_manual"` 状态下显示为 "Connected"
- [x] 1.3 `LlmRolesTab.tsx` 和 `RoleCardList.tsx` 彻底剔除 Copilot 视觉残留
- [x] 1.4 后端 `llm.py` 在第三方角色测试通过时，将状态置为 `verified` 并写入证据草稿库 (`import_drafts.json`)

---

## 2. 彻底清理 Copilot Mock 路由适配层与前端测试修复 (已完成)

### 2.1 前端：CopilotTab 真实数据适配与单元测试回归 (已完成)
- [x] 2.1.1 在 `mock-copilot-data.ts` 中定义通用的物理渠道数据默认值 `defaultCopilotCredentials` 和 `defaultCopilotModelGroups`
- [x] 2.1.2 修改 `CopilotTab.tsx` 函数签名，采用上述默认物理渠道数据作为 `credentials` 和 `modelGroups` 的缺省参数
- [x] 2.1.3 修改 `SettingsPage.test.tsx` 的 `baseViewProps`，当 `activeTab === 'copilot'` 时动态混入 `defaultCopilotCredentials` 和 `defaultCopilotModelGroups`
- [x] 2.1.4 运行 `npm run test -- --run`，见证所有 416 个 Vitest 前端用例全绿通过

### 2.2 后端：废除 Mock ID 路由翻译适配层 (已完成)
- [x] 2.2.1 彻底删除 `llm.py` 中 `_resolve_mock_copilot_route` 适配函数
- [x] 2.2.2 重构 `_role_test_targets` 函数，直连物理 `route_id`，剔除 Mock 翻译逻辑
- [x] 2.2.3 重构 `_persist_copilot_sdk_probe_success` 函数，直连物理 `route_id` 写入，剔除 Mock 翻译逻辑
- [x] 2.2.4 运行 `uv run pytest`，验证后端所有 409 个用例全绿通过，包括 `test_copilot_sdk_test.py`

---

## 3. 交叉验证与本地真机体验 (已完成)
- [x] 3.1 重启 Studio App Dev 服务
- [x] 3.2 在浏览器或 Tauri Shell 中打开 Copilot 面板，实测点击 Test 并变绿，验证状态保存正常，无 Mock 痕迹
- [x] 3.3 在 API Keys 页面连通并获取第三方 untested 模型，在 Copilot 面板拖动/排序真实渠道路由，点击 Test 运行 Claude SDK 级别工具测试，验证绿色点亮且状态完美保存

---

## 4. 彻底解决 Copilot 动画缺失与第三方路由测试对齐 (100% 已完成)
- [x] 4.1 通用 `/roles/{role_name}/test-jobs` 异步任务底层 `_role_test_provider_result` 引入 Copilot 路由分流，与专有 `_probe_copilot_sdk_tool_call` 探测完美对齐（后端对齐）
- [x] 4.2 修复 `CopilotTab.tsx` 默认无配置渲染，扩大切片范围以支持 `sonnet-4-7-third-party` 第三方角色渲染与测试（前端修复）
- [x] 4.3 遵循严格 TDD 原则，编写并跑通 `test_copilot_role_test_jobs_aligns_with_sdk_probe` 单元测试，验证 pytest (410/410) 与 vitest (416/416) 双全绿！

