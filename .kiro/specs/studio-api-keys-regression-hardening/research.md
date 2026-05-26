---
status: Implementing
created: 2026-05-25
owner: Studio
related_requirement: .kiro/specs/studio-api-keys-regression-hardening/requirement.md
---

# Studio API Keys 回归加固调研

## 摘要

这两个回归共享同一种失败模式：局部修复解决了可见症状，但绕开了旧约束。重新加入原生 macOS `Edit` submenu 让输入框里的 `Cmd+V` 可用，但它和之前的“双击提示音”修复冲突。另一方面，v4 registry cutover 后，前端从已持久化 routes 推导 `available_models`，而 Provider Test 路径仍然只记录单个 `model_seen`；因此即使 provider 的 models endpoint 能返回完整模型目录，UI 也只会显示一个已有 route，例如 `claude-sonnet`。

更稳的修法不是继续一个点击一个点击地补。实现应该恢复旧的 double-click invariant，增加明确的可编辑区域 paste 路径，并让 Provider Test 把所有发现的模型写入 v4 route registry。

本调研还补充一个 parity 结论：当前 regression 文档不能单独代表“删除前 API Keys 全功能”。旧 API Keys 功能来自 `.kiro/specs/studio-api-keys-redesign/` 和 commit `33a4135` 添加的组件；commit `3717eee` 在 v4 registry frontend cutover 中删除了这些组件。因此后续实现必须额外跑一遍功能一致性清单。

v4 生产契约以 `.kiro/specs/llm-provider-intelligence-v2/design.md` 为准。`studio-api-keys-redesign` 仍可作为 UX 参考，但其中 v3 API 路径已经被 v4 registry supersede，不能直接照搬。PM 最新执行要求：先完整恢复删除前前端状态，再做 v4 API 接线。

## 证据：native double-click 回归

### 之前的修复

Commit `14f8e36 fix(studio): guard native double click behavior` 增加了三个重要部分：

- `apps/studio/frontend/src/hooks/useNativeDoubleClickGuard.ts`
  - capture-phase 的 `mousedown`、`dblclick` 和 `selectstart` guard；
  - 跳过可编辑目标：`input`、`textarea`、`select`、`[contenteditable]`、`[role="textbox"]`、Monaco 和 `data-allow-native-double-click`；
  - 只对非编辑 chrome `preventDefault`，不 `stopPropagation`。
- `apps/studio/frontend/tests/e2e/native-double-click.spec.ts`
  - 断言非编辑 Settings chrome 双击会被 default-prevent；
  - 断言可编辑 input 不会被 default-prevent；
  - 断言 heading 上的 `selectstart` 会被阻止，但 input 内允许。
- `apps/studio/tauri/src/lib.rs`
  - 调用 `enable_macos_default_menu(false)`；
  - 安装 `macos_menu_without_edit`；
  - 包含 App、File、View、Window 和 Help 菜单，但有意省略 native `Edit`。

关键历史信号在函数名和菜单内容里：这次修复是有意避开 native `Edit` submenu 的。

### 当前冲突

后来的 paste fix 把 Tauri macOS menu 改回带 Undo/Redo/Cut/Copy/Paste/Select All 的 native `Edit` submenu。这样聚焦 input 粘贴可用了，但用户反馈 API Keys 页面删除/重构后，旧的双击提示音回归又回来了。

当前 `docs/development/FRONTEND_UI_SPEC.md` 也写成了 custom app menu 必须包含 native `Edit` submenu。这个说法与 `14f8e36` 的证据冲突；实现必须在最终快捷键策略被证明后更新该 spec。

### 约束

实现不能简单二选一：

- 移除 native `Edit` 但不提供替代路径，很可能会破坏 API key input 的 `Cmd+V`。
- 保留 native `Edit` 很可能会在 Tauri/WebKit 里重新引入双击提示音路径。

需要的形态是：保留 double-click guard 和 no-native-Edit invariant，然后实现并测试一个面向聚焦可编辑区域的 paste shortcut 路径。候选方案按优先级如下：

1. 前端对 editable targets 做 `keydown` fallback：在用户手势期间读取剪贴板文本，通过 `setRangeText` 或 contenteditable selection APIs 插入，并 dispatch 正常 input event。
2. 如果 WebKit clipboard 访问不够，使用 Tauri 专用 paste command/shortcut bridge。
3. 只有在 Tauri/WebKit 实验证明 native menu 不再触发双击提示音路径时，才考虑 native menu；这与当前用户反馈相反，应视为高风险。

## 证据：Provider Test 只返回一个 model

### 当前后端路径

`apps/studio/backend/app/services/copilot_test.py` 定义了：

- `PingResult(latency_ms: int, model_seen: str | None = None)`
- `_ping_provider(...) -> PingResult`
- `_first_model_id(response) -> str | None`

