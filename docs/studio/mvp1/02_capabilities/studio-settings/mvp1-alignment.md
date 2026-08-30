---
module: 02_capabilities/studio-settings
doc: mvp1-alignment
role: alignment
status: FROZEN（Settings UI/API 大体 live；API Keys 已消费 6 态投影与 catalog evidence_refs 蓝态；部分 ③b 内核逻辑仍在 Studio 后端适配壳中待边界收敛。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [settings-six-state-provider-health, model-group-role-materialization, node-properties-role-test, copilot-sdk-test-parity]
aligns_with: 01_workflows/00_settings-ux-spec.md（settings runtime base）
---

# studio-settings — MVP1 Alignment

> **Tier**: capability | **Owns**: `settings-six-state-provider-health` / `model-group-role-materialization` 的 Studio UI/消费切面 + `node-properties-role-test` 机制 + `copilot-sdk-test-parity` 配置切面 | **现状**: Settings UI/API 大体 live；API Keys 已消费 6 态投影与 catalog evidence_refs 蓝态；部分 ③b 内核逻辑还在 Studio 后端适配壳中待边界收敛。 | **Related**: [baseline](./baseline.md)（双向）· `settings` region · `gateway` · `llm-copilot-http-api` · `copilot-assist` · `i18n`

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
- Status: live.
- 归属: capability `studio-settings`; region `settings`; platform `gateway`.

### F2b. 一条路由的 Test 也要问它会不会用工具(2026-08-21,问题台账 L6)

- 机制: 用户对**某一条具名路由**按 Test(`POST /llm/routes/{route_id}/probe`),这条路由通过生成探测拿到 `verified` 之后,再被问一次工具问题——给它一个非用不可的工具和一个只有调工具才能回答的问题,读它回不回 tool call;回了就把工具结果喂回去,读它出不出得来(网关 `probing/tool_loop.py`,即探测阶梯的 T3)。看见它调了工具,就把 `tool_protocol` 记成 `probed_verified`。
- 决策(「这条路由能用吗」对 agent 阶段是另一个问题): 引擎每个 agent 循环都在绑工具、读 tool call(`call/chat_model.py::_dispatch`),所以一条通过了生成探测的路由**仍可能对 agent 完全无用**,而在此之前没有任何入口问过这件事。
- 决策(只挂在具名单条路由的 Test 上,**不挂**批量「测试模型」): T3 是阶梯最深的一级——每条路由两次真实请求,而 T1 只是一次 GET(决策文档 D1 的分级表)。挂在具名单条路由的 Test 上,代价被**用户自己那一次点击**框住;挂在批量路径上,它会被端点列出的模型数乘一遍。
- 决策(拒绝不写 `False`): 「没看到工具调用」有两个分不开的成因——协议根本没有工具,和模型选择用散文回答。写 `False` 会抹掉这条路由可能真有的能力,而**悄悄缩水的 capability 比没测过的更坏**(网关 `measured_tool_calling` 的原话与理由)。
- 决策(UI 要分得清「测出来的」和「文档说的」): 端点摘要里 `tool_protocol` 从此有三档——`verified`(被看见调过工具)/ `supported`(某份 catalog 或协议文档声称)/ `not_listed`。要把一个 agent 阶段交给哪个端点,靠的正是这个区别。端点级取**下界并集**,与 `methodIds` 同一条规则:一个模型被看见调过工具,是关于这个端点的事实,不因兄弟模型没测过而收回。
- 原话/来源: `docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md` D1 的 T3 行(「工具调用回不回来 / ReAct 闭环收不收敛」)与 D7 的 P5 开工补记。
- 测试: `apps/studio/backend/tests/routers/test_llm_tool_loop_probe.py` 四条(看见调工具→记成 probed_verified;只调没闭环→仍verify 协议、强弱写进 message;散文回答→不写;生成探测就失败→根本不问);`ProviderCard.test.tsx` 四条(measured 压过文档声称、端点级并集、三档文案各不相同)。
- Status: live。
- 归属: capability `studio-settings`; region `settings`; platform `gateway`。

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

