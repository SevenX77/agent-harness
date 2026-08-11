---
milestone: MVP1
status: drafted（现状记录 + 给 engine designer 的提示词,待用户转发）
verified_at: 2026-06-06
owner: engine 模块设计师(predict 重设计归 engine)
module: predict-migration-to-engine
doc: migration-note
workflow_axis: N/A（gateway MVP1 是库/公共能力模块,无独立用户旅程 workflow 文档）
binds_design: ./README.md · ./DESIGN_UNITS_INDEX.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/call/predict.py:PredictGatewayChatModel/_generate · packages/graph-agent-gateway/src/graph_agent_gateway/call/protocol.py:PredictContext/resolve_generation/ModelResolverProtocol/resolve · packages/graph-agent-gateway/src/graph_agent_gateway/call/resolver.py:ModelResolver/resolve · apps/studio/backend/app/services/predictor.py:PredictorService/dispatch_predict_job/PredictDeadlockError
units: [predict-migration-to-engine]
aligns_with: ./README.md（M4 predict scope） · ./DESIGN_UNITS_INDEX.md（predict-migration-to-engine）
---

# Predict:从 Gateway 移交 Engine

> **Tier**：predict 的 **mock/模拟 = 业务逻辑 → 移交 engine（out of gateway scope）**；gateway 只留 **role→route 编排（③b 公共）**。本文不是 baseline+alignment 模块对，是"现状+证据 + 给 engine 设计师的提示词"。
> **Owns（gateway 侧仅此一句）**：gateway 只输出编排结果（route），**不承载 predict 的 mock 业务逻辑**；迁移后 gateway 删 `PredictGatewayChatModel` / resolver 的 predict 特判 / `PredictContext` 协议位。
> **Status**：决策已定（mock 移交 engine）；engine 侧重设计归 engine designer（提示词见下，待用户转发）；**gateway 侧待办本期不动**，等 engine 方案定了再按其接口边界删除。
> **Related**：[[01-handoff-interface]]（gateway 迁移后只暴露 role→route 一等 API）· [[02-orch-role-resolution]]（role→route 编排，predict 删除后这条保持纯净）· [[09-inv-invocation-runtime]]（`GatewayChatModel` 正常调用层，predict 特判从 resolver 摘除后不影响它）
> **决策日志**：client 层 A' 重设计决策（**完整逻辑 + 用户原话见本文 §4，本文留底**）—— M4（`PredictGatewayChatModel` 是什么 + 架构问题：mock=业务逻辑应移交 engine；predict 重设计归用户/engine = out of scope）；归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md:58`（predict-migration：mock=业务逻辑→engine；role→route 公共，不变）。**M4 的「编排/调用分离」根源 = D2（跨模块共享）**，另见 [[01-handoff-interface]]（route 级一等 API）/ studio copilot（copilot SDK 调用 = ③a，见 copilot-assist + ux-spec §3.8）（copilot 同源「调用方自己调」）。
> 决策(用户):predict 的过度设计要去掉,功能交给 engine。本文 = 现状+证据 + 一段可直接转发给 engine 设计师的提示词。
> Gateway 侧只保留一条原则:**gateway 只输出编排结果(route),不承载 predict 的 mock 业务逻辑**。

## 1. 定义

predict 是 **skill（`graph_agent`)的「干跑模拟」**：不调真 LLM，用 mock 顶替每个 phase 的生成，产出 phase 执行路径并和期望路径 diff，供 skill 作者验证路由。**与 copilot 无关**（copilot 是 `claude_agent_sdk` 独立运行时，不跑 skill phase 图）。

**判据归属**：mock「怎么出结果」是**业务逻辑**（绑死 predict 这个 engine 能力），不是 gateway 机制衍生的公共能力——换个 app 装上 gateway，它不需要"假装是模型吐 mock"这个分支 → **业务逻辑归 engine**。gateway 唯一保留的是"role→route 编排"（任何 app 都要、③b 公共）。

## 2. 现状(代码证据)

predict 是 **skill(graph_agent)的「干跑模拟」**:不调真 LLM,用 mock 顶替每个 phase 的生成,产出 phase 执行路径并和期望路径对比。**与 copilot 无关**(copilot 是 claude_agent_sdk 独立运行时)。