当前 parser 读取 `data` 或 `models`，然后只返回第一个 item 的 `id` 或 `name`。它不返回列表。

`apps/studio/backend/app/routers/llm.py` 的 `test_endpoint()`：

- 加载一个 `ProviderEndpoint`；
- 调用 `_ping_provider(...)`；
- 只更新 endpoint 的 `status`、`last_test_at` 和 `last_test_message`；
- 当 `result.model_seen` 存在时，在 message 里写入 `Model seen: ...`；
- 不 upsert 任何 `ProviderRoute`。

### 当前前端投影

`apps/studio/frontend/src/api/llm.ts` 从 v4 registry 投影 API Keys state：

- `routesForEndpoint(registry, endpointId)` 按 `endpoint_id` 过滤 `provider_routes`；
- `endpointToCredential(...)` 从这些 routes 设置 `available_models`；
- `providerTestResponseFromEndpoint(...)` 也从 routes 设置 `available_models`，并从 `routes[0]` 设置 `model_seen`。

因此 UI 只能显示已经作为 routes 存在的模型。如果 endpoint 只有一个 route，即使 provider 返回更多模型，Test 也只显示一个。

### 既有 spec 意图

旧的 API Keys Round 3 spec 已经写过预期行为：

- `.kiro/specs/studio-api-keys-redesign/round3-design.md` 把 `GET /models` 描述为首选 Test 路径，并说明 HTTP 200 应同时完成鉴权和提取 `available_models`。
- 同一份 spec 要求解析 OpenAI 风格 `data[].id`，以及 Gemini 风格 `models[].name`，并去掉 `models/` 前缀。
- `.kiro/specs/studio-api-keys-redesign/round3-tasks.md` Task D2.2 说明 parser 输出应为 `list[ModelInfo]`。
- Task D2.3 说明 Provider Test response 仍返回 `available_models: ModelInfo[]`。

v4 registry cutover 改变了数据必须持久化的位置，但没有移除“收集列表”的需求。

### 现有可复用 route 逻辑

`apps/studio/backend/app/services/llm_credentials.py` 已经在 `_v3_payload_to_v4(...)` 中把 legacy v3 `available_models` 转为 v4 routes：

- `_legacy_models(provider)` 读取 `available_models` 或 `models`；
- `_route_slug(model_id)` 归一化 provider model id；
- `canonicalize_model(endpoint_id=..., provider_model_id=route_slug)` 计算 canonical id 和 display name；
- `normalize_route_capabilities(...)` 写 capability metadata；
- route id 使用 `f"{endpoint_id}:{route_slug}"`。

实现应该复用或抽取这套 route 生成行为，而不是在 router 里发明第二套 slug/canonicalization 路径。

## v4 接线矩阵与恢复策略

### API 路径映射

| 删除前 / round3 路径 | v4 现行或目标路径 | 恢复要求 |
|---|---|---|
| `GET /api/llm/credentials` | `GET /api/llm/registry` + `GET /api/llm/registry/endpoints/{endpoint_id}/secret` | API Keys 初始加载必须从 registry 投影 provider cards，并对 redacted secrets 做 secret hydration。 |
| `PUT /api/llm/credentials` | `PUT /api/llm/registry/endpoints` | 用户编辑 Provider Name / Base URL / API Key 时只 upsert endpoints，不写 Test outcome 字段。 |
| `POST /api/llm/providers/test` | `POST /api/llm/endpoints/{endpoint_id}/test` | Test 前先保存 endpoint 草稿；Test 后刷新/合并 registry routes。 |
| `POST /api/llm/providers/test-models` | 无 1:1 已实现接口；可设计批量 route 创建/probe，或先创建 `unverified_manual` route 后调用 `POST /api/llm/routes/{route_id}/probe` | Manual probing 不能停留在前端本地 state，必须最终写入 `provider_routes`。 |
| `GET /api/llm/providers/notable-models` | 当前前端 local fixture，或未来 import-draft/provider metadata API | 候选列表只能作为输入提示，不能当作已验证模型。 |
| Provider list field `available_models` | v4 `provider_routes` 按 `endpoint_id` 投影 | 刷新后模型列表必须由 routes 复现。 |

### 恢复策略

- 禁止整包 cherry-pick `33a4135` 的前端实现，因为它会带回 v3 credentials API 和旧数据模型。
- 推荐以 `33a4135` 的组件行为和测试为 UX 参考，在当前 worktree 的 `apps/studio/frontend/src/components/studio/api-keys/` 和 v4 `api/llm.ts` 上做适配。
- 行为目标是 Requirement 5 parity，不是与旧 commit 字节级一致。
- 建议执行前对比参考：
  ```bash
  git diff 33a4135..HEAD -- apps/studio/frontend/src/components/studio/api-keys/
  ```

