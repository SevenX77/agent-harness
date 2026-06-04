---
module: 10-inv-route-chat-model-factory
doc: mvp1-alignment
status: written
last_verified: 2026-06-02
---

# 10-inv-route-chat-model-factory - MVP1 Alignment(目标设计)

> **Tier**：③b gateway 公共能力（**MVP1 新建**调用层核心；现源码不存在，职责暂由 resolver 实例化 + client_manager SDK 工厂代管）
> **Owns**：把一条 `ResolvedRoute` 构造成原生 LangChain ChatX（`ChatAnthropic`/`ChatOpenAI`/`ChatGoogleGenerativeAI`），内部 = base_url 调用时幂等归一化双保险 + provider profile init-kwargs + thinking 归一化 + stream_usage 默认开 + deepseek 单方法 patch（借鉴）。**只构造模型，不 invoke**（invoke 归 09，编排循环第 5 步调本工厂）。
> **Status**：设计定稿（2026-06 判据复核，归属表判 10=纯 ③b 新建不变）；代码 = `RouteChatModelFactory` 待新建，现真实调用仍由 `LLMClientManager._dispatch_provider_call`+`_call_*` 完成。
> **Related**：[[09-inv-invocation-runtime]]（invoke 运行时，拿本工厂构造的 ChatX 执行 `.invoke()`）· [[11-inv-provider-profiles]]（本工厂调用 `ProviderProfile` 表合 init-kwargs）· [[03-orch-credentials-endpoints]]（base_url 保存时归一化 = 主修复，本工厂只做调用时副保险）· [[01-handoff-interface]]（`ResolvedRoute` 契约 = 工厂唯一输入）· [[04-orch-registry-schema]]（`ResolvedRoute` 字段权威源）
> **决策日志**：`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md`（M6 `RouteChatModelFactory` 新建 / D2 编排-调用分离 / F1 base_url 归一化 / F4 thinking / F5 usage+stream_usage / F6 provider profile init-kwargs / §4 借鉴 vs 自建）+ `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（§4 判 10 纯 ③b 新建）
> **现状**：见同目录 `baseline.md`（诚实声明现源码无 `RouteChatModelFactory`）

## 1. 定义

MVP1 目标：新建 `RouteChatModelFactory`（一条 `ResolvedRoute` → 原生 LangChain ChatX 实例的构造器）。它是 D2「调用层」的落点 —— 编排层只决定用哪条 route，调用层才把 route 变成可 invoke 的原生 ChatX。本工厂**只构造、不 invoke**：[[09-inv-invocation-runtime]] 的编排循环第 5 步调本工厂拿 ChatX，再自己 `.invoke()`。

- **输入**：一条 `ResolvedRoute`（protocol/base_url/credential_ref/provider_model_id/effective runtime settings）。
- **职责**：解析凭证（经 `CredentialProviderProtocol`，不落明文）→ base_url 调用时幂等归一化双保险 → 按 protocol 选 ChatX 类 → 合成 init kwargs（route 字段 + [[11-inv-provider-profiles]] 的 `ProviderProfile` defaults + route runtime settings）→ 返回原生 ChatX 实例。
- **输出**：一个原生 `ChatAnthropic` / `ChatOpenAI` / `ChatGoogleGenerativeAI`（已带 thinking 归一化、stream_usage、必要的 deepseek 单方法 patch）。

本模块**纯 ③b 公共**（"把 route 构造成可调用模型"是任何调模型 app 的刚需），归属表判 10=纯 ③b 新建（`module-disposition-revised.md:43,84`）。`baseline.md` 诚实声明现源码不存在本类，职责暂由 resolver 实例化 `GatewayChatModel` + client_manager SDK 工厂代管。

## 2. 数据流 / 机制(目标设计与编号流程)

覆盖率:100%。本文件覆盖 `RouteChatModelFactory` 的目标职责、它要替换的 baseline 调用职责、以及 deerflow/deepagents 参考实现。`RouteChatModelFactory` 是拟新建的调用层工厂，用一条 `ResolvedRoute` 构造原生 LangChain ChatX。

目标覆盖:

| 范围 | 目标关系 |
|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-459` | `ResolvedRoute`/`ResolvedRole` 是工厂输入和编排交接物。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:190-236` | 现状 `_dispatch` 调用点应改为调用 `RouteChatModelFactory` 构造 ChatX 后 invoke。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-295` | SDK client 工厂职责不再服务真实调用；probe 可继续复用。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:440-1012` | provider `_call_*` 与 dict 消息转换由原生 ChatX 取代；截断 token 升级逻辑保留并搬出。 |
| `temp/deerflow/backend/packages/harness/deerflow/models/factory.py:34-47` | `stream_usage` 默认开启的参考，解决第三方 OpenAI-compatible usage 为空。 |
| `temp/deerflow/backend/packages/harness/deerflow/models/factory.py:94-146` | thinking 开关归一化参考，覆盖 Anthropic、OpenAI-compatible extra_body、vLLM、Codex 等形状。 |
| `temp/deerflow/backend/packages/harness/deerflow/models/patched_deepseek.py:18-59` | 只在 payload 差异必要时子类覆盖单方法的参考。 |
| `temp/deepagents/libs/deepagents/deepagents/_models.py:15-36` | `resolve_model` 用 `init_chat_model` 加 provider profile kwargs 构造 ChatX 的参考。 |

**上下游**：[[09-inv-invocation-runtime]] 编排循环第 5 步选定一条 `ResolvedRoute` → **本工厂构造原生 ChatX**（凭证解析 → base_url 双保险 → 选 ChatX 类 → 合 init-kwargs ← [[11-inv-provider-profiles]] `ProviderProfile`）→ 返回 ChatX → 09 执行 `.invoke()`。

1. 输入一条 `ResolvedRoute`。`ResolvedRoute`（运行期 route 候选）已经携带 `protocol`、`base_url`、`credential_ref`、`credential_fingerprint`、`provider_model_id`、`call_method_id`、`request_mapper_id` 与 effective runtime settings(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`)。
2. `RouteChatModelFactory` 先解析凭证。`RouteChatModelFactory`（route 到 ChatX 的构造器）应通过现有 `CredentialProviderProtocol`（按 `credential_ref` 取明文 key 的凭证读取协议）取 `credential_ref`，保持“不把明文 key 写入 route”的边界；现状 `LLMClientManager._resolve_api_key`（按 route 凭证引用取明文 key 的内部函数）已经体现这个约束(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:1034-1055`)。
3. `RouteChatModelFactory` 对 base_url 做调用时幂等归一化双保险。主修复仍是保存 credential/endpoint 时归一化（归 [[03-orch-credentials-endpoints]]）；工厂只负责“已规范则 no-op，未规范则按 protocol 修到 ChatX 需要的形状”(`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:169-180`)。
4. `RouteChatModelFactory` 按 `route.protocol` 选择原生 ChatX 类:`anthropic_compatible` -> `ChatAnthropic`，`openai_compatible` 和需要 OpenAI shape 的 routes -> `ChatOpenAI`，`google_genai` -> `ChatGoogleGenerativeAI`；`ark_runtime` 需要先确认 LangChain 原生适配面，不能凭旧 Ark SDK 分支直接假定等价(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:19`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:962-981`)。
5. `RouteChatModelFactory` 合成 init kwargs。init kwargs(传给 ChatX 构造器的参数字典)来源包括 route model id、api key、base_url、timeout、temperature/max tokens、tool/structured-output/reasoning 等 runtime settings；现状这些设置分散在 `_dispatch` 调用参数和 `_call_*` kwargs 中(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:197-225`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:459-482`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:691-752`)。
6. `RouteChatModelFactory` 调用 `ProviderProfile` 表。`ProviderProfile`(provider/model 到 init kwargs、`pre_init`、动态 factory 的声明式表,归 [[11-inv-provider-profiles]])把 provider 差异放在构造参数层，不重写消息转换(`temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:36-90`; `temp/deepagents/libs/deepagents/deepagents/profiles/provider/provider_profiles.py:317-379`)。
7. `RouteChatModelFactory` 处理 thinking。thinking(provider reasoning/extended-thinking 开关)现状在 resolver、GatewayChatModel 和 client_manager 中逐层传递；MVP1 应把构造期差异收束成 ChatX init kwargs 或调用 kwargs(`packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:114-118`; `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:205-213`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:709-752`)。
8. `RouteChatModelFactory` 对 OpenAI-compatible ChatX 默认打开 `stream_usage`。`stream_usage`(让 LangChain streaming 响应携带 token usage 的开关)；deerflow 已说明第三方 base_url 下 LangChain 默认可能不给 usage，因此工厂应显式补上(`temp/deerflow/backend/packages/harness/deerflow/models/factory.py:34-47`; `temp/deerflow/backend/packages/harness/deerflow/models/factory.py:154-161`)。
9. `GatewayChatModel._generate`(执行一次模型生成请求的 LangChain 入口)保留编排循环，但第 190-236 行的 `_dispatch` 应改成“取 ChatX -> 原始 `BaseMessage` invoke -> 取 `AIMessage`”。这样仍保留 probe、熔断、fallback event、usage 汇总和异常分类(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:111-271`; `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:101-117`)。
10. 截断 token 升级重试搬到编排层包住 ChatX invoke。`_call_with_token_escalation`(现状 token 放大重试逻辑)不能留在被退役的 `_call_*` 内，也不能被删除(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:990-1012`; `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:200-204`)。
11. 返回 `AIMessage` 后，`GatewayChatModel._build_chat_result`(把响应包成 LangChain `ChatResult` 的函数)或后继桥接逻辑只注入 route metadata，不拍平 thinking content blocks。当前 `_coerce_text`(把任意 content 强制转字符串)会把非字符串内容转字符串，目标是保留 ChatX 的 richer content shape(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:313-357`; `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:645-658`; `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:208-220`)。

