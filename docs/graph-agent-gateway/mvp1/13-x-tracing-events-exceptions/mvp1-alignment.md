---
module: 13-x-tracing-events-exceptions
doc: mvp1-alignment
status: drafted
verified_at: 2026-06-02
---

# 13 — Tracing / Events / Exceptions（横切：fallback 事件、异常、tracing）· MVP1 设计

> **组织方式**：**以每个功能为索引** —— 每个功能（F1–F3）一段，把它的机制/数据流·决策+动机·原话·测试点·status·归属（region/platform）**全收在自己段里**；仅「定义」「接口契约」是模块级总览，模块级证据附录（已实现/差异、覆盖代码/覆盖率、代码索引）放在文末。现状基线见同目录 `baseline.md`。
> **Tier**：③b gateway 公共能力内核（事件 DTO / 异常类 / tracing helper 全在 `packages/graph-agent-gateway` 包内，**无反转、无下沉**）
> **Owns**：fallback 事件 payload（含 from/to route 诊断、分类决策、provider status code、effective runtime settings）、三类 Gateway 结构化异常（语义 + 触发点）、callback 发射边界（callback 失败不遮蔽 runtime 错误）
> **Status**：设计定稿（A' 决策记录已纠正 401/402/403/404 = fallback 非 fail-fast）；代码 = 已实现并测试覆盖，MVP1 只在调用层迁 ChatX 后保留触发位置，不改事件/异常结构
> **Related**：[[01-handoff-interface]]（route 契约，事件 payload 复用同一 `ResolvedRoute`）· [[06-orch-error-classification]]（`classify_exception` 语义源，本模块只触发不重定义）· [[07-orch-fallback-circuit-probe]]（`_generate` fallback 循环，本模块是它的可观测输出）· [[09-inv-invocation-runtime]]（调用层换 ChatX，异常仍回到本模块分类分支）
> **决策日志**：client 层 A' 重设计决策（**完整逻辑 + 用户原话见各功能段 F1/F2，本模块留底**）—— D1（保留编排外壳，不删 `GatewayChatModel`）+ M5（错误分类真实语义：401/402/403/404 = fallback 非 fail-fast）+ 兼容性验证清单第 7 条（fallback event payload 不丢 from/to route 诊断）；归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（13 = 纯 ③b 公共，原 review 已判对，不变）。**M5 错误分类语义跨模块共享**，权威源 [[06-orch-error-classification]]；本模块只在分类决策上发事件/抛异常。
> **现状**：见同目录 `baseline.md`

## 定义

本模块是 Gateway 的横切观测/异常底座，覆盖三个 ③b 公共能力（即下文 F1–F3）：

- **fallback 事件**（`LLMFallbackEvent` + tracing helper，见 **F1**）：把一次 route 切换的诊断打包成结构化事件，经 callback 发给 tracing 底座。**判据归属 ③b 公共**——任何调模型的 app 都需要"哪条 route 失败、为什么、切到哪条"的可观测输出，不依赖应用加工四件事（① UI ② 产品策略 ③ 调用方式 ④ 存储介质）。
- **结构化异常**（`GatewayError` 基类 + 三个子类，见 **F2**）：把"role 没配置 / DI 缺 resolver / 候选链全失败"表达成带稳定 `code` 和机器可读 `context` 的异常，供 Studio/trace 读字段而不是解析自由文本。同属 ③b 公共。
- **callback 发射边界**（`emit_llm_fallback_event`，见 **F3**）：逐个调 callback 的 `on_event`，单个 callback 失败只记日志，不遮蔽 runtime 主流程错误。

MVP1 核心约束：**调用层从自研 `_call_*` 换成原生 ChatX 后，fallback 事件、异常语义、触发点仍归编排层**，不随自研调用层一起删除。事件/异常结构本身一字不改，只把 dispatch 那一步的"异常来源"从自研 dispatch 换成 ChatX invoke。本文只写文档目标，不改代码。

