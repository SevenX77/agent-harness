---
status: Draft
created: 2026-06-01
updated: 2026-06-01
owner: Studio Frontend + Tauri(Rust) + Engine
master_scope: Studio 画布唯一主文档，负责全部 canvas 功能（编辑态 + 运行态）
supersedes:
  - canvas-authoring-v1        # 已实现：连线反写 / 新建节点 / Properties 编辑（吸收为 REQ-3/9/10，需迁 Rust）
  - canvas-micro-topology-v1   # 运行态只读展开 / Nudge / Payload schema（吸收为 REQ-11..14）
cross_spec:
  - studio-feature-copilot-chat # L2 子图下钻要求 copilot per-skill 会话缓存（归该 spec）
engine_contract: docs/engine/mvp0/skill-spec/   # FROZEN，禁止偏离
---

# 需求规格 — 画布拓扑重构（Canvas Topology Redesign，画布主文档）

## 0. 定位

本 spec 是 Studio 画布的**唯一主文档**，负责全部 canvas 功能。它**吸收并取代**：
- `canvas-authoring-v1`（已实现：连线反写 GRAPH.md、右键新建节点、Properties 字段编辑）→ 收编为 REQ-3 / REQ-9 / REQ-10，状态 ✅已实现，**需迁 Rust**。
- `canvas-micro-topology-v1`（Draft：运行态只读节点内联展开、Nudge 计数、Payload schema）→ 收编为 REQ-11..14。

实现状态图例：🆕 新增 ｜ ✅已实现(需迁 Rust) ｜ ⏭️ 延后。

---

## 1. 背景与核心痛点
1. **横向挤压**：dagre `LR`，节点越加越宽，左右面板被挤瘪。
2. **接口锁死**：`onConnect` 禁 INPUT/OUTPUT 连线（数据模型其实已支持 `depends_on="input"`）。
3. **线太细**：1.5–2px，右键断开判定率极低。
4. **节点内部黑盒**：子图 / agent 步骤 / logic 动作 / 运行态执行细节均不可见。
5. **原点漂移 + 动画乱闪**。

---

## 2. 架构基石：统一文件变更管线（第一性原理）

> **[DECISION-CANVAS-01] 所有画布写操作走同一条 Rust 管线；写入与校验解耦。全量迁 Rust。**

1. **单一真相源**：画布只渲染文件状态（`GRAPH.md` / `SKILL.md` / `LOGIC.md` / `SUBGRAPH.md`），前端不维护独立画布数据模型。
2. **统一写入 = Rust**：连线、新建节点、属性编辑、步骤增删改序、全局属性——**全部**走同一组 Rust Tauri 文件命令，直接 `std::fs` 落盘，不经 Python sidecar。
3. **写 / 校验解耦**：写（Rust，快、本地、不做业务判断）与校验（引擎编译，Python graph-agent，按需）分离。
4. **FATAL 不前置阻断**：写永远落盘；编译按需暴露 `[F-v3-*]`；用户 / copilot 修复。
5. **全量迁 Rust（[DECISION-CANVAS-08]）**：authoring-v1 已落地的 Python 路径（`writeSkillFile` + `graph/serialize` HTTP + 前端 `js-yaml`）**迁移到 Rust 文件命令**。这是有成本的重写（已实现 + 已测代码），但收口为一条写路径。
6. **现状差距（需实现）**：Rust 层（`apps/studio/tauri/src/lib.rs`）当前**只有 OS 集成命令**，需新增 `read_skill_file` / `write_skill_file` / `serialize_graph` / `mutate_phase_body`；编译保留 Python；Web 态降级（回退 HTTP 或禁编辑）。

---

## 3. 功能需求

### A. 布局与视觉

**REQ-1 纵向拓扑布局** 🆕
- dagre `'LR'`→`'TB'`；INPUT/OUTPUT 固定在**图坐标系**顶 / 底（随画布滚动，**非视口 HUD**）；句柄 Target→Top、Source→Bottom。

