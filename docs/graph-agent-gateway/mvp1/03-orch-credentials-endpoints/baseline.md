---
module: 03-orch-credentials-endpoints
doc: baseline
status: drafted
binds_design: ./mvp1-alignment.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/registry/contracts.py:CredentialProviderProtocol · packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:EndpointCredentialProvider/FallbackCredentialProvider · packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:compute_credential_fingerprint · apps/studio/backend/app/services/llm_credentials.py:upsert_endpoints/_stable_endpoint_id · apps/studio/backend/app/services/llm_roles.py:load_roles_file/save_roles_file/validate_references · apps/studio/backend/app/services/llm_paths.py:credentials_path/roles_path
units: [credentials-endpoints-canonicalization]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 03-orch-credentials-endpoints — Baseline(现状)

本文件只描述当前源码现状,不把目标实现写成现状。README 只限定本模块覆盖范围;目标决策与 PM 原话见同目录 `mvp1-alignment.md`。

## 覆盖代码(含覆盖率)

覆盖率:brief 要求的 7 个对象已覆盖 7/7,为 100%。

| 覆盖对象 | 判据归属 | 现状职责 |
|---|---|---|
| `registry/contracts.py` | **③b 公共** | `CredentialDescriptor` 是不含明文 secret 的凭证可用性描述;`CredentialProviderProtocol` 是宿主在 readiness 与执行期取 secret 的回调协议;`SecretLifetimePolicy` 是进程内 secret-bearing 对象的生命周期策略;`TerminalRetryPolicy` 是 runtime/probe/SDK retry 默认值集合(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/contracts.py:12`,`:33`,`:43`,`:107`)。 |
| `registry/credentials.py` | **③b 公共** | `EndpointCredentialProvider` 把 endpoint 与 `credential_ref` 映射到可描述/可获取的凭证;`FallbackCredentialProvider` 先问宿主 provider,再回退 endpoint-backed storage(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:14`,`:48`)。 |
| `registry/storage.py:compute_credential_fingerprint` | **③b 公共** | `compute_credential_fingerprint` 把 endpoint 身份、协议、base_url、secret、timeout/proxy 等哈希成不可逆 fingerprint,供 cache/变更检测使用(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13`)。 |
| `services/llm_credentials.py` | **③a 存储 + 迁移 helper** | `load_credentials` / `save_credentials` / `upsert_endpoints` / `upsert_routes` 是 Studio v4 credentials 文件的读写边界,负责 endpoint/route 持久化与 secret 保留(`apps/studio/backend/app/services/llm_credentials.py:39`,`:70`,`:107`,`:158`)；`_stable_endpoint_id` 只在 v3→v4 migration 中按 host/name 生成历史 endpoint id,不是统一 canonical endpoint_id 生成器(`apps/studio/backend/app/services/llm_credentials.py:299`,`:369`)。 |
| `services/llm_roles.py` | **③a 存储** | `load_roles_file` / `save_roles_file` / `validate_references` 是 Studio roles YAML 的读写边界,负责 schema v2/v3 与 route 引用校验(`apps/studio/backend/app/services/llm_roles.py:47`,`:58`,`:88`)。 |
| `services/llm_paths.py` | **③a 存储介质注入** | `credentials_path` / `roles_path` / `import_drafts_path` / `canonical_rules_path` 定义 Studio LLM 配置文件位置,支持环境变量覆盖(`apps/studio/backend/app/services/llm_paths.py:13`,`:21`,`:29`,`:37`)。**判据:存储介质(存哪个文件)= ③a 注入;gateway 只定 schema + 读写契约。** |
| endpoint/route schema clue | **③b 公共(权威源)** | `ProviderEndpoint` 保存 endpoint 的 protocol、base_url、credential_ref、api_key、status 等;`ProviderRoute` 保存单个物理模型 route 的 endpoint_id、provider_model_id、canonical_id、status 与 capabilities(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163`,`:207`)。 |

