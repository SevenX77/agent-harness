---
module: 02-orch-role-resolution
doc: mvp1-alignment
status: drafted
---

# 02 — Role Resolution（角色 → 路线解析）· MVP1 设计

> **Tier**：③b gateway 公共能力内核（`resolve_role` 已在包内；materialize 编排内核现散 ③a 待下沉）
> **Owns**：接收角色编排结构（fallback_chain + 意图），解析成有序可执行 `ResolvedRoute` 链 + 跳过诊断；**不调模型**
> **Status**：设计定稿（2026-06 判据第四轮反转）；代码 = resolve_role 待补跳过语义 + route 级 API、materialize 待下沉
> **Related**：[[01-handoff-interface]]（route 契约）· [[04-orch-registry-schema]]（schema 权威源）· [[05-orch-capabilities-and-models]]（capability/lint）· [[08-orch-test-status-ssot]]（6 态投影，materialize 消费）· [[12-inv-copilot-invocation]]（route 级消费方）
> **决策日志**：`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md` D2 + `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`
> **现状**：见同目录 `baseline.md`

## 1. 定义

MVP1 目标：把 role→route 变成一等编排 API。编排层只返回有序 `ResolvedRoute` 链，不调用模型；调用层或 Copilot 拿 route 自己执行。两段职责按判据分层：
- **materialize**（角色编辑结构 → fallback_chain）：按意图**过滤路线 / 降级 / 排链 / role-fit 诊断** = **③b 公共编排内核**（现散 ③a `llm_role_materializer.py` 待下沉）；materialization_report 的渲染留 ③a。
- **resolve_role**（fallback_chain → `ResolvedRole`）：逐条解析候选 route、跳过不可用、过滤后空链报错 = **③b 公共**（已在 gateway 包）。

不调模型（调用归 [[09-inv-invocation-runtime]]）。本文只写文档目标，不改代码。

## 2. 数据流 / 机制（目标；现状逐步见 `baseline.md`）

**上下游**：① 前端拖拽编辑角色（③a UI）→ 角色编排结构（model_groups + 意图）→ **materialize（③b 内核，现 ③a）** → `fallback_chain`（route_id 列表）→ **resolve_role（③b）** → `ResolvedRole`（有序 `ResolvedRoute` + 跳过诊断）→ 调用层 / copilot 自己调。

**状态机（route 进链判定，目标语义）**：候选 →〔6 态：`failed/off`→skip ｜ `cooling_down`→warning ｜ `ready/蓝/untested`→continue〕→〔intent：`not_fit/needs_test`→排除 ｜ `using/downgraded`→进链〕→ `fallback_chain` → resolve_role 逐条解析。

**目标设计与流程**（逐步）：

1. `materialize_role`（③b 编排内核，现散 ③a 待下沉）仍然先把用户选择的 model groups 投影成 `fallback_chain`，并保留 provider model 的手动顺序，见当前 `apps/studio/backend/app/services/llm_role_materializer.py:39-42`。

2. `materialize_role` 继续把不可用候选排除在保存响应链外并写入 `skipped_provider_details`；按 6 态收敛，排除条件 = `failed`（含原 needs_setup 配置缺口）/ `off`，对 `cooling_down` 写 warning，见当前 `apps/studio/backend/app/services/llm_role_materializer.py:51-59`。该过滤/降级/排链是 ③b 编排内核职责（现散 ③a）。

3. `build_gateway_model_resolver`（③a 装配入口，从 Studio v4 credentials + v2/v3 roles 构造 gateway resolver）继续用 `roles.to_registry_snapshot(credentials)` 拼成 gateway runtime snapshot，见当前 `apps/studio/backend/app/services/gateway_resolver.py:18-21`。

4. `resolve_role`（③b，role 展开成有序 `ResolvedRoute` 链）读取 role 后，应按 `role.fallback_chain` 的声明顺序遍历；有 `route_override` 时仍只解析 override 那一条，见当前 entry 选择逻辑 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:45-55`。

5. `resolve_role` 遇到普通 fallback 链 entry 的 route missing、route disabled/failed、endpoint missing、credential missing 时，目标语义是**记录 warning/skipped diagnostic 并继续下一条**；当前这些点是直接抛错，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56-71`。

