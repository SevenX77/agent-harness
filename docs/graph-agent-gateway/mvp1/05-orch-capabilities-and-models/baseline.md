---
module: 05-orch-capabilities-and-models
doc: baseline
status: drafted
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:normalize_route_capabilities/build_runtime_setting_descriptors · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/lint.py:lint_role_routes/capability_key_for_lint · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/profile_selector.py:select_verified_profile/ProfileSelectionError · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/resolver.py:resolve_role · apps/studio/backend/app/routers/llm.py:probe_route/_registry_response/_capability_state · apps/studio/backend/app/services/llm_model_identity.py:project_model_identity · apps/studio/backend/app/services/llm_model_groups.py:project_model_group_identity/normalize_model_group_key · apps/studio/backend/app/services/llm_notable_models.py:notable_model_ids/default_provider_notes_dir · apps/studio/backend/app/services/llm_route_capabilities.py:route_effective_capabilities/route_thinking_capability/verified_profile_route_capabilities
units: [capability-model-knowledge]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 05-orch-capabilities-and-models — Baseline(现状)

本文只描述当前源码事实: capability 如何归一化、verified profile 如何选择、lint 如何 warn/block,以及 Studio 后端如何把模型身份、分组、notable model 和 route capability 投影给前端。当前 mvp1 README 的模块清单要求本模块覆盖这些文件。

## 覆盖代码(含覆盖率)

覆盖率: 8/8 个指定文件已核实,公共入口 13/13 已解释;私有 helper 只按参与的规则分组说明。