## 3. 接口契约

> 本工厂是 D2「调用层」的构造器入口，跨边界契约：① 接收一条 `ResolvedRoute`（编排交接物）；② 返回一个原生 ChatX 实例（交 09 invoke）；③ 调用 [[11-inv-provider-profiles]] 的 `ProviderProfile` 合 init-kwargs；④ 经 `CredentialProviderProtocol` 取凭证（不落明文）。**本工厂不 invoke、不做 fallback**。

| 边界 | 契约 |
|---|---|
| **09 编排 → 10 工厂（构造入参）** | 一条 `ResolvedRoute`（字段权威源 `registry/schema.py:415-445`）。工厂从中取 protocol（选 ChatX 类）、base_url（双保险后传 ChatX）、credential_ref（解析凭证）、provider_model_id（model 名）、timeout_seconds、effective_runtime_settings（temperature/max tokens/reasoning/tool/structured-output）。**不接受 provider/model 字符串**（与 deepagents `resolve_model` 的 `provider:model` spec 区别，见 §5 决策 2）。 |
| **10 工厂 → ChatX 类选择** | `route.protocol`（`registry/schema.py:19` Protocol 字面量）映射：`anthropic_compatible`→`ChatAnthropic`，`openai_compatible`/需 OpenAI shape→`ChatOpenAI`，`google_genai`→`ChatGoogleGenerativeAI`；`ark_runtime` 适配面待定（§8 待办 2）。 |
| **10 工厂 → 11 ProviderProfile（合 init-kwargs）** | 调 [[11-inv-provider-profiles]] 的 `apply_provider_profile`-类入口：以 route 生成基础 kwargs → 叠 provider/model profile defaults（headers / Responses API / 温度默认 / stream_usage / thinking 开关）→ 叠 route runtime settings；**调用方显式 kwargs 最高优先级**（caller-wins）。 |
| **10 工厂 → 凭证（不落明文）** | 经 `CredentialProviderProtocol`（按 `credential_ref` 取明文 key）解析，明文 key 只进 ChatX init kwargs 的 `api_key`，**绝不写回 `ResolvedRoute`**；现状约束体现于 `_resolve_api_key`（`client_manager.py:1034-1055`）。 |
| **10 工厂输出（交 09 invoke）** | 一个原生 `BaseChatModel` 子类实例（`ChatAnthropic`/`ChatOpenAI`/`ChatGoogleGenerativeAI`，或必要时 deepseek 单方法子类），已配置 base_url（双保险后）、api_key、model、timeout、thinking、stream_usage 与 provider profile kwargs。09 拿它执行 `.invoke(原始 BaseMessage)`。 |
| **base_url 双保险（与 03 分工）** | 主修复 = [[03-orch-credentials-endpoints]] 保存 credential/endpoint 时按 protocol 归一化（每 protocol 固定规则）；本工厂只做**调用时幂等副保险**（已 canonical→no-op，未 canonical→按 protocol 修）。**工厂不能替代保存侧修复**（`client-layer-decision-record.md:169-180`、`baseline.md:65`）。 |
| **归属 / 稳定性** | `ResolvedRoute` 字段权威源 = [[04-orch-registry-schema]]；`ProviderProfile` 表归 [[11-inv-provider-profiles]]；本工厂**只消费不定义**，防 drift。 |