6. `resolve_role` 遇到 `route_override` 指定的单条 route 失败时，目标语义仍应 **fail fast**，因为 override 是调用方显式选择，不是 fallback 链里的可跳过候选；当前 override 由 `ModelResolver.resolve` 传入，见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:92-98`。

7. `select_verified_profile`（选择一个 route 上已验证的调用 profile）仍应在 route 可执行后运行；profile 不可选时是 route 级不可执行原因，目标语义应进入 skipped diagnostic 或 override fail-fast，当前调用点见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:72-75`。

8. `_effective_runtime_settings`（把 route entry 的用户设置、route capability 默认值、protocol 默认值合成最终 runtime settings）仍负责生成 route 的最终调用参数来源，因为调用层只应消费已解析 route，当前实现见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:156-270`。

9. `lint_role_routes`（对 role 的 route 链做 capability lint）仍只在可执行 route 集合上运行；blocking lint 应让该 role 解析失败或让对应 route 被跳过，这取决于 lint severity 的产品语义，当前 blocking 直接抛错，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116-122`。

10. `resolve_role` 过滤后如果没有任何 route，目标语义是抛 `RegistryResolutionError` 并带 skipped summary；当前纯函数会返回空 `ResolvedRole`，空链错误由 `ModelResolver.resolve` 后置抛出，见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:104-109`。

11. `ModelResolver`（把 registry 解析结果包成 `GatewayChatModel` 或 predict mock model）应新增 route-only API，例如 `resolve_routes(role_name, model_override)` 返回 `ResolvedRole`，这样 Copilot 和未来 API 不必绕过 class 去直接 import `registry.resolver.resolve_role`，当前 Copilot 是直接调 pure helper，见 `apps/studio/backend/app/services/copilot.py:419-437`。

12. `ModelResolver.resolve`（把 role/model override 解析成 LangChain chat model）继续作为 Engine 旧入口，只在 route-only 结果不为空时包成 `GatewayChatModel` 或 `PredictGatewayChatModel`，当前包装逻辑见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:119-146`。

## 3. 接口契约

| 边界 | 契约 |
|---|---|
| **③a → ③b（materialize 入参）** | 角色编排结构 `RoleEntry`{ model_groups（候选 + 意图 thinking/token + fallback 开关）}。③b **看得到**"编排结构 + 意图"（通用），**看不到**"用户怎么 UI 编辑出它"（③a 应用加工）。 |
| **materialize → resolve_role** | `RegistrySnapshot.RoleEntry.fallback_chain` = `RoleRouteEntry[]`（`route_id` + `runtime_settings`）。 |
| **resolve_role 输出** | `ResolvedRole`{ `routes`: `ResolvedRoute[]`（protocol/base_url/credential_ref/provider_model_id/effective settings，字段权威源 `registry/schema.py:415-439`）, `runtime_policy`, `lint_results`, `source_profile`, **`skipped_diagnostics`（待补字段，`schema.py:448-459`）** }。 |
| **两级对外 API（③b 公共）** | ① role 级 `ModelResolver.resolve(role_name, model_override)` → `BaseChatModel`（已有 `resolver.py:73-146`）；② **route 级 `resolve_routes(role_name, model_override)` → `ResolvedRole`（待补，契约由 [[01-handoff-interface]] 钉死）**。 |
| **错误** | role 不存在 / 过滤后空链 → `RegistryResolutionError`（配置错误，**非** 后置 `AllProvidersFailedError`）；`route_override` 坏 route → fail-fast。 |
| **归属 / 稳定性** | `ResolvedRoute`/`ResolvedRole` 字段权威源 = [[04-orch-registry-schema]]（`registry/schema.py`）；本模块**只链接不复制**，防 drift。 |

## 4. 设计决策基础（用户原话）

> **判据（本轮反转 materialize 归属）**："换个 app 还原样能用吗？能=③b，不能=③a。" → materialize 的意图过滤/降级/排链是 fallback 机制内在需求，任何调模型 app 都要 → **③b 公共**（原误判 ③a authoring）。

> **D2 编排/调用分离**（决策记录 `:62-63`）："你只要知道谁跟你说我现在要调 copilot，把 copilot 解析好的 route 给我，你就给他……编排和调用是不是应该更模块化更内聚化，API 写清楚，编排输入什么输出什么。"