| 文件 | 覆盖入口 | 覆盖说明 |
|---|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py` | `normalize_route_capabilities`：用于把 provider/API/raw metadata 归一成 route capability 字典。`build_runtime_setting_descriptors`：用于把 route capability 转成前端可安全渲染的 runtime setting 控件描述。 | 100%,含 runtime descriptor 常量与 Anthropic thinking 规则。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/resolve/profile_selector.py` | `select_verified_profile`：用于在一条 route 的 ready verified profiles 中选出最符合 runtime intent 的调用 profile。`ProfileSelectionError`：用于表达没有任何 verified profile 能满足请求意图。 | 100%,含 reasoning/image modality 选择和排序。 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/resolve/lint.py` | `lint_role_routes`：用于检查显式 role fallback chain 上每条 route 是否满足 lint requirement 和 runtime setting 能力边界。`capability_key_for_lint`：用于把 lint 名称映射到 normalized capability key。 | 100%,含 runtime setting lint。 |
| `apps/studio/backend/app/services/llm_model_identity.py` | `project_model_identity`：用于把 route/endpoint 名字解析成 Studio 展示名、分区标签和置信度。 | 100%,私有 token/owner/family helper 按流程覆盖。**判据归属(2026-06-03 第四轮反转)：品牌/家族识别内核 = ③b 公共能力(现散 ③a 待下沉)，展示名样式覆盖留 ③a；详见 `mvp1-alignment.md` §5#1。** |
| `apps/studio/backend/app/services/llm_notable_models.py` | `notable_model_ids`：用于从 provider notes 文档的 Notable Model IDs 小节提取建议模型 ID。`default_provider_notes_dir`：用于定位默认 provider notes 目录。 | 100%。**判据归属(反转)：已知可用知识库内核 = ③b 公共(现散 ③a 待下沉)，数据源路径注入 + 展示面板留 ③a；详见 `mvp1-alignment.md` §5#1。** |
| `apps/studio/backend/app/services/llm_route_capabilities.py` | `route_effective_capabilities`：用于把 route 原始 capabilities 与 ready verified profile 派生 facts 合并。`route_thinking_capability`：用于读取合并后的 thinking capability。`verified_profile_route_capabilities`：用于从 ready verified profiles 推导 verified_methods、modalities 和 thinking_protocol。 | 100%。**判据归属(反转)：能力合并内核 = ③b 公共(现散 ③a 待下沉)；详见 `mvp1-alignment.md` §5#1。** |
| `apps/studio/backend/app/services/llm_model_groups.py` | `project_model_group_identity`：用于把 route 投影成 Available Models 的模型组身份。`normalize_model_group_key`：用于生成稳定分组 key。 | 100%。**判据归属(反转)：同模型分组内核 = ③b 公共(现散 ③a 待下沉)，family 折叠/弃用区展示留 ③a；详见 `mvp1-alignment.md` §5#1。** |
| 调用点 | `resolve_role`：用于把 role 显式 fallback_chain 解析成有序 runtime routes,并调用 profile 选择与 lint。`_registry_response`：用于组装 Studio registry DTO,包含 lint、model_groups 和 route_runtime_settings。 | 覆盖关键使用链,见代码索引。 |

## 现状逻辑

### 1. capability 归一化与 runtime descriptor

1. 输入是一条 route 的 `protocol`、`provider_model_id` 和 provider/API/probe 原始能力字段;输出是 `dict[str, CapabilityValue]`,其中 `CapabilityValue` 用于保存能力值、来源、观测时间和说明文字(`registry/schema.py:67-75`, `registry/capabilities.py:35-42`)。
2. `normalize_route_capabilities` 先固定写入 `min_output_tokens=1`,来源为 provider_doc,表示没有更细 provider 约束时聊天 API 至少接受 1 个输出 token(`registry/capabilities.py:44-53`)。
3. 它从 `input_modalities` / `inputModalities` / `modalities` 结构里读输入输出模态,并用 `_string_list` 做小写、去空、去重(`registry/capabilities.py:55-60`, `registry/capabilities.py:296-325`)。
4. 它把 `max_output_tokens`、`maxOutputTokens`、`max_tokens`、`outputTokenLimit`、嵌套 `token_limits` 等别名统一到 `max_output_tokens`;把 `max_input_tokens`、`context_window`、`context_length` 等统一到 `max_input_tokens`(`registry/capabilities.py:62-107`)。
5. 它把 runtime setting metadata 统一成 capability,覆盖 `temperature`、`top_p`、`stop_sequences`、`seed`、`tool_choice`、`parallel_tool_calls`、`reasoning_effort`;`_runtime_setting_capability` 用于把 bool 或 `{supported,min,max,default,values}` 规整成统一结构(`registry/capabilities.py:109-120`, `registry/capabilities.py:339-348`)。
6. 它把 provider feature 里的 structured output、vision、tool use 投影为 `structured_output_protocol`、`vision`、`tool_protocol`;Anthropic-compatible route 在没有显式 tool info 时默认补 `tool_protocol=True`,来源 provider_doc(`registry/capabilities.py:122-142`)。
7. Anthropic thinking 规则在归一化阶段写入 `thinking_protocol`、`adaptive_thinking`、`manual_thinking_budget_supported`;`_anthropic_manual_thinking_budget_supported` 用于判断 Opus 4.7 是否禁用手动 budget,`_anthropic_adaptive_thinking_supported` 用于判断 Claude 4.6/4.7 家族是否支持 adaptive thinking(`registry/capabilities.py:144-201`, `registry/capabilities.py:351-364`)。
8. `build_runtime_setting_descriptors` 固定输出 11 个 normalized runtime setting 控件描述,前端不需要自己猜 provider 支持什么;`RuntimeSettingDescriptor` 用于表达 key、类型、支持状态、上下限、默认值、枚举和来源(`registry/capabilities.py:20-32`, `registry/capabilities.py:205-217`, `registry/schema.py:147-160`)。

### 2. route probe 与 capability 写入

1. `probe_route` 用于探测一条 route 并更新 normalized capability metadata;普通路径会把请求里的能力项写成 `source="probed_verified"`(`apps/studio/backend/app/routers/llm.py:782-805`)。
2. 当 probe 请求带 runtime setting metadata 时,`probe_route` 调 `normalize_route_capabilities` 把原始 runtime setting 能力归一化后合并进 route capabilities(`apps/studio/backend/app/routers/llm.py:806-815`)。
3. `_official_normalized_route_capabilities` 用于官方 API list 模型结果的能力归一化,并额外写入 source/source_urls 供前端解释来源(`apps/studio/backend/app/routers/llm.py:3449-3470`)。
4. `_third_party_route_capability_values` 用于第三方 provider route 的能力归一化,并补充 model_type / capability_family 一类目录展示字段(`apps/studio/backend/app/routers/llm.py:4303-4330`)。

### 3. verified profile 选择

1. `VerifiedProfile` 用于描述一条 provider model 已验证过的调用方式,包含 profile_id、capability、method_id、request_mapper_id、status、default、fallback_rank 和输入输出模态(`registry/schema.py:189-204`)。
2. `select_verified_profile` 先过滤 `status=="ready"` 的 profiles;没有 ready profile 时返回 `None`,表示 route 可继续走默认调用方式而不是立即失败(`registry/profile_selector.py:14-23`)。
3. 它再按 required input modalities 过滤;如果用户要求的模态没有任何 ready profile 覆盖,抛 `ProfileSelectionError`(`registry/profile_selector.py:25-34`)。
4. 当 `RuntimeSettings.reasoning.enabled=True` 时,它只选 `_profile_supports_reasoning` 判定为 reasoning/thinking 的 profile;没有则抛 `ProfileSelectionError`(`registry/profile_selector.py:36-45`)。
5. 非 reasoning 请求优先选非 reasoning profile,否则退回任意可用 profile;`_preferred_profile` 用 default、fallback_rank、profile_id 排序,保证选择稳定(`registry/profile_selector.py:47-52`, `registry/profile_selector.py:69-73`)。
6. `resolve_role` 在解析每个 explicit route entry 时调用 `select_verified_profile`,并把 selected profile 的 method_id/request_mapper_id 写入 `ResolvedRoute`,供后续调用层使用(`registry/resolver.py:72-113`)。

### 4. lint 只 warn/block,不驱动动态选型

1. `RoleEntry` 用于保存可执行 role 的显式 `fallback_chain` 和 `lint_requirements`;这说明选路输入是具体 route_id,不是 capability 查询条件(`registry/schema.py:264-273`)。
2. `lint_role_routes` 只遍历 role 已声明的 fallback_chain 和调用方传入的 routes,不会搜索 registry 里的其他 route(`registry/lint.py:27-38`)。
3. lint requirement 先由 `capability_key_for_lint` 映射到 normalized capability key,支持 thinking、tool_calling、structured_output、vision、max_input_tokens、max_output_tokens(`registry/lint.py:9-24`)。
4. 如果 capability 缺失,`severity="error"` 产生 `blocking=True` 和 `code="requires_probe"`,warn 则只给非 blocking 提醒(`registry/lint.py:39-58`)。
5. 如果 capability 明确不支持,lint 产出 incompatible;error 会 blocking,warn 不 blocking(`registry/lint.py:60-72`)。
6. 如果 error 级 capability 来源不是 manual 或 probed_verified,lint 要求 probe 验证,仍然只是产出 `LintResult`(`registry/lint.py:74-86`, `registry/schema.py:388-400`)。
7. `_lint_runtime_settings` 用于检查 role route entry 上的实际 runtime settings 是否超出 route capability 边界,覆盖 token 上下限、seed、stop_sequences、tool_choice、parallel_tool_calls、reasoning effort、structured output 和 thinking budget 规则(`registry/lint.py:90-332`)。
8. `resolve_role` 在 routes 解析完成后调用 `lint_role_routes`;只有 blocking lint 会让解析失败,非 blocking lint 被带回 `ResolvedRole.lint_results`(`registry/resolver.py:116-132`)。
9. `_registry_response` 在 Studio registry DTO 中也计算 lint_results,供前端展示,但同样不改变 role fallback_chain 顺序(`apps/studio/backend/app/routers/llm.py:1347-1383`)。

### 5. Studio 模型身份、分组和 notable 投影

1. `ModelIdentityProjection` 用于保存 route 的展示名、section label、识别置信度和 token 分析结果(`apps/studio/backend/app/services/llm_model_identity.py:11-19`)。
2. `project_model_identity` 从 `provider_model_id`、`canonical_id`、`route_slug` 和 endpoint 文本中推断 owner/family,再生成展示名、section label 与 unknown_tokens(`apps/studio/backend/app/services/llm_model_identity.py:83-121`)。
3. `_tokenize_model_name` 用于保护日期和版本号,再按非字母数字切分 token;`_titleize_token` 用于把 gpt/claude/gemini 等品牌 token 变成稳定展示大小写(`apps/studio/backend/app/services/llm_model_identity.py:124-187`)。
4. `_infer_owner` / `_infer_family` 用于从 route 和 endpoint 文本推断模型归属与家族,例如 Anthropic/Claude、OpenAI/GPT、Google/Gemini、ByteDance/Ark(`apps/studio/backend/app/services/llm_model_identity.py:222-282`)。
5. `ModelGroupIdentityProjection` 用于保存 Available Models 的模型组 key、组展示名、section label 和被剥离的 release/capability/channel tokens(`apps/studio/backend/app/services/llm_model_groups.py:17-26`)。
6. `project_model_group_identity` 先调用 `project_model_identity`,再剥离快照日期、thinking/vision 等能力 token 和末尾 route channel token,但精确执行仍使用 route_id(`apps/studio/backend/app/services/llm_model_groups.py:43-68`)。
7. `notable_model_ids` 从 `docs/development/llm_provider_notes/<provider>.md` 的 `## 4. Notable Model IDs` 小节提取反引号里的 model IDs,用于没有 list API 的 provider 提示候选(`apps/studio/backend/app/services/llm_notable_models.py:12-37`)。
8. `route_effective_capabilities` 把 route 原始 capabilities 与 ready verified profile facts 合并;`verified_profile_route_capabilities` 会从 ready profiles 推导 `verified_methods`、modalities 和 `thinking_protocol=True`(`apps/studio/backend/app/services/llm_route_capabilities.py:10-64`)。

