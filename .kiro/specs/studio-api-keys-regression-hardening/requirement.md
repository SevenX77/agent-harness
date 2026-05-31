---
status: Implementing
created: 2026-05-25
owner: Studio
source_feedback: "API Keys 回归反馈：macOS 双击提示音复现；Provider Test 只显示一个 Anthropic model。"
related_code_paths:
  - apps/studio/tauri/src/lib.rs
  - apps/studio/frontend/src/hooks/useNativeDoubleClickGuard.ts
  - apps/studio/frontend/src/index.css
  - apps/studio/frontend/src/components/studio/api-keys/
  - apps/studio/frontend/src/api/llm.ts
  - apps/studio/backend/app/services/copilot_test.py
  - apps/studio/backend/app/routers/llm.py
  - apps/studio/backend/app/services/llm_credentials.py
linked_specs:
  - .kiro/specs/studio-api-keys-redesign/
  - .kiro/specs/llm-provider-intelligence-v2/
---

# Studio API Keys 回归加固需求

## 背景

本 spec 只收敛 2026-05-25 暴露的 API Keys 回归，不扩大为新的 LLM Provider 架构重做。目标是在继续动代码前锁定边界：macOS/Tauri 下非编辑区双击不能再触发系统提示音，同时 API key 输入框仍必须支持 `Cmd+V`；Provider Test 成功后必须展示并持久化 provider 返回的完整模型列表，而不是只显示一个历史 route 或单个 `model_seen`。

同时，本 spec 必须作为“删除后恢复 API Keys 页”的 parity gate 使用：修复回归时不能只修当前截图里的两个点，还要确认被 v4 registry frontend cutover 删除的 API Keys 功能没有继续缺失。

冲突优先级：`llm-provider-intelligence-v2` 是当前 v4 registry 生产契约；`studio-api-keys-redesign` 只作为删除前 API Keys UX/交互参考。旧文档里的 `/providers/test`、`/providers/test-models`、`/credentials` 等 v3 API 路径不得直接恢复为新实现的目标接口。

该 spec 已由 PM 解锁进入 Implementation 阶段。执行顺序强制为：先完整恢复删除前 API Keys 前端 UI/交互状态并用前端 fixture/mock 验证 parity，再执行 v4 API 接线和后端 route 持久化。

## 需求

### Requirement 1: macOS 双击保护与编辑快捷键必须同时成立
**目标：** 作为 Studio 桌面端用户，我希望非编辑区域双击保持安静，同时输入框等可编辑区域仍支持正常粘贴，这样 Settings 才像一个桌面应用，并且不会破坏 API key 输入。

#### 验收标准
1. 当用户在 Tauri/WebKit 里双击非编辑类 Settings 外壳、provider card、accordion header 或菜单附近 action surface 时，系统必须阻止会触发 macOS `Edit` 菜单闪烁或系统提示音的原生文本选择命令。
2. 当事件目标是 `input`、`textarea`、`[contenteditable]`、`[role="textbox"]`、Monaco，或标记了 `data-allow-native-double-click` 的元素时，全局 double-click guard 不得阻止原生编辑选择行为。
3. 当聚焦的 API key input、Base URL input、textarea、contenteditable 字段或 Monaco editor 在 macOS 上收到 `Cmd+V` 时，系统必须只粘贴一次剪贴板文本，并触发 React state 使用的正常 input/change 路径。
4. 如果原生 macOS `Edit` submenu 会重新引入双击提示音回归，实现必须避开该原生 submenu，并通过经过测试的 frontend/Tauri 快捷键路径提供粘贴能力。
5. 实现必须保留 commit `14f8e36` 引入的回归覆盖，并增加可编辑区域粘贴行为覆盖，防止两个约束被悄悄互相牺牲。

### Requirement 2: Provider Test must persist the full discovered model catalog
**目标：** 作为正在配置 LLM provider 的 Studio 用户，我希望 Test 能发现 provider 返回的所有模型，这样 API Keys 和 LLM Roles 展示真实 route 选项，而不是一个占位模型。

#### 验收标准
1. 当 provider models-list 请求成功并返回多个模型时，后端必须解析每一个受支持的 model id，并为被测试的 endpoint upsert route 记录。
2. 如果 provider 响应是 OpenAI/Anthropic 风格的 `data[].id`，parser 必须按响应顺序收集每一个字符串 `id`，并去掉完全重复项。
3. 如果 provider 响应是 Gemini 风格的 `models[].name`，parser 必须收集每一个字符串 `name`，去掉开头的 `models/` 前缀，并去掉完全重复项。
4. 当 Test 成功完成时，v4 registry 的下一次 refresh 必须暴露从该 endpoint 所有已持久化 routes 推导出的 `available_models`，不能只暴露 `model_seen` 或第一个 route。
5. 当 Test 发现某个 model id 已经有该 endpoint 对应 route 时，系统必须保留用户拥有的 route metadata 和 capability 字段；除非新的 probe 对同一个后端拥有字段提供了严格更新的 verified 值。
6. 当 Test 发现新模型时，生成的 route id 必须使用与 v3-to-v4 migration 相同的 slug/canonicalization 语义，保证 LLM Roles 可以引用稳定 route id。
7. 当模型列表不可用但鉴权仍可验证时，endpoint 可以变为 verified 并显示解释信息，但 UI 不得编造 placeholder model；Manual Model Probing 仍作为 fallback。
8. Provider Test 的前端接线必须使用 v4 数据流：先通过 `PUT /api/llm/registry/endpoints` 保存 endpoint 草稿，再调用 `POST /api/llm/endpoints/{endpoint_id}/test`，最后刷新或合并 `/api/llm/registry` 中的 `provider_routes`。
9. 后端 `POST /api/llm/endpoints/{endpoint_id}/test` 必须补齐 `llm-provider-intelligence-v2` 设计里的能力：更新 endpoint 状态，并从 model list 结果创建或更新 route candidates。