> **A' 保留编排外壳**（决策记录 `:40`）："不用留 A，这是错误判断，正确的是 A'。" → 保留 `GatewayChatModel`，fallback/probe/熔断/usage/metadata 留编排外壳。

## 5. 决策 + 动机

- **materialize 编排内核 = ③b 公共（本轮反转）**：意图驱动的能力编排是 fallback 机制内在需求，换 app 还要。**被否**：旧 §6 判它"③a authoring 投影 / 属产品解释 / 不是 Gateway runtime schema"。现实现散 ③a `llm_role_materializer.py` 待下沉；materialization_report 渲染留 ③a。
- **把 role→route 做成一等 API**：架构决策要求编排/调用分离——编排层只决定 route，调用层才执行 provider 调用；决策记录明示输入输出边界，见 `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:45-56`。
- **保留 `GatewayChatModel`**：决策记录否决了"resolver 直接返回原生 ChatX + 删除编排外壳"的方案；fallback、probe、熔断、usage、metadata 都还在编排外壳里，见 `.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md:28-39`。
- **跳过普通 fallback 链里的坏 route**：fallback chain 的意义是"按顺序尝试候选"；第一条暂未配置时直接崩，会破坏后续已配置 route 的执行机会，当前崩点见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56-71`。
- **`model_override` 继续作为精确 route override**：MVP1 schema 的 execution identifier 是 `route_id`，不是 provider/model 模糊字符串；`RoleRouteEntry` 也用 `route_id` 做唯一引用，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:247-261`。
- **runtime resolver 不做动态替代选择**：capability 只能 lint/warn/block，不能按能力自动找别的 route；MVP1 README 的编排层描述要求 role→route 确定性解析，见 `docs/graph-agent-gateway/mvp1/README.md:13-18`、`:27`。**注**：下沉 materialize/capability 到 ③b ≠ 引入动态选型——它们是分类/能力描述，runtime 仍按显式 `route_id` 执行。

## 6. 测试关键点

- **跳过语义**：`fallback_chain` 第一条 route = `failed` → 后续 route **仍被解析进链**（防回归成"第一坏就崩"）。
- **override fail-fast**：`route_override` 指向坏 route → **fail-fast，不 skip**。
- **过滤后空链**：全部候选不可用 → `RegistryResolutionError` 带 skipped summary（**不是**后置 `AllProvidersFailedError`）。
- **materialize intent**：thinking `required` 但 route 不支持 → `not_fit` 排除；output token 超 cap 且 `downgrade=block` → 不进链；`downgrade=allow_with_warning` → 进链 + warning。
- **6 态对齐**：materialize 跳过 `failed`（含原 needs_setup 配置缺口）/ `off`；**不再有独立 needs_setup 态**。
- **skipped diagnostics**：被跳过的 route 进诊断字段（Studio/trace 能看到"哪些 route 被跳过、为什么"，不只最终失败）。
- **手动顺序不重排**：materialize 用保存的 manual_order，不做 ready-first/价格/能力重排（回归点 `test_llm_role_materializer_api.py:145-193`）。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`resolve_role`（已在）、materialize 编排内核（待下沉）、`ResolvedRoute/ResolvedRole` 契约。
- **③a** `apps/studio/backend`：materialize 现位置（`llm_role_materializer.py`，待下沉）、materialization_report 渲染、`build_gateway_model_resolver` 装配入口、角色编辑 UI。
- **② Rust**：N/A（角色/凭证数据永不 Rust）。

## 8. gaps / 待设计

