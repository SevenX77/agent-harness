---
module: 07-orch-fallback-circuit-probe
doc: baseline
status: drafted
verified_at: 2026-06-02
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel/_generate/_is_marked_down/_probe/_invoke_with_token_escalation/_mark_down/_usage_total_calls/_record_usage · packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:LLMClientManager/probe_provider/is_provider_marked_down/mark_provider_down/record_usage/_probe_provider/_is_provider_marked_down/_mark_provider_down · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:RuntimePolicy/ProbeResult · packages/graph-agent-gateway/src/graph_agent_gateway/registry/probe_contracts.py · apps/studio/backend/app/services/copilot_test.py:ModelProbeResult/_probe_model/_probe_official_call_method · apps/studio/backend/app/services/llm_health_store.py:RuntimeCircuit/SqliteLlmHealthStore
units: [fallback-circuit-probe-health]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 07-orch-fallback-circuit-probe — Baseline(现状)

本篇只写编排步骤：fallback 遍历、熔断跳过、probe、异常分类、mark_down、fallback event、usage 归属。真实 provider 调用、消息转换、输出解析和 `_build_chat_result` 的细节在 [09-inv-invocation-runtime/baseline.md](../09-inv-invocation-runtime/baseline.md) 写。

## 覆盖代码(含覆盖率)

覆盖率：本模块 brief 指定的 5 组代码已全部核源码，文档覆盖率 100%。共享文件按 [mvp1 README](../README.md) 的边界切分：`gateway_chat_model.py` 的 fallback / probe / 熔断 / usage 编排步骤写 07，单 route invoke / 结果桥接写 09；`client_manager.py` 现只覆盖 probe / 熔断 / usage 健康职责。

| 代码 | 本篇覆盖的用途 |
|---|---|
| `GatewayChatModel._generate` 是 LangChain 调用进入 Gateway 后执行 fallback 链的主循环；本篇只覆盖它的编排段，范围是 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:97-269`。 |
| `_is_marked_down` 是 `_generate` 调用 client manager 判断 route 是否仍在 down TTL 内的桥接函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:494-501`。 |
| `_probe` 是 `_generate` 调用 client manager 做 1-token 探活的桥接函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:503-520`。 |
| `_mark_down` 是 `_generate` 在 fallback-eligible 失败后把 route 写入熔断缓存的桥接函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:597-604`。 |
| `_usage_total_calls` 是 `_generate` 判断 client manager 是否已记录 usage 的探测函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:861-878`。 |
| `_record_usage` 是 `_generate` 在调用层未记账时补记 endpoint usage 的桥接函数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:880-889`。 |
| `LLMClientManager` 是当前 Gateway 的 SDK client 缓存、probe、熔断和 usage 统计容器；本篇覆盖健康/统计职责，类定义见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:40-52`。 |
| `LLMClientManager.is_provider_marked_down` 是对外判断 route down TTL 的方法，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:43-51`。 |
| `LLMClientManager.probe_provider` 是对外执行 route 探活的方法，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:53-66`。 |
| `LLMClientManager.mark_provider_down` 是对外写入 route 熔断状态的方法，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:68-77`。 |
| `RuntimePolicy` 是 resolver 交给运行时的健康策略配置，字段包含 down TTL、probe timeout 和 token escalation 轮数，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:88-98`。 |
| `ProbeResult` 是 endpoint/route probe 结果 DTO，当前由 `probe_contracts.py` 重新导出给后端/诊断侧使用，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:320-329` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/probe_contracts.py:1-7`。 |
| `ModelProbeResult` 是 Studio 后端一次模型探测的返回结构，见 `apps/studio/backend/app/services/copilot_test.py:47-61`。**判据归属:= ③a 应用(copilot 专属,绑 SDK 调用方式),与 ③b 通用 route probe 不同源;详见 `mvp1-alignment.md` §5。** |
| `_probe_model` 是 Studio 后端按 provider/backend 发最小生成请求的探测函数，见 `apps/studio/backend/app/services/copilot_test.py:138-169`。**判据归属:= ③a 应用(copilot 假测试,留 studio)。** |
| `_probe_official_call_method` 是 Studio 后端按具体官方 API family 发最小生成请求的探测函数，见 `apps/studio/backend/app/services/copilot_test.py:172-204`。**判据归属:= ③a 应用(copilot 假测试,留 studio)。** |
| `RuntimeCircuit` 是 Studio 后端持久化熔断状态的记录对象，见 `apps/studio/backend/app/services/llm_health_store.py:14-23`。**判据归属:熔断持久化 = ③b 公共内核(本轮反转,待下沉 gateway);存储介质留注入。** |
| `SqliteLlmHealthStore` 是 Studio 后端保存和查询 runtime circuit 的 SQLite store，见 `apps/studio/backend/app/services/llm_health_store.py:26-124`。**判据归属:= ③b 公共内核(本轮反转,原判 ③a seam);SQLite 路径(存储介质 ③a)注入,store 逻辑 ③b 待下沉。** |

## 编号执行流程

1. `GatewayChatModel._generate` 先把 LangChain `BaseMessage` 转成 dict，再合并 role 的 system prompt prefix；这一步是当前调用层输入准备，不是本篇要保留的编排能力，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:104-107`，具体问题见 09 baseline。

