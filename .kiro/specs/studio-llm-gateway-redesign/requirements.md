---
status: Ready for Review
created: 2026-06-01
owner: Studio + Engine
direction: ./architecture-direction.md
supersedes_draft: ./requirement.md
related_spec: ../studio-llm-platform-control-plane-runtime/requirements.md
source: Gemini implementation_plan.md (MVP0) + 2026-06-01 audit + architecture-direction.md
---

# LLM Gateway & Roles Redesign — Requirements

## Introduction

这是一个**聚焦的回归修复 + 状态同步切片**，比 `studio-llm-platform-control-plane-runtime`
窄。它只解决 2026-06-01 审计确认的三个近期问题，并把它们对齐到
[architecture-direction.md](./architecture-direction.md) 的**远端服务化方向**。

**根因背景**：2026-05-25 两个 hard cutover 提交（`ecab5fe1`、`c8bfb93f`）删了旧 LLM 栈，
回归丢失了旧 resolver 的 skip+WARNING 容错与旧 save 的"逻辑/凭证解耦"。本 spec 在新 registry
架构内**重新植入**这两个行为，并把测试状态从前端易失态改为后端 SSOT 回写。

**近期范围（本 spec 的承诺项）**：Requirement 1（save 解耦）、Requirement 2（resolver 优雅跳过）、
Requirement 3（测试状态 SSOT 回写）、Requirement 4（远端就绪形状约束，横切）。

**模块全景（已记录）**：Requirement 5（侧边栏过滤——经代码核实为**误诊，已撤回**）、Requirement 6
（WaveSpeed 诚实失败，任务延后）作为"按下葫芦不起瓢"的完整性记录，见 `tasks.md` 与 `docs/deferred-items.md`。

## Requirements

### Requirement 1: 角色保存与凭证解耦（消除保存死锁）

**Objective:** 作为用户，我希望增删改任意角色不被"其它角色引用了未配置路由"所阻断，
以便在没有配置任何凭证时也能自由编辑角色。

#### Acceptance Criteria

1. When 前端调用 `PUT /api/llm/roles` 或 `DELETE /api/llm/roles/{role_name}`，
   the system shall 仅对 `RolesData` 做 schema/格式校验，不针对当前 `llm_credentials.json`
   的 `known_route_ids` 做路由引用硬校验（即 `_save_roles_with_active_routes` 以
   `known_route_ids=None` 调用 `validate_references` 与 `save_roles_file`）。
2. When 一份 `llm_roles.yaml` 的某些角色（如默认模板 `fast`）引用了未配置的 `route_id`，
   the system shall 仍允许保存/删除**其它**角色成功并返回 200，而不是返回 400。
3. If 保存负载本身 schema 非法（缺字段、类型错误、`schema_version` 不符），
   then the system shall 返回明确的 400 校验错误（这条路径保持不变）。
4. The system shall 不依赖凭证状态来决定角色 YAML 能否落盘；逻辑层（YAML）与物理层
   （credentials JSON）在写入时完全解耦。

### Requirement 2: 运行期 resolver 对未配置路由优雅跳过

**Objective:** 作为运行时，我希望解析一个角色的 `fallback_chain` 时跳过未配置/不可执行的路由
并继续尝试后续路由，以便配置不全时仍能用可用路由执行，而不是崩在第一个缺失路由上。

> **设计立场（重要）**：这是对 V2 cutover 文档（`docs/graph-agent-gateway/mvp0/mvp0-alignment.md`
> "Runtime 行为" + "未知 route ID 抛结构化错误"）的**有意修订**，不是简单复旧。
> 修订**只作用于解析期（resolve-time）逐条 chain entry**：未配置 → 跳过。
> 执行期（execution-time）的错误分类（fail-fast vs fallback）**保持不变**。

#### Acceptance Criteria

1. When `resolve_role` 遍历 `fallback_chain`，遇到 `route_id` 不在 snapshot
   （`route is None`）、或 `route.status` 不在 `EXECUTABLE_ROUTE_STATUSES`、
   或 endpoint 缺凭证，the system shall **跳过该条目并继续下一条**，而不是抛
   `RegistryResolutionError`。
2. When 跳过任一条目，the system shall 记录一条 `logger.warning`，包含 `role_name`、
   被跳过的 `route_id` 与原因（移植旧 `config/llm_config.py:resolve_role` 的可观测降级，
   满足 logging 铁律）。
3. If 整条 `fallback_chain` 过滤后没有任何可执行路由，then `resolve_role` shall raise
   `RegistryResolutionError`，由 `ModelResolver.resolve` 映射为 `GatewayRoleNotConfiguredError`
   （`resolver.py:99`，**解析期**契约），而不是静默返回空。`AllProvidersFailedError`
   （`resolver.py:104`）**保留给执行期**——≥1 条路由解析成功、但 `GatewayChatModel` 调用时全部失败
   ——不用于解析期空链。（单一明确契约，便于 TDD 断言。）
4. When `model_override`（显式单路由）指向未配置路由，the system shall 仍按既有契约抛
   `[F-v3-gateway-role-not-configured]`（单点显式指定与多路由 fallback 链语义不同，不在本条放宽范围）。
5. The system shall 不引入按 provider/capability/price/latency 的动态选型；跳过仅基于
   "已声明的 chain 顺序中该条目当前是否可执行"。

### Requirement 3: 测试状态持久化为后端 SSOT（切 Tab/重启不丢）

**Objective:** 作为用户，我希望 role/copilot 的测试结果在切换 Settings Tab 或重启 App 后依然保留，
以便不必反复重测。

