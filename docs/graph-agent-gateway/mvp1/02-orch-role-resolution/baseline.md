---
module: 02-orch-role-resolution
doc: baseline
status: drafted
---

# 02-orch-role-resolution — Baseline(现状)

本文只描述当前源码。核心结论:Studio 已经能把 Role authoring 投影成 `fallback_chain`,但 runtime 解析仍会在链上第一个坏 route 处直接抛错,尚未恢复“逐条跳过 + 空链再报错”的语义。

## 覆盖代码(含覆盖率)

覆盖率:4/4 个 brief 指定目标已覆盖,100%。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| `registry/resolver.py:resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链,不调用模型) | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33-132` | 覆盖 role→route、`route_override`、credential 检查、profile 选择、effective runtime settings、lint blocking。 |
| `resolver.py:ModelResolver`(用途:把 registry 解析结果包成 LangChain `GatewayChatModel` 或 predict mock model) | `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:41-184` | 覆盖 `model_override`、空链处理、predict 分支、手动 mark-down。 |
| `services/gateway_resolver.py:build_gateway_model_resolver`(用途:从 Studio v4 credentials + v2/v3 roles 构造 gateway resolver) | `apps/studio/backend/app/services/gateway_resolver.py:15-21` | 覆盖 Studio→Gateway 装配入口。 |
| `services/llm_role_materializer.py:materialize_role`(用途:把 Studio Role 的 model groups 投影成 gateway `fallback_chain`) | `apps/studio/backend/app/services/llm_role_materializer.py:27-96` | 覆盖 authoring 顺序、状态投影、跳过报告、runtime settings 写入。**判据归属:意图过滤/降级/排链/role-fit 诊断 = ③b 编排内核(现散 ③a 待下沉),report 渲染留 ③a;详见 `mvp1-alignment.md`。** |

辅助证据:`test_gateway_resolver_bridge_builds_snapshot_without_env_patch`(用途:验证 Studio 文件数据能构造 gateway resolver)见 `apps/studio/backend/tests/services/test_gateway_resolver_bridge.py:19-70`;`test_put_role_v3_skips_needs_setup_and_off_provider_models`(用途:验证 materializer 会跳过未配置/关闭模型)见 `apps/studio/backend/tests/routers/test_llm_role_materializer_api.py:91-142`。

## 编号执行流程

1. `materialize_role`(用途:把 Studio Role authoring 投影成 gateway fallback chain)先决定要看哪些 model group:开启 fallback 时用全部 `role.model_groups`,否则只用第一个 group,见 `apps/studio/backend/app/services/llm_role_materializer.py:39`。

2. `_ordered_provider_models`(用途:返回一个 group 里的 provider model 顺序)当前只是 `list(group.provider_models)`,所以 fallback 链排序来自用户保存的手动顺序,没有 ready-first 或价格/能力重排,见 `apps/studio/backend/app/services/llm_role_materializer.py:40-42`、`apps/studio/backend/app/services/llm_role_materializer.py:125-128`。

3. `materialize_role`(用途:把 Studio Role authoring 投影成 gateway fallback chain)会跳过找不到 route、找不到 endpoint、拿不到状态投影的 provider model,但这些分支当前是 silent continue,不写入 warning/report,见 `apps/studio/backend/app/services/llm_role_materializer.py:42-50`。

4. `_projection`(用途:把 route + endpoint + durable circuit 转成 UI/runtime 状态投影)读取健康库的 active circuits,再调用 `project_provider_model_state` 生成 `ready/untested/cooling_down/needs_setup/off` 等状态,见 `apps/studio/backend/app/services/llm_role_materializer.py:131-154`。

5. `materialize_role`(用途:把 Studio Role authoring 投影成 gateway fallback chain)遇到 `needs_setup` 或 `off` 会把 route 写进 `skipped_provider_details`,并继续看下一条,见 `apps/studio/backend/app/services/llm_role_materializer.py:51-59`;这条行为被 `test_put_role_v3_skips_needs_setup_and_off_provider_models` 覆盖,见 `apps/studio/backend/tests/routers/test_llm_role_materializer_api.py:131-142`。

