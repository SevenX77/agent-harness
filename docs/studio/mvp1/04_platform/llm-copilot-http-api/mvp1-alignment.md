---
module: 04_platform/llm-copilot-http-api
doc: mvp1-alignment
status: drafted（`routers/llm.py` 是巨型 router，HTTP glue 与 probe/materialize/draft/6态内核混在一起；Copilot SDK test 仍走假路径 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity]
aligns_with: 01_workflows/00_settings-ux-spec.md（HTTP/Settings/Copilot）· docs/graph-agent-gateway/mvp1/README.md（③a/③b handoff）
---

# llm-copilot-http-api — MVP1 Alignment

> **Tier**: platform | **Owns**: ③a Studio HTTP 适配壳；底下调用的公共内核只链接 gateway SSOT | **现状**: `routers/llm.py` 是巨型 router，HTTP glue 与 probe/materialize/draft/6态内核混在一起；Copilot SDK test 仍走假路径 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `gateway` · `studio-settings` · `settings` · `copilot-assist` · `docs/graph-agent-gateway/mvp1/`

## 1. 定义
本模块是 Studio 后端暴露给前端的 LLM/Copilot HTTP 面，约 4960 行集中在 `apps/studio/backend/app/routers/llm.py`（+ `routers/copilot.py`）。MVP1 把它定性为 **③a Studio HTTP 适配壳**：它的唯一职责是把 HTTP 请求翻译成对编排、凭证、探测、角色、Copilot service 的清晰调用，再把结果投影成前端 DTO。

**适配壳 vs 内核的边界**（本模块最重要的标注）：现状这个巨型 router 把 API handler、job store、probe 策略、projection、evidence、role materialize 全揉在一个文件里。按判据，其中**真正的能力内核（base_url 归一化 / capability 归一化 / probe 策略 / materialize / 6 态总结 / draft 知识库 / endpoint 拆分）属 ③b 公共，应下沉 gateway 包**；router 留下的只应是 HTTP glue（DTO 解析 + 状态码 + 调 service + job/进度/HTTP 包装 + 落存储）。本文按 endpoint 家族写目标边界，为后续拆分留索引。本文只写文档目标，不改代码。

## 2. 数据流 / 机制（设计细节）
本模块只拥有 ③a Studio HTTP 适配壳：前端 HTTP/WS → `routers/llm.py` / `routers/copilot.py` 解析 DTO、做状态码映射、启动 job/进度包装、调用 service/gateway、落 Studio 存储，再返回前端 DTO。公共内核机制不在这里复制；provider registry、endpoint 标准化、capability/profile、materialize / `resolve_role`、route probe / fallback / circuit、六态投影与 draft/evidence SSOT 均引用 [`docs/graph-agent-gateway/mvp1/`](../../../../graph-agent-gateway/mvp1/)（尤其 [`02-orch-role-resolution`](../../../../graph-agent-gateway/mvp1/02-orch-role-resolution/mvp1-alignment.md)、[`03-orch-credentials-endpoints`](../../../../graph-agent-gateway/mvp1/03-orch-credentials-endpoints/mvp1-alignment.md)、[`04-orch-registry-schema`](../../../../graph-agent-gateway/mvp1/04-orch-registry-schema/mvp1-alignment.md)、[`05-orch-capabilities-and-models`](../../../../graph-agent-gateway/mvp1/05-orch-capabilities-and-models/mvp1-alignment.md)、[`07-orch-fallback-circuit-probe`](../../../../graph-agent-gateway/mvp1/07-orch-fallback-circuit-probe/mvp1-alignment.md)、[`08-orch-test-status-ssot`](../../../../graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md)）。