## 现状逻辑

### 1. endpoint 与 route 是分层存储

1. `ProviderEndpoint` 是一个可调用 endpoint 的配置记录:它包含 `endpoint_id`、`protocol`、`base_url`、`credential_ref`、`api_key`、状态、超时和代理字段(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-181`)。
2. `ProviderRoute` 是一个 endpoint 上的物理模型 route:它包含 `route_id`、`endpoint_id`、`route_slug`、`provider_model_id`、`canonical_id`、状态和能力(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-220`)。
3. `LLMCredentialsFile` 是 Studio active credentials 文件 schema:它把 `provider_endpoints`、`provider_routes` 与 `runtime_policy` 放在同一个 v4 文件内(`apps/studio/backend/app/models/llm_config.py:121-130`)。
4. `load_credentials` 是 v4 credentials 入口:文件不存在返回空 v4 registry,遇到 legacy provider schema 或非 v4 schema 会直接报错,避免 runtime 静默退回旧配置(`apps/studio/backend/app/services/llm_credentials.py:39-67`)。
5. `save_credentials` 是 credentials 写入入口:它调用 `_save_credentials_unlocked` 原子写文件,并把权限设为 `0600`(`apps/studio/backend/app/services/llm_credentials.py:70-79`,`:449-482`)。

### 2. credential_ref 已经是 route 运行时引用,不是明文 secret

1. `ResolvedRoute` 是 resolver 输出给运行时的单条 route:它包含 `credential_ref` 和 `credential_fingerprint`,但没有 `api_key` 字段(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`)。
2. `ResolvedRoute._has_credential_reference` 是 resolved route 的校验器:它要求 `credential_ref` 非空,否则 resolved route 不能成立(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:441-445`)。
3. `resolve_role` 是 registry 的纯解析函数:它用 endpoint 自带 `credential_ref` 或默认 `endpoint:<endpoint_id>` 生成 route 的 `credential_ref`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33-40`,`:64`)。
4. `EndpointCredentialProvider` 是 endpoint-backed 凭证 provider:初始化时同时登记 `endpoint:<endpoint_id>` 与 endpoint 自带 `credential_ref`,因此 route 可以只拿 ref,不拿 secret(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:14-22`)。
5. `EndpointCredentialProvider.describe` 是非明文 readiness 查询:它只返回 exists/status/fingerprint/scope,不返回 secret 值(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:24-36`)。
6. `EndpointCredentialProvider.get` 是执行期 secret 查询:只有真实调用前才取 `endpoint.api_key`,缺失或空值抛 `KeyError`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:38-45`)。
7. `CredentialProviderProtocol` 是宿主 callback 契约:它把 `describe(ref)` 的非 secret 状态查询与 `get(ref)` 的执行期取 secret 分成两个方法(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/contracts.py:33-40`)。
8. `apps/studio/backend/app/services/copilot.py:_resolve_route_runtime` 是一个实际消费例子:它先检查 `route.credential_ref`,再调用 `credential_provider.get(route.credential_ref)` 取 secret,并把 route.base_url 作为 runtime base_url 使用(`apps/studio/backend/app/services/copilot.py:449-469`)。

### 3. base_url 保存时按 protocol 写入 canonical

> **现状观察**:active credentials 的主要写入口已经在保存时调用 gateway 公共 `canonicalize_base_url(base_url, protocol)`。resolver、fingerprint、SDK client 和 endpoint test 继续读取同一个 `endpoint.base_url` 字段；差别是该字段在 upsert / v3 migration 后已经是 per-protocol canonical 形态。目标设计另见 `mvp1-alignment.md`。

1. `upsert_endpoints` 是 endpoint upsert 入口:它先把 payload 校验成 `ProviderEndpoint`,再用 `canonicalize_base_url(incoming.base_url, incoming.protocol)` 更新写入值,同时保留未提交 secret、curated `provider_kind`、`rate_limit_bucket` 等既有行为(`apps/studio/backend/app/services/llm_credentials.py:107-136`)。
2. `_v3_payload_to_v4` 是 v3→v4 migration 的转换入口:它在构造 `ProviderEndpoint` 前按 legacy provider 的 protocol canonicalize `base_url`,因此 migration 写出的 v4 endpoint 也走同一规则(`apps/studio/backend/app/services/llm_credentials.py:299-326`)。
3. `compute_credential_fingerprint` 是凭证 fingerprint 计算函数:它把 `endpoint.protocol` 传给 `_normalize_base_url`,后者调用 `canonicalize_base_url`,因此 hash payload 的 `base_url` 输入是 protocol-canonical 值(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13-42`)。
4. `resolve_role` 是 route 解析入口:它把保存后的 `endpoint.base_url` 直接写进 `ResolvedRoute.base_url`;保存侧已 canonical 的 endpoint 在 resolver 输出中保持同一路径(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:77-84`)。
5. `LLMClientManager` 的 OpenAI / Anthropic / Google / Ark client 工厂仍把 `route.base_url` 原样传给 SDK;当前契约依赖保存侧 canonical 与调用层幂等双保险,而不是在这些工厂里重新猜路径(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-285`)。
6. `test_endpoint` 的 probe helper 仍只对 endpoint base_url 做 `rstrip("/")`;在 upsert / migration 写入的 endpoint 上,它读到的已经是 canonical base_url(`apps/studio/backend/app/routers/llm.py:460-486`,`:4906-4907`)。

