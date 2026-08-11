---
module: 05-orch-capabilities-and-models
doc: mvp1-alignment
status: drafted
binds_design: ./baseline.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:normalize_route_capabilities/build_runtime_setting_descriptors · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/lint.py:lint_role_routes/capability_key_for_lint · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/profile_selector.py:select_verified_profile/ProfileSelectionError · packages/graph-agent-gateway/src/graph_agent_gateway/resolve/resolver.py:resolve_role · apps/studio/backend/app/routers/llm.py:probe_route/_registry_response/_capability_state · apps/studio/backend/app/services/llm_model_identity.py:project_model_identity · apps/studio/backend/app/services/llm_model_groups.py:project_model_group_identity/normalize_model_group_key · apps/studio/backend/app/services/llm_notable_models.py:notable_model_ids/default_provider_notes_dir · apps/studio/backend/app/services/llm_route_capabilities.py:route_effective_capabilities/route_thinking_capability/verified_profile_route_capabilities
units: [capability-model-knowledge]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 05 — Capabilities & Models（能力归一化 / profile 选择 / lint / 模型知识）· MVP1 设计

> **组织方式**：**以每个功能为索引** —— 每个功能(F1–F8)一段，把它的机制/数据流 · 决策+动机 · 原话 · 测试点 · status · 归属**全收在自己段里**；仅「定义」「接口契约」「跨功能设计依据」是模块级总览，证据附录（已实现/差异、覆盖代码、代码索引）落在文末。现状基线见同目录 `baseline.md`。
> **Tier**：③b gateway 公共能力内核（`capabilities`/`lint`/`profile_selector` 已在包内；**model_groups / identity / notable / route_capabilities 的能力内核也属 ③b，现散 ③a `apps/studio/backend/app/services` 待下沉**）
> **Owns**：把各厂商参差的模型能力**归一化**成统一表示、把能力翻译成前端可渲染的**控件描述符**、在单条 route 内选择已验证的**调用 profile**、对显式 route 链做 capability **lint**、把原始 model id 客观**分组（model group）/ 识别品牌家族（identity）/ 沉淀已知可用知识（notable）/ 合并静态+探测能力（route_capabilities）**；**不调模型、不做动态选型**
> **Status**：设计定稿（2026-06-03 判据第四轮反转 model_groups/identity/notable/route_capabilities 归属）；代码 = `capabilities`/`lint`/`profile_selector` 不动，四项模型知识能力内核待下沉 ③b，`_capability_state` 四态轴已落地
> **Related**：[[02-orch-role-resolution]]（消费 profile + lint 结果）· [[04-orch-registry-schema]]（`CapabilityValue`/`VerifiedProfile`/`LintResult` 字段权威源）· [[08-orch-test-status-ssot]]（capability_state 第二轴投影落点）· [[10-inv-route-chat-model-factory]] / [[11-inv-provider-profiles]]（消费 `call_method_id`/`request_mapper_id`）
> **决策日志**：`packages/graph-agent-gateway/README.md` §2/§3 + `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §6.0 + `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（行 42-45 四项反转）
> **现状**：见同目录 `baseline.md`

## 定义

MVP1 对齐目标：保留现有 capability/profile/lint/模型知识语义，但按"公共能力内核 vs 应用加工"判据**把它们稳定定位为「编排输入和诊断」**，而不是"动态选型"，也不是"产品展示投影"。两类职责按判据分层：

- **能力归一化 + 控件描述符 + profile 选择 + lint**（`capabilities.py` / `profile_selector.py` / `lint.py`）：把模型能力标准化、翻译成可配置项、在单 route 内选调用方式、守门配置合法性 = **③b 公共**（已在 gateway 包）。
- **模型知识：分组 / 识别 / 知识库 / 能力合并**（`llm_model_groups.py` / `llm_model_identity.py` / `llm_notable_models.py` / `llm_route_capabilities.py`）：把原始 model id 客观分组、归类品牌家族、沉淀"哪些模型存在/可用/值得试"、合并静态+探测能力 = **③b 公共能力内核（本轮反转，现散 ③a 待下沉）**；只有**展示名样式覆盖 / family 折叠 / 弃用区 / notable 数据源路径注入 / identity 展示投影**这层应用加工留 ③a。

调用层 A' 迁移到原生 ChatX 时，这些模块仍只负责描述 route 能力、选单 route 内调用 profile、阻断非法配置、产出模型知识 DTO。**不调模型**（调用归 [[09-inv-invocation-runtime]]），**不做动态选型**（capability 只能 lint/warn/block，runtime 仍按显式 `route_id` 执行）。本文只写文档目标，不改代码。

## 接口契约

> 跨边界签名 / schema / 错误 / 归属，单独成段（模块级，跨功能共享）。`ResolvedRoute`/`ResolvedRole`/`CapabilityValue`/`VerifiedProfile`/`LintResult` 字段权威源 = [[04-orch-registry-schema]]（`registry/schema.py`），本模块**只链接不复制**，防 drift。