| 关注点 | 代码 |
|---|---|
| mock 协议 | `protocol.py:14-21` `PredictContext.resolve_generation(phase, role, messages) → (payload, mocked_source)` |
| **塞进 gateway 的 mock model** | `call/predict.py:17,34-55` `PredictGatewayChatModel`(subclass `GatewayChatModel`,`_generate` 不调 provider,直接返回 mock) |
| resolver 里的 predict 特判 | `resolver.py:119-134`(`predict_context` 存在时返回 `PredictGatewayChatModel`) |
| predict 编排服务 | `apps/studio/backend/app/services/predictor.py:41-128`(`predict_skill` + `mock_llm` + `path_diff` + 死锁守卫) |

## 过度设计问题

`PredictGatewayChatModel` 把「mock 怎么出结果」这种**业务逻辑**塞进了 gateway 的 model 类里,违反编排/调用分离:gateway 应只回答「该用哪条 route」,不应内置一个「假装是模型、吐 mock」的分支。`resolver.resolve` 还得为 predict 特判返回不同类型。

## 3. 接口契约

> 迁移**后**的目标边界：gateway 对 predict 只暴露 role→route，predict 的 mock 注入全在 engine。下表钉死"engine↔gateway"那条缝。

| 边界 | 契约（迁移后目标） |
|---|---|
| **engine predict → gateway（唯一需要）** | engine 跑 predict 时，向 gateway 要"解析好的 route"= `resolve_routes(role)`/`resolve(role)`（[[01-handoff-interface]]/[[02-orch-role-resolution]]）。gateway **只**返回 route/编排结果，**不返回**任何 predict 专用 mock model。 |
| **mock 注入点（engine 内，gateway 不感知）** | mock「怎么出结果」（原 `PredictContext.resolve_generation(phase, role, messages) → (payload, mocked_source)`）的注入位置 = **engine 自己决定**（skill 运行器调 model 前短路 / engine 级 mock model）。gateway 不持有 `PredictContext` 协议位。 |
| **gateway 删除项（engine 接口定后执行）** | ① `PredictGatewayChatModel`（`call/predict.py`）；② `resolver.py:119-134` 的 predict 特判（`resolve` 不再因 `predict_context` 返回不同类型）；③ `protocol.py:PredictContext` 协议位。删除后 `ModelResolver.resolve` 返回类型恒为 `GatewayChatModel`（无 predict 分叉）。 |
| **不变项（gateway 编排保持纯净）** | role→route 一等 API（[[01-handoff-interface]]）+ `GatewayChatModel` 正常调用层（[[09-inv-invocation-runtime]]）不受影响；predict 特判摘除是"减一个分叉"，不改正常路径。 |
| **归属 / 稳定性** | predict mock = engine 业务逻辑（不在 gateway 包）；gateway 只留 role→route（③b 公共）。接口需求由 engine designer 提出，gateway 据此暴露最小 role→route API。 |

## 4. 设计决策基础（用户原话）

> **M4 — predict mock 是业务逻辑，不该写在 gateway**（client 层 A' 重设计决策，本文留底）。**架构问题（决策记录、A' 本期不处理）**：mock「怎么出结果」是**业务逻辑**，不该写在 gateway 的 model 类里；按编排/调用分离（D2），gateway 只输出编排结果（route），mock 应在 predict 流程自己做。用户原话：
> > "predict完全不调用llm 的话为什么要把逻辑写在gateway呢? 这是业务逻辑, 应该在跑predict流程里面自己mock就好了 ... anyway 这不归你管"
> → mock 移出 gateway、回到 predict 流程自己做；predict 重设计归用户/engine，gateway 本期不动、等接口边界定了再删。**A' 决策**：本期不碰 predict（其 `_generate` 全自走、不经 dispatch），只需保住 `GatewayChatModel` 类 + 构造器 + `bind_tools`，predict 自动不变。

> **M4 — 是什么 + 架构问题**（client 层 A' 重设计决策，本文留底）：`PredictGatewayChatModel` 是 skill（`graph_agent`)的「干跑模拟」，**不调真 LLM**，用 `predict_context.resolve_generation` 出 mock，产 `predict_trace` + `path_diff`；**不是 copilot**（copilot = `claude_agent_sdk` 独立运行时，不跑 skill phase 图）。证据：`call/predict.py:17`（subclass `GatewayChatModel`）、`:34-55`（mock `_generate`，不调 provider）、`protocol.py:14-21`（`resolve_generation`）、`apps/studio/backend/app/services/predictor.py:41-128`（`predict_skill` + `mock_llm` + `path_diff` + 死锁守卫）。架构问题：mock 是业务逻辑，不该写在 gateway 的 model 类里。

## ✂️ 给 engine designer 的提示词(可直接转发)