### 4. 写入边界保护 secret,但 active storage 仍保存 secret

1. `serialize_for_response` 是 API 响应序列化入口:它使用 pydantic `model_dump(mode="json")`,让 `SecretStr` 以脱敏形式返回(`apps/studio/backend/app/services/llm_credentials.py:102-104`;`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:171-172`)。
2. `upsert_endpoints` 是 endpoint upsert 入口:它保留未提交的现有 secret,避免 UI 回写脱敏占位符时覆盖真实 secret(`apps/studio/backend/app/services/llm_credentials.py:107-136`)。
3. `_preserved_secret` 是 secret 保留规则:空字符串表示清空,非占位符的新值表示替换,占位符 `**********` 表示沿用 current secret(`apps/studio/backend/app/services/llm_credentials.py:431-446`)。
4. `_credentials_payload_for_storage` 是落盘 payload 生成函数:它会把 `SecretStr` 的真实值写回 active credentials 文件,说明当前 storage 不是外部 secret vault,而是本地受权限保护的 secret 文件(`apps/studio/backend/app/services/llm_credentials.py:475-482`)。
5. `_save_credentials_unlocked` 是 credentials 原子写函数:它创建临时文件、fsync、chmod `0600`、再 replace,这是当前 storage 边界的主要安全措施(`apps/studio/backend/app/services/llm_credentials.py:449-472`)。

### 5. roles 只引用 route,不直接碰 endpoint secret

1. `load_roles_file` 是 roles YAML 读取入口:它拒绝旧 short-code schema,并把 route_id 形状做兼容归一化后校验成 `RolesData`(`apps/studio/backend/app/services/llm_roles.py:47-54`)。
2. `save_roles_file` 是 roles YAML 写入入口:它先调用 `validate_references`,再把 response-only materializer diagnostics 排除后原子写入(`apps/studio/backend/app/services/llm_roles.py:58-80`,`:177-188`)。
3. `validate_references` 是 route 引用校验函数:它检查 roles、profiles、bundles 的 fallback_chain/model_groups 是否引用已知 route_id,但不读取 endpoint secret(`apps/studio/backend/app/services/llm_roles.py:88-133`)。
4. `_atomic_write` 是 roles 文件写入 helper:它用临时文件和 `os.replace` 避免半写文件,但没有 credentials 文件那样的 `0600` 权限处理,因为 roles 不应保存 secret(`apps/studio/backend/app/services/llm_roles.py:191-206`)。