- **代码下沉**（后续工程，非本轮）：materialize 编排内核 → gateway 包；report 渲染留 studio。
- **待办**：新增 `ModelResolver.resolve_routes`（route→route 一等 API 返回 `ResolvedRole` 而非 chat model），并让 Copilot/registry response 复用它；当前这些路径直接调用 pure helper，见 `apps/studio/backend/app/services/copilot.py:419-437`、`apps/studio/backend/app/routers/llm.py:4588-4603`。
- **待办**：给 `ResolvedRole` 增加 skipped diagnostics 字段，记录 route missing/status/endpoint/credential/profile/lint 的跳过原因；当前字段列表见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-459`。
- **待办**：把普通 fallback 链的不可执行 entry 改为 warning + continue，把 override 的不可执行 entry 保持 fail-fast；当前普通链与 override 共用同一抛错分支，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:45-75`。
- **疑点**：blocking lint 是"整个 role 配置错误"还是"该 route 跳过后继续下一条"。当前 blocking lint 在全部 route 解析后抛 role 级错误，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116-122`。

## 已实现 / 与 baseline 差异

- **已实现**：role→route 的纯数据形态已经存在。`ResolvedRoute`（一条 runtime-ready route candidate）包含 protocol/base_url/credential/provider_model/effective settings，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`；`ResolvedRole`（解析后的 role 元数据和有序 routes）包含 routes/runtime_policy/lint/source profile，见 `:448-459`。
- **已实现**：Copilot 内部已经按"编排只给 route，调用方自己调"的方向使用 `resolve_role`，见 `apps/studio/backend/app/services/copilot.py:419-437`；真正调用发生在 `stream_query` 里遍历 routes 并创建 Claude SDK session，见 `:218-263`。
- **未实现**：runtime `resolve_role` 尚未跳过普通链上的未配置/不可执行 entry，当前是直接抛 `RegistryResolutionError`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56-71`。
- **未实现**：route-only API 还不是 `ModelResolver` 的公开方法。现在 Engine 协议只有 `ModelResolverProtocol.resolve` 返回 `BaseChatModel`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:24-39`。
- **未实现**：skipped diagnostics 没有 schema 字段。`ResolvedRole` 当前只有 `lint_results/source_profile` 等字段，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-459`。

## 覆盖代码（含覆盖率）

覆盖率：4/4 个 brief 指定目标已覆盖，100%。其中 runtime 解析覆盖 `registry/resolver.py:33-132` 与 `resolver.py:41-184`；Studio 装配覆盖 `services/gateway_resolver.py:15-21`；authoring 投影覆盖 `services/llm_role_materializer.py:27-269`。

| 覆盖目标 | 归属 | MVP1 目标 |
|---|---|---|
| `registry/resolver.py:resolve_role`（role 展开成有序 `ResolvedRoute` 链，不调模型） | **③b**（已在包内） | 恢复逐条跳过语义、暴露 skipped diagnostics、过滤后空链抛配置错误、保留精确 `route_override` |
| `resolver.py:ModelResolver`（把解析结果包成 `GatewayChatModel`/predict mock） | **③b**（已在包内） | 兼容 Engine `BaseChatModel` 入口 + 补 route 级 `resolve_routes` 一等 API |
| `services/gateway_resolver.py:build_gateway_model_resolver`（Studio v4 creds + roles 构造 resolver） | **③a 装配入口** | 继续作 Studio 装配入口，可复用同一 snapshot 构造 route-only resolver |
| `services/llm_role_materializer.py:materialize_role`（角色编辑 → fallback_chain） | **③b 编排内核（现散 ③a 待下沉）** | 意图过滤/降级/排链/role-fit 诊断下沉 gateway；report 渲染留 ③a |

## 代码索引（clues）

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33-132`：`resolve_role`（③b）是应承载跳过语义和空链报错的地方。
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:73-146`：`ModelResolver.resolve`（③b）是旧 Engine 入口，应继续保留。
- `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:24-39`：`ModelResolverProtocol` 当前只暴露 chat model 返回值（route 级 API 待补）。
- `apps/studio/backend/app/services/copilot.py:419-437`：`_resolve_copilot_runtime` 展示了 route-only API 的现实需求（③a 消费方）。
- `apps/studio/backend/app/services/llm_role_materializer.py:27-96`：`materialize_role`（③b 编排内核，现散 ③a 待下沉）是保存/展示前的投影。
- `apps/studio/backend/app/routers/llm.py:4588-4603`：`_role_effective_runtime_settings` 现在也直接调用 pure `resolve_role`，遇到解析错误会跳过整个 role。

## 交叉引用（链接，不复制）

- [[01-handoff-interface]]：`ResolvedRoute/ResolvedRole` 契约 + route 级 handoff API
- [[04-orch-registry-schema]]：schema 字段权威源（本模块只链接）
- [[05-orch-capabilities-and-models]]：capability / lint（materialize 消费）
- [[08-orch-test-status-ssot]]：6 态投影（materialize 消费，已取消 needs_setup）
- 决策记录 `client-layer-decision-record.md` D2 / 归属表 `module-disposition-revised.md`
