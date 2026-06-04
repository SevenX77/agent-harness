---
module: 03-orch-credentials-endpoints
doc: mvp1-alignment
status: drafted
---

# 03-orch-credentials-endpoints — MVP1 Alignment(目标设计)

> **Tier**：③b gateway 公共能力(凭证/端点 schema + 读写规范 + base_url 按协议归一化 + 凭证指纹 + **endpoint 标准化拆分 + 生成 canonical endpoint_id**；存储介质由 ③a 注入)
> **Owns**：定义 `ProviderEndpoint`/`ProviderRoute`/`credential_ref` 的数据结构与读写契约；把「同一端点的等价 URL 收敛成 canonical」、「原始混合凭证 → 标准 endpoint list + canonical id」做成任何 app 可复用的公共能力；**不绑死存储位置**
> **Status**：设计定稿(2026-06 判据第四轮反转 + F1 base_url 决策)；代码 = endpoint 拆分 + canonical id 生成待集中下沉 ③b(现散 ③a 前端 + `_stable_endpoint_id`)、base_url 保存时归一化待补、`_normalize_base_url` 待升级为 per-protocol
> **Related**：[[01-handoff-interface]](`ResolvedRoute` 携带 credential_ref/base_url)· [[04-orch-registry-schema]](`ProviderEndpoint/ProviderRoute` schema 权威源)· [[10-inv-route-chat-model-factory]](调用时 base_url 幂等双保险)· [[07-orch-fallback-circuit-probe]](probe 打到 canonical base_url；F1 双向)· studio copilot（copilot SDK 调用 = ③a，见 `docs/studio/mvp1/02_capabilities/copilot-assist/` + `00_settings-ux-spec.md` §3.8）
> **决策日志**：本模块 base_url / 凭证决策依据 client 层 A' 重设计 F1(base_url 归一化——每 protocol 确定规则、保存时归一化)+ D3(gateway 可复用服务、API 一等公民)——完整逻辑 + PM 原话留底于本文 §4/§5；归属判据见 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`(03 凭证端点 schema/读写/base_url 归一化 = ③b；**endpoint 标准化拆分反转为 ③b**)。D3 是跨模块共享决策,另见 [[01-handoff-interface]] §4、[[04-orch-registry-schema]] §4(均同引 D3 划分 ③b 公共边界)。
> **现状**：见同目录 `baseline.md`

本文件描述 MVP1 对齐目标:密钥通过 `credential_ref` 执行期获取,endpoint 保存时按 protocol 写入 canonical `base_url`,**原始混合凭证由 gateway 拆成标准 endpoint list 并生成 canonical `endpoint_id`**,fingerprint 反映 endpoint/credential 变更,Studio storage 只承担文件边界。

## 1. 定义

MVP1 目标：把「凭证 / 端点」的**数据结构 · 读写契约 · 归一化 · 拆分 · 指纹**全部固定为 gateway 公共能力，任何调模型的 app 装上 gateway 都能用，因此除「存储介质(存哪个文件)」外整块归 **③b 公共**。

按判据「换个 app 还原样能用吗?能=③b」拆开本模块的能力：
- **③b 公共**：`credential_ref` 取密钥契约、endpoint/route schema、`base_url` 按协议归一化、凭证指纹、**endpoint 标准化拆分 + 协议匹配 + 测试 + 生成 canonical endpoint_id**。这些是 gateway 机制衍生的最佳方案，不绑死 UI/产品策略/调用方式/存储。
- **① 前端**：用户怎么录入(provider 卡、多 URL 行)。
- **③a 应用加工**：endpoint upsert + 实际**存储介质**(存哪个文件)、批量探测的 job/进度/HTTP 包装、draft import-apply 工作流。

不调模型(调用归 [[09-inv-invocation-runtime]])。本文只写文档目标，不改代码。

## 2. 数据流 / 机制(目标；现状逐步见 `baseline.md`)

**上下游**：① 前端录入原始混合凭证(多 key / 多 URL / 多协议混在一起，③a/① UI)→ **③b 拆分 + 协议匹配 + 测试 + 生成 canonical endpoint_id** → 标准 endpoint list → ③a `upsert_endpoints` + **存储介质(文件)** → `resolve_role`(③b)读 endpoint 生成 `ResolvedRoute`(只带 `credential_ref` + canonical base_url + fingerprint，不带明文)→ 调用层执行期 `CredentialProviderProtocol.get(credential_ref)` 取 secret。

