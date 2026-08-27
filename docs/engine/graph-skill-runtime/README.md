---
doc: graph-skill-runtime-index
role: index
status: living
updated: 2026-08-27
---

# Graph Skill Runtime 文档索引

本文是 engine 独立发布议题的文档地图。它把“当前正在运行的契约”和“尚未实现的目标契约”分开，避免把未来设计误写成现有能力。

## 权威地图

| 要回答的问题 | 权威文档 | 状态与使用方式 |
| --- | --- | --- |
| 当前 `graph-agent` 代码、接口、Studio 配置和 MoirAI 集成已经做到什么 | [`baseline.md`](./baseline.md) | `drafted` baseline；以 `origin/main@3564b49e` 为核验截面，并与目标文档双向绑定 |
| 独立 Python runtime、SDK、CLI、portable skill 格式、executor 与 MoirAI 集成应当变成什么 | [`v1-alignment.md`](./v1-alignment.md) | `drafted` alignment；是本轮未来目标的权威正文，但尚未成为实现契约 |
| 当前 engine MVP1 的模块职责与接口设计 | [MVP1 文档索引](../mvp1/INDEX.md) | 当前设计阅读入口；独立拆仓完成前继续有效 |
| 当前实现接受的 skill 文件格式 | [FROZEN format ground truth](../skill-spec/00-FORMAT-GROUND-TRUTH.md) | 当前实现格式的唯一真相源；仍被代码与 contract maps 消费，本轮不修改、不降级、不替换 |
| 当前包的使用事实 | [`packages/graph-agent/README.md`](../../../packages/graph-agent/README.md) | 面向当前 `graph-agent` 0.3.1 的指南，不承诺未来 `gskill` 接口 |
| MoirAI 名字、人格和神话映射为何这样选择 | [MoirAI 命名与人格叙事](../../strategy/moirai-copilot-persona-narrative.md) | `living` guide；不承载能力状态或实现契约 |

## 两条契约线

**当前线**以 FROZEN format ground truth、engine MVP1 设计和活代码为准。当前 skill 根仍使用 `GRAPH.md`，phase 类型文件仍是 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md`，Studio 仍维护 `.workspace/runtime_config.json`。

**未来线**以 [`v1-alignment.md`](./v1-alignment.md) 为准。目标使用 `SKILL.md` 作为 Agent Skills 发现与调用入口，使用 `graph.yaml` 保存机器图定义，并将 agent phase 文件命名为 `AGENT.md`。这些决定目前都是 drafted，不能据此判断现有代码已经支持新格式。

未来线只有同时满足以下条件后才能接管当前线：实现完成；迁移与跨宿主验证通过；所有代码、contract maps、示例和文档引用重钉到新契约；旧格式在同一次切换中删除。切换前，任何调用者都不得绕过当前 FROZEN 契约，也不得维护双读格式。

## 状态标签

本目录正文使用以下语义标签：

- **当前事实**：可由指定基线提交的代码、配置或文档直接核验。
- **目标决定**：已经纳入 drafted v1 目标，但尚未实现。
- **建议**：实现阶段可采用的做法，必须经相应阶段验收验证。
- **待讨论**：缺少证据或需要产品裁决，不能当作默认决定。