- 机制: provider/model/role status projects through the canonical six states used in settings copy and downstream gating.
- 决策: users need distinguish untested/setup missing, historically ready, failed with reason, cooling-down, ready, and off cases.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:255` records the canonical state model and current draft gaps.
- 测试: each canonical state is reachable in fixtures; old `needs_setup` does not leak into new UI copy.
- Status: live for API Keys / registry projection; remaining work is module-boundary cleanup.
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
- 六态最终标签(中/英,= i18n P1 首批词条):`ready`=就绪/Ready · `historical_ready`=曾连通/Previously connected · `untested`=未测试/Untested · `failed`=失败(带原因)/Failed · `cooling_down`=冷却中/Cooling down · `off`=已关闭/Off。
  **修订记录(2026-08-29,用户批示)**:本行原句尾为「`historical_ready` **直接显示**(非仅 tooltip)」,被用户批示推翻:「模型标签后面没必要写"previously connected"蓝色框已经表示同样意思了」。现行口径:**模型/provider 标签(chip)上 `historical_ready` 与 `ready` 一样只以边框颜色表意**(蓝框=曾连通,绿框=就绪),文字标签留在 tooltip 与 aria-label(可访问性口径同 J-01.F 结案方式);**独立状态徽章**(ProviderStateBadge 这类以状态为主体的字段,非模型标签后缀)不在本修订范围,仍显示六态文字。
- Copilot SDK 测试 = **短 smoke,走真实路径**(建会话 + 发一条 + 收到流式即过),不做完整 session 创建探测。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| STUDIO_SETTINGS-1 | 六态 | 单元 `settings-six-state-provider-health`；**为什么**：6 态标准投影是 ③b gateway 内核，Studio 只渲染消费、不自定义状态 |
| STUDIO_SETTINGS-2 | materialize 边界 | 单元 `model-group-role-materialization`；**为什么**：materialize/model group/endpoint 标准化归 ③b 内核，Studio 只传角色意图 |
| STUDIO_SETTINGS-3 | Copilot test | 单元 `copilot-sdk-test-parity`（消费/配置面；owner=copilot-assist）；**为什么**：copilot role 测试须走真实 SDK 路径，与实际 chat 等价 |
| STUDIO_SETTINGS-4 | 设置不挡壳 | 单元 `shell-runtime-gate`（消费；owner=shell-layout）；**为什么**：Settings 中央 overlay 不卸载 copilot、不阻塞壳，边调边看 |
| STUDIO_SETTINGS-5 | 具名单条路由的 Test 连带问 T3(工具循环),批量测试模型不问 | F2b；**为什么**：引擎每个 agent 循环都绑工具，一条通过生成探测的路由仍可能对 agent 无用，而此前无人问过；T3 每条路由两次真实请求，挂在具名单条路由的一次点击上代价可控，挂在批量路径上会被模型数乘一遍。看不到工具调用时**不写 `False`**——那有两个分不开的成因，悄悄缩水的 capability 比没测过的更坏 |

## 6. 测试关键点
1. 六态: API Keys / registry 已消费 ready/historical_ready/untested/failed/cooling_down/off 六态投影；历史 `needs_setup` 不应再泄漏到新 UI copy。
2. materialize 边界: baseline 现状为 `llm.py` 混 HTTP glue/probe/materialize/draft ⚠️；目标为 ③b graph-agent-gateway 负责公共内核，Studio 只做 UI/策略/适配。
3. Copilot test: baseline 现状为 探测路径与真实 chat 不等价 ⚠️；目标为 短 smoke 走真实 SDK session。
4. 设置不挡壳: baseline 现状为 Settings 不完整时仍可 edit/compile；目标为 predict/run/copilot/publish 显示局部 setup error。

## 7. 涉及 region / platform
`settings` region · `gateway` · `llm-copilot-http-api` · `copilot-assist` · `i18n`

## 8. gaps / 报警
- 六态: API Keys / registry 六态投影已落地；继续关注其它 Settings 消费面是否仍有旧 `needs_setup` 文案或枚举残留。
- 🚨 materialize 边界: `llm.py` 混 HTTP glue/probe/materialize/draft ⚠️；目标 ③b graph-agent-gateway 负责公共内核，Studio 只做 UI/策略/适配。
- 🚨 Copilot test: 探测路径与真实 chat 不等价 ⚠️；目标 短 smoke 走真实 SDK session。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `settings` region · `gateway` · `llm-copilot-http-api` · `copilot-assist` · `i18n`