| 边界 | 契约 |
|---|---|
| **归一化输入 → ③b** | `normalize_route_capabilities(protocol, provider_model_id, raw_caps) -> dict[str, CapabilityValue]`（`registry/capabilities.py:35-202`）。输入 = provider/API/probe 原始能力字段；输出 = normalized capability 字典，每值带 `source`（`provider_doc`/`probed_verified`/`manual`…）。**③b 看得到**"原始能力字段"（通用），**看不到**"哪个面板展示/什么色"（③a）。 |
| **控件描述符 → ③b** | `build_runtime_setting_descriptors(route: ProviderRoute) -> dict[str, RuntimeSettingDescriptor]`（`registry/capabilities.py:205-217`，`RuntimeSettingDescriptor` schema `registry/schema.py:147-160`）。按 11 个固定 key 输出控件描述（key/类型/支持状态/上下限/默认/枚举/来源），驱动 ① intent 控件；前端只选"关心哪几种能力"，不硬编码 provider 规则。 |
| **profile 选择 → ③b** | `select_verified_profile(route, runtime_settings) -> VerifiedProfile | None`（`registry/profile_selector.py:14-52`）。无 ready profile → 返回 `None`（走默认调用方式，不失败）；要求模态/reasoning 无 ready profile 覆盖 → 抛 `ProfileSelectionError`（无 verified profile 满足请求意图的异常）。**单 route 入参**（只接收单个 `ProviderRoute`），结构上保证不跨 route 选型。 |
| **lint → ③b** | `lint_role_routes(role, routes) -> list[LintResult]`（`registry/lint.py:27-87`）。`LintResult`{ `severity`(warn/error)、`blocking`(bool)、`code`(`requires_probe`/incompatible…) }（`registry/schema.py:388-400`）。**只产出结果**，不改 `fallback_chain`、不补 route。 |
| **模型知识 → ③b（现散 ③a 待下沉）** | `project_model_group_identity(route) -> ModelGroupIdentityProjection`（组 key/组展示名/section/剥离 token，`llm_model_groups.py:43-68`）；`project_model_identity(route) -> ModelIdentityProjection`（展示名/section/置信度/unknown_tokens，`llm_model_identity.py:83-121`）；`notable_model_ids(provider, notes_dir) -> list[str]`（`llm_notable_models.py:16-37`）；`route_effective_capabilities(route) -> dict`（静态 + ready verified 合并，`llm_route_capabilities.py:10-64`）。**输出 = 模型知识 DTO**；③b **看得到**"route + endpoint 原始信息"（通用），**看不到**"family 折叠态/弃用区/展示名样式覆盖/数据源在哪个文件"（③a 应用加工）。 |
| **capability_state 第二轴（D2，四态）** | `_capability_state(capabilities) -> Literal["unknown","callable_only","partial","known"]`（现散 ③a `routers/llm.py`，已按四态落地）。**判据 = 按每个 capability 的 `source` 算（probe-verified vs doc/list/draft 声称 vs 未知），不并入 `route.status`（availability）**。投影侧落点见 [[08-orch-test-status-ssot]] 回填。归属 = route 内在轴（③b 标准总结，现散 ③a待下沉）。机制/决策见 §F8。 |
| **错误** | profile 无匹配 → `ProfileSelectionError`（route 级不可执行原因，由 `resolve_role` 转 skipped diagnostic 或 override fail-fast，归 [[02-orch-role-resolution]]）；blocking lint → `RegistryResolutionError`（role 级配置错误）。**不抛"找不到更好的 route"类错误**（无动态选型）。 |
| **归属 / 稳定性** | 所有上述 schema 字段权威源 = [[04-orch-registry-schema]]；本模块只链接。`call_method_id`/`request_mapper_id` 的消费契约由 [[10-inv-route-chat-model-factory]] / [[11-inv-provider-profiles]] 钉死。 |

## 跨功能设计依据（判据 / D2 / 模型知识归属 / 无动态选型边界）

> 这一段**只收"横跨多个功能、无法归到单一 F"的依据**：通用归属判据、模型知识整体归属、D2 编排/调用分离、无动态选型架构边界。功能各自的决策/原话/测试见对应 ### F<n>。

**通用判据（原话）**：

> **判据（通用，每模块引）· README §2 行 44-45 + ux-spec §6.0 行 342/352（同义校准）**：
> "判定一个逻辑归谁，只问一句：**换一个完全不同的应用装上 gateway，这个能力还原样能用吗？** 能 → 公共（gateway）；不能（因为它绑死了上面四件事之一）→ 应用。"
> → model group 分组 / identity 归类 / notable 知识 / route_capabilities 合并，换任何调模型 app 都原样要 → **③b 公共**（本轮反转旧"③a 产品解释"判断）。

> **本轮反转的 PM 校准 · ux-spec §6.0 行 342（verbatim）**：
> "凡**不依赖「应用加工四件事」（UI / 产品策略 / 调用方式 / 存储介质）**，都是 ③b 公共能力——**含 model group 分组 / 6 态标准总结 / Probe Knowledge Catalog / materialize 编排内核**（这几项**反转**了旧版"归 ③a"的判断）。"

> **模型知识属 gateway（available models）· README §3.B（verbatim，标注 🔻 = 公共但现散 ③a）**：
> "**按同类分组（model group）**（🔻 现 `llm_model_groups.py`）：把同一模型的多个变体 / 快照 / 渠道折叠成一个用户可见的"模型组"……**品牌 / 家族识别（identity）**（🔻 现 `llm_model_identity.py`）……**Probe Knowledge Catalog + notable**（🔻 现 `probe_catalog.py` / legacy `llm_import_drafts.py` / `llm_notable_models.py`）：记住"哪些 endpoint 连通过、哪些模型存在 / 可用、哪些能力被探测证实、哪些模型值得优先试"……这是 gateway 背后可沉淀、可共享的知识资产。"

