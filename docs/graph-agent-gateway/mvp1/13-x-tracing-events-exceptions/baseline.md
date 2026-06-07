---
module: 13-x-tracing-events-exceptions
doc: baseline
status: drafted
verified_at: 2026-06-06
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMFallbackEvent/model_dump · packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayError/AllProvidersFailedError/GatewayResolverMissingError/GatewayRoleNotConfiguredError · packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:build_llm_fallback_event/emit_llm_fallback_event · packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel/_generate/_fallback_event_context/_route_diagnostics/_failure_record · packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py:classify_exception/ErrorClassification
units: [tracing-events-exceptions]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 13-x-tracing-events-exceptions — Baseline(现状)

> 本文只描述当前源码（fallback event、异常类型、触发点）；目标设计见同目录 `mvp1-alignment.md`。
> **判据归属**：本模块全部三块（fallback 事件 DTO / 结构化异常 / tracing helper）= **③b gateway 公共能力内核**，已在 `packages/graph-agent-gateway` 包内，**无反转、无下沉项**（归属表 13 行见 `module-disposition-revised.md:56`）。判据：任何调模型的 app 都需要这套可观测/异常底座，不依赖应用加工四件事（① UI ② 产品策略 ③ 调用方式 ④ 存储介质）→ ③b 公共。
> **注**：错误分类当前权威源是 [[06-orch-error-classification]]；401/402/403/404 当前分类是 **fallback**（credential/route scope），**不是全部 fail-fast**。本模块只记录分类后的事件/异常触发点，不重定义分类语义。

## 覆盖代码(含覆盖率)

覆盖率：brief 指定的 `events.py`、`exceptions.py`、`tracing.py:emit_llm_fallback_event` 100% 覆盖；为了说明触发点，额外覆盖 `gateway_chat_model.py:_generate/_fallback_event_context`。

| 覆盖项 | 覆盖状态 | 现状说明 |
|---|---:|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMFallbackEvent` | 100% | `LLMFallbackEvent` 是 Gateway fallback 事件 DTO：保存 phase、from/to provider、原因、固有事件码和 context。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayError` | 100% | `GatewayError` 是 Gateway 结构化异常基类：保存稳定 code 和机器可读 context。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:AllProvidersFailedError` | 100% | `AllProvidersFailedError` 表示一个 role 的候选 route 全部失败或 fail-fast 分类被包装成统一网关错误。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayResolverMissingError` | 100% | `GatewayResolverMissingError` 表示 LLM/Agent phase 没有注入 model resolver。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayRoleNotConfiguredError` | 100% | `GatewayRoleNotConfiguredError` 表示 role 或 route override 在 registry 中不可解析。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:build_llm_fallback_event` | 100% | `build_llm_fallback_event` 是 fallback event 构造 helper：把参数组装成 `LLMFallbackEvent`。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:emit_llm_fallback_event` | 100% | `emit_llm_fallback_event` 是 callback 发射 helper：逐个调用 callback，并吞掉 callback 自身异常。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:_generate` | 触发点覆盖 | `_generate` 是当前 fallback runtime 循环：在 probe/dispatch 失败时分类、记录、发事件或抛异常。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:_fallback_event_context` | payload 覆盖 | `_fallback_event_context` 是 fallback event context 构造器：写入 from/to route 诊断和 runtime settings。 |

## fallback event payload(现状)

`LLMFallbackEvent` 是 Gateway 自有事件 DTO：定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:9`。