```
背景:graph_agent(skill engine)有一个 predict / 干跑模拟能力——不调真 LLM,用 mock 顶替每个 phase 的生成,
产出实际 phase 执行路径,并和期望路径 diff,用于 skill 作者验证路由。

当前实现把 mock 逻辑塞在了 LLM gateway 里:
- gateway 的 `PredictGatewayChatModel`(call/predict.py)是一个「假装是 chat model、_generate 直接吐 mock」的类;
- gateway 的 resolver 要为 predict 特判返回它;
- mock 内容由 `PredictContext.resolve_generation(phase, role, messages)`(protocol.py)提供;
- engine 侧编排在 services/predictor.py 的 predict_skill(mock_llm=...)。

我们(gateway 侧)的方向决策:gateway 只负责「编排」——输入 role、输出该用哪条 route;**不承载 predict 的 mock 业务逻辑**。
所以希望把 predict 的 mock/模拟能力收回 engine 自己拥有。

请你作为 engine 设计师判断与设计(开放问题,不预设答案):
1. predict 的 mock 应该在 engine 的哪一层注入最合理?(skill 运行器在调用 model 前短路?还是一个 engine 级的 mock model?)
2. 你之前设计过 predict「几层拿结果」的方式(其中有需要 copilot 预测结果的)——这套分层应该如何在 engine 内表达,gateway 只需对外提供「解析好的 route」即可满足吗?
3. engine 拿 mock 后,还需要 gateway 提供什么?(只要 route?还是别的?)把这个接口需求提清楚,gateway 侧据此只暴露「role→route」编排 API。
4. 迁移后 gateway 侧应删除哪些(PredictGatewayChatModel / resolver 的 predict 特判 / PredictContext 协议位)?给出你期望的接口边界。

目标:predict 的业务逻辑全部回到 engine;gateway 回归纯编排,不再有 predict 专用 model 类。
```

## 6. 测试关键点（gateway 侧 · 迁移后）

> predict 自身的 mock / path_diff 测试归 engine；gateway 侧只测"摘除 predict 特判后正常路径不回归 + role→route 保持纯净"。

- **resolver 无 predict 分叉**：删 `resolver.py:119-134` 特判后，`ModelResolver.resolve(role)` 返回类型恒为 `GatewayChatModel`（不再因 `predict_context` 返回 `PredictGatewayChatModel`）；正常调用路径不受影响。
- **role→route 纯净**：[[01-handoff-interface]] 的 `resolve_routes`/`resolve` 不含任何 predict 专用字段/分支；engine predict 拿到的就是普通 route。
- **不回归 copilot/正常调用**：摘除 predict 是"减一个分叉"，`GatewayChatModel._generate` 正常 fallback/probe/usage/metadata（[[09-inv-invocation-runtime]]）行为不变。
- **（engine 侧，仅指针）** mock 注入 / `path_diff`（期望 vs 实际 phase 路径）/ 死锁守卫的测试归 engine（`services/predictor.py`），gateway 不测。
- **删除完整性**：迁移落地后，gateway 包内不再 import/定义 `PredictGatewayChatModel` 与 `PredictContext`（grep 应为空）。

## 涉及 region / platform

- **engine**（`graph_agent` + `apps/studio/backend/app/services/predictor.py`）：predict mock/模拟/path_diff 的归宿，重设计归 engine designer。
- **③b gateway** `packages/graph-agent-gateway`：迁移后只留 role→route（`resolver.py`/`registry/resolver.py`）；删除 `call/predict.py` + resolver predict 特判 + `protocol.py:PredictContext`。
- **② Rust**：N/A。

## Gateway 侧待办(engine 方案定了再做,本期不动)

- 删 `PredictGatewayChatModel` + `resolver.py:119-134` predict 特判 + `protocol.py:PredictContext`(按 engine 给的接口边界)。
- 编排 API 保持「role→route」纯净。

## 交叉引用（链接，不复制）

- [[01-handoff-interface]]：迁移后 gateway 只暴露 role→route 一等 API（predict 拿这个）
- [[02-orch-role-resolution]]：role→route 编排（predict 特判删除后保持纯净）
- [[09-inv-invocation-runtime]]：`GatewayChatModel` 正常调用层（不受 predict 摘除影响）
- **client 层 A' 重设计决策 M4（§6 out-of-scope）**：完整逻辑 + 用户原话见本文 §4（本文留底）；M4 的编排/调用分离根源 = D2，共享见 [[01-handoff-interface]] / studio copilot（copilot SDK 调用 = ③a，见 copilot-assist + ux-spec §3.8）。归属表 `docs/graph-agent-gateway/mvp1/module-disposition-revised.md:58`
