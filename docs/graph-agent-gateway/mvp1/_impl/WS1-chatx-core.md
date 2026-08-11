---
ws_id: WS-1-chatx-core
modules: [11, 10, 09, 07]
depends_on: []   # 不被 WS-2 阻塞:base_url 共享原语由本 WS 步骤 0 自产,WS-2 反过来 import 它
blocks: [WS-5]
owns_files:
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/base_url.py    # 新建(步骤0:canonicalize_base_url 共享原语;WS-2 import)
  - packages/graph-agent-gateway/src/graph_agent_gateway/call/profiles.py   # 新建(11)
  - packages/graph-agent-gateway/src/graph_agent_gateway/call/factory.py  # 新建(10),或并入 models.py
  - packages/graph-agent-gateway/src/graph_agent_gateway/call/models.py              # 改(10 落点候选)
  - packages/graph-agent-gateway/src/graph_agent_gateway/call/chat_model.py  # 改(09/07)
  - packages/graph-agent-gateway/src/graph_agent_gateway/call/clients.py      # 改(09 _call_*/dispatch · 07 token-escalation)
  - packages/graph-agent-gateway/src/graph_agent_gateway/call/resolver.py            # 改(09:resolve 构造 ChatX 那段)
  - packages/graph-agent-gateway/pyproject.toml                                # 改(google_genai 可选依赖,见 §5 注)
spec_ssot:
  - ../11-inv-provider-profiles/mvp1-alignment.md §1/§2/§3/§6
  - ../10-inv-route-chat-model-factory/mvp1-alignment.md §1/§2/§3/§3.5/§6
  - ../09-inv-invocation-runtime/mvp1-alignment.md §1/§1.5/§2/§3/§6
  - ../07-orch-fallback-circuit-probe/mvp1-alignment.md (token 升级搬家 + 编排外壳保留)
status: drafted
---

# WS-1 调用核心(ChatX 迁移)— 任务书

## 1. 目标(intent + why)

把 gateway 的「一条 route 的实际调用」从自研 `_call_*`(手写消息转换 + provider payload + 响应解析)换成**原生 LangChain ChatX 的 `.invoke()`**,并新建两块支撑:`ProviderProfile`(provider 差异 init-kwargs 表)、`RouteChatModelFactory`(`ResolvedRoute`→`BaseChatModel` 构造器)。**为什么**:现有 `_langchain_messages_to_dict` 把带 tool_calls 的空-content `AIMessage` 转成空 content dict,导致多轮 tool loop 在 anthropic 上 `400 content must not be empty`(头号 bug);A' 决策用原生 ChatX 接管转换/调用/解析,但**保留 `GatewayChatModel` 编排外壳**(fallback/probe/熔断/usage 不动)。目标机制以 spec_ssot 为准,不在此复制。

## 2. SSOT 指针(grounding,IR2/IR5)

- **目标(怎么做)**:见 frontmatter `spec_ssot`(11/10/09 的 alignment;07 的 token 升级搬家)。
- **现状(起点)**:`../09-.../baseline.md`、`../10-.../baseline.md`(诚实声明无 factory)、`../11-.../baseline.md`(诚实声明无 ProviderProfile)。
- **范本/参考**:`../references/chatx-provider-patterns.md`(deepagents `ProviderProfile` lookup/merge/pre_init/factory;deerflow thinking 归一化 / `stream_usage` / `PatchedChatDeepSeek` 单方法 patch;`GenericRouteChatModel` 5 条序列化规则,已真机 PASS)。
- **实现前必读源码(先读并确认关键符号再动手)**:
  - `call/clients.py:440-1012`(`_call_openai_compatible`/`_call_openai_responses`/`_call_google_genai`/`_call_ark_runtime`/`_call_anthropic_compatible`/`_call_wavespeed_any_llm`/`_dispatch_provider_call`/`_call_with_token_escalation` — 要被 ChatX 取代/搬家的现状)
  - `call/chat_model.py:96-271`(`_generate` 编排循环)、`:313-357`(`_build_chat_result`)、`:645-707`(`_coerce_text`/`_langchain_messages_to_dict` — 要退役的拍平/转 dict)
  - `call/clients.py:144-295`(SDK client 工厂,probe 仍复用)、`:310-323`(`record_usage`)
  - `resolver.py:92-146`(`ModelResolver.resolve` 现在如何包成 `GatewayChatModel`)
  - `registry/schema.py:415-459`(`ResolvedRoute`/`ResolvedRole` 字段,**只读**)

## 3. 文件归属(并发锁,IR1)

- **本 WS owns(可改/建)**:见 frontmatter `owns_files`。
- **禁止触碰(别的 WS 的)**:
  - `registry/storage.py`、`apps/studio/.../llm_credentials.py` → **WS-2**(WS-2 保存侧归一化;它 `import` 本 WS 步骤 0 产的 `registry/base_url.py`,方向不反)
  - `registry/resolver.py`(`resolve_role` skip)、`protocol.py` → **WS-5**
  - `events.py`/`exceptions.py`/`tracing.py` → **WS-4**
  - `apps/studio/.../llm_state_projection.py` 等 → **WS-3**
