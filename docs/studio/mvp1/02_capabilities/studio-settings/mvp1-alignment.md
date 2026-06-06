---
module: 02_capabilities/studio-settings
doc: mvp1-alignment
status: FROZEN（Settings UI/API 大体 live；6 态仍是旧 5 态/`needs_setup`，部分 ③b 内核逻辑还在 Studio 后端巨型路由中 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [settings-six-state-provider-health, model-group-role-materialization, node-properties-role-test, copilot-sdk-test-parity]
aligns_with: 01_workflows/00_settings-ux-spec.md（settings runtime base）
---

# studio-settings — MVP1 Alignment

> **Tier**: capability | **Owns**: `settings-six-state-provider-health` / `model-group-role-materialization` 的 Studio UI/消费切面 + `node-properties-role-test` 机制 + `copilot-sdk-test-parity` 配置切面 | **现状**: Settings UI/API 大体 live；6 态仍是旧 5 态/`needs_setup`，部分 ③b 内核逻辑还在 Studio 后端巨型路由中 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `settings` region · `gateway` · `llm-copilot-http-api` · `copilot-assist` · `i18n`

## 1. 定义
`studio-settings` owns the runtime configuration capability that makes predict, run, publish, and copilot usable: identity/path basics, provider credentials, model groups, abstract LLM roles, and Copilot route configuration.

Source workflow basis: `01_workflows/00_settings-ux-spec.md:340`, `01_workflows/00_settings-ux-spec.md:361`, `01_workflows/00_settings-ux-spec.md:395`, `01_workflows/00_settings-ux-spec.md:433`.

## 2. 数据流 / 机制（设计细节）
### F1. Settings Shell And Persistence

- 机制: Settings is an overlay tab shell with debounced saves and websocket-driven refresh.
- 决策: Settings is a runtime base, not part of the linear authoring/run journey.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:340` defines the four-layer model; `01_workflows/00_settings-ux-spec.md:497` records the Settings shell status.
- 测试: switching tabs preserves dirty state; external registry/role changes refresh without losing local edits.
- Status: live.
- 归属: capability `studio-settings`; region `settings`; platform `state-engine`.

### F2. API Keys And Provider Health

- 机制: Provider cards edit credential fields, test endpoints, fetch models, and project provider/model state into the UI.
- 决策: API Keys owns concrete provider reachability; LLM Roles consumes only routable model groups.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:361` assigns API Keys responsibilities; `01_workflows/00_settings-ux-spec.md:530` lists current API Keys drift.
- 测试: missing key/base URL, failed endpoint, cooling-down circuit, and successful model fetch map to the canonical visible state.
- Status: live but state model stale.
- 归属: capability `studio-settings`; region `settings`; platform `gateway`.

### F3. LLM Roles Materialization

- 机制: model groups become candidate routes; role cards define active route/fallback order; backend materializes executable bundles.
- 决策: run/predict reference settings-built bundles and do not store separate model config.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:395` assigns LLM Roles; `01_workflows/00_settings-ux-spec.md:163` says run pages reuse the same materializer.
- 测试: disabled/unusable routes are skipped or marked; active route validation blocks invalid saves.
- Status: mostly live.
- 归属: capability `studio-settings`; platform `gateway`; downstream `predict`, `run-execution`.

### F4. Copilot Role Configuration

- 机制: Copilot tab configures copilot-compatible routes and tests the real Copilot runtime path.
- 决策: Copilot settings are part of runtime config, but real chat behavior belongs to `copilot-assist`.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` assigns Copilot settings; `01_workflows/00_settings-ux-spec.md:241` records current mismatch between fake test and runtime.
- 测试: copilot route names keep their prefix boundary; role test uses the same SDK/session path as chat.
- Status: partial/stale.
- 归属: capability `studio-settings`; capability `copilot-assist`; region `settings`.

### F5. Canonical Six-state Projection

