# settings MVP1 Alignment

## 定义

`settings` owns the UI region for runtime configuration: General identity/path settings, API Keys provider setup, LLM Roles model routing, and Copilot role setup.

Source workflow basis: `01_workflows/00_settings-ux-spec.md:340`, `01_workflows/00_settings-ux-spec.md:361`, `01_workflows/00_settings-ux-spec.md:395`, `01_workflows/00_settings-ux-spec.md:433`.

## 接口契约

- Inputs: credentials registry, model groups, roles data, app settings, save status/error.
- Outputs: provider field changes, endpoint tests, model fetches, role changes, copilot route tests.
- Capability link: `studio-settings`.
- Platform link: `gateway`; HTTP surface documented in `04_platform/llm-copilot-http-api/`.

## F1. Settings Shell

- 机制: tabbed settings surface with close action, error boundaries, and responsive layout.
- 决策: Settings is a runtime base, not a blocking first-run wizard.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:497` records Settings shell status.
- 测试: each tab loads independently; tab failure stays inside error boundary.
- Status: live.
- 归属: region `settings`; capability `studio-settings`.

## F2. General

- 机制: expose identity and app-level settings consumed by publish/runtime.
- 决策: General is the low-frequency identity/path base.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:517` records General settings.
- 测试: user id change is reflected in publish precondition; save error is visible.
- Status: partial/live.
- 归属: region `settings`; capability `publish`, `studio-settings`.

## F3. API Keys

- 机制: manage provider credentials, endpoint config, get-models, and endpoint tests.
- 决策: provider reachability lives here; downstream roles consume projected state.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:361` defines API Keys responsibilities; `01_workflows/00_settings-ux-spec.md:530` records drift.
- 测试: key/base URL/test/get-models flows cover success, missing setup, failed endpoint, cooling-down.
- Status: live with state model drift.
- 归属: region `settings`; platform `gateway`.

## F4. LLM Roles

- 机制: map graph-agent roles to model groups and fallback route chains.
- 决策: predict/run reuse Settings materializer; they do not own separate model routing config.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:395` defines LLM Roles; `01_workflows/00_settings-ux-spec.md:163` says run pages reuse the same materializer.
- 测试: active route validation blocks invalid saves; fallback order is persisted.
- Status: mostly live.
- 归属: region `settings`; platform `gateway`.

## F5. Copilot Settings

- 机制: configure copilot-compatible roles and run SDK/route tests.
- 决策: Settings configures routes; Copilot panel consumes them.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` defines Copilot responsibilities; `01_workflows/00_settings-ux-spec.md:587` records current drift.
- 测试: copilot role ids keep prefix; test path matches real chat runtime.
- Status: partial/stale.
- 归属: region `settings`; region `copilot`; capability `copilot-assist`.

## F6. Canonical State Projection

- 机制: provider/model/role statuses render from canonical six-state projection and reasons.
- 决策: visible state should explain setup, historical readiness, failures, cooldown, ready, and off.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:255` records the canonical state model.
- 测试: each state has UI fixture and copy; old `needs_setup` does not leak.
- Status: target-design.
- 归属: region `settings`; platform `gateway`.

## 已决(PM 2026-06-04)

- 六态标签见 `studio-settings` 已决(就绪/曾连通/未测试/失败/冷却中/已关闭);`historical_ready` **直接显示**,非仅 tooltip。
