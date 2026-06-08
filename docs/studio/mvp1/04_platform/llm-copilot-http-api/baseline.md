---
module: 04_platform/llm-copilot-http-api
doc: baseline
status: verified（WS-5 更新后现状；`routers/llm.py` 中 Copilot SDK test 已对接真实 ClaudeSDKClient。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/routers/llm.py:router · apps/studio/backend/app/routers/llm.py:get_llm_registry · apps/studio/backend/app/routers/llm.py:_probe_copilot_sdk_tool_call · apps/studio/backend/app/routers/copilot.py:copilot_ws · apps/studio/backend/app/routers/copilot.py:test_copilot_role_sdk
units: [settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity]
---

# llm-copilot-http-api — Baseline（当下代码实现逻辑）

> **Scope**: Studio ③a LLM/Copilot HTTP 适配壳：registry/endpoint/model/role/import/model-profile/Copilot WS+test 的端点形状、DTO 投影与 job 包装。
> **现状一句话**: `routers/llm.py` 中 Copilot SDK test 端点已完整对接 `ClaudeSDKClient` 并集成每会话独立的环境变量与工具探测逻辑。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
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
| `test_llm_role/start_role_test_job/get_role_test_job` (`routers/llm.py:996-1037`) | role test 端点把 role 配置中的 model-group provider candidates 展开成 targets；`failed/off` 返回 blocked 且不探测，第三方 hard failure 写回 route metadata 与 probe-failed evidence。 |
| `get_model_profiles/put_model_profiles/delete_model_profile/apply_model_profile` (`routers/llm.py:1222-1280`) | model profile 端点维护可复用 route bundle,并把 profile snapshot 应用到 role。 |
| `_registry_response` (`routers/llm.py:1336`) | `_registry_response` 把 credentials 与 roles join 成前端 registry DTO，并分开暴露 availability `ui_state` 与 capability evidence `unknown/callable_only/partial/known`。 |
| `_force_probe_route` (`routers/llm.py:1818`) | `_force_probe_route` 对单 route 发真实模型 probe,成功清 circuit,网络类失败写 health circuit。 |
| `_role_test_provider_result` (`routers/llm.py:1889`) | `_role_test_provider_result` 计算单 route 在 role test 中的 admission、probe 和状态回写；第三方 probe 失败会更新 route/evidence，临时网络类失败走 health circuit。 |
| `_probe_copilot_sdk_tool_call` (`routers/llm.py:2150`) | `_probe_copilot_sdk_tool_call` 现状用 `AsyncAnthropic` 做 Copilot tool-call 验证,与真实 Copilot SDK 运行路径不一致。 |
| `_probe_role_route` (`routers/llm.py:2662`) | `_probe_role_route` 根据 verified profile 或 third-party probe 后端测试一条 role route。 |
| `_role_test_entries` (`routers/llm.py`) | `_role_test_entries` 合并 materialization report 与 role model_groups，确保 Role Test 覆盖所有配置候选，而不是只测已进入 fallback_chain 的 route。 |
| `_capability_state/_capability_summary` (`routers/llm.py`) | `_capability_state/_capability_summary` 暴露 `unknown/callable_only/partial/known` 能力证据完整度，并汇总 thinking/tools/structured-output 支持状态。 |
| `_probe_official_model_profile_result` (`routers/llm.py:2735`) | `_probe_official_model_profile_result` 对官方模型尝试多种调用方法,产出 `VerifiedProfile` 列表。 |
| `_upsert_discovered_routes` (`routers/llm.py:4381`) | `_upsert_discovered_routes` 把 models-list/probe 发现的模型写成 `ProviderRoute`。 |
| `_role_effective_runtime_settings` (`routers/llm.py:4588`) | `_role_effective_runtime_settings` 调 registry resolver 计算每个 role-route 的有效 runtime settings。 |
| `_materialize_roles_for_response` (`routers/llm.py:4613`) | `_materialize_roles_for_response` 把 model_groups 或 copilot role 展开成前端可直接展示的 route fallback_chain。 |
| `apps/studio/backend/app/routers/copilot.py:router` (`:18`) | Copilot router 是 `/api/skills/.../copilot` 与 `/api/copilot/...` 的入口集合。 |
| `dispatch_copilot` (`routers/copilot.py:23`) | `dispatch_copilot` 保留旧 dispatch scaffold,当前直接 501。 |
| `copilot_ws` (`routers/copilot.py:34`) | `copilot_ws` 通过 websocket 调 `stream_query` 并把 Copilot event 发回前端。 |
| `post_copilot_context` (`routers/copilot.py:58`) | `post_copilot_context` 缓存 Studio view context,不触发模型调用。 |
| `test_copilot_role_sdk` (`routers/copilot.py:89`) | `test_copilot_role_sdk` 对 Copilot role targets 发 tool-call 测试。 |

