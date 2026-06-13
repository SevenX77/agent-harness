# MVP1 三模块接口设计与修改（2026-06-11）

> 状态：独立设计工作包。  
> 用途：给 Engine PM / Gateway PM / Studio PM 分派接口化和错误范围实施任务。  
> 非目标：不直接覆盖 FROZEN MVP1 权威文档；不新增 `temp/productization-mvp1-error-enumeration-2026-06-11.md` 以外的错误范围。

## 1. 最终结果

MVP1 产品化后，`graph-agent`、`graph-agent-gateway`、`apps/studio` 三模块按接口边界协作：

| 模块 | 核心职责 | 不能做什么 |
|---|---|---|
| Engine | 定义并实现执行原语：compile、run-by-artifact、predict-by-artifact、resume、run artifact store、runtime state store、event stream、run result contract。 | 不能直接依赖 gateway concrete module；不能把源码路径作为核心 runtime 输入；不能裸 `Path` 写运行产物/运行态。 |
| Gateway | 定义并实现配置真相、凭证解析、route handoff、fallback decision、6-state projection/materialize。 | 不能让 Studio 自己发明状态规则；不能裸读配置文件作为唯一契约；不能把凭证失败静默变成空 route。 |
| Studio | 定义本地/远端 adapter、transport switch、本地 provider、publish pipeline、golden headless caller、UI/产品编排。 | 不能直接 import engine/gateway 内部实现；不能绕过 compile 直接跑源码；不能绕过 gateway 自算 6-state/fallback。 |

## 2. 十二个设计点

| ID | 设计点 | 规则 owner | 配合方 | 最终边界 |
|---|---|---|---|---|
| D1 | SDK + Adapter 边界 | Engine/Gateway 各自拥有 SDK 语义；Studio 拥有 adapter transport | 三模块 | Studio 只通过 `EngineAdapter` / `GatewayAdapter` 调原语；adapter 可切 in-process 或 HTTP(loopback)。 |
| D2 | 存储三线 + 成品库 | Engine 拥有运行产物/运行态/artifact identity；Gateway 拥有配置真相；Studio publish 拥有 release decision | 三模块 | 配置真相线、运行产物线、运行态线、成品库分开；provider 只存取，不发明语义。 |
| D3 | 冻结编译产物与 run-by-version | Engine | Studio publish/run/predict | 核心 runtime 只吃 `ArtifactRef`，源码入口必须先 compile 到 ephemeral artifact。 |
| D4 | Engine ↔ Gateway 依赖倒置 | Engine 定 SPI；Gateway 实现 provider | Engine/Gateway/Studio | Engine 只依赖 `LLMProvider` SPI，不 import gateway concrete module。 |
| D5 | Gateway 凭证、route、fallback | Gateway | Studio copilot/settings、Engine SPI consumer | 凭证解析、route handoff、fallback decision 都由 Gateway 公共门面输出。 |
| D6 | 6 态与 materialize | Gateway | Studio Settings UI | Gateway 计算状态，Studio 只渲染。failed reason 只用于 failed 态。 |
| D7 | Golden headless | Headless golden component；Engine 只提供 run result contract；Studio 拥有 UX | Engine/Studio | Golden 消费 `run_results_ref + baseline_ref`，不再由 Engine evaluator 负责“跑+判”。 |
| D8 | GRAPH parse/serialize | Engine/shared parser owns executable syntax | Studio canvas/source editor | Canvas 和源码使用同一 parse/serialize 边界；UI metadata 不进执行 fingerprint。 |
| D9 | Publish 流水线 | Studio publish owns release；Engine owns artifact identity | Engine/Studio | publish 写成品库 release，不 zip 源码当 runtime 包。 |
| D10 | Resume/checkpoint | Engine owns runtime state store | Studio debug-resume | checkpoint/resume 走 lease + heartbeat + fencing。 |
| D11 | Event stream | Engine owns envelope/cursor semantics；Studio owns transport UI | Engine/Studio | 事件统一 `EventEnvelope`，支持 cursor 续接、seq 去重、gap 错误。 |
| D12 | 反写执行规则 | Codex/PM process | 三模块 | FROZEN 文档另行反写；本工作包只做实施分派和审查入口。 |

## 3. 核心接口契约

### 3.1 Engine 接口

```text
ArtifactRef(
  artifact_id,
  content_hash,
  store: "ephemeral" | "product",
  version?,
  manifest_ref,
  source_map_ref
)

RunArtifactRequest(
  artifact_ref,
  inputs,
  execution_context,
  idempotency_key
)

RunSession(
  run_id,
  event_stream_ref,
  result_ref?,
  status_ref?
)

LeaseToken(
  lease_id,
  owner_id,
  fencing_token,
  ttl_ms,
  safety_margin_ms
)

ResponseEnvelope(
  schema_version,
  ok,
  data?,
  error_code?,
  error_payload?
)
```

