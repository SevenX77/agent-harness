---
module: 14-api-router
doc: baseline
status: drafted
---

# 14-api-router — Baseline(现状)

> 本文只描述当前源码（按 endpoint 家族）；目标设计见同目录 `mvp1-alignment.md`。
> **判据归属**：`routers/llm.py`/`routers/copilot.py` = **③a Studio HTTP 适配壳，非 gateway 核心模块**（`module-disposition-revised.md` 行 47 + 决策记录 D3 `:73`）。判据：HTTP 端点形状、job/进度包装、DTO 投影绑死 studio 的调用方式 + 存储介质 → ③a。
> **⚠️ 内核 vs 适配壳标注**：下文现状里凡 **base_url 归一化 / capability 归一化·对比 / probe 策略（批批打·命中停·结构错短路）/ materialize 编排 / 6 态标准总结 / draft 知识库 / endpoint 标准化拆分** 的逻辑——其**能力内核按判据属 ③b 公共（现散 ③a `apps/studio/backend/app/services/llm_*` 或内联 router，待下沉 gateway 包）**；router 自身**仅应保留 HTTP glue**（DTO 解析 + 状态码 + 调 service + job/进度/HTTP 包装 + 落存储）。下沉清单见 `module-disposition-revised.md` §2。

本模块解释 Studio 后端暴露给前端的 LLM/Copilot HTTP 面。`apps/studio/backend/app/routers/llm.py` 约 4960 行,现状把 registry CRUD、endpoint/model/role test、import draft、model profile、capability projection、官方 provider 探测和若干内部投影 helper 放在一个巨型 router 里。本文按 endpoint 家族讲清楚,不逐行复述。

## 覆盖代码(含覆盖率)

覆盖率:100%。manifest 要求的 `routers/llm.py` 与 `routers/copilot.py` 已覆盖;由于 `routers/llm.py` 超过 400 行,本文按家族索引,并在“待办/疑点”中记录后续拆分计划。

