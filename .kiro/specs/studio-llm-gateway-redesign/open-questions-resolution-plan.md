---
status: Proposed (待用户过目)
created: 2026-06-02
owner: Claude (架构) — 真机脚本 codex 落地、调研 Claude、设计裁定关键取舍呈用户
context: 承接 client-layer-decision-record §5 去风险 + Gemini audit + 本轮代码核实
---

# 开放问题去风险方案（测试 / 调研 / 设计）

> 分类原则：
> - **TEST（真机）**：假设只能用系统**真实运行路径的 SDK**验证（memory `real-machine-verification`）。「我记得/应该」一律先测。
> - **RESEARCH（调研）**：需查外部库 / 现状代码 / 范本才能定方案。
> - **DESIGN（裁定）**：取舍题，出方案/选项；架构取舍呈用户。

---

## Bucket 0 — 已通过读代码解决（给结论，不必再测/研）

### 0.1 参数修正链闭环（#5 params 轴）= 端到端**已存在**
证据链：probe → `ProviderRoute.capabilities` → 两处读取：
- (a) studio `materialize_role._apply_intent`（`llm_role_materializer.py:157-269`）把 capabilities（thinking、max_output_tokens）烤进 `RoleRouteEntry.runtime_settings`；
- (b) gateway `resolve_role._effective_runtime_settings`（`registry/resolver.py:106,156-270`）把 `route.capabilities` 合并成 `effective_runtime_settings`（带 provenance）；
- → `gateway_chat_model.py:562-622` 一组 helper 把 effective 应用到真实请求（temperature/max_output_tokens/reasoning budget/structured_output/tool_choice）。

**结论**：「参数轴」闭环通。剩两件：① 模块08 文档没写这条链 → 文档补（归 #5）。② 还发现 capabilities 被读了**两次**（studio materialize + gateway resolve），职责重叠 → W3 后端迁入后要定谁主谁副，避免双重应用。

### 0.2 route-first API（`resolve_routes`）= 数据其实**已经在流**
证据：copilot（`copilot.py:429`）和 studio router（`llm.py:4596`）都直接调 `resolve_role(...)` 拿 `ResolvedRole.routes` 自用；只有 `ModelResolver.resolve()`（`resolver.py:93`）包成 `BaseChatModel` 给 graph-agent。

**结论**：D2（编排/调用分离）在 `resolve_role` 这层基本已落地。`resolve_routes()` 不是从零造，而是「把 copilot 已经在做的事正名」：在 `ModelResolver` 暴露 `resolve_routes(role)->ResolvedRole` 公共方法（让 copilot 别 reach 进内部函数），`resolve()` 改成调它再包 ChatX。低风险，归 #1 设计。

### 0.3 健康/熔断双源机制 = 已读清 → 转 DESIGN（见 D1）
`SqliteLlmHealthStore`（持久 circuit，`llm_health_store.py`）vs `client_manager._provider_down_cache`（进程内，`client_manager.py:51,340-368`）。机制清楚 → 是裁定题不是测/研。

### 0.4 `probe_import_draft` 桩 = 已确认 → 转 SCOPE（见 D2）
`llm.py:872-876`，docstring 自陈「real agent probing is handled by a later worker」。

---

## Bucket A — 需真机测试（TEST）

### T1. ChatX 异常 → `classify_exception` 真机分类 ★A' 头号风险
**逻辑**：A' 的错误恢复（401→fallback、400→fail-fast、网络→retry）全靠 `classify_exception` 读异常 HTTP 状态码（`error_classification.py:_status_code ~:223-232`）。现状按「自研 `_call_*` dispatch 抛的异常形状」写。换原生 ChatX 后，抛的是 langchain 包装的 SDK 异常（`anthropic.APIStatusError`/`openai.APIStatusError`/`httpx.HTTPStatusError`/google），结构不同。若 `_status_code` 取不到 → 分类全错 → fallback/熔断**静默失效**。这是 A' 最大且未验证的假设，必须真机测。
**方案**：扩 `temp/probe_chatx.py`。每 protocol（anthropic/openai/google/ark）造：①假 key(401) ②假 model(404) ③非法参数(400) ④假 base_url/断网(网络)。捕 ChatX 真实异常 → 打印 type/属性/能否取 status_code → 喂 `classify_exception` 断言分类符合真实语义表。再测 `max_retries`(默认2) 耗尽后异常仍可分类。
**解锁**：是否要给 `_status_code` 加「解包 langchain/SDK 异常」分支。**Phase C 进入闸**。
**谁做**：用例/逻辑 Claude，脚本 codex，真机跑（用 creds 文件已配 endpoint）。