### Manual model probing 的 v4 决策

当前 v4 只有 `POST /api/llm/routes/{route_id}/probe`，它要求 route 已存在；旧 `POST /providers/test-models` 已不适合作为目标接口。PM 默认拍板方案 B：

1. Phase 1 先完整恢复 Manual probing 的前端输入式 UI，不接后端新 API，用 fixture/mock 验证交互 parity。
2. Phase 2 由 endpoint Test / import-draft / provider metadata 先创建 route candidates，Manual panel 只对已有 route 调用 `routes/{route_id}/probe`。

这个方案不新增批量 route API，风险较低，贴近 `llm-provider-intelligence-v2` 的 route-first 模型。代价是：如果某个 model id 完全不在 route candidates 中，Manual panel 不能假装 probe 成功；需要提示用户先通过 endpoint Test / import draft 生成候选。若未来产品要求“输入任意 model id 后一键创建 route”，再另开方案 A。

无论哪个阶段，Manual panel 的 `onModelsUpdated` 只允许反映后端已持久化的 `provider_routes`，不能只更新 React 本地 state。

## 证据：删除前 API Keys 功能清单

### 历史删除点

`git log --name-status` 显示：

- commit `33a4135 feat(studio): API Keys round 3 — multi-SDK probe + 8-vendor matrix + LLM Roles spec (#82)` 新增了：
  - `apps/studio/frontend/src/components/studio/api-keys/AddProviderForm.tsx`
  - `ManualModelTestPanel.tsx`
  - `OfficialVendorSelect.tsx`
  - `ProviderCard.tsx`
  - `ProviderListSkeleton.tsx`
  - 对应 tests
- commit `3717eee feat(studio): cut over llm registry frontend` 删除了上述 API Keys 组件和 `settings/api-keys/ApiKeysTab.tsx`。

这说明“删掉的 API Keys”不是一个单点控件，而是一整套 provider 管理面板。恢复时只修 paste 和 `available_models` 不够。

### 旧 spec 已拍板能力

`.kiro/specs/studio-api-keys-redesign/requirements.md` 和 `round3-design.md` 明确过以下功能：

1. API Keys 页面支持 provider 级配置，而不是按模型 vendor 硬编码分组。
2. Round 3 又把 UI 收敛成 Official Providers 上半区 + Third-party Providers 下半区。
3. Official Providers 预渲染 Anthropic / OpenAI / Gemini / DeepSeek / Ark。
4. Third-party Providers 支持新增自定义 provider，字段为 Provider Name、Base URL、API Key。
5. API key input 永远 `type="text"`；mask 走 CSS/display layer；真实 draft/state 永远是 backend 返回的真值。
6. 保留浏览器密码管理器抑制属性，例如 `data-1p-ignore`、`data-lpignore`、`data-form-type="other"`、`name="provider-secret-{id}"`。
7. Test 按钮职责是鉴权 + 模型列表获取，不再承担 SDK protocol 表单选择。
8. Test 成功要持久化 `available_models`，失败要持久化 error code/message。
9. UI 展示 Available SDKs 和 Available Models chips。
10. 自动模型列表不可用时，Manual Model Probing 支持用户手动累加验证 model ids。
11. 删除 provider 需要 AlertDialog/确认流程。
12. Loading 使用 ProviderListSkeleton 或等价 skeleton。
13. Refresh 后 badge 和 `available_models` 必须从后端恢复。
14. LLM Roles 只用后端返回的 route id / DTO 做引用，不从前端字符串推导执行目标。

### 当前 regression 文档覆盖情况

已覆盖：

- Tauri/WebKit 双击提示音与 `Cmd+V` paste 共存。
- Official provider stale placeholder endpoint canonicalization。
- Provider Test 从单个 `model_seen` 升级为完整模型列表。
- Route upsert 必须使用 v3-to-v4 migration 相同 slug/canonicalization。
- 不覆盖用户手动 route metadata。
- 实现前必须加 failing tests 和手动 UI 验证。

原先没有写全、现在已补进 Requirement 5 的 parity 项：

- Official/Third-party 两区完整保留。
- Official 固定 provider 列表。
- Third-party add/edit/delete 功能。
- API key mask/show/copy/InputGroup 行内动作。
- Test button 状态、badge、error code、available SDK/model chips。
- Manual model probing 累加闭环。
- DeleteConfirmDialog。
- Refresh 持久化恢复。
- Loading skeleton。
- 窄视口布局约束。

## 当前实现差距表

