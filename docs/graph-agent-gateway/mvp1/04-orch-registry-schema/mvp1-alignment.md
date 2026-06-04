---
module: 04-orch-registry-schema
doc: mvp1-alignment
status: drafted
---

# 04-orch-registry-schema — MVP1 Alignment(目标设计)

> **Tier**：③b gateway 公共能力(registry endpoint/route/role/profile/resolved runtime schema = Studio↔Gateway 共同契约；Studio DTO 的 display/authoring 字段是 ③a 应用加工，投影时剥离)
> **Owns**：定义 gateway 全部 runtime 数据结构(`ProviderEndpoint`/`ProviderRoute`/`RoleEntry`/`ModelProfile`/`ResolvedRoute`/`ResolvedRole`/`RegistrySnapshot`…)、canonical 保守分组、snapshot 加载校验；是其它模块「只链接不复制」的字段权威源
> **Status**：设计定稿(2026-06，基本已对，**无反转**)；代码 = schema 待补 skipped diagnostics + snapshot provenance(D1 回填)、`canonicalize_model` 保守不变、Studio DTO 剥离边界已对
> **Related**：[[01-handoff-interface]](`ResolvedRoute/ResolvedRole` 契约消费方)· [[02-orch-role-resolution]](`resolve_role` 用本 schema)· [[03-orch-credentials-endpoints]](`ProviderEndpoint` credential/base_url 字段)· [[05-orch-capabilities-and-models]](`CapabilityValue`/canonical 分组)· [[08-orch-test-status-ssot]](D1 snapshot 版本-stale 交叉)
> **决策日志**：本模块 schema 作为编排↔调用契约边界,依据 client 层 A' 重设计 D2(编排/调用分离——schema 是交接数据契约)+ D3(gateway 可复用服务,数据结构由它定义)——完整逻辑 + PM 原话留底于本文 §4/§5；归属判据见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`(04 registry schema = ③b 公共，原 review 已判对，不变)。D2/D3 是跨模块共享决策,另见 [[01-handoff-interface]] §4(route 契约同引 D2/D3)、[[03-orch-credentials-endpoints]] §4(凭证边界同引 D3)。
> **现状**：见同目录 `baseline.md`

MVP1 目标:把 registry schema 固定为 Studio↔Gateway 的共同契约。Studio 可以有 display/authoring 字段,但 runtime snapshot 只消费 gateway schema;canonical 分组只做保守展示和 profile 组织,不驱动动态 route 选择。

## 1. 定义

MVP1 目标：把 registry schema 固定为 **Studio↔Gateway 的共同契约**——这套 endpoint/route/role/profile/resolved runtime 数据结构是 gateway 机制本身的数据模型，任何调模型的 app 装上 gateway 都用同一套，因此整块归 **③b 公共**。

按判据「换个 app 还原样能用吗?能=③b」拆开本模块：
- **③b 公共契约**：`registry/schema.py` 全部 gateway runtime DTO + 字段校验 + `canonicalize_model` 保守分组 + snapshot 加载校验。这是 gateway 的数据模型，跨 app 复用。
- **③a 应用加工**：Studio DTO(`models/llm_config.py`)在 gateway 字段之上额外挂的 **display 字段(如 `display_name`)/ authoring 字段** —— 这些是「用户怎么看 / 怎么编辑」(① UI / ③a 加工)，投影到 gateway runtime snapshot 时**剥离**。

**本模块无反转**(原 review 已判对 ③b)。本文只写文档目标，不改代码。

## 2. 数据流 / 机制(目标；现状逐步见 `baseline.md`)

**上下游**：Studio 文件(`LLMCredentialsFile` v4 + `RolesData` v2/v3，含 display/authoring 字段)→ `RolesData.to_registry_snapshot(credentials)`(剥 display/authoring，只留 gateway 字段)→ `RegistrySnapshot`(纯 gateway runtime)→ `resolve_role` 消费 → `ResolvedRole`/`ResolvedRoute`。schema 是这条流里所有节点共用的字段权威源。

**目标设计与流程**(逐步)：

1. `LLMCredentialsFile`(用途:Studio active credentials 文件 schema,固定 v4,持 endpoint/route/runtime_policy)继续作为 Studio v4 文件入口,保存 endpoint/route/runtime_policy;它可以包含 Studio 的 display labels(③a),但投影到 gateway 时必须剥离,见当前 `apps/studio/backend/app/models/llm_config.py:121-133`。