| 字段 | 当前语义 | 代码依据 |
|---|---|---|
| `event_type` | 固定为 `llm_fallback`，用于 callback/event subscriber 识别事件类型。 | `events.py:19` |
| `phase_name` | 触发 fallback 的 phase 名；缺省场景常传 `<gateway>`。 | `events.py:13`、`gateway_chat_model.py:138` |
| `from_provider` | 当前失败 route 的 id；现状 `_candidate_id()` 直接返回 `route_id`。 | `events.py:14`、`gateway_chat_model.py:395` |
| `to_provider` | 下一个未 marked-down route 的 id；没有下一条则是 `<none>`。 | `events.py:15`、`gateway_chat_model.py:359` |
| `reason` | 失败异常的类型和消息，或 `RuntimeError: probe failed`。 | `events.py:16`、`gateway_chat_model.py:141`、`gateway_chat_model.py:179` |
| `code` | 固定为 fallback event 专属码 `[F-v3-gateway-llm-fallback]`，是 `init=False` 固有常量；调用点不再传 `code`，不复用全灭异常码。 | `events.py:9`、`events.py:20`、`gateway_chat_model.py:137`、`:174`、`:249` |
| `context` | 结构化诊断字典，`__post_init__` 会复制一份避免外部共享引用。 | `events.py:18`、`events.py:21` |

`LLMFallbackEvent.model_dump` 是事件序列化方法：它返回 event_type、phase、from/to provider、reason、code 和 context，见 `events.py:27`。

`_fallback_event_context` 是 GatewayChatModel 的事件 context 构造器：它写入 `role_name`、`fallback_decision`、`error_type`、`provider_status_code`、`unclassified_default`、`from_route`、`to_route` 和 `effective_runtime_settings`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:373` 到 `gateway_chat_model.py:392`。

`_route_diagnostics` 是 route 诊断压缩器：它只暴露 `route_id`、`endpoint_id`、`provider_model_id`、`canonical_id`、`protocol`，不暴露密钥，见 `gateway_chat_model.py:399` 到 `gateway_chat_model.py:408`。

## 异常类型语义(现状)

`GatewayError` 是结构化异常基类：它先尝试继承 `graph_agent.ModelProviderError`，独立导入时退回 `RuntimeError`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:7` 和 `exceptions.py:13`。

| 异常 | 语义 | payload | 触发线索 |
|---|---|---|---|
| `AllProvidersFailedError` | 一个 role 的执行候选链失败，或 fail-fast 分类被包装为该结构化错误。 | `role_name`、`phase_name`、`failed_provider_codes`、`last_error_chain`。 | `exceptions.py:33`、`exceptions.py:49`、`gateway_chat_model.py:130`、`gateway_chat_model.py:244`、`gateway_chat_model.py:267` |
| `GatewayResolverMissingError` | 需要 LLM 的 phase 没有 resolver 依赖。 | `phase_name`、`required_dependency=model_resolver`。 | `exceptions.py:63`、`packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:133` |
| `GatewayRoleNotConfiguredError` | 请求的 role 或 route/model override 不在 registry 可解析范围。 | `role_name`、`model_override`。 | `exceptions.py:77`、`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:87`、`resolver.py:99` |

## 编号执行流程(现状)

1. `GatewayChatModel._generate` 是 runtime fallback 循环：它先把 LangChain messages 转 dict 并套 system prompt prefix，见 `gateway_chat_model.py:96` 和 `gateway_chat_model.py:104`。
2. 它按 `self.resolved_role.routes` 遍历候选 route，并跳过 marked-down route，见 `gateway_chat_model.py:111` 和 `gateway_chat_model.py:113`。
3. 如果 probe 抛异常，`classify_exception` 产出 fallback/fail-fast 决策；非 fallback 决策直接抛 `AllProvidersFailedError`，fallback 决策会 mark down 并 emit event，见 `gateway_chat_model.py:123`、`gateway_chat_model.py:124`、`gateway_chat_model.py:129`、`gateway_chat_model.py:137`。该 emit 调用不传 `code`。
4. 如果 probe 返回 false，代码把它当 `RuntimeError: probe failed`，记录 failure、mark down、发 fallback event，见 `gateway_chat_model.py:153`、`gateway_chat_model.py:168`、`gateway_chat_model.py:174`。该 emit 调用不传 `code`。
5. 如果 dispatch 调用抛异常，代码同样分类；非 fallback 决策抛 `AllProvidersFailedError`，fallback 决策 mark down 并 emit event，见 `gateway_chat_model.py:236`、`gateway_chat_model.py:237`、`gateway_chat_model.py:242`、`gateway_chat_model.py:249`。该 emit 调用不传 `code`。
6. 如果所有 route 都没有成功返回，循环末尾抛 `AllProvidersFailedError`，见 `gateway_chat_model.py:267`。
7. `emit_llm_fallback_event` 构造 `LLMFallbackEvent`，逐个调用 callback 的 `on_event(event)`；callback 自己失败只记日志，不遮蔽 runtime 错误，见 `tracing.py:31`、`tracing.py:41`、`tracing.py:48`、`tracing.py:51`。`build_llm_fallback_event` / `emit_llm_fallback_event` 签名均不接受 `code` 参数。

