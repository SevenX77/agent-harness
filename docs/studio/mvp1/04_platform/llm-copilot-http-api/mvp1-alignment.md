---
module: llm-copilot-http-api
doc: mvp1-alignment
tier: ③a studio platform（后端 LLM/Copilot HTTP 适配壳）
status: drafted
---

# llm-copilot-http-api — Studio LLM/Copilot HTTP 面 · MVP1 设计

> **本文 = studio ③a 平台文档**（`04_platform/`，后端基础设施层）。**2026-06-03 从 gateway mvp1 模块 14 迁入**：它是 ③a 应用加工，不属 ③b gateway 公共内核，故移出 gateway 文件夹归 studio 平台层。
> **跨树引用约定**：本文中 `NN-orch-*` / `NN-inv-*` 形式的 wikilink 指 **gateway mvp1 模块**（`docs/graph-agent-gateway/mvp1/`）——router 调用的能力内核属 ③b 公共；HTTP 壳本身属本文 ③a。
> **Tier**：**③a Studio HTTP 适配壳**。`routers/llm.py`/`routers/copilot.py` = Studio 把 HTTP 输入翻译成 service/gateway 调用的适配层（消费方），**不是 ③b gateway 公共内核**。判据：HTTP 端点形状、job/进度包装、DTO 投影绑死了"这个 app 的调用方式 + 存储介质"，换个 app 不会复用同一套 router → ③a 应用加工。
> **Owns**：HTTP 端点族（registry CRUD / endpoint·model·role test / import draft / model profile / capability projection / 官方 provider 探测 / Copilot ws+test）的协议适配 + DTO 投影 + job 包装；**底下调的 service 多数是 ③b 公共能力内核（待下沉）**。
> **Status**：设计定稿；代码 = `routers/llm.py` 约 4960 行巨型 router，MVP1 标注每端点 delegate 去向 + 登记拆分待办，**本轮不动代码**。
> **⚠️ 内核 vs 适配壳**：文档内凡出现 **base_url 归一化 / capability 归一化·对比 / probe 策略（批批打·命中停·结构错短路）/ materialize 编排 / 6 态标准总结 / draft 知识库 / endpoint 标准化拆分** 的逻辑，其**能力内核属 ③b 公共（现散 ③a 待下沉）**；router 自身**仅 HTTP glue**（解析 DTO + 状态码映射 + 调 service + job/进度包装 + 落存储）。判据权威源：`packages/graph-agent-gateway/README.md` §2 + ux-spec §6.1 逐操作归属表（A1–A12）。
> **Related**：[[02-orch-role-resolution]]（materialize/`resolve_role` 内核，router 的 `_role_effective_runtime_settings`/`_materialize_roles_for_response` 调它）· [[03-orch-credentials-endpoints]]（base_url 归一化 + endpoint 拆分内核，`put_registry_endpoints` 调它）· [[05-orch-capabilities-and-models]]（capability/profile/lint 内核，probe 端点调它）· [[07-orch-fallback-circuit-probe]]（route probe + 熔断 health store）· [[08-orch-test-status-ssot]]（6 态投影 + draft 知识库）· [[copilot-assist]]（Copilot ws/test 端点 delegate 去向）
> **决策日志**：client 层 A' 重设计决策（**完整逻辑 + 用户原话见本文 §4/§5，本模块留底**）—— D3（gateway 可复用、前端不归 gateway、router = studio 适配器非 gateway 核心）+ F1（base_url 保存时归一化，见本文 §5 第 2 条）；归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md` 行 47（14 routers = ③a 应用/薄壳适配）+ ux-spec §6.1/§6.3。**D3 跨模块共享**，另见 [[copilot-assist]]（copilot SDK 调用据 D3 判 ③a）；**F1 共享决策**权威源 [[03-orch-credentials-endpoints]]。
> **现状**：见同目录 `baseline.md`

## 1. 定义