Engine 必须定义：

- `ArtifactRef` / `CompiledArtifactManifest` / source map / execution fingerprint。
- `run_artifact` / `predict_artifact` / `resume`，并携带 `Idempotency-Key`。
- `RunArtifactStore`：`begin_run`、`put_batch`、`seal_run`、`get_object(hash)`；封存后再写必须失败。
- `RuntimeStateStore`：`acquire_lease`、`heartbeat`、`snapshot`、`restore`、`release`；写入必须校验 fencing token。
- `LLMProvider` SPI。
- `EventEnvelope` / `ResponseEnvelope` / stream cursor。
- `RunResultSnapshot`，供 golden headless 消费。

### 3.2 Gateway 接口

```text
ConfigTruthStore:
  get_config(user_id, key) -> ConfigRecord(value, etag)
  put_config(user_id, key, value, if_match?, if_none_match?) -> etag

CredentialResolver:
  resolve(request(source, user_id, role)) -> CredentialResolveResponse(secret_handle, expires_at)

Route/Fallback:
  resolve_routes(request) -> ResolvedRouteChain
  decide_fallback(request) -> FallbackDecision
  materialize_role(request) -> MaterializedRole
  project_route_state(request) -> ProviderModelStateProjection
```

Gateway 必须定义：

- 配置真相写入的 `etag` / `if_match` / `if_none_match`。
- 凭证 source：`local_input` / `remote_vault`，返回 secret handle 和 `expires_at`。
- route handoff DTO。
- fallback decision：`retry_same` / `switch_route` / `give_up`。
- 6-state projection/materialize。
- 空 route、空 fallback chain、give_up 都是显式错误，不是普通空值。

### 3.3 Studio 接口

Studio 必须定义：

- `EngineAdapter`：`compile`、`run_artifact`、`predict_artifact`、`resume`。
- `GatewayAdapter`：`resolve_routes`、`materialize_role`、`project_route_state`、`decide_fallback`、`resolve_credential`。
- adapter transport switch：`in_process` + `http_loopback`。
- 本地 provider：config store、run artifact store、runtime state store、product artifact store。
- HTTP 本地模拟 harness：超时、拒连、5xx、序列化失败、schema mismatch、幂等、事件流断线、多 worker。
- publish pipeline protocol：stage invisible artifact -> registry commit visible -> compensation GC。
- golden headless caller protocol：只消费 run result 和 baseline。

## 4. 错误范围

错误范围唯一来源是 `temp/productization-mvp1-error-enumeration-2026-06-11.md`。

当前必须覆盖“本地模拟远端”能触发的错误：

| 族 | 必做错误 |
|---|---|
| 完整性 | `get(hash)` hash 校验失败；hash 取不到 dev/prod 分层；哈希漂移；GRAPH 往返/指纹漂移。 |
| 并发 | config etag 冲突；seal 后再写；lease 抢占；旧 lease fencing 拒写；publish 版本撞车。 |
| 传输 | HTTP 超时、拒连、5xx、序列化失败、schema mismatch、幂等重试、事件流断线/cursor/gap/去重。 |
| 原子性 | publish 多步部分失败不留半成品，补偿 GC。 |
| 凭证 | 假 vault 失败、secret 过期。 |
| 资源/终态 | 空 route、空 fallback chain、give_up 必须显式报错。 |

现在只留接口位、不做恢复逻辑：

- 时钟漂移。
- 真网络分区。
- 跨节点配额。

这些推迟项实施时记录到 `docs/deferred-items.md`。

## 5. 统一恢复纪律

- 每个错误必须有专属 `error_code`。
- 只允许硬失败或显式降级。
- 禁止静默降级。
- dev/prod 分层只用于“完整性·按 hash 取不到”。
- publish 失败不能留下半成品。
- 脑裂场景不能双写。
- prod 缺 artifact 不能静默重编。

## 6. 审查口径

Codex 复审时按这些问题验收：

1. 测试是否先 RED，且失败原因正是旧路径或接口缺口。
2. 接口 owner 是否正确；provider/adapter 是否只翻译和存取，不制定语义。
3. `GREEN-2` 是否进入真实 owner-side production path，而不是 fake。
4. HTTP 本地模拟能否触发传输族错误。
5. 多 worker 能否触发 etag/lease/fencing 并发错误。
6. 错误是否都有专属 `error_code`，且没有静默降级。
7. 三个真多机错误是否只留位，未提前实现恢复逻辑。
