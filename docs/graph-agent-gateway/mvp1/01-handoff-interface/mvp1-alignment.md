---
module: 01-handoff-interface
doc: mvp1-alignment
status: drafted
verified_at: 2026-06-02
---

# 01-handoff-interface — MVP1 Alignment(目标设计)

> **Tier**：③b gateway 公共能力(`ResolvedRoute/ResolvedRole` 契约 + 两级对外接口都在/应在 gateway 包；Copilot WS 事件 DTO 是 ③a 消费方引用，非泄漏)
> **Owns**：定义编排↔调用的唯一交接物 `ResolvedRoute/ResolvedRole` 契约，并把「role→route」暴露为两级对外公共 API(role 级已有、route 级待补)；**不调模型**
> **Status**：设计定稿(2026-06 判据第四轮 + D3 两级 API 钉死)；代码 = route 级直调 public API 待新增、`ModelResolverProtocol` 待补 route-first 返回、`__init__` 待导出 route handoff 类型
> **Related**：[[02-orch-role-resolution]](resolve_role/materialize 产出本契约)· [[04-orch-registry-schema]](`ResolvedRoute/ResolvedRole` 字段权威源)· [[09-inv-invocation-runtime]](调用层消费本契约)· [[10-inv-route-chat-model-factory]](`ResolvedRoute`→ChatX)· [[12-inv-copilot-invocation]](route 级消费方，已并入本模块)
> **决策日志**：`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md` D2 + D3 + `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`(01 = ③b 公共，**补 route 级直调 public API**)
> **现状**：见同目录 `baseline.md`

> 本文按 A' 决策记录写目标：保留 `GatewayChatModel`(用途:把 `ResolvedRole` 包成 LangChain chat model 并在内部跑 fallback/熔断/probe/usage 的编排外壳)编排外壳，但把 `ResolvedRoute/ResolvedRole` 升级为编排和调用的唯一交接物。代码事实仍以当前源码行号为准，不把目标当成已实现。

## 1. 定义

MVP1 目标：让 **route(`ResolvedRoute`/`ResolvedRole`)成为编排层和调用层之间唯一的交接物**，并把「role→route 解析」做成 gateway 的**两级对外公共 API**——任何调模型的 app 装上 gateway 都能用，与具体应用无关，因此整块归 **③b 公共**。

按 D3「gateway = 可复用服务，对外 API 一等公民」，对外接口分两级：
- **① role 级**(已有)：app 给一个 role name，gateway 解析 → 返回包好的 `BaseChatModel`(`GatewayChatModel`)，并自动按 fallback 链一路调到底。入口 = `ModelResolver.resolve`(用途:把 role/model override 解析成可直接 `.invoke` 的 LangChain chat model)。
- **② route 级**(待补，本轮**反转升级为已定 ③b 新增要求**)：app 直接给一条 route(或一个 role name)，gateway **只返回解析好的 `ResolvedRole`/`ResolvedRoute`，不替 app 调**——不需要编排外壳、要自己用别的 SDK 跑的 app(如 Copilot 走 `claude_agent_sdk`)用这级。

本文只写文档目标，不改代码。

## 2. 数据流 / 机制(目标；现状逐步见 `baseline.md`)

**上下游**：① 调用方(Graph Agent phase / Copilot service / 未来其他 app)给 role name(+可选 override)→ **gateway 编排(`resolve_role`，③b)** → `ResolvedRole`(有序 `ResolvedRoute` + runtime policy)→〔role 级:gateway 包成 `GatewayChatModel` 自己一路调 ｜ route 级:直接把 route 交回调用方，调用方自己用 ChatX/SDK 跑〕。

**交接边界铁律**：route 是唯一交接物。调用层**不得**重新按 provider/model 猜测或动态选择别的 route；MVP0 alignment 明确禁止 capability/price/latency/availability 搜索替代 route，见 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:118`。

**目标设计与流程**(逐步)：

`ResolvedRoute`(用途:描述「一条 route 怎么调」的调用层输入契约，含 endpoint/protocol/credential/provider model/runtime settings 和诊断字段)字段定义位于 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415`。