本模块是 Studio 后端暴露给前端的 LLM/Copilot HTTP 面，约 4960 行集中在 `apps/studio/backend/app/routers/llm.py`（+ `routers/copilot.py`）。MVP1 把它定性为 **③a Studio HTTP 适配壳**：它的唯一职责是把 HTTP 请求翻译成对编排、凭证、探测、角色、Copilot service 的清晰调用，再把结果投影成前端 DTO。

**适配壳 vs 内核的边界**（本模块最重要的标注）：现状这个巨型 router 把 API handler、job store、probe 策略、projection、evidence、role materialize 全揉在一个文件里。按判据，其中**真正的能力内核（base_url 归一化 / capability 归一化 / probe 策略 / materialize / 6 态总结 / draft 知识库 / endpoint 拆分）属 ③b 公共，应下沉 gateway 包**；router 留下的只应是 HTTP glue（DTO 解析 + 状态码 + 调 service + job/进度/HTTP 包装 + 落存储）。本文按 endpoint 家族写目标边界，为后续拆分留索引。本文只写文档目标，不改代码。

## 2. 数据流 / 机制（目标；现状逐步见 `baseline.md`）

**上下游**：前端 HTTP（① ts）→ `routers/llm.py`/`routers/copilot.py`（③a 适配壳：解析 DTO + 状态码映射）→ 调 ③b 公共能力内核（编排 `resolve_role`/materialize、capability 归一化、route probe、base_url 归一化、6 态总结、draft 知识库——现多数散在 `apps/studio/backend/app/services/llm_*` 待下沉）→ ③a 包装 job/进度 + 落存储 → 投影前端 DTO。

**目标设计与流程**（逐步）

1. API 层只做协议适配：解析请求 DTO、做 HTTP 状态码映射、调用 service/gateway function，然后返回前端 DTO。现状 `get_llm_registry`（`/api/llm/registry` 读取端点：读 credentials/roles 后委托投影）已接近这个形态，它只读 credentials/roles 并委托 `_registry_response`，见 `apps/studio/backend/app/routers/llm.py:312-318`。
2. Registry 读取端点返回统一后端 SSOT。`_registry_response`（把 credentials 与 roles join 成前端 registry DTO 的投影器）应继续包含 provider endpoints/routes、roles、model profiles、canonical groups、lint、route runtime settings 和 role effective runtime settings，见 `routers/llm.py:1336-1384`。**内核归属**：canonical group 分组、lint、effective runtime settings 的计算 = ③b 公共；router 只做 join + DTO 包装。
3. Endpoint 保存端点负责持久化 endpoint 与 secret，但 base_url canonicalization 应在保存路径发生。现状 `put_registry_endpoints`（upsert endpoints，缺席的不删除）直接调用 `upsert_endpoints`，见 `routers/llm.py:334-343`；MVP1 应确保该 service 在写入前按 protocol 归一化。**内核归属**：base_url 按 protocol 归一化 + endpoint 标准化拆分 = ③b 公共（[[03-orch-credentials-endpoints]]）；router 只 upsert + 落存储。
4. Test/probe 端点必须走真实运行路径或与运行路径等价的官方 profile 选择。`test_endpoint_models`（对指定模型 ID probe，成功 upsert verified routes）与 `_probe_official_model_profile_result`（对官方模型尝试多种调用方法，产 `VerifiedProfile` 列表）当前已经把 official provider probe 转成 `VerifiedProfile`，见 `routers/llm.py:581-780`、`:2735-2805`，但 Copilot SDK test 仍需改成真实 Claude SDK 路径（[[copilot-assist]]）。**内核归属**：probe 策略（批批打/命中停/结构错短路）+ route probe + 错误分类 = ③b 公共；router 只做 job/进度/HTTP 包装。
5. Role 保存端点只保存精确 route chain，不按 provider/capability/price 动态选型。现状 role 保存通过 `_save_roles_with_active_routes`（保存前校验 route reference）校验，见 `routers/llm.py:4726-4735`，registry resolver 才在运行前给出有效 route。
6. Model profile 端点继续作为 authoring abstraction。`apply_model_profile`（把 profile 的 fallback_chain snapshot 写入 role）见 `routers/llm.py:1279-1309`，运行时只读 role 当前 route chain。
7. Copilot API 入口保持独立 router：HTTP/WebSocket 层转发给 `stream_query`，实际调用仍在 Copilot service（③a 领域，[[copilot-assist]]），见 `apps/studio/backend/app/routers/copilot.py:34-55`。
8. 大文件拆分目标：保留 `router` 注册点，把 probe job、official profile probe、role materialization、registry response projection、evidence import/export 拆成 service 模块（其中能力内核继续下沉 ③b，studio 适配/工作流留 ③a）。拆分后 HTTP endpoint 的行为不变，但每个 service 可以单独测试。

