# PR alpha Gateway + LLM Roles Phase 1 Ship Report

一句话给 PM ack：PR alpha 已把 Gateway 从 Engine 运行面抽成独立包，并把 LLM Roles Phase 1 的 `temperature/max_tokens` 控制落到 model 槽位；本地 ship gate 已绿，后续 PR 不需要再补这层底座。

## §1 PR 目标 + scope

PR alpha 只交付两件事，和四件套 spec 一致。

第一，Gateway 抽 package。`requirements.md:12` 要求 `graph-agent` 与 `graph-agent-gateway` 物理分离，Engine 不再直接依赖 OpenAI/Anthropic 等 provider SDK，而是通过 DI 消费模型解析服务。`design.md:35-39` 进一步锁定：核心执行流显式接收 `model_resolver`，concrete resolver 留在 `graph-agent-gateway`。

第二，LLM Roles Phase 1 data 层。`requirements.md:14` 要求 role 的具体模型可以单独配置 `temperature/max_tokens`；`design.md:47-53` 要求顶层 `temperature` 废除并迁移到 `RoleModelEntry`。

明确不在 alpha 做的内容见 `tasks.md:21-28`：不做 γ0 契约补丁、不做 PR beta middleware、不做 γ1 compile-schema、不做 γ1.5 preflight、不做 γ2 state-io、不做 γ3 cleanup、不做 LLM Roles Phase 2-5 UI。

## §2 src 改动字段级清单

`packages/graph-agent-gateway/src/graph_agent_gateway/__init__.py:5-20`: 公开导出 Gateway 六个稳定入口。WHY 是让 Engine/Studio 只依赖包门面；WHAT 是导出三类异常、`GatewayChatModel`、`ModelResolver`、`ModelResolverProtocol`；HOW 是通过 `__all__` 锁定可见 API。

`packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:10-24`: 新增 `ModelResolverProtocol.resolve`。字段包括 `role_name`、`thinking_enabled`、`model_override`、`callbacks`、`phase_name`、`**kwargs`，返回 `BaseChatModel`。WHY 是把 Engine 从 concrete resolver 和 provider SDK 中剥离；HOW 是 Engine 只调用协议，不创建 resolver 单例。

`packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:10-21`: `ModelEntry` 定义模型注册项。`name/reasoning/min_max_tokens/max_input_tokens/fc_supported/providers/provider_options` 分别表达模型名、推理能力、输出默认、输入上限、函数调用能力、provider 映射和 provider 专属参数。WHY 是把模型能力从运行代码移到数据结构。

`packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:24-38`: `ProviderEntry` 定义 provider 注册项。`api_key_env/api_key_env_fallback/base_url/llm_base_url/proxy_env/timeout/trust_env/retry_strategy` 都是 provider client 构造所需字段。WHY 是 provider 细节留在 Gateway，不进入 Engine phase。

`packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:41-48`: `RoleModelEntry` 是 PR alpha 的 LLM Roles 核心落点。`providers` 决定 provider 尝试顺序，`temperature` 和 `max_tokens` 是 model 槽位级参数。WHY 是同一个 role 的不同 fallback model 不应共享一组生成参数。

`packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:51-61`: `RoleEntry` 表达 role 本体。`active_model` 是首选模型，`model_fallback` 控制 fallback，`system_prompt_prefix` 是 role 级提示，`models` 是 model 槽位表。当前 `temperature/max_tokens` 仍可读取，用于迁移期兜底，但保存路径会移除顶层旧字段。

`packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:64-74`: `RolesData` 汇总 `models/providers/roles` 三张主表，并保留 `single_model_roles/peer_model_groups/circuit_breaker`。WHY 是 resolver 一次拿到完整配置树。

`packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py:77-132`: `ModelDef/ProviderDef/ResolvedProvider/ResolvedRole` 是运行时归一化结构。它们把 YAML key 复制进 `code/provider_code/role_name`，把 `None` 默认归一成运行时默认值，最后形成 `call_chain`。

`packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:13-27`: `GatewayError` 统一 code/context 序列化。WHY 是 Studio 不再解析自由文本；HOW 是错误字符串带 code，机器字段放进 `context`。

`packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:30-57`: `AllProvidersFailedError` 固定 `[F-v3-gateway-all-providers-failed]`。payload 字段是 `role_name`、`phase_name`、`failed_provider_codes`、`last_error_chain` 和附加 context。

`packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:60-71`: `GatewayResolverMissingError` 固定 `[F-v3-gateway-resolver-missing]`。payload 字段是 `phase_name` 和 `required_dependency: model_resolver`。WHY 是 DI 缺失要与 provider 调用失败分开。

`packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:74-91`: `GatewayRoleNotConfiguredError` 固定 `[F-v3-gateway-role-not-configured]`。payload 字段是 `role_name` 和 `model_override`。WHY 是 role 未注册、override 未命中、映射缺失都属于配置错误。

`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:28-32`: `ModelResolverStats.total_resolves` 记录 resolve 调用数。

`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:35-48`: `ModelResolver.__init__` 接收 `roles_data` 和 `client_manager`。未传 roles 时读默认 YAML；client manager 可由测试或 Studio 注入。

`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:49-98`: `resolve` 递增统计，调用 `_resolve_role`，根据 predict mock 钩子返回 `PredictGatewayChatModel` 或普通 `GatewayChatModel`。传给 model 的字段包括 `max_tokens/temperature/callbacks/phase_name/thinking_enabled/client_manager/name`。

`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:100-205`: `_resolve_role` 执行 role 解析。它按 `role_name -> GRAPH_AGENT_DEFAULT_ROLE -> balanced` 找角色；按 `model_override` 或 `active_model` 决定首选模型；按 `model_fallback` 和 `single_model_roles` 扩展候选；按 `RoleModelEntry.temperature/max_tokens` 优先读取生成参数，最后构造 `ResolvedRole.call_chain`。

`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:207-218`: `mark_provider_down` 手动标记 provider down，兼容新旧 client manager 接口。

`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:220-242`: `_load_default_roles_data`、`_default_client_manager`、`_provider_max_tokens` 分别负责默认配置读取、默认 manager 延迟导入、provider option token 上限读取。

`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:29-45`: `GatewayChatModel` 字段包括 `role_name/resolved_role/max_tokens/temperature/phase_name/event_callbacks/probe_before_call/thinking_enabled/bound_tools/tool_choice/tool_kwargs/client_manager`。WHY 是一个 LangChain model 实例必须携带完整 fallback 链、生成参数、trace 通道和 provider 调度器。

`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:47-78`: `__init__` 把 callbacks、bound tools、tool kwargs 归一成 tuple/dict，保证 Pydantic model 状态稳定。

`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:80-90`: `_llm_type` 和 `_identifying_params` 给 LangChain/trace 暴露模型身份，包括 role、active model、candidate 链。

`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:92-159`: `_generate` 是 fallback 主循环。它把 message 转 dict，跳过 marked-down provider，probe 失败就 mark down，dispatch 成功就构造 `ChatResult`，dispatch 失败就记录 failure、mark down、发 `LLMFallbackEvent`，全部失败后抛 `AllProvidersFailedError`。

`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:161-192`: `bind_tools` 返回带工具的新 `GatewayChatModel`，不污染原实例。HOW 是复制 role、fallback、callbacks、client manager 和 LangChain 元数据，只替换工具字段。

`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:194-233`: `_build_chat_result` 和 `_next_candidate_id` 把 provider response 翻成 LangChain 输出，并给 fallback trace 找下一个候选。

`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:236-444`: helper 函数覆盖 candidate id、默认 manager、probe/dispatch/mark_down 兼容层、usage 解析、kwarg 类型校验、message/tool 转换、usage 补记。WHY 是把 provider manager 新旧接口差异集中在 Gateway 内。

`packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:13-30`: `build_llm_fallback_event` 复用 `graph_agent.callbacks.events.LLMFallbackEvent`，字段是 `phase_name/from_provider/to_provider/reason/code/context`。

`packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:33-59`: `emit_llm_fallback_event` 遍历 callbacks 调 `on_event`，callback 自身失败只写日志。WHY 是 tracing 失败不能遮盖 provider 失败。

`packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:15-40`: `PredictGatewayChatModel` 继承 `GatewayChatModel`，保存 `mock_strategy`，`_generate` 返回固定 `predict mock`。WHY 是 predict 模式不打真实 provider。

`packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`: 保留 provider SDK wrapper 空边界，当前 `__all__` 为空。WHY 是先完成包切割，不提前暴露 provider wrapper API。

`packages/graph-agent/src/graph_agent/core/harness.py:355-378`: `GraphAgentHarness.__init__` 接收 `model_resolver`，为空时抛 `GatewayResolverMissingError("<harness>")`。WHY 是清退 `get_model_resolver()` 隐式单例。