> **编排 / 调用分离 · D2（决策）+ PM 原话（verbatim，不改一字）· 另见 [[10-inv-route-chat-model-factory]] / [[09-inv-invocation-runtime]]（同一 D2，跨模块共享，重复留底防 drift）**：
> **决策（D2）**：把「编排（orchestration）」与「调用（invocation）」做成两个内聚模块，各有明确 API。**编排层**：输入 role_name / model_override，输出解析好的 `ResolvedRoute`(s)（protocol / base_url / credential_ref / provider_model_id / runtime settings + fallback 顺序 + 熔断/probe 决策），**只决定「该用哪条 route」，不负责真正调用**。**调用层**：输入一条 `ResolvedRoute` + messages（+ runtime params），输出 `AIMessage` / 结果，负责 build 原生 ChatX + invoke + 取结果。对 05 的含义：05 产出的 capability/profile 编排字段（`call_method_id` / `request_mapper_id` / `capabilities` / `effective_runtime_settings`）是**编排层输出**，A' 迁移时它们成为「route → 原生 ChatX 调用适配（RouteChatModelFactory，M6）」的**输入**，**而不是 gateway 自研消息转换的理由**——gateway 不再自己做消息转换，改由原生 ChatX 消费这些字段。
> **PM 原话**："你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了, 这是调copilot的路径,你只负责输出编排结果, 不负责调用. 所以这里还引申出一个问题, 编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么"

**编排字段消费（数据流，原 §2.2 步 6，跨 F1/F3/F7 输出）**：调用层消费 `ResolvedRoute.call_method_id` / `request_mapper_id` / `capabilities` / `effective_runtime_settings`；MVP1 A' 迁移时这些字段仍是 route 到 ChatX 调用适配（[[10-inv-route-chat-model-factory]]）的输入，**而不是 gateway 自研消息转换的理由**（`registry/schema.py:415-438`；依据 = D2 编排/调用分离，见上方「编排 / 调用分离」）。

**跨功能决策 + 动机**：

1. **模型知识能力内核 = ③b 公共（本轮反转，原 §决策原因 #5 被否）**：把原始 model id 客观**分组（model_groups）/ 归类品牌家族（identity）/ 沉淀已知可用知识（notable）/ 合并静态+探测能力（route_capabilities）**，是 gateway 对模型数据的标准化/组织/知识沉淀，换任何调模型 app 都原样要用 → **③b 公共**（README §3.B、disposition 表行 32-35）。**被否**：原 §决策原因 #5 判"Studio model identity 和 model group 留在后端 service，原因是展示归一化属于**产品解释，不是 Gateway runtime schema**；代码注释要求 routers 调 service 不在路由内联清洗"——其中"调 service 不内联"作为代码组织约束仍对，但"属产品解释/不是 Gateway schema → 留 ③a"的**定调全部反转**为"③b 公共能力内核，现散 ③a `apps/studio/backend/app/services` 待下沉"。**留 ③a 的只有**：展示名样式覆盖、family 折叠、弃用区、notable 数据源路径注入、identity 展示投影渲染。**被否（原 §1 #5）**：原 §1 #5 把它们整体判成"显示/解释层、不改变 runtime route_id、属产品解释"——其能力内核被错划 ③a，现反转为 ③b 公共。**关键边界（判据，目标语义）**：**model group / identity / notable / route_capabilities = 模型知识的客观加工**（分组/归类/合并都不依赖 UI/产品策略/调用方式/存储介质），换任何 app 都要 → **③b 公共**。
2. **选择显式 route chain 而不是动态能力搜索**（原 #1 保留）：让 role 执行可复现、可解释、可由 Studio 审核；MVP1 README §3.E 已把 lint 定为“不替应用选型”，当前代码也只遍历显式 `fallback_chain[*].route_id`,不会按 provider/capability/price/latency/availability 搜索替代 route（`registry/schema.py:264-273`, `registry/lint.py:27-87`）。**注**：下沉 model_groups/identity/notable/route_capabilities 到 ③b **≠ 引入动态选型**——它们是**分类/知识/能力描述**，runtime 仍按显式 `route_id` 执行（README §3.E lint「不替应用选型」、disposition §0）。
3. **A' 不改 05 核心分类/归一化规则，只迁调用层**（原 §已实现/差异 #5 保留）：MVP1 A' 不要求重写 05 的归一化/分类规则，而是要求调用层换 ChatX 时**继续保留这些编排字段和投影**；selected profile 从 client manager dispatch 输入改为 `ResolvedRoute` 上的调用方法提示，交 RouteChatModelFactory/provider profile 适配层消费（依据 = D2 编排/调用分离，完整决策 + PM 原话见上方「编排 / 调用分离」；调用层落点 [[10-inv-route-chat-model-factory]] / [[11-inv-provider-profiles]]）。

**跨功能测试关键点**：

- **无动态选型回归**：05 不新增任何"按 capability/price/latency 自动找别的 route"路径（架构边界，非缺功能）。

---

## 功能逐项（每个功能为索引）

### F1 capability 规范化 / 探测 + 控件描述符（`normalize_route_capabilities` / `build_runtime_setting_descriptors`）

- **机制 / 数据流**：① provider raw metadata / list-models / probe result →〔**归一化 ③b**〕`normalize_route_capabilities` → route capabilities → 〔**描述符 ③b**〕`build_runtime_setting_descriptors` → 前端控件。导入/探测阶段拿到 provider raw metadata 或 probe result，调用 `normalize_route_capabilities`（把 provider/API/raw metadata 归一成 route capability 字典的函数）归一化为 route capabilities（`registry/capabilities.py:35-202`，`apps/studio/backend/app/routers/llm.py:806-815`）。**判据 ③b**。Studio registry API 调 `build_runtime_setting_descriptors`（把 route capability 转成前端可安全渲染的 runtime setting 控件描述的函数），把每条 route 的 capability 投影成固定 11 个 runtime setting 控件描述（`registry/capabilities.py:205-217`，`apps/studio/backend/app/routers/llm.py:1377-1380`）。**判据 ③b**（控件描述符是公共能力，前端只选"关心哪几种能力" → README §3.C）。
  - capability 是 route metadata。`CapabilityValue`（保存能力值、来源、观测时间、说明文字的结构）用于保存能力值和来源，**不得承载用户本次请求意图**（`registry/schema.py:67-75`, `registry/capabilities.py:1-5`）。**判据**：归一化是 ③b 公共（README §3.C）。
  - runtime intent 是 role/profile route entry。`RuntimeSettings`（保存用户写在 route entry 上的 provider-neutral 运行参数的结构）用于保存 temperature、max_output_tokens、reasoning 等（`registry/schema.py:121-135`）。
  - **关键边界（判据，目标语义）**：capability = route **内在事实**（支持/默认/边界），不承载用户本次请求意图；runtime intent = role/profile route entry 的 `RuntimeSettings`。
