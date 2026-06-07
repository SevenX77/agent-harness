---
status: Ready for Gemini (contract gate passed; RED tests installed)
created: 2026-06-06
updated: 2026-06-06
owner: Graph-Agent Gateway
ws_id: WS-5-resolution-purity
modules: [01, 02]
depends_on: [WS-1]          # 共享 resolver.py；WS-1 已并入 HEAD，已解锁
blocks: []
contract_gate: passed 2026-06-06
red_tests:
  files:
    - packages/graph-agent-gateway/tests/test_registry_resolver.py
    - packages/graph-agent-gateway/tests/test_runtime_hard_cutover.py
    - packages/graph-agent-gateway/tests/test_model_resolver_protocol.py
  command: uv run pytest packages/graph-agent-gateway/tests/test_registry_resolver.py packages/graph-agent-gateway/tests/test_model_resolver_protocol.py packages/graph-agent-gateway/tests/test_runtime_hard_cutover.py -q
  result: 10 failed, 20 passed, 1 xfailed (expected RED)
owns_files:
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py   # resolve_role：skip + skipped diagnostics + 空链配置错误 + override fail-fast + lint skip
  - packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py            # ModelResolver：新增 resolve_routes route 级 API + 清理空链死代码
  - packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py            # ModelResolverProtocol：新增 resolve_routes 签名
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py     # ⚠️ 扩展自初始 owns（见 §2）：仅新增 skipped diagnostics 字段/类型，不动既有字段
  - packages/graph-agent-gateway/tests/                                         # WS-5 新增/修改的 gateway 包测试
spec_ssot:
  - ../../../docs/graph-agent-gateway/mvp1/01-handoff-interface/mvp1-alignment.md   # §1/§2/§3/§6：route 级 API + 唯一交接物 + 测试点
  - ../../../docs/graph-agent-gateway/mvp1/02-orch-role-resolution/mvp1-alignment.md # 定义/接口契约/F1/F2/F3/F5/F6
related_baseline:
  - ../../../docs/graph-agent-gateway/mvp1/01-handoff-interface/baseline.md
  - ../../../docs/graph-agent-gateway/mvp1/02-orch-role-resolution/baseline.md
applies_standard: ../../../docs/development/task-spec-standard.md   # 7 铁律 IR1–IR7
review_flow: Claude 写 WS-5 需求输入 → Codex 写 RED 测试 → Claude 过契约门 → Codex 更新本文为实施任务书 → Gemini 实现到 GREEN → Codex 审到 §6 硬退出全满足 → Codex 回写 baseline → Claude 终审
---

# Graph-Agent Gateway MVP1 · WS-5 解析纯化 — Implementation Tasks

> **给流水线各环节**：本文是 WS-5 的实施任务书。当前状态 = **Codex RED 测试已落地，Claude 契约门已通过，待 Gemini 实现到 GREEN**。
> - **Codex（写测试）**：已按 §5 写入 RED 测试，覆盖 §4 行为契约分支 + §5 回归点；不得削弱断言。
> - **Claude（契约门）**：已确认 RED 测试忠实编码 01/02 alignment 目标，允许 Gemini 实施。
> - **Gemini（实现）**：先读 §3 列的源码并**回述关键符号/现状**，再写代码到测试变绿；只碰 §2 owns，目标机制以 `spec_ssot` 的 alignment 为唯一真理（本文不复制设计原理，只给指针 + 可测契约）。
> - **Codex（审查 + 回写）**：审到 §6 硬退出**全满足**（非主观"满意"），再照**真实代码**回写 §8 指定 baseline。
> - **git 纪律**：本 WS 任何人都**不要 `git commit`**；stage 只按文件名 stage §2 owns 文件，**禁止 `git add .`**；提交由用户侧 `::git-stage` 外部管。

## Requirements 映射（_Requirements 标签 → alignment 出处）

