---
module: 12-inv-copilot-invocation
doc: mvp1-alignment
status: drafted (降 stub — 内容已移 studio copilot 页)
---

# 12 — Copilot Invocation（降 stub）· MVP1 设计

> **Tier**：⚠️ **降 stub**。gateway 对 copilot 的**唯一**职责 = `resolve_routes("copilot_chat")` 返回一条通用 route；**gateway 库完全不感知 copilot**。copilot SDK 调用 / session / 事件翻译 / 假测试 = **③a Studio 领域**（不在本模块）。
> **Owns**：仅"把 `copilot_chat` 这个 role 解析成有序 `ResolvedRoute`"——而这本就是 [[02-orch-role-resolution]]/[[01-handoff-interface]] 的能力，**本模块不再持有独立职责，并入 [[01-handoff-interface]]**。
> **Status**：本模块降为 stub；copilot 专属内容（`stream_query`/`get_or_create_session`/`build_options`/`_translate_sdk_message`/假测试/SDK env 注入/本地 fallback）**已移入 studio 文档**（`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3.4/§3.8/§6.3），正文在此只留指针，**非删除**。
> **Related**：[[01-handoff-interface]]（route 契约 + route 级 `resolve_routes` 一等 API，copilot 是其消费方，模块 12 并入此处）· [[02-orch-role-resolution]]（`resolve_role` 解析 `copilot_chat`）· [[03-orch-credentials-endpoints]]（两个 base_url 助手 `_ark`/`_deepseek` = ③b 归一化原语，归属此模块）
> **决策日志**：`.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md` D2（编排/调用分离，copilot 调用方自己调）+ D3（gateway 不含调用方式）+ `docs/graph-agent-gateway/mvp1/module-disposition-revised.md` 行 45（12 copilot = ③a 应用，降 stub 并入 01）+ ux-spec §6.3（copilot 四层，③b 只 resolve_routes + capability）
> **现状**：见同目录 `baseline.md`（同样已压成 stub + 指针）

## 1. 定义（stub）

**gateway 视角的 copilot = 一条叫 `copilot_chat` 的普通 role**。gateway 对它的全部职责是：调用方说"我要调 copilot"时，gateway 用 `resolve_routes("copilot_chat", model_override)` 返回一条（或多条 fallback）已解析、已归一化、可执行的 `ResolvedRoute`，**然后就结束了**。谁拿这条 route、用 `claude_agent_sdk` 怎么 spawn CLI、怎么注 env、怎么翻译事件、怎么本地 fallback、怎么测试——**gateway 一概不感知，也不应感知**。

**判据**（ux-spec §6.3 守边界检查）：copilot 的 SDK 调用 / 测试 / session 绑死了"这个 app 的实际调用方式"（应用加工四件事之③）→ ③a Studio 领域。换个 app 装上 gateway，它不会用 `ClaudeSDKClient` 跑 copilot → 故 gateway 不持有 copilot 调用逻辑。**"换个 app 还原样能用吗？"对 copilot SDK 调用 = 不能 → ③a。**

因此本模块**降为 stub 并入 [[01-handoff-interface]]**：route 级一等 API（`resolve_routes`）由 01 定义，copilot 只是它众多消费方之一，没有独立的"gateway copilot 模块"。本文只写文档目标，不改代码。

## 2. 数据流 / 机制（stub）

**gateway 侧（唯一职责）**：调用方 → `resolve_routes("copilot_chat", model_override)`（[[01-handoff-interface]]/[[02-orch-role-resolution]]）→ 有序 `ResolvedRoute[]`（含 `route_id/endpoint_id/protocol/base_url/credential_ref/provider_model_id/call_method_id/effective_runtime_settings`，字段权威源 [[04-orch-registry-schema]]）→ **交付完成**。

**③a Studio 侧（gateway 不感知，详见 studio copilot 页）**：拿 route → `_resolve_route_runtime` 取 secret/base_url/env → `build_options` 写 `ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL` 到 `ClaudeAgentOptions.env` → `get_or_create_session` 建/复用 `ClaudeSDKClient` → `stream_query` 遍历 route 调用 + 本地 fallback → `_translate_sdk_message` 把 SDK block 翻成 websocket event。**以上全部机制（含行号）见 `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3.8「Copilot SDK 调用机制」**，本模块不复制。

**覆盖代码（含覆盖率）**