| 差距 | 相关需求 | 当前状态 |
|---|---|---|
| `test_endpoint` 不写 routes | Req 2 | 只更新 endpoint `status` / `last_test_at` / `last_test_message`，message 中最多包含单个 `model_seen`。 |
| `_ping_provider` 只返回 `model_seen` | Req 2 | `_first_model_id` 只取第一个 `data[].id` 或 `models[].name`。 |
| `testProviderModels` 是本地 stub | Req 5.7, 5.9 | 只查 cached registry 里是否已有 route，不调用后端，也不创建 route。 |
| `onModelsUpdated` 仅更新本地 credentials | Req 5.7, 5.9 | 手动追加模型刷新后会丢，除非后端 routes 已经存在。 |
| API key hidden 时使用 `type="password"` | Req 5.3 | `ProviderCard.apiKeyInputType(false)` 返回 `"password"`，违反 round3 A1。 |
| Tauri native `Edit` menu 存在 | Req 1 | 与 commit `14f8e36` 的 `macos_menu_without_edit` 方案冲突，可能复现双击提示音。 |
| `available_sdks` 只有单 protocol | Req 5.6 | 当前从 `[endpoint.protocol]` 投影；这符合 v4 单 protocol，但不同于 round3 多 SDK 探测文案。 |
| `FRONTEND_UI_SPEC.md` 仍要求 native `Edit` submenu | Req 4.2 | 与 regression 证据冲突，完成修复时必须同步修订。 |
| 无 `design.md` / `tasks.md` | 全流程 | Baseline 阶段限制下还没有施工单；PM 解锁后必须补 v4 接线任务。 |

## 实现风险

1. 当 model id 已存在时，不要覆盖用户手动编辑过的 route display name 或 capabilities。
2. Test 时不要替换整个 endpoint route set；应 upsert 返回的 models，并保留 manual/probed routes，除非用户删除它们。
3. 不要把 synthetic fallback models 展示得像 provider 真实返回的一样。
4. 不要依赖前端本地 state 存 discovered models；refresh 必须能从后端持久化 routes 复现同一列表。
5. API key inputs 不要使用 `type="password"`；现有 API Keys redesign 要求 text input + CSS masking。
6. 不要通过重新引入 native `Edit` menu 来修 paste，除非 Tauri shell 验证能推翻当前回归。
7. 不要把 regression fix 当作 API Keys 全量恢复；执行前必须逐条过 Requirement 5 parity 清单。
8. 不要恢复旧 v3 API 路径；所有前端接线必须落到 v4 registry endpoint/route DTO。

## 实现解锁后的最小验证矩阵

### Backend

- Parser unit tests:
  - OpenAI/Anthropic `{"data": [{"id": "a"}, {"id": "b"}]}` 返回 `["a", "b"]`。
  - Gemini `{"models": [{"name": "models/gemini-2.5-pro"}, {"name": "gemini-2.5-flash"}]}` 返回 `["gemini-2.5-pro", "gemini-2.5-flash"]`。
  - invalid JSON、缺失 list、非 dict entries 和 duplicate ids 都被确定性处理。
- Router tests:
  - 成功的 endpoint Test 会 upsert 多个 `ProviderRoute` entries；
  - duplicate model ids 上 existing route metadata 会被保留；
  - invalid key 会让 endpoint 保持 failed，并且不新增 routes。

### Frontend

- API projection test:
  - 一个 endpoint 有两个 routes 的 registry，会在 API Keys state 里产出两个 `available_models` chips。
- ProviderCard test:
  - persisted models 从 route-backed provider state 渲染，不能被折叠成一个 model。
- Editable shortcut test:
  - 聚焦的 API key input 可以通过 `Cmd+V` fallback path 粘贴，且不会重复插入。
- API Keys parity tests:
  - Official Providers 渲染固定 provider cards。
  - Third-party Providers 支持新增、取消、删除确认。
  - show/hide/copy action 使用 InputGroup 行内按钮并可点击。
  - Manual Model Probing 通过 model extend + dedupe 后同时显示旧 model 和新增 model。
  - refresh 后保留 status badge、SDK/model chips 和手动追加模型。
- v4 接线测试:
  - `testProvider()` 先 upsert endpoint，再调用 `endpoints/{id}/test`，最后从 registry routes 投影 models。
  - Manual probing 后端持久化为 `provider_routes`，刷新后仍显示。
  - redacted secret 通过 `registry/endpoints/{id}/secret` hydration 回填 input value。

### Tauri / browser 手动检查

- 可行时通过 `cd apps/studio/tauri && cargo tauri dev` 启动。
- 在 API Keys 中检查：
  - 用 `Cmd+V` 粘贴到 API key input；
  - show/hide API key；
  - copy API key；
  - 点击 Test，覆盖成功路径和 invalid-key 路径；
  - 展开/收起 Manual model probing；
  - 新增、取消、删除第三方 provider；
  - refresh 后确认 key、status、SDK/model chips 仍在；
  - 双击非编辑 card/header chrome，确认没有提示音或菜单闪烁；
  - 检查窄视口没有横向溢出。
