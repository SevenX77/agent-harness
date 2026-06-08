---
ws_id: WS-5-copilot-workbench
modules: [02_capabilities/copilot-assist, 03_regions/copilot, 04_platform/llm-copilot-http-api]
depends_on: [WS-0, WS-1]
blocks: []
owns_files:
  - apps/studio/frontend/src/components/copilot/
  - apps/studio/frontend/src/store/copilotStore.ts
  - apps/studio/frontend/src/hooks/useCopilot.ts
  - apps/studio/backend/app/services/copilot.py
  - apps/studio/backend/app/routers/copilot.py
  - apps/studio/backend/app/routers/llm.py
  - apps/studio/frontend/src/components/studio/settings/copilot/
spec_ssot:
  - docs/studio/mvp1/_impl/IMPL_PLAN.md §三/§六/§七
  - docs/studio/mvp1/01_workflows/00_settings-ux-spec.md §3
  - docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md
  - docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/studio-settings/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/settings/mvp1-alignment.md
  - docs/graph-agent-gateway/mvp1/01-handoff-interface/mvp1-alignment.md
  - docs/graph-agent-gateway/mvp1/02-orch-role-resolution/mvp1-alignment.md
  - docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md
  - docs/graph-agent-gateway/mvp1/09-inv-invocation-runtime/mvp1-alignment.md
  - docs/development/FRONTEND_UI_SPEC.md §2
status: ready-for-contract-gate
---

# WS-5 Copilot 工作台 — 需求书

本需求书是 WS-5 的契约输入。所有判断只以 Studio MVP1 和 gateway MVP1 设计文档为准；当前代码和旧测试只能作为 baseline / drift 证据。实现前必须先有 RED 测试、PM 契约门，并等待用户在聊天窗口明确确认；系统自动审批不算确认。

## 1. 目标(intent + why)

让 Copilot chat、session 持久化、Settings Copilot runtime 配置和 Copilot SDK Test 走同一条可信配置路径。用户看到的 Copilot role、available model group、route fallback、SDK readiness、chat runtime 和 test 结果必须来自后端 DTO / gateway route 解析 / 真实 `ClaudeSDKClient` 路径，而不是 mock 数据、前端名字猜测、静态徽章或与真实运行不同的 Anthropic probe。

本 WS 是旁路工作，但不是低风险 UI 修补。它要解决 Copilot “看起来能用但测试与真实调用不同、session 会丢、Settings 与 chat 各自维护事实”的问题，为后续真实 Copilot authoring 辅助和 WS-3/WS-6 运行后分析保留可信入口。

## 2. SSOT 指针(grounding,IR2/IR5)

- Copilot chat / session 权威：`docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md` 与 `docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md`。对应 `baseline.md` 只用于确认现状 gap，例如 ThinkingBlock 丢失、session 纯内存、安全写未做、model picker 只消费旧路径。
- Copilot Settings / SDK Test 权威：`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3、`docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md`、`studio-settings` 和 `settings` alignment。对应 `baseline.md` 记录 WS-4 后现状：六态和 Role Test 大体 live，但 Copilot tab 仍有保存/role-key drift，Copilot SDK test 仍是假路径。
- Gateway 外部契约权威：`docs/graph-agent-gateway/mvp1/01-handoff-interface/mvp1-alignment.md`、`02-orch-role-resolution/mvp1-alignment.md`、`08-orch-test-status-ssot/mvp1-alignment.md`、`09-inv-invocation-runtime/mvp1-alignment.md`。gateway route resolution / test status 当前按 floating-draft 消费；Studio 只消费 route handoff，不复制 ③b 内核。
- UI 规则权威：`docs/development/FRONTEND_UI_SPEC.md` §2，尤其 Copilot runtime 独立 Settings 页、`CatalogAccordion` / role card / route grid / `Select` / `SaveStatusBadge` / semantic token 规则。
- WS 分区权威：`docs/studio/mvp1/_impl/IMPL_PLAN.md`。当前 worktree 没有 `docs/studio/mvp1/DESIGN_UNITS_INDEX.md`；若旧 gate 或旧需求书提到 `DESIGN_UNITS_INDEX.md`，只能视为待修复的文档锚点，不得把不存在的文件当 SSOT。
- 实现前必读源码：frontmatter `owns_files` 中 Copilot UI、store、hook、backend copilot service/router、`llm.py` test-sdk 段和 Settings Copilot。行号必须执行时重新核实。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/backend/app/routers/llm.py` 与 WS-4 共享，必须按 `IMPL_PLAN.md` 排队：WS-5 只处理 Copilot SDK test parity、Copilot role target 展开和相关 DTO 投影，不改 API Keys、LLM Roles、model registry materialization 的公共逻辑。若发现 test parity 必须触碰 WS-4 正在占用的段，先登记 deferred 或请求文件锁释放。

