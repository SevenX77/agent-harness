---
module: 02-orch-role-resolution
doc: mvp1-alignment
status: drafted
binds_design: ./baseline.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolve_role · packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:ModelResolver · apps/studio/backend/app/services/gateway_resolver.py:build_gateway_model_resolver · apps/studio/backend/app/services/llm_role_materializer.py:materialize_role
units: [role-resolution-materialize]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 02 — Role Resolution（角色 → 路线解析）· MVP1 设计

> **Tier**：③b gateway 公共能力内核（`resolve_role` 已在包内；materialize 编排内核现散 ③a 待下沉）
> **Owns**：接收角色编排结构（fallback_chain + 意图），解析成有序可执行 `ResolvedRoute` 链 + 跳过诊断；**不调模型**
> **Status**：设计定稿（2026-06 判据第四轮反转）；代码 = resolve_role 普通链跳过语义与 skipped diagnostics 已落地，materialize 待下沉
> **Related**：[[01-handoff-interface]]（route 契约）· [[04-orch-registry-schema]]（schema 权威源）· [[05-orch-capabilities-and-models]]（capability/lint）· [[08-orch-test-status-ssot]]（6 态投影，materialize 消费）· studio copilot（copilot SDK 调用 = ③a，见 `docs/studio/mvp1/02_capabilities/copilot-assist/` + `00_settings-ux-spec.md` §3.8）
> **决策依据**：client 层 A' 重设计决策（D1 A' / D2 编排-调用分离，完整逻辑 + PM 原话见各功能段 F4/F5）+ 归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`
> **现状**：见同目录 `baseline.md`
> **组织方式**：**以每个功能为索引** —— 每个功能（F1–F6）一段，把它的机制/数据流·决策+动机·原话·测试点·status·归属**全收在自己段里**；仅「定义」「接口契约」「上下游 + 状态机（跨功能数据流脊）」是模块级总览，证据附录（已实现/差异、覆盖代码、代码索引）置于文末。

## 定义

MVP1 目标：把 role→route 变成一等编排 API。编排层只返回有序 `ResolvedRoute` 链，不调用模型；调用层或 Copilot 拿 route 自己执行。两段职责按判据分层：
- **materialize**（角色编辑结构 → fallback_chain）：按意图**过滤路线 / 降级 / 排链 / role-fit 诊断** = **③b 公共编排内核**（现散 ③a `llm_role_materializer.py` 待下沉）；materialization_report 的渲染留 ③a。
- **resolve_role**（fallback_chain → `ResolvedRole`）：逐条解析候选 route、跳过不可用、过滤后空链报错 = **③b 公共**（已在 gateway 包）。

不调模型（调用归 [[09-inv-invocation-runtime]]）。本文只写文档目标，不改代码。

## 接口契约（模块级，跨功能共享）

| 边界 | 契约 |
|---|---|
| **③a → ③b（materialize 入参）** | 角色编排结构 `RoleEntry`{ model_groups（候选 + 意图 thinking/token + fallback 开关）}。③b **看得到**"编排结构 + 意图"（通用），**看不到**"用户怎么 UI 编辑出它"（③a 应用加工）。 |
| **materialize → resolve_role** | `RegistrySnapshot.RoleEntry.fallback_chain` = `RoleRouteEntry[]`（`route_id` + `runtime_settings`）。 |
| **resolve_role 输出** | `ResolvedRole`{ `routes`: `ResolvedRoute[]`（protocol/base_url/credential_ref/provider_model_id/effective settings，字段权威源 `registry/schema.py:415-439`）, `runtime_policy`, `lint_results`, `source_profile`, **`skipped_diagnostics`（已落地，`list[SkippedRoute]`，`schema.py:448-476`）** }。 |
| **两级对外 API（③b 公共）** | ① role 级 `ModelResolver.resolve(role_name, model_override)` → `BaseChatModel`（已有 `resolver.py:73-146`）；② **route 级 `resolve_routes(role_name, model_override)` → `ResolvedRole`（待补，契约由 [[01-handoff-interface]] 钉死）**。 |
| **错误** | role 不存在 / 过滤后空链 → `RegistryResolutionError`（配置错误，**非** 后置 `AllProvidersFailedError`）；`route_override` 坏 route → fail-fast。 |
| **归属 / 稳定性** | `ResolvedRoute`/`ResolvedRole` 字段权威源 = [[04-orch-registry-schema]]（`registry/schema.py`）；本模块**只链接不复制**，防 drift。 |

### 上下游 + 状态机（跨功能数据流脊；目标语义，现状逐步见 `baseline.md`）

**上下游**：① 前端拖拽编辑角色（③a UI）→ 角色编排结构（model_groups + 意图）→ **materialize（③b 内核，现 ③a；见 F4）** → `fallback_chain`（route_id 列表）→ **resolve_role（③b；见 F1/F2/F3）** → `ResolvedRole`（有序 `ResolvedRoute` + 跳过诊断）→ 调用层 / copilot 自己调。

**状态机（route 进链判定，目标语义）**：候选 →〔6 态：`failed/off`→skip ｜ `cooling_down`→warning ｜ `ready/蓝/untested`→continue〕→〔intent：`not_fit/needs_test`→排除 ｜ `using/downgraded`→进链〕→ `fallback_chain` → resolve_role 逐条解析。

**装配入口（③a，喂 snapshot 给 resolve_role）**：`build_gateway_model_resolver`（③a 装配入口，从 Studio v4 credentials + v2/v3 roles 构造 gateway resolver）继续用 `roles.to_registry_snapshot(credentials)` 拼成 gateway runtime snapshot，见当前 `apps/studio/backend/app/services/gateway_resolver.py:18-21`。

---

## 功能逐项（每个功能为索引）

### F1 `resolve_role` 路线解析（role 展开成有序 `ResolvedRoute` 链）

- **机制/数据流**：`resolve_role`（③b，role 展开成有序 `ResolvedRoute` 链）读取 role 后，应按 `role.fallback_chain` 的声明顺序遍历；有 `route_override` 时仍只解析 override 那一条，见当前 entry 选择逻辑 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:45-55`。`select_verified_profile`（选择一个 route 上已验证的调用 profile）仍应在 route 可执行后运行；profile 不可选时是 route 级不可执行原因，目标语义应进入 skipped diagnostic 或 override fail-fast，当前调用点见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:72-75`。`_effective_runtime_settings`（把 route entry 的用户设置、route capability 默认值、protocol 默认值合成最终 runtime settings）仍负责生成 route 的最终调用参数来源，因为调用层只应消费已解析 route，当前实现见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:156-270`。
- **决策+动机**：`resolve_role`（③b）是应承载跳过语义和空链报错的地方（跳过/空链语义见 F2，override 解析见 F3）；逐条解析的产物是 `ResolvedRoute`（一条 runtime-ready route candidate，含 protocol/base_url/credential/provider_model/effective settings）。
- **原话**：（本功能为机制承载点，跳过/空链/override 等关键决策原话见 F2/F3；编排/调用分离原话见 F5）
- **status**：role→route 的纯数据形态已经存在（已实现，见文末附录）；逐条跳过 / 空链 / route-only 暴露 = target。
- **测试点**：`fallback_chain` 按声明顺序逐条解析进链（顺序正确）；route 可执行后才选 profile、合成 effective settings（跳过/override 的具体测试点见 F2/F3）。
- **归属**：region/platform ③b `packages/graph-agent-gateway`：`resolve_role`（已在）、`ResolvedRoute/ResolvedRole` 契约。