### T2. base_url 每 protocol 规则真机巩固
**逻辑**：F1 = 保存时归一化成 canonical，规则已定（anthropic 去 `/v1`、openai 保持、deepseek-anthropic 去`/v1`+`/anthropic`、ark `/api/v3`）。handover 明说「锁定前再真机测巩固」—— 历史上多次用错格式才失败，需真机确认每条规则 work、错误格式确实失败（证明归一化必要）。事实确认，不能靠记忆。
**方案**：每 protocol 真 endpoint，canonical 发 1-token 确认 200；错误格式（如 anthropic 带 `/v1`）确认失败。记录。
**解锁**：锁定每 protocol canonical 规则，喂保存时归一化（W0 `upsert_endpoints`）+ factory 双保险。

### T3. lint raw vs effective capabilities（构造单测，非真机）
**逻辑**：已读 `lint.py:44` —— lint 用 RAW `route.capabilities`，非合并 verified profile 后的 effective。`VerifiedProfile` 带 `capability` 字段（被测过的能力）。疑点：若某能力只在 verified profile 里被证明、`route.capabilities` 没有/未标 probed_verified，raw lint 会误判 `requires_probe` blocking → 解析期被 lint 卡死，即使能力其实可用。
**方案**：构造单测 —— route：capabilities 缺某能力但有覆盖它的 VerifiedProfile；role 该能力设 `error` lint。跑 `resolve_role` 看是否误 block；对照组（capabilities 标 probed_verified）。
**解锁**：lint 用 raw 还是 effective（或 profile 能力回填 capabilities）。正确性题，可能改 `resolve_role` 给 lint 的入参。
**谁做**：用例 Claude，单测 codex。

### T4. A' 末跳参数映射验收（Phase C）
**逻辑**：承 0.1 —— 现状 `gateway_chat_model.py:562-622` 把 effective 应用到自研 dispatch。A' 换 ChatX 后这些参数必须改成 ChatX 的 init-kwargs/invoke（factory 10 + profiles 11 承接），要测确认参数真到达 provider、没被迁移悄悄丢。
**方案**：Phase C 验收单测 —— 一条 route 设非默认 max_output_tokens + reasoning budget，经 factory build 的 ChatX invoke，断言请求体带上这些值（mock transport 截请求或真机看响应）。
**解锁**：A' 验收线之一，保参数闭环不被迁移破坏。

---

## Bucket B — 需调研（RESEARCH）

### R1. Ark（火山引擎）运行期 → 原生 ChatX 映射
**逻辑**：A' 假设每条 route 都能 build 原生 ChatX。anthropic/openai/google 有成熟 langchain 包；Ark 不一定有干净 native ChatX。若没有，factory(10) 对 ark route 落不了地 → W1 可行性风险，必须先调研再设计 factory。
**方案**：① 查 langchain 生态有无 ChatArk/langchain-volcengine（WebSearch+PyPI，走 web-access skill）；② 读现状 ark 调法 —— `client_manager` ark 分支 + copilot `_ark_anthropic_base_url`（`:476`，ark 有两种：openai-compat `/api/v3` 与 anthropic-over-ark `/api/compatible`）；③ 看 deerflow/deepagents 有无 ark。
**候选结论（待证）**：ark openai-compat 多半能用 `ChatOpenAI`+自定义 base_url(`/api/v3`)；anthropic-over-ark 用 `ChatAnthropic`+base_url。若成立则 ark 只是 factory 一条 protocol 映射，无需特殊 ChatX。
**真机收尾**：选定候选 ChatX 真机对 ark 发 1-token。
**解锁**：factory(10) 的 ark 映射策略；要不要给 ark 写 provider-profile 子类。
**谁做**：调研 Claude（联网 web-access、读码），真机 codex。

---

## Bucket C — 设计裁定（DESIGN）

### D1. 健康/熔断 SSOT 双源：统一 / 单向同步 / 分离 ★需你拍
**逻辑**：两套语义其实不同：
- 持久 `SqliteLlmHealthStore`（route/endpoint/bucket scope，retry_at，reason_code）=「测试/探活结论 + cooling_down」，studio `materialize_role` 用它**门控哪些 route 进链** + UI 就绪灯 →「该不该提供这条 route」的持久判断。
- 进程内 `_provider_down_cache`（monotonic TTL）=「这条 route 刚 live 失败，TTL 内别试」，gateway 运行期 fallback 用 →「此刻先跳过」的瞬时判断。
- 现状完全不通：运行期 mark-down 不落持久库（UI/下次看不到）；持久 cooling_down 不被运行期 fallback 读。