## baseline/alignment 差异

1. baseline 已有 capability 归一化、verified profile 选择、lint blocking 和 Studio 展示投影;这些是 MVP1 应保留的编排素材,不是要删除的旧层(`registry/capabilities.py:35-202`, `registry/profile_selector.py:14-52`, `registry/lint.py:27-87`)。
2. baseline 仍把 selected profile 的 `call_method_id` / `request_mapper_id` 传给当前 gateway client manager 调用路径;MVP1 A' 会把这些信息作为 `ResolvedRoute` 上的调用层输入,由新的 ChatX 调用适配消费(`registry/resolver.py:94-113`)。
3. baseline lint 的语义已经符合当前 mvp1 边界:只 warn/block,不根据 capability 搜索替代 route;alignment 需要保护这个边界,避免把 capability 做成动态选型引擎(`registry/lint.py:27-87`, `registry/resolver.py:116-132`)。
4. baseline 的 Studio 投影渲染是显示/解释层,不是 runtime identity;当前代码仍要求 runtime 精确执行 role 当前保存的 route chain(`apps/studio/backend/app/services/llm_model_groups.py:50-53`, `registry/resolver.py:55-113`)。**判据标注(2026-06-03 第四轮反转)：identity/model_group/notable/route_capabilities 的分组/识别/知识/合并**内核**属 ③b 公共能力(现散 ③a 待下沉)——它们不依赖 UI/产品策略/调用方式/存储介质，换 app 仍原样要;只有 family 折叠/弃用区/展示名样式这层渲染留 ③a。"投影不改 runtime route_id"这点不变。详见 `mvp1-alignment.md` §5#1。**