### 1. 保存 endpoint 时归一化 base_url

1. 输入:Studio 后端收到 endpoint payload,由 `upsert_endpoints`(用途:把 endpoint payload 写入 v4 credentials 文件,保留未提交 secret)变成 `ProviderEndpoint`(`apps/studio/backend/app/services/llm_credentials.py:107-123`)。
2. 判定:读取 `ProviderEndpoint.protocol`,因为 protocol 决定 SDK 拼接路径的规则;当前 schema 已把 protocol 与 base_url 放在同一 endpoint 对象内(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-181`)。
3. 归一化:按 protocol 写入 canonical `base_url`。F1 决策(每 protocol 规则固定,详见本文 §5 决策 2)要求 anthropic-compatible 去尾 `/v1`(SDK 自加 `/v1/messages`)、openai-compatible 保持 provider 接受的 `/v1` 形状、deepseek-anthropic 去 `/v1` 后补 `/anthropic`、ark openai-compat 使用 `.../api/v3`;当前只有 Copilot runtime 对 deepseek/ark 有局部 helper,说明保存时规则尚未集中(`apps/studio/backend/app/services/copilot.py:476-491`)。
4. 持久化:canonical endpoint 进入 `LLMCredentialsFile.provider_endpoints`,再由 `_save_credentials_unlocked`(用途:credentials 原子写函数,临时文件→fsync→chmod 0600→replace)原子写入 active credentials 文件(`apps/studio/backend/app/services/llm_credentials.py:133-135`,`:449-482`)。
5. 输出:后续 resolver、probe、client factory、fingerprint 都读取同一个 canonical `endpoint.base_url`,而不是各自猜测(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:77-84`;`apps/studio/backend/app/routers/llm.py:4906-4907`)。

### 2. 原始混合凭证 → 标准 endpoint list + canonical endpoint_id(③b 公共，整块缺漏补设计)

> **本节是新增设计：当前文档完全没写「endpoint 标准化拆分 + 生成 canonical endpoint_id」这块 ③b 公共能力。** baseline 现状是这块散在前端(前端拆 / 前端给 id)+ v3→v4 migration 的 `_stable_endpoint_id`(`llm_credentials.py:369`)；MVP1 目标是把它**下沉为 ③b 公共能力**(本轮反转，详见 §5 决策 1)。

1. 输入:① 前端把用户在一个 provider 卡里录入的**原始信息**(可能含多 key / 多 URL / 多协议混在一起)交给 gateway,前端**只负责怎么收集原始输入**,不自己拆、不自己生成 id(`ux-spec` §6.1 A4)。
2. 协议匹配(③b):gateway 用内置协议 SDK 对每个 URL 打各协议推理端点 + 对应 auth header(native anthropic=`x-api-key`、anthropic 兼容第三方=`Authorization: Bearer`),自动判定该 URL 是哪个 protocol(`ux-spec` §6.1 A3)。
3. 测试连通(③b):对拆出的每条候选 endpoint 做连通性验证(official 走 list-models、third-party 走选一个模型 probe),确认可用。
4. 拆分(③b):把「多 URL × 协议」拆成多条**标准 endpoint**——一个 endpoint = 一套 base_url + protocol + credential(`ux-spec` §6.1 A4)。
5. 生成 canonical endpoint_id(③b):为每条拆出的 endpoint 生成确定的 canonical id。**规则 = `{slug}-{protocol}[-n]`**(`slug` 来自 provider/host 收敛，`protocol` 区分同 host 多协议，`-n` 处理重名)。**当前 `_stable_endpoint_id`(用途:v3→v4 migration 里按 host 硬编码 endpoint id)按 host 硬编码(如 `anthropic-official`)、且只在 migration 路径,不是统一 canonical 规则,本轮反转后应退役/并入 ③b 统一 canonical id 生成**(`apps/studio/backend/app/services/llm_credentials.py:369`)。
6. 输出(③b → ③a):gateway 返回**标准 endpoint list(每条带 canonical endpoint_id)**;③a 只负责 `upsert_endpoints` + 把它存进文件(存储介质),前端只负责渲染(`ux-spec` §6.1 A4:③a「upsert + 存储」、③b「拆分 + 协议匹配 + 测试 + 生成 canonical endpoint_id」)。

