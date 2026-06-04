# copilot MVP1 Alignment

## 定义

`copilot` owns the right-side assistant panel UI: message list, tool/diff rendering, route picker, composer, chat connection status, and contextual empty states.

Source workflow basis: `01_workflows/00_settings-ux-spec.md:433`, `01_workflows/04_run-and-verify.md:124`.

## 接口契约

- Inputs: current skill id, current view context, copilot role route data, websocket events.
- Outputs: user message, optional route override, attach/context selection requests.
- Capability links: `copilot-assist`, `studio-settings`, `golden-eval`, `debug-resume`.
- Platform link: `gateway`.

## F1. Chat Panel And Connection State

- 机制: show connection status, reconnect delay, messages, errors, and composer in the side panel.
- 决策: Copilot is a side assistant, not a blocking modal.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot configuration and runtime dependency.
- 测试: closed websocket disables send; reconnect updates status; switching skills resets messages/context.
- Status: live with skill prop risk.
- 归属: region `copilot`; capability `copilot-assist`.

## F2. View Context Sync

- 机制: selected node/edge/lint/view state posts to copilot context endpoint with compaction.
- 决策: chat should understand current screen without pasting huge payloads.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:462` lists cross-cutting settings/copilot dependencies.
- 测试: selecting node updates context; large context is summarized with fingerprint.
- Status: live.
- 归属: region `copilot`; capability `copilot-assist`.

## F3. Model Route Picker

- 机制: chat can choose from the configured copilot role fallback routes.
- 决策: route config comes from Settings; chat only consumes it.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot settings; `01_workflows/00_settings-ux-spec.md:395` assigns role mapping.
- 测试: changing route affects future messages; unavailable config shows scoped error.
- Status: live.
- 归属: region `copilot`; capability `studio-settings`.

## F4. Tool And Diff Rendering

- 机制: tool calls and edit diffs render inside assistant messages with expandable details.
- 决策: assistant actions need inspectable output, especially for code/doc edits.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` uses copilot-like output as the reference for trace folding; same pattern applies here.
- 测试: Read/Edit/Bash events show start/result; diff bubble only appears when diff text exists.
- Status: live.
- 归属: region `copilot`; capability `copilot-assist`.

## F5. Golden Design Entry

- 机制: trace/golden flows can open copilot chats for missing node golden design.
- 决策: golden creation has trace-local and batch copilot entries.
- 原话/来源: `01_workflows/04_run-and-verify.md:124` lists copilot golden creation; `01_workflows/04_run-and-verify.md:137` requires both entries.
- 测试: golden CTA starts a chat seeded with graph/node/output context.
- Status: target-design.
- 归属: region `copilot`; capability `golden-eval`.

## 待 PM 补 gap

- Exact behavior for Attach file and Add context buttons.