## 决策原因

1. capability 只描述支持、默认和边界,不表达用户运行意图;用户意图属于 role/profile route entry 的 fixed runtime settings。当前代码也把 `CapabilityValue` 与 `RuntimeSettings` 分成两个 schema,且 `capabilities.py` 文件注释明确 capabilities 不编码 user runtime intent(`registry/schema.py:67-75`, `registry/schema.py:121-135`, `registry/capabilities.py:1-5`)。
2. 禁止 capability-based automatic model replacement,原因是 role 编排必须可解释、可复现;当前代码的选路输入只能来自显式 `fallback_chain[*].route_id`,lint 只遍历这条显式链并产出 warn/block(`registry/schema.py:264-273`, `registry/lint.py:27-87`)。
3. verified profile 选择只在一条 route 内选择“怎么调用”,不是跨 route 选择“调谁”;这与 `select_verified_profile` 只接收单个 `ProviderRoute` 的函数签名一致(`registry/profile_selector.py:14-19`)。
4. Studio model identity/model group 让用户理解模型目录,但不会改变 runtime route identity;代码注释也明确 exact execution still uses each route_id(`apps/studio/backend/app/services/llm_model_groups.py:48-53`)。**判据标注(反转)：原把它们整体定调为"产品展示投影 → 留 ③a"已被否;按判据其分组/识别**能力内核 = ③b 公共**(现散 ③a 待下沉)，只有展示渲染留 ③a。"不改 runtime route identity / 执行仍用精确 route_id"不变。详见 `mvp1-alignment.md` §5#1。**

