# MVP1 三模块接口设计与修改实施计划（2026-06-11）

> 状态：实施分派计划。  
> 适用对象：Engine PM、Gateway PM、Studio PM。  
> 执行方式：每个 PM 独立 worktree + 独立分支；每步先 RED 报告，审核后再写 Kiro `task.md` 和 Gemini prompt。

## 1. 总体四步

每个模块都按四步走：

| 步骤 | 产物 | PM 做什么 | Codex 审什么 |
|---|---|---|---|
| Step 1 | 接口定义 RED 报告 | 只写接口契约测试，跑出预期失败。 | RED 是否证明接口缺失、owner 是否正确、没有生产代码改动。 |
| Step 2 | 接口定义实现报告 | 写 Kiro `task.md` 和 Gemini prompt，交 Gemini 实施接口与 owner-side 最小收口。 | 接口是否按设计落地，`GREEN-2` 是否不是 fake。 |
| Step 3 | 功能收口 RED 报告 | 只写功能迁移和错误范围测试，证明旧路径仍存在。 | RED 是否覆盖该模块负责的 §1 错误，是否每错一个断言。 |
| Step 4 | 功能收口实现报告 | 写 Kiro `task.md` 和 Gemini prompt，交 Gemini 收口真实功能。 | 旧路径是否被收掉，错误恢复是否硬失败/显式降级，无静默。 |

## 2. 每步固定作业流

每个 PM 的每一步必须执行：

1. 在自己的 worktree/branch 内工作。
2. 只写/改测试，运行目标命令，确认 RED。
3. 向 Codex 提交 RED 报告，包含：改了哪些测试、命令、失败摘要、失败原因为什么符合预期。
4. 等 Codex 审核通过。
5. 编写 Kiro spec `task.md`。
6. 编写 Gemini 实施提示词 `gemini-prompt.md`。
7. 把 prompt 交给 Gemini 实施。
8. PM 审核 Gemini diff、测试输出、边界风险。
9. PM 向 Codex 提交实施报告。
10. 等 Codex 复审通过后进入下一步。

## 3. worktree / branch 约定

从主仓库根目录执行：

```bash
cd /Users/sevenx/Documents/coding/agent-harness
git worktree add .worktrees/pm-engine-mvp1-interface-2026-06-11 -b codex/pm-engine-mvp1-interface-2026-06-11 feat/studio-mvp1-integration
git worktree add .worktrees/pm-gateway-mvp1-interface-2026-06-11 -b codex/pm-gateway-mvp1-interface-2026-06-11 feat/studio-mvp1-integration
git worktree add .worktrees/pm-studio-mvp1-interface-2026-06-11 -b codex/pm-studio-mvp1-interface-2026-06-11 feat/studio-mvp1-integration
```

每个 PM 只在自己的 worktree 内改本模块代码和必要测试。跨模块接口依赖只能通过文档和报告协调，不能直接改别人的模块。

## 4. Engine PM 任务范围

### Step 1: 接口定义 RED

目标测试：

- `packages/graph-agent/tests/core/test_productization_artifact_contracts.py`
- `packages/graph-agent/tests/core/test_productization_storage_contracts.py`
- `packages/graph-agent/tests/core/test_productization_llm_event_contracts.py`
- `packages/graph-agent/tests/core/test_productization_run_result_contracts.py`

必须 RED 的点：

- `ArtifactRef`、`CompiledArtifactManifest`、`RunArtifactRequest`、`RunSession` 缺失。
- `RunArtifactRequest` / `PredictArtifactRequest` / `ResumeRequest` 缺 `idempotency_key`。
- `RunArtifactStore` 缺 seal 不变量和 `get(hash)` hash 校验。
- `LeaseToken` 缺 `fencing_token`。
- `ResponseEnvelope` / `schema_version` / error payload 缺失。
- E-I6 run result contract 缺失。

### Step 2: 接口定义 GREEN

实现范围：

- `packages/graph-agent/src/graph_agent/core/artifacts.py`
- `packages/graph-agent/src/graph_agent/core/adapter_contracts.py`
- `packages/graph-agent/src/graph_agent/core/storage_contracts.py`
- `packages/graph-agent/src/graph_agent/core/llm_provider.py`
- `packages/graph-agent/src/graph_agent/core/event_contracts.py`
- `packages/graph-agent/src/graph_agent/core/result_contracts.py`

注意：

- `LLMProvider` SPI 的 contract fake 是唯一允许例外，因为真实实现归 Gateway。
- 其他 `GREEN-2` 必须连到 owner-side 最小 production path。

### Step 3: 功能收口 RED

目标任务：

- E-F1 compile frozen artifact identity。
- E-F2 runtime only accepts artifact ref。
- E-F3 storage providers and fencing。
- E-F5 no concrete gateway import。
- E-F8 event stream cursor/seq/gap/backpressure。

必须 RED 的错误：

- 同源不同路径 hash 漂移。
- UI metadata 进入 execution fingerprint。
- 同 `Idempotency-Key` run 重复执行。
- seal 后再写。
- lease 冲突、旧 fencing token 写入。
- Engine 未注入 SPI 时自造 gateway 或无明确错误。
- provider invoke 失败未走 SPI error shape。
- event stream 断线、重复、gap、cursor 过旧、反压、乱序。

### Step 4: 功能收口 GREEN

实现目标：

- engine runtime 从源码路径收口到 artifact ref。
- run artifacts 写 `RunArtifactStore`。
- checkpoint/resume 写 `RuntimeStateStore`。
- concrete gateway import 全部替换为 `LLMProvider` SPI。
- event emission 统一为 `EventEnvelope`。

## 5. Gateway PM 任务范围

### Step 1: 接口定义 RED

目标测试：

