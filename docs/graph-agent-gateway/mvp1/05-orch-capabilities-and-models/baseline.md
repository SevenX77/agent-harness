---
module: 05-orch-capabilities-and-models
doc: baseline
status: drafted
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:normalize_route_capabilities/build_runtime_setting_descriptors · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/lint.py:lint_role_routes/capability_key_for_lint · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/profile_selector.py:select_verified_profile/ProfileSelectionError · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/resolver.py:resolve_role · apps/studio/backend/app/routers/llm.py:probe_route/_registry_response/_capability_state · packages/graph-agent-gateway/src/graph_agent_gateway/registry/model_naming.py:project_model_identity · packages/graph-agent-gateway/src/graph_agent_gateway/registry/model_naming.py:project_model_group_identity/normalize_model_group_key · apps/studio/backend/app/services/llm_notable_models.py:notable_model_ids/default_provider_notes_dir · packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:route_effective_capabilities/verified_profile_capabilities
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
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/model_naming.py` | `project_model_identity`：把原始 model id 读成名字——品牌、家族、可读形式。`project_model_group_identity`：在它之上回答「哪些路线对人来说是同一个模型」。`normalize_model_group_key`：生成稳定分组 key。 | 100%。**已下沉(#772)**：原 `services/llm_model_identity.py` + `services/llm_model_groups.py`。宿主给端点起的用户可见标签由 `provider_label` 参数显式传入，不从 endpoint 读——网关 `ProviderEndpoint` 没有展示字段。 |
| `apps/studio/backend/app/services/llm_notable_models.py` | `notable_model_ids`：用于从 provider notes 文档的 Notable Model IDs 小节提取建议模型 ID。`default_provider_notes_dir`：用于定位默认 provider notes 目录。 | 100%。**判据归属(反转)：已知可用知识库内核 = ③b 公共(现散 ③a 待下沉)，数据源路径注入 + 展示面板留 ③a；详见 `mvp1-alignment.md` §5#1。** |
| `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py` | `route_effective_capabilities`：把路由静态声明的能力与探测验证出的能力合并成一份有效能力，实测压过声称。`verified_profile_capabilities`：只有 `ready` 档案算数，且「会不会思考」看候选**声明的 capability**，不从名字里猜。 | 100%。**已下沉(#771)**：原 `services/llm_route_capabilities.py`，同时删掉了网关 `role/materialization.py` 里那份行为不同的私有拷贝。`route_thinking_capability` 已取消，调用方直接读 `route_effective_capabilities(route).get("thinking_protocol")`。 |
| 调用点 | `resolve_role`：用于把 role 显式 fallback_chain 解析成有序 runtime routes,并调用 profile 选择与 lint。`_registry_response`：用于组装 Studio registry DTO,包含 lint、model_groups 和 route_runtime_settings。 | 覆盖关键使用链,见代码索引。 |

## 现状逻辑

### 1. capability 归一化与 runtime descriptor

1. 输入是一条 route 的 `protocol`、`provider_model_id` 和 provider/API/probe 原始能力字段;输出是 `dict[str, CapabilityValue]`,其中 `CapabilityValue` 用于保存能力值、来源、观测时间和说明文字(`registry/schema.py`, `registry/capabilities.py`)。
2. `normalize_route_capabilities` 先固定写入 `min_output_tokens=1`,来源为 provider_doc,表示没有更细 provider 约束时聊天 API 至少接受 1 个输出 token(`registry/capabilities.py`)。
3. 它从 `input_modalities` / `inputModalities` / `modalities` 结构里读输入输出模态,并用 `_string_list` 做小写、去空、去重(`registry/capabilities.py`, `registry/capabilities.py`)。
4. 它把 `max_output_tokens`、`maxOutputTokens`、`max_tokens`、`outputTokenLimit`、嵌套 `token_limits` 等别名统一到 `max_output_tokens`;把 `max_input_tokens`、`context_window`、`context_length` 等统一到 `max_input_tokens`(`registry/capabilities.py`)。
5. 它把 runtime setting metadata 统一成 capability,覆盖 `temperature`、`top_p`、`stop_sequences`、`seed`、`tool_choice`、`parallel_tool_calls`、`reasoning_effort`;`_runtime_setting_capability` 用于把 bool 或 `{supported,min,max,default,values}` 规整成统一结构(`registry/capabilities.py`, `registry/capabilities.py`)。
6. 它把 provider feature 里的 structured output、vision、tool use 投影为 `structured_output_protocol`、`vision`、`tool_protocol`;Anthropic-compatible route 在没有显式 tool info 时默认补 `tool_protocol=True`,来源 provider_doc(`registry/capabilities.py`)。
7. Anthropic thinking 规则在归一化阶段写入 `thinking_protocol`、`adaptive_thinking`、`manual_thinking_budget_supported`;`_anthropic_manual_thinking_budget_supported` 用于判断 Opus 4.7 是否禁用手动 budget,`_anthropic_adaptive_thinking_supported` 用于判断 Claude 4.6/4.7 家族是否支持 adaptive thinking(`registry/capabilities.py`, `registry/capabilities.py`)。
8. `build_runtime_setting_descriptors` 固定输出 11 个 normalized runtime setting 控件描述,前端不需要自己猜 provider 支持什么;`RuntimeSettingDescriptor` 用于表达 key、类型、支持状态、上下限、默认值、枚举和来源(`registry/capabilities.py`, `registry/capabilities.py`, `registry/schema.py`)。

### 2. route probe 与 capability 写入

1. `probe_route` 用于探测一条 route 并更新 normalized capability metadata;普通路径会把请求里的能力项写成 `source="probed_verified"`(`apps/studio/backend/app/routers/llm.py:782-805`)。
2. 当 probe 请求带 runtime setting metadata 时,`probe_route` 调 `normalize_route_capabilities` 把原始 runtime setting 能力归一化后合并进 route capabilities(`apps/studio/backend/app/routers/llm.py:806-815`)。
3. `_official_normalized_route_capabilities` 用于官方 API list 模型结果的能力归一化,并额外写入 source/source_urls 供前端解释来源(`apps/studio/backend/app/routers/llm.py:3449-3470`)。
4. `_third_party_route_capability_values` 用于第三方 provider route 的能力归一化,并补充 model_type / capability_family 一类目录展示字段(`apps/studio/backend/app/routers/llm.py:4303-4330`)。

### 3. verified profile 选择

1. `VerifiedProfile` 用于描述一条 provider model 已验证过的调用方式,包含 profile_id、capability、method_id、request_mapper_id、status、default、fallback_rank 和输入输出模态(`registry/schema.py`)。
2. `select_verified_profile` 先过滤 `status=="ready"` 的 profiles;没有 ready profile 时返回 `None`,表示 route 可继续走默认调用方式而不是立即失败(`resolve/profile_selector.py:select_verified_profile`)。
3. 它再按 required input modalities 过滤;如果用户要求的模态没有任何 ready profile 覆盖,抛 `ProfileSelectionError`(`resolve/profile_selector.py:select_verified_profile`)。
4. 当 `RuntimeSettings.reasoning.enabled=True` 时,它只选 `_profile_supports_reasoning` 判定为 reasoning/thinking 的 profile;没有则抛 `ProfileSelectionError`(`resolve/profile_selector.py:select_verified_profile`)。
5. 非 reasoning 请求优先选非 reasoning profile,否则退回任意可用 profile;`_preferred_profile` 用 default、fallback_rank、profile_id 排序,保证选择稳定(`resolve/profile_selector.py:select_verified_profile`, `resolve/profile_selector.py:select_verified_profile`)。
6. `resolve_role` 在解析每个 explicit route entry 时调用 `select_verified_profile`,并把 selected profile 的 method_id/request_mapper_id 写入 `ResolvedRoute`,供后续调用层使用(`resolve/resolver.py:resolve_role`)。

### 4. lint 只 warn/block,不驱动动态选型

1. `RoleEntry` 用于保存可执行 role 的显式 `fallback_chain` 和 `lint_requirements`;这说明选路输入是具体 route_id,不是 capability 查询条件(`registry/schema.py`)。
2. `lint_role_routes` 只遍历 role 已声明的 fallback_chain 和调用方传入的 routes,不会搜索 registry 里的其他 route(`resolve/lint.py:lint_role_routes`)。
3. lint requirement 先由 `capability_key_for_lint` 映射到 normalized capability key,支持 thinking、tool_calling、structured_output、vision、max_input_tokens、max_output_tokens(`resolve/lint.py:lint_role_routes`)。
4. 如果 capability 缺失,`severity="error"` 产生 `blocking=True` 和 `code="requires_probe"`,warn 则只给非 blocking 提醒(`resolve/lint.py:lint_role_routes`)。
5. 如果 capability 明确不支持,lint 产出 incompatible;error 会 blocking,warn 不 blocking(`resolve/lint.py:lint_role_routes`)。
6. 如果 error 级 capability 来源不是 manual 或 probed_verified,lint 要求 probe 验证,仍然只是产出 `LintResult`(`resolve/lint.py:lint_role_routes`, `registry/schema.py`)。
7. `_lint_runtime_settings` 用于检查 role route entry 上的实际 runtime settings 是否超出 route capability 边界,覆盖 token 上下限、seed、stop_sequences、tool_choice、parallel_tool_calls、reasoning effort、structured output 和 thinking budget 规则(`resolve/lint.py:lint_role_routes`)。
8. `resolve_role` 在 routes 解析完成后调用 `lint_role_routes`;只有 blocking lint 会让解析失败,非 blocking lint 被带回 `ResolvedRole.lint_results`(`resolve/resolver.py:resolve_role`)。
9. `_registry_response` 在 Studio registry DTO 中也计算 lint_results,供前端展示,但同样不改变 role fallback_chain 顺序(`apps/studio/backend/app/routers/llm.py:1347-1383`)。

### 5. 模型身份、分组和 notable 投影

1. `ModelIdentityProjection` 保存展示名、section label、识别置信度与 token 分析结果(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/model_naming.py:ModelIdentityProjection`)。
2. `project_model_identity` 从 `provider_model_id`、`canonical_id`、`route_slug` 与宿主传入的 `provider_label` 推断 owner/family,再生成展示名、section label 与 unknown_tokens(`registry/model_naming.py:project_model_identity`)。
3. `_tokenize_model_name` 先保护日期与版本号再按非字母数字切分;`_titleize_token` 把 gpt/claude/gemini 等品牌 token 变成稳定展示大小写(同文件私有 helper)。
4. `_infer_owner` / `_infer_family` 从模型 id 与宿主标签推断归属与家族(Anthropic·Claude、OpenAI·GPT、Google·Gemini、ByteDance·Ark…)。
5. `ModelGroupIdentityProjection` 保存模型组 key、组展示名、section label 和被剥离的 release / capability / channel tokens(`registry/model_naming.py:ModelGroupIdentityProjection`)。
6. `project_model_group_identity` 先调 `project_model_identity`,再剥离快照日期、thinking/vision 等能力 token 与末尾的 route channel token。**这是给人看的粗分组,不是执行身份**——`registry/identity.py` 的 `canonical_id` 必须与 route_id 后缀逐字节一致,精确执行仍走各自的 `route_id`。
7. `notable_model_ids` 从 `docs/development/llm_provider_notes/<provider>.md` 的 `## 4. Notable Model IDs` 小节提取反引号里的 model id,给没有 list API 的 provider 提示候选(`apps/studio/backend/app/services/llm_notable_models.py:notable_model_ids`)。**仍在 studio**:规则属公共,但它读宿主自己的文档目录,按「存储由宿主注入」要先把规则与介质拆开。
8. `route_effective_capabilities` 合并路由声明与 ready verified profile 推出的事实;`verified_profile_capabilities` 从 ready 档案推出 `verified_methods`、modalities 与 `thinking_protocol`(`registry/capabilities.py`)。