## 4. 设计决策基础(用户原话)

> **D1 方案 A'（保留编排外壳）**（决策记录 `:41`）："不用留A, 这是错误判断, 正确的是A'。" → 不删 `GatewayChatModel`、不裸返回 ChatX；本工厂只负责把 route 构造成 ChatX，编排外壳照旧。

> **D2 编排 / 调用分离**（决策记录 `:63`）："编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么。" → 本工厂是「调用」端构造器：输入一条 `ResolvedRoute`，输出可 invoke 的原生 ChatX。

> **F1 base_url 归一化（主在保存侧）**（决策记录 `:200-202`）："base_url 归一化的关键是每个protocol都有确定的统一的规则……如果结果足够确定, 我觉得放在credential保存时归一化是最好的, 每个endpoint都有固定格式, 存这个固定格式保证不会出错。" → 主修复在 03 保存侧；本工厂只做调用时幂等副保险，deerflow/deepagents 此步无范本可抄，自建。

> **通用判据（gateway = 富能力可复用网关）**（README §2）："换一个完全不同的应用装上 gateway，这个能力还原样能用吗？能 → 公共（gateway）。" → "把 route 构造成可调用模型"任何调模型 app 都要，故本模块纯 ③b 公共（新建）。

## 5. 决策 + 动机(决策原因)

