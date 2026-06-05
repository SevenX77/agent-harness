# compile-lint MVP1 Alignment

## 定义

`compile-lint` owns real-time lint, manual compile, compile error display, and the Compile -> Predict -> Run stage gate.

Source workflow basis: `01_workflows/03_compile.md:7`, `01_workflows/03_compile.md:10`, `01_workflows/03_compile.md:26`.

## 接口契约

- Frontend lint sends changed markdown and receives pass/fail/error payload.
- Manual compile calls engine-backed compile and receives structured errors with file, line, field, severity, and message.
- Center action bar gates Predict on compile-pass and Run on predict-pass.
- Region links: `center-action-bar`, `canvas`, `properties`, `editor`, `input`.
- Platform link: `engine`.

## F1. Realtime Lint

- 机制: editor changes debounce, call lint, then publish status for the center action bar.
- 决策: real-time lint should mark context only, not flood the user with global panels while they are mid-edit.
- 原话/来源: `01_workflows/03_compile.md:13` defines the 800ms lint action; `01_workflows/03_compile.md:28` says real-time lint only marks context.
- 测试: incomplete edit marks checking/failed without toast or drawer; empty content returns idle.
- Status: live mechanism, presentation target-design.
- 归属: capability `compile-lint`; region `editor`, `center-action-bar`.

## F2. Manual Compile Drawer

- 机制: clicking Compile runs full compile and opens a drawer with all errors, copyable details, and no sidebar coverage.
- 决策: keep the Compile button; change it from bottom floating panel to drawer.
- 原话/来源: `01_workflows/03_compile.md:18` defines the drawer; `01_workflows/03_compile.md:35` records the PM quote to remove the floating card.
- 测试: drawer lists every error with file/line/field/message; copy works; drawer does not cover side panels.
- Status: target-design. Current bottom panel must be removed.
- 归属: capability `compile-lint`; region `center-action-bar`; component target `Drawer`.

## F3. Contextual Error Locations

- 机制: compile errors map to canvas node badge, Properties/input field tooltip, and Monaco inline marker.
- 决策: errors should appear where the user can fix them.
- 原话/来源: `01_workflows/03_compile.md:15`, `01_workflows/03_compile.md:16`, and `01_workflows/03_compile.md:17` list the three locations; `01_workflows/03_compile.md:34` keeps the PM wording.
- 测试: the same engine error appears at its node, its field, and its file line when those surfaces are visible.
- Status: target-design.
- 归属: regions `canvas`, `properties`, `input`, `editor`; platform `engine`.

## F4. Stage Gate

- 机制: compile-pass unlocks Predict; predict-pass unlocks Run.
- 决策: run must be blocked until both structure and predict flight have passed.
- 原话/来源: `01_workflows/03_compile.md:20` defines the gate; `01_workflows/04_run-and-verify.md:10` repeats the spine.
- 测试: failing compile disables Predict and Run; passing compile enables Predict; failing predict keeps Run disabled.
- Status: compile gate live; predict-pass missing.
- 归属: capability `compile-lint`; capabilities `predict`, `run-execution`; region `center-action-bar`.

## F5. Engine Error Contract

- 机制: engine returns structured compile errors; Studio should not invent separate validation rules when engine can own them.
- 决策: compile check content and error codes stay engine-owned.
- 原话/来源: `01_workflows/03_compile.md:22` lists engine checks; `01_workflows/03_compile.md:30` says do not create Studio-only compile codes.
- 测试: engine errors survive through API to UI without losing file/line/field/severity.
- Status: backend live; some location metadata may need engine expansion.
- 归属: platform `engine`; capability `compile-lint`.

## 已决(PM 2026-06-04)

- 编译 **warning 级不阻塞 Predict**(只 error 阻塞);warning 仅标记/提示,不挡试飞。
- 报错呈现 = 底部 drawer(只盖画布、一键复制 Copilot,自动弹;见 `center-action-bar`),标题/文案随实现定。