| 覆盖项 | 说明 |
|---|---|
| `apps/studio/backend/app/routers/llm.py:router` (`:127`) | `router` 是 `/api/llm` 前缀下所有 LLM registry API 的 FastAPI 路由器。 |
| `OfficialLanguageProbeCandidate` (`routers/llm.py:146`) | `OfficialLanguageProbeCandidate` 描述官方 provider 某个模型可尝试的调用方法、能力标签、runtime settings 和排序。 |
| `OfficialModelProfileProbeResult` (`routers/llm.py:160`) | `OfficialModelProfileProbeResult` 保存官方模型探测后得到的 verified profiles、失败消息和 probe attempts。 |
| `RoleTestTarget` (`routers/llm.py:168`) | `RoleTestTarget` 是 role test 时的一条具体 route+endpoint+role entry 组合。 |
| `EndpointTestJobResponse` (`routers/llm.py:187`) | `EndpointTestJobResponse` 是官方 endpoint 批量测试 job 的进度 DTO。 |
| `RoleTestJobResponse` (`routers/llm.py:218`) | `RoleTestJobResponse` 是 role test job 的进度 DTO,包含每条 route 的 compact status。 |
| `get_llm_registry` (`routers/llm.py:312`) | `get_llm_registry` 返回红acted endpoint/route/role registry,并附带 model groups、lint、runtime settings 投影。 |
| `put_registry_endpoints` (`routers/llm.py:334`) | `put_registry_endpoints` upsert endpoints,缺席的 endpoint 不删除。 |
| `delete_registry_endpoint` (`routers/llm.py:346`) | `delete_registry_endpoint` 删除 endpoint,并清理 roles 中引用该 endpoint 下 routes 的条目。 |
| `start_endpoint_test_job` (`routers/llm.py:363`) | `start_endpoint_test_job` 为 official provider 启动异步批量测试 job。 |
| `test_endpoint` (`routers/llm.py:460`) | `test_endpoint` 对 endpoint 做最小 models-list 连通性测试,发现模型后 upsert routes。 |
| `test_endpoint_models` (`routers/llm.py:581`) | `test_endpoint_models` 对指定模型 ID 做 probe,成功后 upsert verified routes。 |
| `probe_route` (`routers/llm.py:782`) | `probe_route` 标记/强制探测单条 route,写入 capability 与 runtime settings 元数据。 |
| `post_import_draft/get_import_draft/probe_import_draft/apply_import_draft` (`routers/llm.py:856-880`) | import draft 端点处理外部发现的 endpoint/route candidates,再显式 apply 到 active credentials。 |
| `get_llm_roles/put_llm_roles/get_llm_role/put_llm_role/delete_llm_role` (`routers/llm.py:899-984`) | role CRUD 端点读写 route-backed roles。 |
| `test_llm_role/start_role_test_job/get_role_test_job` (`routers/llm.py:996-1037`) | role test 端点把 role fallback_chain 展开成 targets 并探测。 |
| `get_model_profiles/put_model_profiles/delete_model_profile/apply_model_profile` (`routers/llm.py:1222-1280`) | model profile 端点维护可复用 route bundle,并把 profile snapshot 应用到 role。 |
| `_registry_response` (`routers/llm.py:1336`) | `_registry_response` 把 credentials 与 roles join 成前端 registry DTO。 |
| `_force_probe_route` (`routers/llm.py:1818`) | `_force_probe_route` 对单 route 发真实模型 probe,成功清 circuit,网络类失败写 health circuit。 |
| `_role_test_provider_result` (`routers/llm.py:1889`) | `_role_test_provider_result` 计算单 route 在 role test 中的 admission、probe 和状态回写。 |
| `_probe_copilot_sdk_tool_call` (`routers/llm.py:2150`) | `_probe_copilot_sdk_tool_call` 现状用 `AsyncAnthropic` 做 Copilot tool-call 验证,与真实 Copilot SDK 运行路径不一致。 |
| `_probe_role_route` (`routers/llm.py:2662`) | `_probe_role_route` 根据 verified profile 或 third-party probe 后端测试一条 role route。 |
| `_probe_official_model_profile_result` (`routers/llm.py:2735`) | `_probe_official_model_profile_result` 对官方模型尝试多种调用方法,产出 `VerifiedProfile` 列表。 |
| `_upsert_discovered_routes` (`routers/llm.py:4381`) | `_upsert_discovered_routes` 把 models-list/probe 发现的模型写成 `ProviderRoute`。 |
| `_role_effective_runtime_settings` (`routers/llm.py:4588`) | `_role_effective_runtime_settings` 调 registry resolver 计算每个 role-route 的有效 runtime settings。 |
| `_materialize_roles_for_response` (`routers/llm.py:4613`) | `_materialize_roles_for_response` 把 model_groups 或 copilot role 展开成前端可直接展示的 route fallback_chain。 |
| `apps/studio/backend/app/routers/copilot.py:router` (`:18`) | Copilot router 是 `/api/skills/.../copilot` 与 `/api/copilot/...` 的入口集合。 |
| `dispatch_copilot` (`routers/copilot.py:23`) | `dispatch_copilot` 保留旧 dispatch scaffold,当前直接 501。 |
| `copilot_ws` (`routers/copilot.py:34`) | `copilot_ws` 通过 websocket 调 `stream_query` 并把 Copilot event 发回前端。 |
| `post_copilot_context` (`routers/copilot.py:58`) | `post_copilot_context` 缓存 Studio view context,不触发模型调用。 |
| `test_copilot_role_sdk` (`routers/copilot.py:89`) | `test_copilot_role_sdk` 对 Copilot role targets 发 tool-call 测试。 |

## 现状逻辑

### 1. Registry 读取与 endpoint CRUD

> **判据标注**：本族里 **canonical 分组、lint、effective runtime settings 计算、base_url 按 protocol 归一化、endpoint 标准化拆分** = ③b 公共能力内核（见 [[03-orch-credentials-endpoints]]/[[02-orch-role-resolution]]）；router 留 **join + DTO 投影 + upsert + 落存储 + 删除引用清理**。当前 `put_registry_endpoints` 直接 upsert、base_url 原样透传（头号根因），MVP1 应在保存路径经 ③b 内核归一化。

