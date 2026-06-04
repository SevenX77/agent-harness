---
module: 03-orch-credentials-endpoints
doc: baseline
status: drafted
---

# 03-orch-credentials-endpoints — Baseline(现状)

本文件只描述当前源码现状,不写理想实现。权威约束来自 `docs/graph-agent-gateway/mvp1/README.md` 的 03 模块 brief 与 `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md` 的 base_url / credential 决策。

## 覆盖代码(含覆盖率)

覆盖率:brief 要求的 7 个对象已覆盖 7/7,为 100%。

| 覆盖对象 | 判据归属 | 现状职责 |
|---|---|---|
| `registry/contracts.py` | **③b 公共** | `CredentialDescriptor` 是不含明文 secret 的凭证可用性描述;`CredentialProviderProtocol` 是宿主在 readiness 与执行期取 secret 的回调协议;`SecretLifetimePolicy` 是进程内 secret-bearing 对象的生命周期策略;`TerminalRetryPolicy` 是 runtime/probe/SDK retry 默认值集合(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/contracts.py:12`,`:33`,`:43`,`:107`)。 |
| `registry/credentials.py` | **③b 公共** | `EndpointCredentialProvider` 把 endpoint 与 `credential_ref` 映射到可描述/可获取的凭证;`FallbackCredentialProvider` 先问宿主 provider,再回退 endpoint-backed storage(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:14`,`:48`)。 |
| `registry/storage.py:compute_credential_fingerprint` | **③b 公共** | `compute_credential_fingerprint` 把 endpoint 身份、协议、base_url、secret、timeout/proxy 等哈希成不可逆 fingerprint,供 cache/变更检测使用(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13`)。 |
| `services/llm_credentials.py` | **③a 存储 + ③b 拆分/canonical(待下沉)** | `load_credentials` / `save_credentials` / `upsert_endpoints` / `upsert_routes` 是 Studio v4 credentials 文件的读写边界,负责 endpoint/route 持久化与 secret 保留(`apps/studio/backend/app/services/llm_credentials.py:39`,`:70`,`:107`,`:158`)。**判据:读写边界 + 存储介质 = ③a;但 base_url canonical 规则 + endpoint 拆分 + 生成 canonical endpoint_id(含现 `_stable_endpoint_id:369`)= ③b 公共,本轮反转,详见 `mvp1-alignment.md` §2.2/§5。** |
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

### 3. base_url 现状是原样透传,只做极轻量清理

> **判据标注**:base_url 按协议归一化(保存时 per-protocol canonical)= **③b 公共能力**(头号根因,F1 决策);当前原样透传是 baseline 风险。另外 baseline **缺一整块**「endpoint 标准化拆分 + 生成 canonical endpoint_id」的描述——这块现散在前端 + `_stable_endpoint_id`(`:369`),本轮反转后亦属 **③b 公共**(拆分/协议匹配/测试/生成 canonical id),前端只录入。两者目标设计见 `mvp1-alignment.md` §2.1/§2.2。

1. `resolve_role` 是 route 解析入口:它把 `endpoint.base_url` 直接写进 `ResolvedRoute.base_url`,没有按 protocol 改写路径(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:77-84`)。
2. `LLMClientManager._get_openai_client` 是 OpenAI-compatible SDK client 工厂:它把 `route.base_url` 原样传给 `OpenAI(base_url=...)`(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-172`)。
3. `LLMClientManager._get_anthropic_client` 是 Anthropic-compatible SDK client 工厂:它把 `route.base_url` 原样传给 `Anthropic(base_url=...)`(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:187-206`)。
4. `LLMClientManager._get_google_client` 是 google-genai SDK client 工厂:它把 `route.base_url` 原样放进 `http_options.base_url`(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:219-245`)。
5. `LLMClientManager._get_ark_client` 是 Volcengine Ark SDK client 工厂:它把 `route.base_url` 原样放进 Ark SDK 的 `base_url` 参数(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:257-285`)。
6. `compute_credential_fingerprint` 是凭证 fingerprint 计算函数:它调用 `_normalize_base_url` 后参与哈希,但 `_normalize_base_url` 目前只 `strip().rstrip("/")`,没有按 `anthropic_compatible` / `openai_compatible` / `ark_runtime` 等 protocol 做 canonical 规则(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13-42`)。
7. `test_endpoint` 是 endpoint 测试 API:它调用 `_endpoint_probe_base_url(endpoint)`,而 `_endpoint_probe_base_url` 也只是 `endpoint.base_url.rstrip("/")`,所以测试路径同样没有 protocol canonical 化(`apps/studio/backend/app/routers/llm.py:460-486`,`:4906-4907`)。

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

## Baseline / Alignment 差异

1. baseline 已经实现 `credential_ref` 运行时取 secret:resolved route 不带 `api_key`,真实调用前由 `CredentialProviderProtocol.get` 取 secret(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`;`apps/studio/backend/app/services/copilot.py:449-469`)。
2. baseline 仍把 secret 保存在 active credentials 文件中:它靠 `SecretStr` 响应脱敏和 `0600` 文件权限保护,还不是外部 vault 或纯 host-managed secret store(`apps/studio/backend/app/services/llm_credentials.py:102-104`,`:449-482`)。
3. baseline 没有保存时按 protocol 归一化 `base_url`:endpoint upsert 只是 validate payload 并保存,`compute_credential_fingerprint._normalize_base_url` 也只去空白和尾斜杠(`apps/studio/backend/app/services/llm_credentials.py:107-136`;`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:41-42`)。
4. alignment 应在保存 endpoint 时写入每个 protocol 的 canonical `base_url`,并保留调用时幂等双保险;当前源码只在 Copilot 特定 call_method 上做 deepseek/ark 的局部 runtime 改写(`apps/studio/backend/app/services/copilot.py:462-491`)。

