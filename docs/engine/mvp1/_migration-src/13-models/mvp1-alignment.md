---
module: 13-models
doc: mvp1-alignment
status: drafted（Phase C 第 2 域,2026-06-03)
aligns_with:
  - ../00-architecture-overview.md（§4 模块 3）
  - ../../../../temp/2026-06-02-engine-gateway-interface-needs.md（第1趴 D1,权威)
---
<!-- 核对进度:已迁 9 块 / 未迁 0 块 / 2026-06-04 -->

~~# 13-models — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)

> **Tier**: 跨层接缝(LLM) | **Owns**: Graph Agent 侧拿模型的接缝 + reasoning 补丁 | **关键性质**: engine **不碰 provider 分支** | **Related**: 第1趴 engine↔gateway 接口(权威)· api §2 · 01-agent-loop

~~## 1. 定义~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)

models = Graph Agent 与"模型"之间的**接缝**。引擎对模型的**全部依赖 = 一个调用面** `ModelResolverProtocol.resolve(role) -> BaseChatModel`(第1趴结论);provider 异质性由 gateway 吸收,engine 不分 provider 写分支。

~~## 2. D1 双模(已拍板,正式收进 mvp1)~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)

| 模式 | 形态 | 现状 |
|---|---|---|
| **role 模式**(生产默认) | `resolve(role) -> GatewayChatModel`,gateway 编排 fallback/probe/熔断/route 归属 | ✅ live |
| **直连/兼容模式**(让 Graph Agent **脱离整套 gateway** 被外部独立采用) | (a) 传现成 `BaseChatModel`;(b) 传参数 spec → engine 用原生 **`init_chat_model`** 现造 `ChatX` | (a) ✅ `chat_model` 注入短路已部分存在;(b) ❌ 待建 |

- 两模式都**收敛成"一个 `BaseChatModel` 交 `create_agent`"** → agent loop 一行不分叉。
- 直连模式**不承载** gateway 编排(fallback/probe/熔断)——这是它"简单"的代价,也是和 role 模式的本质区别;可用性由 user 自负。
- `reasoning_patch`:♻️ 兼容补丁,沿用。

~~## 3. 设计决策基础(用户原话)~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)

> 第1趴 D1:"接口做成双模:role 模式(用我们的 gateway)…直连模式(兼容接口,给不用我们 gateway 的人)…目的是让 graph-agent 能脱离我们整套 gateway/registry 独立被外部采用。"

~~## 4. 决策 + 动机~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)

| ID | 决策 | 动机 |
|---|---|---|
| MD1 | engine 只认 `BaseChatModel`(model-first),不要 route-first | route-first 是 Copilot 的事,不强加给 engine(第1趴 D1) |
| MD2 | 直连模式 = Graph Agent **对外可独立采用**的关键 | 产品边界:脱离 gateway 也能跑 |
| MD3 | engine 不碰 provider 分支 | role 模式由 gateway 吸收;直连模式 user 自负可用性 |

~~## 5. 测试关键点~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)

1. `resolve() -> BaseChatModel` 契约稳定(`create_agent` 的 `model=` 吃它)。
2. **直连模式 standalone**:不 import gateway 也能用 `init_chat_model` 造 ChatX 跑通。
3. **D-test-3**:`create_agent(model=GatewayChatModel)` 端到端 usage / thinking blocks / tool-call metadata 不丢(承 01 + uncovered-areas)。

~~## 6. 涉及 region / platform~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)

engine 走进程内 DI(`ModelResolverProtocol`),不走 HTTP;gateway 是独立子系统(第1趴),engine 只读其 `resolve()` 调用面。

~~## 7. gaps / 待设计~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)

1. 直连模式 `init_chat_model`(参数 spec → ChatX)实现(kiro)。
2. D1 双模之前只在 temp 第1趴,本域正式收进 mvp1;predict mock(D2)归 predict 域。

~~## 交叉引用(链接,不复制)~~ → ✅[已迁入](../../02-mechanism/06-seam/01-models/mvp1-alignment.md#1-定义)
00-architecture-overview §4 · 第1趴 engine-gateway-interface-needs(D1) · api-engine-studio-contract §2 · 01-agent-loop · predict 域(D2,待 Phase C)
