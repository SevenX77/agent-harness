---
module: 04-orch-registry-schema
doc: baseline
status: drafted
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:RegistrySnapshot/ResolvedRoute/ResolvedRole · packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py · packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:canonicalize_model · packages/graph-agent-gateway/src/graph_agent_gateway/models.py · apps/studio/backend/app/models/llm_config.py:to_registry_snapshot
units: [registry-schema-contract]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 04-orch-registry-schema — Baseline(现状)

本文描述当前 registry schema、canonical 分组、snapshot 加载校验,以及 Studio DTO 如何桥接 gateway runtime schema。当前 schema 已是 v4 credentials + v2/v3 roles 的硬切形态,旧 `models/providers/active_model` schema 会被拒绝。

## 覆盖代码(含覆盖率)

覆盖率:5/5 个 brief 指定目标已覆盖,100%。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| `registry/schema.py`(用途:定义 gateway endpoint/route/role/profile/resolved runtime schema) | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:16-478` | 覆盖字段、校验、runtime DTO、import draft/evidence DTO。**判据:全部 gateway runtime schema 字段 = ③b 公共契约(全包共享的权威源,其它模块只链接不复制)。无反转。** |
| `registry/__init__.py`(用途:把 registry 公共 schema/contract 作为稳定 import surface 导出) | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py:5-71` | 覆盖 re-export 边界。**判据:③b 公共 import surface。** |
| `registry/canonical.py:canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key) | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:13-56` | 覆盖 alias、anthropic transport prefix、orphan slug。**判据:③b 公共(保守分组,不驱动动态选型)。** |
| `models/llm_config.py`(用途:Studio v4 credentials/v2-v3 roles 文件 DTO,并投影到 gateway snapshot) | `apps/studio/backend/app/models/llm_config.py:1-349` | 覆盖 Studio 展示字段、authoring fields、`to_registry_snapshot`。**判据:Studio DTO 的 display/authoring 字段(如 `display_name`)= ③a 应用加工(剥离 seam 已描述,投影时剥掉);`to_registry_snapshot` 输出的 gateway 字段 = ③b。详见 `mvp1-alignment.md` §3。** |
| `models.py`(用途:GenericRouteChatModel 通用 LangChain route wrapper) | `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:24-301` | 覆盖 `GenericRouteChatModel`、ordinary-chat dispatcher 桥接、tool binding 与 public `__all__`。**判据:③b 公共调用层,不承载 registry schema。** |

辅助证据:`test_studio_display_fields_are_stripped_from_gateway_runtime_snapshot`(用途:验证 Studio display fields 不进入 gateway runtime snapshot)见 `apps/studio/backend/tests/models/test_llm_config_boundary.py:15-59`;`test_credentials_v4_schema_redacts_secret_and_rejects_legacy_v3`(用途:验证 v4 credentials schema 与 secret redaction)见 `apps/studio/backend/tests/services/test_llm_v4_backend_contract.py:58-74`。

## 编号执行流程

1. `ProviderEndpoint`(用途:表示一个可调用 endpoint 及其 credential/protocol metadata)保存 `endpoint_id/protocol/base_url/credential_ref/api_key/status/test metadata/provider kind/rate limit bucket/timeout/trust_env/proxy_env/metadata`,并校验 endpoint id 是 slug,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-187`。

2. `ProviderRoute`(用途:表示某 endpoint 上的一条物理模型 route)保存 `route_id/endpoint_id/route_slug/provider_model_id/canonical_id/status/capabilities/verified_profiles/metadata`,并校验 `route_id == endpoint_id:route_slug`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-244`。

3. `RoleRouteEntry`(用途:表示 role/profile fallback 链里的一条 route 引用)保存 `route_id/runtime_settings_source/runtime_settings`,并用 `ROUTE_ID_RE` 校验 route id 形状,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:247-261`。

4. `RoleEntry`(用途:表示可执行 role 的 route-chain 配置)保存 `system_prompt_prefix/source_profile_id/source_profile_snapshot/fallback_chain/lint_requirements`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:264-273`。

