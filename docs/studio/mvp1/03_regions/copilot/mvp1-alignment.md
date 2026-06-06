---
module: 03_regions/copilot
doc: mvp1-alignment
status: FROZEN（面板与 WS live；session 仍易丢，ThinkingBlock/@mention/analysis bar 未落，且 Workspace 传 outer `skillId` 有下钻风险 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [copilot-session-persistence, copilot-sdk-test-parity]
aligns_with: 01_workflows/04_run-and-verify.md（analysis bar）· 01_workflows/00_settings-ux-spec.md（copilot route）
---

# copilot — MVP1 Alignment

> **Tier**: region | **Owns**: `copilot-session-persistence` 的 UI/session 渲染切面；`copilot-sdk-test-parity` 的配置结果消费切面 | **现状**: 面板与 WS live；session 仍易丢，ThinkingBlock/@mention/analysis bar 未落，且 Workspace 传 outer `skillId` 有下钻风险 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `copilot-assist` · `studio-settings` · `settings` · `native-fs` · `golden-eval`

## 1. 定义
`copilot` owns the right-side assistant panel UI: message list, tool/diff rendering, route picker, composer, chat connection status, and contextual empty states.

Source workflow basis: `01_workflows/00_settings-ux-spec.md:433`, `01_workflows/04_run-and-verify.md:124`.

## 2. 数据流 / 机制（设计细节）
### F1. Chat Panel And Connection State

- 机制: show connection status, reconnect delay, messages, errors, and composer in the side panel.
- 决策: Copilot is a side assistant, not a blocking modal.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot configuration and runtime dependency.
- 测试: closed websocket disables send; reconnect updates status; switching skills resets messages/context.
- Status: live with skill prop risk.
- 归属: region `copilot`; capability `copilot-assist`.

### F2. View Context Sync

- 机制: selected node/edge/lint/view state posts to copilot context endpoint with compaction.
- 决策: chat should understand current screen without pasting huge payloads.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:462` lists cross-cutting settings/copilot dependencies.
- 测试: selecting node updates context; large context is summarized with fingerprint.
- Status: live.
- 归属: region `copilot`; capability `copilot-assist`.

### F3. Model Route Picker

- 机制: chat can choose from the configured copilot role fallback routes.
- 决策: route config comes from Settings; chat only consumes it.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot settings; `01_workflows/00_settings-ux-spec.md:395` assigns role mapping.
- 测试: changing route affects future messages; unavailable config shows scoped error.
- Status: live.
- 归属: region `copilot`; capability `studio-settings`.

### F4. Tool And Diff Rendering

- 机制: tool calls and edit diffs render inside assistant messages with expandable details.
- 决策: assistant actions need inspectable output, especially for code/doc edits.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` uses copilot-like output as the reference for trace folding; same pattern applies here.
- 测试: Read/Edit/Bash events show start/result; diff bubble only appears when diff text exists.
- Status: live.
- 归属: region `copilot`; capability `copilot-assist`.

### F5. Golden Design Entry

- 机制: trace/golden flows can open copilot chats for missing node golden design.
- 决策: golden creation 有 trace-local 入口 + **批量 = Copilot 分析 bar**(predict/run 后弹窗,sonner→弹窗),见 `copilot-assist` F7。
- 原话/来源: `01_workflows/04_run-and-verify.md:124` lists copilot golden creation; `01_workflows/04_run-and-verify.md:137` requires both entries.
- 测试: golden CTA starts a chat seeded with graph/node/output context.
- Status: target-design.
- 归属: region `copilot`; capability `golden-eval`.

## 3. 接口契约
- Inputs: current skill id, current view context, copilot role route data, websocket events.
- Outputs: user message, optional route override, attach/context selection requests.
- Capability links: `copilot-assist`, `studio-settings`, `golden-eval`, `debug-resume`.
- Platform link: `gateway`.

## 4. 设计决策基础（PM 原话）
- 砍掉旧 Attach file / Add context 占位按钮(上下文统一走 F4 @mention)。
- **composer 新增图片附加**:① 拖拽图片文件;② 粘贴剪贴板图片(= "截图后加载":系统截图到剪贴板再 ⌘V)。**可行性已核**:`claude_agent_sdk` 有 `ImageContent` 输入类型 + `query` 收 message dict(含图)+ Claude 多模态 → 收图 OK;拖拽/粘贴纯前端、无需新 Tauri 插件。
- **不做应用内截图按钮**:截图统一靠系统快捷键 + 粘贴(② 已覆盖)——Mac `⌘⌃⇧4` / Windows `Win+Shift+S` 都框选到剪贴板、跨平台都简单;应用内 capture 要写三套原生代码、不值。
- **文件格式**:仅支持 Claude 原生组——图片(PNG/JPEG/GIF/WebP,单张 ≤~5MB)/ PDF / 文本类(md/code/json/csv 当文本读);**不支持格式给清晰提示**(转 PDF/图片/文本)。**自动转格式不在 copilot 做**,归 DEF-012(引擎内置转换 tools)、技能图按需调。
- **前提**:copilot 角色须用 vision 模型(Claude 系);非 vision 模型给"不支持图片"降级提示。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| COPILOT-1 | session UI | 单元 `copilot-session-persistence`；**为什么**：退出再进对话一模一样，session 渲染基于持久化(D8) |
| COPILOT-2 | analysis bar | 单元 `copilot-session-persistence`；**为什么**：copilot 分析 bar 是 golden/诊断入口，挂在会话流里 |
| COPILOT-3 | 下钻 skillId | 单元 `copilot-session-persistence`；**为什么**：下钻子图时 copilot 用 currentSkillId、cwd 含子图 path，不丢上下文 |

## 6. 测试关键点
1. session UI: baseline 现状为 内存态 / skill 切换 reset 风险 ⚠️；目标为 顶部多 session tab 持久化并恢复。
2. analysis bar: baseline 现状为 旧 golden 入口/sonner 口径残留 ⚠️；目标为 predict/run 后输入框上方弹 analysis bar，确认后消失。
3. 下钻 skillId: baseline 现状为 Panel 收 outer `skillId`，非 `currentSkillId` ⚠️；目标为 子图下钻时 copilot 上下文与 currentSkillId 一致。

## 7. 涉及 region / platform
`copilot-assist` · `studio-settings` · `settings` · `native-fs` · `golden-eval`

## 8. gaps / 报警
- 🚨 session UI: 内存态 / skill 切换 reset 风险 ⚠️；目标 顶部多 session tab 持久化并恢复。
- 🚨 analysis bar: 旧 golden 入口/sonner 口径残留 ⚠️；目标 predict/run 后输入框上方弹 analysis bar，确认后消失。
- 🚨 下钻 skillId: Panel 收 outer `skillId`，非 `currentSkillId` ⚠️；目标 子图下钻时 copilot 上下文与 currentSkillId 一致。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `copilot-assist` · `studio-settings` · `settings` · `native-fs` · `golden-eval`
