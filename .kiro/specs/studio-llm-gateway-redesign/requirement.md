# Requirement Specification - LLM Gateway & Roles Redesign

## 1. Background & Core Pain Points (背景与核心痛点)

当前 Studio 平台的 **API Keys**（凭证管理）、**LLM Roles**（逻辑角色配置）与 **Copilot**（应用交互层）在实现层面存在以下关键缺陷，导致用户体验割裂且功能死锁：

1. **Copilot 测试状态丢失 (State Volatility)**：
   * **痛点**：在 Copilot 页面点击 "Test" 测试完成后，只要切换到 Settings 的其他页面（如 General 或 API Keys）再切回来，之前测试成功的状态（如 `SDK Ready` 数量和各个 Route 的 `ready`/`unsupported` 状态点）会完全消失，变回未测试状态。
   * **根源**：Copilot 页面测试状态（`routeStatusOverrides`）目前仅作为 React 局部状态存在于 `CopilotTab.tsx` 中。当切换 Tab 时，`CopilotTab` 组件被卸载 (Unmount)，其局部 State 被完全销毁，未作任何持久化或全局状态提升。

2. **WaveSpeed 第三方服务兼容性壁垒**：
   * **痛点**：用户在 API Keys 页面添加 WaveSpeed 选用 Anthropic 协议能够测试成功，但在 Copilot 页面中却被判定为 `Unsupported`（不支持）。
   * **根源**：WaveSpeed 物理协议为 `openai_compatible`。若用户为了配合 Claude SDK 的 Anthropic API 调用心智而在 API Keys 中强行以 `anthropic_compatible` 接入且测试成功，由于 WaveSpeed 实际上仅支持 OpenAI 的 `/chat/completions` 或专有 `/wavespeed-ai/any-llm` 格式，`AsyncAnthropic` 客户端对其发起的 SDK Tool Call 真实测试会抛出 404 或格式异常。此外，在 `mock-copilot-data.ts` 的过滤逻辑中，对于未明确适配为 deepseek 或 ark 命名的第三方服务，默认走 `anthropic_messages` 方式请求，导致非标准代理在 Copilot 高阶校验中直接折戟。

3. **LLM Roles 页面添加与删除 API 彻底失效 (Schema Deadlock)**：
   * **痛点**：用户在 LLM Roles 页面执行添加、修改或删除角色动作时，频繁遭遇 `Validation failed: Request failed with status code 400 - The request parameters are invalid. (role fast fallback_chain[0] references unknown route ...)` 的报错，导致任何编辑操作全部被锁死失效。同时，界面上依然顽固显示 `balanced`、`premium`、`fast` 等无关的仓库模版数据。
   * **根源**：
     * **硬校验死锁**：后端在处理角色 YAML (`llm_roles.yaml`) 保存或删除请求时，会强制调用 `validate_references` 校验**整份文件中的所有角色**是否都存在于当前用户的物理凭证库中（`known_route_ids`）。如果默认模版里的 `fast` 角色引用了用户尚未配好的 `openrouter-prod:deepseek.deepseek-r1`，即便用户只是想删除自己建的 deepseek 角色，保存操作也会因为 unrelated `fast` 角色校验失败而整体报错，形成无法自拔的死锁！
     * **缺乏边界隔离**：仓库默认下发的 `llm_roles.yaml` 模版包含了大量预设角色。用户的 `llm_credentials.json` 刚创建时没有任何 credentials，因此任何一次对 Roles 的 REST API 写操作都会直接触发 validation panic，彻底阻断了增删改路径。

---

## 2. First-Principles Redesign Plan (第一性原理重构设计)

为彻底消解上述痛点，本 Spec 提出一套基于边界隔离与状态提升的第一性原理重构方案。

### 2.1 状态提升：持久化与非易失性 Copilot 测试状态
* **REQ-1**：将 CopilotTab 的 `routeStatusOverrides` 状态从局部组件 State **提升至 SettingsPage.tsx 的全局 Tab 共享 State**（或者统一存入全局 store 中），在 Settings 面板生命周期内保持常驻。
* **REQ-2**：切换 Tab 时，SettingsPage 保证该测试状态不丢失。当再次切回 Copilot 页面时，能够完美呈现上一次的测试进度与就绪报告。