| 标签 | 含义 | alignment 出处 |
|---|---|---|
| `02.F2-skip` | 普通 fallback 链上不可执行 entry → 跳过 + continue（不再第一条坏就崩） | 02 §F2 机制/决策 |
| `02.F2-empty` | 过滤后空链 → `resolve_role` 内抛 `RegistryResolutionError`（带 skipped summary），**非**后置 `AllProvidersFailedError` | 02 §F2 测试点「过滤后空链」 |
| `02.F2-diag` | `ResolvedRole` 新增 `skipped_diagnostics`，记录每条被跳过 route 的 route_id/reason_code/message/from_override | 02 §F2 gaps + 01 §3 数据契约 |
| `02.F3-override` | `route_override` 指定的坏 route → **fail-fast**，不 skip | 02 §F3 |
| `02.F6-lint` | blocking lint → 跳过该 route（进 `skipped_diagnostics`）+ continue；override 单条被 block → fail-fast；空链才抛配置错误 | 02 §F6 gaps（PM 2026-06-04 已定） |
| `01.§3-resolve_routes` | `ModelResolver` + `ModelResolverProtocol` 新增 route 级 `resolve_routes(role_name, *, route_override) → ResolvedRole`（只返 route，不调模型、不包 chat model） | 01 §3「② route 级」+ §8 #1（PM 2026-06-04 已定）；02 §F5 gaps |
| `01.§6-parity` | 两级 API 解析同一 role → **同一组有序 route**（role 级与 route 级不分叉） | 01 §6「route 是唯一交接物」 |
| `01.§6-no-call` | `resolve_routes` 返回后 gateway **不发起任何 provider 调用**（纯编排） | 01 §6「route 级不替 app 调」 |

---

## 1. 目标与 SSOT 指针（IR5）

**做什么**：把 gateway 的 role→route 解析"纯化"为两件事——
1. **模块 02**：`resolve_role`（registry 纯函数，把一个 role 展开成有序 `ResolvedRoute` 链，不调模型）从"链上第一个坏 route 直接抛错"改成"**普通 fallback 链坏 route 逐条跳过 + 产 skipped diagnostics + continue**；**过滤后空链**才抛结构化配置错误；只有 **`route_override` 指定的坏 route 才 fail-fast**；blocking lint 也改为跳该 route 而非整 role 失败。
2. **模块 01**：把 route 升级为**一等交接 API**——在 `ModelResolver`（把 registry 解析结果包成 chat model 的类）和 `ModelResolverProtocol`（engine 依赖注入用的 resolver 协议）上**新增 route 级 `resolve_routes`**，只返回解析好的 `ResolvedRole/ResolvedRoute`、不替调用方调模型，供 engine/predict/copilot 等"自己用别的 SDK 跑"的消费方使用。

**为什么**：fallback 链的意义是"按顺序尝试候选"，第一条暂未配置就崩会让后续可用 route 永远没机会执行（02 §F2 决策）；route 级 API 是"编排/调用分离"（D2）的落点——编排只决定"用哪条 route"，调用方自己执行（01 §5 / 02 §F5）。**目标机制的完整原理、决策、PM 原话见 `spec_ssot` 两份 alignment，本文不复制（IR5）。**

**目标真理（怎么做）**：
- route 级 API + 唯一交接物 + 测试点 → 01 alignment §1 / §2 / §3 / §6。
- skip / 空链 / override / lint / resolve_routes → 02 alignment 「定义」「接口契约」+ F1/F2/F3/F5/F6。

**现状起点**：01 baseline、02 baseline（见 frontmatter `related_baseline`）。

---

## 2. 文件归属（并发锁，IR1）

### 本 WS owns（可改/建）
| 文件 | 改什么 |
|---|---|
| `registry/resolver.py` | `resolve_role`：skip + `skipped_diagnostics` + 空链配置错误 + override fail-fast + lint skip（§4） |
| `resolver.py` | `ModelResolver` 新增 `resolve_routes`；清理空链死代码（§4 D 步） |
| `protocol.py` | `ModelResolverProtocol` 新增 `resolve_routes` 方法签名 |
| `registry/schema.py` | **⚠️ 扩展（见下）**：仅新增 `skipped_diagnostics` 字段 + skipped 诊断类型，**不动** `ResolvedRoute/ResolvedRole` 既有任何字段 |
| `packages/graph-agent-gateway/tests/` | WS-5 新增/修改的测试文件 |