- `packages/graph-agent-gateway/tests/test_productization_config_credential_contracts.py`
- `packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py`

必须 RED 的点：

- `ConfigTruthStore` 缺 `user_id`、`etag`、`if_match`、`if_none_match`。
- `CredentialResolveResponse` 缺 `secret_handle` / `expires_at`，或泄漏 raw secret。
- route handoff DTO 缺失。
- fallback decision action 缺失。
- 6-state projection/materialize contract 缺失。
- 空 route / give_up / 空 fallback chain 未显式错误化。

### Step 2: 接口定义 GREEN

实现范围：

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/config_store.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/credential_resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolve/handoff.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolve/fallback.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/projection.py`

### Step 3: 功能收口 RED

目标任务：

- G-F1 resolver uses `ConfigTruthStore`。
- G-F2 fallback decision public API。
- G-F3 6-state projection/materialize in gateway。
- G-F6 credential vault failures and expired handles。
- G-F7 resource terminal errors。

必须 RED 的错误：

- 两个并发 `put_config` 同 key 出现 last-writer-wins。
- stale `etag` 未报 `config.etag_conflict`。
- fake vault 5xx 未显式标 route unavailable。
- expired secret handle 被拿去跑。
- no route / give_up / empty fallback chain 静默继续。

### Step 4: 功能收口 GREEN

实现目标：

- resolver 配置读取走 `ConfigTruthStore`。
- fallback decision 从 `GatewayChatModel` 私有逻辑导出为公共函数。
- 6-state projection/materialize 下沉到 gateway。
- credential source 和 expiry 按契约处理。
- 资源终态统一返回 error payload。

## 6. Studio PM 任务范围

### Step 1: 接口定义 RED

目标测试：

- `apps/studio/backend/tests/core/adapters/test_productization_adapters.py`
- `apps/studio/backend/tests/core/adapters/test_productization_local_providers.py`
- `apps/studio/backend/tests/core/adapters/test_productization_http_loopback_harness.py`
- `apps/studio/backend/tests/services/test_productization_publish_golden_contracts.py`

必须 RED 的点：

- `EngineAdapter` / `GatewayAdapter` 缺 transport switch。
- HTTP loopback harness 缺失，无法触发传输族错误。
- local providers 缺 etag/fencing/seal/hash 校验。
- publish/golden contract 缺失。

### Step 2: 接口定义 GREEN

实现范围：

- `apps/studio/backend/app/core/adapters/engine.py`
- `apps/studio/backend/app/core/adapters/gateway.py`
- `apps/studio/backend/app/core/adapters/http_transport.py`
- `apps/studio/backend/app/core/adapters/product_store_local.py`
- `apps/studio/backend/app/core/adapters/run_artifact_store_local.py`
- `apps/studio/backend/app/core/adapters/runtime_state_store_local.py`
- `apps/studio/backend/app/core/adapters/gateway_config_store_local.py`
- `apps/studio/backend/tests/support/http_loopback_harness.py`
- `apps/studio/backend/app/services/publish_pipeline.py`
- `apps/studio/backend/app/services/golden_headless.py`

### Step 3: 功能收口 RED

目标任务：

- S-F9 HTTP transport failure handling。
- S-F1 services depend on adapters。
- S-F2 run/predict source entry compiles ephemeral artifact first。
- S-F3 publish writes ProductArtifactStore release。
- S-F10 publish atomicity and version conflict。
- S-F4/S-F5 copilot/settings consume gateway interfaces。
- S-F6 golden headless。
- S-F7 resume adapter。
- S-F8 GRAPH roundtrip/fingerprint。

必须 RED 的错误：

- timeout、connection refused、5xx、serialization failure、schema mismatch。
- 同 `Idempotency-Key` 超时重发重复执行。
- event stream disconnect / cursor resume / gap / dedupe。
- corrupted artifact bytes 未 hash 校验失败。
- missing hash 在 dev/prod 未分层。
- publish partial failure 留半成品。
- release version 覆盖。
- Studio 服务直接 import SDK internals。
- Studio 自算 gateway 状态/fallback。
- golden 仍走 final_state whole-run diff。
- resume endpoint 仍 501。
- GRAPH serialize/parse 不一致或 UI metadata 进 fingerprint。

### Step 4: 功能收口 GREEN

实现目标：

- Studio services 全部经 adapters。
- source run/predict 变成 source -> ephemeral artifact -> run_artifact。
- publish 变成 artifact release + two-stage commit。
- copilot/settings 消费 GatewayAdapter。
- golden UI/backend 调 headless evaluator。
- resume endpoint 薄接 EngineAdapter。
- GRAPH 走 shared parser/serializer。

## 7. 总门禁

单模块 gate：

```bash
uv run pytest packages/graph-agent/tests/core -q
uv run pytest packages/graph-agent-gateway/tests -q
uv run pytest apps/studio/backend/tests -q
```

跨模块 gate：

```bash
uv run pytest packages/graph-agent/tests packages/graph-agent-gateway/tests apps/studio/backend/tests -q
```

关键词覆盖自检：

```bash
for p in etag fencing 幂等 "hash 校验" 超时 原子 seal "HTTP 本地模拟" "Idempotency-Key" "schema_version" "ResponseEnvelope"; do
  rg -n "$p" docs/mvp1-three-module-interface-design-and-changes-2026-06-11 temp/productization-mvp1-interface-implementation-plan-2026-06-11.md
done
```

## 8. 回滚规则

- Step 1/3 只含测试，审核不通过时只回滚该 step 的测试改动。
- Step 2/4 只回滚当前 step 的 Gemini 实施改动，不回滚前面已通过的 step。
- Interface Batch A 必须单任务回滚，不能因为一个 late gate 失败回滚所有接口任务。