6. `_apply_intent`(用途:按 Role/Model Group 的 thinking 与 token 意图决定 route 是否适合执行)会在 thinking required 但能力未知时返回 `needs_test`,在 thinking unsupported 或 token block 时返回 `not_fit`,见 `apps/studio/backend/app/services/llm_role_materializer.py:157-208`。

7. `_apply_output_token_intent`(用途:把用户的输出 token 意图转成 `max_output_tokens` 或 warning)会从 route capability 的 `max_output_tokens.value.max` 取上限,超出且 `downgrade=block` 时让该 route 不进入链,见 `apps/studio/backend/app/services/llm_role_materializer.py:226-269`。

8. `materialize_role`(用途:把 Studio Role authoring 投影成 gateway fallback chain)只把 `role_fit` 不属于 `needs_test/not_fit` 的 route 追加进 `fallback_chain`,并把 `resolved_settings` 写成 `RoleRouteEntry.runtime_settings`,见 `apps/studio/backend/app/services/llm_role_materializer.py:82-90`。

9. `build_gateway_model_resolver`(用途:从 Studio v4 credentials + v2/v3 roles 构造 gateway resolver)读取 active credentials,再读取 roles 文件或空 `RolesData`,最后用 `roles.to_registry_snapshot(credentials)` 生成 `ModelResolver`,见 `apps/studio/backend/app/services/gateway_resolver.py:18-21`。

10. `ModelResolver.__init__`(用途:保存 registry snapshot 并准备 credential provider)要求调用方给 `registry_snapshot` 或显式 credentials/roles 路径;如果给 snapshot,会用 endpoint credentials provider 包一层 fallback credential provider,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:44-69`。

11. `ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)当前不接受 `role_name=None`;没传 role 会直接抛 `GatewayRoleNotConfiguredError`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:73-91`。

12. `ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)把 `model_override` 原样传给 `resolve_role` 的 `route_override`,所以当前 override 实际是精确 `route_id` override,不是旧模型短码 override,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:92-98`。

13. `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链)先按 role 名取 `snapshot.roles[role_name]`;role 不存在时抛 `RegistryResolutionError`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:41-43`。

14. `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链)有 `route_override` 时只构造单条 `RoleRouteEntry`,否则按 `role.fallback_chain` 原顺序遍历,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:45-55`。

15. `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链)当前遇到 route 不存在、route status 不是 `verified/unverified_manual`、endpoint 不存在、endpoint 没有 credential 时都会立刻抛 `RegistryResolutionError`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56-71`。

16. `select_verified_profile`(用途:选择一个 route 上已验证的调用 profile)失败时会让 `resolve_role` 抛 `RegistryResolutionError`,成功时把 profile id/capability/method/mapper 写入 `ResolvedRoute`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:72-113`。

17. `_effective_runtime_settings`(用途:把 route entry 的用户设置、route capability 默认值、protocol 默认值合成最终 runtime settings)会给 temperature、max output tokens、reasoning 等字段打 source,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:156-270`。

18. `lint_role_routes`(用途:对 role 的 route 链做 capability lint)在所有 route 已解析后运行;blocking lint 会让 `resolve_role` 抛 `RegistryResolutionError`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116-122`。

19. `ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)把 `RegistryResolutionError` 统一映射成 `GatewayRoleNotConfiguredError`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:99-103`。

20. `ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)如果拿到的 `ResolvedRole.routes` 为空,当前会抛 `AllProvidersFailedError`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:104-109`;`_resolve_copilot_runtime` 也有自己的空链保护,见 `apps/studio/backend/app/services/copilot.py:429-437`。

21. `ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)用第一条 route 的 effective `max_output_tokens/temperature/reasoning.enabled` 决定模型构造参数,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:111-118`。