**REQ-4 12px 隐形热区** 🆕
- 双层 SVG（底层透明 12px `pointer-events: stroke` + 顶层 2px `pointer-events: none`），或 React Flow 原生 `interactionWidth`。

**REQ-5 焦点驱动动画** 🆕
- 选中节点仅其**直接相邻**入 / 出边播放粒子动画，其余静默（不递归全图）。原点用 `getBezierPath` 中点 + `EdgeLabelRenderer` 锚定防漂移。

### B. 连线与拓扑

**REQ-2 黑板状态可视化连线 + i/o panel** 🆕
- 连线 = 执行依赖，**非字段接线**；字段按 `io.inputs` 从 `BlackboardState` 切片过滤（引擎为黑板模型）。
- 点连线原点 → i/o panel 显示该处状态机推断（上游 `io.outputs` 并集 + 全局 inputs），上游字段高亮。
- 点 phase 节点 → 显示前置黑板字段（上游高亮）→ 勾选纳入 `io.inputs` → 本 phase `io.outputs` → 是否落盘 artifacts。
- 删除原"`sourceType === targetType` 变红"（黑板模型无此语义）。

**REQ-3 拖拽改拓扑 → 写回 GRAPH.md** ✅已实现(需迁 Rust)
- `depends_on` 真相在 `GRAPH.md` 的 `<phase depends_on>`；连线加、删线移除；拒绝自依赖 / 重复 / global。
- 已由 authoring-v1 实现（Python `graph/serialize`）→ 迁 Rust `serialize_graph`。

### C. 节点编辑

**REQ-9 canvas 右键新建节点** ✅已实现(需迁 Rust)
- 空白右键菜单：New Logic / Agent / Subgraph Phase；生成唯一 id（`logic`、`logic-2`…）；写 phase 文件 + serialize GRAPH.md + 刷新。
- 已由 authoring-v1 实现 → 写文件改走 Rust。

**REQ-10 Properties 面板编辑 phase frontmatter（白名单）** ✅已实现(需迁 Rust)
- 单击节点 → Properties 编辑该 phase 文件 frontmatter 白名单字段，保存保留未知字段与正文。
- ⚠️ **白名单须对齐 FROZEN 契约**（authoring-v1 旧白名单已过时）：
  - logic：`name` / `io` / `actions` / `validator`（旧 `execute_steps` 作废）。
  - agent：`name` / `llm_role` / `validator` / `io` / `tools` / `subagents` / `subgraphs` / `references` / `examples` / `max_iterations`（旧 `prompt`/`user_prompt_template`/`agent_tools`/`model_override` 作废——业务 prompt 在 body `<role>`/`<goal>`）。
  - subgraph：按 `04-subgraph-md-spec.md`。
- 保存走 Rust `write_skill_file`。

### D. 下钻导航

**REQ-6 三层下钻** 🆕
- **L1 宏观**：input/output/phase 纵向全局图。
- **L2 子图下钻**：双击 subgraph → 切入**完整子 skill 工作台**（panel + canvas + copilot）+ 面包屑返回。跨 spec：copilot per-skill 会话缓存归 `studio-feature-copilot-chat`。
- **L3 编辑态步骤展开**：节点右缘 `+` handle 展开。agent=body `<step id name>`、logic=body `<action>`，**顺序由 body 标签决定**（非 frontmatter 数组）。右键节点删步骤 / hover 线 `+` / 右键线菜单新增 / 拖步骤到连线中央换序。走统一 Rust 管线（结构化写 body XML，非 regex）。

### E. 运行态可视化（吸收自 micro-topology）

**REQ-11 运行态只读节点内联展开** 🆕
- 运行完 / 挂起的 agent 节点点 `+` → 内联展开内部执行子树。**与 L3 共用展开 UI 组件，按 mode 区分**：编辑态(REQ-6 L3)可写源文件、运行态只读 trace。
- 渲染倾向：agent-loop 内部用 **LangSmith 风格竖向时间轴（纯 DOM）**，非 React Flow 连线图（见 research §6）。