2. `RolesData`(用途:Studio active roles 文件 schema,允许 v2/v3,持 profiles/bundles/roles)继续作为 v2/v3 roles 文件入口,保存 model profiles、model bundles、roles,见当前 `apps/studio/backend/app/models/llm_config.py:257-266`。

3. `RolesData.to_registry_snapshot`(用途:把 Studio credentials + roles join 成 gateway runtime snapshot，剥 display/authoring)继续是 Studio↔Gateway schema 衔接点,输出 `RegistrySnapshot` 而不是 Studio response DTO,见当前 `apps/studio/backend/app/models/llm_config.py:279-296`。**这是 ③b 公共契约与 ③a 应用加工的剥离 seam。**

4. `_gateway_endpoint`(用途:把 Studio endpoint DTO 转成 gateway endpoint DTO,排除 display_name)、`_gateway_route`(用途:把 Studio route DTO 转成 gateway route DTO)、`_gateway_model_profile`(用途:把 Studio model profile DTO 转成 gateway model profile DTO)、`_gateway_role`(用途:把 Studio role DTO 转成 gateway role DTO)继续负责剥离 display/authoring 字段,见当前 `apps/studio/backend/app/models/llm_config.py:89-118`。

5. `ProviderEndpoint`(用途:表示一个可调用 endpoint 及其 credential/protocol metadata)继续承载 protocol/base_url/credential policy/timeout/proxy 等 endpoint 级事实;调用层只读 resolved route,不回读 Studio DTO,当前字段见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-181`。

6. `ProviderRoute`(用途:表示某 endpoint 上的一条物理模型 route)继续承载 provider model、canonical group、status、capabilities、verified profiles;`route_id` 继续是 runtime 唯一执行标识,当前校验见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-244`。

7. `RoleRouteEntry`(用途:表示 role/profile fallback 链里的一条 route 引用)继续承载精确 `route_id` 与 entry-specific runtime settings,让 role fallback 顺序由数据声明,见当前 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:247-255`。

8. `RuntimeSettings`(用途:表示一条 route entry 上用户配置的 provider-neutral 调用设置)与 `EffectiveRuntimeSetting`(用途:表示 resolver 产出的最终 runtime setting 及来源)继续分离:前者是用户/配置输入,后者是 resolver 输出,当前字段见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:121-145`。

9. `ResolvedRoute`(用途:表示一条 runtime-ready route candidate)继续作为编排→调用的唯一 route 交接物,必须包含 protocol、base_url、credential_ref、provider_model_id、canonical_id、effective runtime settings 等调用必需字段,见当前 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`。

10. `ResolvedRole`(用途:表示解析后的 role 元数据和有序 routes)目标上应增加 skipped diagnostics 与 snapshot provenance,以便 `resolve_role` 的跳过语义可观测;当前字段还没有这些位置,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-459`。

11. `load_registry_snapshot`(用途:从显式 v4 credentials 文件和 v2/v3 roles 文件加载 runtime snapshot)继续执行 hard cutover 校验,拒绝旧 schema,见当前 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:186-202`。

12. `_assert_v4_credentials`(用途:校验 credentials 文件处于 v4 hard cutover 边界)继续要求 schema version 4,并拒绝旧 provider credentials 字段,见当前 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:227-237`。

13. `_assert_supported_roles`(用途:校验 roles 文件处于 v2/v3 route-chain schema)继续拒绝旧 models/providers/active_model schema,见当前 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:240-261`。

14. `_gateway_roles_payload`(用途:把 Studio v3 roles 文件裁剪成 gateway runtime role payload)继续允许 v3 Studio roles 里有 authoring 字段,但 runtime 只保留 gateway role keys,见当前 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:264-289`。

15. `canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key)继续只做保守 canonical grouping;route 执行仍必须指向精确 route_id,当前逻辑见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:22-49`。

16. `RegistryResponse`(用途:表示 redacted registry response 和 grouped display metadata)继续可以包含 canonical groups、model groups、lint、runtime setting descriptors、role effective runtime settings,但这些是 **Studio 展示投影(③a)**,不是 gateway runtime 输入,见 `apps/studio/backend/app/models/llm_config.py:299-319`。