**上下游总览（跨 F1–F3 的统一编排脊柱）**：编排层 `GatewayChatModel._generate`（fallback 循环，[[07-orch-fallback-circuit-probe]]）在 probe/dispatch 失败时 → 调 `classify_exception`（[[06-orch-error-classification]]）得分类决策 → `fallback_allowed` 分支构造 `LLMFallbackEvent`（F1）→ `emit_llm_fallback_event` 逐 callback 发射（F3）→ tracing 底座消费；`fail_fast` 分支 / 全链失败则抛 `AllProvidersFailedError`（带 `failed_provider_codes` + `last_error_chain`，F2）→ 上层（Studio/trace）读结构化字段。

## 接口契约（模块级，跨功能共享）

| 边界 | 契约 |
|---|---|
| **③b → tracing 底座（事件发射）** | `emit_llm_fallback_event(event, callbacks)`：逐个调 `callback.on_event(event)`；单个 callback 抛异常 → 仅记日志（WARNING），继续给后续 callback 发，**不向上传播**（runtime 主流程不被观测层污染）。事件类型固定 `event_type="llm_fallback"`。 |
| **`LLMFallbackEvent` payload（事件 DTO 字段）** | `phase_name`（触发 phase；缺省 `<gateway>`）· `from_provider`（失败 route 的 `route_id`，字段名历史叫 provider 但值是 route id）· `to_provider`（下一条未 marked-down route 的 `route_id`，无则 `<none>`）· `reason`（异常类型+消息）· `code`（当前复用 `[F-v3-gateway-all-providers-failed]`，是否拆独立 event code 待主控）· `context`（结构化诊断字典，`__post_init__` 复制避免共享引用）。`model_dump()` 把以上序列化。 |
| **`context` 子字段（诊断契约，决策记录兼容性清单第 7 条钉死）** | `fallback_decision`（`classify_exception` 分类结果）· `provider_status_code`（分类器读到的 HTTP status）· `unclassified_default`（未知异常是否走默认分类）· `from_route` / `to_route`（route 诊断，由 `_route_diagnostics` 压缩，**不含密钥**）· `effective_runtime_settings`（实际 runtime 参数 + 来源）。route 成一等交接物后，`from_route`/`to_route` 应直接复用同一份 `ResolvedRoute`（字段权威源 [[01-handoff-interface]]/[[04-orch-registry-schema]]）。 |
| **异常对外契约（③b → Studio/trace）** | 三类异常均继承 `GatewayError`（带稳定 `code` + 机器可读 `context`）：① `GatewayRoleNotConfiguredError`{`role_name`,`model_override`} = 编排期 role/route override 不可解析；② `GatewayResolverMissingError`{`phase_name`,`required_dependency=model_resolver`} = LLM phase 缺 DI；③ `AllProvidersFailedError`{`role_name`,`phase_name`,`failed_provider_codes`,`last_error_chain`} = 执行期候选链全失败 / fail-fast 分类包装。上层读字段，不解析自由文本。 |
| **归属 / 稳定性** | 事件/异常/tracing helper 全在 `packages/graph-agent-gateway`（③b 公共），**无下沉项**；错误分类语义（哪个 status → fallback/fail-fast）权威源 = [[06-orch-error-classification]]，本模块只触发不重定义。 |

---

## 功能逐项（每个功能为索引）

### F1 fallback 事件 payload（`LLMFallbackEvent`，含 from/to route 诊断）

