# Research — 取证与现状(论据先行)

> 本文件只陈述**坐实的事实**(文件:行号 / 真机日志 / 引文)。设计结论在 `design.md`。
> 取证日期 2026-06-30,代码基线 `main` @ `98a65e3e`。真机数据目录:`%APPDATA%\AgentStudio`。

## 0. 真相源面板(settings General 最下方)与本 spec 的关系

- General 最下方 = 「真相源」卡片,数据来自 `getTruthSources()`,渲染于
  [GeneralTab.tsx:253-272](../../../apps/studio/frontend/src/components/studio/settings/GeneralTab.tsx)。
- 后端注册表 [runtime_truth_sources.py:82-190](../../../apps/studio/backend/app/services/runtime_truth_sources.py):
  三个退役 catalog 文件已移除,社区同步日志归 `llm_credentials`(上游 spec C1)。
- **真机磁盘仍有** `community_catalog_cache.json` / `llm_probe_catalog.json` / `community_upload_queue.json`
  (`%APPDATA%\AgentStudio\llm`,Jun 29 创建)→ 说明**当前运行的是 Phase 9 之前的旧构建**;重测前需重建 sidecar。

## 1. endpoint 测试现状(只有连通性,无 method 穷举)

`test_endpoint`([llm.py:703-914](../../../apps/studio/backend/app/routers/llm.py)):
1. `_gateway_test_provider_endpoint(endpoint)` 发 **get-models**(列模型,**无需 model**)。
   - ok 且有模型 → `discovered_model_ids`;**ok 但空表** → message「Endpoint reachable but returned no models」,
     `status=unverified_manual`,`model_list_reached=True`([llm.py:723-727](../../../apps/studio/backend/app/routers/llm.py))。
   - 非 ok → `_endpoint_probe_failure_message`。
2. official:get-models 可达即 `verified`([llm.py:790-794](../../../apps/studio/backend/app/routers/llm.py))。
3. 第三方:必须真发生成 `_verify_third_party_endpoint_by_probe`([llm.py:4792-4892](../../../apps/studio/backend/app/routers/llm.py)),
   先 `_detect_third_party_protocol_for_models` 探**单个**协议,再逐模型 probe。

**候选选取与上限**([llm.py:4679-4705](../../../apps/studio/backend/app/routers/llm.py)):
- 候选 = discovered → endpoint 已知 routes → **`notable_model_ids(backend)` 文档保底**(三级兜底)。
- 排序 `endpoint_probe_priority`:**绿(verified)→蓝(probe-verified)→未试→失败**([llm_credentials_evidence.py:187-234](../../../apps/studio/backend/app/services/llm_credentials_evidence.py))。
- 上限 `_THIRD_PARTY_PROBE_MODEL_LIMIT = 6`([llm.py:4593](../../../apps/studio/backend/app/routers/llm.py))。
- 早停:遇第一个 `ok` 停(verified);遇结构性 `{invalid_key, quota_exceeded}` 停(failed,
  `_STRUCTURAL_PROBE_STATUSES` [llm.py:4589](../../../apps/studio/backend/app/routers/llm.py));`invalid_model`/超时等**非结构性**继续往下试到 6 个。

**测前不拉远端 catalog**;测后有 best-effort 上传 `_autoshare_after_probe_best_effort`
([llm.py:156-189](../../../apps/studio/backend/app/routers/llm.py)),受 `remote_model_catalog_enabled` 门控。

## 2. 状态投影现状 = 多字段 + 三层现算(R1 的根因)

**存储的状态字段**:
- `ProviderEndpoint.status` / `ProviderRoute.status`:`Literal["verified","unverified_manual","disabled","failed"]`,
  **只在 test/probe 时写**,真实运行调用**不写**。
- `ProviderRoute.ui_state`:**从不持久化**,投影时现算。
- `reason_code`:gateway 投影器仅 3 值(`missing_config/endpoint_unreachable/model_failed`),
  另一套散在 `route.metadata["reason_code"]`(probe 枚举 `invalid_key/quota_exceeded/...`)。
- `route.evidence[]`:studio-only,append-only,`trust_state` ∈ {probe-verified, probe-failed, ...}。