## baseline/alignment 差异

1. baseline 已有 capability 归一化、verified profile 选择、lint blocking 和 Studio 展示投影;这些是 MVP1 应保留的编排素材,不是要删除的旧层(`registry/capabilities.py`, `resolve/profile_selector.py:select_verified_profile`, `resolve/lint.py:lint_role_routes`)。
2. baseline 仍把 selected profile 的 `call_method_id` / `request_mapper_id` 传给当前 gateway client manager 调用路径;MVP1 A' 会把这些信息作为 `ResolvedRoute` 上的调用层输入,由新的 ChatX 调用适配消费(`resolve/resolver.py:resolve_role`)。
3. baseline lint 的语义已经符合当前 mvp1 边界:只 warn/block,不根据 capability 搜索替代 route;alignment 需要保护这个边界,避免把 capability 做成动态选型引擎(`resolve/lint.py:lint_role_routes`, `resolve/resolver.py:resolve_role`)。
4. 投影是显示/解释层,不是 runtime identity;runtime 仍精确执行 role 当前保存的 route chain(`registry/model_naming.py:project_model_group_identity` 的模块说明, `resolve/resolver.py:resolve_role`)。**判据落地(2026-08-13)**:2026-06-03 第四轮反转判定 identity / model_group / route_capabilities 的**能力内核属 ③b 公共**,这三项已分别在 #772 与 #771 下沉进本包;notable 的知识内核同判归公共,但其数据源是宿主文档目录,按「存储由宿主注入」尚未下沉。渲染那层(family 折叠、弃用区、展示名样式)仍留 ③a。「投影不改 runtime route_id」不变。详见 `mvp1-alignment.md` §5#1。