- **机制 / 数据流**：编排层 `GatewayChatModel._generate` 的 fallback 循环在 probe/dispatch 失败、且分类为 `fallback_allowed` 时构造 `LLMFallbackEvent` 并交给 F3 发射。`LLMFallbackEvent`（fallback 事件 DTO）：MVP1 保留 `phase_name`、`from_provider`、`to_provider`、`reason`、`code`、`context`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:9` 到 `events.py:19`。统一编排循环各步骤（与 F2 共享同一循环，F2 负责其中抛异常的分支）：
  1. 编排层拿到 `ResolvedRole.routes` 后遍历 route。当前循环在 `gateway_chat_model.py:111`，MVP1 保留这个位置的 fallback/probe/mark-down/error 分类职责。
  2. marked-down route 继续跳过，不发 event，因为没有新失败发生。当前跳过在 `gateway_chat_model.py:113`。
  3. probe 异常继续走 `classify_exception`；只有 `fallback_allowed` 才发 `LLMFallbackEvent`，非 fallback 直接抛 `AllProvidersFailedError`（抛异常分支属 F2），当前触发在 `gateway_chat_model.py:123` 到 `gateway_chat_model.py:151`。
  4. probe false 继续当作 fallback_allowed 的探活失败，发 event 并尝试下一条 route，当前触发在 `gateway_chat_model.py:153` 到 `gateway_chat_model.py:188`。
  5. 调用层从自研 `_dispatch()` 换成 ChatX invoke 后，ChatX 抛出的异常仍回到同一个分类分支（异常来源变化属 F2）；当前 dispatch 异常触发在 `gateway_chat_model.py:237` 到 `gateway_chat_model.py:265`。
  6. event context 继续包含 `from_route` 和 `to_route`，字段由 `_route_diagnostics`（route 诊断压缩器，只暴露 route_id/endpoint_id/provider_model_id/canonical_id/protocol，不暴露密钥）生成，见 `gateway_chat_model.py:389` 和 `gateway_chat_model.py:399`。
  7. response metadata 和 event context 继续带 `effective_runtime_settings`，确保 runtime settings 的来源能被 trace 解释，见 `gateway_chat_model.py:331`、`gateway_chat_model.py:391`。
- **决策 + 动机**：
  - **事件 DTO 放在 Gateway 包内**，是为了 Gateway 不 import Graph Agent execution internals；MVP0 alignment 明确 Gateway 自己拥有 fallback event DTO 和 gateway base exception，见 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:78`。**被否的近路**：复用 graph_agent 的 execution event/exception → 会让 ③b 公共网关反向依赖某个 engine 的内部类型，破坏可复用性。
  - **A' 迁移不能丢 fallback event**：兼容性验证清单第 7 条要求 fallback event payload 仍带 from/to route 诊断（见下方原话留底）；D1 明确 `_generate` 中 fallback/probe/mark-down/usage/metadata 是编排职责（坐实点：`gateway_chat_model.py:111-271` — 熔断跳过 `:113`、probe `:115`、分类 `:124,238`、mark-down `:135,249`、fallback event `:136,250`、usage `:227`、metadata `:313-357`），故调用层迁移不动这些。
- **原话**：
  > **D1 — 否决 A，保留编排外壳**（client 层 A' 重设计决策，本文留底）。**决策**：resolver/gateway **不**裸返回原生 ChatX、**不**删 `GatewayChatModel`，保留它作为编排外壳，只把「每条 route 的实际调用」从自研消息转换换成原生 langchain ChatX。**否决 A（激进版）的理由**：A =「resolver 直接产 ChatX + 删 GatewayChatModel + 用 `with_fallbacks()`」会回归 fallback / probe / 熔断 / usage / metadata / predict；真机只验证了「调用层换 ChatX 修空-content bug」，**从未验证「删编排层」**；且 `with_fallbacks()` 只按异常类型，表达不了「按 HTTP status 分类」。用户原话：
  > > "不用留A, 这是错误判断, 正确的是A'"
  > → A' 只换调用层，**不删 `GatewayChatModel`**；fallback 事件、probe、熔断、usage、metadata 都还在编排外壳里，因此 fallback event 触发点不随调用层迁移消失。

  > **兼容性验证清单第 7 条**（client 层 A' 重设计决策的「A' 实现必过」清单，本文留底）。**要求**："fallback event payload 仍带 from/to route 诊断。" → 这是 A' 迁移的硬性兼容闸口：调用层换 ChatX 后，事件 payload 不得丢失 route diagnostics。
- **测试点**：
  - **payload 带 route 诊断**：成功切换时 fallback event 的 `context.from_route`/`to_route` 带 route diagnostics（route_id/endpoint_id/provider_model_id/canonical_id/protocol），**不含密钥**；带 `effective_runtime_settings`。
  - **phase 不丢给 SDK**：`phase_name` 由编排层填，不能让 ChatX SDK 自己决定。
- **status**：事件 DTO 已实现（`events.py:LLMFallbackEvent`，100% 覆盖）；MVP1 = 保留，payload 不随调用层迁移删除；若 route 成一等交接物，payload 应直接使用同一 `ResolvedRoute`。
- **归属**：③b `packages/graph-agent-gateway`：`events.py`（事件 DTO）、`gateway_chat_model.py:_fallback_event_context`/`_route_diagnostics`（触发点 + context 构造）。region/platform N/A（本模块无 ③a 应用加工成分；② Rust N/A）。