- **共享文件协调**:`call/chat_model.py`/`call/clients.py` 被本 WS 步骤 09 和 07 都改 → **靠内部串行(§7)解决,不并发编辑**。

## 4. 现状锚点(baseline)

现无 `RouteChatModelFactory`、无 `ProviderProfile`;真实调用走 `LLMClientManager._dispatch_provider_call`+`_call_*`;`resolver.py` 把 role 解析后包成 `GatewayChatModel`。详见各 baseline。

## 5. 目标行为(可测的契约)

- **ProviderProfile(11)**:`register_provider_profile(key, profile)`(key=`provider` 或 `provider:model`,重复注册 additive 合并);`get_provider_profile(spec)`(exact model 叠在 provider 之上);`apply_provider_profile(spec, **caller)` → init-kwargs(合并序 `pre_init`→`init_kwargs`→`factory`→**caller-wins**)。**不接 `ResolvedRoute`、不 invoke、不选型**;**不与 `VerifiedProfile` 合并**。
- **RouteChatModelFactory(10)**:`build(route: ResolvedRoute) → BaseChatModel`。流程:解析凭证(经 `CredentialProviderProtocol`,不落明文)→ base_url 调用时**幂等**副保险(import 步骤 0 的 `registry/base_url.py`,已 canonical 则 no-op)→ 按 `route.protocol` 选官方 ChatX(`anthropic_compatible→ChatAnthropic`、`openai_compatible→ChatOpenAI`、`google_genai→ChatGoogleGenerativeAI`、**`ark_runtime→ChatOpenAI`**)→ 无官方则 `GenericRouteChatModel` 兜底 → 第 6 步调 `apply_provider_profile` 合 init-kwargs → 返回 `BaseChatModel`。**只构造,不 invoke**。
- **invocation(09)**:`_generate` 保留编排外壳,第 1 步不再 `_langchain_messages_to_dict`(原始 `BaseMessage` 直接交 ChatX);第 5/7 步:用 10 的 factory 构造 ChatX → `.invoke()` → `AIMessage`;`_build_chat_result` **augment**(非重建)注入 `{route_id,endpoint_id,canonical_id,protocol,provider_model_id,effective_runtime_settings,usage}`,从 `AIMessage.usage_metadata` 取 usage,**thinking content blocks 不拍平**(不再 `_coerce_text`)。退役 `_call_*` 的「消息转换 + provider 调用/解析」两件;`system_prompt_prefix` 改以 `SystemMessage` 合并/插入。
- **orchestration(07)**:`GatewayChatModel` 不删;`_call_with_token_escalation`(截断升级重试)从 `_call_*` 内**搬到编排层**包住 ChatX invoke,不删;probe/熔断/mark-down/usage 归属保留;ChatX 自身有界瞬时重试(F2)不禁用。
- **格式中立(09 §1.5)**:三张脸都在 —— ChatX 面(factory 产 `BaseChatModel`)、普通 chat 面(repurposed `_call_*` 内核,返非-LangChain)、route handoff(只给 route);ChatX 面与普通 chat 面**共用同一调用内核**。

> **依赖补全(Codex 已核)**:`langchain_google_genai` 当前不可导入;实现 `google_genai→ChatGoogleGenerativeAI` 需补依赖。建议照 `ark` 先例做成**可选 extra**(`graph-agent-gateway[google]`)+ **lazy import**(构造时 `importlib`,未装则报清晰错),`pyproject.toml` 已纳入 owns_files。Codex 可定 core-dep 还是 extra,但要与 ark 模式一致。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

> 抽自 09/10/11 alignment §6 的「兼容性验证清单」。标 ★ 的是**先写失败测试(TDD RED)**。

- ★ **多轮 tool loop 空-content 回归(核心)**:复现 qiniu-anthropic 多轮 tool loop(旧路径 `AIMessage(content="")`+tool_calls → 空 content dict → `400`);原始 `BaseMessage` 交 ChatX 后应消除。
- ★ **异常分类形状不回归(头号风险)**:ChatX 瞬时重试耗尽后的异常仍被 `classify_exception` 正确分类(fake 401→fallback、fake 400 非 capability→fail-fast、网络错→fallback)。**真实分类语义权威源 06,不改 06**。
- **base_url 双保险幂等**:已 canonical→no-op;未 canonical 按 protocol 修(anthropic 去尾 `/v1`、openai 保持、deepseek-anthropic 去 `/v1` 后 `+/anthropic`、ark `.../api/v3`)。
- **thinking blocks 不拍平**:reasoning/thinking content blocks 经 `_build_chat_result` 仍保 block 结构。
- **stream_usage 默认开**:OpenAI-compatible 第三方 base_url streaming 仍带 usage。
- **ProviderProfile lookup + caller-wins**:exact model 叠 provider;caller(route runtime settings)压 profile default。
- **`VerifiedProfile` 不被吞 / capability 不动态选型**:`select_verified_profile` 仍在解析层正常;profile 表不引入按 capability/price 搜索替代 route。
- **ark_runtime 适配回归**:目标改 `ChatOpenAI` 时,**必须同步改写**现状那条「ark 不得走 OpenAI-compatible client」的测试(别把旧实现测试当目标约束)。
- **predict 分支不回归**:保住 `GatewayChatModel` 类 + 构造器 + `bind_tools`;`PredictGatewayChatModel._generate` 全自走、返回类型/契约不变。
- **deepseek payload patch 仅单方法**:若移植 `PatchedChatDeepSeek`,只覆盖 `_get_request_payload`,**不重写整套消息转换**。
- **usage 维度对齐**:`AIMessage.usage_metadata` → `record_usage` 按 endpoint 累计不丢。
- **真实 e2e(非 CI 闸,但必须真跑)**:`chatx-provider-patterns.md` 的 live 冒烟 5/5(`GenericRouteChatModel` 经 `create_agent` 跑通工具循环)。