> **⚠️ owns 扩展声明（透明）**：初始 brief 给的 owns 是前三个 + 测试。**`registry/schema.py` 是 Claude 据下列三点裁定新增的**，请 PM 知悉：
> 1. **物理必需**：`skipped_diagnostics` 是 `ResolvedRole` 的字段（01 §3 数据契约 / 02 §F2 gaps 指明字段权威源在 `registry/schema.py:448-459`）；不在 schema.py 加字段，`resolve_role` 无处写跳过诊断，`02.F2-diag` 落不了地。
> 2. **授权**：IMPL_PLAN §五「04 registry schema … DTO bridge seam **如需微调，并入相关 WS**，不单立」——`skipped_diagnostics` 即 02 模块的 schema 微调，并入 WS-5。
> 3. **无并发冲突（IR1）**：WS-1 已并入 HEAD；WS-2（storage/credentials）、WS-3（state-projection/materializer）、WS-4（events/exceptions/tracing）的 owns 均**不含** `registry/schema.py`。

### 禁止触碰（别的 WS / 接线非本轮）
| 文件 | 归属 / 原因 |
|---|---|
| `gateway_chat_model.py`、`client_manager.py` | WS-1 调用核心（共享热点） |
| `registry/storage.py`、`apps/studio/.../llm_credentials.py` | WS-2 base_url 保存侧 |
| `apps/studio/.../llm_state_projection.py`、`llm_role_materializer.py` | WS-3 6 态 |
| `events.py`、`exceptions.py`、`tracing.py` | WS-4 事件/异常 code |
| `__init__.py`（gateway 公共门面） | route handoff 类型导出 = **后续工程非本轮**（01 §8 #4）。engine/predict 经 `ModelResolverProtocol` 注入消费 `resolve_routes`，消费方需要 `ResolvedRole/ResolvedRoute` 类型时走 `graph_agent_gateway.registry.schema` import，本轮**不**改顶层门面。 |
| `apps/studio/.../copilot.py`、`apps/studio/.../routers/llm.py`、`packages/graph-agent/.../llm_phase_node.py` | ③a/engine 消费方；接线改走 `resolve_routes` = 后续工程（01 §8 #4）。**它们仍直调 pure `resolve_role`，会继承本轮新语义**——见 §4-E 不回归。 |

> **resolver.py 的预存改动**：工作树里 `resolver.py` 已含未提交的 `predict_context` 相关行（见 [resolver.py:81](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:81)、[:119-134](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:119)）。Gemini 实现 `resolve_routes` **以工作树现状为基线，保留 predict 分支不回退**，不要和它打架。

---

## 3. Grounding：实现前必读并回述（IR2，防脑补）

> Gemini 动手前，先打开下列文件、**回述每个符号当前做什么 + 当前行为**，再写代码。

| 符号（file:line） | 当前做什么 | WS-5 要改什么 |
|---|---|---|
| `registry/resolver.py:resolve_role` [:33-132](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33) | role 展开成有序 `ResolvedRoute` 链；纯函数不调模型 | 见 §4-B/C |
| 抛错点 [:56-58](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56)（route missing）、[:59-60](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:59)（status 不可执行）、[:61-63](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:61)（endpoint missing）、[:66-71](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:66)（credential missing）、[:72-75](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:72)（profile selection failed） | 普通链 entry 任一不可执行 → 立即 `raise RegistryResolutionError` | 普通链 → skip + diag + continue；override → 保持 fail-fast |
| `EXECUTABLE_ROUTE_STATUSES` [:26](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:26) | `{"verified","unverified_manual"}` | 不变（判定标准沿用） |
| `route_override` 分支 [:45-50](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:45) | override 时构造单条 `RoleRouteEntry`，否则遍历 `role.fallback_chain` | 需据此区分 override（fail-fast）vs 普通链（skip） |
| lint blocking [:116-122](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116) | 全部解析后 `lint_role_routes`；任一 blocking → 抛 role 级错（用 `first.route_id`/`first.capability`/`first.message`） | blocking → 跳该 route 进 diag + continue；override 单条被 block → fail-fast；空链才抛 |
| `ResolvedRole` [schema.py:448-459](packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:448) | 字段 = role_name/system_prompt_prefix/runtime_policy/routes/lint_results/source_profile_* | 新增 `skipped_diagnostics`（§4-A） |
| `ResolvedRoute` [schema.py:415-439](packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:415) | 单条 runtime-ready route | **不动** |
| `ModelResolver.resolve` [resolver.py:73-146](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:73) | 调 `resolve_role` → 空链抛 `AllProvidersFailedError`（[:104-109](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:104)）→ 算 max_tokens/temperature/thinking → predict 分支（[:119-134](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:119)）返 `PredictGatewayChatModel`，否则 `GatewayChatModel` | 新增 `resolve_routes`；清理空链死代码（§4-D）；**predict/role 级返回不回归** |
| `RegistryResolutionError → GatewayRoleNotConfiguredError` 映射 [resolver.py:99-103](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:99) | `resolve()` 把 registry 配置错误统一映射成 engine 可识别异常 | role 级保留此映射；route 级 `resolve_routes` 的错误暴露策略见 §4-D |
| `ModelResolverProtocol` [protocol.py:24-39](packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py:24) | 只有 `resolve(...) → BaseChatModel` | 新增 `resolve_routes(...) → ResolvedRole` |
| `mark_provider_down` [resolver.py:148-183](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:148) | 用单条 `fallback_chain` 调 `resolve_role` 再取 `role.routes[0]` 标记熔断 | 不主动改；但需在测试里确认正常可执行 route 的标记行为不回归（§5） |
| ③a 消费方 `_resolve_copilot_runtime` [copilot.py:419-437](apps/studio/backend/app/services/copilot.py:419) / `_role_effective_runtime_settings` [llm.py:4588-4603](apps/studio/backend/app/routers/llm.py:4588) | **都直调 pure `resolve_role`** | **不改**，但会继承新语义 → §4-E 不回归 |