17. `_registry_response`(用途:组装 Studio LLM registry API response)继续按 `canonical_id` 分组展示 routes,并调用 `_role_effective_runtime_settings` 输出每个 role/route 的 effective settings,见 `apps/studio/backend/app/routers/llm.py:1336-1383`。

18. `_role_effective_runtime_settings`(用途:为 registry response 投影每个 role/route 的 effective runtime settings)目标上应使用同一个 route-only resolver API,避免直接调用 pure helper 后吞掉解析错误;当前直接调用 `resolve_role` 并在 `RegistryResolutionError` 时 continue,见 `apps/studio/backend/app/routers/llm.py:4588-4603`。

19. `models.py`(用途:gateway provider SDK wrapper 的预留边界)继续不承载 schema;未来 A' 的 provider wrapper 或 ChatX factory 应落在调用层模块,不是 registry schema 模块,当前占位见 `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`。

## 3. 接口契约

> 本模块**是** schema 权威源——其它模块「只链接不复制」字段清单指向这里。本表钉「schema = ③b 公共契约 vs Studio DTO = ③a 应用加工」的剥离 seam + 稳定性。

| 边界 | 契约 |
|---|---|
| **③b 公共契约(schema 字段)** | `registry/schema.py:16-468` 全部 gateway runtime DTO：`ProviderEndpoint`(`:163`)/`ProviderRoute`(`:207`)/`RoleRouteEntry`(`:247`)/`RoleEntry`(`:264`)/`ModelProfile`(`:276`)/`RuntimeSettings`(`:121`)/`CapabilityValue`(`:67`)/`VerifiedProfile`(`:189`)/import-draft 系列(`:288-385`)/`RegistrySnapshot`(`:403`)/`ResolvedRoute`(`:415`)/`ResolvedRole`(`:448`)。`ConfigDict(extra="forbid")` 禁未知字段(如 `ProviderRoute:207-219`)。**这是本模块对全包的对外契约，其它模块只链接。** |
| **③a 应用加工(Studio DTO display/authoring 字段)** | `models/llm_config.py` 的 Studio wrapper 在 gateway 字段之上挂的 `display_name`(`:71-75`)等 display/authoring 字段 = **① UI / ③a 加工**，gateway 感知不到。剥离 seam = `to_registry_snapshot`(`:279-296`)+ `_gateway_*` helpers(`:89-118`)。 |
| **剥离边界(③a → ③b)** | `RolesData.to_registry_snapshot(credentials) → RegistrySnapshot`：把 display/authoring 剥掉，只把 gateway schema 字段放进 snapshot。测试断言 `test_studio_display_fields_are_stripped_from_gateway_runtime_snapshot`(`test_llm_config_boundary.py:53-59`)。 |
| **snapshot 加载校验(③b)** | `load_registry_snapshot`(`resolver.py:186-202`)+ `_assert_v4_credentials`(`:227-237`)+ `_assert_supported_roles`(`:240-261`)：hard cutover，拒绝旧 schema。 |
| **canonical 分组(③b 保守)** | `canonicalize_model(provider_model_id, …) → CanonicalModel`：explicit alias / `anthropic/` transport prefix / orphan slug 三种结果，默认 `confidence="orphan"`(`canonical.py:45-49`)。**只做保守分组，不驱动动态 route 选择**(route 执行仍指精确 route_id)。 |
| **稳定性 / re-export** | `registry/__init__.py:41-71` 的 `__all__` 是稳定 public surface；schema 新增字段(skipped diagnostics / snapshot provenance)后须同步 re-export。 |

## 4. 设计决策基础(用户原话)

> **判据(本模块「schema = ③b / Studio display = ③a」依据)**："换个 app 还原样能用吗?能=③b,不能=③a。"(ux-spec §6.0、`module-disposition-revised.md:15`) → gateway runtime schema 是 gateway 数据模型，任何调模型 app 复用 → **③b 公共**；Studio 的 `display_name` 等是「Studio 怎么展示/编辑」(绑死 UI)→ ③a，投影时剥离。**本模块无反转(原 review 已判对)。**