1. `get_llm_registry` 读取 credentials 与 roles,再调用 `_registry_response` 输出 `RegistryResponse` (`routers/llm.py:312-318`)。
2. `_registry_response` 会先规范化响应中的 credentials、materialize roles,再按 `canonical_id` 建 groups,对每个 role 调 `lint_role_routes`,并附带 route/runtime settings 投影 (`routers/llm.py:1336-1384`)。
3. `get_registry_endpoint_secret` 只给本地设置 UI 返回某个 endpoint 的 API key 明文,未知 endpoint 抛 404 (`routers/llm.py:321-330`)。
4. `put_registry_endpoints` 调 `upsert_endpoints`,只覆盖请求里出现的 endpoint,不把缺席 endpoint 当删除 (`routers/llm.py:334-343`)。
5. `delete_registry_endpoint` 删除 endpoint 前先计算引用,如果 endpoint 下有 routes 且 roles 文件存在,会从 roles 中移除这些 route 引用,再调用 `delete_endpoint` (`routers/llm.py:346-360`)。

### 2. endpoint/model/route 探测

> **判据标注**：本族里 **probe 策略（批量短路·命中停·结构错短路）、route probe（1-token 真请求）、capability 归一化、错误分类** = ③b 公共能力内核（现散 router 内联 + `services/llm_route_capabilities.py` 等待下沉，见 [[05-orch-capabilities-and-models]]/[[07-orch-fallback-circuit-probe]]）；router 留 **job/进度/HTTP 包装 + 落存储**。

1. `start_endpoint_test_job` 只允许 official endpoint,同一 endpoint 已有 queued/running job 时返回原 job,否则创建 job 并后台启动 `_run_official_endpoint_test_job` (`routers/llm.py:363-393`)。
2. `test_endpoint` 对 endpoint 发最小 models-list 请求;成功拿到模型时调用 `_upsert_discovered_routes`,并把 observation 追加进 evidence library (`routers/llm.py:460-574`)。
3. `test_endpoint_models` 对用户指定模型 ID 做 probe。official provider 会先产出 `VerifiedProfile`,third-party provider 则跑 `_probe_model`;成功后写 verified route,失败时更新 endpoint/route 状态和 evidence (`routers/llm.py:581-780`)。
4. `probe_route` 对单条 route 更新 capability 标记;带 `force=true` 时委托 `_force_probe_route` 发真实请求并处理 health circuit (`routers/llm.py:782-818`)。
5. `_force_probe_route` 在 missing key 时直接把 route 写成 failed;真实 probe 成功时写 verified 并 clear circuit;timeout/rate/network 类失败时打开 route circuit;其他失败写入 route metadata (`routers/llm.py:1818-1887`)。

### 3. import draft 与 evidence library

> **判据标注**：**draft 知识库内核（记录/复用/合并探测证据）** = ③b 公共（现 `services/llm_import_drafts.py` 待下沉，见 [[08-orch-test-status-ssot]]）；router 留 **import/apply 工作流 + 远端源选择**（现硬编码 GitHub repo，应改可配置）= ③a 应用加工。

1. `sync_catalog` 拉远端 evidence library 并合并到本地 (`routers/llm.py:397-412`)。
2. `share_catalog` 导出本地 verified probe evidence,用于社区共享 (`routers/llm.py:415-445`)。
3. `post_import_draft` 创建 draft,`get_import_draft` 读取 draft,`probe_import_draft` 只把 draft 标记为 probed,`apply_import_draft` 显式把 draft merge/apply 到 active credentials (`routers/llm.py:856-880`)。

### 4. role 与 model profile

> **判据标注**：**materialize（角色→fallback 链）、6 态投影、route probe** = ③b 公共内核（见 [[02-orch-role-resolution]]/[[08-orch-test-status-ssot]]/[[07-orch-fallback-circuit-probe]]）；router 留 **HTTP CRUD + job 包装 + Copilot/Graph Agent 分流保护**（分流认 `copilot_` 前缀 = ③a 产品策略，绑 copilot 语义，留 ③a service 不下沉 ③b）。