2. `GatewayChatModel._generate` 读取 `ResolvedRole.runtime_policy`，然后按 `ResolvedRole.routes` 的声明顺序遍历 route 候选；这个顺序就是 fallback 链，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:108-112`，`ResolvedRole.routes` 的字段定义在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-456`。

3. `_is_marked_down` 在每条 route 调用前询问 `LLMClientManager.is_provider_marked_down`；如果 route 仍在 down TTL 窗口内，`_generate` 直接 `continue` 到下一条候选，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:113-114` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:446-452`。

4. `LLMClientManager._is_provider_marked_down` 用 `endpoint_id:provider_model_id` 作为 down-cache key，过期后删除缓存并返回 false，未过期则返回 true，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:286-295`。

5. `_probe` 在 `probe_before_call=True` 时调用 `LLMClientManager.probe_provider`；如果 manager 支持 `credential_provider` 参数，就把凭证读取器传进去，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:115-122` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:455-472`。

6. `LLMClientManager._probe_provider` 对 `openai_compatible` 发 `chat.completions.create(..., max_tokens=1, temperature=0)`，对 `anthropic_compatible` 发 `messages.create(..., max_tokens=1)`；其他协议直接返回 true，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:316-383`。

7. `LLMClientManager._probe_provider` 捕获 probe 异常后先用 `classify_exception` 判断是否可 fallback；不可 fallback 的异常重新抛出，可 fallback 的异常会写入 down-cache 并返回 false，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:343-355` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:369-381`。

8. `GatewayChatModel._generate` 捕获 `_probe` 抛出的异常后再次用 `classify_exception` 转成 fallback 决策；`fallback_allowed` 之外的结果会立刻抛 `AllProvidersFailedError`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:123-134`。

9. `classify_exception` 是运行时异常分类入口，它把 `retry_same_route` 和 `fallback_route` 都映射为 `fallback_allowed`，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py:75-98`；状态码语义由 06 模块维护，本篇只消费结果。

10. `GatewayChatModel._generate` 对 probe 异常的 fallback 分支会调用 `_mark_down`，再发 `emit_llm_fallback_event`；事件 context 包含 from/to route 诊断、fallback decision、provider status code 和 runtime settings，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:135-151` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:373-392`。

11. `GatewayChatModel._generate` 对 `probe_ok=False` 的分支会构造固定的 `"probe failed"` failure record，写入 down-cache，并发 fallback event 后继续下一条 route，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:153-189`。

12. `_dispatch` 是当前调用层桥接函数；`GatewayChatModel._generate` 在真正调用前后读取 usage 计数，若调用层没有自己记录 usage，就从响应里补记 endpoint usage，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:190-236`，调用细节见 09 baseline。

13. `LLMClientManager.record_usage` 以 endpoint/provider 字符串为桶累计 `total_calls`、prompt tokens、completion tokens 和 total tokens，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:256-268`；`GatewayChatModel._generate` 当前传入的是 `candidate.endpoint_id`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:229-235`。