`packages/graph-agent/src/graph_agent/core/runner.py:162-198`: `run_skill` 接收并传递 `model_resolver`。`runner.py:232-310` 的 `_run_skill_dict` 把它传给 V2.1 root 或 `load_workflow_from_md`。`runner.py:481-491` 的 V2.1 path 在无 mock 时用 resolver 生成 `chat_model`。

`apps/studio/backend/app/services/gateway_resolver.py:16-23`: `build_gateway_model_resolver` 从 Studio `llm_roles.yaml` 读取配置，排除 `migration_required` 后校验成 Gateway `RolesData`，再构造 `ModelResolver`。WHY 是 Studio 拥有配置文件，Engine 只消费注入对象。

`apps/studio/backend/app/services/run_manager.py:231-236`: Studio run worker 调 `run_skill` 时传 `model_resolver=build_gateway_model_resolver()`。

`apps/studio/backend/app/services/predictor.py:72-76`: predict job 同样显式注入 Gateway resolver，即使 predict 使用 mock LLM，也保持 runtime 入口契约一致。

`apps/studio/backend/app/services/migrations.py:27-58`: `migrate_roles_payload` 把 provider type 旧值归一，并把 role 顶层 `temperature/max_tokens` pop 后 setdefault 到每个 `role.models[*]`。WHY 是旧配置无损迁移，新模型槽位已有值时不被覆盖。

`apps/studio/backend/app/services/llm_roles.py:27-45`: `load_roles_file` 在内存中迁移 legacy YAML，设置 `migration_required`。`llm_roles.py:48-57` 保存时验证引用并原子写入。`llm_roles.py:93-114` dump 时排除 `migration_required`，写回新 schema。

## §3 4 件套 spec ↔ src 对照表

| spec 条目 | 代码落点 | 状态 |
| --- | --- | --- |
| `requirements.md:18` R1 ModelResolverProtocol DI | `protocol.py:10-24`, `runner.py:162-198`, `harness.py:355-378` | 已完成 Model 相关 DI；SkillResolver 留后续 |
| `requirements.md:21` 独立包结构 | `packages/graph-agent-gateway/src/graph_agent_gateway/*.py` | 已完成 9 个 src 文件 |
| `requirements.md:22` Provider Error Payload | `exceptions.py:30-91`, `gateway_chat_model.py:137-159` | 已完成 3 个 `[F-v3-gateway-*]` |
| `requirements.md:23` 温度下推 | `migrations.py:46-57`, `llm_roles.py:27-45` | 已完成内存迁移与保存新格式 |
| `requirements.md:24` 参数透传 | `llm_config.py:41-48`, `resolver.py:151-169`, `gateway_chat_model.py:112-126` | 已完成 model 槽位级读取 |
| `design.md:35-39` Engine 只消费 protocol | `harness.py:374-378`, `runner.py:174-198` | 已清退隐式 resolver 单例生产入口 |
| `design.md:47-53` LLM Roles data contract | `RoleModelEntry`、Studio migration、Gateway resolver | 已完成 |
| `tasks.md:54-74` alpha1 package extraction | `__init__.py`, `protocol.py`, `resolver.py`, `gateway_chat_model.py`, `llm_config.py`, `predict_interception.py`, `exceptions.py`, `models.py`, `tracing.py` | 已完成 |
| `tasks.md:78-92` alpha2 DI | `GraphAgentHarness` 和 `run_skill` model_resolver 参数 | 已完成 |
| `tasks.md:94-104` alpha3 structured failure | `GatewayError` 三个子类 | 已完成 |
| `tasks.md:114-127` alpha4 fallback trace | `tracing.py:13-59`, `_generate` fallback event | 已完成 alpha 范围 |
| `tasks.md:129-146` alpha5 roles data layer | `migrations.py`, `llm_roles.py`, `llm_config.py`, `resolver.py` | 已完成 |
| `research.md:33-36` PR #90 clean port | 当前分支 log 未 cherry-pick PR #90；按 alpha scope 手工落地 | 已遵守 |

## §4 Test 跑通统计

`pytest packages/graph-agent-gateway/tests/ -v`: 23 passed。

`pytest packages/graph-agent/tests/ -v`: 945 passed, 3 skipped, 50 xfailed, 53 xpassed, 2 warnings。

`pytest apps/studio/backend/tests/ -v`: 343 passed, 1 skipped。