## 决策原因

1. `credential_ref` 优先于明文下沉 route,原因是 route 是编排与调用的交接物,它会进入诊断、metadata、fallback event 等可观察路径;`ResolvedRoute` 只保留 ref 和 fingerprint,可以降低 secret 泄漏面(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`)。
2. endpoint 和 route 分层,原因是一个 endpoint 可以承载多个 model route;删除 endpoint 时同步删除其 routes,说明 endpoint 是连接/凭证边界,route 是模型能力边界(`apps/studio/backend/app/services/llm_credentials.py:139-155`)。
3. fingerprint 纳入 base_url/secret/timeout/proxy,原因是这些字段改变后 SDK client cache 或测试缓存都可能失效;当前 hash payload 明确包含这些字段(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:26-38`)。
4. 保存时归一化比调用时临时猜路径更稳定,原因是 endpoint 的 canonical `base_url` 一旦确定,probe、runtime、fingerprint、Copilot env 都能看到同一份事实;当前多处原样透传正是 baseline 风险(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:77-84`;`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:161-205`)。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/contracts.py:12-40`: credential readiness 与执行期 secret lookup 合约。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:14-45`: endpoint-backed `credential_ref` 映射与执行期取 secret。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13-42`: credential fingerprint 与当前轻量 base_url 清理。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:64-88`: `credential_ref`、`base_url`、`credential_fingerprint` 写入 `ResolvedRoute`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-285`: OpenAI/Anthropic/Google/Ark client 工厂原样使用 `route.base_url`。
- `apps/studio/backend/app/services/llm_credentials.py:107-136`: endpoint upsert 保留 secret 但未 canonicalize base_url。
- `apps/studio/backend/app/services/llm_credentials.py:431-482`: secret 占位符规则与 active credentials 落盘。
- `apps/studio/backend/app/services/llm_roles.py:88-133`: roles/profile/bundle route 引用校验。
- `apps/studio/backend/app/services/llm_paths.py:13-49`: Studio LLM 文件路径边界。

## 待办/疑点

1. 待办:实现 endpoint 保存时按 protocol canonicalize `base_url`;当前没有对应函数,`_normalize_base_url` 只做字符串清理(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:41-42`)。
2. 待办:调用层保留幂等 base_url 双保险;当前 SDK 工厂和 probe helper 都原样使用 route/endpoint base_url(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:161-205`;`apps/studio/backend/app/routers/llm.py:4906-4907`)。
3. 疑点:active credentials 文件仍写入明文 API key,这与 `credential_ref` 不落 route 明文并不冲突,但如果 MVP1 要升级到 host-managed secret store,需要明确迁移边界(`apps/studio/backend/app/services/llm_credentials.py:475-482`)。
4. 疑点:roles 文件写入没有 chmod `0600`;按当前职责 roles 不含 secret,但若未来把 credential metadata 扩展到 roles,需要重新确认权限边界(`apps/studio/backend/app/services/llm_roles.py:191-206`)。

5. ~~疑点(原 alignment 疑点#4):canonical 规则应写在 Gateway registry 还是 Studio service 层~~ → **已定 ③b 公共(本轮反转)**:base_url canonical 规则 + endpoint 拆分 + 生成 canonical endpoint_id(规则 `{slug}-{protocol}[-n]`)都属 endpoint/protocol runtime contract = ③b 公共能力;前端只录入,③a 只 upsert + 存储(存储介质)。证据 `ux-spec` §6.1 守边界(`:375`)、`module-disposition-revised.md:29`、`mvp1-alignment.md` §5/§8。