- **决策 + 动机**：**capability 保持"描述事实"，runtime settings 保持"用户意图"**（原 #2 保留）：避免把 provider 默认值误当成用户想要的参数；当前代码把 capability schema 与 runtime intent schema 分开,并在 capability 模块注释里钉明“不编码 user runtime intent”（`registry/schema.py:67-75`, `registry/schema.py:121-135`, `registry/capabilities.py:1-5`）。
- **测试点**：
  - **capability 不承载意图**：normalized capabilities 里**不出现**用户本次 `RuntimeSettings`（temperature/reasoning 等）——只描述 support/default/bounds（防把 provider 默认值当用户意图）。
  - **token 别名归一**：`max_output_tokens`/`maxOutputTokens`/`max_tokens`/`outputTokenLimit`/嵌套 `token_limits` 全收敛到 `max_output_tokens`；`max_input_tokens`/`context_window`/`context_length` 收敛到 `max_input_tokens`（`capabilities.py:62-107`）。
  - **Anthropic thinking 规则**：Opus 4.7 禁手动 budget → `manual_thinking_budget_supported=False`；Claude 4.6/4.7 家族 → `adaptive_thinking=True`（`capabilities.py:144-201`）。
  - **控件描述符固定 11 项**：`build_runtime_setting_descriptors` 输出数量恒定，前端不漏控件（`capabilities.py:205-217`）。
- **status**：已实现——capability 归一化已覆盖 token limit 别名、modalities、runtime setting descriptors、tool/vision/structured output 和 Anthropic thinking 规则（`registry/capabilities.py:55-201`）。A' 换 ChatX 不动。
- **归属**：**③b** `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py`（归一化 + 描述符），已在包内。

### F2 lint（只 warn/block，不驱动选型）（`lint_role_routes`）

- **机制 / 数据流**：role 解析时 → 〔**lint ③b**〕`lint_role_routes` warn/block。lint 是配置守门。`lint_role_routes`（对显式 role fallback chain 逐 route 检查能力要求和 runtime 边界的函数）用于产出 warn/error/blocking，blocking 可让解析失败，但 **lint 不改变 fallback_chain，也不根据 capability 动态补 route**（`registry/lint.py:27-87`，`registry/resolver.py:116-122`）。resolver 对已解析出来的 route 列表调用 `lint_role_routes`；如果有 blocking lint，抛 `RegistryResolutionError`（registry 解析失败异常），否则把 lint_results 带到 `ResolvedRole`（解析后的 role 元数据和有序 routes 的结构）（`registry/resolver.py:116-132`）。**判据 ③b**。
  - **关键边界（判据，目标语义）**：lint = 配置守门，不按能力补 route。
- **决策 + 动机**：**lint 设计成 warn/block**（原 #4 保留）：capability 缺失可能只是需要 probe，不能自动推断"另一个 route 更好"；error 级缺失才 blocking 并给 `requires_probe`（`registry/lint.py:45-57`，`registry/lint.py:74-86`）。
- **原话**：
  > **lint 不替应用选型 · README §3.E（verbatim）**：
  > "**lint 校验**（✅ `registry/lint.py:lint_role_routes`）：检查路线配置是否满足能力要求，只 warn / block，不替应用选型。"
- **测试点**：**lint 只产结果不改链**：blocking lint → `RegistryResolutionError`，但 `fallback_chain` 顺序/成员**不变**；非 blocking → 进 `ResolvedRole.lint_results`（防 lint 退化成动态选型）。
- **status**：已实现——lint 已覆盖缺 capability、capability incompatible、未验证 error capability 以及 runtime setting 超界/不支持（`registry/lint.py:39-87`、`:90-332`）。
- **归属**：**③b** `packages/graph-agent-gateway/src/graph_agent_gateway/resolve/lint.py`（lint）+ `registry/resolver.py`（调用使用链），已在包内。

### F3 profile_selector（单 route 内"怎么调"）（`select_verified_profile`）

- **机制 / 数据流**：role 解析时：`resolve_role` 按 `fallback_chain` 取 route → 〔**profile 选择 ③b**〕`select_verified_profile` 选单 route 内调用方式。profile selection 是单 route 内的"调用方法选择"。`select_verified_profile`（在当前 route 的 ready profiles 中选 method_id/request_mapper_id 的函数）用于在当前 route 选调用方式，**不跨 route 找替代模型**（`registry/profile_selector.py:14-52`）。**判据**：单 route 内选择 = ③b 公共。用户把 model profile 应用到 role 后，role 保存精确 `fallback_chain[*].route_id`；`RoleEntry`（保存可执行 role 的显式 fallback_chain 和 lint_requirements 的结构）用于保存这个显式链和 lint requirements（`registry/schema.py:264-273`）。resolver 解析 role 时按 fallback_chain 顺序取 route，调用 `select_verified_profile` 选当前 route 的 verified profile，并把 profile id、capability、method_id、request_mapper_id 写入 `ResolvedRoute`（一条 runtime-ready route candidate 的结构）（`registry/resolver.py:55-113`）。**判据 ③b**。
  - **关键边界（判据，目标语义）**：profile selection = 单 route 内"怎么调"，不跨 route 选"调谁"。