### Requirement 3: Official provider Test must not use stale placeholder endpoints
**目标：** 作为使用官方 provider 的 Studio 用户，我希望 Test 使用 canonical provider 默认值，这样历史 placeholder URL 不会造成假的 network error。

#### 验收标准
1. 测试官方 Anthropic provider 时，除非用户明确配置了 custom endpoint，请求必须使用 `https://api.anthropic.com` 和 `anthropic_compatible`。
2. 测试官方 OpenAI、Gemini 或 DeepSeek provider 时，除非用户明确配置了 custom endpoint，请求必须使用该 provider 的 canonical base URL 和 protocol。
3. 如果本地持久化状态包含历史 placeholder，例如 `api.anthropic.example`，Test 在发送后端请求前必须 canonicalize action payload。
4. Test 完成后，前端不得用较旧的后端响应覆盖用户当前正在编辑、尚未完成输入的字段。

### Requirement 4: 实现安全门
**目标：** 作为维护者，我希望这个回归通过 failing tests 和明确验证来修复，避免修一个症状时重新引入相邻回归。

#### 验收标准
1. 修改实现代码前，worker 必须先为 double-click/paste 共存路径和多模型 Provider Test 持久化写 failing tests。
2. 完成 Req 1 时，worker 必须同步修订 `docs/development/FRONTEND_UI_SPEC.md` 中当前与 `14f8e36` 冲突的 Tauri macOS `Edit` 菜单规则，明确最终已验证策略。
3. 后端验证必须包含 targeted parser/router tests，证明多个 provider models 会变成已持久化 routes。
4. 前端验证必须包含 API projection tests，证明 Test 后 `available_models` 会从该 endpoint 的所有 routes 渲染出来。
5. 手动验证必须在 app shell 或等价 local browser/Tauri 路径打开 API Keys，测试粘贴、show/hide/copy、Test 成功/错误状态、accordion 展开，以及窄视口。
6. 实现不得 revert 无关的 dirty worktree 变更。

### Requirement 5: 删除前 API Keys 功能一致性
**目标：** 作为 Studio 用户，我希望恢复后的 API Keys 页面与删除前已拍板的功能一致，这样不会在修复两个回归时丢掉旧页面已经交付过的 provider 管理能力。

#### 验收标准
1. API Keys 页面必须保留 Official Providers 和 Third-party Providers 两个物理分区；Official Providers 至少预渲染 Anthropic、OpenAI、Gemini、DeepSeek、Ark，Third-party Providers 支持用户新增自定义 provider。
2. Official provider card 必须隐藏 Provider Name 和 Base URL 编辑入口，使用 canonical 默认值和稳定 endpoint id，例如 `anthropic-official`、`openai-official`、`gemini-official`、`deepseek-official`、`ark-official`；Third-party provider form/card 必须支持用户编辑 Provider Name、Base URL 和 API Key。
3. API Key 输入框必须保持 `type="text"`，真实 value 与存储值同步；mask 只能是 CSS/display layer，不得污染 draft/state，也不得恢复 `Saved key retained` placeholder 行为。
4. API Key 输入框必须提供显示/隐藏和复制操作，并使用本地 `InputGroup` / `InputGroupButton` / `InputGroupAddon` 组织行内动作，避免绝对定位按钮覆盖 input。
5. Test 按钮必须在空 key 时 disabled，在测试中显示临时 testing 状态，完成后通过 v4 endpoint/route DTO 持久化状态 badge、`last_test_at`、`last_test_message`、`last_error_code` 和 `available_models`。
6. Test 成功必须展示 Available SDKs 和 Available Models chips；在 v4 registry 中 Available SDKs 默认展示 endpoint 的单个 `protocol`，除非另一个已批准设计重新引入多 SDK 探测。Test 失败必须展示后端返回的可诊断错误信息，不得把 stale network error 或旧 route 当作成功结果。
7. 当自动模型列表不可用时，Manual model probing 的前端 UI 必须完整恢复输入多个 model id、添加/删除行、loading、结果提示和去重展示；v4 API 接线阶段采用方案 B：只对后端已存在的 route candidates 调用 `POST /api/llm/routes/{route_id}/probe`，并把 probe 成功后的 routes 作为持久化来源。禁止只通过前端 `setCredentials` 或本地 cache 假装追加成功；若未来要求“未在 list 的 model 一键添加”，必须另开方案 A 的批量 route API 设计。
8. 删除第三方 provider 或 route 相关配置时必须有二次确认，使用本地 `DeleteConfirmDialog` 或同等已批准 shadcn/Radix wrapper，不得退回 `window.confirm`。
9. 页面刷新后，已保存 API key、status badge、Available SDKs、Available Models 和 Manual probing 追加结果必须从后端持久化数据恢复。
10. LLM Roles / Available Routes 只能消费后端 v4 registry 的 endpoint/route DTO；前端不得从 raw model string、display name 或 provider brand 自行推导 route ownership。
11. Loading 状态必须保留 skeleton 或等价稳定占位，避免 credentials 加载期间页面跳动或误显示为空。
12. 窄视口下 provider card、input action、badge、model chips 和 Manual probing 区域不得横向溢出或遮挡关键操作。
13. 恢复 API Keys UI 时不得整包 cherry-pick `33a4135` 前端实现；只能把它作为 UX/交互参考，在当前 v4 registry DTO 和当前 worktree 文件上做适配。