**REQ-12 Nudge 计数 + 报错时间轴** 🆕
- Validator 重试节点标 `Nudge: 2/3`（红 / 黄徽章）；最终失败附 Error Stack 气泡。

**REQ-13 运行态 Payload Schema** 🆕
- 后端向前端推流微观执行事件的 Schema。候选 A 打平增量流 vs B 嵌套快照；MVP0 推荐 **B 快照覆盖**（前端简单、状态一致），见 research §6。必含 `parent_node_id` / `node_type`。

**REQ-14 运行态性能约束** 🆕
- 50+ 微观步骤时缩放 / 展开 FPS ≥ 30；嵌套深度 >3 的 Subgraph 展开顶层渲染 < 500ms（虚拟化 / DOM 重用）；超限退化为双击下钻。

### F. 全局与快捷

**REQ-7 空画布快捷** 🆕
- 单击空白 → `GRAPH.md` 全局属性 panel（`schema_version`/`name`/`description`/`io`/`llm_role`/`phases`）；双击空白 → editor 编辑 GRAPH.md。

**REQ-8 引擎侧运行时策略开关** ⏭️延后
- `state_compaction_summary` / `prompt_cache`（agent phase）/ `predict_risk_guard` 均为 **engine 未落地** 功能；studio 仅开关 UI。`prompt_cache` 加字段须改 FROZEN 契约。`predict_risk_guard` 等 predict 阶段真实预估再做。

---

## 4. 范围

**In scope**：全部画布交互（布局 / 连线 / 热区 / 动画 / 编辑态结构 / 运行态展开 / 下钻 / 全局属性）+ 统一 Rust 文件管线 + 黑板可视化 + 运行态 Payload schema 前端消费。

**Out of scope**（跨 spec / 引擎）：copilot 会话缓存实现（copilot spec）；引擎 `state_compaction`/`prompt_cache` 底层（engine）；运行态微观事件的**后端装配逻辑**（engine 侧 run_manager，本 spec 只定义前端消费的 schema 契约）。

---

## 5. 关键决策登记 (Decision Log)

| ID | 决策 | 原因 | 落点 |
|---|---|---|---|
| DECISION-CANVAS-01 | 统一 Rust 写管线，写校验解耦 | 一条写路径；本地快写；FATAL 后置可修 | §2 / research §3 |
| DECISION-CANVAS-02 | INPUT/OUTPUT 图坐标固定，非视口 HUD | 与 dagre TB 一致 | REQ-1 |
| DECISION-CANVAS-03 | REQ-2 黑板可视化，删类型相等校验 | 引擎黑板模型，字段按 io.inputs 切片 | REQ-2 |
| DECISION-CANVAS-04 | depends_on 真相在 GRAPH.md | 脚手架 + authoring-v1 确认 | REQ-3 |
| DECISION-CANVAS-05 | 步骤换序改 body `<step>`/`<action>` | FROZEN：顺序由 body 标签决定 | REQ-6 |
| DECISION-CANVAS-06 | 本 spec 为画布唯一主文档，吸收并取代另两份 | 全局统筹，避免抢同批文件 | §0 |
| DECISION-CANVAS-07 | §6 策略降级为可选，引擎未落地不做 | prompt_cache/compaction 属 engine | REQ-8 |
| DECISION-CANVAS-08 | 全量迁 Rust（含 authoring-v1 已实现 Python 路径） | 收口一条写路径 | §2.5 |
| DECISION-CANVAS-09 | 运行态/编辑态展开**共用 UI 组件**，按 mode 区分 | 避免重复造 UI | REQ-6/REQ-11 |
| DECISION-CANVAS-10 | 运行态 Payload 用 B 快照覆盖（MVP0） | 前端简单、状态一致 | REQ-13/research §6 |
| DECISION-CANVAS-11 | Properties 白名单对齐 FROZEN，废 authoring-v1 旧字段 | 旧白名单与引擎契约不符 | REQ-10 |