### 3. 解析 route 时只输出 credential_ref

1. 输入:`resolve_role`(用途:registry 纯解析函数,把 role 展开成有序 `ResolvedRoute` 链)收到 `RegistrySnapshot`、role_name、可选 route_override 和 credential provider(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33-40`)。
2. join:它用 `entry.route_id` 找 route,再用 `route.endpoint_id` 找 endpoint(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:55-63`)。
3. ref:它优先使用 `endpoint.credential_ref`,否则生成 `endpoint:<endpoint_id>` 作为默认 ref(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:64`)。
4. readiness:它通过 `_describe_credential`(用途:容错查询 ref 是否存在,provider 不存在或报错返回 None)查询 ref 是否存在(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:65-71`,`:135-144`)。
5. output:它创建 `ResolvedRoute`,写入 `credential_ref`、`credential_fingerprint`、protocol、canonical base_url、timeout/proxy、provider_model_id 与 canonical_id,但不写 `api_key`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:77-113`)。

### 4. 执行期取 secret,诊断期只看 descriptor

1. readiness 路径调用 `CredentialProviderProtocol.describe`(用途:非 secret readiness 查询,只返 exists/status/fingerprint/scope);这个方法只返回 `CredentialDescriptor`,用于 UI/配置可用性判断(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/contracts.py:12-40`)。
2. invocation 路径调用 `CredentialProviderProtocol.get`(用途:执行期取 secret);Copilot 的 `_resolve_route_runtime`(用途:copilot 把一条 route 转成 SDK runtime env,取 secret + base_url)已按这个契约从 `route.credential_ref` 取 secret(`apps/studio/backend/app/services/copilot.py:449-469`)。
3. fallback 路径允许 host provider 优先:如果宿主 provider 能描述/返回 secret,`FallbackCredentialProvider`(用途:先问宿主 provider 再回退 endpoint-backed storage)直接使用宿主结果;否则回到 endpoint-backed provider(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:48-72`)。
4. 诊断输出使用 fingerprint/scope/status,不输出 secret:`EndpointCredentialProvider.describe`(用途:endpoint-backed readiness 查询)返回 `fingerprint` 与 `scope`,但不返回 `api_key`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:24-36`)。

### 5. fingerprint 与 cache 失效

1. `compute_credential_fingerprint`(用途:把 endpoint 身份/协议/base_url/secret/timeout/proxy 哈希成不可逆缓存键)把 endpoint_id、protocol、base_url、secret、timeout、trust_env、proxy_env、credential_ref 放入 hash payload(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:26-38`)。
2. MVP1 保存 canonical base_url 后,fingerprint 应该以 canonical base_url 为输入;这样同一个 SDK 语义的 endpoint 不会因为 `/v1/`、尾斜杠等 UI 输入差异反复失效(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:29`,`:41-42`)。
3. `LLMCredentialsFile.endpoint_fingerprint`(用途:Studio 端检查 endpoint 是否被并发修改的入口)是 Studio 端检查 endpoint 是否被并发修改的入口;endpoint test 用它丢弃过期测试结果(`apps/studio/backend/app/models/llm_config.py:131-133`;`apps/studio/backend/app/routers/llm.py:467-527`)。

### 6. storage 边界

1. credentials storage 只负责 active endpoint/route/runtime_policy 文件;`load_credentials`(用途:v4 credentials 读取入口,拒绝 legacy/非 v4 schema)拒绝旧 schema,保证 runtime 不回退旧 provider/env 行为(`apps/studio/backend/app/services/llm_credentials.py:39-67`)。
2. roles storage 只负责 roles/profile/bundle authoring 文件;`validate_references`(用途:校验 roles/profile/bundle 只引用已知 route_id)确保 route_id 引用存在,但不做动态选型或 secret 读取(`apps/studio/backend/app/services/llm_roles.py:88-133`)。
3. path storage 只负责文件位置;`_env_or_default`(用途:集中处理 env override 与默认 app settings dir)集中处理 env override 与默认 app settings dir(`apps/studio/backend/app/services/llm_paths.py:45-49`)。