### F2 异常类型语义（各 exception 类型与触发点）

- **机制 / 数据流**：在 F1 共享的统一编排循环里，`fail_fast` 分支 / 全链失败抛 `AllProvidersFailedError`（带 `failed_provider_codes` + `last_error_chain`）→ 上层（Studio/trace）读结构化字段。具体抛异常的位置即 F1 步骤 3（非 fallback 直接抛 `AllProvidersFailedError`，`gateway_chat_model.py:123-151`）与步骤 5（调用层换 ChatX 后 ChatX 抛出的异常仍回到同一分类分支，`gateway_chat_model.py:237-265`）。`AllProvidersFailedError`（候选链失败异常）：MVP1 继续用它包装 `failed_provider_codes` 和 `last_error_chain`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:33` 和 `exceptions.py:49`。三类异常均继承 `GatewayError`（带稳定 `code` + 机器可读 `context`）：① `GatewayRoleNotConfiguredError`{`role_name`,`model_override`} = 编排期 role/route override 不可解析；② `GatewayResolverMissingError`{`phase_name`,`required_dependency=model_resolver`} = LLM phase 缺 DI；③ `AllProvidersFailedError`{`role_name`,`phase_name`,`failed_provider_codes`,`last_error_chain`} = 执行期候选链全失败 / fail-fast 分类包装。
- **决策 + 动机**：
  - **结构化异常替代纯文本 RuntimeError**，是为了 Studio/trace 能读 `last_error_chain` 而不是解析自由文本，见 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:29`。
  - **异常分类不变**：M5 明确 `classify_exception` 沿用，并纠正 401/402/403/404 是 fallback 不是 fail-fast（见下方原话留底）。本模块只在分类决策上发事件/抛异常，分类语义本身归 [[06-orch-error-classification]]。
- **原话**：
  > **M5 — 错误分类真实语义**（client 层 A' 重设计决策，纠正多处文档错误简写，本文留底）。**真实语义**：**401 / 402 / 403 / 404 = fallback（credential/route scope），不是 fail-fast！**（429/500/502/503/504/529、网络错、400+capability 标记同为 `fallback_allowed`；400 非 capability / 413 / 422 才 `fail_fast`；未知 → `fail_fast_with_route_context`）。决策原文明确把 `design.md:142`「400/401/403/404/422 → fail-fast」判定为错（401/403/404 实为 fallback），并已在那一轮一并更正 `design.md:142`。本模块的 fallback 事件正是在 401/402/403/404 走 `fallback_allowed` 分支时发射；写测试时必须按真实语义验证，不能沿用旧简写。**M5 是跨模块共享决策，权威语义源 [[06-orch-error-classification]]**（`registry/error_classification.py:15-17` 三组状态码常量、`:133-188` 分支、`:83-88` action→decision 映射）。
- **测试点**：
  - **结构化异常 payload**：`AllProvidersFailedError` 暴露 `failed_provider_codes` 和 `last_error_chain`（Studio/trace 读字段，非解析文本；回归点 `test_all_providers_failed_error.py:11`）。
  - **ChatX 迁移后异常仍可分类**：调用层换 ChatX 后，ChatX/SDK 抛出的异常仍能被 `classify_exception` 读取 status code 和 chained exception（否则 fallback/fail-fast 判定失准）。
  - **错误分类真实语义（防回归旧简写）**：401/402/403/404 → `fallback_allowed`（发 fallback event，尝试下一条 route），**不是** fail-fast；400(非 capability)/413/422 → `fail_fast`（抛 `AllProvidersFailedError`，不发 fallback event）。
  - **fail-fast 不发 fallback event**：fail-fast 分支只抛异常、不发 `LLMFallbackEvent`（是否补一个非 fallback diagnostic event 待主控判断）。
- **status**：三类 Gateway 结构化异常已实现（`exceptions.py:GatewayError/AllProvidersFailedError/GatewayResolverMissingError/GatewayRoleNotConfiguredError`，均 100% 覆盖）；MVP1 = 保留语义，仅补清楚编排期错误与执行期错误的边界；执行期分类不变（401/402/403/404 = fallback）。
- **归属**：③b `packages/graph-agent-gateway`：`exceptions.py`（异常类）、`gateway_chat_model.py:_generate`（抛异常触发点）。region/platform N/A（② Rust N/A；③a 应用加工成分无）。