**投影函数** `project_route_state`
([state_projection.py:72-118](../../../packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py)),
输入 = `endpoint_status + route_status + credential_available + circuit_retry_at + evidence_refs`,
studio 端在 `_project_route_ui_states`([llm.py:2143-2187](../../../apps/studio/backend/app/routers/llm.py))逐 route 组装。

**前端第三层现算**(R1.2 要删的):
[ProviderCard.tsx:577-649](../../../apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx)
`endpointStateDisplayStatus` + `providerTestResultFailureScope` 用
`last_test_status + last_error_code + **对 message 文本子串匹配**` 再判一次,且分 scope:
**model 级失败(invalid_model)→ 显示 `untested`;endpoint 级失败(invalid_api_key)→ 显示红 `failed`**。
→ 这就是 Qiniu「Untested 却报 invalid key / 两个同样失败一红一不红」的根因。

**gateway 不回写状态**:`materialize_role`/`resolve_routes`/`dispatch` 只返回瞬态结果,
状态只在 studio 显式 `save_credentials()` 时落盘 → 故"每次真实调用写状态"需事件回流(R1.5)。

## 3. WaveSpeed 真机取证(credentials + runtime_activity 日志)

3 个 endpoint(按 base_url × 协议派生):
- `llm-wavespeed-ai-v1-openai-d1d55e56a2` openai_compatible @ `https://llm.wavespeed.ai/v1`
- `llm-wavespeed-ai-anthropic-e5ee396672` anthropic_compatible @ `https://llm.wavespeed.ai`(无 /v1)
- `llm-wavespeed-ai-v1-google-fd266d8c21` google_genai @ `https://llm.wavespeed.ai/v1`

**日志时间线**(`logs/studio_runtime_activity.jsonl`):
- **08:20**(key 当时错):三 endpoint 全 `failed`,openai/anth message = `Invalid API key (wavespeed_error)`,
  `discovered_model_count=0`。→ 截图顶部「Invalid API key」当时**是对的**。
- **08:53**(key 修好):
  - openai:`model_list_observed` **`model_count:0`**(空表!)→ endpoint_test `failed`,
    message `invalid_model 404, model `o3-mini` does not exist`,`discovered_model_count:0`。
  - anthropic:`endpoint_test failed`,message `Endpoint reachable but no model ids were available to probe`。
  - google:`failed`,`invalid_model 404`。
- **08:56**:`manual_model_probe status=verified`(手填真模型 claude-opus-4.8 等)→ openai endpoint 翻 verified。

**关键结论**:
- **wavespeed openai 不返回 model list**(`model_count:0`);"Connected. Model seen: …"是 08:56 手测后的 message,非自动测。
- **`o3-mini` 是文档保底模型**,来自 `notable_model_ids("openai")` 读
  [docs/development/llm_provider_notes/openai.md](../../../docs/development/llm_provider_notes/openai.md) 的「## 4. Notable Model IDs」
  ([llm_notable_models.py:16-37](../../../apps/studio/backend/app/services/llm_notable_models.py))。**与 wavespeed 无关**。
- 因此该 endpoint **连通性已由 get-models(ok 空表)证明**,被判 failed 仅因「拿保底模型乱测→404」。
  → 正确态应为 untested + ⚠(R2),不是 failed。

**「API Key/Base URL 旁绿勾」语义**:仅格式校验(非空 / URL 合法),**不代表测通**——是误导用户的来源。

## 4. 连通性 vs 生成验证(回答「不填 model 能不能测」)

- **连通性**:get-models(列模型)**无需 model**;ok(哪怕空表)即证明 key+url+协议可达
  ([llm.py:723-727](../../../apps/studio/backend/app/routers/llm.py))。`invalid_model` 也间接证明可达
  (拿到提供方结构化错误,协议探测里 [llm.py:4716-4717](../../../apps/studio/backend/app/routers/llm.py) 把它当「协议/鉴权已到达」)。