- 机制: provider/model/role status should project through the canonical six states used in settings copy and downstream gating.
- 决策: users need distinguish setup missing, historically ready, failed with reason, cooling-down, ready, and off cases.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:255` records the canonical state model and current draft gaps.
- 测试: each canonical state is reachable in fixtures; old `needs_setup` does not leak into new UI copy.
- Status: target-design.
- 归属: capability `studio-settings`; platform `gateway`; region `settings`.

### F6. Settings As Runtime Dependency

- 机制: predict/run/copilot/publish ask settings/gateway for resolved credentials, roles, or identity at action time.
- 决策: Settings is the base layer for these workflows but should not block the entire app shell.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:462` lists cross-cutting dependencies; `01_workflows/00_settings-ux-spec.md:609` records cross-cutting issues/gaps.
- 测试: compile/edit works when settings are incomplete; predict/run/copilot/publish show scoped setup errors.
- Status: partial live.
- 归属: `studio-settings`; downstream `predict`, `run-execution`, `copilot-assist`, `publish`.

## 3. 接口契约
- General: user identity and artifact/registry-adjacent settings consumed by publish.
- API Keys: provider credentials, endpoint config, model discovery, endpoint health.
- LLM Roles: graph-agent abstract role to model-group/fallback route mapping.
- Copilot: copilot_chat roles and SDK/session tests.
- Backend/API: `llm-copilot-http-api` exposes HTTP glue; gateway package owns reusable route/materializer logic.
- Region link: `settings`; platform link: `gateway`.

## 4. 设计决策基础（PM 原话）
- 六态最终标签(中/英,= i18n P1 首批词条):`ready`=就绪/Ready · `historical_ready`=曾连通/Previously connected · `untested`=未测试/Untested · `failed`=失败(带原因)/Failed · `cooling_down`=冷却中/Cooling down · `off`=已关闭/Off。`historical_ready` **直接显示**(非仅 tooltip)。
- Copilot SDK 测试 = **短 smoke,走真实路径**(建会话 + 发一条 + 收到流式即过),不做完整 session 创建探测。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| STUDIO_SETTINGS-1 | 六态 | 单元 `settings-six-state-provider-health`；**为什么**：6 态标准投影是 ③b gateway 内核，Studio 只渲染消费、不自定义状态 |
| STUDIO_SETTINGS-2 | materialize 边界 | 单元 `model-group-role-materialization`；**为什么**：materialize/model group/endpoint 标准化归 ③b 内核，Studio 只传角色意图 |
| STUDIO_SETTINGS-3 | Copilot test | 单元 `copilot-sdk-test-parity`（消费/配置面；owner=copilot-assist）；**为什么**：copilot role 测试须走真实 SDK 路径，与实际 chat 等价 |
| STUDIO_SETTINGS-4 | 设置不挡壳 | 单元 `shell-runtime-gate`（消费；owner=shell-layout）；**为什么**：Settings 中央 overlay 不卸载 copilot、不阻塞壳，边调边看 |

## 6. 测试关键点
1. 六态: baseline 现状为 前后端仍有 `needs_setup` 旧 5 态 ⚠️；目标为 ready/historical_ready/untested/failed/cooling_down/off 六态投影。
2. materialize 边界: baseline 现状为 `llm.py` 混 HTTP glue/probe/materialize/draft ⚠️；目标为 ③b graph-agent-gateway 负责公共内核，Studio 只做 UI/策略/适配。
3. Copilot test: baseline 现状为 探测路径与真实 chat 不等价 ⚠️；目标为 短 smoke 走真实 SDK session。
4. 设置不挡壳: baseline 现状为 Settings 不完整时仍可 edit/compile；目标为 predict/run/copilot/publish 显示局部 setup error。

## 7. 涉及 region / platform
`settings` region · `gateway` · `llm-copilot-http-api` · `copilot-assist` · `i18n`

## 8. gaps / 报警
- 🚨 六态: 前后端仍有 `needs_setup` 旧 5 态 ⚠️；目标 ready/historical_ready/untested/failed/cooling_down/off 六态投影。
- 🚨 materialize 边界: `llm.py` 混 HTTP glue/probe/materialize/draft ⚠️；目标 ③b graph-agent-gateway 负责公共内核，Studio 只做 UI/策略/适配。
- 🚨 Copilot test: 探测路径与真实 chat 不等价 ⚠️；目标 短 smoke 走真实 SDK session。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `settings` region · `gateway` · `llm-copilot-http-api` · `copilot-assist` · `i18n`
