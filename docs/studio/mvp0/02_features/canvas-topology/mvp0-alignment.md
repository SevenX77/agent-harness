# canvas-topology — MVP0 对齐（Canvas Topology MVP0 Alignment）

> **结论**：**已对齐 ✅**。本 spec 为画布**唯一主文档**，已吸收并取代 `canvas-authoring-v1`（编辑态，已实现）与 `canvas-micro-topology-v1`（运行态，调研）。
> **主 spec**：[`.kiro/specs/studio-feature-canvas-topology/`](../../../.kiro/specs/studio-feature-canvas-topology/requirement.md)

---

## 0. 架构基石：统一 Rust 文件管线（全量迁 Rust）
**Rust `std::fs` 直写（不经 Python sidecar）→ 画布按文件重渲染 → 按需引擎编译(Python) 暴露 `[F-v3-*]` → 用户/copilot 修复（FATAL 不前置阻断）。**
authoring-v1 已实现的 Python 路径（`writeSkillFile`/`graph/serialize`/`js-yaml`）迁 Rust 命令；编译保留 Python；Web 态降级。

---

## 1. MVP0 全集（对齐 REQ）

| 组 | 目标 | REQ | 状态 |
|---|---|---|---|
| 布局视觉 | 纵向 TB 布局（IO 图坐标固定，非 HUD） | REQ-1 | 🆕 |
| 布局视觉 | 12px 隐形热区 | REQ-4 | 🆕 |
| 布局视觉 | 焦点驱动动画 + 原点锚定 | REQ-5 | 🆕 |
| 连线拓扑 | 黑板状态可视化 + i/o panel（删类型相等） | REQ-2 | 🆕 |
| 连线拓扑 | 拖拽改拓扑 → GRAPH.md depends_on | REQ-3 | ✅已实现(迁 Rust) |
| 节点编辑 | 右键新建 logic/agent/subgraph 节点 | REQ-9 | ✅已实现(迁 Rust) |
| 节点编辑 | Properties 编辑 frontmatter（白名单对齐 FROZEN） | REQ-10 | ✅已实现(迁 Rust) |
| 下钻 | L1 宏观 / L2 子图切完整工作台 / L3 编辑态步骤展开 | REQ-6 | 🆕 |
| 运行态 | 只读节点内联展开（LangSmith 竖向时间轴） | REQ-11 | 🆕 |
| 运行态 | Nudge 计数 + 报错时间轴 | REQ-12 | 🆕 |
| 运行态 | Payload Schema（选 B 快照覆盖） | REQ-13 | 🆕 |
| 运行态 | 性能（50+ 步 30fps / 嵌套 <500ms） | REQ-14 | 🆕 |
| 全局快捷 | 单击空白→GRAPH.md 全局属性；双击→编辑 | REQ-7 | 🆕 |
| 引擎策略 | state_compaction / prompt_cache / predict_risk_guard | REQ-8 | ⏭️延后(engine) |

---

## 2. 切出 MVP0（跨 spec / 引擎）
- copilot per-skill 会话缓存（L2 切回对话还在）→ `studio-feature-copilot-chat`。
- `state_compaction`/`prompt_cache` 底层 → graph-agent（gateway 层）。
- 运行态微观事件**后端装配** → engine run_manager（本 spec 只定义前端消费 schema）。

---

## 3. 对齐自检
- [x] 每 REQ 有 FROZEN 契约 / `file:line` 依据
- [x] 数据真相已核实（depends_on→GRAPH.md；步骤顺序→body XML；字段→io 切片）
- [x] 吸收另两 spec 全部能力，标注实现状态与迁 Rust 成本
- [x] Properties 白名单对齐 FROZEN（废 authoring-v1 过时字段）
- [x] 运行态 / 编辑态展开共用 UI 组件（按 mode 区分）
- [x] 延后项（REQ-8）明确归 engine