## 3. 接口契约

> 本模块是"对外 HTTP 契约"的所在地（① ↔ ③a 握手）。下表是端点级契约；DTO 字段权威源在 [[04-orch-registry-schema]]，本模块只链接不复制。

| 边界 | 契约 |
|---|---|
| **① ↔ ③a（LLM registry，HTTP）** | `GET /api/llm/registry`（`RegistrySnapshot`，api_key **redacted**）· `GET …/endpoints/{id}/secret`（单条明文，scoped reveal）· `PUT …/registry/endpoints`（upsert ③b 拆好的 endpoint 列表，缺席不删）· `DELETE …/endpoints/{id}`（删 endpoint + 清理 roles 中引用）· `POST …/endpoints/{id}/test`（批量模型探测 job）· `POST …/routes/{id}/probe[?force=true]`（单 route 真探）。DTO = endpoint/route + 6 态 `ui_state`，api_key 一律 redact。 |
| **① ↔ ③a（roles / bundles，HTTP）** | `GET/PUT/DELETE /api/llm/roles[/{name}]` · `POST /api/llm/roles/{name}/test(-jobs)` · `GET/PUT/DELETE /api/llm/model-bundles[/{id}]`+`/test` · `GET /api/llm/model-groups` · `GET/PUT/DELETE /api/llm/model-profiles[/{id}]`+`/apply`。`put_llm_roles` 含 Copilot/Graph Agent 分流保护（`_is_copilot_role` 认 `copilot_` 前缀）。 |
| **① ↔ ③a（import draft，HTTP）** | `POST/GET …/import-drafts` + `…/probe` + `…/apply`（draft 创建/读取/标记 probed/显式 apply 到 active credentials）· `sync_catalog`/`share_catalog`（远端证据库拉取/共享）。 |
| **① ↔ ③a（Copilot，HTTP/WS）** | `WS /api/.../copilot`（`copilot_ws` 转发 `stream_query`）· `POST /api/copilot/context`（缓存 view context，不调模型）· `POST /api/copilot/roles/{name}/test-sdk`（Copilot role SDK 测试，MVP1 改真 `ClaudeSDKClient`）。 |
| **③a → ③b（router 调内核）** | router 把原始输入交 ③b 内核（endpoint 拆分 / base_url 归一化 / list-models 解析 / capability 归一化 / route probe / 批量探测策略 / materialize / `resolve_role` / 6 态总结 / draft 读写），**③b 返回标准结果**，③a 只包装 job/HTTP + 落存储。内核现散 `services/llm_*` 待下沉，见 `module-disposition-revised.md` §2。 |
| **归属 / 稳定性** | router 自身 = ③a HTTP glue；**DTO 字段权威源** = [[04-orch-registry-schema]]（`registry/schema.py`），本模块只链接不复制，防 drift。 |

## 4. 设计决策基础（用户原话）