---

## 4. 目标行为契约（可测；写行为不写实现，Gemini 自选实现）

> 机制原理/决策见 alignment（IR5）；下表是 Codex 写测试、Gemini 实现的**可测契约**。

### A. `skipped_diagnostics` 数据契约（`02.F2-diag`）
`ResolvedRole` 新增字段 `skipped_diagnostics`：被跳过 route 的有序列表，每条至少含：
- `route_id: str`
- `reason_code`：枚举之一 —— `route_missing` / `route_not_executable` / `endpoint_missing` / `credential_missing` / `profile_unavailable` / `lint_blocked`（一一对应 §3 各抛错点）
- `message: str`（人类可读原因，可沿用现抛错文案）
- `from_override: bool`（该跳过是否源自 `route_override`，普通链 = `False`）

实现建议（非强制）：新增 `SkippedRoute`(BaseModel, `extra="forbid"`) + `ResolvedRole.skipped_diagnostics: list[SkippedRoute] = Field(default_factory=list)`；`reason_code` 用 `Literal[...]`（code-style：Literal over stringly-typed）。字段权威源归 04，本轮在 schema.py 落地即可。

### B. 普通 fallback 链解析（`route_override is None`）
| 输入分支 | 现状 | 目标 |
|---|---|---|
| entry route_missing / status 不可执行 / endpoint_missing / credential_missing / profile_unavailable | 立即 raise | **skip 该 entry**：记 `skipped_diagnostics`（对应 reason_code，from_override=False）+ continue 下一条 |
| 某 entry 解析成功 | 进 routes | 进 `resolved_routes`（顺序 = 声明顺序，`02.F1`） |
| 解析后跑 lint，某 route blocking（`02.F6-lint`） | 抛 role 级错 | 该 route 从 `resolved_routes` 剔除 + 记 diag(`lint_blocked`) + continue；`lint_results` 仍保留全部 lint 供诊断 |
| 遍历 + lint 后 `resolved_routes` 为空（全跳过，或 `fallback_chain` 本就空） | 返回空 `ResolvedRole`（空链错误后置在 `resolve()`） | **在 `resolve_role` 内** raise `RegistryResolutionError`，message 带 skipped summary（`02.F2-empty`） |

### C. `route_override` 解析（fail-fast，`02.F3-override`）
| 输入 | 目标 |
|---|---|
| override 指定 route 不可执行（任一 reason_code，含 lint blocking） | **fail-fast**：`raise RegistryResolutionError`，**不** skip、**不**进 diag-then-continue（override 是调用方显式选择，不是可跳过候选） |
| override 指定 route 可执行 | 正常返回单条 route 的 `ResolvedRole` |