`uvx ruff check packages/graph-agent-gateway packages/graph-agent/src packages/graph-agent/tests apps/studio/backend/app apps/studio/backend/tests`: All checks passed。

`python -m mypy packages/ apps/studio/backend/app`: Success, 209 source files。

额外 grep gate：旧 `graph_agent.models.gateway_chat_model` / `graph_agent.models.resolver` / `get_model_resolver()` / `reset_model_resolver` 引用在 alpha 范围内无命中；旧 `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py` 和 `resolver.py` 已删除。

## §5 跟 mvp0 R1-R12 对齐

PR alpha 直接完成 `requirements.md:18` 里 R1 的 ModelResolverProtocol DI 部分：Engine runtime 通过 `model_resolver` 参数接入 Gateway，不再自己构造 provider resolver。SkillResolverProtocol 属于后续，不在 alpha 扩 scope。

PR alpha 新增并完成 `R[NEW]-Gateway-01` (`requirements.md:21`)：`packages/graph-agent-gateway` 成为独立包，concrete Gateway 能力从 Engine models 目录移走。

PR alpha 新增并完成 `R[NEW]-Gateway-02` (`requirements.md:22`)：`[F-v3-gateway-all-providers-failed]`、`[F-v3-gateway-resolver-missing]`、`[F-v3-gateway-role-not-configured]` 三个错误码进入结构化 payload。

PR alpha 新增并完成 `R[NEW]-Roles-01` (`requirements.md:23`)：Studio 读取 legacy `llm_roles.yaml` 时把顶层 `temperature/max_tokens` 下推到每个 `RoleModelEntry`。

PR alpha 新增并完成 `R[NEW]-Roles-02` (`requirements.md:24`)：Gateway resolver 优先使用 `RoleModelEntry.temperature/max_tokens`，并传给 `GatewayChatModel` 调用链。

R2-R12 中涉及 compile schema、Agent middleware、preflight、state-io、cleanup、全 tracing/error 清扫的项目均按 `tasks.md:21-28` 留给后续 PR，没有在 alpha 中偷跑。

## §6 已知遗留 / 后续 PR 依赖

`gamma0`：契约补丁 14h，处理 Agent AST/loader `exit_contract` 删除、validator 字段扩展、middleware order 契约补丁。alpha 只提供模型 DI 底座。

`PR beta`：middleware 34h，处理 `CognitiveFlowMiddleware`、ReAct loop 替换和 Agent semantic tracing 重构。alpha 不改 Agent loop 架构，只确保 run_skill 能注入 resolver。

`gamma1`：compile-schema 50h，处理 `GRAPH.md` body XML 和 mention 静态校验补完。alpha 不碰 compile schema。

`gamma1.5`：preflight 38h，处理 predict/preflight 阻断、compile 期 LLM 提醒和 DAG 静态检查。alpha 只保持 predict 注入契约。

`gamma2`：state-io 40h，处理 StateMapper、state-io、subgraph isolation。alpha 不做状态契约改造。

`gamma3`：cleanup 44h，处理 V2.1 schema cleanup 和全 engine trace/error contract 清扫。alpha 只收 gateway fallback trace。

LLM Roles Phase 2-5 UI 仍在后续：双栏设置、DND、Test Chain、Tauri shell 和人工 UI 验收不属于 alpha (`tasks.md:27`)。

## §7 Ship gate 状态

CI green：本轮未触发远端 PR pipeline；本地等价 gate 已全部通过，需以实际 PR CI 作为最终远端记录。

mypy：通过，`Success: no issues found in 209 source files`。

ruff：通过，完整 alpha 范围 `All checks passed!`。

a2 audit PASS：Step 5 用户已确认 PASS；4 项必修已按 grep gate 验证，包括旧 Gateway 文件删除、Harness resolver 必填、Studio 注入 resolver、Agent ReAct loop test 改为 run_skill 驱动。

主控复核：本报告按 `tasks.md:230-241` ship gate 覆盖 package 独立、DI 强制、三个错误码、model-level `temperature/max_tokens`、legacy migration test、a2 drift audit 和 logic-explained 字段级说明。

git log 备注：`git log feat/pr-alpha-gateway-llm-roles-phase1 --max-count=12` 当前显示分支 HEAD 为 `6699a55 docs(mvp0): align kiro cleanup with hard cutover`；本任务边界要求不 git mutate、不 commit，因此 ship report 记录的是当前工作树 PR alpha 实施结果与本地验证结果。