### F2 fallback 链跳过坏 route + 过滤后空链报错 + skipped diagnostics

- **机制/数据流**：`resolve_role` 遇到普通 fallback 链 entry 的 route missing、route disabled/failed、endpoint missing、credential missing、profile unavailable 时，会记录 `SkippedRoute` 并继续下一条;相同错误如果来自 `route_override` 则 fail-fast，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:60-140`。`resolve_role` 过滤后如果没有任何 route，会抛 `RegistryResolutionError` 并带 skipped summary，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:212-219`。
- **决策+动机**：**跳过普通 fallback 链里的坏 route**：fallback chain 的意义是"按顺序尝试候选"；第一条暂未配置时直接崩，会破坏后续已配置 route 的执行机会。当前 resolver 已按该语义追加 `skipped_diagnostics` 并继续，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:67-140`。
- **原话**：（跳过语义为机制驱动，无单独 PM 原话；归属判据原话见 F4，编排/调用分离原话见 F5）
- **status**：runtime `resolve_role` 已跳过普通链上的未配置/不可执行 entry，并把 skipped diagnostics 写入 `ResolvedRole.skipped_diagnostics`;`SkippedRoute` 和 `ResolvedRole.skipped_diagnostics` 已在 schema 中落地，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:57-140`、`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:198-227` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-476`。
- **测试点**：
  - **跳过语义**：`fallback_chain` 第一条 route = `failed` → 后续 route **仍被解析进链**（防回归成"第一坏就崩"）。
  - **过滤后空链**：全部候选不可用 → `RegistryResolutionError` 带 skipped summary（**不是**后置 `AllProvidersFailedError`）。
  - **skipped diagnostics**：被跳过的 route 进诊断字段（Studio/trace 能看到"哪些 route 被跳过、为什么"，不只最终失败）。
- **gaps / 待办**：
  - 已落地: `ResolvedRole.skipped_diagnostics` 字段记录 route missing/status/endpoint/credential/profile/lint 的跳过原因，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-476`。
  - 已落地:普通 fallback 链的不可执行 entry 会记录 skipped diagnostic 并继续，override 的不可执行 entry 保持 fail-fast，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:60-140`。
- **归属**：region/platform ③b `packages/graph-agent-gateway`（`resolve_role` 跳过语义 + `ResolvedRole` skipped_diagnostics 契约）。

### F3 `model_override` 精确 route override（fail-fast）

- **机制/数据流**：`resolve_role` 遇到 `route_override` 指定的单条 route 失败时，目标语义仍应 **fail fast**，因为 override 是调用方显式选择，不是 fallback 链里的可跳过候选；当前 override 由 `ModelResolver.resolve` 传入，见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:92-98`。
- **决策+动机**：**`model_override` 继续作为精确 route override**：MVP1 schema 的 execution identifier 是 `route_id`，不是 provider/model 模糊字符串；`RoleRouteEntry` 也用 `route_id` 做唯一引用，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:247-261`。
- **原话**：（override fail-fast 为机制驱动，无单独 PM 原话；两级 API / 编排-调用分离原话见 F5）
- **status**：override 当前与普通链共用同一抛错分支（见 F2 gaps）；override fail-fast 与普通链 skip 的分离 = target。
- **测试点**：**override fail-fast**：`route_override` 指向坏 route → **fail-fast，不 skip**。
- **归属**：region/platform ③b `packages/graph-agent-gateway`（`resolve_role` override 分支语义）。

### F4 materialize 投影（角色编排结构 → fallback_chain）

- **机制/数据流**：
  1. `materialize_role`（③b 编排内核，现散 ③a 待下沉）仍然先把用户选择的 model groups 投影成 `fallback_chain`，并保留 provider model 的手动顺序，见当前 `apps/studio/backend/app/services/llm_role_materializer.py:39-42`。
  2. `materialize_role` 继续把不可用候选排除在保存响应链外并写入 `skipped_provider_details`；按 6 态收敛，排除条件 = `failed`（含原 needs_setup 配置缺口）/ `off`，对 `cooling_down` 写 warning，见当前 `apps/studio/backend/app/services/llm_role_materializer.py:51-59`。该过滤/降级/排链是 ③b 编排内核职责（现散 ③a）。
- **决策+动机**：**materialize 编排内核 = ③b 公共（本轮反转）**：意图驱动的能力编排是 fallback 机制内在需求，换 app 还要。**被否**：旧 §6 判它"③a authoring 投影 / 属产品解释 / 不是 Gateway runtime schema"。现实现散 ③a `llm_role_materializer.py` 待下沉；materialization_report 渲染留 ③a。
- **原话**：
  > **判据（本轮反转 materialize 归属）**："换个 app 还原样能用吗？能=③b，不能=③a。" → materialize 的意图过滤/降级/排链是 fallback 机制内在需求，任何调模型 app 都要 → **③b 公共**（原误判 ③a authoring）。
- **status**：materialize 现位于 ③a（`llm_role_materializer.py`），代码下沉 = target（见 gaps）。
- **测试点**：
  - **materialize intent**：thinking `required` 但 route 不支持 → `not_fit` 排除；output token 超 cap 且 `downgrade=block` → 不进链；`downgrade=allow_with_warning` → 进链 + warning。
  - **6 态对齐**：materialize 跳过 `failed`（含原 needs_setup 配置缺口）/ `off`；**不再有独立 needs_setup 态**。
  - **手动顺序不重排**：materialize 用保存的 manual_order，不做 ready-first/价格/能力重排（回归点 `test_llm_role_materializer_api.py:145-193`）。
- **gaps / 待办**：**代码下沉**（后续工程，非本轮）：materialize 编排内核 → gateway 包；report 渲染留 studio。
- **归属**：region/platform ③b 编排内核（待下沉）；现位置 ③a `apps/studio/backend`：materialize（`llm_role_materializer.py`，待下沉）、materialization_report 渲染、角色编辑 UI。② Rust：N/A（角色/凭证数据永不 Rust）。

### F5 两级对外 API（role 级 `resolve` + route 级 `resolve_routes`；编排/调用分离 + A'）

- **机制/数据流**：
  - `ModelResolver`（把 registry 解析结果包成 `GatewayChatModel` 或 predict mock model）应新增 route-only API，例如 `resolve_routes(role_name, model_override)` 返回 `ResolvedRole`，这样 Copilot 和未来 API 不必绕过 class 去直接 import `registry.resolver.resolve_role`，当前 Copilot 是直接调 pure helper，见 `apps/studio/backend/app/services/copilot.py:419-437`。
  - `ModelResolver.resolve`（把 role/model override 解析成 LangChain chat model）继续作为 Engine 旧入口，只在 route-only 结果不为空时包成 `GatewayChatModel` 或 `PredictGatewayChatModel`，当前包装逻辑见 `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:119-146`。
- **决策+动机**：
  - **把 role→route 做成一等 API**（D2 编排/调用分离）：编排层只决定"该用哪条 route"，调用层才执行 provider 调用；copilot 走 `claude_agent_sdk` 不归 gateway 调，只问 gateway 要 route。client 层共享决策，另见 [[01-handoff-interface]] §5 / [[09-inv-invocation-runtime]] §5。
  - **保留 `GatewayChatModel`**（A'，否决激进版 A）：否决"resolver 直接返回原生 ChatX + 删编排外壳 + 用 `with_fallbacks()`"——它会回归 fallback/probe/熔断/usage/metadata，且 `with_fallbacks()` 只按异常类型分流、表达不了"按 HTTP status 分类"；第八轮真机只验证了"换 ChatX 修空-content bug"，从未验证"删编排层"。fallback、probe、熔断、usage、metadata 都还在编排外壳里。client 层共享决策，另见 [[09-inv-invocation-runtime]] §5。
- **原话**：
  > **D2 编排/调用分离**（PM 原话；client 层共享决策，另见 [[01-handoff-interface]] §4 / [[09-inv-invocation-runtime]] §4）："你只要知道谁跟你说我现在要调 copilot，把 copilot 解析好的 route 给我，你就给他……编排和调用是不是应该更模块化更内聚化，API 写清楚，编排输入什么输出什么。"

  > **A' 保留编排外壳**（PM 原话；client 层共享决策，另见 [[09-inv-invocation-runtime]] §4）："不用留 A，这是错误判断，正确的是 A'。" → 保留 `GatewayChatModel`，fallback/probe/熔断/usage/metadata 留编排外壳。
- **status**：Copilot 内部已按"编排只给 route，调用方自己调"的方向使用 `resolve_role`（已实现，见文末附录）；但 route-only API 还不是 `ModelResolver` 的公开方法，现在 Engine 协议只有 `ModelResolverProtocol.resolve` 返回 `BaseChatModel`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:24-39`。route 级 `resolve_routes` = target。
- **测试点**：（API 契约见模块级「接口契约」两级对外 API 行 + [[01-handoff-interface]]；route-only 返回 `ResolvedRole` 而非 chat model，role 级仍兼容 `BaseChatModel` 入口。）
- **gaps / 待办**：新增 `ModelResolver.resolve_routes`（route→route 一等 API 返回 `ResolvedRole` 而非 chat model），并让 Copilot/registry response 复用它；当前这些路径直接调用 pure helper，见 `apps/studio/backend/app/services/copilot.py:419-437`、`apps/studio/backend/app/routers/llm.py:4588-4603`。
- **归属**：region/platform ③b `packages/graph-agent-gateway`（`ModelResolver`：兼容 Engine `BaseChatModel` 入口 + 补 route 级 `resolve_routes` 一等 API）；消费方 ③a `apps/studio/backend`（copilot、registry response）。