> **D3 — Gateway = 可复用服务，前端不归 gateway，router = studio 适配器非核心**（client 层 A' 重设计决策，本文留底）。**决策**：gateway 只提供服务（编排 + 调用），**不含任何前端**；前端是 **studio 的前端**，studio 只是 gateway 的一个消费方；gateway 必须设计清晰对外 API 供其他 app 复用。**含义（本模块的直接依据）**：`routers/llm.py`、`routers/copilot.py` = studio 的 HTTP 适配器（消费方），**非 gateway 核心**；而 `apps/studio/backend/app/services/llm_*`（动脑 services）= **应迁入 gateway 包**。用户原话：
> > "前端不归gateway管, 前端是studio的前端, gateway只管提供服务, 所以模块功能分个清楚, API怎么提供要写清楚, 要考虑复用其他app"
> → 故本模块定性为薄适配壳、能力内核下沉。D3 是跨模块共享决策，另见 [[copilot-assist]]（copilot SDK 调用同据 D3 判 ③a）。

> **判据铁律（ux-spec §6.0 第四轮反转）**："换个 app 还原样能用吗？能=③b 公共，不能（绑死那四件事之一）=③a。" → HTTP 端点形状、job/进度包装绑死了 studio 的调用方式 → router 留 ③a；但端点底下的 base_url 归一化 / capability / probe 策略 / materialize / 6 态 / draft 内核 = ③b 公共，应下沉。

## 5. 决策 + 动机

1. **API 层不应成为编排/调用混合层**。A' 决策（D2）要求编排输出 route、调用层消费 route；router 如果继续直接藏 probe、profile、materialize、SDK 调用细节，后续很难判断某个失败属于 HTTP 输入、编排选择还是真实调用。**因此本模块定性为薄适配壳，内核下沉。**
2. **保存时归一化 base_url 比运行时临时修正更稳**（client 层 A' 重设计决策 F1）。**决策**：主 = credential 保存时归一化（每 endpoint 存确定的 canonical 格式，每 protocol 规则固定），副 = 调用时幂等归一化做双保险（已 canonical 则 no-op）。HTTP save 端点是 endpoint 数据进入 active credentials 的边界；在这里（经 ③b 内核）归一化可让 graph-agent、Copilot、probe 三条路径拿到同一 canonical 数据。用户原话："base_url 归一化的关键是每个protocol都有确定的统一的规则 ... 如果结果足够确定, 我觉得放在credential保存时归一化是最好的, 每个endpoint都有固定格式, 存这个固定格式保证不会出错"。**F1 共享决策权威源 [[03-orch-credentials-endpoints]]**（每 protocol canonical 规则 + 保存路径），本模块只钉「save 端点必须调到归一化 service」。
3. **Test endpoint 必须贴近真实运行路径**，因为 MVP0 素材与 client 层 A' 重设计决策都指出"裸 SDK 单次 probe"不能证明 agent loop 能跑。现状 `_probe_copilot_sdk_tool_call`（Copilot SDK 测试探针，实际用 `AsyncAnthropic`）就是要修的反例，见 `routers/llm.py:2150-2172`；目标见 [[copilot-assist]]。
4. **保留 model profile 作为 authoring abstraction**，是为了让前端复用"Claude Opus thinking"这类组合，但 runtime 只执行 role 保存的 route chain。现状 `apply_model_profile` 已把 profile snapshot 写入 role，见 `routers/llm.py:1279-1309`，这符合"profile 修改不隐式改变已有 role"的方向。
5. **拆 router 是为了降低理解成本而不是改变行为**。`routers/llm.py` 已经超过 4900 行，文档只能按 endpoint 家族讲；代码后续也应按同样家族拆分（能力内核下沉 ③b，studio 适配留 ③a），否则每个 MVP1 改动都要穿越整座文件。**被否的近路**：把内核也留在 router"图省事" → 违反 D3「gateway 可复用」+ 让公共能力被 studio HTTP 壳绑死。

## 6. 测试关键点

> router 是适配壳，测试关注点 = HTTP 契约 + delegate 正确性 + 不在 router 内重新实现内核语义。能力内核本身的测试归各 gateway 内核模块（02/03/05/07/08）；copilot SDK 测试归 [[copilot-assist]]。