| 覆盖项 | 归属 | 说明 |
|---|---|---|
| `apps/studio/backend/app/services/copilot.py:_resolve_copilot_runtime`（`:419`，解析 `copilot_chat` role → routes） | ③a 消费 ③b 编排 | gateway 唯一接触点：调 `resolve_role`/（目标）`resolve_routes`。**目标**：改走 [[01-handoff-interface]] 的一等 `resolve_routes` API，不再自己手装 registry snapshot。 |
| `apps/studio/backend/app/services/copilot.py:_ark_anthropic_base_url`（`:476`） | **③b 归一化原语**（归属模块 03） | ark 去 `/api/v3` 补 `/api/compatible`。按判据属 ③b base_url 归一化（[[03-orch-credentials-endpoints]]），随归一化下沉后 copilot 端不再各写一份。 |
| `apps/studio/backend/app/services/copilot.py:_deepseek_anthropic_base_url`（`:485`） | **③b 归一化原语**（归属模块 03） | deepseek 去 `/v1` 补 `/anthropic`。同上，归属模块 03。 |
| `stream_query`/`get_or_create_session`/`build_options`/`make_session_key`/`_translate_sdk_message`/`_resolve_route_runtime` | ③a Studio 领域 | copilot SDK 调用 / session / env 注入 / 事件翻译。**详见 studio copilot 页** §3.8，本模块不持有。 |
| `routers/copilot.py:copilot_ws`/`test_copilot_role_sdk`、`routers/llm.py:_probe_copilot_sdk_tool_call`（假测试） | ③a Studio 领域 | HTTP/WS 适配壳（[[14-api-router]]）+ 假测试修正。**详见 studio copilot 页** §3.4。 |

## 3. 接口契约

> 本模块降 stub，对外契约就是 [[01-handoff-interface]] 的 route 级 API；copilot 只是消费方。下表只钉死"gateway↔copilot"那一条缝。

| 边界 | 契约 |
|---|---|
| **③a copilot → ③b gateway（唯一调用）** | `resolve_routes("copilot_chat", model_override) → ResolvedRole`（有序 `ResolvedRoute[]` + skipped 诊断）。契约由 [[01-handoff-interface]] 定义；`model_override` = 精确 route override（fail-fast），fallback 链坏 route 逐条 skip（语义见 [[02-orch-role-resolution]]）。 |
| **③b → copilot 的 route（消费什么）** | 每条 `ResolvedRoute` 至少带 `route_id/endpoint_id/protocol/base_url（已 canonical）/credential_ref/provider_model_id/call_method_id/effective_runtime_settings`（字段权威源 [[04-orch-registry-schema]] `registry/schema.py:415-439`）。copilot 据此取 secret + 映射 SDK env，**gateway 不参与映射**。 |
| **eligible 判据（③a 问 ③b capability）** | ③a 判某 route 是否 copilot-eligible = 问 ③b"该 route 是否 anthropic-messages 兼容"（protocol/call_method：anthropic 原生 / deepseek-anthropic / ark-anthropic / openrouter-anthropic）。**gateway 只答 capability，不知"copilot-eligible"这个产品概念**。 |
| **gateway 不感知的（明确划界）** | SDK session / `ClaudeSDKClient` / env 注入 / 事件翻译 / 本地 fallback / 假测试 / `copilot_` 前缀分流 / 内置角色动态浮出 = **③a，gateway 全不感知**（ux-spec §6.3 守边界检查"库完全不知道 copilot 是什么"）。 |
| **base_url 归一化原语归属** | `_ark_anthropic_base_url`/`_deepseek_anthropic_base_url` = **③b 归一化（归属模块 03 [[03-orch-credentials-endpoints]]）**，不是 copilot 资产；目标下沉 gateway 包，保存时统一归一化。 |

## 4. 设计决策基础（用户原话）

> **D2 — 编排 / 调用分离（copilot 用例）**（决策记录 `:62-63`）："你只要知道谁跟你说我现在要调copilot, 把copilot解析好的route给我, 你就给他, 就ok了, 这是调copilot的路径,你只负责输出编排结果, 不负责调用。" → gateway 给 route，copilot 调用方（`claude_agent_sdk`）自己调；**这是模块 12 降 stub 的直接依据**。

> **D3 — gateway 不含实际调用方式**（决策记录 `:78`）："前端不归gateway管, 前端是studio的前端, gateway只管提供服务……要考虑复用其他app。" → copilot 用 Claude SDK 调是 studio 的"实际调用方式"（应用加工之③），不进 gateway 核心。

> **判据守边界（ux-spec §6.3）**："copilot 的 SDK 调用/测试/session 全在 ③a；③b **只** resolve_routes + capability。**库完全不知道 copilot 是什么**——它只解析一个叫 `copilot_chat` 的 role 的 route,谁拿去怎么用与它无关。" → gateway 模块 12 无独立职责，stub 化并入 01。

## 5. 决策 + 动机