`ResolvedRole`(用途:描述「一个 role 的有序 route 链和运行策略」的编排层输出契约)字段定义位于 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448`。

`ModelResolverProtocol`(用途:Engine 侧依赖注入用的 resolver 协议，定义解析入口签名)是 Engine 依赖的 resolver 协议：当前返回 `BaseChatModel`，目标应新增 route-first 能力，同时保留 model 返回兼容已有 LangChain 调用路径，见 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:24`。

1. 编排输入：调用方传 `role_name` 和可选 override。当前协议字段是 `role_name` 与 `model_override`，见 `protocol.py:30` 和 `protocol.py:33`；MVP1 语义应明确 override 是 route override，或更名为 route override。
2. 编排解析：resolver 调用 registry `resolve_role()`(用途:把一个 role 展开成有序 `ResolvedRoute` 链，逐条 join route/endpoint/credential/profile/runtime settings，不调模型)，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33`、`registry/resolver.py:55`、`registry/resolver.py:77`。
3. 编排输出：resolver 返回 `ResolvedRole`，其中 `routes` 是 fallback 顺序，`runtime_policy` 是探活/熔断/截断升级策略，见 `registry/schema.py:455` 和 `registry/schema.py:456`。
4. Graph Agent 调用消费(role 级)：Graph Agent 仍可以拿 `GatewayChatModel`，但该 model 内部只应把 `ResolvedRoute` 交给调用层工厂/ChatX，不再自研消息转换，决策记录指出 A' 改 `_generate`(用途:`GatewayChatModel` 的 fallback 执行循环，遍历 routes 做 probe/dispatch/usage/event)的消息准备、dispatch、结果构建三步，见 `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:83`。
5. Copilot 调用消费(route 级)：Studio Copilot 应拿同一份 `ResolvedRoute`，再由 `claude_agent_sdk` 自己调用；当前 `stream_query`(用途:Copilot WebSocket 业务入口，解析 route 后用 Claude SDK 调)已有这个方向，但 helper 在 service 内部，没走对外 public API，见 `apps/studio/backend/app/services/copilot.py:210` 和 `copilot.py:419`。
6. 交接边界：route 是唯一交接物，调用层不得重新按 provider/model 猜测或动态选择。MVP0 alignment 明确禁止 capability/price/latency/availability 搜索替代 route，见 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:118`。

### route 契约目标

1. 身份字段：`route_id`、`endpoint_id`、`provider_model_id`、`canonical_id` 是 route 诊断和调用身份，当前字段在 `registry/schema.py:421`、`registry/schema.py:422`、`registry/schema.py:430`、`registry/schema.py:431`。
2. 调用字段：`protocol`、`base_url`、`credential_ref`、`timeout_seconds`、`trust_env`、`proxy_env` 是 provider 调用需要的最小环境，当前字段在 `registry/schema.py:423` 到 `registry/schema.py:429`。
3. 安全字段：`credential_fingerprint` 是 cache/diagnostics 用的非明文密钥标识，当前字段在 `registry/schema.py:426`，构造来源在 `registry/resolver.py:85`。
4. provider profile 字段：`selected_profile_id`、`call_method_id`、`request_mapper_id` 让调用层按 profile 做 init-kwargs 或 mapper 选择，当前字段在 `registry/schema.py:432` 到 `registry/schema.py:435`。
5. runtime 字段：`runtime_settings` 和 `effective_runtime_settings` 分别保存用户意图和 resolver 合成值，当前字段在 `registry/schema.py:437` 和 `registry/schema.py:438`；provider matrix 说明 effective 值会进入 response metadata 和 fallback events，见 `docs/graph-agent-gateway/mvp0/provider-runtime-settings-matrix.md:42`。

## 3. 接口契约

> 本模块是 handoff 契约的钉死处。`ResolvedRoute/ResolvedRole` 字段权威源在 [[04-orch-registry-schema]](`registry/schema.py`)，本表**只链接不复制字段清单**，防 drift；本表只钉「跨边界的方向 + 签名 + 错误 + 归属 + 稳定性」。