### 2.2 物理连通参数建立 vs. 运行期延迟路由解析
* **REQ-3**：重新理顺 **API Keys 页面（参数可连通性）** 的递进式心智模型：
  * **官方 Provider**：用户输入 API Key，点击 Test 证明网络可达。
  * **第三方 Provider**：输入 API Key + Base URL。为了确认这组参数的真实物理通道可达，必须通过 `Model Probe` 探测。只要探测成功，API Key + Base URL 输入框旁边亮起**绿色小勾**，Provider 状态升级为 `Connected` (`unverified_manual`)。
* **REQ-4**：**侧边栏与模型装配的去过滤化**：
  * LLM Roles 页面右侧的 `Available Models` 侧边栏和 Copilot 的模型选择中，**必须完整呈现所有已连通 Provider 的可用模型**，绝对不能因为模型状态为 `untested` 而做阻断性过滤。
  * 允许用户将任何已登记的模型/路由拖入 fallback chain，在 Role Page 点击 **`Test`** 时才执行真机 Endpoint 连通性测试。测试成功后，后端自动将该物理路由状态升级为 `verified`（就绪投影为 `ready`），亮起**绿色指示灯**。

### 2.3 解耦角色校验与凭证约束 (Validation Decoupling)
* **REQ-5**：**消除保存死锁**：
  * 逻辑层的 YAML 结构（角色 Fallback 意图）与物理层的 JSON 结构（物理连接凭证）应该在**写入时完全解耦**。
  * 后端执行 `_save_roles_with_active_routes` 进行角色保存/删除时，**不再强绑定 active_route_ids 进行硬校验拦截**（即传入 `known_route_ids=None` 给保存函数，只做基础的 YAML 格式与 Schema 验证）。
  * **运行期容错与显示回退**：若角色 fallback chain 包含未配置凭证的路由，在 runtime resolver 中由 `ModelResolver` 执行延迟路由解析时自动过滤或优雅 Fallback，在前端 UI 中将其显示为 `untested` / `offline`，但绝对不阻止角色的持久化增删改操作。

### 2.4 规范化 WaveSpeed 与 Claude SDK 兼容性处理
* **REQ-6**：明确 WaveSpeed 这一 OpenAI 兼容端点在 Claude SDK 调用时的行为边界：
  * 明确记录并检测当 WaveSpeed 选用非原生 Anthropic 协议时的报错日志，并在 `_probe_copilot_sdk_tool_call` 的测试报告中提供直观、明确的降级提示。
  * 在 Kiro Spec 下完善其参数持久化记录，保证在网关层做 100% 格式对齐与优雅回退。

---

## 3. Verification Plan (验证计划)

### 3.1 Automated Test Suites (自动化测试验证)
* **Backend Pytest**：
  * 运行 `uv run pytest` 验证所有 backend 接口与 schema contract，特别是 `test_llm_v4_backend_contract.py` 与 `test_copilot_sdk_test.py`。
  * 引入或修补测试用例以验证不带 active_route_ids 限制的角色 YAML 写入流程是否通畅。
* **Frontend Vitest**：
  * 运行 `npm run test` 确保 settings、api-keys、llm-roles 与 copilot-tab 相关的 416 个单测全部通过。

### 3.2 Manual Verification Scenario (人工体检流程)
1. **API Keys -> Copilot 联动体检**：
   * 在 API Keys 页测试第三方通道，获取 untested 模型列表。
   * 切至 Copilot 页，将新路由拖入 fallback 链，点击 Test 测试并亮绿。
   * 切回 API Keys，再切回 Copilot，**实测验证亮绿状态完美保留**。
2. **Roles 页面增删改无死锁体验**：
   * 在未配置 OpenRouter 凭证的前提下，在 Roles 页面任意添加一个自定义角色或删除已有角色。
   * **实测验证操作瞬间成功，无任何 Validation 400 报错拦截**！