### 6. path 边界集中在 llm_paths

1. `credentials_path` 返回 active credentials 路径:优先 `STUDIO_LLM_CREDENTIALS_PATH`,否则落到 `APP_SETTINGS_DIR/llm/llm_credentials.json`(`apps/studio/backend/app/services/llm_paths.py:13-18`,`:45-49`)。
2. `roles_path` 返回 active roles 路径:优先 `STUDIO_LLM_ROLES_PATH`,否则落到 `APP_SETTINGS_DIR/llm/llm_roles.yaml`(`apps/studio/backend/app/services/llm_paths.py:21-26`,`:45-49`)。
3. `import_drafts_path` 返回 import draft/evidence store 路径:优先 `STUDIO_LLM_IMPORT_DRAFTS_PATH`,否则落到 `APP_SETTINGS_DIR/llm/llm_import_drafts.json`(`apps/studio/backend/app/services/llm_paths.py:29-34`,`:45-49`)。
4. `canonical_rules_path` 返回 canonical rules 路径:优先 `STUDIO_LLM_CANONICAL_RULES_PATH`,否则落到 `APP_SETTINGS_DIR/llm/llm_canonical_rules.yaml`(`apps/studio/backend/app/services/llm_paths.py:37-42`,`:45-49`)。

### 7. v3 migration 有 host 映射 endpoint id,但没有统一 canonical endpoint_id 生成器

1. `migrate_v3_credentials_to_v4` 是显式迁移入口:它只接受 schema_version 3,先创建 `.v3.bak` 备份,再调用 `_v3_payload_to_v4` 生成 v4 registry 并通过 `save_credentials` 落盘(`apps/studio/backend/app/services/llm_credentials.py:82-99`)。
2. `_v3_payload_to_v4` 遍历 legacy `providers`,对每个 provider 调 `_stable_endpoint_id` 生成 endpoint_id,并在构造 `ProviderEndpoint` 前按 protocol canonicalize legacy `base_url`(`apps/studio/backend/app/services/llm_credentials.py:299-326`)。
3. `_stable_endpoint_id` 是 migration 专用 host/name 映射 helper:它对 api.anthropic.com、api.openai.com、api.deepseek.com、Google、Volcengine、OpenRouter、WaveSpeed、七牛等 host 返回固定 id,其它情况返回旧 provider id/code(`apps/studio/backend/app/services/llm_credentials.py:369-393`)。
4. 现有源码没有一个通用的 `{slug}-{protocol}[-n]` canonical endpoint_id 生成器;`_stable_endpoint_id` 也不在 `upsert_endpoints` 新保存路径中调用,所以它只能证明 migration 里有历史 id 稳定化,不能证明保存侧已有 canonical endpoint_id 规则(`apps/studio/backend/app/services/llm_credentials.py:107-136`,`:299-326`,`:369-393`)。

## Baseline / Alignment 差异