- **HTTP 契约稳定**：拆分前后同一端点（`GET registry` / `PUT endpoints` / `roles test-jobs` / Copilot ws）的请求/响应 DTO 不变（行为不变，只搬实现）。
- **secret redaction**：`GET /api/llm/registry` 返回的 api_key 一律 redacted；只有 `GET …/endpoints/{id}/secret` 返回单条明文（scoped reveal）。
- **Copilot/Graph Agent 分流**：`put_llm_roles` 保存 Graph Agent roles 时保留现有 Copilot roles，反之亦然（`_is_copilot_role` 认 `copilot_` 前缀，回归点 `routers/llm.py:909-952`）。
- **endpoint 删除清理引用**：`delete_registry_endpoint` 删 endpoint 时，从 roles 中移除引用该 endpoint 下 routes 的条目。
- **save 触发归一化**：`put_registry_endpoints` 写入前 base_url 已按 protocol canonical（内核语义验证归 [[03-orch-credentials-endpoints]]，router 只验"有没有调到归一化 service"）。
- **Copilot SDK test 走真 SDK**：`test_copilot_role_sdk` 改走 `ClaudeSDKClient`（非 `AsyncAnthropic`），否则 API 层给前端一个不可靠的"通过"信号（[[copilot-assist]]）。
- **draft apply 显式**：`apply_import_draft` 只在显式调用时 merge/apply 到 active credentials（不隐式写入）。

## 7. 涉及 region / platform

- **③a** `apps/studio/backend/app/routers`：`llm.py`（巨型 LLM registry router）、`copilot.py`（Copilot ws/context/test router）= HTTP 适配壳本体，**留 ③a**。
- **③a → 待下沉 ③b**：现散在 `apps/studio/backend/app/services/llm_*` 的能力内核（materialize / model_groups / identity / notable / state_projection / import_drafts / health_store / route_capabilities），按判据应下沉 `packages/graph-agent-gateway`；router 内联的 probe 策略 / list-models 解析 / endpoint 拆分同理（下沉清单见 `module-disposition-revised.md` §2）。
- **① 前端 (ts)** `apps/studio/frontend`：HTTP 调用方（只投影 registry DTO，不持第二份真相）。
- **② Rust**：N/A（凭证/角色/registry 数据永不 Rust）。

## 8. gaps / 待设计

- **待办（后续工程，非本轮）**：把 `routers/llm.py` 的非 HTTP glue 逻辑拆到 service 层，尤其是 official profile probe、role test job、registry response projection、import draft/evidence；其中能力内核继续下沉 ③b（gateway 包），studio 适配/工作流（job/进度/HTTP 包装、import-apply UI 工作流、远端源选择）留 ③a。
- **待办**：把 Copilot SDK test 改为真实 `ClaudeSDKClient` 路径，否则 API 层仍会给前端一个不可靠的"通过"信号；归 [[copilot-assist]]。
- **待办**：`put_llm_roles` 中 Copilot/Graph Agent 分流属于产品保护逻辑，但现在写在 router handler 内（`routers/llm.py:909-952`）；分流"认 `copilot_` 前缀"是 ③a 产品策略，后续最好下沉到 service 层以便复用和测试（注意：是 ③a service，不是 ③b——它绑死 copilot 语义）。
- **疑点**：`dispatch_copilot`（`routers/copilot.py:23`）保留旧 dispatch scaffold 当前直接 501，是否清理需主控确认。

## 已实现 / 与 baseline 差异

