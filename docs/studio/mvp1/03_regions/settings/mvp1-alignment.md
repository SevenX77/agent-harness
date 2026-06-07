---
module: 03_regions/settings
doc: mvp1-alignment
status: FROZEN（Settings shell live；前后端/界面仍有旧 `needs_setup` 与局部易失状态，Copilot tab 还有保存/role-key drift ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity, i18n-error-code-ui-copy]
aligns_with: 01_workflows/00_settings-ux-spec.md（settings UX）
---

# settings — MVP1 Alignment

> **Tier**: region | **Owns**: `settings-six-state-provider-health` / `model-group-role-materialization` 的 region UI + `copilot-sdk-test-parity` 测试按钮/状态 + i18n copy 消费 | **现状**: Settings shell live；前后端/界面仍有旧 `needs_setup` 与局部易失状态，Copilot tab 还有保存/role-key drift ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `studio-settings` · `gateway` · `llm-copilot-http-api` · `i18n`

## 1. 定义
`settings` owns the UI region for runtime configuration: General identity/path settings, API Keys provider setup, LLM Roles model routing, and Copilot role setup.

Source workflow basis: `01_workflows/00_settings-ux-spec.md:340`, `01_workflows/00_settings-ux-spec.md:361`, `01_workflows/00_settings-ux-spec.md:395`, `01_workflows/00_settings-ux-spec.md:433`.

## 2. 数据流 / 机制（设计细节）
### F1. Settings Shell

- 机制: tabbed settings surface with close action, error boundaries, and responsive layout.
- 决策: Settings is a runtime base, not a blocking first-run wizard.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:497` records Settings shell status.
- 测试: each tab loads independently; tab failure stays inside error boundary.
- Status: live.
- 归属: region `settings`; capability `studio-settings`.

### F2. General

- 机制: expose identity and app-level settings consumed by publish/runtime.
- 决策: General is the low-frequency identity/path base.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:517` records General settings.
- 测试: user id change is reflected in publish precondition; save error is visible.
- Status: partial/live.
- 归属: region `settings`; capability `publish`, `studio-settings`.

### F3. API Keys

- 机制: manage provider credentials, endpoint config, get-models, and endpoint tests.
- 决策: provider reachability lives here; downstream roles consume projected state.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:361` defines API Keys responsibilities; `01_workflows/00_settings-ux-spec.md:530` records drift.
- 测试: key/base URL/test/get-models flows cover success, missing setup, failed endpoint, cooling-down.
- Status: live with state model drift.
- 归属: region `settings`; platform `gateway`.

### F4. LLM Roles

- 机制: map graph-agent roles to model groups and fallback route chains.
- 决策: predict/run reuse Settings materializer; they do not own separate model routing config.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:395` defines LLM Roles; `01_workflows/00_settings-ux-spec.md:163` says run pages reuse the same materializer.
- 测试: active route validation blocks invalid saves; fallback order is persisted.
- Status: mostly live.
- 归属: region `settings`; platform `gateway`.

### F5. Copilot Settings

- 机制: configure copilot-compatible roles and run SDK/route tests.
- 决策: Settings configures routes; Copilot panel consumes them.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` defines Copilot responsibilities; `01_workflows/00_settings-ux-spec.md:587` records current drift.
- 测试: copilot role ids keep prefix; test path matches real chat runtime.
- Status: partial/stale.
- 归属: region `settings`; region `copilot`; capability `copilot-assist`.

### F6. Canonical State Projection

- 机制: provider/model/role statuses render from canonical six-state projection and reasons.
- 决策: visible state should explain setup, historical readiness, failures, cooldown, ready, and off.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:255` records the canonical state model.
- 测试: each state has UI fixture and copy; old `needs_setup` does not leak.
- Status: target-design.
- 归属: region `settings`; platform `gateway`.

## 3. 接口契约
- Inputs: credentials registry, model groups, roles data, app settings, save status/error.
- Outputs: provider field changes, endpoint tests, model fetches, role changes, copilot route tests.
- Capability link: `studio-settings`.
- Platform link: `gateway`; HTTP surface documented in `04_platform/llm-copilot-http-api/`.

## 4. 设计决策基础（PM 原话）
- 六态标签见 `studio-settings` 已决(就绪/曾连通/未测试/失败/冷却中/已关闭);`historical_ready` **直接显示**,非仅 tooltip。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| SETTINGS-1 | 六态 | 单元 `settings-six-state-provider-health`；**为什么**：UI/API 仍有 needs_setup 旧态，要渲染六态标签 + 错误 copy 一致 |
| SETTINGS-2 | role materialization UI | 单元 `model-group-role-materialization`；**为什么**：前端编辑角色/绑定，把角色结构交 ③b 物化 |
| SETTINGS-3 | Copilot settings | 单元 `copilot-sdk-test-parity`（消费/UI；owner=copilot-assist）；**为什么**：Copilot tab 测试按钮/状态走真实 SDK，现仍依赖 mock-copilot-data |

## 6. 测试关键点
1. 六态: baseline 现状为 UI/API 仍有 `needs_setup` 旧态 ⚠️；目标为 六态标签和错误 copy 一致。
2. role materialization UI: baseline 现状为 局部易失 routeStatus/role key 风险 ⚠️；目标为 显示来自 ③b/③a 单一投影，不本地猜真相。
3. Copilot settings: baseline 现状为 Copilot test/save 仍有路径差异 ⚠️；目标为 真实 SDK smoke 结果在 Copilot tab 可见。

## 7. 涉及 region / platform
`studio-settings` · `gateway` · `llm-copilot-http-api` · `i18n`

## 8. gaps / 报警
- 🚨 六态: UI/API 仍有 `needs_setup` 旧态 ⚠️；目标 六态标签和错误 copy 一致。
- 🚨 role materialization UI: 局部易失 routeStatus/role key 风险 ⚠️；目标 显示来自 ③b/③a 单一投影，不本地猜真相。
- 🚨 Copilot settings: Copilot test/save 仍有路径差异 ⚠️；目标 真实 SDK smoke 结果在 Copilot tab 可见。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `studio-settings` · `gateway` · `llm-copilot-http-api` · `i18n`