- **决策 + 动机**：**verified profile 只在单 route 内选择调用方法**（原 #3 保留）：能支持同一模型 route 的不同 protocol/method 实测结果，但**不会把一条失败 route 替换成另一条未知 route**；`select_verified_profile` 只接收单个 `ProviderRoute` 的签名固化了这条边界（`registry/profile_selector.py:14-19`，`packages/graph-agent-gateway/tests/test_registry_profile_selector.py:246-281`）。
- **测试点**：
  - **profile 选择不跨 route**：单 route 无 ready profile → 返回 `None`（不失败、不去别的 route 找）；要 reasoning 但本 route 无 reasoning profile → `ProfileSelectionError`（不替换 route）。
  - **profile 排序稳定**：default → fallback_rank → profile_id 三键排序，多次解析结果一致（`profile_selector.py:69-73`）。
- **status**：已实现——profile selection 已按 ready status、required modalities、reasoning intent 和 default/fallback_rank/profile_id 稳定排序（`registry/profile_selector.py:21-52`、`:69-73`）。输出作 `ResolvedRoute` 调用方法提示。
- **归属**：**③b** `packages/graph-agent-gateway/src/graph_agent_gateway/resolve/profile_selector.py`（profile 选择）+ `registry/resolver.py`，已在包内。

### F4 model_groups 分组（`project_model_group_identity`）

- **机制 / 数据流**：同一份 route capabilities 被 〔**分组 ③b（现散 ③a）**〕`project_model_group_identity` 投影成 Available Models 模型知识 DTO（③a 套上 family 折叠 / 弃用区 / 展示名样式）。`project_model_group_identity`（把同模型多变体折叠成一张模型组卡身份的函数）= **把原始模型数据标准化/组织/合并/沉淀知识，换任何 app 都要 → ③b 公共**；它**不改变 runtime route_id**（runtime 仍按显式 `route_id` 执行）（`apps/studio/backend/app/services/llm_model_groups.py:43-68`）。**留 ③a 的只有**：展示名样式覆盖 / family 折叠 / 弃用区分区 / identity 展示投影渲染。Studio 前端通过 registry DTO 看到 model_groups；它**展示**这些信息（套 family 折叠 / 弃用区 / 颜色），但 **role 执行仍以保存的 route chain 为准**（`apps/studio/backend/app/routers/llm.py:1361-1383`）。**判据**：model_groups DTO 的分组内核 ③b（现散 ③a），渲染 ③a。
  - **关键边界（判据，目标语义）**：model group = 模型知识的客观加工（分组不依赖 UI/产品策略/调用方式/存储介质），换任何 app 都要 → ③b 公共。
- **决策 + 动机**：分组内核归属反转见「跨功能设计依据」决策 #1（model_groups 与 identity/notable/route_caps 同批反转为 ③b 公共能力内核，现散 ③a 待下沉）。本功能特定边界：`project_model_group_identity` 折叠同模型多变体后 runtime 仍用精确 `route_id`。
- **原话**：
  > **PM §0 原话 item 2（verbatim，不改一字，model group 用户语境）**：
  > "llm role 页面, 根据规则过滤 available models: llm 模型, endpoint测通的; 新建role , 拖动 model group(相同模型合并, endpoint 状态颜色和APIkey页面一样) 到 roles card……"（ux-spec §0 行 15）

  > **留 ③a 的应用加工层 · PM §2.0 #R3 原话（verbatim，family 折叠 = ③a 产品策略/展示）**：
  > "#R3 在model family上做一个折叠功能: anthropic 可以折叠起来, 隐藏里面的所有模型"（ux-spec §2.0 行 80）→ family 折叠 = 展示策略，留前端 ①/③a；identity 的"归类成 anthropic 家族"内核 = ③b。
- **测试点**：**模型知识 = 客观分组、不影响执行**：`project_model_group_identity` 折叠同模型多变体后，runtime **仍用精确 `route_id`** 执行（`llm_model_groups.py:48-53` 注释「exact execution still uses each route_id」必测）。
- **status**：已实现——Studio registry response 已输出 model_groups（`apps/studio/backend/app/routers/llm.py:1361-1383`）。分组内核下沉 gateway；family 折叠/弃用区展示留 ③a = target。
- **归属**：**③b 公共能力内核（现散 ③a 待下沉）** `apps/studio/backend/app/services/llm_model_groups.py`（分组）。**③a 应用加工（留 studio / 前端）**：展示名样式覆盖、family 折叠、弃用区分区。

### F5 identity 品牌/家族识别（`project_model_identity`）

- **机制 / 数据流**：同一份 route capabilities 被 〔**识别 ③b（现散 ③a）**〕`project_model_identity` 投影成模型知识 DTO。`project_model_identity`（把 route/endpoint 名解析成品牌/家族归类的函数）= **把原始模型数据标准化/组织/合并/沉淀知识，换任何 app 都要 → ③b 公共**；它**不改变 runtime route_id**（runtime 仍按显式 `route_id` 执行）（`apps/studio/backend/app/services/llm_model_identity.py:83-121`）。**留 ③a 的只有**：identity 展示投影渲染。
  - **关键边界（判据，目标语义）**：identity = 模型知识的客观加工（归类不依赖 UI/产品策略/调用方式/存储介质），换任何 app 都要 → ③b 公共。identity 的"归类成 anthropic 家族"内核 = ③b；family 折叠（展示策略）留前端 ①/③a（见 F4 #R3 原话）。
