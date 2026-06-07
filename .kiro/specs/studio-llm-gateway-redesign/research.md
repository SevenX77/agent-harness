# Research Notes - LLM Gateway & Roles Code Walkthrough

## 1. Copilot Tab Switching State Loss (切页状态丢失调研)

### 现状分析
* **状态定义位置**：`apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx` 第 166 行：
  ```typescript
  const [routeStatusOverrides, setRouteStatusOverrides] = useState<Record<string, CopilotRouteJobStatus>>({})
  ```
* **生命周期受限**：Settings 面板使用 Tab 切换机制。在 `SettingsPageContent.tsx` 第 80 行中：
  ```tsx
  {activeTab === "llm_roles" ? (
     <LlmRolesTab ... />
  ) : activeTab === "copilot" ? (
     <CopilotTab ... />
  ) : ... }
  ```
  这意味着，只要用户切换到非 Copilot 的 Tab（例如 General 或 API Keys），整个 `CopilotTab` 组件就会被 React **完全销毁并卸载 (Unmount)**。储存在其内部组件 State 的 `routeStatusOverrides` 被直接清空。当用户切回 Copilot 页时，组件重新挂载，测试状态只能回归初始的 `untested` 或未测试状态。
* **重构方案**：
  我们需要将 `copilotRouteStatusOverrides` 提升到父级 `SettingsPage.tsx` 组件中。由 `SettingsPage` 维护这个 overrides 字典状态，并在渲染 `CopilotTab` 时作为 prop 传递进去：
  ```tsx
  <CopilotTab
    data={rolesData}
    credentials={credentials}
    modelGroups={modelGroups}
    onChange={onRolesDataChange}
    routeStatusOverrides={copilotRouteStatusOverrides}
    onRouteStatusOverridesChange={setCopilotRouteStatusOverrides}
    ...
  />
  ```

---

## 2. WaveSpeed & Claude SDK Protocol Compatibility (WaveSpeed 协议兼容性调研)

### 现状分析
* **WaveSpeed 服务特征**：
  在 `docs/development/llm_provider_notes/wavespeed.md` 中记录，WaveSpeed 官方 Endpoint 为 `https://llm.wavespeed.ai/v1`，主协议为 `openai_compatible`（支持 `/chat/completions`）。
* **Claude Agent SDK 心智与要求**：
  Copilot 页面是基于 **Claude Agent SDK** 构建的，该 SDK 仅兼容 Anthropic 的 Messages 格式请求（即 `anthropic` 或 `anthropic_compatible` 协议）。
* **问题发生的根源链条**：
  1. **API Keys 页探测成功**：用户在 API Keys 页新建了一个 WaveSpeed 的第三方 Provider，并且把它的协议指定为了 `anthropic_compatible`。由于 API Keys 页的参数可达性探测（Get Models 或极简 Probe）可能仅发起了底层的轻量可达性验证，一旦验证成功，就会判定网络及参数通路建立。
  2. **Copilot 高阶测试失败**：进入 Copilot 面板测试该路由时，后端 `llm.py` 会进入专门针对 Copilot 的专属探测函数 `_probe_copilot_sdk_tool_call`（第 2150 行）。该探测函数在底层使用 `AsyncAnthropic` 客户端：
     ```python
     client = AsyncAnthropic(api_key=api_key, base_url=base_url)
     response = await client.messages.create(...)
     ```
     `AsyncAnthropic` 客户端会往 `base_url + "/messages"`（即 `https://llm.wavespeed.ai/v1/messages`）发起 POST 请求。由于 WaveSpeed 实际上仅支持 OpenAI 的格式规范而不支持标准的 Anthropic messages 接口路由，该请求会在 WaveSpeed 侧直接报 404 或协议格式错误。
  3. **状态判定为 Unsupported**：由于 HTTP 请求抛出异常，`_probe_copilot_sdk_tool_call` 返回了 `status="error"`。当这个状态返回给前端时，在前端 `copilot-role-test.ts` 的状态映射器中（第 63 行）：
     ```typescript
     if (status === "failed" || status === "blocked") return "unsupported"
     ```
     这直接导致 WaveSpeed 路由的就绪灯亮红，状态显示为 "Unsupported"（不支持）。
* **核心结论**：
  WaveSpeed 接入 Anthropic API 并不是它的原生模式，强行以 Anthropic 接入后，其物理端点实际上是不支持 Anthropic 原生 messages 调用格式的。因此，Copilot 专属的工具调用真机探测在发送 Anthropic Tools schema 时直接失败，后端捕获到异常并回写失败是**符合事实的物理安全边界行为**。

---

## 3. LLM Roles Validation Deadlock (角色保存硬校验死锁调研)

### 现状分析
* **死锁根源位置**：`apps/studio/backend/app/routers/llm.py:_save_roles_with_active_routes`（第 4726 行）：
  ```python
  def _save_roles_with_active_routes(data: RolesData) -> RolesData:
      active_path = roles_path()
      active_route_ids = set(load_credentials().provider_routes)
      try:
          validate_references(data, known_route_ids=active_route_ids)
          save_roles_file(active_path, data, known_route_ids=active_route_ids)
          return load_roles_file(active_path)
      except InvalidRoleReference as exc:
          raise HTTPException(status_code=400, detail=str(exc)) from exc
  ```
* **阻断流程**：
  当用户执行添加、删除、或修改角色的动作时，前端会将修改后的 `RolesData` 发送给 `PUT /api/llm/roles`，或者由 `DELETE /api/llm/roles/{role_name}` 处理。后端接收后会调用 `_save_roles_with_active_routes`。
  该函数提取了当前 credentials 里的 active_route_ids，然后对**整份 `llm_roles.yaml` 的所有内容**执行 `validate_references`。
  由于系统初始化下发的 `llm_roles.yaml` 包含了大量模板角色（例如 `fast`），这些模板角色引用了例如 `openrouter-prod:deepseek.deepseek-r1` 这样尚未激活/配置的路由。
  一旦 `known_route_ids` 缺席了这些路由，`validate_references` 就会抛出 `InvalidRoleReference`，保存请求以 400 校验失败告终。这直接导致任何角色管理动作（包括添加新角色、删除不相干的自定义角色）全部锁死，完全无法进行 YAML 写入。
* **重构方案**：
  解耦角色声明（YAML）与物理凭证（Credentials）。在 YAML 保存时，**只应进行 Schema 规范度与基本校验**，而不应该因为物理路由没配好就拒绝写入。
  我们直接在 `_save_roles_with_active_routes` 中**以 `known_route_ids=None` 保存 YAML**。而在运行期（运行时 Resolver 或真机 Role 测试时）才执行延迟校验与降级。这既能保障运行时不崩，又能完美释放编辑侧的死锁！