### F3 tracing emit（`emit_llm_fallback_event`）

- **机制 / 数据流**：`emit_llm_fallback_event`（fallback 发射 helper）：MVP1 继续由编排层调用它，而不是让 ChatX 或 provider SDK 直接接触 Gateway callback，见 `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:33`。F1 构造好 `LLMFallbackEvent` 后交给本 helper，逐个调 callback 的 `on_event` 发给 tracing 底座；单个 callback 失败只记日志，不遮蔽 runtime 主流程错误。
- **决策 + 动机**：
  - **fallback event 通过 callback adapter 发射**，是为了对齐 tracing 底座而不是在 Gateway 内直接处理 callback 循环；MVP0 alignment 已记录 GW-3 完成，见 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md:41`。
  - **callback 失败不能遮蔽 runtime 错误**：观测层是旁路，不应让一个坏 callback 把真实的模型调用错误吞掉或顶替；当前测试验证 failing callback 后仍能给后续 callback 发 event，见 `packages/graph-agent-gateway/tests/test_llm_fallback_event.py:67`。
- **原话**：本功能的发射边界要求由 D1（保留编排外壳、callback 发射归编排层，原话见 F1）与兼容性验证清单（A' 迁移后 ChatX/SDK 不直接接触 Gateway callback）共同支撑；无独立的额外用户原话，发射不向上污染主流程的语义已写入"决策 + 动机"与下方测试点。
- **测试点**：
  - **callback 失败不遮蔽**：一个 callback 的 `on_event` 抛异常 → 后续 callback **仍收到** event，且 runtime 主流程错误不被吞（回归点 `test_llm_fallback_event.py:test_callback_failure_does_not_mask_fallback_event_delivery:67`）。
- **status**：`emit_llm_fallback_event` 已实现（`tracing.py:emit_llm_fallback_event`，100% 覆盖）；MVP1 = 保留作为 fallback event 发射边界，ChatX 异常仍回到这里发 event，callback 失败不影响主流程。
- **归属**：③b `packages/graph-agent-gateway`：`tracing.py`（发射 helper）。region/platform N/A（事件 callback 的具体订阅者/tracing 持久化是消费方的事，不在本模块；② Rust N/A）。

---

## gaps / 待设计

- **疑点**：fallback event 的 `code` 是否继续复用 `[F-v3-gateway-all-providers-failed]`，还是拆出单独 event code，需要主控确认；当前调用点见 `gateway_chat_model.py:142`/`:256`。
- **疑点**：`AllProvidersFailedError` 同时承载"全候选失败"和"fail-fast 分类后的结构化包装"，命名是否需要在 MVP1 文档或代码中细化，需要主控判断。
- **疑点**：fallback event 当前只在 `fallback_allowed` 分支发射；fail-fast 分支只抛异常。是否需要 fail-fast diagnostic event，需要 tracing 产品判断。
- **疑点**：`from_provider`/`to_provider` 字段名是否保留历史命名；当前实际值已经是 route id，改名涉及所有事件订阅者。
- **核实项**：ChatX 迁移后需要主控核实 ChatX 抛出的异常是否仍能被 `classify_exception` 读取 status code 和 chained exception（[[06-orch-error-classification]] 的输入假设）。

## 交叉引用（双向 [[link]]，不复制）

- [[01-handoff-interface]]：`ResolvedRoute/ResolvedRole` 契约 + route 级 handoff API（事件 payload 复用同一 route）
- [[06-orch-error-classification]]：`classify_exception` 真实语义（401/402/403/404 = fallback），本模块只触发不重定义
- [[07-orch-fallback-circuit-probe]]：`_generate` fallback 循环（本模块是它的可观测输出 + 异常出口）
- [[09-inv-invocation-runtime]]：调用层换 ChatX（dispatch 异常来源变化，触发分支不变）
- **client 层 A' 重设计决策 D1 / M5 / 兼容性清单第 7 条**：完整逻辑 + 用户原话见各功能段 F1/F2（本模块留底）；M5 共享语义源 [[06-orch-error-classification]]。归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`