1. 采用 A'，不采用 A。A' 保留 `GatewayChatModel` 编排外壳，只把真实调用改成原生 ChatX；A 会删除编排层，回归 fallback/probe/usage/metadata/predict 风险(`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:28-38`)。
2. 工厂接 `ResolvedRoute`，不是接 provider/model 字符串。deepagents 的 `resolve_model`(以 `provider:model` spec 调 `init_chat_model` 的 helper)；我们需要携带 route_id、endpoint_id、credential_ref、runtime settings 和 route metadata，所以只能借鉴模式，不能照搬接口(`temp/deepagents/libs/deepagents/deepagents/_models.py:15-36`; `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`)。
3. base_url 双保险必须在工厂里幂等执行。权威记录明确保存时归一化是主方案，但调用时仍要防线；deerflow/deepagents 假定 base_url 已经正确，没有可直接照抄的规则(`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:169-180`; `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:232-242`)。
4. deepseek patch 只借鉴“单方法覆盖”。`PatchedChatDeepSeek`(deerflow 的 DeepSeek ChatX 子类)只覆盖 `_get_request_payload` 来恢复 reasoning_content，不重写整套消息转换；这符合 MVP1 “原生 ChatX 为主，仅 payload 差异才子类覆盖单方法”的边界(`temp/deerflow/backend/packages/harness/deerflow/models/patched_deepseek.py:18-59`; `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:224-228`)。
5. 不直接抄 deerflow/deepagents 文件。deerflow `create_chat_model` 耦合 `AppConfig`/`resolve_class`/tracing；deepagents 用 `init_chat_model` + 自己的 profile registry 消费 `provider:model` 字符串。两者输入都与 gateway 的 `ResolvedRoute` 不一样 → **移植模式 + 具体逻辑进吃 `ResolvedRoute` 的 `RouteChatModelFactory`**，不搬文件(`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:260-262`)。