## 3. 接口契约

> `ProviderEndpoint`/`ProviderRoute`/`ResolvedRoute` 字段权威源在 [[04-orch-registry-schema]](`registry/schema.py`)，本表**只链接不复制字段清单**，防 drift。

| 边界 | 契约 |
|---|---|
| **① → ③b(endpoint 拆分入参)** | 原始混合凭证(多 key / 多 URL / 多协议)。③b **看得到**「URL + key + 原始录入信息」(通用)，**看不到**「provider 卡 UI / 多 URL 行交互怎么长」(① UI)。 |
| **③b → ③a(endpoint 拆分出参)** | 标准 endpoint list：`ProviderEndpoint[]`，每条带 **canonical `endpoint_id`(规则 `{slug}-{protocol}[-n]`)** + 探测出的 protocol + 连通结果。③a 只 `upsert_endpoints` + 存文件。 |
| **③a → ③b(凭证读写契约)** | `CredentialProviderProtocol`{ `describe(ref) → CredentialDescriptor`(非 secret，readiness), `get(ref) → secret`(执行期) }。权威源 `registry/contracts.py:33-40`。secret **永不**进 `ResolvedRoute`。 |
| **resolve_role 输出(凭证部分)** | `ResolvedRoute`{ `credential_ref`(非空，`_has_credential_reference` 校验，`schema.py:441`), `credential_fingerprint`(非明文), `base_url`(canonical), protocol, timeout/proxy }。**无 `api_key` 字段**。字段权威源 `schema.py:415-439`。 |
| **base_url 归一化(③b 公共，两道)** | 主 = 保存时 per-protocol canonical(`upsert_endpoints` 入口)；副 = 调用时幂等 no-op 双保险([[10-inv-route-chat-model-factory]] / copilot `_resolve_route_runtime`)。canonical 规则随 protocol 固定(F1)。 |
| **存储介质(③a 注入)** | gateway 定 schema + 读写契约，**存哪个文件由 ③a 注入**：`credentials_path`/`roles_path`/`import_drafts_path`/`canonical_rules_path`(`llm_paths.py:13-42`，支持 env override)。 |
| **错误** | credential_ref 缺失 → resolved route 不成立(`schema.py:441`)；执行期 secret 缺失/空 → `KeyError`(`credentials.py:38-45`)。 |
| **归属 / 稳定性** | endpoint/route/resolved schema 权威源 = [[04-orch-registry-schema]]；本模块只链接。canonical endpoint_id 规则稳定性由 ③b 维护(本轮已定 ③b)。 |

## 4. 设计决策基础(用户原话)

> **判据(本模块「endpoint 拆分 + canonical id 归 ③b」依据)**："换个 app 还原样能用吗?能=③b,不能=③a。"(ux-spec §6.0、`module-disposition-revised.md:15`) → 「把原始混合凭证用内置协议 SDK 自动拆成标准 endpoint + 测试 + 生成 canonical id」是任何调模型 app 的通用需求(不绑死 UI/产品策略/调用方式/存储)→ **③b 公共**。前端只负责「怎么收集原始输入」(① UI)，存哪个文件是 ③a(存储介质)。

> **§0 #1a official**(ux-spec `:11`)："akikey页面: a. official, 用户填入api key , 直接点test , get 所有的model list, 不需要probe, 因为比较可控, 只要API key 能连通(/model 获取模型列表)" —— protocol/连通由系统判，用户只填 key。

> **§0 #1b third-party 协议系统自动测**(ux-spec `:13`)："第三方唯一的区别是, 用户得填入URL, (protocol以前要自己选, 现在系统自动测); 用户必须在模型列表里面选一个模型进行一次模型测试, 才能验证这个endpoint可用" —— **protocol「现在系统自动测」**= ③b 协议探测，直接支撑「拆分 + 协议匹配」归 ③b。