---

## 模块级证据附录

### 已实现 / 与 baseline 差异

| 项 | baseline 现状 | MVP1 alignment | 功能 |
|---|---|---|---|
| 事件 DTO | 已有 Gateway-owned `LLMFallbackEvent`。 | 保留，不随调用层迁移删除。 | F1 |
| 发射 helper | `emit_llm_fallback_event` 逐 callback 调 `on_event`，callback 失败只记日志。 | 保留，ChatX 异常仍回到这里发 event。 | F3 |
| 触发点 | probe 异常、probe false、dispatch 异常。 | 触发点仍在编排层；dispatch 分支改成 ChatX invoke 异常。 | F1/F2 |
| payload | 已带 from/to route、decision、status code、runtime settings。 | 继续保留；若 route 成一等交接物，payload 应直接使用同一 `ResolvedRoute`。 | F1 |
| 异常 | 已有三类 Gateway 结构化异常。 | 保留语义；仅补清楚编排期错误与执行期错误的边界。 | F2 |
| 错误分类 | 当前 `_generate` 用 `classify_exception` 决定 fallback 或 fail-fast。 | 继续沿用分类器；决策记录明确执行期分类不变（401/402/403/404 = fallback）。 | F2 |

### 覆盖代码（含覆盖率）

覆盖率：brief 指定的事件、异常、tracing helper 100% 覆盖；触发点用 `GatewayChatModel._generate` 补充覆盖。

| 覆盖项 | 覆盖状态 | MVP1 目标 | 功能 |
|---|---:|---|---|
| `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMFallbackEvent`（Gateway 自有 fallback 事件 DTO：保存 phase、from/to provider、原因、错误码、context） | 100% | 继续作为 Gateway-owned fallback 事件 DTO。 | F1 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayError`（结构化异常基类：保存稳定 code 和机器可读 context） | 100% | 继续作为稳定 code/context 的异常基类。 | F2 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:AllProvidersFailedError`（一个 role 的候选 route 全部失败或 fail-fast 分类被包装成统一网关错误） | 100% | 继续表达候选链执行失败，并携带 route-level failure chain。 | F2 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayResolverMissingError`（LLM/Agent phase 没有注入 model resolver） | 100% | 继续表达 DI 缺 resolver，不受 ChatX 迁移影响。 | F2 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayRoleNotConfiguredError`（role 或 route override 在 registry 中不可解析） | 100% | 继续表达编排期 role/route 不可解析。 | F2 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:emit_llm_fallback_event`（callback 发射 helper：逐个调用 callback，并吞掉 callback 自身异常） | 100% | 继续作为 fallback event 发射边界，callback 失败不影响主流程。 | F3 |
| `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel._generate`（fallback runtime 循环：在 probe/dispatch 失败时分类、记录、发事件或抛异常） | 触发点覆盖 | 继续保留编排循环；只替换调用步骤，不替换 fallback/error/tracing。 | F1/F2 |

### 代码索引（clues）

- `packages/graph-agent-gateway/src/graph_agent_gateway/events.py:LLMFallbackEvent`：Gateway fallback 事件 DTO。（F1）
- `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:build_llm_fallback_event`：事件构造 helper。（F1）
- `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py:emit_llm_fallback_event`：事件发射 helper。（F3）
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayError`：结构化异常基类。（F2）
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:AllProvidersFailedError`：候选链失败异常。（F2）
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayResolverMissingError`：resolver DI 缺失异常。（F2）
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py:GatewayRoleNotConfiguredError`：role/override 不可解析异常。（F2）
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel._generate`：fallback/error/tracing 触发主循环。（F1/F2）
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:GatewayChatModel._fallback_event_context`：fallback event context 构造器。（F1）
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:_route_diagnostics`：route diagnostics 压缩 helper。（F1）
- `packages/graph-agent-gateway/tests/test_llm_fallback_event.py:test_callback_failure_does_not_mask_fallback_event_delivery`：callback 失败不遮蔽事件发射的测试。（F3）
- `packages/graph-agent-gateway/tests/test_all_providers_failed_error.py:test_all_providers_failed_error_exposes_standard_payload`：结构化异常 payload 测试。（F2）
