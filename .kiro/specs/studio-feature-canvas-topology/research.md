---
status: Draft
created: 2026-06-01
updated: 2026-06-01
owner: Studio Frontend + Tauri(Rust) + Engine
related_requirements: .kiro/specs/studio-feature-canvas-topology/requirement.md
engine_contract: docs/engine/mvp0/skill-spec/   # FROZEN
absorbs:
  - canvas-authoring-v1/design.md
  - canvas-micro-topology-v1/research.md
---

# 画布拓扑重构调研（Canvas Topology Redesign Research，主文档）

本调研支撑 requirement.md 全部 REQ，并吸收 `canvas-authoring-v1`（编辑态，已实现）与 `canvas-micro-topology-v1`（运行态，调研）的技术结论。现状结论均有 `file:line` 依据。

---

## 1. 纵向布局
- `src/lib/layout.ts:31` `rankdir: 'LR'` → `'TB'`；IO 节点固定图坐标顶 / 底（随滚动，非视口）；句柄 Target→Top、Source→Bottom。
- **已删**原 §1.2 直线消弯（与原点 bezier 中点定位自相矛盾），统一默认 path + label 中点。

## 2. 黑板状态可视化（取代类型校验）
- 引擎黑板模型：`docs/engine/mvp0/public-api-contract.md:128` `BlackboardState{data,flow,messages,run_id}`；phase 进出发完整 `{inputs,phase_outputs,scratch}`（`execution-runtime/logic-explained.md:92`）。
- FROZEN：`io.inputs`=从黑板切片，`io.outputs`=回写黑板边界（`03-logic-md-spec.md:38-43`）。**无两端相等语义**。
- 状态机推断（前端可算）：沿 `depends_on` DAG 累积上游 `io.outputs` 并集 + 全局 inputs = 该点黑板可用字段。点原点 / 节点高亮 + 勾选过滤。

## 3. 统一文件变更管线（全量迁 Rust）

### 3.1 现状（已核实）
- Python 是 sidecar：`apps/studio/tauri/src/sidecar.rs` 子进程 + TCP 健康轮询。
- Rust `apps/studio/tauri/src/lib.rs` 当前 `#[tauri::command]` 仅 OS 集成（`open_in_cursor`/`reveal_in_file_manager`/`select_directory`…），**无 skill 文件读写**。
- 当前写路径（authoring-v1 已实现，待迁移）：`writeSkillFile` + `POST /api/skills/{id}/graph/serialize`（`backend/app/routers/skills.py:122`）+ 前端 `js-yaml`；`src/lib/tauri.ts` 仅桥 OS 动作。

### 3.2 目标管线
```
变更 → Rust std::fs 直写 GRAPH.md/SKILL.md/LOGIC.md → 前端重读重渲染 → 按需引擎编译(Python) 暴露 [F-v3-*] → 用户/copilot 修
```
需新增 Rust 命令：`read_skill_file` / `write_skill_file` / `serialize_graph`（`<phase depends_on>` 序列化）/ `mutate_phase_body`（步骤增删改序）。

### 3.3 authoring-v1 → Rust 迁移清单（已实现代码，需重写写入侧）
| 已实现件 | 现路径 | 迁移动作 |
|---|---|---|
| frontmatter 读写 | `src/components/studio/panels/phase-frontmatter.ts`（js-yaml） | 解析可留前端；**写**改 Rust `write_skill_file` |
| graph serialize client | `src/api/client.ts serializeSkillGraph` → HTTP | 改 Rust `serialize_graph` |
| authoring helper | `src/components/GraphCanvas/canvas-authoring.ts` | 生成 refs 逻辑保留；落盘改 Rust |
| 连线 / 新建 / 属性保存编排 | `Workspace.tsx` | 写步骤换 Rust 命令，刷新逻辑不变 |
- 编译 / 校验仍 Python（FROZEN `[F-v3-*]`）。Web 态降级回退 HTTP 或禁编辑。