1. **HTTP 壳 / DTO**：`/api/llm/registry`、endpoint CRUD/test、route probe、role/profile/model-bundle/import-draft 端点负责 Studio 的 HTTP 契约、redaction、错误码、job id/progress 与前端 DTO；DTO 字段权威源链接 gateway schema，不复制第二份真理。
2. **Studio 消费与渲染**：Settings、LLM Roles、Copilot Settings 读取 ③a DTO，并在前端处理表单、拖拽、toast、保存状态、颜色文案和空态；可执行 route、六态、fallback chain、probe 结果来自 gateway / 后端 SSOT。
3. **Copilot 边界**：Copilot WS 与 `test-sdk` 端点属于 Studio ③a，因为它们绑定 `claude_agent_sdk` 的实际调用方式；gateway 只解析 `copilot_chat` 这类 role 到 route，不拥有 Copilot session/chat 语义。
4. **现状 drift**：baseline 仍记录 `routers/llm.py` 巨型 router 混入 probe/materialize/projection/job store，以及 Copilot SDK test 走假路径；清理目标是文档边界变薄，后续代码再把公共内核下沉到 gateway，Studio 保留 HTTP glue 与应用加工。

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

## 4. 设计决策基础（PM 原话）
> **本文 = studio ③a 平台文档**（`04_platform/`，后端基础设施层）。**2026-06-03 从 gateway mvp1 模块 14 迁入**：它是 ③a 应用加工，不属 ③b gateway 公共内核，故移出 gateway 文件夹归 studio 平台层。
> **跨树引用约定**：本文中 `NN-orch-*` / `NN-inv-*` 形式的 wikilink 指 **gateway mvp1 模块**（`docs/graph-agent-gateway/mvp1/`）——router 调用的能力内核属 ③b 公共；HTTP 壳本身属本文 ③a。
> **Tier**：**③a Studio HTTP 适配壳**。`routers/llm.py`/`routers/copilot.py` = Studio 把 HTTP 输入翻译成 service/gateway 调用的适配层（消费方），**不是 ③b gateway 公共内核**。判据：HTTP 端点形状、job/进度包装、DTO 投影绑死了"这个 app 的调用方式 + 存储介质"，换个 app 不会复用同一套 router → ③a 应用加工。
> **Owns**：HTTP 端点族（registry CRUD / endpoint·model·role test / import draft / model profile / capability projection / 官方 provider 探测 / Copilot ws+test）的协议适配 + DTO 投影 + job 包装；**底下调的 service 多数是 ③b 公共能力内核（待下沉）**。
> **Status**：设计定稿；代码 = `routers/llm.py` 约 4960 行巨型 router，MVP1 标注每端点 delegate 去向 + 登记拆分待办，**本轮不动代码**。
> **⚠️ 内核 vs 适配壳**：文档内凡出现 **base_url 归一化 / capability 归一化·对比 / probe 策略（批批打·命中停·结构错短路）/ materialize 编排 / 6 态标准总结 / draft 知识库 / endpoint 标准化拆分** 的逻辑，其**能力内核属 ③b 公共（现散 ③a 待下沉）**；router 自身**仅 HTTP glue**（解析 DTO + 状态码映射 + 调 service + job/进度包装 + 落存储）。判据权威源：`packages/graph-agent-gateway/README.md` §2 + ux-spec §6.1 逐操作归属表（A1–A12）。
> **Related**：[[02-orch-role-resolution]]（materialize/`resolve_role` 内核，router 的 `_role_effective_runtime_settings`/`_materialize_roles_for_response` 调它）· [[03-orch-credentials-endpoints]]（base_url 归一化 + endpoint 拆分内核，`put_registry_endpoints` 调它）· [[05-orch-capabilities-and-models]]（capability/profile/lint 内核，probe 端点调它）· [[07-orch-fallback-circuit-probe]]（route probe + 熔断 health store）· [[08-orch-test-status-ssot]]（6 态投影 + draft 知识库）· [[copilot-assist]]（Copilot ws/test 端点 delegate 去向）
> **决策日志**：client 层 A' 重设计决策（**完整逻辑 + 用户原话见本文 §4/§5，本模块留底**）—— D3（gateway 可复用、前端不归 gateway、router = studio 适配器非 gateway 核心）+ F1（base_url 保存时归一化，见本文 §5 第 2 条）；归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md` 行 47（14 routers = ③a 应用/薄壳适配）+ ux-spec §6.1/§6.3。**D3 跨模块共享**，另见 [[copilot-assist]]（copilot SDK 调用据 D3 判 ③a）；**F1 共享决策**权威源 [[03-orch-credentials-endpoints]]。
> **现状**：见同目录 `baseline.md`

