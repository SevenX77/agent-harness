---
module: 12-inv-copilot-invocation
doc: baseline
status: drafted (降 stub — 现状详情已移 studio copilot 页)
---

# 12-inv-copilot-invocation — Baseline（现状 · stub）

> **本模块降 stub**。按第四轮判据（`module-disposition-revised.md` 行 45）：**gateway 库完全不感知 copilot**——它对 copilot 的唯一接触 = 解析一个叫 `copilot_chat` 的普通 role 成 route；copilot 怎么拿 route 用 `claude_agent_sdk` 真正调（session / env 注入 / 事件翻译 / 本地 fallback / 假测试）= **③a Studio 领域**，不是 gateway 调用层。
> **现状详情去向（原内容不丢，非删除）**：本模块原先详写的 copilot SDK 运行机制（`stream_query`/`get_or_create_session`/`build_options`/`make_session_key`/`_translate_sdk_message`/`_resolve_route_runtime`/假测试/base_url→env 注入/本地 fallback）已**整段移入** `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3.8「Copilot SDK 调用机制」（含全部代码行号）。本 stub 只保留 gateway 视角的接触点 + 指针。
> 目标设计见同目录 `mvp1-alignment.md`（同样为 stub + 指针）。

## gateway 视角现状（唯一接触点）

gateway 对 copilot 的全部现状职责，是被 `_resolve_copilot_runtime`（Studio 侧，读 credentials + roles 构造 registry snapshot，调 `resolve_role(snapshot, "copilot_chat", route_override=...)` 得有序 `ResolvedRoute` 列表，`apps/studio/backend/app/services/copilot.py:419`）调用一次 `resolve_role`（[[02-orch-role-resolution]]）。输出是 `ResolvedRoute` 列表，**不是** LangChain `BaseChatModel`。拿到 route 之后的一切都在 Studio，gateway 不参与。

| 现状代码 | 归属 | 说明 |
|---|---|---|
| `services/copilot.py:_resolve_copilot_runtime`（`:419`） | ③a 消费 ③b 编排 | gateway 唯一接触点：调 `resolve_role("copilot_chat")`。route 解析语义本属 [[02-orch-role-resolution]]/[[01-handoff-interface]]。 |
| `services/copilot.py:_ark_anthropic_base_url`（`:476`） | **③b 归一化原语（归属模块 03）** | ark base_url 去尾斜杠 / 截 `/api/v3` / 补 `/api/compatible`。按判据属 ③b base_url 归一化（[[03-orch-credentials-endpoints]]），非 copilot 资产。 |
| `services/copilot.py:_deepseek_anthropic_base_url`（`:485`） | **③b 归一化原语（归属模块 03）** | deepseek base_url 去尾斜杠 / 截 `/v1` / 补 `/anthropic`。同上，归属模块 03。 |
| `stream_query`(`:201`)/`get_or_create_session`(`:276`)/`build_options`(`:112`)/`make_session_key`(`:93`)/`_translate_sdk_message`(`:364`)/`_resolve_route_runtime`(`:449`)/`ViewContext`(`:78`) | ③a Studio 领域 | copilot SDK 调用 / session 缓存 / env 注入 / 事件翻译 / 本地 fallback。**详见 studio copilot 页** §3.8（原本模块内容移入处）。 |
| `routers/copilot.py:copilot_ws`(`:34`)/`test_copilot_role_sdk`(`:89`)、`routers/llm.py:_probe_copilot_sdk_tool_call`(`:2150`) | ③a Studio 领域 | HTTP/WS 适配壳（[[14-api-router]]）+ **假测试**（测试用 `AsyncAnthropic`、运行用 `ClaudeSDKClient`，测的 SDK ≠ 跑的 SDK）。详见 studio copilot 页 §3.4。 |

## 判据说明（为什么降 stub）

copilot 的 SDK 调用 / 测试 / session 绑死"这个 app 的实际调用方式"（应用加工四件事之③ 调用方式）。判定一句话——**"换个完全不同的 app 装上 gateway，这个能力还原样能用吗？"** 对 copilot SDK 调用 = **不能**（别的 app 不会用 `ClaudeSDKClient` 跑）→ ③a 应用。gateway 只保留"解析 `copilot_chat` route"这一 ③b 公共能力（且已属 01/02）。故本模块**无独立 gateway 职责，降 stub 并入 [[01-handoff-interface]]**。

## 待办/疑点（指针）

- 现状的 copilot 运行路径、base_url→env 注入、假测试、首条 route 兜底等完整现状逐步描述 + 行号，见 `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §3.5（接线工程清单）/§3.8（SDK 调用机制）。
- 两个 base_url 助手（`_ark`/`_deepseek`）的归一化规则归 [[03-orch-credentials-endpoints]]，目标随 base_url 归一化下沉 ③b 保存路径，下沉后删除 copilot 本地副本。