- **决策 + 动机**：识别内核归属反转见「跨功能设计依据」决策 #1（identity 与 model_groups/notable/route_caps 同批反转为 ③b 公共能力内核，现散 ③a 待下沉）。
- **测试点**：（与 F4「模型知识 = 客观分组、不影响执行」同一架构边界——投影不改变 runtime 精确 route_id 执行。）
- **status**：识别内核下沉 gateway；展示名样式覆盖留 ③a = target。
- **归属**：**③b 公共能力内核（现散 ③a 待下沉）** `apps/studio/backend/app/services/llm_model_identity.py`（品牌/家族识别）。**③a 应用加工**：展示名样式覆盖、identity 展示投影渲染。

### F6 notable 已知可用知识库（`notable_model_ids`）

- **机制 / 数据流**：〔**知识 ③b（现散 ③a）**〕`notable_model_ids` 投影成模型知识 DTO（沉淀"哪些模型存在/可用/值得试"）。`notable_model_ids`（从 provider notes 文档提取已知可用 model id 的函数）= **把原始模型数据标准化/组织/合并/沉淀知识，换任何 app 都要 → ③b 公共**（`apps/studio/backend/app/services/llm_notable_models.py:16-37`）。**留 ③a 的只有**：notable 数据源路径注入 / notable 在哪个面板展示。
  - **关键边界（判据，目标语义）**：notable = 模型知识的客观加工（沉淀已知可用知识不依赖 UI/产品策略/调用方式/存储介质），换任何 app 都要 → ③b 公共。
- **决策 + 动机**：知识库归属反转见「跨功能设计依据」决策 #1（notable 与 model_groups/identity/route_caps 同批反转为 ③b 公共能力内核，现散 ③a 待下沉）。
- **测试点 / 现状 gap（原 baseline #3）**：`notable_model_ids` 依赖 Markdown 小节标题精确等于 `## 4. Notable Model IDs`；provider notes 标题变化会静默返回空列表，目前无运行时错误提示（`apps/studio/backend/app/services/llm_notable_models.py:8-37`）。下沉 ③b 时应让"找不到小节"显式 WARNING，不静默吞。
- **status**：知识库下沉 gateway；数据源路径注入 + 展示面板留 ③a = target。
- **归属**：**③b 公共能力内核（现散 ③a 待下沉）** `apps/studio/backend/app/services/llm_notable_models.py`（已知可用知识）。**③a 应用加工**：notable 数据源路径注入、notable 在哪个面板展示。

### F7 route_capabilities 合并（`route_effective_capabilities`）

- **机制 / 数据流**：route capabilities → 〔**合并 ③b（现散 ③a）**〕`route_effective_capabilities`（并入 ready verified profile facts）→ 供描述符/投影/lint 复用。`route_effective_capabilities`（把静态声明能力 + ready verified profile 派生能力合并的函数）= **把原始模型数据标准化/组织/合并/沉淀知识，换任何 app 都要 → ③b 公共**；它**不改变 runtime route_id**（runtime 仍按显式 `route_id` 执行）（`apps/studio/backend/app/services/llm_route_capabilities.py:10-64`）。
  - **关键边界（判据，目标语义）**：route_capabilities = 模型知识的客观加工（合并不依赖 UI/产品策略/调用方式/存储介质），换任何 app 都要 → ③b 公共。
- **决策 + 动机**：能力合并归属反转见「跨功能设计依据」决策 #1（route_capabilities 与 model_groups/identity/notable 同批反转为 ③b 公共能力内核，现散 ③a 待下沉）。
- **疑点（原 #2）**：resolver 是否应使用 `route_effective_capabilities` 合并 ready verified profile facts 后再 lint，目前源码没有这样做；这可能影响 verified profile 对 thinking capability 的补强（`apps/studio/backend/app/services/llm_route_capabilities.py:10-19`，`registry/resolver.py:104-116`）。下沉 `route_effective_capabilities` 到 ③b 后，resolver 与 Studio 投影可共用同一份合并能力。
- **status**：能力合并下沉 gateway；可供 resolver lint 复用 = target。
- **归属**：**③b 公共能力内核（现散 ③a 待下沉）** `apps/studio/backend/app/services/llm_route_capabilities.py`（静态+探测能力合并）。

### F8 capability 就绪轴（D2，第二轴 capability_state）（`_capability_state`）

> 源：`studio-llm-platform-control-plane-runtime` R5.3「role 要 thinking/tools/structured/vision 时，capability 就绪与 availability 就绪分开记」；studio `00_settings-ux-spec.md §4.2` 已立 `capability_state` 轴。（PM 2026-06-03 需求对账补；接 gaps。）

- **机制 / 数据流**：`_capability_state(capabilities) -> Literal["unknown","callable_only","partial","known"]`（capability 就绪轴，现散 ③a `routers/llm.py`，已按四态落地）。
  - **capability 两个正交面**：① **支持**（route 是否声称 thinking/tools/structured/vision —— 现已覆盖）；② **capability 就绪** = 每个契约是否 **probe-verified**（`CapabilityValue.source==probed_verified`，`schema.py:67-74`）vs 仅 doc/list/draft 声称 vs 未知。
  - **四态轴**：`unknown`(无线索)/ `callable_only`(key/endpoint 通但无契约验证)/ `partial`(部分契约 verified)/ `known`(全 verified)。**判据 = 按每个 capability 的 `source` 算，不并入 `route.status`（availability）**。