1. `get_llm_roles` 返回 `_materialize_roles_for_response` 后的 route-backed roles (`routers/llm.py:899-901`)。
2. `put_llm_roles` 有 Copilot/Graph Agent 分流保护:保存 Graph Agent roles 时保留现有 Copilot roles,保存 Copilot roles 时保留现有 Graph Agent roles (`routers/llm.py:909-952`)。
3. `put_llm_role` 单 role replace;如果 request 有 `model_groups`,先调用 `materialize_role` 展开为 route chain (`routers/llm.py:964-981`)。
4. `test_llm_role` 与 `start_role_test_job` 都先 materialize role,再由 `_role_test_targets` 把 fallback_chain 转成 route+endpoint targets (`routers/llm.py:996-1037`,`:1046-1068`)。
5. `_role_test_provider_result` 先通过 `_provider_model_projection` 得到 UI state,再根据 admission 决策决定 block/untested/probe;Copilot role 调 `_probe_copilot_sdk_tool_call`,普通 role 调 `_probe_role_route` (`routers/llm.py:1889-1959`)。
6. `get_model_profiles/put_model_profiles` 读写 profile map,`delete_model_profile` 删除 profile 并在仍引用它的 roles 上留下 deleted snapshot,`apply_model_profile` 把 profile 的 fallback_chain snapshot 写入 role (`routers/llm.py:1222-1309`)。

### 5. route 投影与内部 helper

> **判据标注**：本族里 **materialize（角色→fallback 链编排）、`resolve_role`（effective runtime settings）、canonical 分组、capability 合并** = ③b 公共能力内核（现散 `services/llm_role_materializer.py` / `services/llm_model_groups.py` / `services/llm_route_capabilities.py` 待下沉，见 [[02-orch-role-resolution]]/[[05-orch-capabilities-and-models]]）；router 留 **DTO 投影 + schema_version 包装**。其中 `_materialize_role_for_response` 对 Copilot role 的"找 canonical model + 扩展同模型组 route" = ③a 产品兼容逻辑（绑 copilot 语义），留 ③a。

1. `_upsert_discovered_routes` 根据 endpoint+model_id 生成 route_id,新 route 调 `_provider_route`,老 route 按 verified/profile/probe attempts 更新 capabilities 与 metadata (`routers/llm.py:4381-4477`)。
2. `_provider_route` 负责构造 `ProviderRoute`:route_id、endpoint_id、provider_model_id、canonical_id、status、capabilities、verified_profiles、metadata (`routers/llm.py:4480-4534`)。
3. `_role_effective_runtime_settings` 把 roles+credentials 转 registry snapshot,逐 role 调 `resolve_role`,把每条 resolved route 的 effective settings 暴露给前端 (`routers/llm.py:4588-4603`)。
4. `_materialize_roles_for_response` 对 Copilot role 做兼容 route 扩展,对 model_groups 角色调用 materializer,最后把 schema_version 提到 3 (`routers/llm.py:4613-4642`)。
5. `_materialize_role_for_response` 对部分 Copilot role 先找 canonical model,再用 `find_compatible_route_ids_for_model` 扩展同模型组 route (`routers/llm.py:4682-4723`)。

### 6. Copilot router

1. `dispatch_copilot` 是未实现旧入口,当前返回 501 (`routers/copilot.py:23-31`)。
2. `copilot_ws` 是真实 websocket 入口,收到请求后调 `app.services.copilot:stream_query` (`routers/copilot.py:34-55`)。
3. `post_copilot_context` 只更新 view context 缓存,用于后续 prompt 拼接 (`routers/copilot.py:58-86`)。
4. `test_copilot_role_sdk` 是 Copilot role 测试入口,但内部调用 LLM router 的 `_probe_copilot_sdk_tool_call` (`routers/copilot.py:89-126`)。

## 待办/疑点

- `apps/studio/backend/app/routers/llm.py` 已达约 4960 行,把 API handler、job store、probe 策略、projection、evidence、role materialize 都放在一个文件里;MVP1 后续应拆成 endpoint registry、probe jobs、role/profile、import drafts、projection helpers 等模块。
- `test_copilot_role_sdk` 的测试实现走 `AsyncAnthropic`,而真实 Copilot 走 `ClaudeSDKClient`;这个问题在 `12-inv-copilot-invocation` 里作为调用层目标修正。
- `put_llm_roles` 中 Copilot/Graph Agent 分流属于产品保护逻辑,但现在写在 router handler 内 (`routers/llm.py:909-952`),后续最好下沉到 service 层以便复用和测试。