## baseline/alignment 差异

baseline 当前事实：fallback event payload 已经带 from/to route 诊断和 effective runtime settings；异常已经是 Gateway-owned 结构化异常；事件 `code` 已拆为专属 `[F-v3-gateway-llm-fallback]`，并内聚到 `LLMFallbackEvent` 的 `init=False` 固有常量。

MVP1 目标差异：保留事件/异常结构；调用层迁移到 ChatX 后，fallback event 仍必须在编排层触发，并继续携带 route diagnostics、classification decision、provider status code 和 effective runtime settings。fallback event 专属 code 已在 WS-4 落地。

## 决策原因

1. 事件 DTO 放在 Gateway 包内，是为了 Gateway 不 import Graph Agent execution internals；当前权威是本模块与 gateway 包源码：`events.py` 定义 `LLMFallbackEvent`，`exceptions.py` 定义 Gateway 结构化异常。
2. fallback event 通过 callback adapter 发射，是为了对齐 tracing 底座而不是在 Gateway 内直接处理 callback 循环；当前代码 `emit_llm_fallback_event` 只调用 callback 的 `on_event`，callback 失败只记日志，测试也覆盖后续 callback 仍能收到事件。
3. 结构化异常替代纯文本 RuntimeError，是为了 Studio/trace 能读 `last_error_chain` 而不是解析自由文本；当前 `AllProvidersFailedError` 暴露 `failed_provider_codes` 和 `last_error_chain`，测试 `test_all_providers_failed_error_exposes_standard_payload` 已覆盖。
4. A' 迁移不能丢 fallback event。client 层 A' 重设计决策的兼容性验证清单（A' 实现必过）第 7 条钉死：**调用层从自研 `_call_*` 换成原生 ChatX 后，fallback event payload 仍必须带 from/to route 诊断**——这是 A' 迁移的硬性兼容闸口。完整清单 + 用户语境见同目录 `mvp1-alignment.md` §4/§5。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMFallbackEvent`：Gateway fallback 事件 DTO。
- `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:FALLBACK_EVENT_CODE`：fallback event 专属 code 常量。
- `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMFallbackEvent.model_dump`：fallback event 序列化方法。
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayError`：结构化异常基类。
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:AllProvidersFailedError`：候选链失败异常。
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayResolverMissingError`：resolver DI 缺失异常。
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayRoleNotConfiguredError`：role/override 不可解析异常。
- `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:build_llm_fallback_event`：fallback event 构造 helper。
- `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:emit_llm_fallback_event`：fallback event callback 发射 helper。
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel._generate`：fallback event 和异常触发主循环。
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel._fallback_event_context`：fallback event context 构造器。

## 待办/疑点

1. 已解决（WS-4）：fallback event 的 `code` 已拆出专属 `[F-v3-gateway-llm-fallback]`，不再复用 `[F-v3-gateway-all-providers-failed]`；全灭码仍只属于 `AllProvidersFailedError`。
2. `AllProvidersFailedError` 同时承载“全候选失败”和“fail-fast 分类后的结构化包装”，命名是否需要在 MVP1 文档或代码中细化，需要主控判断。