- **模块 12 降 stub 并入 [[01-handoff-interface]]**：gateway 对 copilot 的全部能力 = route 级 `resolve_routes`，这本就是 01 的一等 API；copilot 不构成独立 gateway 模块。**被否的旧形态**：把 copilot 当成一个"gateway 调用层模块"详写 SDK 流程——错，那是把 ③a 调用方式塞进 ③b 文档。
- **copilot 专属内容移 studio，非删**：`stream_query`/session/env 注入/事件翻译/假测试是真实存在且重要的机制，只是归属 ③a；故迁入 `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3.4/§3.8/§6.3 留底（满足"原内容不丢"），gateway 这边只留指针。
- **两个 base_url 助手判给模块 03**：`_ark`/`_deepseek` 是 protocol 归一化规则，不是 copilot 业务；按 F1（base_url 归一化）应下沉 ③b 保存路径，归 [[03-orch-credentials-endpoints]]。copilot 现在各写一份 = 归一化未下沉的临时态，下沉后消除重复。
- **gateway 不引入"copilot-eligible"概念**：eligible = ③a 产品判据，gateway 只提供"anthropic-messages 兼容"这个客观 capability，由 ③a 据此判 eligible。这守住"③b 领域无关"。

## 6. 测试关键点（stub — gateway 侧）

> gateway 侧只测"`copilot_chat` route 能被正确解析"；copilot SDK 调用 / 真 SDK 测试 / `copilot_` 前缀 / 动态浮出的测试**全归 ③a**，关键点见 studio copilot 页 §3.7。

- **`copilot_chat` 解析**：`resolve_routes("copilot_chat")` 返回有序 `ResolvedRoute[]`，route 字段完整（base_url 已 canonical、credential_ref 可取 secret）——复用 [[02-orch-role-resolution]] 的跳过/override/空链语义，**不为 copilot 另写解析逻辑**。
- **gateway 不感知 copilot**：grep ③b 公共 API/包内 → **不得**出现 `ClaudeSDKClient` / `ANTHROPIC_BASE_URL` env 注入 / `stream_query` / copilot session / "copilot-eligible"（守边界检查 1，违反 = copilot 调用方式漏进 ③b）。
- **base_url 助手归 ③b**：`_ark`/`_deepseek` 归一化规则的单测随 [[03-orch-credentials-endpoints]] 走（每 protocol canonical 形状），不在 copilot 域测。
- **（③a 侧，仅指针）真 SDK 测试 / `copilot_` 前缀 / 未测也显示 / 动态浮出 / 本地 fallback**：见 `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3.7。

## 7. 涉及 region / platform

- **③b** `packages/graph-agent-gateway`：`resolve_routes`/`resolve_role`（解析 `copilot_chat`，能力本属 01/02）；两个 base_url 助手下沉后归 03。**本模块无独立 ③b 代码**。
- **③a** `apps/studio/backend`：`services/copilot.py`（SDK 调用 / session / env / 事件翻译 / 本地 fallback）、`routers/copilot.py`（ws/context/test 适配壳）、`routers/llm.py:_probe_copilot_sdk_tool_call`（假测试）。**copilot 全部实质逻辑在此**，文档归 studio copilot 页。
- **② Rust**：copilot **配置**= N/A；copilot **聊天 session 落盘**（D8）= Rust native-fs，属 skill 工作台 region，非本模块。

## 8. gaps / 待设计

- **待办（并入 01）**：copilot 改走 [[01-handoff-interface]] 的一等 `resolve_routes` API，不再让 `_resolve_copilot_runtime` 自己手装 registry snapshot；当前直接调 pure helper，见 `apps/studio/backend/app/services/copilot.py:419-437`。
- **待办（归 03）**：`_ark_anthropic_base_url`/`_deepseek_anthropic_base_url` 随 base_url 归一化下沉 ③b 保存路径；下沉后 copilot 端删除本地副本，route 拿到时已 canonical。
- **待办（归 studio + 14）**：假测试 `_probe_copilot_sdk_tool_call`（`AsyncAnthropic`）→ 真 `ClaudeSDKClient` 路径；`_resolve_copilot_route`（`copilot.py:445`）只取首条 route → 走全 fallback 链。详见 studio copilot 页 §3.4/§3.5。
- **疑点（归 studio）**：Copilot WS 是否暴露 route diagnostics = 产品可观测性取舍，归 [[01-handoff-interface]] 待办，不在 gateway copilot 域。

## 交叉引用（链接，不复制）

- [[01-handoff-interface]]：route 级 `resolve_routes` 一等 API（**模块 12 并入此处**，copilot 是消费方）
- [[02-orch-role-resolution]]：`resolve_role` 解析 `copilot_chat`（跳过/override/空链语义复用）
- [[03-orch-credentials-endpoints]]：`_ark`/`_deepseek` base_url 归一化原语归属此模块
- [[14-api-router]]：Copilot ws/context/test HTTP 适配壳 + 假测试修正
- **studio copilot 页**：`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3.4（真 SDK 测试）/ §3.8（SDK 调用机制，从本模块移入）/ §6.3（copilot 四层归属）
- 决策记录 `client-layer-decision-record.md` D2/D3 + 归属表 `module-disposition-revised.md` 行 45