`apps/studio/frontend/src/components/studio/settings/copilot/` 只处理 Copilot runtime 页，不扩散到 LLM Roles。`apps/studio/frontend/src/components/copilot/`、`store/copilotStore.ts`、`hooks/useCopilot.ts` 只处理 chat/session/event rendering，不接 Canvas authoring、run/golden/debug 或 safe write 全链路。

禁止触碰 Canvas、authoring panels、Tauri writer、run/golden/debug、gateway/engine packages。修改后端 Python 后必须重启 Studio App 或重新拉起 `cd apps/studio/tauri && cargo tauri dev` 再验。

## 4. 现状锚点(baseline)

当前 baseline 显示 Copilot 面板、websocket、文本流、工具气泡和 Settings Copilot tab 已存在，但关键事实仍漂移：session 纯内存，ThinkingBlock 未翻译，Settings Copilot 仍可残留 mock / 静态徽章，`copilot_` role key 可能被选组逻辑改坏，SDK Test 用 `AsyncAnthropic` 而真实 chat 用 `ClaudeSDKClient`，fallback 可能只取首条 route。WS-5 要用 RED 测试锁住这些 drift，不得因为旧测试或旧 UI 能过就保留。

如果现有测试断言 mock Copilot roles、静态 Backend Integration badge、裸 Anthropic probe 或丢失 session 属于正常，Codex 必须先把测试改成 MVP1 RED 断言并确认旧实现失败；不能为了旧测试维持 MVP0 行为。

## 5. 目标行为(可测的契约)

- Copilot session keyed by workspace identity、skill id 和 session id。一个 skill 支持多 session tab 与 new chat；切换 skill、回 Home、重开 Studio 后恢复 session 列表和上次活跃 tab，读写失败必须显式告警。
- Copilot chat 事件不丢结构：Text、ThinkingBlock、ToolUse、ToolResult、done/error 都按 SDK block 类型渲染；折叠只是视觉，不得摘要替代或吞机器码。
- Copilot Settings 不使用 mock 数据。available model group、route fallback、provider state、SDK readiness 和候选 filtering 来自后端 registry DTO / gateway route handoff；无真数据时展示空态或 skeleton。
- Copilot role 只能包含一个 model group，但该 group 内的 route fallback 链必须完整保留并可排序、删除、添加；执行目标保存精确 `route_id`，不得用 display name 或 provider model id 反推。
- `copilot_` role key 必须在新建、选组、保存、测试、chat runtime 中保持，不能被裸 model group id 覆盖，避免后端误分流到 graph-agent role。
- 默认浮出的 Claude / DeepSeek 内置候选必须来自 available models 的动态择优阶梯；没有目标 family 时不造假默认。未测试 route 仍可显示，不能因 SDK 能力未知就被前端预过滤。
- Copilot SDK Test 必须走真实 Copilot 调用等价路径：`ClaudeSDKClient`、per-session env、base_url / API key 注入、tool loop smoke。测试成功或失败写回可诊断证据；不再用 `AsyncAnthropic` 伪造 SDK readiness。
- Copilot runtime fallback 必须按 route 顺序尝试完整 fallback 链；单条 route 解析失败时继续下一条，全链失败才返回可诊断 error。
- Settings Copilot header 使用真实 save status，不再显示静态 Backend Integration 徽章。保存失败、route invalid、SDK test failed 都要有用户可见错误。
- UI 必须遵守 `FRONTEND_UI_SPEC.md` §2：本地 `components/ui` wrapper、`CatalogAccordion`、`Select`、`Button`、`Badge` / `Tag`、语义 token、响应式 route grid、Playwright 或浏览器点击验证和窄宽度检查。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，且 RED 要在旧实现上真实失败。最低覆盖如下：