1. baseline 已经实现 `credential_ref` 运行时取 secret:resolved route 不带 `api_key`,真实调用前由 `CredentialProviderProtocol.get` 取 secret(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`;`apps/studio/backend/app/services/copilot.py:449-469`)。
2. baseline 仍把 secret 保存在 active credentials 文件中:它靠 `SecretStr` 响应脱敏和 `0600` 文件权限保护,还不是外部 vault 或纯 host-managed secret store(`apps/studio/backend/app/services/llm_credentials.py:102-104`,`:449-482`)。
3. baseline 已实现 upsert / v3 migration 保存时按 protocol 归一化 `base_url`,并让 `compute_credential_fingerprint` 使用 canonical base_url 输入(`apps/studio/backend/app/services/llm_credentials.py:107-136`,`:299-326`;`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13-42`)。
4. 差异:import draft apply 仍是 secondary write entrance,当前不在 WS-2 owns_files 内,还会把 draft endpoint 的 raw `base_url` 写进 active credentials;已登记 deferred 后续接入同一 helper(`apps/studio/backend/app/services/llm_import_drafts.py:136-202`;`docs/deferred-items.md`)。

## 决策原因

1. `credential_ref` 优先于明文下沉 route,原因是 route 是编排与调用的交接物,它会进入诊断、metadata、fallback event 等可观察路径;`ResolvedRoute` 只保留 ref 和 fingerprint,可以降低 secret 泄漏面(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`)。
2. endpoint 和 route 分层,原因是一个 endpoint 可以承载多个 model route;删除 endpoint 时同步删除其 routes,说明 endpoint 是连接/凭证边界,route 是模型能力边界(`apps/studio/backend/app/services/llm_credentials.py:139-155`)。
3. fingerprint 纳入 base_url/secret/timeout/proxy,原因是这些字段改变后 SDK client cache 或测试缓存都可能失效;当前 hash payload 明确包含这些字段(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:26-38`)。
4. 保存时归一化比调用时临时猜路径更稳定,原因是 endpoint 的 canonical `base_url` 一旦确定,probe、runtime、fingerprint、Copilot env 都能看到同一份事实;此前多处原样透传正是这次收敛的风险来源(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:77-84`;`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:161-205`)。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/contracts.py:12-40`: credential readiness 与执行期 secret lookup 合约。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:14-45`: endpoint-backed `credential_ref` 映射与执行期取 secret。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13-42`: credential fingerprint 与 protocol-canonical base_url 输入。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:64-88`: `credential_ref`、`base_url`、`credential_fingerprint` 写入 `ResolvedRoute`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-285`: OpenAI/Anthropic/Google/Ark client 工厂原样使用 `route.base_url`。
- `apps/studio/backend/app/services/llm_credentials.py:107-136`: endpoint upsert 保存时 canonicalize base_url,并保留 secret/provider_kind/rate_limit_bucket 规则。
- `apps/studio/backend/app/services/llm_credentials.py:299-393`: v3→v4 migration 保存时 canonicalize base_url;`_stable_endpoint_id` 仍只是 host/name 映射,不是通用 canonical endpoint_id 生成器。
- `apps/studio/backend/app/services/llm_credentials.py:431-482`: secret 占位符规则与 active credentials 落盘。
- `apps/studio/backend/app/services/llm_roles.py:88-133`: roles/profile/bundle route 引用校验。
- `apps/studio/backend/app/services/llm_paths.py:13-49`: Studio LLM 文件路径边界。

## 待办/疑点

1. 待办:import draft apply 写 endpoint 时仍需接入同一个 base_url canonical helper;当前已作为 deferred 追踪(`apps/studio/backend/app/services/llm_import_drafts.py:136-202`;`docs/deferred-items.md`)。
2. 待办:调用层继续保留幂等 base_url 双保险;SDK 工厂和 probe helper主要消费已保存的 canonical route/endpoint base_url(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:161-205`;`apps/studio/backend/app/routers/llm.py:4906-4907`)。
3. 疑点:active credentials 文件仍写入明文 API key,这与 `credential_ref` 不落 route 明文并不冲突,但如果 MVP1 要升级到 host-managed secret store,需要明确迁移边界(`apps/studio/backend/app/services/llm_credentials.py:475-482`)。
4. 疑点:roles 文件写入没有 chmod `0600`;按当前职责 roles 不含 secret,但若未来把 credential metadata 扩展到 roles,需要重新确认权限边界(`apps/studio/backend/app/services/llm_roles.py:191-206`)。

5. 待办:如果后续要把 endpoint_id 生成变成通用能力,不能复用 `_stable_endpoint_id` 当作已完成实现;当前它只服务 v3 migration 的 host/name 映射(`apps/studio/backend/app/services/llm_credentials.py:299-326`,`:369-393`)。