### D. route 级 API `resolve_routes`（`01.§3-resolve_routes` / `01.§6-*`）
- **签名**：`resolve_routes(self, role_name: str, *, route_override: str | None = None) → ResolvedRole`（新 API 直接用干净命名 `route_override`；旧 `resolve(model_override=...)` 改名传播**不在本轮**，见 §7）。
- **行为**：内部走与 `resolve()` **同一条** `resolve_role`，返回 `ResolvedRole`（含 routes + skipped_diagnostics）；**不**构造/返回任何 chat model、**不**发起任何 provider 调用（`01.§6-no-call`）。
- **错误暴露**：role 不存在 / 过滤后空链 / override 坏 route → 让 `RegistryResolutionError` 暴露给调用方（route 级消费方要看见结构化配置错误；**不**映射成 `GatewayRoleNotConfiguredError`——那是 role 级 `resolve()` 给 engine 的兼容映射）。
- **parity（`01.§6-parity`）**：同一 snapshot + 同一 role，`resolve()` 内部 `resolved_role.routes` 与 `resolve_routes()` 返回的 `.routes` **逐条一致**（route_id 顺序、endpoint、effective settings 相同）。
- **协议**：`ModelResolverProtocol` 同步新增 `resolve_routes` 方法签名（engine/predict 经注入消费）。
- **死代码清理**：B 步把空链错误下沉进 `resolve_role` 后，`resolve()` 里 `if not resolved.routes: raise AllProvidersFailedError`（[resolver.py:104-109](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:104)）**永不触发** → **删除该分支**；若 `AllProvidersFailedError` 在 `resolver.py` 再无其他使用点，**一并清理其 import**（[resolver.py:14-17](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:14)）。**严禁留无标记死代码或静默保留**（WS-1 踩坑④）。

### E. 不回归（本轮必须保住的现有行为）
1. **role 级 `resolve()` 不变**：仍返回 `GatewayChatModel`（含 max_tokens/temperature/thinking 计算、callbacks/phase_name 传递）；空链/坏配置经 `RegistryResolutionError → GatewayRoleNotConfiguredError` 映射给 engine（错误**类型**可能从 `AllProvidersFailedError` 变为 `GatewayRoleNotConfiguredError`，属预期；须测试断言新类型 + §6 确认 studio/engine HTTP 映射不破坏）。
2. **predict 分支不回归**：`resolve(predict_context=...)` 仍返回 `PredictGatewayChatModel`；role→route 纯净不被破坏（predict 移交 engine 本期不做，见 `predict-migration-to-engine.md`）。
3. **engine 消费不变**：`LlmPhaseNode._resolved_tracing_model`（[llm_phase_node.py:173](packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:173)）调 `resolve()` 仍拿 `BaseChatModel`（本轮不接线 engine 走 resolve_routes）。
4. **`mark_provider_down` 不回归**：对正常可执行 route 的手动熔断标记行为不变。
5. **③a 消费方继承新语义（预期，非回归）**：`copilot._resolve_copilot_runtime` 和 `llm._role_effective_runtime_settings` 直调 `resolve_role`，本轮后行为变为"普通链 skip 坏 route 用好的、全坏才抛"。这是 alignment 期望的统一语义，**不是 bug**。但**它们的现有测试若因此失败，列入报告由 PM 定夺，禁止静默改测试**（WS-1 踩坑②）。它们内部的旧空链保护（copilot `if not resolved.routes` / llm `except RegistryResolutionError`）变冗余，属接线期清理（§7 deferred），**本轮不动**。

---

## Phase 0: 契约门（Claude 审 RED 测试）

- [x] 0.1 Codex 写完 RED 测试后，Claude 审"测试是否忠实编码 01/02 alignment 目标"
  - 重点：§4 每条分支都有测试？override fail-fast 与普通链 skip 是否分开断言？空链断言的是 `RegistryResolutionError`（带 skipped summary）而非 `AllProvidersFailedError`？parity 测试是否对比 `resolve()` 与 `resolve_routes()` 的 routes？skipped_diagnostics 的 reason_code 是否逐枚举断言？
  - 结果：**契约门已通过（2026-06-06）**，允许 Gemini 实现；实现仍须保持 RED 断言强度，不得为过测削弱测试。
  - _Requirements: 02.F2-skip, 02.F2-empty, 02.F2-diag, 02.F3-override, 02.F6-lint, 01.§3-resolve_routes, 01.§6-parity, 01.§6-no-call_