## 决策原因

1. capability 只描述支持、默认和边界,不表达用户运行意图;用户意图属于 role/profile route entry 的 fixed runtime settings。当前代码也把 `CapabilityValue` 与 `RuntimeSettings` 分成两个 schema,且 `registry/capabilities.py` 文件注释明确 capabilities 不编码 user runtime intent(`registry/schema.py`, `registry/schema.py`, `registry/capabilities.py`)。
2. 禁止 capability-based automatic model replacement,原因是 role 编排必须可解释、可复现;当前代码的选路输入只能来自显式 `fallback_chain[*].route_id`,lint 只遍历这条显式链并产出 warn/block(`registry/schema.py`, `resolve/lint.py:lint_role_routes`)。
3. verified profile 选择只在一条 route 内选择“怎么调用”,不是跨 route 选择“调谁”;这与 `select_verified_profile` 只接收单个 `ProviderRoute` 的函数签名一致(`resolve/profile_selector.py:select_verified_profile`)。
4. model identity / model group 让用户理解模型目录,但不改变 runtime route identity;`registry/model_naming.py` 的模块说明写明这是给人看的粗分组,执行仍用各自 `route_id`,并与 `registry/identity.py` 的执行身份互不顶替。**判据落地(2026-08-13)**:原把它们整体定调为「产品展示投影 → 留 ③a」已被否;其能力内核 = ③b 公共,已随 #772 下沉,只有展示渲染留 ③a。

