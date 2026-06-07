# research.md — 代码走访与系统设计现状剖析

## 1. API Keys 页面测试与草稿同步现状

### 1.1 凭证测试接口与多方同步缺失
* **定位文件**：`apps/studio/backend/app/routers/llm.py:test_endpoint` (L460 - L572)
* **现状分析**：
  * 当前的 `test_endpoint` 只做了一件事：使用 `_ping_provider`（L482）向真实的 LLM 接口发请求。
  * 请求成功后，如果检测到是第三方的 Provider，直接将其状态更新为 `"unverified_manual"` (L501) 并持久化存回 credentials。
  * **设计偏差**：完全没有引入对远端 Draft（`import_drafts.json`）的下载、比对、diff 补全机制。`/catalog/sync`（L397）接口与测试链路处于完全割裂的状态，导致无法满足多方草稿同步更新本地配置的心智模型。

### 1.2 前端对第三方 Provider 成功状态映射错误
* **定位文件**：`apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:TestMessage` (L151)
* **现状分析**：
  * 在 `ProviderCard.tsx` 中，`TestMessage` 组件只处理了 `"ok"`、`"testing"`、`"not_configured"` 以及 `["invalid_key", "rate_limited", "quota_exceeded", "network_error", "timeout"]` 状态。
  * **设计偏差**：当第三方渠道 Get Models 成功后，后端写入的 `last_test_status` 为 `"unverified_manual"`。在 `TestMessage` 内，这个状态被漏判，直接落入 fallback 返回 `<Badge variant="secondary">Not configured</Badge>`。这导致卡片明明获取模型成功了，却依然显示灰色“未配置”图标。
  * **绿色小勾漏显**：`hasReachableModelList` 计算属性（L779）中只判断了 `matchedStatus === "untested" || matchedStatus === "ok"`，因为忽略了 `"unverified_manual"`，导致输入框旁边的绿色连通小勾在第三方测试成功后无法正常显现。

---

## 2. LLM Roles 页面：Copilot 残留与测试写回缺失

### 2.1 Copilot 角色折叠面板视觉残留
* **定位文件**：`apps/studio/frontend/src/components/studio/settings/llm-roles/RoleCardList.tsx:roleCategoryGroups` (L146)
* **现状分析**：
  * 在 Roles 列表渲染逻辑中，依然定义了 `category: "copilot"`（L166）这一完整分组，并在手风琴组件内进行挂载。这与 Copilot 已拥有专属页面的现状冲突。

### 2.2 角色测试（Role Test）不写回第三方 Route 状态
* **定位文件**：`apps/studio/backend/app/routers/llm.py:_role_test_provider_result` (L1855)
* **现状分析**：
  * 当执行 Role 测试时，对于官方路由（`official`），会通过 `_ensure_official_role_test_verified_profile`（L1873）进行真机探测并把 `verified` 状态写存回 `credentials.json`。
  * **但对于第三方路由（L1888）**，代码直接调用了 `_probe_role_route` 并仅在 HTTP 响应中返回 status，**完全没有写入 credentials 和 evidence record**。
  * 这导致即便用户在 Roles 卡片里测试第三方模型（比如 OpenRouter 的 DeepSeek 链路）成功，模型标签依然会是灰框（`unverified_manual`），警告也不会消失。

### 2.3 可用模型侧边栏过滤失效
* **定位文件**：`apps/studio/frontend/src/components/studio/settings/llm-roles/AvailableModelsSidebar.tsx:buildAvailableModelGroups` (L377)
* **现状分析**：
  * 侧边栏在构建模型列表时，直接抓取了全局所有的 `provider_models`（L384）并显示其 `ui_state`，这导致许多尚未在 API Keys 页面进行测试连通（状态为 `needs_setup` 或 `untested`）的第三方 Endpoint 及其模型直接被渲染供用户拖拽。
  * 应该严格拦截非 `ready` / `verified` 状态的 Endpoint 模型，保持界面只显示可用通道。

---

## 3. Copilot 专属页面测试逻辑套用通用机制

### 3.1 缺乏 SDK 级别专属连通性校验
* **定位文件**：`apps/studio/frontend/src/components/studio/settings/copilot/copilot-role-test.ts:runCopilotRoleTestJob` (L24)
* **现状分析**：
  * 前端 `CopilotTab.tsx` 里的 "Test" 按钮，目前触发的依然是和普通 Role 完全一样的 `startRoleTestJob` 接口。
  * 后端完全没有针对 Claude SDK 专用的 Headers、API 响应路由与工具调用（Tool Calling）进行实测与仿真模拟，无法完成 SDK 高阶可用性凭证的回写。