> **F1 base_url 归一化(保存时 + per-protocol 固定规则)**(client 层 A' 重设计决策 F1)："base_url 归一化的关键是每个protocol都有确定的统一的规则 ... 如果结果足够确定, 我觉得放在credential保存时归一化是最好的, 每个endpoint都有固定格式, 存这个固定格式保证不会出错" —— 保存时 canonical(主)+ per-protocol 固定规则。

> **F1 调用时幂等双保险**(client 层 A' 重设计决策 F1)："副 = 调用时幂等归一化做双保险(已 canonical 则 no-op)" —— 调用层 no-op 保护历史数据;调用层落点见 [[10-inv-route-chat-model-factory]]。

> **D3 gateway = 可复用服务 / 存储介质归应用**(client 层 A' 重设计决策 D3)："前端不归gateway管 ... gateway只管提供服务 ... 要考虑复用其他app" + README §2「存储介质(应用做)：把 gateway 定义的数据存到哪个文件 / 路径(只是『插座插哪』)」。D3 是跨模块共享决策,另见 [[01-handoff-interface]] §4、[[04-orch-registry-schema]] §4。

## 5. 决策 + 动机

1. **endpoint 标准化拆分 + 生成 canonical endpoint_id = ③b 公共(本轮反转，补整块缺漏)**：原 review/旧表述把「前端拆分 / 前端生成 id / `_stable_endpoint_id` 退役」当结论；按判据「用内置协议 SDK 自动拆 + 测 + 生成 canonical id」是任何 app 可复用的 gateway 机制，**反转为 ③b 公共**——拆分 / 协议匹配 / 测试 / 生成 canonical id(规则 `{slug}-{protocol}[-n]`)归 ③b，前端只录入，③a 只 upsert + 存储。**被否的旧表述**：「前端自己拆 endpoint / 前端生成 endpoint_id / `_stable_endpoint_id` 直接退役不替代」。证据：`ux-spec` §6.1 守边界检查(`:375`)「⚠️ 原『前端拆分 / 前端生成 id / `_stable_endpoint_id` 退役』已反转——endpoint 标准化拆分 + canonical id 归 ③b」。
2. **base_url 保存时归一化(主)+ 调用时幂等(副)**：F1 决策——每 protocol 规则确定统一,存 canonical 最稳;调用时 no-op 双保险保护历史数据。per-protocol 规则:anthropic 去尾 `/v1`(SDK 自加 `/v1/messages`)、openai 保持 provider 接受形状、deepseek-anthropic 去 `/v1` 后补 `/anthropic`、ark openai-compat 用 `.../api/v3`。被否:「运行时乱归一化」(之前觉得乱是因为多次实验用错格式,规则其实每 protocol 确定)。deerflow/deepagents **不做**这步(它们假设 base_url 已对)→ 没东西可抄,自建。(client 层 A' 重设计决策 F1;PM 原话见 §4。)
3. **保存时归一化比调用时临时归一化更可靠**：resolver、probe、fingerprint、client factory 和 Copilot env 都读同一份 canonical endpoint,减少"测试与运行不是同一路径"的风险(`apps/studio/backend/app/routers/llm.py:460-486`;`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-285`)。
4. **`credential_ref` 优先于明文下沉 route**：route 会进入 role materialization、fallback event、response metadata 等诊断面,不能把 secret 当普通字段传递;`ResolvedRoute` 只保留 ref 和 fingerprint,降低 secret 泄漏面(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`)。
5. **endpoint 与 route 分层是必要边界**：endpoint 代表连接/凭证/protocol,route 代表模型/capability/canonical_id;删除 endpoint 时同步删 route,说明这两个层级不能混成一个 provider 字符串(`apps/studio/backend/app/services/llm_credentials.py:139-155`)。
6. **fingerprint 纳入 base_url/secret/timeout/proxy**：这些字段改变后 SDK client cache 或测试缓存都可能失效;当前 hash payload 明确包含这些字段;MVP1 后 fingerprint 输入应为 canonical base_url，否则等价 endpoint 产生不同 hash(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:26-38`)。
7. **存储介质归 ③a 注入**：gateway 定 schema + 读写规范，存哪个文件是应用的事(README §2 存储介质)；`llm_paths.py` 的 env override 正是这条边界。

## 6. 测试关键点

- **per-protocol base_url canonical**：保存 anthropic endpoint(base_url 带 `/v1`)→ 存成去尾 `/v1`；deepseek-anthropic 带 `/v1` → 存成去 `/v1` 补 `/anthropic`；ark → `.../api/v3`；openai → 保持 provider 接受形状(防回归成「只 strip 尾斜杠」)。
- **保存=调用同一路径**：保存后 resolver / probe / client factory / fingerprint / copilot env 读到的 base_url **完全一致**(防「测试通了运行又错」)。
- **fingerprint 对等价 URL 稳定**：同一 endpoint 录入 `https://x/v1` 与 `https://x/v1/`(尾斜杠) → canonical 后 fingerprint **相同**(不反复失效)。
- **endpoint 拆分 + canonical id**：一个 provider 卡录入多 URL × 协议 → ③b 拆成多条 endpoint，每条 canonical id 符合 `{slug}-{protocol}[-n]`；同 host 多协议不撞 id(`-protocol` 区分)；重名走 `-n`。
- **协议自动探测**：third-party URL 不让用户选 protocol → ③b 打各协议推理端点 + auth header 自动判定(`x-api-key` vs `Bearer`)。
- **secret 不进 route**：`ResolvedRoute` **无** `api_key` 字段；credential_ref 非空才成立；执行期 `get(ref)` 才取 secret，诊断只看 `describe`。
- **前端不拆/不生成 id**：前端只交原始输入，拆分 + canonical id 由 ③b 做(回归反转点：不再前端拆、不再前端生成 id)。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：endpoint/route schema(`registry/schema.py`)、`credential_ref` 契约(`registry/contracts.py`/`credentials.py`)、`compute_credential_fingerprint` + base_url 归一化(`registry/storage.py`)、endpoint 拆分 + canonical id 生成(待下沉)、`resolve_role` 写 `ResolvedRoute`。
- **③a** `apps/studio/backend`：`upsert_endpoints` + **存储介质**(`llm_credentials.py`)、`llm_paths.py` 路径注入、批量探测 job/HTTP 包装、draft import-apply 工作流、`_stable_endpoint_id`(现 migration 用，待并入 ③b canonical id)。
- **① 前端**：provider 卡录入、多 URL 行(只收集原始输入，不拆 / 不生成 id)。
- **② Rust**：N/A(凭证/endpoint 数据永不 Rust)。

## 8. gaps / 待设计

1. **代码下沉**(后续工程，非本轮)：endpoint 标准化拆分 + 协议匹配 + 测试 + 生成 canonical endpoint_id → gateway 包；前端拆分逻辑 + `_stable_endpoint_id` 退役并入 ③b canonical id 生成；base_url per-protocol canonical 集中到 gateway。
2. 待办:新增或迁移一个 protocol-aware canonicalizer,并让 `upsert_endpoints` / v3→v4 migration / import draft apply 都走同一规则(`apps/studio/backend/app/services/llm_credentials.py:107-136`,`:299-356`;`apps/studio/backend/app/services/llm_import_drafts.py:136-202`)。
3. 待办:更新 `compute_credential_fingerprint` 的 base_url 输入语义,确保 canonical base_url 与 fingerprint/cache 失效一致(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:26-38`)。
4. 待办:调用层保留幂等 normalize,尤其是 `LLMClientManager._get_anthropic_client`(用途:Anthropic-compatible SDK client 工厂,原样透传 base_url) 和 Copilot `_resolve_route_runtime` 两条路径(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:187-206`;`apps/studio/backend/app/services/copilot.py:449-491`)。
5. ~~疑点:anthropic/openai/deepseek/ark 的 canonical 规则应写在 Gateway registry 还是 Studio service 层~~ → **已定 ③b 公共(本轮反转，原疑点#4 作废)**：base_url canonical 规则 + endpoint canonical id 规则都属 endpoint/protocol runtime contract = ③b 公共能力，不宜散在 router helper；存储介质留 ③a 注入(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-181`)。

## 已实现 / 与 baseline 差异

1. 已实现:`ResolvedRoute` 强制有 `credential_ref`,并且不保存 `api_key`;这是 MVP1 的正确交接方向(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`)。
2. 已实现:`EndpointCredentialProvider`(用途:endpoint-backed 凭证 provider) 和 `FallbackCredentialProvider` 已经能支持 endpoint-backed 与 host-backed 两类取密钥方式(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:14-72`)。
3. 已实现:Studio credentials 文件写入是原子的,并把 active credentials 文件权限设为 `0600`(`apps/studio/backend/app/services/llm_credentials.py:449-472`)。
4. 差异:baseline 的 `base_url` 是原样透传;MVP1 要求保存 endpoint 时按 protocol canonicalize,再由调用层做 no-op 双保险(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:77-84`;`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:161-205`)。
5. 差异:baseline 的 fingerprint 只清理尾斜杠;MVP1 要求 fingerprint 输入已经是 protocol canonical base_url,否则等价 endpoint 会产生不同 hash(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13-42`)。
6. 差异:baseline 仍把明文 API key 写在 active credentials 文件;MVP1 当前文档目标是"不落 route 明文",不是已经完成外部 secret vault 迁移(`apps/studio/backend/app/services/llm_credentials.py:475-482`)。
7. **差异(本轮反转新增)**:baseline 的 endpoint 拆分 + endpoint_id 生成散在前端 + `_stable_endpoint_id`(migration 硬编码 host id);MVP1 要求拆分 + 协议匹配 + 测试 + 生成 canonical id(`{slug}-{protocol}[-n]`)下沉 ③b 公共，前端只录入(`apps/studio/backend/app/services/llm_credentials.py:369`;`ux-spec` §6.1 `:375`)。

## 覆盖代码(含覆盖率)

覆盖率:brief 要求的 7 个对象已覆盖 7/7,为 100%。

| 覆盖对象 | 判据归属 | MVP1 对齐结论 |
|---|---|---|
| `registry/contracts.py` | **③b 公共** | `CredentialDescriptor` 是非 secret readiness DTO;`CredentialProviderProtocol` 是执行期取 secret 的宿主接口;`SecretLifetimePolicy` 是缓存/诊断 redaction 策略;`TerminalRetryPolicy` 是 retry 默认值来源(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/contracts.py:12`,`:33`,`:43`,`:107`)。 |
| `registry/credentials.py` | **③b 公共** | `EndpointCredentialProvider` 是 v4 endpoint-backed 迁移 provider;`FallbackCredentialProvider` 是 host provider 与 endpoint storage 的过渡组合(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:14`,`:48`)。 |
| `registry/storage.py:compute_credential_fingerprint` | **③b 公共** | `compute_credential_fingerprint` 是不可逆 fingerprint 生成函数;MVP1 需要让它消费 canonical base_url,否则同一 endpoint 的等价 URL 会产生不同 fingerprint(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13-38`)。base_url canonical + endpoint 拆分/canonical id 都属 ③b 公共(反转)。 |
| `services/llm_credentials.py` | **③a 存储 + ③b 拆分(待下沉)** | `upsert_endpoints` 应成为保存时 base_url canonicalize 的入口(canonical 规则属 ③b)，**存储介质留 ③a**;`save_credentials` 继续做原子落盘与权限保护;`_stable_endpoint_id` 退役并入 ③b canonical id 生成(`apps/studio/backend/app/services/llm_credentials.py:70-79`,`:107-136`,`:369`)。 |
| `services/llm_roles.py` | **③a 存储** | `validate_references` 继续保证 roles/profile/bundle 只引用真实 route_id,不处理 endpoint secret(`apps/studio/backend/app/services/llm_roles.py:88-133`)。 |
| `services/llm_paths.py` | **③a 存储介质注入** | `credentials_path` / `roles_path` / `import_drafts_path` / `canonical_rules_path` 继续是配置文件位置 SSOT(存储介质注入)，避免 router/service 各自拼路径(`apps/studio/backend/app/services/llm_paths.py:13-49`)。 |
| endpoint/route schema clue | **③b 公共(权威源)** | `ProviderEndpoint` 是 credential/base_url/protocol 边界;`ResolvedRoute` 是编排交接物,只携带 `credential_ref`、fingerprint 与 canonical runtime fields(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-181`,`:415-439`)。 |

## 决策原因(详细，承上 §5)

1. 保存时归一化比调用时临时归一化更可靠:resolver、probe、fingerprint、client factory 和 Copilot env 都读同一份 canonical endpoint,减少"测试与运行不是同一路径"的风险(`apps/studio/backend/app/routers/llm.py:460-486`;`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-285`)。
2. 调用时仍要幂等双保险:当前源码存在多条消费路径,包括 Gateway SDK clients 和 Copilot SDK runtime;即使保存时 canonical 了,调用层 no-op normalize 也能保护历史数据(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:144-285`;`apps/studio/backend/app/services/copilot.py:449-491`)。
3. `credential_ref` 是必要边界:route 会进入 role materialization、fallback event、response metadata 等诊断面,不能把 secret 当普通字段传递;`ResolvedRoute` 的字段设计已经体现这一点(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`)。
4. endpoint 与 route 分层是必要边界:endpoint 代表连接/凭证/protocol,route 代表模型/capability/canonical_id;删除 endpoint 时同步删 route,说明这两个层级不能混成一个 provider 字符串(`apps/studio/backend/app/services/llm_credentials.py:139-155`)。

## 代码索引 clues

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-181`: `ProviderEndpoint` 保存 protocol/base_url/credential/status。**③b 公共(权威源)。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-445`: `ResolvedRoute` 输出 credential_ref/fingerprint,不输出 secret。**③b 公共。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:64-113`: `resolve_role` join endpoint/route 后生成 runtime route。**③b 公共。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/credentials.py:14-72`: endpoint-backed 与 fallback credential provider。**③b 公共。**
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:13-42`: fingerprint payload 与当前轻量 base_url normalize(待升级 per-protocol)。**③b 公共。**
- `apps/studio/backend/app/services/llm_credentials.py:107-136`: endpoint upsert 的保存时 canonicalize 落点(canonical 规则 ③b / 存储 ③a)。
- `apps/studio/backend/app/services/llm_credentials.py:369`: `_stable_endpoint_id`(v3→v4 migration 硬编码 host id)，本轮反转后退役并入 ③b 统一 canonical endpoint_id 生成。
- `apps/studio/backend/app/services/llm_credentials.py:431-482`: secret 保留与落盘权限边界(③a 存储)。
- `apps/studio/backend/app/services/llm_roles.py:88-133`: route reference validation(③a 存储)。
- `apps/studio/backend/app/services/copilot.py:476-491`: deepseek/ark runtime base_url helper,可作为保存时规则缺口的证据(③a 调用方式,base_url 规则应集中 ③b)。

## 待办/疑点(原始留底，承上 §8)

1. 待办:新增或迁移一个 protocol-aware canonicalizer,并让 `upsert_endpoints` / v3→v4 migration / import draft apply 都走同一规则(`apps/studio/backend/app/services/llm_credentials.py:107-136`,`:299-356`;`apps/studio/backend/app/services/llm_import_drafts.py:136-202`)。
2. 待办:更新 `compute_credential_fingerprint` 的 base_url 输入语义,确保 canonical base_url 与 fingerprint/cache 失效一致(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py:26-38`)。
3. 待办:调用层保留幂等 normalize,尤其是 `LLMClientManager._get_anthropic_client` 和 Copilot `_resolve_route_runtime` 两条路径(`packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py:187-206`;`apps/studio/backend/app/services/copilot.py:449-491`)。
4. ~~疑点:anthropic/openai/deepseek/ark 的 canonical 规则应写在 Gateway registry 还是 Studio service 层~~ → **已定 ③b 公共(本轮反转)**:base_url canonical 规则 + endpoint 拆分/canonical id 生成都属 endpoint/protocol runtime contract = ③b 公共,存储介质留 ③a 注入(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:163-181`;`ux-spec` §6.1 `:375`)。

## 交叉引用(链接，不复制)

- [[01-handoff-interface]]：`ResolvedRoute` 携带 credential_ref / canonical base_url / fingerprint
- [[04-orch-registry-schema]]：`ProviderEndpoint`/`ProviderRoute`/`ResolvedRoute` schema 字段权威源(本模块只链接)
- [[10-inv-route-chat-model-factory]]：调用时 base_url 幂等双保险(副归一化落点)
- studio copilot（copilot-assist + ux-spec §3.8）：copilot `_resolve_route_runtime` 消费 credential_ref + base_url
- 本模块 base_url / 凭证决策依据 client 层 A' 重设计 F1/D3(完整逻辑 + PM 原话留底于本文 §4/§5)/ 归属判据见 `module-disposition-revised.md` / `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §6.1