5. `ModelProfile`(用途:表示 authoring 期可复用 route bundle)保存 `model_profile_id/canonical_id/tags/fallback_chain/lint_requirements`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:276-285`。

6. `RuntimePolicy`(用途:表示 gateway runtime health/probing 策略)保存 provider down TTL、probe timeout、token escalation rounds、terminal retry、secret lifetime policy,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:88-99`。

7. `RuntimeSettings`(用途:表示一条 route entry 上用户配置的 provider-neutral 调用设置)保存 temperature/top_p/max_output_tokens/stop/seed/tool choice/parallel tool calls/structured output/reasoning,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:121-135`。

8. `CapabilityValue`(用途:表示一个标准化 capability 值及来源)保存 value/source/observed_at/message,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:67-75`。

9. `VerifiedProfile`(用途:表示一条 route 已验证过的一种调用方法)保存 profile/capability/method/mapper/status/default/fallback rank/modalities/runtime overrides/metadata,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:189-204`。

10. `EndpointCandidate`(用途:表示 import draft 里的 endpoint 候选)继承 endpoint 字段并增加 display name 和 field sources,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:288-293`。

11. `RouteCandidate`(用途:表示 import draft 里的 route 候选)保存 endpoint、slug、provider model、canonical、display、capabilities、field sources、metadata,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:295-318`。

12. `ProbeResult`(用途:表示 import draft 上一次 endpoint/route probe 的结果)保存 target type、status、observed_at、capabilities、error,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:320-329`。

13. `EvidenceRecord`(用途:表示 provider docs、model list、probe、agent note 等证据记录)保存 evidence id/type/trust/scope/url/provider/route/model/method/probe/capability/attempt metadata,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:332-366`。

14. `ProviderImportDraft`(用途:表示不可信 Agent import draft 及其证据库)保存 draft metadata、endpoint candidates、route candidates、probe results、evidence records、agent notes、diff,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:369-385`。

15. `RegistrySnapshot`(用途:表示内存中 join 后的 runtime registry snapshot)保存 snapshot version、provider endpoints、provider routes、runtime policy、model profiles、roles,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:404-414`。旧 snapshot 未携带版本时 `snapshot_version=None`，保持兼容读取。

16. `ResolvedRoute`(用途:表示一条 runtime-ready route candidate)保存 role、route、endpoint、protocol、base_url、credential ref/fingerprint、timeout/proxy、provider model、canonical、profile、capabilities、runtime settings、effective runtime settings、snapshot version,并要求 credential_ref 非空,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:417-447`。

17. `SkippedRoute`(用途:表示 resolver 跳过 route 的诊断记录)保存 route_id、reason_code、message、from_override,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-463`;`ResolvedRole`(用途:表示解析后的 role 元数据和有序 routes)保存 role_name、system prompt、runtime policy、routes、lint results、skipped_diagnostics、source profile metadata,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:466-478`。

18. `registry.__init__`(用途:把 registry 公共 schema/contract 作为稳定 import surface 导出)从 contracts、credentials、schema re-export DTO,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py:5-39`;`__all__` 明确公开名,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/__init__.py:41-71`。

19. `CanonicalModel`(用途:表示 canonical 分组结果及置信度)保存 `canonical_id/confidence`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:13-20`。

20. `canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key)先应用 explicit aliases,再把 `anthropic/` 前缀视为 transport-normalized,否则把 provider model slug 成 orphan canonical,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:22-49`。

21. `_slug`(用途:把任意模型字符串收敛成小写 slug)会 trim/lower,把 `/` 变 `.`,把 `_` 变 `-`,并移除非 slug 字符,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:52-56`。

22. `LLMCredentialsFile`(用途:表示 Studio active credentials 文件 schema)固定 `schema_version=4`,保存 Studio 端 endpoint/route/runtime_policy,并用 gateway storage 计算 endpoint fingerprint,见 `apps/studio/backend/app/models/llm_config.py:121-133`。