| 边界 | 契约 |
|---|---|
| **编排 → 调用(唯一交接物)** | `ResolvedRole`{ `routes`: `ResolvedRoute[]`(有序 fallback 候选), `system_prompt_prefix`, `runtime_policy`(探活/熔断/截断升级), `lint_results`, `source_profile_*` }。字段权威源 `registry/schema.py:415-459`。调用层只消费此结构，**不得**回读 Studio DTO、不得按 provider/model 另选 route。 |
| **① role 级对外 API(③b 公共，已有)** | `ModelResolver.resolve(role_name, *, thinking_enabled, model_override, callbacks, phase_name, predict_context) → BaseChatModel`。协议 = `ModelResolverProtocol.resolve`(`protocol.py:24-39`)。返回值是包好的 `GatewayChatModel`/`PredictGatewayChatModel`，gateway 自动按 fallback 链调到底。`model_override` 当前实为精确 `route_override`(`registry/resolver.py:45`)。 |
| **② route 级对外 API(③b 公共，待补 — 本轮反转升级为已定要求)** | `resolve_routes(role_name, model_override) → ResolvedRole`(签名由本模块钉死，[[02-orch-role-resolution]] 落实)。**只返回解析好的 route，不替 app 调**。给「不要编排外壳、自己用别的 SDK 跑」的 app 用(Copilot)。当前 Copilot 绕过 class 直接 import pure `resolve_role`(`copilot.py:419-437`)，应改走此 API。 |
| **③a 消费方 → Copilot WS(③a 应用，非 ③b 泄漏)** | `CopilotWsRequestPayload`(用途:Copilot WS 请求体，只含 `user_message` + `model_override`)/ `CopilotEvent*`(用途:Copilot WS 输出事件联合，表达 text/tool/done/error)位于 `apps/studio/backend/app/models/copilot.py:21`、`:63`。这是 **Studio copilot 应用自己的 WS 事件契约**，gateway 感知不到——它**引用** route(经 route 级 API 取得)，但不是 gateway 公共 handoff 契约的一部分。**不算领域泄漏**(③a 拿 ③b 的 route 自己用，符合判据)。 |
| **错误** | role 不存在 / 过滤后空链 → `RegistryResolutionError`(配置错误)→ `ModelResolver.resolve` 统一映射 `GatewayRoleNotConfiguredError`；resolver 依赖缺失 → `GatewayResolverMissingError`(`llm_phase_node.py:133`)。 |
| **归属 / 稳定性** | `ResolvedRoute`/`ResolvedRole` 字段权威源 = [[04-orch-registry-schema]]；本模块**只链接不复制**。两级 API 签名稳定性由本模块维护(D3 要求「API 怎么提供要写清楚」)。 |

## 4. 设计决策基础(用户原话)

> **判据(本模块「route 级直调 API 归 ③b」依据)**："换个 app 还原样能用吗?能=③b,不能=③a。"(`module-disposition-revised.md:15`、ux-spec §6.0) → 「给 app 解析好 route 让它自己调」是任何调模型 app 的通用需求(不绑死 UI/产品策略/调用方式/存储)→ **③b 公共**。Copilot WS 事件是 Studio 自己怎么把 route 用出去(绑死 copilot 语义 + Claude SDK 调用方式)→ ③a 应用，但它**引用** route ≠ 泄漏。

> **D2 编排/调用分离 + copilot 用例**(决策记录 `:62-63`)："你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了, 这是调copilot的路径,你只负责输出编排结果, 不负责调用. 所以这里还引申出一个问题, 编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么"

> **D3 gateway = 可复用服务 / API 一等公民 / 两级 API**(决策记录 `:78-80`)："前端不归gateway管, 前端是studio的前端, gateway只管提供服务, 所以模块功能分个清楚, API怎么提供要写清楚, 要考虑复用其他app" —— 直接支撑「route 级直调 API 升级为已定 ③b 公共 API」。

> **§0 #3 copilot 取 route 自己调**(ux-spec `:17`)："copilot和llm roles类似, 只是copilot的role 只能填一个 model group, 并且测试走 copilot 自己的调用, 测试和真实调用没什么区别" —— copilot 拿 route、用自己的 SDK 调(③a 调用方式)，gateway 只给 route(③b)。