- **决策 + 动机**：**轴归属（Claude 定，PM 可推翻）**：`capability_state` 是 **route 内在轴**（ux-spec §4.2「了解多少能力」），按 route **声称**的 capability 集算；"适不适合本角色"是另一条 `role_fit`(role 级)——两者不混。判据归属 = ③b 标准总结（现散 ③a 待下沉）。投影侧落点见 [[08-orch-test-status-ssot]] 回填。
- **测试点**：**capability_state 四态（D2 回填）**：`unknown`(无线索)/`callable_only`(key/endpoint 通无契约验证)/`partial`(部分契约 probe-verified)/`known`(全 verified)，**按 per-capability `source` 算，不并入 `route.status`**；`tools`/`structured_output` 改派生（不再硬编码 `unknown`，`llm.py:1778-1779`）。
- **现状 gap**：四态投影已落地：无线索→`unknown`，有非 verified 声称但无 probe→`callable_only`，部分 verified→`partial`，全部 fact capabilities verified→`known`；`tools`/`structured_output` summary 已改为按能力值派生。剩余 gap 是该 route 内在轴仍散在 ③a，后续可随模型知识下沉迁入 gateway。
- **status**：四态 capability_state 已实现；下沉 gateway = target。
- **归属**：route 内在轴（③b 标准总结，现散 ③a `routers/llm.py`，四态已实现，待随模型知识能力下沉）。投影侧落点 [[08-orch-test-status-ssot]]。

---

## gaps / 待设计

> 保留原"待办/疑点"全部条目。各功能特有的 gap/疑点已就地收进对应 ### F<n>（F6 notable Markdown 标题 gap、F7 resolver 合并疑点）；下列为跨功能 / 后续工程项。

- **代码下沉**（后续工程，非本轮）：`llm_model_groups.py` / `llm_model_identity.py` / `llm_notable_models.py` / `llm_route_capabilities.py` 的能力内核 → gateway 包；family 折叠 / 弃用区 / 展示名样式 / notable 数据源路径注入留 studio（disposition 下沉清单行 58-64）。
- **待办（原 #1）**：A' 实现 RouteChatModelFactory 时，需明确 `ResolvedRoute.call_method_id` / `request_mapper_id` 与新 provider profile init-kwargs 的映射边界，避免把 verified profile 误用成跨 route 动态选型（`registry/schema.py:432-435`；映射边界归调用层 [[10-inv-route-chat-model-factory]] / [[11-inv-provider-profiles]]，依据 = D2 + F6 provider init-kwargs profile）。
- **疑点（原 #3）**：`select_verified_profile` 的 reasoning 判断基于 profile 文本包含 thinking/reasoning，不是结构化 enum；若后续 profile capability 命名变化，需补测试保护（`registry/profile_selector.py:55-66`）。

## 交叉引用（链接，不复制）

- [[02-orch-role-resolution]]：`resolve_role` 消费 `select_verified_profile` + `lint_role_routes` 结果；materialize 意图过滤共享 capability 语义
- [[04-orch-registry-schema]]：`CapabilityValue`/`VerifiedProfile`/`LintResult`/`RuntimeSettingDescriptor`/`ResolvedRoute` 字段权威源（本模块只链接）
- [[08-orch-test-status-ssot]]：capability_state 第二轴投影落点（与 availability 6 态分开）
- [[10-inv-route-chat-model-factory]]：消费 `ResolvedRoute.call_method_id`/`request_mapper_id` 构造原生 ChatX
- [[11-inv-provider-profiles]]：provider 差异 → init-kwargs profile（消费 profile 选择结果）
- 决策日志：`packages/graph-agent-gateway/README.md` §2/§3 · `00_settings-ux-spec.md` §6.0 · `module-disposition-revised.md` 行 31-35

---

## 已实现 / 与 baseline 差异（模块级证据附录）

> 保留原"已实现/差异"全部条目 + 判据反转标注。逐功能 status 见各 ### F<n>；下表为全模块差异汇总。

1. **已实现**：capability 归一化已覆盖 token limit 别名、modalities、runtime setting descriptors、tool/vision/structured output 和 Anthropic thinking 规则（`registry/capabilities.py:55-201`）。
2. **已实现**：profile selection 已按 ready status、required modalities、reasoning intent 和 default/fallback_rank/profile_id 稳定排序（`registry/profile_selector.py:21-52`、`:69-73`）。
3. **已实现**：lint 已覆盖缺 capability、capability incompatible、未验证 error capability 以及 runtime setting 超界/不支持（`registry/lint.py:39-87`、`:90-332`）。
4. **已实现**：Studio registry response 已输出 lint_results、model_groups、route_runtime_settings、role_effective_runtime_settings（`apps/studio/backend/app/routers/llm.py:1361-1383`）。
5. **与 baseline 差异**：MVP1 A' 不要求重写 05 模块的核心分类/归一化规则，而是要求在调用层换 ChatX 时继续保留这些编排字段和投影（依据 = D2 编排/调用分离，见「跨功能设计依据」编排 / 调用分离）。
6. **与 baseline 差异**：当前 selected profile 仍服务于 client manager 的 provider-specific dispatch；MVP1 中它应作为 `ResolvedRoute` 上的调用方法提示，交给 RouteChatModelFactory/provider profile 适配层消费（`registry/resolver.py:94-113`；依据 = D2，落点 [[10-inv-route-chat-model-factory]] / [[11-inv-provider-profiles]]）。
7. **与 baseline 差异**：05 不新增 capability-based automatic routing；这点不是缺功能，而是架构边界（README §3.E，`registry/lint.py:27-87`, `registry/resolver.py:55-132`）。
8. **与 baseline 差异（本轮反转）**：原 baseline §差异 #4 把 Studio 投影定调为"显示/解释层，不是 runtime identity"，并据此暗示其归 ③a；本轮按判据反转——`model_groups`/`identity`/`notable`/`route_capabilities` 的**能力内核属 ③b 公共，现散 ③a 待下沉**，只有展示渲染留 ③a。runtime 精确执行保存的 route chain 这一点不变（`apps/studio/backend/app/services/llm_model_groups.py:50-53`）。