| 项目 | baseline 现状 | MVP1 目标 |
|---|---|---|
| Registry SSOT | `get_llm_registry` + `_registry_response` 已输出 joined registry、lint、runtime settings（`routers/llm.py:312-318`,`:1336-1384`） | 保留，并确保 test status、effective settings、capabilities 都从后端投影（内核归 ③b）。 |
| endpoint save | `put_registry_endpoints` 直接 upsert（`routers/llm.py:334-343`） | 保存时按 protocol canonicalize base_url（③b 内核），调用时只做幂等双保险。 |
| route probe | `probe_route` 可写 capability/runtime settings，`_force_probe_route` 可真实 probe 并写 circuit（`routers/llm.py:782-818`,`:1818-1887`） | 保留，并让 health/test 状态成为 UI SSOT（6 态总结 ③b 内核）。 |
| role test | `_run_role_test_targets` 并发跑每个 target，`_role_test_provider_result` 决定 ok/failed/blocked（`routers/llm.py:1070-1129`,`:1889-1959`） | 保留入口，但 graph-agent role test 应走真实 gateway/agent loop；Copilot role test 应走真实 Claude SDK。 |
| official profile | `_probe_official_model_profile_result` 已产 `VerifiedProfile`（`routers/llm.py:2735-2805`） | 保留为 provider profile / invocation profile 的证据来源，但不要让 capability lint 动态选 route。 |
| 文件组织 | `routers/llm.py` 同时做 API、service、probe、projection、job store | 拆为多个 service 模块，router 只保留 HTTP glue（能力内核下沉 ③b）。 |
| Copilot router | websocket 和 context 已独立在 `routers/copilot.py`（`:34-86`） | 保留；测试端点对齐真实运行 SDK。 |

## 代码索引（clues）

| 论断 | 代码线索 |
|---|---|
| `/api/llm` router 入口 | `apps/studio/backend/app/routers/llm.py:router` (`:127`) |
| registry 响应聚合 | `get_llm_registry` (`:312-318`), `_registry_response` (`:1336-1384`) |
| endpoint upsert/delete | `put_registry_endpoints` (`:334-343`), `delete_registry_endpoint` (`:346-360`) |
| endpoint official job | `start_endpoint_test_job` (`:363-393`), `_run_official_endpoint_test_job_impl` (`:3880`) |
| endpoint/model probe | `test_endpoint` (`:460-574`), `test_endpoint_models` (`:581-780`) |
| route probe / circuit | `probe_route` (`:782-818`), `_force_probe_route` (`:1818-1887`) |
| import drafts | `post_import_draft/get_import_draft/probe_import_draft/apply_import_draft` (`:856-880`) |
| roles CRUD/test | `get_llm_roles` (`:899`), `put_llm_roles` (`:909`), `test_llm_role` (`:996`), `start_role_test_job` (`:1009`) |
| model profiles | `get_model_profiles` (`:1222`), `put_model_profiles` (`:1228`), `delete_model_profile` (`:1249`), `apply_model_profile` (`:1279`) |
| role effective settings | `_role_effective_runtime_settings` (`:4588-4603`)（调 [[02-orch-role-resolution]] `resolve_role`） |
| route materialization | `_materialize_roles_for_response` (`:4613-4642`), `_materialize_role_for_response` (`:4682-4723`)（调 ③b materialize 内核） |
| Copilot websocket | `apps/studio/backend/app/routers/copilot.py:copilot_ws` (`:34-55`) |
| Copilot context | `post_copilot_context` (`:58-86`) |
| Copilot test | `test_copilot_role_sdk` (`:89-126`)（delegate `_probe_copilot_sdk_tool_call`，假测试，见 [[copilot-assist]]） |

## 交叉引用（链接，不复制）

- [[02-orch-role-resolution]]：materialize / `resolve_role` 内核（router 的 `_role_effective_runtime_settings`/`_materialize_roles_for_response` delegate 到这里）
- [[03-orch-credentials-endpoints]]：base_url 归一化 + endpoint 拆分内核（`put_registry_endpoints` delegate）
- [[04-orch-registry-schema]]：DTO 字段权威源（本模块只链接）
- [[05-orch-capabilities-and-models]]：capability/profile/lint 内核（probe 端点 delegate）
- [[07-orch-fallback-circuit-probe]]：route probe + 熔断 health store
- [[08-orch-test-status-ssot]]：6 态投影 + draft 知识库内核
- [[copilot-assist]]：Copilot ws/test 端点的调用层目标（假测试修正）
- **client 层 A' 重设计决策 D3 + F1**：完整逻辑 + 用户原话见本文 §4/§5（本模块留底）；D3 共享见 [[copilot-assist]]，F1 共享源 [[03-orch-credentials-endpoints]]。归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md` 行 47 + ux-spec §6.1/§6.3