> **A' 保留编排外壳**(决策记录 `:40`)："不用留A, 这是错误判断, 正确的是A'。" → 保留 `GatewayChatModel`，fallback/probe/熔断/usage/metadata 留编排外壳，**不**裸返回 ChatX。

## 5. 决策 + 动机

1. **route 级直调 public API = 已定 ③b 新增要求(本轮反转)**：原 baseline/alignment 把它记为「待主控确认 handoff API 形状」；按 D3 + 判据，「给 app 解析好 route 让它自己调」是 gateway 必须提供的公共服务，**反转升级为已定 ③b 新增要求**——两级接口都钉死(role 级已有、route 级待补)。被否的旧表述：「route 形状待主控拍板」。
2. **A' 否决「resolver 直接产 ChatX + 删 `GatewayChatModel`」**：`GatewayChatModel` 保留编排职责，避免丢失 fallback/probe/熔断/usage/metadata，见 `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:22` 和 `client-layer-decision-record.md:28`。
3. **编排/调用分离是为了解决 Copilot 路径**：决策记录明确 Copilot 只需要「解析好的 route」，Gateway 不负责调用 Copilot，见 `client-layer-decision-record.md:47` 和 `client-layer-decision-record.md:54`。
4. **route-first 契约避免两套消费方各自解释配置**：当前 Graph Agent 通过 model 间接消费 route，Copilot service 通过 `_resolve_copilot_runtime()`(用途:Copilot service 内部 helper，解析 `copilot_chat` role 取 routes + credential provider)直接消费 route，见 `llm_phase_node.py:173` 和 `copilot.py:419`。两条路径应收敛到同一 handoff API。
5. **route 契约必须保留 runtime settings 来源**：provider runtime matrix 说明 effective runtime settings 的来源顺序和元数据用途，见 `docs/graph-agent-gateway/mvp0/provider-runtime-settings-matrix.md:32` 和 `provider-runtime-settings-matrix.md:42`。
6. **不照抄 MVP0 旧模型**：MVP0 baseline 已声明旧 `ResolvedRole.call_chain/ResolvedProvider` 模型过时，见 `docs/graph-agent-gateway/mvp0/baseline.md:8`；当前源码是 `ResolvedRole.routes`，见 `registry/schema.py:456`。

## 6. 测试关键点

- **route 是唯一交接物**：role 级返回的 `GatewayChatModel` 内部、route 级返回的 `ResolvedRole`，**两条路径解析同一 role 应得到同一组有序 route**(防止 role 级和 route 级 API 解析结果分叉)。
- **route 级不替 app 调**：`resolve_routes(role_name)` 返回 `ResolvedRole` 后，gateway **不应**发起任何 provider 调用(纯编排，调用由 app 自己做)。
- **role 级一路调到底**：`ModelResolver.resolve` 返回的 model 在 `.invoke` 时才遍历 routes、按 fallback 链调，第一条坏掉能切下一条。
- **override fail-fast vs fallback skip**：`model_override`(route override)指坏 route → fail-fast；普通 fallback 链坏 route → skip(交接契约对两级 API 一致)。
- **Copilot 走 public API 后行为不变**：Copilot 从直接 import pure `resolve_role` 改为走 route 级 public API 后，拿到的 routes(顺序/credential provider)与现状一致(回归 `copilot.py:419-437`)。
- **WS 事件不承担 route 解析**：`CopilotEvent` 即使将来加 route diagnostics，route 的解析也**不**发生在 WS 层(WS 只渲染，解析在 ③b)。
- **MVP0 旧模型不回归**：handoff 契约用 `ResolvedRole.routes`，不得退回 `call_chain/ResolvedProvider`。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`ResolvedRoute/ResolvedRole` 契约(`registry/schema.py`)、`ModelResolverProtocol`/`ModelResolver`(两级对外 API)、`__init__` 公共导出门面、`GatewayChatModel` 编排外壳。
- **③a** `apps/studio/backend`：Copilot WS 事件 DTO(`models/copilot.py`，**应用自己的契约，引用 route**)、`_resolve_copilot_runtime` 消费 helper(应改走 route 级 public API)、Graph Agent phase 的 model-first 消费点。
- **② Rust**：N/A(角色/凭证/route 数据永不 Rust)。

## 8. gaps / 待设计

