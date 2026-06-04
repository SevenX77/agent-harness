---
module: 06-orch-error-classification
doc: baseline
status: drafted
---

# 06-orch-error-classification — Baseline(现状)

本文只描述当前源码里的真实错误分类语义,并纠正历史文档中“401/403/404 fail fast”的过时简写。MVP1 brief 明确要求覆盖 `registry/error_classification.py:classify_exception/classify_error_context`,并说明 401/402/403/404 与 capability 400 是 fallback,非 capability 400/413/422 是 fail request(`docs/graph-agent-gateway/mvp1/README.md:31`)。

## 覆盖代码(含覆盖率)

覆盖率: 1/1 个指定文件已核实,2/2 个公共分类入口已解释,3/3 个公开 Pydantic 结果/上下文模型已解释。

| 文件 | 覆盖入口 | 覆盖说明 |
|---|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py` | `classify_exception`：用于把异常映射为 legacy `decision` 以及 v1.1 action/scope。`classify_error_context`：用于把异常和 route/endpoint/stream 上下文映射为结构化 retry/fallback/fail action。 | 100%,含状态码常量、网络错误、provider payload、异常链 helper。**判据归属：纯 ③b 公共能力(错误码语义任何调模型 app 可复用，不依赖 UI/产品策略/调用方式/存储介质;disposition 表行 36 已判对，本轮不变);详见 `mvp1-alignment.md` §1。** |
| 调用点 | `GatewayChatModel._generate`：用于在 probe 和真实 dispatch 失败时调用分类器决定 fallback 还是终止。`LLMClientManager.probe_provider`：用于 probe 多模型时复用分类器判断是否继续。 | 覆盖关键 runtime 使用链。 |

## 现状逻辑

### 1. 数据模型与状态码分组

1. `Decision` 用于保留旧 fallback loop 的三态输出: `fallback_allowed`、`fail_fast`、`fail_fast_with_route_context`(`registry/error_classification.py:10`)。
2. `ErrorAction` 用于表达 v1.1 语义中的动作: `retry_same_route`、`fallback_route`、`fail_request`(`registry/error_classification.py:11`)。
3. `ErrorScope` 用于标记错误影响范围,包括 request、route、endpoint、credential、bucket、stream、unknown(`registry/error_classification.py:12`)。
4. `ErrorContext` 用于携带 route_id、endpoint_id、credential_ref、method_id、request_mapper_id、runtime settings、provider error 和 stream phase(`registry/error_classification.py:20-36`)。
5. `ErrorActionClassification` 用于返回 v1.1 action/scope/status/fallback_eligible/retryable 等结构化结果(`registry/error_classification.py:38-58`)。
6. `ErrorClassification` 用于返回旧 decision 以及 action/scope/status/message,供当前 fallback loop 继续消费(`registry/error_classification.py:60-73`)。
7. 状态码分组是源码里的真实语义: `RETRYABLE_STATUS_CODES={429,500,502,503,504,529}`,`FALLBACK_STATUS_CODES={401,402,403,404}`,`FAIL_REQUEST_STATUS_CODES={400,413,422}`(`registry/error_classification.py:15-17`)。**测试关键点(铁律，不可改坏)：401/402/403/404→fallback(不是 fail-fast)、400+capability→fallback、400非capability/413/422→fail_fast、429/5xx/网络错→retry(`fallback_allowed`)、未知→`fail_fast_with_route_context`。"401→fallback 不 fail-fast"是头号回归点必测;详见 `mvp1-alignment.md` §6。**

### 2. `classify_exception` 执行流程

1. `classify_exception` 接收异常和可选 route_id,先构造只带 route_id 的 `ErrorContext`,再调用 `classify_error_context` 得到 v1.1 action(`registry/error_classification.py:75-82`)。
2. 如果 action 是 `retry_same_route` 或 `fallback_route`,legacy decision 一律映射成 `fallback_allowed`;这就是当前 GatewayChatModel 能继续尝试下一条 route 的依据(`registry/error_classification.py:83-84`)。
3. 如果 action 是 fail_request 且 `unclassified_default=True`,decision 映射为 `fail_fast_with_route_context`;这用于未知异常,要求带 route context 暴露而不是静默 fallback(`registry/error_classification.py:85-86`)。
4. 其他 fail_request 映射为 `fail_fast`;这覆盖非 capability 400、413、422 等请求级错误(`registry/error_classification.py:87-98`)。

### 3. `classify_error_context` 执行流程

1. `classify_error_context` 从 context 或异常链中提取 status_code、provider_error_type、provider_error_message;`_status_code` 用于识别异常对象的 `status_code` 或 `response.status_code`(`registry/error_classification.py:101-109`, `registry/error_classification.py:223-232`)。
2. 如果 `stream_phase=="after_200_sse"`,分类为 `fallback_route` / `stream`,因为 200 后 SSE 中断属于流式 route 失败(`registry/error_classification.py:111-121`)。
3. 如果异常链里有 `httpx.ConnectError` 或 `httpx.TimeoutException`,分类为 `retry_same_route` / `route`,并标记 retryable;`_has_network_failure` 会沿 `__cause__` / `__context__` 检查包装异常(`registry/error_classification.py:122-132`, `registry/error_classification.py:235-239`, `registry/error_classification.py:293-301`)。
4. 如果 status 是 429/500/502/503/504/529,分类为 `retry_same_route`;429 scope 是 bucket,其他 retryable 状态 scope 是 endpoint(`registry/error_classification.py:133-143`)。
5. 如果 status 是 401/402/403/404,分类为 `fallback_route`;404 scope 是 route,401/402/403 scope 是 credential。注意:这四个状态在真实源码中不是 fail-fast(`registry/error_classification.py:144-154`)。
6. 如果 status 是 400 且 `_looks_like_route_capability_error` 命中 unsupported/not supported/unknown parameter/invalid model/model not found,分类为 `fallback_route` / `route`(`registry/error_classification.py:155-168`, `registry/error_classification.py:272-290`)。
7. 如果 status 是 400/413/422 且没有 capability fallback 条件,分类为 `fail_request` / `request`(`registry/error_classification.py:169-178`)。
8. 其他未知异常分类为 `fail_request` / `unknown`,并设置 `unclassified_default=True`;后续 `classify_exception` 会映射成 `fail_fast_with_route_context`(`registry/error_classification.py:179-188`)。

### 4. runtime 调用点

1. `GatewayChatModel._generate` 在 probe 抛异常时调用 `classify_exception`;decision 不是 `fallback_allowed` 就立刻抛 `AllProvidersFailedError`,否则 mark down 并发 fallback event 后继续下一候选(`gateway_chat_model.py:123-152`)。
2. `GatewayChatModel._generate` 在真实 dispatch 抛异常时同样调用 `classify_exception`;非 fallback_allowed 终止,fallback_allowed 则 mark down、emit event、继续下一 route(`gateway_chat_model.py:237-255`)。
3. `LLMClientManager.probe_provider` 在 route probe 中遇到异常时也调用 `classify_exception`;不是 fallback_allowed 的异常会重新抛出,避免把请求级错误误判成“这个模型暂时不通”(`client_manager.py:407`, `client_manager.py:433`)。

## baseline/alignment 差异

1. baseline 源码真实语义已经与最新决策记录一致:401/402/403/404 是 fallback,400 capability 错误是 fallback,非 capability 400/413/422 是 fail request,未知是 fail with route context(`registry/error_classification.py:15-17`, `registry/error_classification.py:133-188`)。
2. 历史 mvp0 文档仍有过时简写,把 400/401/403/404/422 归成 fail fast;新决策记录已明确指出这类写法错误,06 alignment 必须保护源码真实语义(`docs/graph-agent-gateway/mvp0/mvp0-alignment.md:146-148`, `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:136-153`)。
3. baseline 的 `classify_exception` 已把 v1.1 action 映射到旧 decision,所以 MVP1 调用层迁移不需要改错误分类,只需要保证 ChatX 抛出的异常仍能被 `_status_code` 和 provider payload helper 识别(`registry/error_classification.py:75-98`, `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:187-193`)。

## 决策原因

1. 401/402/403/404 做 fallback 的原因是它们更像 credential/route scope 问题,可能下一条 route 或 credential 可用;源码把 404 scope 标成 route,401/402/403 scope 标成 credential(`registry/error_classification.py:144-154`)。
2. 非 capability 400/413/422 做 fail request 的原因是它们通常表示请求形状、payload 过大或 schema 验证问题,继续 fallback 可能掩盖调用方错误(`registry/error_classification.py:169-178`)。
3. 400 capability 错误做 fallback 的原因是 unsupported parameter、invalid model、model not found 等表明当前 route/mapper 不适配,下一条 route 可能可用(`registry/error_classification.py:155-168`, `registry/error_classification.py:272-290`)。
4. 未知异常 fail with route context 的原因是不能把未分类错误当作模型选择信号;这与 mvp0 “无法分类时带 route context 暴露错误”的要求一致(`registry/error_classification.py:179-188`, `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:172`)。

## 代码索引(clues)

- `registry/error_classification.py:15-17` — 状态码分组,其中 401/402/403/404 明确属于 fallback status。
- `registry/error_classification.py:20-36` — `ErrorContext`：用于携带 route/endpoint/credential/stream 上下文。
- `registry/error_classification.py:38-58` — `ErrorActionClassification`：用于返回 v1.1 action/scope。
- `registry/error_classification.py:60-73` — `ErrorClassification`：用于返回 current fallback loop 消费的 decision。
- `registry/error_classification.py:75-98` — `classify_exception`：用于把 action 映射成 legacy decision。
- `registry/error_classification.py:101-188` — `classify_error_context`：用于执行真实错误分类。
- `registry/error_classification.py:223-232` — `_status_code`：用于从异常链提取 provider status code。
- `registry/error_classification.py:254-269` — `_provider_error_payload`：用于读取 provider JSON error payload。
- `registry/error_classification.py:272-290` — `_looks_like_route_capability_error`：用于识别 400 capability 类错误。
- `registry/error_classification.py:293-301` — `_exception_chain`：用于沿 cause/context 检查包装异常。
- `gateway_chat_model.py:123-152` — probe 异常分类调用点。
- `gateway_chat_model.py:237-255` — dispatch 异常分类调用点。
- `packages/graph-agent-gateway/tests/test_registry_error_classification.py:25-54` — 测试已断言 401/402 fallback、413 fail_fast、未知 fail_fast_with_route_context。
- `packages/graph-agent-gateway/tests/test_registry_error_classification.py:82-105` — 测试已断言 SSE after 200 fallback 和 400 unsupported fallback。

## 待办/疑点

1. ChatX A' 迁移后需补确定性测试,确认 ChatX/SDK 抛出的 status_code、response JSON、wrapped network error 仍能被 `_status_code`、`_provider_error_payload`、`_exception_chain` 正确识别(`registry/error_classification.py:223-301`, `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:250`)。
2. 当前 capability 400 的识别依赖字符串 marker,覆盖 unsupported/not supported/unknown parameter/invalid model/model not found;若 provider 返回本地化或新字段,可能需要扩展 marker,但 MVP1 不应改现有分类语义(`registry/error_classification.py:272-290`)。