1. Session persistence：创建两条 Copilot session、切 tab、发送消息、模拟刷新或重新 mount，断言 session 列表和活跃 tab 恢复；切换 workspace / skill 后不串台。
2. Session failure feedback：模拟 native writer read/write 失败，断言 UI 或 store 暴露显式错误，不静默丢聊天。
3. Event rendering：后端或 hook 输入 ThinkingBlock、ToolUse、ToolResult、error、done，断言消息渲染保留结构、可折叠展开且不丢机器码。
4. Settings no mock：无 registry / 无 compatible routes 时显示真实空态；有 registry DTO 时只从 DTO 生成 Copilot roles 和 candidates；不得读取 `mock-copilot-data` 或默认 mock roles。
5. `copilot_` role key：新建 role、选择 model group、保存、测试后 role id 仍带 `copilot_` 前缀，后端 `_is_copilot_role` 路径可识别。
6. Dynamic defaults：构造 available models，断言 Claude 优先 opus 4.8 后退 4.7，DeepSeek 优先 V4 Pro 后退 V3.2 Pro；缺 family 时不浮出假默认。
7. Candidate visibility：untested route 仍出现在 Copilot 可选模型中；不因前端名字猜测 SDK 兼容性而隐藏。
8. True SDK Test parity：测试端点使用真实 `ClaudeSDKClient` 等价路径和 env 注入；旧 `AsyncAnthropic` probe 路径必须被 RED 抓住。失败原因进入 DTO / toast / inline 状态。
9. Fallback chain：构造第一条 route 失败、第二条成功，断言 chat runtime 继续 fallback；全链失败返回 scoped error。
10. Save status：Settings Copilot 不再显示静态 Backend Integration badge，改为真实 idle / pending / saving / saved / failed 状态。
11. Backend restart validation：后端 Python 变更完成后重启 Studio App 或重新拉起 Tauri dev，并验证 Copilot WS 或 SDK test 端点加载的是新代码。
12. 真实 e2e：用 Playwright 或等价浏览器打开 Copilot 面板和 Settings Copilot，覆盖发送、切 session、空态、SDK test 成功/失败、保存失败或取消路径，并检查窄宽度无溢出。
13. No-fake 边界：不许 fake mock。测试不得通过 mock 掉 registry DTO、mock 掉 SDK test 成功、mock 掉 session writer 或隐藏 route fallback 来制造假绿；至少一条后端/前端集成路径要覆盖真实 DTO shape。

## 7. 硬依赖约束

WS-5 依赖 WS-1 writer 和 gateway route API。若 native session writer 未释放，session 持久化必须标为 blocked 或条件放行，不得落回 localStorage 假持久化。若 gateway route handoff / role resolution 的字段未 pinned，相关测试只能按 floating-draft DTO 写最小边界，不能在 Studio 中发明替代 runtime。

Copilot SDK Test 依赖 `claude-agent-sdk` 和 Studio sidecar vendor baseline。若干净 sidecar 无法 import `claude_agent_sdk` 或启动 `/health`，先停在 baseline 修复，不允许用跳过 SDK Test 代替。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后才允许实现，且最终 GREEN 不削弱断言。
- [ ] Copilot session 持久化、多 session tab、workspace / skill 隔离和失败告警通过测试。
- [ ] Copilot SDK Test 与真实 `ClaudeSDKClient` runtime 路径等价，不再靠 mock 或 `AsyncAnthropic` 宣称可用。
- [ ] Settings Copilot 消费真实 registry DTO，`copilot_` role key、single model group、route fallback 和 save status 均通过测试。
- [ ] Chat event rendering 保留 ThinkingBlock、tool call、tool result、error/done 结构。
- [ ] 后端 Python 改动后已重启 Studio App 或 Tauri dev，并记录验证结果。
- [ ] Playwright 或浏览器真实 e2e 覆盖 Copilot 面板、Settings Copilot、成功/失败/空态和窄宽度。
- [ ] MVP0 旧测试已审计；被改写、删除或保留的旧测试及理由已记录，且没有旧测试继续要求 mock、假 SDK test、静态徽章或内存 session 假成功。
- [ ] 没有修改 Canvas、authoring panels、run/golden/debug、Tauri writer、gateway/engine packages。

## 9. 不做(范围锁定,IR7)

不做 Copilot brain 场景，不做对话式建技能向导，不做 judge / 打磨 / commit-msg / run 后分析 bar，不接 Canvas authoring，不接 run/trace/golden/debug，不做安全写 + diff apply + Bash 审批全链路，不改 LLM Roles 核心编辑，不复制 gateway ③b 内核。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现后按真实代码状态回写 copilot-assist、copilot region、llm-copilot-http-api、settings / studio-settings 中与 Copilot 相关的 `baseline.md`。只能写已经实现并验证的现状；未做的 brain、safe write、wizard、analysis bar 等继续保留 target-design / deferred。

## 11. 评审检查点

PM 契约门重点审 RED 是否覆盖 session、真实 SDK parity、无 mock 数据、`copilot_` role key、fallback chain、save status 和 no-fake 边界。Codex 审查退出以 §8 为准。PM 终审检查 baseline 诚实、gateway 边界未复制、后端重启验证已记录。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws5-copilot-workbench.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、后端重启 Studio App、baseline 回写、Codex 审和 PM 终审。Gemini 只能把已批准 RED 实现到 GREEN；不得删改 RED、不得扩大到 WS-2/WS-3/WS-4/WS-6。