1. 需要主控确认 route 级 handoff API 的**精确形状**(归属已定 ③b，形状待定)：是在 `ModelResolverProtocol` 增加 `resolve_routes()`，还是让 `resolve()` 返回新 wrapper，再保留旧 `resolve_chat_model()` 兼容。**注**：归属不再是疑点(已定 ③b 公共 API)，只剩签名取舍。
2. 需要主控确认 `model_override` 是否改名为 `route_override`；当前代码行为已是 route override，见 `registry/resolver.py:37`。
3. 现有 Copilot WS 事件模型已确认在 `apps/studio/backend/app/models/copilot.py`；若 MVP1 新增 gateway-side Copilot route diagnostics DTO，应在 manifest 另行登记，不要混同现有 WS 事件模型(后者是 ③a 应用契约)。
4. 需要主控确认 Copilot WS 是否应暴露 route diagnostics；这属于 ③a 产品可观测性取舍(应用加工)，不是 ③b 公共契约，也不是纯代码事实。
5. **代码下沉/接线**(后续工程，非本轮)：让 Copilot `_resolve_copilot_runtime` 从直接 import pure helper 改为调用 route 级 public API；`__init__` 导出 route handoff 类型。

## 已实现 / 与 baseline 差异

| 项 | baseline 现状 | MVP1 alignment |
|---|---|---|
| route 数据 | `ResolvedRoute` 已存在，但主要藏在 `GatewayChatModel.resolved_role.routes` 内部。 | route 成为公开 handoff API 的一等输出(两级 API)。 |
| resolver API | `ModelResolverProtocol.resolve()` 返回 `BaseChatModel`，见 `protocol.py:38`。 | role 级保留；**新增 route 级 public API** 使调用方能直接取得 `ResolvedRole/ResolvedRoute`(已定 ③b 要求)。 |
| Graph Agent 消费 | `LlmPhaseNode._resolved_tracing_model`(用途:Graph Agent phase 解析入口，调 resolver 拿 model 再包 tracing 代理)只拿 model，见 `llm_phase_node.py:173`。 | Graph Agent 编排层拿 route，调用层再用 route 构造 ChatX/Gateway model。 |
| Copilot 消费 | `_resolve_copilot_runtime()` 自己从 registry 取 routes，见 `copilot.py:419`。 | Copilot 走 route 级 public API，拿 route 后自行调用 `claude_agent_sdk`(③a 调用方式)。 |
| 公共导出 | `__init__.py`(用途:Gateway 包公开门面，导出 resolver/model/异常/fallback event)导出 resolver/model/errors/events，但未导出 route handoff helper，见 `__init__.py:15`。 | 公共门面应暴露稳定 route handoff 类型/API，避免 service 绕内部 resolver。 |
| WS 事件 | `CopilotEvent` 不带 route 信息，见 `apps/studio/backend/app/models/copilot.py:63`。 | 可选增加 route diagnostics(③a 产品取舍)；即使不加，WS 也不应承担 route 解析。 |

## 覆盖代码(含覆盖率)

覆盖率：目标设计覆盖 brief 指定入口 100%；其中 Copilot WS 事件实际路径已核实为 `apps/studio/backend/app/models/copilot.py`。

| 覆盖项 | 归属 | 覆盖状态 | MVP1 目标 |
|---|---|---:|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:ModelResolverProtocol` | **③b** | 100% | `ModelResolverProtocol` 当前只返回 `BaseChatModel`；MVP1 应补齐 route-first 编排 API(route 级 public API)。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py` | **③b** | 100% | `__init__.py` 当前未导出 route handoff API；MVP1 应让公共门面暴露稳定 route 契约入口。 |
| `apps/studio/backend/app/models/copilot.py` | **③a 应用契约** | 100% | `CopilotEvent*` 当前只承载 WS 文本/工具/error；MVP1 可按产品需要补 route diagnostics(③a 取舍)，但核心不是让 WS 自己解析 route。**它引用 route ≠ ③b 泄漏**。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRoute` | **③b** | 100% | `ResolvedRoute` 应成为调用层输入的唯一 route 数据。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRole` | **③b** | 100% | `ResolvedRole` 应成为 role→routes 编排结果。 |