## 7. 内部子步骤顺序(严格串行,IR1 共享文件)

0. **base_url 共享原语**(新文件 `registry/base_url.py`):纯函数 `canonicalize_base_url(url, protocol)`(幂等;anthropic 去尾 `/v1`、openai 保持、deepseek-anthropic 去 `/v1` 后 `+/anthropic`、ark `.../api/v3`、wavespeed root)+ 逐 protocol 单测。**WS-1 自产、WS-2 import**(替代原"等 WS-2 给桩"方案:no-op 桩过不了 §6 base_url 测试;真桩与 WS-2 重复 = divergence)。
1. **11 ProviderProfile**(新文件 `call/profiles.py`,加法,最独立)。
2. **10 RouteChatModelFactory**(新文件,消费 11;import WS-2 的 base_url helper —— 若 WS-2 未就绪,先用桩,WS-2 落地后替换)。
3. **09 接线**(改 `call/chat_model.py`/`resolver.py`/`call/clients.py`:`_generate` 换调用步、`_build_chat_result` augment、退役 `_call_*` 转换/调用)。
4. **07 接线**(改 `call/chat_model.py`/`call/clients.py`:搬 `_call_with_token_escalation` 到编排层、保留外壳)。

## 8. 验收标准(硬退出,IR4)

- [ ] §6 全部测试绿(含 ★ 两条先 RED 后 GREEN)。
- [ ] `RouteChatModelFactory.build(route)` 对 4 种 protocol 返回正确官方 ChatX,非标走 `GenericRouteChatModel`。
- [ ] `apply_provider_profile` 合并优先级 + caller-wins 有确定性单测。
- [ ] **无回归**:异常分类形状、predict 分支、thinking 不拍平、usage 归属 —— 各有专测且绿。
- [ ] ark 旧「不得走 OpenAI client」测试已随目标改写(无 stale 测试残留)。
- [ ] 至少一条**真实 e2e**(generic adapter 经 `create_agent` 工具循环)人工跑通并记录。
- [ ] `uv run pytest packages/graph-agent-gateway/tests -q` 全绿;`uv run mypy`(改动文件)0 error。

## 9. 不做(范围锁定,IR7)

- 不改 `registry/storage.py` / studio `llm_credentials.py`(WS-2)、`registry/resolver.py` skip(WS-5)、`events/exceptions/tracing.py`(WS-4)、studio projection(WS-3)。
- **不整块删 `client_manager`**:probe 探活、熔断 TTL、usage 统计、SDK client(probe 用)保留;只退役「消息转换 + provider 调用/解析」。
- **不重写整套消息转换**:provider 差异进 `ProviderProfile` init-kwargs;仅 payload 必须改才子类覆盖单方法。
- 不动 06 错误分类本体、不动 predict、不做 05 下沉。
- 范围外问题 → 记 `docs/deferred-items.md`。

## 10. baseline 回写指令(IR6,实现后)

实现落地后,照真实代码改这些 baseline 的「现状」与「Baseline/Alignment 差异」:
- `11-.../baseline.md`:`ProviderProfile` 已存在(指真实新文件:符号)。
- `10-.../baseline.md`:`RouteChatModelFactory`/`GenericRouteChatModel` 已存在;删「本模块现源码不存在」。
- `09-.../baseline.md`:`_call_*` 已退役/repurposed、`_build_chat_result` 已 augment、usage 改 `usage_metadata`。
- `07-.../baseline.md`:`_call_with_token_escalation` 已搬编排层。
- 回写后 baseline = 真实代码(此时「目标当现状」物理上不可能)。

## 11. 评审检查点

- **契约门(Claude 审测试,放 Gemini 前)**:重点查 ★ 两条(qiniu 空-content、异常分类形状)是否**忠实编码** alignment §6 的目标(尤其分类的 fake 401→fallback / fake 400 非 capability→fail-fast 三例是否齐),以及 ark 测试是否按目标改写而非沿用旧约束。
- **Codex 审查退出** = §8 全满足(非主观满意)。
- **Claude 终审**:① 合不合 A'(编排外壳保留、只换调用);② baseline 回写是否诚实(对真实代码);③ 测试非假绿(异常分类/e2e 不是 mock 到绿)。