- [x] 0.2 RED 测试已落地并验证为预期失败
  - 测试文件：
    - `packages/graph-agent-gateway/tests/test_registry_resolver.py`
    - `packages/graph-agent-gateway/tests/test_runtime_hard_cutover.py`
    - `packages/graph-agent-gateway/tests/test_model_resolver_protocol.py`
  - RED 命令：`uv run pytest packages/graph-agent-gateway/tests/test_registry_resolver.py packages/graph-agent-gateway/tests/test_model_resolver_protocol.py packages/graph-agent-gateway/tests/test_runtime_hard_cutover.py -q`
  - RED 结果：`10 failed, 20 passed, 1 xfailed`（预期失败点：缺 `skipped_diagnostics`、普通链仍第一条坏 route 就抛、缺 `resolve_routes`、空链仍走旧 `AllProvidersFailedError` 路径）。
  - _Requirements: 全部_

## Phase 1: schema —— skipped diagnostics 字段/类型

- [ ] 1.1 `ResolvedRole` 新增 `skipped_diagnostics` 字段 + 诊断类型
  - 按 §4-A 落地：新增 skipped 诊断类型（建议 `SkippedRoute`，`extra="forbid"`，`reason_code` 用 `Literal` 六枚举）+ `ResolvedRole.skipped_diagnostics: list[...] = default_factory=list`。
  - **只增不改**：不动 `ResolvedRoute/ResolvedRole` 任何既有字段（§2 owns 扩展约束）。
  - 验证命令：`uv run pytest packages/graph-agent-gateway/tests -q -k "skipped or resolved_role"`；`uv run mypy packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`
  - _Requirements: 02.F2-diag_

## Phase 2: resolve_role —— skip + 空链配置错误 + override fail-fast + lint skip

- [ ] 2.1 普通 fallback 链坏 route 跳过 + skipped diagnostics + continue
  - 按 §4-B：route_missing/route_not_executable/endpoint_missing/credential_missing/profile_unavailable 改为 skip + 记 diag(from_override=False) + continue；解析成功的按声明顺序进链。
  - _Requirements: 02.F2-skip, 02.F2-diag, 02.F1_

- [ ] 2.2 过滤后空链 → `RegistryResolutionError`（带 skipped summary）
  - 按 §4-B 末行：遍历 + lint 后 `resolved_routes` 为空（全跳过或 fallback_chain 本就空）→ 在 `resolve_role` 内 raise `RegistryResolutionError`，message 含被跳过 route 摘要。
  - _Requirements: 02.F2-empty_

- [ ] 2.3 `route_override` 坏 route fail-fast
  - 按 §4-C：override 模式（单条）任一不可执行原因（含 lint blocking）→ fail-fast raise，不进 skip/continue。
  - _Requirements: 02.F3-override_

- [ ] 2.4 blocking lint → 跳该 route + continue（非整 role 失败）
  - 按 §4-B lint 行：blocking lint 命中的 route 从 `resolved_routes` 剔除 + 记 diag(`lint_blocked`) + continue；`lint_results` 仍保留全部 lint；override 单条被 block → fail-fast（§4-C）。
  - **内部顺序建议**（Gemini 可选等价实现）：① 逐条解析（2.1/2.3）→ ② 解析成功的进 `provider_routes`/`resolved_routes` → ③ 跑 `lint_role_routes` 并按 2.4 处理 blocking → ④ 空链判定（2.2）→ ⑤ 组装 `ResolvedRole`。
  - 验证命令：`uv run pytest packages/graph-agent-gateway/tests -q -k "resolve_role"`；`uv run mypy packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py`
  - _Requirements: 02.F6-lint, 02.F2-empty, 02.F3-override_

## Phase 3: route 级 resolve_routes API + 空链死代码清理

- [ ] 3.1 `ModelResolver.resolve_routes` + `ModelResolverProtocol` 签名
  - 按 §4-D：新增 `resolve_routes(role_name, *, route_override=None) → ResolvedRole`，走同一 `resolve_role`，不包 chat model、不发 provider 调用；`RegistryResolutionError` 直接暴露（不映射）；`ModelResolverProtocol` 同步新增签名。
  - _Requirements: 01.§3-resolve_routes, 01.§6-parity, 01.§6-no-call_

- [ ] 3.2 清理空链死代码
  - 按 §4-D 末段：删除 `resolve()` 中 `if not resolved.routes: raise AllProvidersFailedError`（[resolver.py:104-109](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:104)）；若 `AllProvidersFailedError` 在本文件无其他使用点，一并清 import。不留无标记死代码。
  - 验证命令：`uv run pytest packages/graph-agent-gateway/tests -q -k "resolve_routes or resolver"`；`uv run mypy packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py`
  - _Requirements: 01.§3-resolve_routes_

## Phase 4: 验证与回报