### F6 capability lint（`lint_role_routes`；不做动态替代选择）

- **机制/数据流**：`lint_role_routes`（对 role 的 route 链做 capability lint）仍只在可执行 route 集合上运行；普通 fallback 链的 blocking lint 会把对应 route 记入 `skipped_diagnostics(reason_code="lint_blocked")` 并继续，其余 route 保留;`route_override` 的 blocking lint 仍 fail-fast，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:182-210`。
- **决策+动机**：**runtime resolver 不做动态替代选择**：capability 只能 lint/warn/block，不能按能力自动找别的 route；MVP1 README 的编排层描述要求 role→route 确定性解析，见 `docs/graph-agent-gateway/mvp1/README.md:13-18`、`:27`。**注**：下沉 materialize/capability 到 ③b ≠ 引入动态选型——它们是分类/能力描述，runtime 仍按显式 `route_id` 执行。
- **原话**：（capability/lint 不做动态替代为确定性解析原则，无单独 PM 原话；归属判据原话见 F4。）
- **status**：blocking lint 的普通链跳过语义已落地;resolver 会移除被 blocking lint 命中的 route 并追加 `SkippedRoute(reason_code="lint_blocked")`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:182-210`。
- **测试点**：（blocking lint 的"整 role 失败 vs 跳该 route 继续"语义待定，见 gaps；capability 不做动态选型——runtime 仍按显式 `route_id` 执行。）
- **gaps / 疑点**：✅ **已落地（PM 2026-06-04 决策）= 跳过该 route、继续下一条**（非整 role 失败）。resolver 会标记该 route 跳过(进 `skipped_diagnostics`)、继续下一条；空链才抛 `RegistryResolutionError`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:198-219`。
- **归属**：region/platform ③b `packages/graph-agent-gateway`（lint 在可执行 route 集合上运行）；capability/lint 权威源 [[05-orch-capabilities-and-models]]（materialize 消费）。

---

## gaps / 待设计（模块级汇总）

> 功能内 gap 见各 F 段；下列为模块级 / 跨功能 gap。

- **代码下沉**（后续工程，非本轮）：materialize 编排内核 → gateway 包；report 渲染留 studio。（详见 F4）
- **待办**：新增 `ModelResolver.resolve_routes`（route→route 一等 API 返回 `ResolvedRole` 而非 chat model），并让 Copilot/registry response 复用它；当前这些路径直接调用 pure helper，见 `apps/studio/backend/app/services/copilot.py:419-437`、`apps/studio/backend/app/routers/llm.py:4588-4603`。（详见 F5）
- **已落地**：`ResolvedRole.skipped_diagnostics` 字段记录 route missing/status/endpoint/credential/profile/lint 的跳过原因，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-476`。（详见 F2）
- **已落地**：普通 fallback 链的不可执行 entry 会记录 skipped diagnostic 并继续，override 的不可执行 entry 保持 fail-fast，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:60-140`。（详见 F2/F3）
- ✅ **已落地（PM 2026-06-04 决策）**：blocking lint = **跳过该 route、继续下一条**（不让整个 role 失败）——与 fallback"跳坏 route"语义一致；resolver 会标记该 route 跳过(进 `skipped_diagnostics`)、继续；**全部候选被跳过(空链)才**抛配置错误 `RegistryResolutionError`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:198-219`。（详见 F6）