## 覆盖代码（含覆盖率）（模块级证据附录）

> 保留原覆盖率结论 + 归属列按判据更新。

覆盖率：8/8 个指定文件 100% 映射；公共入口 13/13 已纳入流程；关键调用点 `resolve_role`、`probe_route`、`_registry_response` 也已索引。本文未覆盖 [[11-inv-provider-profiles]] 的新增 provider profile 适配实现（README 放在调用层模块 11，`docs/graph-agent-gateway/mvp1/README.md:68`）。

| 文件 | 归属 | MVP1 目标 |
|---|---|---|
| `registry/capabilities.py`（`normalize_route_capabilities` 归一化 + `build_runtime_setting_descriptors` 控件描述符） | **③b**（已在包内） | 保留归一化规则与 11 控件描述符；A' 换 ChatX 不动 |
| `registry/profile_selector.py`（`select_verified_profile` 单 route 内选 ready profile） | **③b**（已在包内） | 保留单 route 选择语义；输出作 `ResolvedRoute` 调用方法提示 |
| `registry/lint.py`（`lint_role_routes` 显式链 lint，不选型） | **③b**（已在包内） | 保留 warn/block，守"不动态选型"边界 |
| `services/llm_model_identity.py`（`project_model_identity` 品牌/家族识别） | **③b 能力内核（现散 ③a 待下沉）** | 识别内核下沉 gateway；展示名样式覆盖留 ③a |
| `services/llm_model_groups.py`（`project_model_group_identity` 同模型折叠成组卡） | **③b 能力内核（现散 ③a 待下沉）** | 分组内核下沉 gateway；family 折叠/弃用区展示留 ③a |
| `services/llm_notable_models.py`（`notable_model_ids` 已知可用知识） | **③b 能力内核（现散 ③a 待下沉）** | 知识库下沉 gateway；数据源路径注入 + 展示面板留 ③a |
| `services/llm_route_capabilities.py`（`route_effective_capabilities` 静态+探测能力合并） | **③b 能力内核（现散 ③a 待下沉）** | 能力合并下沉 gateway；可供 resolver lint 复用 |
| 调用点（`resolve_role` 解析使用链 / `_registry_response` 组装 Studio registry DTO） | **③b**（`resolve_role`）+ **③a**（DTO 组装/渲染） | resolve 使用链不动；DTO 组装的分组/状态内核下沉 ③b，渲染留 ③a |

## 代码索引（clues）（模块级证据附录）

> 保留原代码索引全部条目 + 归属标注。

- `docs/graph-agent-gateway/mvp1/README.md:58` — 05 模块覆盖 brief。
- `packages/graph-agent-gateway/README.md:59-69` — §3.B 模型知识 + §3.C 能力（model group/identity/notable/route_capabilities 标 🔻 = 公共但现散 ③a）。
- `docs/graph-agent-gateway/mvp1/module-disposition-revised.md:42-45` — 四项反转判定（model_groups/identity/notable/route_capabilities → ③b 公共）。
- 历史 mvp0 材料只作背景,不作为本模块 baseline 或 MVP1 接口事实来源；本模块的现状依据以当前代码和 mvp1 README / disposition 为准。
- 「编排 / 调用分离」（D2，本文留底，见「跨功能设计依据」）— RouteChatModelFactory 目标是用 ResolvedRoute 构造原生 ChatX；落点 [[10-inv-route-chat-model-factory]]（决策记录系临时文档已不引用）。
- `registry/capabilities.py:20-32` — `RUNTIME_SETTING_DESCRIPTORS`（固定前端 runtime setting 控件集合的常量）。**③b**。
- `registry/capabilities.py:35-202` — `normalize_route_capabilities`（归一化 route capabilities 的函数）。**③b**。
- `registry/capabilities.py:205-269` — `build_runtime_setting_descriptors`（生成前端控件描述的函数）。**③b**。
- `registry/profile_selector.py:14-52` — `select_verified_profile`（单 route 内选 verified profile 的函数）。**③b**。
- `registry/lint.py:27-87` — `lint_role_routes`（role route lint，只产出结果的函数）。**③b**。
- `registry/resolver.py:72-132` — `resolve_role`（把 selected profile 和 lint_results 装入 resolved role 的函数）。**③b**。
- `apps/studio/backend/app/services/llm_model_identity.py:83-121` — `project_model_identity`（Studio 模型身份投影函数）。**③b 内核（现散 ③a）**。
- `apps/studio/backend/app/services/llm_model_groups.py:43-68` — `project_model_group_identity`（Studio 模型组投影函数）。**③b 内核（现散 ③a）**。
- `apps/studio/backend/app/services/llm_notable_models.py:16-37` — `notable_model_ids`（从文档提取 notable models 的函数）。**③b 内核（现散 ③a）**。
- `apps/studio/backend/app/services/llm_route_capabilities.py:10-64` — `route_effective_capabilities` / `verified_profile_route_capabilities`（合并 verified profile facts 的函数）。**③b 内核（现散 ③a）**。
- `apps/studio/backend/app/routers/llm.py:_capability_state` — capability 就绪轴已四态；`tools`/`structured_output` summary 已按能力值派生。