- [ ] 4.1 跑 WS-5 必要验证（全绿 + 真实 e2e）
  - `uv run pytest packages/graph-agent-gateway/tests -q`（owns 全包）
  - `uv run mypy packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py packages/graph-agent-gateway/src/graph_agent_gateway/protocol.py packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`
  - **消费方回归门**（owns 外，只读跑测试，不改它们）：`uv run pytest apps/studio/backend/tests -q -k "copilot or role_effective or registry"`——确认 ③a 消费方经 `resolve_role` 的新语义未**破坏**其测试；失败按 §4-E #5 列报告。
  - 若有 Studio/Tauri dev session 运行，改 backend Python 后按项目规则重启；未运行则报告"未启动 dev session"。
  - _Requirements: 全部_

- [ ] 4.2 回报等待 Codex 审 + 回写 baseline
  - 回报 modified files、每条验证命令与结果、是否有 deferred、消费方回归门结果、是否重启 Studio。
  - **不要 claim 终审通过**；由 Codex 审到 §6 硬退出全满足后回写 §8 baseline，再交 Claude 终审。
  - stage 只按文件名 stage §2 owns 文件，禁止 `git add .`；不要 `git commit`。
  - _Requirements: 全部_

---

## 5. 测试要求（Codex 必须覆盖，IR3/IR4）

**真实 e2e 要求（IR4，至少一条非 fake mock）**：用真实 `RegistrySnapshot` fixtures（混合好/坏 route）跑真实 `resolve_role`/`resolve_routes`，断言实际产出，**不**得 mock `resolve_role` 内部到绿。

必覆盖：
1. **普通链 skip**（`02.F2-skip`）：`fallback_chain` 第一条 = `failed`/缺 endpoint/缺 credential → 后续可用 route **仍被解析进链**（防回归"第一坏就崩"）；被跳过的进 `skipped_diagnostics` 且 reason_code 正确。
2. **每个 reason_code**（`02.F2-diag`）：route_missing / route_not_executable / endpoint_missing / credential_missing / profile_unavailable / lint_blocked 各有用例命中对应 reason_code、from_override=False。
3. **过滤后空链**（`02.F2-empty`）：全部候选不可用 → `RegistryResolutionError`（带 skipped summary），**断言不是** `AllProvidersFailedError`。
4. **override fail-fast**（`02.F3-override`）：`route_override` 指坏 route → `RegistryResolutionError` fail-fast，**不** skip（断言不会去解析别的 route、不产 continue）；override 指可执行 route → 正常单条返回。
5. **lint skip**（`02.F6-lint`）：blocking lint 命中链中某 route → 该 route 不在结果 routes、进 `skipped_diagnostics(lint_blocked)`、其余 route 仍在；override 单条被 lint block → fail-fast。
6. **resolve_routes 契约**（`01.§3/§6`）：返回 `ResolvedRole`（非 chat model）；**parity** —— 同 snapshot+role 下 `resolve()` 的 routes 与 `resolve_routes()` 的 routes 逐条一致；**no-call** —— `resolve_routes` 过程不触发任何 provider 调用（可用 spy/无网络 fixture 断言）。
7. **回归 - role 级 resolve**：`resolve()` 仍返回 `GatewayChatModel`；坏配置经映射抛 `GatewayRoleNotConfiguredError`（断言新错误类型）。
8. **回归 - predict 分支**：`resolve(predict_context=...)` 仍返回 `PredictGatewayChatModel`。
9. **回归 - mark_provider_down**：正常可执行 route 的手动熔断标记不回归。
10. **回归 - ③a 消费方**（owns 外，跑现有测试套件）：copilot `_resolve_copilot_runtime` / llm `_role_effective_runtime_settings` 经新 `resolve_role` 语义后，现有测试通过；若行为变更使某测试失败，**列报告**（§4-E #5），不静默改。

---

## 6. 验收标准（硬退出，IR4）