23. `RolesData`(用途:表示 Studio active roles 文件 schema)允许 `schema_version=2/3`,保存 model profiles、model bundles、roles,见 `apps/studio/backend/app/models/llm_config.py:257-266`。

24. `RolesData.to_registry_snapshot`(用途:把 Studio credentials + roles join 成 gateway runtime snapshot)把 Studio DTO 的 display/authoring 字段剥掉,只把 gateway schema 字段放入 `RegistrySnapshot`,见 `apps/studio/backend/app/models/llm_config.py:279-296`。

25. `load_registry_snapshot`(用途:从显式 v4 credentials 文件和 v2/v3 roles 文件加载 runtime snapshot)读取 JSON/YAML,校验版本,把 v3 roles payload 修剪成 gateway fields,再构造 `RegistrySnapshot`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:186-202`。

26. `_assert_v4_credentials`(用途:校验 credentials 文件处于 v4 hard cutover 边界)要求 `schema_version == 4`,并拒绝 `providers/provider_credentials` 旧字段,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:227-237`。

27. `_assert_supported_roles`(用途:校验 roles 文件处于 v2/v3 route-chain schema)要求版本是 2 或 3,并拒绝旧 `models/providers/single_model_roles/peer_model_groups/circuit_breaker` 以及 role 内的 `active_model/models`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:240-261`。

28. `_gateway_roles_payload`(用途:把 Studio v3 roles 文件裁剪成 gateway runtime role payload)只保留 system prompt、source profile、fallback chain、lint requirements 等 gateway role keys,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:264-289`。

29. `models.py`(用途:GenericRouteChatModel 通用 LangChain route wrapper)已落地 `GenericRouteChatModel`,负责把 `ResolvedRoute` 交给 ordinary-chat dispatcher,并支持 tool binding、usage metadata 与 `__all__ = ["GenericRouteChatModel"]`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:24-301`。

## Baseline / Alignment 差异

当前 baseline 已有清晰的 gateway runtime schema 和 Studio wrapper schema:Gateway schema 禁止未知字段,例如 `ProviderRoute` 使用 `ConfigDict(extra="forbid")`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-219`;Studio wrapper 额外保留 display/authoring 字段,例如 `ProviderEndpoint.display_name`,见 `apps/studio/backend/app/models/llm_config.py:71-75`。**判据标注:gateway runtime schema 字段 = ③b 公共契约;Studio wrapper 的 display/authoring 字段(`display_name` 等)= ③a 应用加工,投影到 gateway snapshot 时由 `to_registry_snapshot` 剥离。两者是同一条 ③a→③b 剥离 seam 的两端,无反转。**

当前 baseline 已有 v4/v2 加载校验:`load_registry_snapshot`(用途:从显式 v4 credentials 文件和 v2/v3 roles 文件加载 runtime snapshot)会拒绝旧 credentials/roles 字段,见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:186-261`。

当前 baseline 的 canonical 分组非常保守:`canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key)只有 explicit alias、`anthropic/` transport prefix、orphan slug 三种结果,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:22-49`。

role resolution skipped diagnostics 已在 schema 中落地:`SkippedRoute`(用途:表示 resolver 跳过 route 的诊断记录)定义 `route_id/reason_code/message/from_override`,并由 `ResolvedRole.skipped_diagnostics` 保存,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-476`。普通 fallback 链的坏 route 与 blocking lint skip 由 resolver 写入该字段;override 错误仍 fail-fast,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:57-140` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:182-227`。

snapshot provenance 已在 registry schema / resolver 层落地:`ProviderRoute.snapshot_version` 标记 route 上 verified evidence 的来源版本,`RegistrySnapshot.snapshot_version` 表示当前物化版本,`resolve_role` 会把当前版本写入每条 `ResolvedRoute.snapshot_version`;当当前 snapshot 有版本且 route evidence 版本不同,resolver 会把旧 `verified_profiles/capabilities` 视为 stale,不再用于 live ready profile 选择、lint 或 effective runtime defaults。

## 决策原因

