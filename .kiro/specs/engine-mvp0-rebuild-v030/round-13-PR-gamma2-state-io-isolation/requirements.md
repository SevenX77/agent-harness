---
spec: engine-mvp0-rebuild-v030/round-13-PR-gamma2-state-io-isolation
phase: PR γ2 (State/IO Isolation)
owner: a2 主笔 / a1 audit
工程量: 35-45h
---

# PR γ2: State/IO Isolation Requirements

## §0 继承字段表 (Round 9/10/11/12 不动)
- **ModelResolverProtocol**: 签名及职责不动。
- **Agent AST**: `exit_contract` 移除不动，业务 `validator` 开关语意不动，中间件顺序不动。
- **CognitiveFlowMiddleware**: 接管 `finish_task` / `ask_clarification` 职责不动。
- **SkillResolverProtocol**: 按 `skill_id` 寻址、`target_skill` 必填、全量入口强制要求 Resolver、无默认 Fallback 行为不动。

## §1 业务诉求 (PM 视角)
- **显式 Input Funnel 过滤**: 引擎收到外部输入时，不再无脑接收所有字段，而是必须经过一次严格的漏斗（Input Funnel）。只有在 `GRAPH.md` 的 `io.inputs` 中显式声明过的字段，才允许进入图内部流转；未声明的冗余字段将被静默丢弃。
- **黑板上下文不交叉污染 (State Shape 规范化)**: 执行期的上下文将告别当前大杂烩的 `data` 字典，被清晰划分为三块物理不交叉的区域：
  - `data.inputs`: 存放经过 Funnel 过滤后的初始入参，执行期完全只读。
  - `data.phase_outputs`: 专门存放各个子节点 (Phase) 完成后经校验的输出。
  - `data.scratch`: 作为系统或内部工具的草稿本，存放不属于输入与输出的中间演算状态。
- **子图与子节点隔离执行**: 当一个 Agent 想要调用子图 (SUBGRAPH) 或子 Agent (subagent) 时，原有的所有临时数据（包括思考过程、内部草稿、前置状态）**绝对不允许**泄漏给子图。子图启动时，它的初始输入必须纯粹来源于父节点的显式传参或其自身的默认空状态。这确保了子图的黑盒性和可复用性。
- **Reference Reader 沙盒化**: 内置的 Reference Reader（用于长文本阅读的子工具）必须在完全隔离的沙盒中执行，不继承父级任何消息和数据，且拥有强制的独立超时（Timeout）机制。