> **方向修正**：放弃 Gemini 草案的"状态提升（state elevation）"治标方案（只解决切 Tab、重启仍丢、
> 且制造前端并行真值源）。采用**写回后端 SSOT**治本方案。

#### Acceptance Criteria

1. When Role Test / Copilot Test 完成，the system shall 将每条路由的测试结论持久化到后端 SSOT
   （route 级状态沿用 `llm_credentials.json` 的 `provider_routes[].status`，并落盘足够的诊断
   信息以重建 UI 的 ready/unsupported 展示）。
2. When 前端进入 Copilot/LLM Roles 页面（含切 Tab 后重新挂载、或 App 重启后），
   the system shall 从后端读取测试状态来渲染就绪灯，而不是依赖组件内的易失 `useState`
   （`routeStatusOverrides` / `roleTestStates` 不再作为唯一真值源）。
3. When 同一路由被重新测试，the system shall 用新结论更新 SSOT，前端反映最新值。
4. The system shall 删除"前端内存态作为唯一真值源"的路径；前端覆盖态至多作为测试进行中的乐观显示，
   完成后以后端 SSOT 为准。

### Requirement 4: 远端服务化就绪形状（横切约束）

**Objective:** 作为平台维护者，我希望本次所有改动都"形状对齐远端多用户服务"，以便将来 LLM 配置/执行
搬到远端时不返工，同时现在不过度设计。

> 依据 [architecture-direction.md](./architecture-direction.md)：gateway/LLM 调用相关（含
> roles/credentials/test）未来远端服务化；studio skill 设计编译留桌面。本次"形状对齐、实现先本地"。

#### Acceptance Criteria

1. When 新增或修改 LLM 配置/测试相关的读写接口，the system shall 让接口签名预留
   `user_id`（或等价 owner 维度）参数位，即使当前实现以单一本地用户填充。
2. When 读写 roles/credentials/测试状态，the system shall 经由一个存储抽象边界（Storage seam），
   其当前实现为本地单文件，但调用方不得假设"本地单文件"这一具体形态。
3. The system shall **不**将任何 LLM 配置数据层逻辑实现进 Tauri Rust 层（与远端化冲突）。
4. The system shall **不**在本切片内引入 DB、KMS、加密存储或真实多用户认证（这些属远期独立 spec）。
5. The system shall 不新增任何加重"反远端债"的代码（如硬编码全局单用户路径、明文密钥的新写入点）。

### Requirement 5: 侧边栏过滤现状核实（原 Gemini 痛点 5 —— 经核实为误诊，撤回）

> **2026-06-01 代码核实**：Gemini 痛点 5 称"侧边栏过滤掉 `untested` 导致无法拖入测试"，**不成立**。
> `AvailableModelsSidebar.buildAvailableModelGroups`（`AvailableModelsSidebar.tsx:385`）当前已允许
> `ready` / `cooling_down` / `untested` 显示——"连通未测"的模型本就能拖入 fallback chain 测试。

#### Acceptance Criteria（核实结论，非待办）

1. `untested`（连通未测）模型**已**在侧边栏显示（`AvailableModelsSidebar.tsx:385`）；Requirement 3
   测试流的前置条件已满足，无需改动。
2. `needs_setup` 经核实**不是**"未测"，而是 `missing_key` / endpoint `failed` / route `failed`
   （`llm_state_projection.py:49`）——缺密钥或已失败的路由；侧边栏隐藏它**符合设计**（拖进 chain 也测不通，
   运行期由 Req 2 跳过）。
3. The system shall **不**为"放开 `needs_setup`"做改动（原 DEF-006 基于误解，已撤回）。若将来确有
   "重测此前 failed 路由"的精确需求，另立精确 scope，不整体放开 `needs_setup`。

### Requirement 6: WaveSpeed 协议边界诚实失败（支持项，任务延后）

**Objective:** 作为用户，我希望当 WaveSpeed（OpenAI 兼容）被以 Anthropic 协议接入并在 Copilot
SDK 调用失败时，得到清晰的降级提示，而不是被误导。

#### Acceptance Criteria

1. When `_probe_copilot_sdk_tool_call` 因 WaveSpeed 不支持 Anthropic `/messages` 而失败，
   the system shall 返回明确的、可读的协议不匹配/降级提示。
2. The system shall **不**在网关层做强制的 OpenAI↔Anthropic 协议翻译（推翻 Gemini 草案 REQ-6 中
   "100% 格式对齐"的表述；与 research.md 结论一致——诚实红灯，不引入不可控翻译开销）。

> 同样按近期范围排期延后，记录于 `docs/deferred-items.md`。

## Out of Scope（本切片明确不做）

- LLM 配置数据层 Rust 化（与远端化冲突，永久否决）。
- 接入 DB / KMS / 加密存储 / 真实多用户认证（远期独立 spec）。
- 状态提升（state elevation）作为测试状态方案（已被 SSOT 回写取代）。
- 动态意图路由 / 基于 capability 的自动选型（沿用 `mvp0-alignment.md` Non-Goals）。
- 第三方模型分类归一（Gemini 痛点 4）——延后，见 `docs/deferred-items.md`。

## Verification

- Backend：`uv run pytest`，新增 `test_role_save_unconfigured_route_success`（Req 1）、
  resolver 跳过/空链测试（Req 2）、测试状态 SSOT 回写/重读测试（Req 3）。
- Frontend：`npm run test`，更新受影响的 SettingsPage/CopilotTab/LlmRolesTab 测试
  （状态来源从内存改为后端，预期需**修改**测试而非"零回归通过"）。
- 人工：未配凭证下增删角色不报 400；测试亮绿后切 Tab + 重启 App 仍亮绿。