22. `ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)有 `predict_context` 时返回 `PredictGatewayChatModel`,否则返回 `GatewayChatModel`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:119-146`。

## Baseline / Alignment 差异

当前 baseline 已有两段跳过语义:authoring materialize 会跳过 `needs_setup/off` 并报告,见 `apps/studio/backend/app/services/llm_role_materializer.py:51-59`;Copilot 调用时某条 route 缺 key 可以继续下一条,见 `apps/studio/backend/app/services/copilot.py:221-238`。但 runtime 核心 `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链)仍是“第一个坏 entry 直接抛”,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56-71`。

目标 alignment 应把跳过语义下沉到 `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链),并把“过滤后空链”作为结构化配置错误,而不是让 `ModelResolver.resolve` 后置抛 `AllProvidersFailedError`;MVP1 README 已把这点列为 `02-orch-role-resolution` 的要求,见 `docs/graph-agent-gateway/mvp1/README.md:27`。

## 决策原因

保留手动顺序,是因为当前 Role authoring 的 provider preference 已迁移为 `manual_order`,测试也要求不重排,见 `apps/studio/backend/tests/routers/test_llm_role_materializer_api.py:145-193`。

不让 capability/price/latency 动态选型,是因为 MVP1 README 把编排定义为 role→route 的确定性解析,交接物是 `ResolvedRoute/ResolvedRole`,见 `docs/graph-agent-gateway/mvp1/README.md:13-18`。

当前把 `model_override` 解释成 `route_override`,是为了让 override 指向精确可执行 route,避免旧“模型名”在多 provider 下变成模糊匹配;证据是 `ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)的传参,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:92-98`。

需要修复 runtime 跳过语义,是因为 save 解耦后 role 可以引用暂未配置或暂不可执行 route;如果 `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链)继续在第一条坏 route 处抛错,后面的可用 route 永远没有机会执行,见当前抛错点 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56-71`。

## 代码索引(clues)

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:26`: `EXECUTABLE_ROUTE_STATUSES`(用途:定义解析期可执行 route status 集合)只允许 `verified/unverified_manual`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33-132`: `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链)是 runtime role→route 的核心。
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:73-146`: `ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)是 Engine 调用的现有入口。
- `apps/studio/backend/app/services/gateway_resolver.py:15-21`: `build_gateway_model_resolver`(用途:从 Studio v4 credentials + v2/v3 roles 构造 gateway resolver)是 Studio backend 接入点。
- `apps/studio/backend/app/services/llm_role_materializer.py:27-96`: `materialize_role`(用途:把 Studio Role authoring 投影成 gateway fallback chain)是 authoring→runtime chain 的投影入口。
- `apps/studio/backend/app/services/copilot.py:419-437`: `_resolve_copilot_runtime`(用途:解析 `copilot_chat` role 并返回 routes + credential provider)已经把 role→route 用作 Copilot 内部交接。

## 待办/疑点

1. 待办:把 `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链)从“坏 entry 直接抛”改为“未配置/不可执行/缺凭证逐条 warning + continue;过滤后空链再抛”,当前回归点在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56-71`。

2. 待办:为 `resolve_role`(用途:把一个 role 展开成有序 `ResolvedRoute` 链)补充 skipped diagnostics,否则 Studio/trace 只能看到最终失败,看不到哪些 route 被跳过;当前 `ResolvedRole` 没有 skipped 字段,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-459`。

3. 疑点:`materialize_role`(用途:把 Studio Role authoring 投影成 gateway fallback chain)对 route/endpoint/projection missing 是 silent continue,见 `apps/studio/backend/app/services/llm_role_materializer.py:42-50`;是否也应进入 `skipped_provider_details`,需要产品判断。

4. 疑点:`ModelResolver.resolve`(用途:把 role/model override 解析成 LangChain chat model)空链当前抛 `AllProvidersFailedError`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:104-109`;MVP1 更合理的是配置错误,但要确认对 Engine 错误码/HTTP 映射的影响。