## 交叉引用（链接，不复制）

- [[01-handoff-interface]]：`ResolvedRoute/ResolvedRole` 契约 + route 级 handoff API
- [[04-orch-registry-schema]]：schema 字段权威源（本模块只链接）
- [[05-orch-capabilities-and-models]]：capability / lint（materialize 消费）
- [[08-orch-test-status-ssot]]：6 态投影（materialize 消费，已取消 needs_setup）
- D2 编排/调用分离 + A' 决策（本文 F4/F5 留底，client 层共享，另见 [[01-handoff-interface]] / [[09-inv-invocation-runtime]]）/ 归属表 `module-disposition-revised.md`

---

## 附录 A — 已实现 / 与 baseline 差异（模块级证据）

- **已实现**：role→route 的纯数据形态已经存在。`ResolvedRoute`（一条 runtime-ready route candidate）包含 protocol/base_url/credential/provider_model/effective settings，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415-439`；`ResolvedRole`（解析后的 role 元数据和有序 routes）包含 routes/runtime_policy/lint/skipped_diagnostics/source profile，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:466-478`。
- **已实现**：Copilot 内部已经按"编排只给 route，调用方自己调"的方向使用 `resolve_role`，见 `apps/studio/backend/app/services/copilot.py:419-437`；真正调用发生在 `stream_query` 里遍历 routes 并创建 Claude SDK session，见 `:218-263`。
- **已实现**：runtime `resolve_role` 已跳过普通链上的未配置/不可执行 entry，并把跳过原因写入 `skipped_diagnostics`;过滤后空链才抛 `RegistryResolutionError`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:60-140` 和 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:212-219`。
- **未实现**：route-only API 还不是 `ModelResolver` 的公开方法。现在 Engine 协议只有 `ModelResolverProtocol.resolve` 返回 `BaseChatModel`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:24-39`。
- **已实现**：skipped diagnostics 已有 schema 字段。`SkippedRoute` 定义跳过原因结构，`ResolvedRole.skipped_diagnostics` 保存 `list[SkippedRoute]`，见 `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448-476`。

## 附录 B — 覆盖代码（含覆盖率，模块级证据）

覆盖率：4/4 个 brief 指定目标已覆盖，100%。其中 runtime 解析覆盖 `registry/resolver.py:33-132` 与 `resolver.py:41-184`；Studio 装配覆盖 `services/gateway_resolver.py:15-21`；authoring 投影覆盖 `services/llm_role_materializer.py:27-269`。

| 覆盖目标 | 归属 | MVP1 目标 |
|---|---|---|
| `registry/resolver.py:resolve_role`（role 展开成有序 `ResolvedRoute` 链，不调模型） | **③b**（已在包内） | 恢复逐条跳过语义、暴露 skipped diagnostics、过滤后空链抛配置错误、保留精确 `route_override` |
| `resolver.py:ModelResolver`（把解析结果包成 `GatewayChatModel`/predict mock） | **③b**（已在包内） | 兼容 Engine `BaseChatModel` 入口 + 补 route 级 `resolve_routes` 一等 API |
| `services/gateway_resolver.py:build_gateway_model_resolver`（Studio v4 creds + roles 构造 resolver） | **③a 装配入口** | 继续作 Studio 装配入口，可复用同一 snapshot 构造 route-only resolver |
| `services/llm_role_materializer.py:materialize_role`（角色编辑 → fallback_chain） | **③b 编排内核（现散 ③a 待下沉）** | 意图过滤/降级/排链/role-fit 诊断下沉 gateway；report 渲染留 ③a |

## 附录 C — 代码索引（clues，模块级证据）

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33-132`：`resolve_role`（③b）是应承载跳过语义和空链报错的地方。
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:73-146`：`ModelResolver.resolve`（③b）是旧 Engine 入口，应继续保留。
- `packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:24-39`：`ModelResolverProtocol` 当前只暴露 chat model 返回值（route 级 API 待补）。
- `apps/studio/backend/app/services/copilot.py:419-437`：`_resolve_copilot_runtime` 展示了 route-only API 的现实需求（③a 消费方）。
- `apps/studio/backend/app/services/llm_role_materializer.py:27-96`：`materialize_role`（③b 编排内核，现散 ③a 待下沉）是保存/展示前的投影。
- `apps/studio/backend/app/routers/llm.py:4588-4603`：`_role_effective_runtime_settings` 现在也直接调用 pure `resolve_role`，遇到解析错误会跳过整个 role。