## 决策原因(详细，承上 §5)

1. A' 否决「resolver 直接产 ChatX + 删除 `GatewayChatModel`」。`GatewayChatModel` 保留编排职责，避免丢失 fallback/probe/熔断/usage/metadata，见 `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:22` 和 `client-layer-decision-record.md:28`。
2. 编排/调用分离是为了解决 Copilot 路径。决策记录明确 Copilot 只需要「解析好的 route」，Gateway 不负责调用 Copilot，见 `client-layer-decision-record.md:47` 和 `client-layer-decision-record.md:54`。
3. route-first 契约避免两套消费方各自解释配置。当前 Graph Agent 通过 model 间接消费 route，Copilot service 通过 `_resolve_copilot_runtime()` 直接消费 route，见 `llm_phase_node.py:173` 和 `copilot.py:419`。
4. route 契约必须保留 runtime settings 来源。provider runtime matrix 说明 effective runtime settings 的来源顺序和元数据用途，见 `docs/graph-agent-gateway/mvp0/provider-runtime-settings-matrix.md:32` 和 `provider-runtime-settings-matrix.md:42`。
5. 不照抄 MVP0 旧模型。MVP0 baseline 已声明旧 `ResolvedRole.call_chain/ResolvedProvider` 模型过时，见 `docs/graph-agent-gateway/mvp0/baseline.md:8`；当前源码是 `ResolvedRole.routes`，见 `registry/schema.py:456`。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:ModelResolverProtocol`(③b)：当前 resolver 协议，MVP1 需要补 route-first 输出能力(route 级 API)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:ModelResolver.resolve`(③b)：当前 model-first 包装点，可作为新增 handoff API 的邻近位置。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolve_role`(③b)：当前纯编排函数，已经能产出 `ResolvedRole`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRoute`(③b)：route handoff 字段定义(权威源)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRole`(③b)：role→routes 编排结果定义(权威源)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py`(③b)：公共 API 导出位置。
- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:LlmPhaseNode._resolved_tracing_model`(③a 消费方)：Graph Agent 当前 model-first 消费点。
- `apps/studio/backend/app/services/copilot.py:_resolve_copilot_runtime`(③a 消费方)：Copilot 当前 route 解析 helper，应改走 route 级 public API。
- `apps/studio/backend/app/models/copilot.py:CopilotWsRequestPayload`(③a 应用契约)：Copilot WS 请求体，目前没有 route 字段。
- `apps/studio/backend/app/models/copilot.py:CopilotEvent`(③a 应用契约)：Copilot WS 输出事件联合类型，目前没有 route diagnostics。

## 交叉引用(链接，不复制)

- [[02-orch-role-resolution]]：`resolve_role`/`materialize` 产出本契约的 `ResolvedRole/ResolvedRoute`
- [[04-orch-registry-schema]]：`ResolvedRoute/ResolvedRole` 字段权威源(本模块只链接)
- [[09-inv-invocation-runtime]]：调用层如何消费本契约 route
- [[10-inv-route-chat-model-factory]]：`ResolvedRoute`→原生 ChatX 的工厂
- [[12-inv-copilot-invocation]]：route 级消费方(模块 12 已降为 stub 并入本模块)
- 决策记录 `client-layer-decision-record.md` D2/D3 / 归属表 `module-disposition-revised.md`

## 待办/疑点(原始留底，承上 §8)

1. 需要主控确认 handoff API 形状：是在 `ModelResolverProtocol` 增加 `resolve_routes()`，还是让 `resolve()` 返回新 wrapper，再保留旧 `resolve_chat_model()` 兼容。(归属已定 ③b，仅签名待定)
2. 需要主控确认 `model_override` 是否改名为 `route_override`；当前代码行为已是 route override，见 `registry/resolver.py:37`。
3. 现有 Copilot WS 事件模型已确认在 `apps/studio/backend/app/models/copilot.py`；若 MVP1 新增 gateway-side Copilot route diagnostics DTO，应在 manifest 另行登记，不要混同现有 WS 事件模型。
4. 需要主控确认 Copilot WS 是否应暴露 route diagnostics；这属于产品可观测性取舍(③a 应用加工)，不是纯代码事实。