用户核心目标「探测→持久化→复用修正正式调用」隐含「持久结论该影响运行期」。三方案：
- **a 统一**：运行期也读写持久库（一个 SSOT）。最贴核心目标，但 gateway-core 耦合 SQLite（违 D3 边界，远端化要换存储）。
- **b 单向同步（推荐）**：两套各管各（瞬时 vs 持久），加单向桥 —— 运行期 mark-down 异步回写持久库一条 circuit（UI/下次可见）；持久 cooling_down 在 resolve/materialize 就把 route 排出链（已做）；运行期 fallback 仍只信进程内 cache（瞬时自愈不污染持久结论）。
- **c 分离+文档化**：承认两个关注点，明确职责不连。最省事，但「复用」打折。
**解锁**：#1 的「熔断/健康 SSOT 落 core 还是 adapter」。**推荐 b，请你拍**。

### D2. probe_import_draft 真实 worker 是否本期范围 ★需你定优先级
**逻辑**：import-draft 探测是 agent 导入新 provider 时的草稿探活，与 role/copilot test 真机探活是两条线。现为桩。
**方案**：建议**本期不做**真实 worker（属 provider 导入向导线，非 A'/核心调用闭环必经），登记 deferred-items，导入向导单独排。若你认为「探测能力边界」必须含 import-draft 自动探活，则升本期。**优先级你定**。

### D3. ProviderProfile（11，新）vs VerifiedProfile（registry，现有）命名/职责
**逻辑**：两个都叫 profile 但不同：`VerifiedProfile`（`schema.py:189`）=「这条 route 测出的一种可用**调用法**」(capability/method_id/request_mapper_id，registry 数据，resolve 时 `select_verified_profile` 选一个)；`ProviderProfile`（新，deepagents 模式）=「provider/model → **init-kwargs 声明表**」(headers/温度默认/thinking 开关，factory 装 ChatX 用)。命名撞车会混淆「选调用法」与「装 kwargs」。
**方案**：重命名新模块（候选 `ProviderInitProfile`/`ChatModelProfile`/`ProviderAdapterProfile`），#1 文档画清边界：VerifiedProfile=测出的能力调用法（数据/编排），新 profile=装配 ChatX 的 init-kwargs（调用层）。

### D4. 小项（Claude 核实后直接给方案）
- **snapshot_version 谁赋值**：`ResolvedRoute` 有字段但 `resolve_role`（`registry/resolver.py:77-113`）构造时没赋。→ 构造时从 snapshot 注入，或显式标「本期不用」。归 #1/W0。
- **skipped_diagnostics 字段**：`materialize_role` 已产 `skipped_provider_details`（report 内，`llm_role_materializer.py:37,52`），但 `ResolvedRole` schema 无结构化字段。→ 给 `ResolvedRole` 加 `skipped` 字段供前端追溯。归 W0-Phase2 + schema。
- **notable_model_ids 标题脆弱**：强依赖 `## 4. Notable Model IDs` 精确匹配 → 微调静默失效。→ 加守卫（匹配失败 WARNING，不静默返回空），对齐无静默失败铁律。

---

## 执行顺序建议
1. **先 T1（头号风险）+ R1（Ark 可行性）** —— 结论若坏，A'(W1) 设计要变，必须最先探。
2. **T2 / T3** 并行，低成本。
3. **D1/D2/D3 裁定**：D1 需你拍（架构取舍），D2 需你定优先级，D3/D4 Claude 出方案过目。
4. **T4** 是 Phase C 验收线，实现期做。

## CCB 分工
真机 probe 脚本逻辑/用例 Claude 出 → codex 落地+跑；调研 Claude（联网走 web-access）；设计裁定 Claude 出方案，D1/D2 关键取舍呈用户；不写产品代码。

---

## 进展记录（2026-06-02）