## 代码索引(clues)

- `registry/schema.py` — `CapabilityValue`：用于保存能力值和来源元数据。
- `registry/schema.py` — `RuntimeSettings`：用于保存用户在 role/profile route entry 上写下的 provider-neutral 运行参数。
- `registry/schema.py` — `VerifiedProfile`：用于描述一条 route 的已验证调用方式。
- `registry/schema.py` — `ProviderRoute`：用于表示一个 endpoint 上的一条物理模型路线。
- `registry/schema.py` — `LintResult`：用于向 resolver 和 Studio 前端表达 warn/error/blocking。
- `registry/capabilities.py` — `normalize_route_capabilities`：用于把 raw provider metadata 统一成 normalized capabilities。
- `registry/capabilities.py` — `build_runtime_setting_descriptors`：用于把 capabilities 转成前端 runtime setting 控件描述。
- `resolve/profile_selector.py:select_verified_profile` — `select_verified_profile`：用于在单条 route 内选择 ready profile。
- `resolve/lint.py:lint_role_routes` — `lint_role_routes`：用于 lint 显式 route chain,不做动态选型。
- `resolve/resolver.py:resolve_role` — `resolve_role`：用于调用 profile 选择、生成 ResolvedRoute 并应用 blocking lint。
- `apps/studio/backend/app/routers/llm.py:782-818` — `probe_route`：用于 route probe 后写入 verified capability。
- `apps/studio/backend/app/routers/llm.py:1347-1383` — `_registry_response`：用于把 lint、model groups 和 runtime descriptors 投影到 registry API。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/model_naming.py:project_model_identity` — 模型展示身份投影。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/model_naming.py:project_model_group_identity` — 模型组投影(给人看的粗分组,非执行身份)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:route_effective_capabilities` / `:verified_profile_capabilities` — 把探测验证出的事实并入路由声明的能力。

## 待办/疑点

1. `resolve_role` 当前对 fallback_chain 中第一个缺失/不可执行 route 仍直接 raise,而 mvp1 解析容错目标要求逐条 skip + warning 后空链再失败;这属于 02/07 解析容错模块,本文件只记录影响点(`resolve/resolver.py:resolve_role`, `../02-orch-role-resolution/mvp1-alignment.md`)。
2. `route_effective_capabilities` 现已在本包内(#771),但 `resolve_role` 传给 `lint_role_routes` 的仍是路由**原始** capabilities;lint 因此看不见探测验证出的能力。是否应在 resolver 侧改用 effective capabilities,仍是未决设计问题——下沉本身没有回答它,只是把两边放到了同一个包里,使它第一次可以被一处决定(`registry/capabilities.py:route_effective_capabilities`, `resolve/resolver.py:resolve_role`, `resolve/lint.py:lint_role_routes`)。
3. `notable_model_ids` 依赖 Markdown 小节标题精确等于 `## 4. Notable Model IDs`;provider notes 标题变化会静默返回空列表,目前无运行时错误提示(`apps/studio/backend/app/services/llm_notable_models.py:8-37`)。