## 代码索引(clues)

- `registry/schema.py:67-75` — `CapabilityValue`：用于保存能力值和来源元数据。
- `registry/schema.py:121-135` — `RuntimeSettings`：用于保存用户在 role/profile route entry 上写下的 provider-neutral 运行参数。
- `registry/schema.py:189-204` — `VerifiedProfile`：用于描述一条 route 的已验证调用方式。
- `registry/schema.py:207-220` — `ProviderRoute`：用于表示一个 endpoint 上的一条物理模型路线。
- `registry/schema.py:388-400` — `LintResult`：用于向 resolver 和 Studio 前端表达 warn/error/blocking。
- `registry/capabilities.py:35-202` — `normalize_route_capabilities`：用于把 raw provider metadata 统一成 normalized capabilities。
- `registry/capabilities.py:205-269` — `build_runtime_setting_descriptors`：用于把 capabilities 转成前端 runtime setting 控件描述。
- `registry/profile_selector.py:14-52` — `select_verified_profile`：用于在单条 route 内选择 ready profile。
- `registry/lint.py:27-87` — `lint_role_routes`：用于 lint 显式 route chain,不做动态选型。
- `registry/resolver.py:72-132` — `resolve_role`：用于调用 profile 选择、生成 ResolvedRoute 并应用 blocking lint。
- `apps/studio/backend/app/routers/llm.py:782-818` — `probe_route`：用于 route probe 后写入 verified capability。
- `apps/studio/backend/app/routers/llm.py:1347-1383` — `_registry_response`：用于把 lint、model groups 和 runtime descriptors 投影到 registry API。
- `apps/studio/backend/app/services/llm_model_identity.py:83-121` — `project_model_identity`：用于模型展示身份投影。
- `apps/studio/backend/app/services/llm_model_groups.py:43-68` — `project_model_group_identity`：用于模型组投影。
- `apps/studio/backend/app/services/llm_route_capabilities.py:10-64` — `route_effective_capabilities` / `verified_profile_route_capabilities`：用于把 verified profile facts 并入 route capabilities。

## 待办/疑点

1. `resolve_role` 当前对 fallback_chain 中第一个缺失/不可执行 route 仍直接 raise,而 mvp1 解析容错目标要求逐条 skip + warning 后空链再失败;这属于 02/07 解析容错模块,本文件只记录影响点(`registry/resolver.py:55-71`, `../02-orch-role-resolution/mvp1-alignment.md`)。
2. `route_effective_capabilities` 是 Studio service 层合并 verified profile facts,但 `resolve_role` 传给 `lint_role_routes` 的是 route 原始 capabilities;是否应在 resolver 侧也消费 effective capabilities,需要后续设计确认(`apps/studio/backend/app/services/llm_route_capabilities.py:10-19`, `registry/resolver.py:104-116`)。
3. `notable_model_ids` 依赖 Markdown 小节标题精确等于 `## 4. Notable Model IDs`;provider notes 标题变化会静默返回空列表,目前无运行时错误提示(`apps/studio/backend/app/services/llm_notable_models.py:8-37`)。