## 6. 测试关键点

> 来源 = 决策记录 §5「兼容性验证清单（A' 实现必过）」`:266-275`。本模块（构造工厂）对应其中与 ChatX 构造 / base_url / thinking / stream_usage / 异常形状相关的项。

- **base_url 双保险幂等**：已 canonical 的 base_url 经工厂 → no-op（不被二次修改）；未 canonical 的按 protocol 修到 ChatX 需要的形状（anthropic 去尾 `/v1`、openai 保持、deepseek-anthropic 去 `/v1` 后 `+/anthropic`、ark `.../api/v3`，F1）。
- **多轮 tool loop 空 content 回归（核心）**：实现工厂前先补失败测试，复现 qiniu-anthropic 多轮 tool loop 的空 content 回归；该风险来自旧 `_langchain_messages_to_dict`（`gateway_chat_model.py:661-692`、`client-layer-decision-record.md:34-38`），工厂 + 09 原始 `BaseMessage` invoke 应消除它（决策记录 `:269`）。
- **异常分类形状不回归（头号风险）**：ChatX retry（F2）耗尽后的异常仍能被 07 的 `classify_exception` 正确分类（fake 401→fallback、fake 400 非 capability→fail-fast、网络错→fallback）；决策记录列为兼容性验证项（`:187-193`、`:248-257`、`:268`）。
- **thinking blocks 不拍平**：工厂构造的 ChatX invoke 后，reasoning/thinking content blocks 经结果桥接仍保留 block 结构，不被 `_coerce_text` 压成字符串（F4，`:271`）。
- **stream_usage 默认开**：OpenAI-compatible ChatX 第三方 base_url 下 streaming 响应仍带 token usage（deerflow 经验，工厂显式补 `stream_usage`，F5，`:270`）。
- **deepseek payload patch**：若移植 `PatchedChatDeepSeek`，仅覆盖 `_get_request_payload` 恢复多轮 reasoning_content，不重写整套消息转换（决策记录 §4、`:256`）。
- **ark_runtime 适配确认**：`ark_runtime` 在 LangChain ChatX 下的目标适配方式需先确认（旧用 Ark 官方 SDK，不等同 OpenAI-compatible ChatX，§8 待办 2）。
- **predict 分支不回归**：保住 `GatewayChatModel` 类 + 构造器 + `bind_tools`，predict 自动不变（决策记录 `:273`）。
- **live 冒烟（非 CI 闸）**：`temp/probe_chatx.py` 5/5 人工跑通（`:275`）。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`RouteChatModelFactory`（**待新建**，建议落 `models.py` 或新 factory 模块）；现职责暂代管点 = `resolver.py:135-146`（实例化 `GatewayChatModel`）、`client_manager.py:144-295`（SDK client 工厂）、`client_manager.py:866-988`（protocol dispatch）。
- **③a** `apps/studio/backend`：N/A（本工厂纯构造层，不含应用加工四件事）。
- **② Rust**：N/A。
- **范本（temp，仅借鉴，不搬文件）**：`temp/deerflow/.../models/{factory.py,patched_deepseek.py}`、`temp/deepagents/.../{_models.py,profiles/provider/provider_profiles.py}`。

## 8. gaps / 待设计(待办/疑点)