## 前端逻辑
N/A。

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
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
| `test_llm_role/start_role_test_job/get_role_test_job` (`routers/llm.py:996-1037`) | role test 端点把 role 配置中的 model-group provider candidates 展开成 targets；`failed/off` 返回 blocked 且不探测，第三方 hard failure 写回 route metadata 与 probe-failed evidence。 |
| `get_model_profiles/put_model_profiles/delete_model_profile/apply_model_profile` (`routers/llm.py:1222-1280`) | model profile 端点维护可复用 route bundle,并把 profile snapshot 应用到 role。 |
| `_registry_response` (`routers/llm.py:1336`) | `_registry_response` 把 credentials 与 roles join 成前端 registry DTO，并分开暴露 availability `ui_state` 与 capability evidence `unknown/callable_only/partial/known`。 |
| `_force_probe_route` (`routers/llm.py:1818`) | `_force_probe_route` 对单 route 发真实模型 probe,成功清 circuit,网络类失败写 health circuit。 |
| `_role_test_provider_result` (`routers/llm.py:1889`) | `_role_test_provider_result` 计算单 route 在 role test 中的 admission、probe 和状态回写；第三方 probe 失败会更新 route/evidence，临时网络类失败走 health circuit。 |
| `_probe_copilot_sdk_tool_call` (`routers/llm.py`) | `_probe_copilot_sdk_tool_call` 已修改为使用真实 `ClaudeSDKClient` + per-session 环境变量注入，并实际执行工具调用探测。 |
| `_probe_role_route` (`routers/llm.py:2662`) | `_probe_role_route` 根据 verified profile 或 third-party probe 后端测试一条 role route。 |
| `_role_test_entries` (`routers/llm.py`) | `_role_test_entries` 合并 materialization report 与 role model_groups，确保 Role Test 覆盖所有配置候选，而不是只测已进入 fallback_chain 的 route。 |
| `_capability_state/_capability_summary` (`routers/llm.py`) | `_capability_state/_capability_summary` 暴露 `unknown/callable_only/partial/known` 能力证据完整度，并汇总 thinking/tools/structured-output 支持状态。 |
| `_probe_official_model_profile_result` (`routers/llm.py:2735`) | `_probe_official_model_profile_result` 对官方模型尝试多种调用方法,产出 `VerifiedProfile` 列表。 |
| `_upsert_discovered_routes` (`routers/llm.py:4381`) | `_upsert_discovered_routes` 把 models-list/probe 发现的模型写成 `ProviderRoute`。 |
| `_role_effective_runtime_settings` (`routers/llm.py:4588`) | `_role_effective_runtime_settings` 调 registry resolver 计算每个 role-route 的有效 runtime settings。 |
| `_materialize_roles_for_response` (`routers/llm.py:4613`) | `_materialize_roles_for_response` 把 model_groups 或 copilot role 展开成前端可直接展示的 route fallback_chain。 |
| `apps/studio/backend/app/routers/copilot.py:router` (`:18`) | Copilot router 是 `/api/skills/.../copilot` 与 `/api/copilot/...` 的入口集合。 |
| `dispatch_copilot` (`routers/copilot.py:23`) | `dispatch_copilot` 保留旧 dispatch scaffold,当前直接 501。 |
| `copilot_ws` (`routers/copilot.py:34`) | `copilot_ws` 通过 websocket 调 `stream_query` 并把 Copilot event 发回前端。 |
| `post_copilot_context` (`routers/copilot.py:58`) | `post_copilot_context` 缓存 Studio view context,不触发模型调用。 |
| `test_copilot_role_sdk` (`routers/copilot.py:89`) | `test_copilot_role_sdk` 对 Copilot role targets 发 tool-call 测试。 |

## 当前边界（llm-copilot-http-api 现在不是什么）
- 不拥有 gateway 公共内核：base_url/capability/probe/materialize/6 态/draft 只链接。
- 不拥有 copilot chat runtime；真实行为归 `copilot-assist`。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| router 边界 | `llm.py` 混 API/service/probe/projection/job store ⚠️ | router 只保留 DTO/status/job 包装，内核 delegate 到 ③b/③a service |
| Role Test persistence | Role Test 已覆盖全部配置候选，blocked skipped routes 可见，第三方失败写回 route/evidence 并可由 registry 投影。 | Role Test 最终状态来自 registry/evidence，而不是前端内存 |
| capability DTO | Registry 已分离 availability state 与 `unknown/callable_only/partial/known` capability state。 | DTO 字段链接 gateway registry schema，不复制第二份真理 |
| Copilot SDK test | `_probe_copilot_sdk_tool_call` 走真实 `ClaudeSDKClient` 并实际请求探测。 | test 端点走真实 `ClaudeSDKClient` smoke |
| DTO SSOT | 端点文档可能复制 gateway schema | DTO 字段链接 gateway registry schema，不复制第二份真理 |
> **验"是否按目标改了"**：1. router 边界；2. Role Test persistence；3. capability DTO；4. Copilot SDK test（已完成并对齐）；5. DTO SSOT。

## 读代码主路径提示
`apps/studio/backend/app/routers/llm.py:router` → `apps/studio/backend/app/routers/llm.py:get_llm_registry` → `apps/studio/backend/app/routers/llm.py:_probe_copilot_sdk_tool_call` → `apps/studio/backend/app/routers/copilot.py:copilot_ws` → `apps/studio/backend/app/routers/copilot.py:test_copilot_role_sdk`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#04-platform-llm-copilot-http-api)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `gateway` · `studio-settings` · `settings` · `copilot-assist` · `docs/graph-agent-gateway/mvp1/`
