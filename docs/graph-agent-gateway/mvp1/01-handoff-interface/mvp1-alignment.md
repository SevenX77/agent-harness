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
> **Related**：[[02-orch-role-resolution]](resolve_role/materialize 产出本契约)· [[04-orch-registry-schema]](`ResolvedRoute/ResolvedRole` 字段权威源)· [[09-inv-invocation-runtime]](调用层消费本契约)· [[10-inv-route-chat-model-factory]](`ResolvedRoute`→ChatX)。route 级消费方（如 studio copilot：拿 route 自己用 SDK 调）由本模块的 route 级 API 覆盖；copilot 怎么用 route 调（SDK/session/事件）属 ③a，见 studio copilot（`docs/studio/mvp1/02_capabilities/copilot-assist/` + `00_settings-ux-spec.md` §3.8）。
> **决策日志**：本模块 route 契约依据 client 层 A' 重设计决策 D2(编排/调用分离)+ D3(gateway 可复用服务、API 一等公民、两级接口)——完整逻辑 + PM 原话留底于本文 §4/§5；归属判据见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`(01 = ③b 公共，**补 route 级直调 public API**)。D2/D3 是跨模块共享决策,另见 [[04-orch-registry-schema]](schema 作为编排↔调用交接数据契约同引 D2/D3)、[[09-inv-invocation-runtime]](调用层落 D2「调用」侧)。
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
4. Graph Agent 调用消费(role 级)：Graph Agent 仍可以拿 `GatewayChatModel`，但该 model 内部只应把 `ResolvedRoute` 交给调用层工厂/ChatX，不再自研消息转换。按 client 层 A' 重设计,`_generate`(用途:`GatewayChatModel` 的 fallback 执行循环，遍历 routes 做 probe/dispatch/usage/event)只改「消息准备 / dispatch / 结果构建」三步(调用层),保留遍历/熔断/probe/usage/异常分类(编排层);这正是 D2 编排/调用分离在 `_generate` 内的体现(决策动机见本文 §5)。
5. Copilot 调用消费(route 级)：Studio Copilot 应拿同一份 `ResolvedRoute`，再由 `claude_agent_sdk` 自己调用；当前 `stream_query`(用途:Copilot WebSocket 业务入口，解析 route 后用 Claude SDK 调)已有这个方向，但 helper 在 service 内部，没走对外 public API，见 `apps/studio/backend/app/services/copilot.py:210` 和 `copilot.py:419`。
6. 交接边界：route 是唯一交接物，调用层不得重新按 provider/model 猜测或动态选择。MVP0 alignment 明确禁止 capability/price/latency/availability 搜索替代 route，见 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:118`。

### route 契约目标

1. 身份字段：`route_id`、`endpoint_id`、`provider_model_id`、`canonical_id` 是 route 诊断和调用身份，当前字段在 `registry/schema.py:421`、`registry/schema.py:422`、`registry/schema.py:430`、`registry/schema.py:431`。
2. 调用字段：`protocol`、`base_url`、`credential_ref`、`timeout_seconds`、`trust_env`、`proxy_env` 是 provider 调用需要的最小环境，当前字段在 `registry/schema.py:423` 到 `registry/schema.py:429`。
3. 安全字段：`credential_fingerprint` 是 cache/diagnostics 用的非明文密钥标识，当前字段在 `registry/schema.py:426`，构造来源在 `registry/resolver.py:85`。
4. provider profile 字段：`selected_profile_id`、`call_method_id`、`request_mapper_id` 让调用层按 profile 做 init-kwargs 或 mapper 选择，当前字段在 `registry/schema.py:432` 到 `registry/schema.py:435`。
5. runtime 字段：`runtime_settings` 和 `effective_runtime_settings` 分别保存用户意图和 resolver 合成值，当前字段在 `registry/schema.py:437` 和 `registry/schema.py:438`；provider matrix 说明 effective 值会进入 response metadata 和 fallback events，见 `docs/graph-agent-gateway/mvp0/provider-runtime-settings-matrix.md:42`。

## 3. 接口契约

> 本模块 = **编排↔调用 route 握手契约的 SSOT**(框架 §3.2 共享接口:gateway 被 Graph Agent / copilot / 未来 app 多方依赖)。`ResolvedRoute/ResolvedRole` 字段权威源在 [[04-orch-registry-schema]](`registry/schema.py`)，本段**只钉形状+归属+稳定性，字段清单链接不复制**(框架 §5)；所有 consumer **只链接本契约，不另写一份**。

### 握手：编排(③b) → 调用方 —— route 是唯一交接物

- **签名(两级对外 API)**：
  - role 级 `ModelResolver.resolve(role_name, *, thinking_enabled, model_override, callbacks, phase_name, predict_context) → BaseChatModel`(协议 `protocol.py:24-39`)——返回包好的 `GatewayChatModel`/`PredictGatewayChatModel`，gateway 自动按 fallback 链调到底；`model_override` 当前实为精确 `route_override`(`registry/resolver.py:45`)。
  - route 级 `resolve_routes(role_name, model_override) → ResolvedRole`(待补，已定 ③b；[[02-orch-role-resolution]] 落实)——**只返回解析好的 route，不替 app 调**；给"不要编排外壳、自己用别的 SDK 跑"的消费方(如 copilot 走 `claude_agent_sdk`)。
- **数据契约**：`ResolvedRole{ routes: ResolvedRoute[](有序 fallback 候选), system_prompt_prefix, runtime_policy(探活/熔断/截断升级), lint_results, source_profile_* }`。字段权威源 [[04-orch-registry-schema]] `registry/schema.py:415-459`(链接不复制)。
- **方向·归属**：producer = gateway 编排(③b)；consumer = Graph Agent phase / copilot service / 未来 app；**owner = 本模块(01)**——owner 改契约负责通知全部 consumer。
- **错误契约**：role 不存在 / 过滤后空链 → `RegistryResolutionError`(配置错误)→ `ModelResolver.resolve` 统一映射 `GatewayRoleNotConfiguredError`；resolver 依赖缺失 → `GatewayResolverMissingError`(`llm_phase_node.py:133`)。
- **不变量·前后置**：route 是**唯一交接物**——调用层**不得**回读 Studio DTO、不得按 provider/model/price/latency 另选或动态搜索 route(MVP0 禁令 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:118`)；两级 API 解析同一 role → 同一组有序 route。
- **稳定性·版本**：两级 API 签名 FROZEN(D3「API 怎么提供要写清楚」)；`ResolvedRoute/ResolvedRole` 字段可扩展、权威源在 04；不得退回 MVP0 旧 `call_chain/ResolvedProvider`。
- **SSOT 落点**：`registry/schema.py`(字段)+ `protocol.py`(resolver 协议)+ `__init__.py`(公共导出门面)。
- **测试关键点**(同步模板 ##6)：两级 API 解析同一 role 得同一组 route；route 级返回后 gateway **不发起任何** provider 调用(纯编排)；`model_override`(route override)坏 route → fail-fast，普通 fallback 链坏 route → skip。

### consumer 拿 route 之后怎么用 —— 各自的事，本模块只链接(§3.5 所有权不变量)

- **Graph Agent**(③a 消费方)：编排层拿 route，调用层用 route 构造原生 ChatX，见 [[10-inv-route-chat-model-factory]] / [[09-inv-invocation-runtime]]。
- **copilot**(③a 消费方)：拿 `resolve_routes("copilot_chat")` 的 route，自己用 `claude_agent_sdk` 调(当前绕 class 直接 import pure `resolve_role`，`copilot.py:419-437`，应改走 route 级 API)。**其 WS 请求/事件契约**(`CopilotWsRequestPayload`/`CopilotEvent*`，`apps/studio/backend/app/models/copilot.py`)= **studio 应用自有契约，owner=studio**，见 studio [[copilot-assist]] §3.1 + `00_settings-ux-spec.md` §3.8——**本模块只链接、不重述**(WS 事件契约归 studio 一处写，gateway 不写第二份)。copilot **引用** route ≠ ③b 泄漏。

## 4. 设计决策基础(用户原话)

> **判据(本模块「route 级直调 API 归 ③b」依据)**："换个 app 还原样能用吗?能=③b,不能=③a。"(`module-disposition-revised.md:15`、ux-spec §6.0) → 「给 app 解析好 route 让它自己调」是任何调模型 app 的通用需求(不绑死 UI/产品策略/调用方式/存储)→ **③b 公共**。Copilot WS 事件是 Studio 自己怎么把 route 用出去(绑死 copilot 语义 + Claude SDK 调用方式)→ ③a 应用，但它**引用** route ≠ 泄漏。

> **D2 编排/调用分离 + copilot 用例**(client 层 A' 重设计决策 D2)："你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了, 这是调copilot的路径,你只负责输出编排结果, 不负责调用. 所以这里还引申出一个问题, 编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么" —— 这条 D2 是跨模块共享决策,另见 [[04-orch-registry-schema]] §4(schema 同引 D2 作交接数据契约)、[[09-inv-invocation-runtime]](D2「调用」侧落点)。

> **D3 gateway = 可复用服务 / API 一等公民 / 两级 API**(client 层 A' 重设计决策 D3)："前端不归gateway管, 前端是studio的前端, gateway只管提供服务, 所以模块功能分个清楚, API怎么提供要写清楚, 要考虑复用其他app" —— 直接支撑「route 级直调 API 升级为已定 ③b 公共 API」。D3 是跨模块共享决策,另见 [[03-orch-credentials-endpoints]] §4、[[04-orch-registry-schema]] §4(均同引 D3 划分 ③b 公共边界)。

> **§0 #3 copilot 取 route 自己调**(ux-spec `:17`)："copilot和llm roles类似, 只是copilot的role 只能填一个 model group, 并且测试走 copilot 自己的调用, 测试和真实调用没什么区别" —— copilot 拿 route、用自己的 SDK 调(③a 调用方式)，gateway 只给 route(③b)。

> **A' 保留编排外壳**(决策记录 `:40`)："不用留A, 这是错误判断, 正确的是A'。" → 保留 `GatewayChatModel`，fallback/probe/熔断/usage/metadata 留编排外壳，**不**裸返回 ChatX。

## 5. 决策 + 动机

1. **route 级直调 public API = 已定 ③b 新增要求(本轮反转)**：原 baseline/alignment 把它记为「待主控确认 handoff API 形状」；按 D3 + 判据，「给 app 解析好 route 让它自己调」是 gateway 必须提供的公共服务，**反转升级为已定 ③b 新增要求**——两级接口都钉死(role 级已有、route 级待补)。被否的旧表述：「route 形状待主控拍板」。
2. **A' 否决「resolver 直接产 ChatX + 删 `GatewayChatModel`」**：A'(温和版,保留编排外壳)否决了 A(激进版,resolver 直接裸返回 ChatX + 删 `GatewayChatModel` + 用 `with_fallbacks()`)。理由:第八轮真机只验证了「调用层换 ChatX 修空-content bug」,从未验证「删编排层」;而 fallback/probe/熔断/usage/metadata 全在 `GatewayChatModel._generate` 里,删掉就回归;且 `with_fallbacks()` 只按异常类型,表达不了我们「按 HTTP status 分类」的 fallback 语义。所以保留 `GatewayChatModel` 作编排外壳。(client 层 A' 重设计决策 D1;PM 原话见 §4「不用留A, 这是错误判断, 正确的是A'」。)
3. **编排/调用分离是为了解决 Copilot 路径**：Copilot 只需要「解析好的 route」,拿 route 后用自己的 `claude_agent_sdk` 跑,Gateway 不负责调用 Copilot——所以编排(决定该用哪条 route)和调用(真正发请求)应做成两个内聚模块、各有清晰 API。(client 层 A' 重设计决策 D2;PM 原话见 §4。跨模块共享:[[04-orch-registry-schema]] 把 `ResolvedRoute/ResolvedRole` 定为这条交接边界的数据契约、[[09-inv-invocation-runtime]] 是「调用」侧落点。)
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
3. **Copilot WS 是否暴露 route diagnostics** = ③a 产品可观测性取舍，归 studio [[copilot-assist]]（gateway 只提供 route，WS 怎么展示/要不要 diagnostics 是 studio 的事，§3.5 所有权不变量）；gateway 侧只保证 route 解析**不**发生在 WS 层。
4. **代码下沉/接线**(后续工程，非本轮)：让 Copilot `_resolve_copilot_runtime` 从直接 import pure helper 改为调用 route 级 public API；`__init__` 导出 route handoff 类型。

## 已实现 / 与 baseline 差异

| 项 | baseline 现状 | MVP1 alignment |
|---|---|---|
| route 数据 | `ResolvedRoute` 已存在，但主要藏在 `GatewayChatModel.resolved_role.routes` 内部。 | route 成为公开 handoff API 的一等输出(两级 API)。 |
| resolver API | `ModelResolverProtocol.resolve()` 返回 `BaseChatModel`，见 `protocol.py:38`。 | role 级保留；**新增 route 级 public API** 使调用方能直接取得 `ResolvedRole/ResolvedRoute`(已定 ③b 要求)。 |
| Graph Agent 消费 | `LlmPhaseNode._resolved_tracing_model`(用途:Graph Agent phase 解析入口，调 resolver 拿 model 再包 tracing 代理)只拿 model，见 `llm_phase_node.py:173`。 | Graph Agent 编排层拿 route，调用层再用 route 构造 ChatX/Gateway model。 |
| Copilot 消费 | `_resolve_copilot_runtime()` 自己从 registry 取 routes，见 `copilot.py:419`。 | Copilot 走 route 级 public API，拿 route 后自行调用 `claude_agent_sdk`(③a 调用方式)。 |
| 公共导出 | `__init__.py`(用途:Gateway 包公开门面，导出 resolver/model/异常/fallback event)导出 resolver/model/errors/events，但未导出 route handoff helper，见 `__init__.py:15`。 | 公共门面应暴露稳定 route handoff 类型/API，避免 service 绕内部 resolver。 |
| Copilot WS 事件契约 | `CopilotEvent`(③a studio 自有契约，`models/copilot.py`)。 | 归 studio [[copilot-assist]] §3.1(本模块只链接、不重述)；gateway 侧唯一不变量：route 解析**不**在 WS 层。 |

## 覆盖代码(含覆盖率)

覆盖率：目标设计覆盖 brief 指定入口 100%；其中 Copilot WS 事件实际路径已核实为 `apps/studio/backend/app/models/copilot.py`。

| 覆盖项 | 归属 | 覆盖状态 | MVP1 目标 |
|---|---|---:|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:ModelResolverProtocol` | **③b** | 100% | `ModelResolverProtocol` 当前只返回 `BaseChatModel`；MVP1 应补齐 route-first 编排 API(route 级 public API)。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py` | **③b** | 100% | `__init__.py` 当前未导出 route handoff API；MVP1 应让公共门面暴露稳定 route 契约入口。 |
| `apps/studio/backend/app/models/copilot.py` | **③a 应用契约(studio owns)** | — | Copilot WS 请求/事件契约归 studio [[copilot-assist]] §3.1，本模块只链接不重述；这里仅记它是 route 的 ③a 消费方(引用 route ≠ ③b 泄漏)。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRoute` | **③b** | 100% | `ResolvedRoute` 应成为调用层输入的唯一 route 数据。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:ResolvedRole` | **③b** | 100% | `ResolvedRole` 应成为 role→routes 编排结果。 |

## 决策原因(详细，承上 §5)

1. A' 否决「resolver 直接产 ChatX + 删除 `GatewayChatModel`」。`GatewayChatModel` 保留编排职责，避免丢失 fallback/probe/熔断/usage/metadata(完整否决理由 + PM 原话见本文 §4「A' 保留编排外壳」、§5 #2;源自 client 层 A' 重设计决策 D1)。
2. 编排/调用分离是为了解决 Copilot 路径。Copilot 只需要「解析好的 route」，Gateway 不负责调用 Copilot,拿 route 后用自己的 `claude_agent_sdk` 跑(完整逻辑 + PM 原话见本文 §4「D2 编排/调用分离」、§5 #3;源自 client 层 A' 重设计决策 D2,跨模块共享见 [[04-orch-registry-schema]]/[[09-inv-invocation-runtime]])。
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
- `apps/studio/backend/app/models/copilot.py`(③a 应用契约，studio owns)：Copilot WS 请求/事件契约(`CopilotWsRequestPayload`/`CopilotEvent`)——契约定义归 studio [[copilot-assist]] §3.1，本模块只作 ③a 消费方线索、不重述。

## 交叉引用(链接，不复制)

- [[02-orch-role-resolution]]：`resolve_role`/`materialize` 产出本契约的 `ResolvedRole/ResolvedRoute`
- [[04-orch-registry-schema]]：`ResolvedRoute/ResolvedRole` 字段权威源(本模块只链接)
- [[09-inv-invocation-runtime]]：调用层如何消费本契约 route
- [[10-inv-route-chat-model-factory]]：`ResolvedRoute`→原生 ChatX 的工厂
- route 级消费方（如 studio copilot）：见本文 §2.5 / §3「② route 级对外 API」——gateway 给解析好的 route，消费方自己用 SDK 调；copilot 的 ③a SDK 调用见 studio copilot（copilot-assist + ux-spec §3.8）。（原 gateway 模块 12「copilot invocation」已移除：copilot 是 ③a 应用、不构成独立 gateway 模块，其握手即本模块的 route 级 API。）
- 本模块 route 契约依据 client 层 A' 重设计决策 D2/D3(完整逻辑 + PM 原话留底于本文 §4/§5)/ 归属判据见 `module-disposition-revised.md`