用 route-chain schema 替代旧 models/providers/active_model schema,是为了让 runtime identifier 变成精确 `route_id`,避免 provider/model 模糊匹配;`ProviderRoute`(用途:表示某 endpoint 上的一条物理模型 route)强制 `route_id == endpoint_id:route_slug`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:239-244`。

Studio DTO 继承 gateway DTO 但剥掉展示字段,是为了让前端可展示 `display_name`,同时不污染 gateway runtime snapshot;证据是 `_gateway_endpoint`(用途:把 Studio endpoint DTO 转成 gateway endpoint DTO)排除 `display_name`,见 `apps/studio/backend/app/models/llm_config.py:89-93`。**判据标注:`display_name` 等展示字段 = ③a 应用加工(① UI 展示);`_gateway_*` helper 的剥离动作 = ③a→③b 剥离 seam;剥离后的 gateway 字段 = ③b 公共契约。**

canonical 分组保持保守,是为了避免不同 provider 的相似模型名被误合并;`canonicalize_model`(用途:把 provider model id 映射成保守 canonical group key)默认返回 `confidence="orphan"`,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py:45-49`。

`models.py`(用途:GenericRouteChatModel 通用 LangChain route wrapper)不承担 registry schema,是为了把「编排数据契约」和「调用实现适配」分开;当前 `GenericRouteChatModel` 已作为调用层通用 wrapper 落地,具体 ChatX/provider 构造仍由 `RouteChatModelFactory` 等调用层模块承接,见 `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:24-301` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/route_chat_model_factory.py:19-82`。

## 代码索引(clues)

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:16-22`: slug/route id/protocol/status 基础枚举。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-244`: `ProviderEndpoint`(用途:表示一个可调用 endpoint 及其 credential/protocol metadata)与 `ProviderRoute`(用途:表示某 endpoint 上的一条物理模型 route)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:247-285`: `RoleRouteEntry`(用途:表示 role/profile fallback 链里的一条 route 引用)、`RoleEntry`(用途:表示可执行 role 的 route-chain 配置)、`ModelProfile`(用途:表示 authoring 期可复用 route bundle)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:403-478`: `RegistrySnapshot`(用途:表示内存中 join 后的 runtime registry snapshot)、`ResolvedRoute`(用途:表示一条 runtime-ready route candidate)、`SkippedRoute`(用途:表示 resolver 跳过 route 的诊断记录)、`ResolvedRole`(用途:表示解析后的 role 元数据和有序 routes,含 `skipped_diagnostics`)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:186-289`: `load_registry_snapshot`(用途:从显式 v4 credentials 文件和 v2/v3 roles 文件加载 runtime snapshot)及版本校验 helper。
- `apps/studio/backend/app/models/llm_config.py:279-296`: `RolesData.to_registry_snapshot`(用途:把 Studio credentials + roles join 成 gateway runtime snapshot)。
- `packages/graph-agent-gateway/src/graph_agent_gateway/models.py:24-301`: `GenericRouteChatModel` 通用 route wrapper。**③b 公共调用层,不承载 registry schema。**

## 待办/疑点

1. 已落地:role resolution skipped diagnostics 已有 schema 字段;`ResolvedRole.skipped_diagnostics` 的类型为 `list[SkippedRoute]`,用于保存 resolver 跳过 route 的原因,见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-476`。

2. 已落地:snapshot provenance 的 schema/resolver 契约已明确;`ProviderRoute.snapshot_version` 保存 route evidence 版本,`RegistrySnapshot.snapshot_version` 保存当前 snapshot 版本,`resolve_role` 构造 `ResolvedRoute` 时传播当前版本并在版本不一致时降级旧 verified evidence。具体由哪个 loader/host 填入版本戳仍由接入侧负责。

3. 疑点:canonical explicit aliases 参数目前只由函数签名支持,常见调用没有传 alias;例如 v3 migration 和 route candidate 构造都只传 endpoint/model,见 `apps/studio/backend/app/services/llm_credentials.py:337-339`、`apps/studio/backend/app/routers/llm.py:2526-2528`。
