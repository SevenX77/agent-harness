# design.md — 系统重构与前后端协议演进方案

## 1. 物理凭证层（API Keys）重构方案

### 1.1 "Get Models" / "Test" 的多方草稿合并设计
在后端 `POST /endpoints/{endpoint_id}/test`（`llm.py`）中，引入与远端/本地草稿的三方对比合并机制：
1. **网络拉取阶段**：执行 `_ping_provider`，同时并发拉取本地及远端最新草稿库：
   ```python
   draft = load_evidence_library() # 本地草稿
   # 如果需要, 自动尝试与远端进行一次 Catalog 同步
   try:
       await sync_remote_evidence_library()
       draft = load_evidence_library()
   except Exception:
       pass
   ```
2. **三方模型合并比对**：
   * 优先使用 API 连通返回的 `discovered_model_ids`。
   * 若 API 失败或未返回模型，且全局 credentials 中无此模型，则从 `draft.route_candidates` 中过滤该 endpoint 的候选模型并写入。
   * 如果 API 返回的模型存在于 `draft.route_candidates` 中，将 draft 里的高阶属性（能力集 `capabilities`、`metadata` 等）通过 diff 补齐合并到全局 `credentials.provider_routes`。

### 1.2 参数级验证 checkmark 前端状态映射修复
在 `ProviderCard.tsx` 中增加对 `"unverified_manual"` 状态的显式支持：
* **输入框绿色小勾 (checkmark)**：
  ```typescript
  const hasReachableModelList = Boolean(
    hasRequiredConfig &&
    matchedResult &&
    !matchedErrorCode &&
    // 允许 unverified_manual 状态作为参数可达的标记
    (matchedStatus === "untested" || matchedStatus === "ok" || matchedStatus === "unverified_manual") &&
    (matchedResult.last_test_at || matchedResult.last_test_message || availableModels.length > 0 || availableSdks.length > 0),
  )
  ```
* **右上角连接状态 Badge**：
  在 `TestMessage` 中，支持 `"unverified_manual"` 显示为特定小字（如“参数已通，待跑模型测试”）：
  ```typescript
  if (status === "unverified_manual") {
    return (
      <Badge variant="outline" className="text-warning gap-1">
        <CheckCircle2 className="size-3 text-success" />
        Parameters Reachable
      </Badge>
    )
  }
  ```

---

## 2. LLM Roles 逻辑层重构方案

### 2.1 彻底割除 Copilot 视觉残留
* 在 `RoleCardList.tsx:roleCategoryGroups` 中，彻底剔除 `category === "copilot"` 的对象元素。
* 在 `LlmRolesTab.tsx` 中，初始化 `CatalogAccordion` 时将 `defaultValue` 仅保留为 `["graph-agent"]`。

### 2.2 角色测试 (Role Test) 的第三方状态回写持久化
在 `llm.py` 运行角色测试的处理器 `_role_test_provider_result` 中：
* 无论是 `official` 还是 `third-party` 渠道，只要 `_probe_role_route` 或 `_probe_model` 返回成功（`status == "ok"`）：
  1. **写入 credentials.json**：加载 `credentials`，将该 `route` 的状态更新为 `status = "verified"`。
  2. **写入 Evidence Library**：调用 `_append_model_probe_evidence(endpoint, result, route_id)`，将此次成功的证据链记录下来，使其能够沉淀到全局的 `import_drafts.json` 中。
* 这保证了第三方路由只要在 Role Card 级测通一次，就能永久在 Role 页面保持绿色边框，消灭 unresolved 警告。

### 2.3 可用模型侧边栏 (AvailableModelsSidebar) 修复
在 `AvailableModelsSidebar.tsx` 中取消对 `untested` 路由的过度过滤：
* **过滤机制**：在 `buildAvailableModelGroups` 内，除了保留 `"ready"` 和 `"cooling_down"`，**必须保留状态为 `"untested"` 的路由**（即已在 API Keys 页面连通并获取到模型，但尚未运行真机 Probe 探测的第三方路由）。
* 允许用户将 `"untested"` 状态的路由正常拖拽装配至 LLM Role 中，随后在 Roles 页面点击 `"Test"` 触发真机测试回写，打破死锁，拉齐至完美心智。

---

## 3. Copilot 专属页面重构方案（彻底废除 Mock 假数据）

为了达成 100% 的前后端一致性，我们废弃一切临时映射或打补丁行为，将 Copilot 页面的 Mock 逻辑连根拔起。

### 3.1 前端重构：动态路由渲染
* **废弃 Mock 静态配置**：停止在前端组件中使用 `mockCopilotRoles` 静态对象列表。
* **动态映射生成**：在 `CopilotTab.tsx` 中，根据从后端获取的真实 `modelGroups` 动态构建兼容 Claude Agent SDK 的可用角色和物理路由。
  * **角色映射**：过滤出 canonical_id 包含 `claude`、`deepseek-v4`、`sonnet` 的模型组，将其映射为可用 Copilot 卡片。
  * **路由生成**：直接展示该模型组下所有已接入（非 `off` 且非 `needs_setup`）的真实物理路由 ID（如 `custom-a8726272-xxx:deepseek.deepseek-v4-pro`）。
* **自动保存回写**：用户在 Copilot 页面拖拽、排序或添加路由时，前端自动向后端 `PUT /api/llm/roles` 接口保存包含 **真实物理路由 ID** 的 fallback chain。

### 3.2 后端净化：彻底删除 Mock 适配代码
* **删除 `_resolve_mock_copilot_route`**：由于前端传输的已是 100% 真实的物理路由 ID，后端彻底移除用于转换 Mock ID 的 `_resolve_mock_copilot_route` 适配函数。
* **净化核心链路**：在 `_role_test_targets`、`_persist_copilot_sdk_probe_success` 和角色测试链路中，直接针对真实的 route_id 进行配置加载与状态回写持久化。

### 3.3 专门的 Copilot SDK 模拟测试与 TDD
1. **测试端点**：`POST /api/copilot/roles/{role_name}/test-sdk`。
2. **实现 Claude SDK 真机测试**：直接对该智能体角色 fallback 链中最上游的**真实物理路由**发起 Claude SDK Messages API 规范的工具调用真机探测。
3. **高阶证据写入**：探测成功后直接向 credentials.json 中的该**真实物理路由**写入 `claude_sdk_tools` 验证通过标志。
4. **重构测试套件**：重构 `test_copilot_sdk_test.py`，全量使用真实的 mock-free 物理路由配置跑通后端测试。

