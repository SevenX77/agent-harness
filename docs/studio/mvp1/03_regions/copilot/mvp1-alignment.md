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

### F3. Role & Route Picker（composer 与 Settings 同源）

- 机制: composer 的 role 下拉与 Settings Copilot tab 的角色卡**同一份派生真相**(`deriveCopilotDisplayRoles`,吃 `GET /api/llm/roles` + registry `model_groups`),route 下拉(model_override)从**选中显示角色的 `fallback_chain`** 派生、可用性用 registry `provider_routes` 投影。**不得**把 `GET /api/llm/registry` 的 roles 物化投影当第二份 role 真相读。
- 约束(同步契约,2026-07-01 PM 决策"copilot role 和 settings 页 roles 不同步"是缺陷):
  1. composer 只列**已绑定 model group**(fallback_chain 非空)的 copilot 角色;Settings 里的空草稿卡(未选组的 `copilot_custom_N`)不出现在 composer——它还不是可用角色。
  2. 无任何持久化 copilot 角色时,Settings 浮出的内置默认(atom-56 语义,rendered-not-persisted)**同样出现在 composer**;首次用它发消息 = "动了" → 前端先按 Settings 同一物化路径(`buildCopilotRoleEntry` + `copilot_<slug>` key,PUT /api/llm/roles)落库,再以持久化 key 发送。
  3. 默认选中 = 派生列表第一项;**删除前端写死的 `copilot_chat` 默认常量**(旧路径,不向后兼容);后端 ws 契约里 `role` 缺省仍按约定名解析,但面板一律显式传 role。
  4. `roles_changed` / `registry_changed` 事件驱动刷新,Settings 改完 composer 实时跟上。
- 决策: route/role config comes from Settings; chat only consumes it — consuming 的派生函数也必须同一份,不许面板自养第二套判定。
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot settings; `01_workflows/00_settings-ux-spec.md:395` assigns role mapping; 浮出/物化语义见 settings copilot 设计 atom-55/56(`docs/studio/mvp1/_impl/frontend-handbook/tpl-copilot-design.json` 派生视图,源头 `00_settings-ux-spec.md` §3.2)。
- 测试: composer 选项集合 == Settings displayRoles(配置完成子集);空草稿不出现;浮出角色首发消息触发物化并用持久化 key;changing route affects future messages; unavailable config shows scoped error; Settings 增删/换组后 composer 经事件刷新对齐。
- Status: live(2026-07-01 收敛落地:面板 registry.roles 第二真相 / 浮出角色被滤 / 空草稿可选 / copilot_chat 写死默认均已删,composer 与 Settings 同源)。
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

### F6. Message Scrolling & Composer（2026-07-01 新增）

- 机制: 消息区滚动遵循 shadcn radix **message-scroller** 交互契约(`https://ui.shadcn.com/docs/components/radix/message-scroller`):流式回复时贴底自动跟随(live edge);用户上滚离开底部即释放跟随、绝不抢滚;露出「回到底部」按钮;新一轮用户消息锚定在视口顶部附近(turn anchoring);布局变化(markdown 展开/图加载)保持阅读位置。落地为 `src/components/ui/message-scroller.tsx` 的 shadcn 风格封装(缺原语先补 ui/ 再用,FRONTEND_UI_SPEC §2.1),面板消息区不再用裸 `overflow-y-auto` 承担主滚动(§2.6)。
- Composer:
  1. 输入框默认可视高度 **≈3 行**(单行太小,PM 2026-07-01),随内容自增到上限(~160px)后内部滚动。
  2. 操作行固定在**输入框下方**(Claude Code 式布局,PM 2026-07-01 "功能在输入框下方,更加清晰"):左侧 route 选择 + role 选择,右侧发送按钮。
  3. **不渲染 Attach file / Add context 占位按钮**(本文件 §4 已决:上下文统一走 @mention;图片走拖拽/粘贴)。占位死按钮当场删,不留。
  4. Enter 发送、Shift+Enter 换行;IME 组合输入(`isComposing`)期间 Enter 不发送。
- 决策: 聊天区的滚动/输入行为向官方 message-scroller 契约看齐,不自造第二套滚动启发式。
- 原话/来源: PM 2026-07-01(本轮任务原话):「参考这个官方组件 ui,优化现在的 copilot 面板」「下方的输入窗口默认只有一行有点太小了」「我比较喜欢 Claude code 的布局方式,功能在输入框下方」。
- 测试: 流式输出时列表贴底;上滚后新增内容不抢滚、出现回底按钮;点击回底恢复跟随;composer 默认高度≈3 行;Enter 发送/Shift+Enter 换行/IME 不误发;占位按钮不存在。
- Status: live(2026-07-01 落地:ui/message-scroller.tsx 封装 @shadcn/react primitive,composer 三行 + Enter/Shift+Enter/IME 语义,占位按钮已删)。
- 归属: region `copilot`; capability `copilot-assist`.

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
| COPILOT-4 | message-scroller + composer(F6) | PM 2026-07-01；**为什么**：流式聊天贴底/释放/回底与三行 composer 是基础可用性，向 shadcn 官方契约看齐、不自造滚动启发式 |
| COPILOT-5 | role/route 同源(F3) | PM 2026-07-01「role 不同步」；**为什么**：composer 与 Settings 必须同一份派生真相 + 同一物化路径，否则两处各自为政必然漂移 |

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