- **verified=能生成**:第三方光 get-models 不算,必须真发一次生成且成功(apikeys#25 设计)→ **需要一个真实模型**。
- 结论:连通性不需要 model,verified 需要;无真实模型时止于「reachable / untested」即可。

## 5. protocol / method 全貌(R5 依据)

- **4 个 protocol**([schema.py:21](../../../packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py)):
  `openai_compatible / anthropic_compatible / google_genai / ark_runtime`。
- **10 个 method**(`OfficialCallMethod`
  [provider_probe.py:26-37](../../../packages/graph-agent-gateway/src/graph_agent_gateway/registry/provider_probe.py)):
  - ark:`ark_chat`(openai 形 chat.completions)、`ark_responses`、`ark_anthropic_messages`(anthropic 形转发)→ **ark 同时有 openai 形与 anthropic 形**。
  - deepseek:`deepseek_chat_completions`、`deepseek_anthropic_messages`。
  - openai:`openai_chat_completions`、`openai_responses`、`openai_completions`。
  - anthropic:`anthropic_messages`;gemini:`gemini_generate_content`。
- protocol = HTTP 形状;method = 同协议族下具体路径/格式。tool-use 是**能力位** `tool_protocol`(布尔),
  现在多为**推断**(provider feature flag / anthropic 文档默认 [capabilities.py:131-142](../../../packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py)),
  **不是真发 tools 请求探出来的**(截图「Tool protocol: not verified yet」即此)。
- engine 运行时走 langchain `create_agent`/`bind_tools`,按 `route.protocol` 选分支、`call_method_id` 选 method,
  tools 作可选参传下([llm_phase_node.py:112-132](../../../packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py) →
  [gateway_chat_model.py:225](../../../packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py))。
- → **method/tool-use 真测属于「role/copilot 实际应用环境」**,本 spec 把它移出 endpoint 测试(R4.2)。

## 6. id 生成 + 索引键(R8 依据)

- **endpoint id** `stable_endpoint_id`([route_identity.py:20-26](../../../packages/graph-agent-gateway/src/graph_agent_gateway/registry/route_identity.py)):
  `{host+path slug}-{协议后缀}-{sha256("协议|规范化base_url")[:10]}`;协议后缀 openai/anthropic/google/ark。
  官方已知 host 走固定 id(`anthropic-official`/`openai-official`/`deepseek-official`/`gemini-official`/`ark-official`,
  [llm_credentials.py:293-305](../../../apps/studio/backend/app/services/llm_credentials.py))。
- **route id** = `{endpoint_id}:{route_slug(model_id)}`。
- **provider 卡片** = 前端把 endpoints 分组的 `credentials.providers[].id`
  ([ApiKeysTab.tsx:53](../../../apps/studio/frontend/src/components/studio/settings/api-keys/ApiKeysTab.tsx));
  后端 registry 只返回 `provider_endpoints`(按 endpoint id 索引),无独立 provider 实体。具体分组键实现 R8.1 时再精确核。
- **catalog evidence 索引** = **`(规范化公网 base_url 的 host, provider_model_id)`**
  ([community_catalog_runtime.py:34-42](../../../apps/studio/backend/app/services/community_catalog_runtime.py)),
  **不用** endpoint id(哈希纯本地,不进 catalog)。

## 7. 手动单模型探测现状(R6 依据)

- 前端 `ManualModelTestPanel` 拿单个 `draft.id`,`testProviderModels` POST 到 `/llm/endpoints/{一个endpoint_id}/models/test`;
  后端 `test_endpoint_models`([llm.py:923-1177](../../../apps/studio/backend/app/routers/llm.py))解析单 endpoint、只在它上面逐模型 probe。
  **无跨 sibling endpoint 循环** → R6 要扇出。

## 8. 模型标签动画现状(R9 依据)

- CSS `.api-route-tag-border-flow`([index.css:297-324](../../../apps/studio/frontend/src/index.css))已存在且接在 `status==="testing"`。
- 但只有「Get models」流程经 `setProviderTesting(...,"models")` 点亮;**手动探测/endpoint 逐模型探测都不置 testing 态**,
  后端探测同步、不发逐模型进度事件 → 动画不触发。R9 需后端发逐模型进度事件 + 前端置态。

## A. 连通性指示器现状(Part A / R-A2 依据)

- **api_key 绿勾** `FieldReachabilityCheck`([ProviderCard.tsx:318-330](../../../apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx)):
  **只有绿勾、无红叉**,渲染条件 = `hasReachableModelList`([:1866](../../../apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx))。
  → 它表达的是「模型列表拿到了」,**不是 api_key(L1)自身连通性**;key 错了也可能不显示红,造成 WaveSpeed「key 无效却挂绿勾」。
- **base_url 图标** `BaseUrlReachabilityIcon` 的状态来自 `baseUrlReachabilityState`
  ([:1630-1636](../../../apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx)),
  内部又调 `endpointStateDisplayStatus`(§2 那套文本匹配)→ **base_url(L2)指示器其实在显示 endpoint 派生态**,不是本层连通性。
- 结论:L1/L2 现状**没有独立连通态**,需按 Part A 重做(get_models 充分非必要)。

## B. provider 身份 / catalog provider_id 现状(Part B 依据)

- **provider 分组**仅 `_endpoint_notable_provider_key`([llm.py:4645-4657](../../../apps/studio/backend/app/routers/llm.py))**硬编码** qiniu / openrouter 两家
  (`_hostname_matches_registered_domain` [llm.py:4641-4642](../../../apps/studio/backend/app/routers/llm.py) 只做后缀匹配),
  **无系统化"注册域(eTLD+1)派生 provider"**;其余落 `_endpoint_probe_backend`。
- **`provider_id`(wire)只透传**:`build_upload_record(... provider_id=record.provider_id)`
  ([community_catalog.py:169](../../../apps/studio/backend/app/services/community_catalog.py));未见从注册域系统填充。
- **无 provider 级 alias/品牌名**:`display_name` 只在 endpoint/route/profile 级
  ([llm_config.py:78/84/95](../../../apps/studio/backend/app/models/llm_config.py)),无 provider 维度。
- **eTLD+1 实现注意**:正确算注册域需 Public Suffix List(`.co.uk`/`.com.cn` 等多级后缀);
  现有 `_hostname_matches_registered_domain` 只是"已知域后缀匹配",不是通用 eTLD+1 → 实现需引 PSL(`tldextract`/`publicsuffix2`)或内置精简表(见 design 待定 T6)。
- **WaveSpeed 双 base_url 实例**(用户给):`https://api.wavespeed.ai/api/v3` 与 `https://llm.wavespeed.ai/v1`
  → 注册域同为 `wavespeed.ai` → eTLD+1 收敛为**单一 provider**;若用完整 host 则裂成两家(反例,印证 R-B4)。

## C. 社区贡献 allowlist 现状(Part C 依据)

- `PUBLIC_PROVIDER_HOST_ALLOWLIST`([community_catalog.py:41-62](../../../apps/studio/backend/app/services/community_catalog.py)):约 15 个 host 的**准入名单**。
- `build_upload_record`([community_catalog.py:156-160](../../../apps/studio/backend/app/services/community_catalog.py)):
  **仅当 host 在名单内**才 `normalize_base_url` + `endpoint_fingerprint` 发布 URL 身份;名单外 → URL 身份置空,
  evidence 实质**不外传**(WaveSpeed `llm.wavespeed.ai` 即被挡)。
- 注释自述动机为隐私(名单内是"public domain carrying no user identity")→ 但与「开放新 provider 贡献」初衷冲突,
  Part C 改为安全闸(拦私有/带密钥 URL、放行公网)。

## 9. 配置项(R10 依据)

- `community_catalog_manifest_url` / `community_catalog_signing_pubkey` 烤死默认值
  ([backends.py:55-60](../../../apps/studio/backend/app/core/backends.py));公钥 = 64-hex(32B ed25519),**token 非文件**;
  可被 `STUDIO_COMMUNITY_CATALOG_*` 环境变量覆盖。读同步只看这两者是否配齐,**不查** `remote_model_catalog_enabled` 开关
  (与 [llm.py:164](../../../apps/studio/backend/app/routers/llm.py) 注释「gates both read and contribute」存在 drift,见 design 待定项)。