> **D2 编排/调用分离 → schema 是交接数据契约**(client 层 A' 重设计决策 D2)："编排和调用是不是应该更模块化更内聚化, API写清楚, 编排输入什么输出什么. 调用输入什么输出什么" → `ResolvedRoute/ResolvedRole` 作为编排↔调用交接物的数据契约，归 schema 模块。D2 是跨模块共享决策,另见 [[01-handoff-interface]] §4(route 契约消费方,同引 D2)、[[03-orch-credentials-endpoints]] §4。

> **D3 gateway = 可复用服务，数据结构由它定义**(client 层 A' 重设计决策 D3)："前端不归gateway管 ... gateway只管提供服务 ... 要考虑复用其他app" + README §2「存储介质(应用做)：数据结构与读写由它(gateway)定义，存到哪个介质由应用注入」→ schema 是 gateway 定义的数据结构(③b)，存储位置才是 ③a。D3 是跨模块共享决策,另见 [[01-handoff-interface]] §4、[[03-orch-credentials-endpoints]] §4。

> **D1 快照版本失效 → 重探**(R3.2，PM 2026-06-03 需求对账)：见下方「MVP1 回填 — 快照版本失效」整块，PM 要求「ClientSpec/版本变 → 相关就绪证据视为 stale 直到重探」，落到 schema = 给 `RegistrySnapshot` 加版本字段(③b 公共能力)。

## 5. 决策 + 动机

1. **schema 以 Gateway runtime 为源头(③b 公共，无反转)**：MVP1 架构把 `ResolvedRoute/ResolvedRole` 定为编排↔调用交接物,见 `docs/graph-agent-gateway/mvp1/README.md:13-18`。schema 是 gateway 数据模型，原 review 已判对 ③b，本轮不变。
2. **Studio wrapper 保留 display/authoring 字段但投影时剥离(③a 加工)**：为了同时满足 UI 可编辑性和 runtime 严格性;`RolesData.to_registry_snapshot` 正是这条边界,见 `apps/studio/backend/app/models/llm_config.py:279-296`。display 字段绑死 UI → ③a；投影剥离保证 gateway runtime snapshot 不被污染。
3. **v4/v2 hard cutover**：为了避免旧 schema 混入 runtime。`_assert_v4_credentials` 拒绝旧 credentials 字段,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:227-237`;`_assert_supported_roles` 拒绝旧 role schema,见 `:240-261`。
4. **用 route-chain schema 替代旧 models/providers/active_model schema**：为了让 runtime identifier 变成精确 `route_id`,避免 provider/model 模糊匹配;`ProviderRoute` 强制 `route_id == endpoint_id:route_slug`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:239-244`。
5. **canonical 分组不用于自动选型(保守)**：canonical 只是保守 grouping key;`canonicalize_model` 默认 `orphan`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:45-49`。保守是为了避免不同 provider 的相似模型名被误合并。
6. **`models.py`(用途:gateway provider SDK wrapper 的预留边界)不承担 registry schema**：为了把「编排数据契约」(`ResolvedRoute/ResolvedRole` 这套 schema)和「调用实现适配」(provider SDK wrapper / ChatX factory)分开。这呼应 client 层 A' 重设计 D2「编排/调用分离」(完整逻辑 + PM 原话见本文 §4「D2」);编排侧产出纯数据 route,调用侧吃 route 构造 ChatX,两者各自内聚。未来 provider wrapper 落调用层模块([[09-inv-invocation-runtime]]/[[10-inv-route-chat-model-factory]]),不进 registry schema。

## 6. 测试关键点

- **Studio display 字段被剥离**：endpoint/route/profile 的 `display_name` 等 display/authoring 字段**不进** gateway runtime snapshot(回归 `test_studio_display_fields_are_stripped_from_gateway_runtime_snapshot`，`test_llm_config_boundary.py:53-59`)。
- **schema 禁未知字段**：gateway DTO `extra="forbid"` —— 给 `ProviderRoute` 塞未知字段应报错(防 ③a 字段悄悄漏进 ③b runtime)。
- **v4/v2 hard cutover**：v3 credentials / 旧 models-providers roles → 加载报错(`_assert_v4_credentials`/`_assert_supported_roles`)；不静默回退旧 schema。
- **canonical 保守不误合并**：不同 provider 的相似模型名 → 默认各自 `orphan`，不被合并到同一 canonical group。
- **route_id 形状校验**：`ProviderRoute.route_id == endpoint_id:route_slug`；`RoleRouteEntry.route_id` 走 `ROUTE_ID_RE`。
- **snapshot 版本传播(D1)**：`RegistrySnapshot` 加 `snapshot_version` 后，`resolve_role` 构造的每条 `ResolvedRoute.snapshot_version` 应被填上(现恒 `None`)；任一版本戳变 → 旧就绪证据视 stale(交叉 08)。
- **skipped diagnostics 字段就位**：`ResolvedRole` 加 skipped 字段后，能表达 route_id / reason_code / message / 是否来自 override(供 02 跳过语义可观测)。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`registry/schema.py`(全部 runtime DTO，权威源)、`registry/__init__.py`(public surface)、`registry/canonical.py`(保守分组)、`resolver.py:186-289`(snapshot 加载 + v4/v2 校验)、`models.py`(provider wrapper 占位)。
- **③a** `apps/studio/backend`：`models/llm_config.py`(Studio file DTO + display/authoring 字段 + `to_registry_snapshot` 剥离 seam + `RegistryResponse` 展示投影)、`routers/llm.py`(`_registry_response`/`_role_effective_runtime_settings` 展示组装)。
- **② Rust**：N/A(角色/凭证/schema 数据永不 Rust)。

## 8. gaps / 待设计

1. 待办:在 `ResolvedRole`(用途:表示解析后的 role 元数据和有序 routes)中加入 skipped diagnostics,字段至少应能表达 route_id、reason_code、message、是否来自 override;当前字段不足,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-459`。
2. 待办:明确 `SnapshotVersion` 的写入和传播(见下方 D1 回填整块)。`ResolvedRoute`(用途:表示一条 runtime-ready route candidate)有 `snapshot_version`,但当前 `RegistrySnapshot` 没有版本字段且 resolver 未赋值,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:403-439`。
3. 待办:如果 route-only API 成为正式 contract,`registry.__init__`(用途:把 registry 公共 schema/contract 作为稳定 import surface 导出)需要同步导出新增 diagnostics DTO,当前 public list 见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py:41-71`。
4. 疑点:`canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key)的 `endpoint_id` 当前被 `del endpoint_id` 丢弃,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:22-30`;未来 explicit alias 是否应按 endpoint/provider 作用域区分,需要产品与数据来源判断。

## 已实现 / 与 baseline 差异

已实现:v4 credentials 与 route registry 已是 Studio active schema。`LLMCredentialsFile`(用途:表示 Studio active credentials 文件 schema)固定 `schema_version=4`,见 `apps/studio/backend/app/models/llm_config.py:121-129`;测试覆盖 v4 redaction 与旧 v3 拒绝,见 `apps/studio/backend/tests/services/test_llm_v4_backend_contract.py:58-74`。

已实现:v2/v3 roles 已是 route-chain schema。`RolesData`(用途:表示 Studio active roles 文件 schema)允许版本 2/3,并持有 `roles: dict[str, RoleEntry]`,见 `apps/studio/backend/app/models/llm_config.py:257-266`。

已实现:Studio display fields 不进入 runtime snapshot(③a→③b 剥离边界)。`test_studio_display_fields_are_stripped_from_gateway_runtime_snapshot`(用途:验证 Studio display fields 不进入 gateway runtime snapshot)明确断言 endpoint/route/profile 的 `display_name` 被剥离,见 `apps/studio/backend/tests/models/test_llm_config_boundary.py:53-59`。

已实现:canonical groups 已用于 Studio registry response 展示(③a 投影)。`_registry_response`(用途:组装 Studio LLM registry API response)按 `route.canonical_id` 聚合 route ids,见 `apps/studio/backend/app/routers/llm.py:1344-1374`。

未实现:skipped diagnostics/snapshot provenance 还未在 schema 中稳定表达。`ResolvedRoute`(用途:表示一条 runtime-ready route candidate)有 `snapshot_version`,但 resolver 构造时未填;`ResolvedRole`(用途:表示解析后的 role 元数据和有序 routes)没有 skipped 字段,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-459`。

未实现:`models.py`(用途:gateway provider SDK wrapper 的预留边界)还只是占位;A' 后调用层的 ChatX factory/provider profiles 还没在这个边界或其他调用层模块落地,见 `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`。

## 覆盖代码(含覆盖率)

覆盖率:5/5 个 brief 指定目标已覆盖,100%。其中 gateway schema 覆盖 `registry/schema.py:16-468`;public surface 覆盖 `registry/__init__.py:5-71`;canonical 覆盖 `registry/canonical.py:13-56`;Studio schema 衔接覆盖 `apps/studio/backend/app/models/llm_config.py:1-349`;provider wrapper 占位覆盖 `models.py:1-9`。

| 覆盖目标 | 判据归属 | MVP1 目标 |
|---|---|---|
| `registry/schema.py`(用途:定义 gateway endpoint/route/role/profile/resolved runtime schema) | **③b 公共契约(权威源)** | 保持 route-chain runtime schema,补 skipped diagnostics/snapshot provenance。schema 字段 = 全包共享的 ③b 公共契约。 |
| `registry/__init__.py`(用途:把 registry 公共 schema/contract 作为稳定 import surface 导出) | **③b 公共** | 继续只导出稳定 DTO/contract,新增 schema 字段后同步 re-export。 |
| `registry/canonical.py:canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key) | **③b 公共** | 保持保守 canonical 分组,只在明确 alias/transport normalization 时合并。 |
| `models/llm_config.py`(用途:Studio v4 credentials/v2-v3 roles 文件 DTO,并投影到 gateway snapshot) | **③a 应用加工(display/authoring)+ ③b 剥离 seam** | 保持 Studio display/authoring 与 gateway runtime 的剥离边界。display 字段 = ③a；`to_registry_snapshot` 剥离 seam 输出 ③b snapshot。 |
| `models.py`(用途:gateway provider SDK wrapper 的预留边界) | **③b 公共(占位)** | A' 调用层落地前继续占位;未来 provider wrapper 不进入 schema 模块。 |

## 决策原因(详细，承上 §5)

schema 要以 Gateway runtime 为源头,是因为 MVP1 架构把 `ResolvedRoute/ResolvedRole` 定为编排↔调用交接物,见 `docs/graph-agent-gateway/mvp1/README.md:13-18`。

Studio wrapper 保留 display/authoring 字段但投影时剥离,是为了同时满足 UI 可编辑性和 runtime 严格性;`RolesData.to_registry_snapshot`(用途:把 Studio credentials + roles join 成 gateway runtime snapshot)正是这条边界,见 `apps/studio/backend/app/models/llm_config.py:279-296`。

v4/v2 hard cutover 是为了避免旧 schema 混入 runtime。`_assert_v4_credentials`(用途:校验 credentials 文件处于 v4 hard cutover 边界)拒绝旧 credentials 字段,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:227-237`;`_assert_supported_roles`(用途:校验 roles 文件处于 v2/v3 route-chain schema)拒绝旧 role schema,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:240-261`。

canonical 分组不用于自动选型,是因为 canonical 只是保守 grouping key;`canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key)默认 `orphan`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:45-49`。

`models.py`(用途:gateway provider SDK wrapper 的预留边界)不承担 registry schema,是为了把"编排数据契约"和"调用实现适配"分开;这呼应 client 层 A' 重设计 D2「编排/调用分离」(完整逻辑 + PM 原话见本文 §4「D2」、§5 #6),provider wrapper 应落调用层模块而非 schema 模块。

## 代码索引(clues)

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:67-145`: capability 与 runtime settings schema。**③b 公共契约。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-285`: endpoint、route、role route entry、role、profile schema。**③b 公共契约。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:288-385`: import draft、candidate、probe、evidence schema。**③b 公共契约。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:403-459`: snapshot 与 resolved runtime schema。**③b 公共契约(权威源,其它模块只链接)。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py:41-71`: registry public `__all__`。**③b 公共。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:22-56`: `canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key)与 `_slug`(用途:把任意模型字符串收敛成小写 slug)。**③b 公共。**
- `apps/studio/backend/app/models/llm_config.py:89-118`: Studio DTO 到 Gateway DTO 的剥离 helper(③a→③b 剥离 seam)。
- `apps/studio/backend/app/models/llm_config.py:121-319`: Studio file DTO 与 registry response DTO(display/authoring = ③a)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:186-289`: snapshot 文件加载和 v4/v2-v3 校验。**③b 公共。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:1-9`: provider SDK wrapper 占位边界。**③b 公共(占位)。**

## 覆盖率

本 alignment 覆盖 brief 要求的 5 个代码目标,覆盖率 100%。其中 gateway schema 覆盖 `registry/schema.py:16-468`;public surface 覆盖 `registry/__init__.py:5-71`;canonical 覆盖 `registry/canonical.py:13-56`;Studio schema 衔接覆盖 `apps/studio/backend/app/models/llm_config.py:1-349`;provider wrapper 占位覆盖 `models.py:1-9`。

## 待办/疑点(原始留底，承上 §8)

1. 待办:在 `ResolvedRole`(用途:表示解析后的 role 元数据和有序 routes)中加入 skipped diagnostics,字段至少应能表达 route_id、reason_code、message、是否来自 override;当前字段不足,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-459`。

2. 待办:明确 `SnapshotVersion` 的写入和传播。`ResolvedRoute`(用途:表示一条 runtime-ready route candidate)有 `snapshot_version`,但当前 `RegistrySnapshot` 没有版本字段且 resolver 未赋值,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:403-439`。

3. 待办:如果 route-only API 成为正式 contract,`registry.__init__`(用途:把 registry 公共 schema/contract 作为稳定 import surface 导出)需要同步导出新增 diagnostics DTO,当前 public list 见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py:41-71`。

4. 疑点:`canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key)的 `endpoint_id` 当前被 `del endpoint_id` 丢弃,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:22-30`;未来 explicit alias 是否应按 endpoint/provider 作用域区分,需要产品与数据来源判断。

## 交叉引用(链接，不复制)

- [[01-handoff-interface]]：`ResolvedRoute/ResolvedRole` 契约消费方(本模块是其字段权威源)
- [[02-orch-role-resolution]]：`resolve_role` 用本 schema 解析
- [[03-orch-credentials-endpoints]]：`ProviderEndpoint` credential/base_url 字段
- [[05-orch-capabilities-and-models]]：`CapabilityValue` / canonical 分组消费方
- [[08-orch-test-status-ssot]]：D1 snapshot 版本-stale 交叉(下方回填整块)
- 本模块 schema 契约依据 client 层 A' 重设计 D2/D3(完整逻辑 + PM 原话留底于本文 §4/§5)+ D1 快照版本失效(留底于本文末「MVP1 回填」整块)/ 归属判据见 `module-disposition-revised.md`

---

## MVP1 回填 — 快照版本失效 → 重探(D1,PM 2026-06-03 需求对账补;解上方待办#2)

> 源:`studio-llm-platform-control-plane-runtime` R3.2「ClientSpec/版本变 → 相关就绪证据视为 stale 直到重探」。
> **判据归属:给 `RegistrySnapshot` 加版本字段 + 版本-stale 失效契约 = ③b 公共能力**(gateway 机制衍生:任何调模型 app 的就绪证据都该随版本失效),颜色/呈现留 ③a。

- **加版本到 snapshot**:给 `RegistrySnapshot`(`schema.py:403-412`,现无版本字段)加 `snapshot_version: SnapshotVersion`;`load_registry_snapshot`(`resolver.py:196-202`)加载时填(registry_version 来自 credentials 文件、generated_at 当场;client/terminal/probe-contract/catalog/profile 戳来自各自 owner)。
- **传播到 route**:`resolve_role`(`resolver.py:78-113`)构造每条 `ResolvedRoute` 时把 `snapshot.snapshot_version` 带上(现恒 `None`,补这一行)。
- **失效契约(R3.2)**:就绪证据(`route.status=verified` / `verified_profiles` / `capabilities`)**仅当 route 的 `snapshot_version` == 当前 snapshot 版本时可信**;任一版本戳变 → 旧证据视为 **stale → 运行期/admission 算 ready 前必须重探**。
- **失效粒度 = 粗粒度(Claude 定,PM 可推翻)**:任一戳变 → 相关就绪证据**全失效重探**(安全优先);"按戳因果细分哪个废哪个"作后续优化。
- **交叉 08**:版本-stale 的"曾 verified" route **不应**仅凭旧 `route.status=verified` 投成 🟢 ready —— 它正是 🔵 蓝(以前 verified、现未重验);见 08 回填 E1。