### 3.4 depends_on 真相（已确认）
`backend/app/services/skills.py:62` GRAPH.md 模板 `<phase depends_on="input" output>init</phase>`——depends_on 在 GRAPH.md body，不在 phase frontmatter。`depends_on="input"` 合法 → INPUT 锚点本就支持，解锁仅去前端 guard。

## 4. 热区 / 焦点动画 / 原点
- 12px 透明 `pointer-events: stroke` 双层 SVG，或原生 `interactionWidth`。
- 焦点：仅直接相邻边激活，不递归全图。
- 原点：`getBezierPath` `(labelX,labelY)` + `EdgeLabelRenderer`（容器 `pointer-events:none`、按钮 `all`）。

## 5. 编辑态步骤增删改序（FROZEN 契约）
- logic（`03-logic-md-spec.md`）：frontmatter `actions:` 仅注册；body `<action>` 决定顺序(:64)。新增需 body+注册+`actions/<name>.py`，否则 `[F-v3-logic-action-not-found]`；删除保持 `actions:` 非空。
- agent（`05-agent-md-spec.md`）：body 顶层 `<step id name>`(:48)，id `^[A-Z][A-Za-z0-9_-]*$`，禁 `<steps>` 壳；删除查 `@step:` 引用否则 `[F-v3-mention-target-not-found]`。
- 经 Rust `mutate_phase_body` 结构化写（非正则）。

## 6. 运行态可视化（吸收自 micro-topology）

### 6.1 业内方案
- **n8n**：深嵌套 Subgraph 用**下钻 + 面包屑**（非内联），简化缩放 / DOM。
- **LangSmith**：纯竖向 Tree（Span 展开 Tool/LLM/Parser + 时长 / Token 角标），不用 DAG，多层嵌套性能好。
- **React Flow**：`parentId` + `extent:'parent'` 原生 Subflow（`>=12.10.2`）。
- **VS Code Outline**：折叠状态持久化（`workspaceState`）→ 展开状态必须记 localStorage，切 Tab / 重跑不回缩。

### 6.2 渲染决策（[DECISION-CANVAS-09]）
- agent-loop 内部（线性"思考→调工具→答复→校验"）用 **LangSmith 风格纯 DOM 竖向时间轴**，不强行画 React Flow 连线。
- 与编辑态 L3 **共用展开组件**，props 区分 `editable`（写源文件）/ `readonly`（读 trace）。
- 深嵌套 Subgraph：有限层内联，超限退化双击下钻（n8n 兜底）。

### 6.3 Payload Schema 决策（[DECISION-CANVAS-10]）
- 现状（已核实）：`backend/app/routers/runs.py` 有 `run()`/`predict()`；微观子步骤（`tool_call`/`nudge`）尚未装配成树推前端（颗粒度偏粗）。
- 候选 A 打平增量流：实时好、后端无状态；前端重组复杂、断线易乱。
- 候选 B 嵌套快照：前端简单、状态一致；带宽略费。
- **MVP0 选 B 快照覆盖**：`{phaseId,status,microSteps:[{stepId,type,status,nudgeCount?,details}]}`；必含 `parent_node_id`/`node_type`。后端装配逻辑归 engine，本 spec 定义前端消费契约。

### 6.4 性能
50+ 步 FPS ≥30；嵌套 >3 层顶层展开 <500ms（虚拟化 / DOM 重用）；Tauri 桥读本地文件防 Web 白屏。

## 7. 空画布快捷
单击 → GRAPH.md 全局属性 panel（`02-graph-md-spec.md`）；双击 → 编辑全文。保存走 Rust。

## 8. 进入 design 前待确认
1. Rust 写事务粒度（单文件 vs 多文件原子：新建 step 可能动 body+frontmatter+`.py`）。
2. 编译触发时机（即时 / 防抖 / 手动）。
3. Web 降级（回退 HTTP 保编辑 vs 只读）。
4. authoring-v1 迁 Rust 的回归测试策略（已有单测 / E2E 如何复用）。
5. 运行态快照下发频率 / 增量边界（纯快照大图带宽）。