- [ ] §5 全部测试绿（含至少一条真实 e2e）
- [ ] 普通链坏 route 跳过 + 后续可用 route 进链；被跳过的全部进 `skipped_diagnostics` 且 reason_code 准确
- [ ] 过滤后空链抛 `RegistryResolutionError`（带 skipped summary），`AllProvidersFailedError` 空链分支已删除、无残留死代码/无用 import
- [ ] `route_override` 坏 route fail-fast；blocking lint 跳该 route 而非整 role 失败
- [ ] `resolve_routes` 返 `ResolvedRole`、不调模型、不发 provider 调用；与 `resolve()` 的 routes parity 一致；`ModelResolverProtocol` 已含签名
- [ ] 无回归：role 级 `resolve()` 返 `GatewayChatModel`、predict 分支返 `PredictGatewayChatModel`、engine `_resolved_tracing_model` 仍拿 `BaseChatModel`、`mark_provider_down` 正常路径不变
- [ ] 错误码变更（空链 → `RegistryResolutionError`/`GatewayRoleNotConfiguredError`）已确认对 studio/engine HTTP/错误码映射**无破坏**；若有影响记 `docs/deferred-items.md` + 报告
- [ ] mypy 干净（§2 owns 四个源码文件）
- [ ] ③a 消费方回归门结果已报告（通过 / 或失败项列出由 PM 定夺）

---

## 7. 不做（范围锁定，IR7 + deferred）

下列均**不在本轮**，发现相关问题记 `docs/deferred-items.md`，不顺手改：
1. **旧 `resolve(model_override=...)` 全局改名 `route_override`**（01 §8 #2 已定方向，但命名传播涉及 `protocol.py`/`resolver.py`/`llm_phase_node.py`/`copilot.py`/`llm.py` 等 owns 外大量调用点）→ **独立清理任务，deferred**。本轮仅新 API `resolve_routes` 用干净的 `route_override` 命名。
2. **`__init__.py` 导出 route handoff 类型**（01 §8 #4 后续工程）→ 不做。engine/predict 经协议注入消费，类型走 `registry.schema` import。
3. **copilot/llm.py/engine 接线改走 `resolve_routes`**（01 §8 #4 后续工程）→ 不做。它们仍直调 pure helper，继承新语义（§4-E）。
4. **materialize 编排内核下沉 ③b**（02 §F4 gaps 后续工程）→ 不做。
5. **predict → engine 移交**（`predict-migration-to-engine.md`）→ 本期不做；本轮只保住 predict 分支不回归。
6. **`ResolvedRoute` 既有字段、`gateway_chat_model`/`client_manager` 调用核心**（WS-1 领域）→ 不动。

---

## 8. baseline 回写指令（IR6，实现落地后由 Codex 照真实代码写）

> baseline 永远照**已落地真实代码**写，**实现前不精修**。

- `docs/graph-agent-gateway/mvp1/02-orch-role-resolution/baseline.md`：
  - 「编号执行流程」#15（[resolver.py:56-71](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:56)「都会立刻抛 `RegistryResolutionError`」）→ 改为描述真实的 skip + diag + continue + 空链才抛。
  - #18 lint blocking（[:116-122](packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:116)）→ 改为真实的 lint skip 语义。
  - #20（[resolver.py:104-109](packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:104) 空链抛 `AllProvidersFailedError`）→ 据真实代码改（该分支已删 / 空链改由 `resolve_role` 抛配置错误）。
  - 「Baseline/Alignment 差异」「待办/疑点」#1/#2/#4 → 据真实落地更新（skip 已实现、skipped_diagnostics 已加、空链错误码已定）。
- `docs/graph-agent-gateway/mvp1/01-handoff-interface/baseline.md`：
  - 「resolve API 契约」/「待办/疑点」#2 → 补记 `resolve_routes` route 级 API 已落地（`ModelResolverProtocol` 已含签名）；`__init__` 导出/下游接线仍 deferred 据实标注。
  - 「已实现/与 baseline 差异」表 resolver API 行 → 据真实代码更新。

## 9. 评审检查点

- **契约门（Claude 审 Codex 测试）**：§5 每条分支有断言？override fail-fast vs 普通链 skip 分开测？空链断言 `RegistryResolutionError` 非 `AllProvidersFailedError`？parity / no-call / 每个 reason_code 都覆盖？回归项（predict/role 级/消费方）都在？
- **Codex 审查退出**：§6 验收清单**逐条**满足（硬退出，非主观满意）；死代码确已清；mypy 干净；消费方回归门已跑。
- **Claude 终审**：合不合 01/02 alignment 意图？baseline 是否照真实代码诚实回写（§8）？测试是否假绿（有无真实 e2e、有无 mock 内部到绿）？owns 边界（尤其 schema.py 只增不改、未碰禁碰清单）是否守住？