> **D3 — Gateway = 可复用服务，前端不归 gateway，router = studio 适配器非核心**（client 层 A' 重设计决策，本文留底）。**决策**：gateway 只提供服务（编排 + 调用），**不含任何前端**；前端是 **studio 的前端**，studio 只是 gateway 的一个消费方；gateway 必须设计清晰对外 API 供其他 app 复用。**含义（本模块的直接依据）**：`routers/llm.py`、`routers/copilot.py` = studio 的 HTTP 适配器（消费方），**非 gateway 核心**；而 `apps/studio/backend/app/services/llm_*`（动脑 services）= **应迁入 gateway 包**。用户原话：
> > "前端不归gateway管, 前端是studio的前端, gateway只管提供服务, 所以模块功能分个清楚, API怎么提供要写清楚, 要考虑复用其他app"
> → 故本模块定性为薄适配壳、能力内核下沉。D3 是跨模块共享决策，另见 [[copilot-assist]]（copilot SDK 调用同据 D3 判 ③a）。

> **判据铁律（ux-spec §6.0 第四轮反转）**："换个 app 还原样能用吗？能=③b 公共，不能（绑死那四件事之一）=③a。" → HTTP 端点形状、job/进度包装绑死了 studio 的调用方式 → router 留 ③a；但端点底下的 base_url 归一化 / capability / probe 策略 / materialize / 6 态 / draft 内核 = ③b 公共，应下沉。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| LLM_COPILOT_HTTP_API-1 | router 边界 | 单元 `settings-six-state-provider-health`（③a HTTP 壳消费）；**为什么**：router 只做 DTO/状态码/job 包装，内核 delegate ③b |
| LLM_COPILOT_HTTP_API-2 | Copilot SDK test | 单元 `copilot-sdk-test-parity`；**为什么**：test 端点走真实 `ClaudeSDKClient` smoke，非 AsyncAnthropic |
| LLM_COPILOT_HTTP_API-3 | DTO SSOT | 单元 `model-group-role-materialization`；**为什么**：DTO 字段链接 gateway registry schema，不复制第二份真理 |

## 6. 测试关键点
1. router 边界: baseline 现状为 `llm.py` 混 API/service/probe/projection/job store ⚠️；目标为 router 只保留 DTO/status/job 包装，内核 delegate 到 ③b/③a service。
2. Copilot SDK test: baseline 现状为 `_probe_copilot_sdk_tool_call` 走 `AsyncAnthropic` ⚠️；目标为 test 端点走真实 `ClaudeSDKClient` smoke。
3. DTO SSOT: baseline 现状为 端点文档可能复制 gateway schema；目标为 DTO 字段链接 gateway registry schema，不复制第二份真理。

## 7. 涉及 region / platform
`gateway` · `studio-settings` · `settings` · `copilot-assist` · `docs/graph-agent-gateway/mvp1/`

## 8. gaps / 报警
- 🚨 router 边界: `llm.py` 混 API/service/probe/projection/job store ⚠️；目标 router 只保留 DTO/status/job 包装，内核 delegate 到 ③b/③a service。
- 🚨 Copilot SDK test: `_probe_copilot_sdk_tool_call` 走 `AsyncAnthropic` ⚠️；目标 test 端点走真实 `ClaudeSDKClient` smoke。

> 旧迁移附录暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#04-platform-llm-copilot-http-api)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `gateway` · `studio-settings` · `settings` · `copilot-assist` · `docs/graph-agent-gateway/mvp1/`