### R1 结论 — Ark 不是 A' 的 blocker
调研（web-access：WebSearch + PyPI 一手页）：
- **推荐：`ChatOpenAI`（langchain-openai 一方包的 OpenAI 聊天模型类）+ base_url `https://ark.cn-beijing.volces.com/api/v3`**（Ark 的 OpenAI 兼容端点）。多源证实可用，支持 tool calling + streaming usage（就是完整 ChatOpenAI）。已知坑：reasoning 模型在 tool-loop 里可能要 `use_responses_api=True, use_previous_response_id=True` → 归 provider-profile（模块11 init-kwargs 表）处理。
- **否决 `langchain-ark`（`ChatArk` 类）**：社区个人维护、PyPI 未验证、最后发版 2024-12（v0.1.5）、文档稀疏、tool/usage 支持未注明。质量关键路径不依赖低维护 fringe 包。
- **否决 `VolcEngineMaasChat`（langchain_community）**：旧 MaaS API（access/secret 双钥），与现状新 Ark runtime SDK（`volcenginesdkarkruntime`，API-key）不是一代。
- **现状对照**：`_get_ark_client`（client_manager.py:258）现在走火山官方 SDK；A' 下 factory 把 `ark_runtime` route 映射成 `ChatOpenAI(/api/v3)`。
- **逼出的设计决策（归 #1/factory）**：schema Protocol 里 `ark_runtime` 是独立协议字面量。A' 下两选：(i) 保留 `ark_runtime`、factory 内部映射成 ChatOpenAI；(ii) 把 ark endpoint 当 `openai_compatible`(/api/v3) 配置、factory 无需特判。倾向 (ii)，待确认现有配置迁移成本。
- **剩一项真机确认**：ChatOpenAI+/api/v3 跑我们自己的 tool-loop + thinking 是否真顺 → 并入 T1/Phase-C 冒烟。
- **用户裁定（2026-06-02，看火山官方说明后定）**：ark 文本模型 → `ChatOpenAI(/api/v3)`，和 deepseek 同套路（原生 ChatX 接兼容端点，provider 差异用 profile 兜）；**官方 Ark SDK 路径不删**（`volcenginesdkarkruntime` 依赖 / `_get_ark_client` / `_call_ark_runtime` / `ark_runtime` 协议 / `[ark]` 可选 extra）——保留为**休眠备用调用法**，留给未来多模态模型 / 官方 SDK 专属能力（多模态、批量推理、上下文缓存、Responses API；见火山官方 SDK「全能力覆盖」）。
  - **架构含义（重要）**：这坐实了「**L3 调用层按 route 的 method 可插拔**」——**判据是模态/任务类型，不是「常见 vs 罕见」：LLM 语言推理模型（text→text）走原生 ChatX**（A'）；多模态模型 / 需官方 SDK 专属能力的 route 走专属 invoker（保留/可插，如 ark 多模态→官方 SDK；copilot→claude_agent_sdk）。所以 **A' 不是「删光自研 dispatch」**：openai/anthropic/google + ark-文本 退役换原生 ChatX，唯独 ark 官方 SDK dispatch（`_call_ark_runtime`）作休眠保留、不删。给 Q6 的 `method`（调用方法）术语一个落点：method = 选哪个 invoker。
  - 旁证 F2（retry）：火山官方 SDK 默认自动重试 2 次（瞬时故障）——与我们「保留瞬时重试、不设 0」一致。

### T1 用例（交 codex 落地，扩 `temp/probe_chatx.py`）
目标：验证原生 ChatX 抛的异常能被 `classify_exception` 正确分类——即 `_status_code`（error_classification.py:223，沿 `__cause__` 链找 `.status_code`/`.response.status_code` 的函数）能取到码，网络错能被 `_has_network_failure`（:235，认 httpx.ConnectError/TimeoutException）识别。
矩阵 = 4 协议 × 失败类型：
- 协议→ChatX：anthropic_compatible→`ChatAnthropic`；openai_compatible→`ChatOpenAI`；google_genai→`ChatGoogleGenerativeAI`；ark_runtime→`ChatOpenAI`+/api/v3。
- 失败→期望（对真实语义表）：①假 key=401→fallback_allowed/fallback_route/credential ②假模型=404→fallback_allowed/fallback_route/route ③非法参数=400 非 capability→fail_fast/fail_request/request ④死地址=网络错→fallback_allowed(retry_same_route) ⑤（可选，难稳定诱发）429/5xx、400-capability→fake 注入做确定性单测补。
- 每条：捕异常→`classify_exception(exc)`→断言 decision/action/scope==期望；并打印 `type(exc)`/`repr`/`_status_code(exc)` 取到没/`__cause__` 链（失败时看清状态码藏哪）。
- 补：ChatX `max_retries`（默认）耗尽后（死地址诱发网络错最易）最终异常仍能分类。
- 两模式：真机（creds 文件真 endpoint，401/404/网络可靠诱发）+ fake 单测（构造各 SDK 异常形状，CI 可跑）。
- 产出：protocol×failure 表（异常类型/取到码？/分类结果/期望/PASS-FAIL）。通过线：每协议真实异常都分类正确；若某协议把状态码藏在 `_status_code` 找不到处 → 结论=给 `_status_code` 加解包分支。