1. 待办:实现 `RouteChatModelFactory` 前要补失败测试，复现 qiniu-anthropic 多轮 tool loop 的空 content 回归；该风险来自 `_langchain_messages_to_dict`(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-692`; `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:34-38`)。
2. 待办:确认 `ark_runtime` 在 LangChain ChatX 下的目标适配方式；当前源码用 Ark 官方 SDK，不等同于 OpenAI-compatible ChatX(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:257-295`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:962-981`)。
3. 疑点:ChatX retry 耗尽后的异常形状是否仍能被 `classify_exception` 正确分类，需确定性单测；权威记录已把它列为兼容性验证项(`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:187-193`; `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:248-257`)。
4. 待办（跨模块协调）:`call_method_id` / `request_mapper_id` 由本工厂消费还是由 [[11-inv-provider-profiles]] 的 `ProviderProfile` 消费，需与 11 §8 待办 2、09 §8 待办 3 一并定（同一悬案）。

## 已实现 / 与 baseline 差异

已实现:

1. `ResolvedRoute` 已经具备工厂所需的大部分输入字段，包括 protocol/base_url/credential/model/runtime settings(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`)。
2. `GatewayChatModel` 已经保留编排外壳和 fallback loop，MVP1 不需要重建这层(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:31-49`; `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:111-271`)。
3. client_manager 已经有 usage 统计、probe、mark-down 等可保留设施(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:53-132`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:310-368`)。

未实现:

1. `RouteChatModelFactory` 源码尚不存在；当前真实调用仍由 `LLMClientManager._dispatch_provider_call` 和 `_call_*` 完成(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:866-988`)。
2. 原始 `BaseMessage` 尚未直接交给 ChatX；现状仍先转 dict(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:104-107`; `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:661-692`)。
3. base_url 调用时幂等归一化尚不在现有调用路径；现状 `_get_openai_client`、`_get_anthropic_client`、`_get_google_client`、`_get_ark_client` 都原样使用 `route.base_url`(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:162-170`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:201-205`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:243-245`; `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:283-285`)。

## 代码索引 clues

- `RouteChatModelFactory`:拟新建调用层工厂，用 `ResolvedRoute` 构造 `ChatAnthropic`、`ChatOpenAI`、`ChatGoogleGenerativeAI` 等原生 ChatX(`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:157-163`)。
- `ResolvedRoute`:一条 runtime-ready route candidate，保存协议、base_url、凭证引用、provider model id 与 runtime settings(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`)。
- `GatewayChatModel._generate`:保留编排外壳；MVP1 只替换它的调用步骤，不替换整个类(`packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:96-271`)。
- `LLMClientManager._get_openai_client/_get_anthropic_client/_get_google_client/_get_ark_client`:现状 SDK client 工厂；MVP1 真实调用不再走这些 factory，但 probe 可继续使用(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-295`)。
- `LLMClientManager._dispatch_provider_call`:现状按 protocol 分发真实调用；MVP1 由 ChatX invoke 替代(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:866-988`)。
- `deerflow.models.factory.create_chat_model`:deerflow 的模型创建函数，展示 thinking、stream_usage、tracing 等构造期处理，但它依赖 deerflow AppConfig，不适合直接搬(`temp/deerflow/backend/packages/harness/deerflow/models/factory.py:50-171`)。
- `deepagents._models.resolve_model`:deepagents 的字符串 spec 到 `BaseChatModel` helper，展示 `init_chat_model` 与 provider profile 组合方式(`temp/deepagents/libs/deepagents/deepagents/_models.py:15-36`)。

## 交叉引用(链接,不复制)

- [[09-inv-invocation-runtime]]：invoke 运行时（拿本工厂构造的 ChatX 执行 `.invoke()`，结果桥接 / thinking 不拍平 / usage 在那边写）
- [[11-inv-provider-profiles]]：`ProviderProfile` init-kwargs 表（本工厂第 6 步调它合 provider 差异；`call_method_id`/`request_mapper_id` 归属悬案共享）
- [[03-orch-credentials-endpoints]]：base_url 保存时归一化 = 主修复（本工厂只做调用时副保险，不替代）
- [[01-handoff-interface]]：`ResolvedRoute` 契约（工厂唯一输入）
- [[04-orch-registry-schema]]：`ResolvedRoute` 字段权威源（本工厂只消费）
- 决策记录 `client-layer-decision-record.md` M6/D1/D2/F1/F4/F5/F6/§4 / 归属表 `module-disposition-revised.md`（§4 判 10 纯 ③b 新建）