14. `GatewayChatModel._generate` 捕获真实调用异常后复用 `classify_exception`；不可 fallback 时抛 `AllProvidersFailedError`，可 fallback 时 mark_down、发 fallback event、继续下一条 route，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:237-265`。

15. `GatewayChatModel._generate` 遍历完所有 route 后抛 `AllProvidersFailedError`；错误 payload 来自累积的 failure records，代码在 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:267-271` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:33-60`。

## Baseline / Alignment 差异

| 主题 | baseline 现状 | MVP1 方向 |
|---|---|---|
| 编排外壳 | `GatewayChatModel._generate` 已承担 fallback、probe、熔断、事件和 usage 归属，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:96-271`。 | 保留 `GatewayChatModel` 作为编排外壳，不删 gateway、不用裸 ChatX 取代整个 resolver/gateway，决策 D1（否决激进版 A）完整逻辑 + PM 原话见 `mvp1-alignment.md` §4 / §5。 |
| 同 route 瞬时重试 | 当前 probe 用的轻量 OpenAI/Anthropic SDK client 仍显式 `max_retries=0`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:112-117` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:146-150`；真实 ChatX 主路径不再走这些 client。 | 改用 ChatX invoke 后保留 ChatX 默认有界瞬时重试；跨 route fallback 仍由 `_generate` 管，决策 F2（撤回真实调用 `max_retries=0`）完整逻辑 + PM 原话见 `mvp1-alignment.md` §5 / §4。 |
| 截断升级重试 | ChatX 主路径的截断升级已在 `GatewayChatModel._invoke_with_token_escalation`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:545-587`；generic ordinary path 的同名策略在 `ordinary_chat._call_with_token_escalation`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/ordinary_chat.py:653-673`。 | 截断升级重试保留在编排/调用桥接边界包住 ChatX invoke；generic ordinary path 保留自身 token escalation，不再挂在 `LLMClientManager`。 |
| 健康状态持久化 | `LLMClientManager` 用进程内 `_provider_down_cache` 做执行期 TTL，见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:49-52` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:340-368`。 | Studio 后端已有 `SqliteLlmHealthStore` 可持久化 circuit，见 `apps/studio/backend/app/services/llm_health_store.py:26-124`。**判据反转:`SqliteLlmHealthStore` = ③b 公共内核(待下沉),不再是"③a seam / 是否打通是疑点"——执行期 down-cache 与持久化 store 都属 ③b,下沉后统一为同一运行时健康源,SQLite 路径(存储介质)留 ③a 注入。** |
| Probe DTO | `ProbeResult` 只是 registry schema 中的 DTO，`probe_contracts.py` 只重导出，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:320-329` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/probe_contracts.py:1-7`。 | 探测结果应继续作为诊断/SSOT 证据流的一部分；执行期 `_generate` 仍只消费 boolean probe/fallback 结果。 |

## 决策原因

保留编排层的原因是当前 `_generate` 里的 fallback、probe、熔断、异常分类、event 和 usage 都是 Gateway 自有语义；直接删除 `GatewayChatModel` 会丢掉这些能力，决策明确否决了裸返回 ChatX + `with_fallbacks()` 的激进方案 A（理由:`with_fallbacks()` 只按异常类型分流、表达不了按 HTTP status 分类，且真机第八轮从未验证"删编排层"），完整逻辑 + PM 原话见 `mvp1-alignment.md` §4 / §5。

把真实调用换成 ChatX 的原因不在 07，而在 09：bug 根源是调用层消息转换把 LangChain message 拍成 provider dict，尤其 tool loop 中的空 `AIMessage(content="")` 被转成 `{"content":""}`、经 anthropic dispatch 发出后触发 qiniu-anthropic `400 content must not be empty`，旧转换 helper 仍可作为非主路径证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:789-820`（`_langchain_messages_to_dict`），完整溯源见 `mvp1-alignment.md` §5 D1。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:111-189`：route 遍历、熔断跳过、probe 成败处理。
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:237-265`：真实调用失败后的分类、mark_down 和 fallback event。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:286-383`：进程内熔断 TTL 和 1-token probe。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py:75-188`：`classify_exception` 到 status/action/decision 的转换。
- `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:31-55`：`emit_llm_fallback_event` 发事件且吞 callback 异常。
- `apps/studio/backend/app/services/copilot_test.py:138-204`：Studio 后端 route/model 探测函数，不是 graph-agent 执行期 fallback loop。**判据:= ③a 应用(copilot 假测试,绑 SDK 调用方式,留 studio)。**
- `apps/studio/backend/app/services/llm_health_store.py:26-124`：SQLite runtime circuit store。**判据:熔断持久化内核 = ③b 公共(本轮反转,待下沉);SQLite 路径(存储介质)留 ③a 注入。**

## 待办/疑点

1. `_probe_provider` 在可 fallback 异常时已经 `_mark_provider_down` 并返回 false，`_generate` 的 `probe_ok=False` 分支又 `_mark_down` 一次；当前只是覆盖同一个 TTL key，但是否需要去重由实现任务决定，证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:352-355`、`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:378-381` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:168-173`。

2. `LLMClientManager.is_provider_marked_down` 接收 `runtime_policy` 但当前立即 `del runtime_policy`，实际 TTL 判断只看已写入的过期时间；如果 MVP1 要让查询逻辑也感知 policy，需要实现任务另行处理，证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:53-61`。

3. `SqliteLlmHealthStore` 已有持久化 circuit，但执行期 `LLMClientManager` 仍用进程内 `_provider_down_cache`；二者是否合并为同一运行时健康源，当前源码没有直接连接，证据见 `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:49-52` 和 `apps/studio/backend/app/services/llm_health_store.py:26-124`。**判据反转后定调:二者都属 ③b 公共内核(`SqliteLlmHealthStore` 待下沉),已不是归属疑点;只剩"下沉后如何在 gateway 包内统一为同一健康源"的工程问题,存储介质 SQLite 路径留 ③a 注入。**
