---
ws_id: WS-2-authoring-workbench
doc: contract-gate
status: red-approved-green-ready
depends_on_requirements: requirements-ws2-authoring-workbench.md
date: 2026-06-08
gate_decision: 用户已在聊天窗口明确确认（2026-06-08）；SubgraphInline 单文件锁已授权；Workspace extraFiles 写盘返工单文件锁已授权
---

# WS-2 Authoring 工作台 — PM 契约门

本文件是 WS-2 在「实现前」的契约门记录。它把已批准的 RED 测试、锁定的 mvp1 裁决、
deferred 跨 WS 依赖、范围与验证命令固化下来，作为进入实现（GREEN）阶段的准入凭据。
所有判断只以 Studio MVP1 / engine MVP1 设计文档和 FROZEN 契约为准；当前代码、旧测试只
作为 drift / 诊断证据。**RED 已先失败；PM 契约门通过、且用户明确确认后才允许实现。**

## 1. 范围与文件归属（IR1）

WS-2 owns（见 requirements frontmatter `owns_files`）：

- `apps/studio/frontend/src/components/GraphCanvas/`
- `apps/studio/frontend/src/components/nodes/SkillNode.tsx`
- `apps/studio/frontend/src/components/edges/ContextEdge.tsx`
- `apps/studio/frontend/src/components/studio/panels/`
- `apps/studio/frontend/src/components/studio/SplitEditor.tsx`
- `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx`
- `apps/studio/frontend/src/api/client.ts`

禁止触碰：Settings/LLM、Copilot、backend run/golden/debug、Tauri writer、
`packages/graph-agent/**`、`packages/graph-agent-gateway/**`、`apps/studio/backend/**`
生产代码，以及除 §1.2 已授权 `SubgraphInline.tsx`、§1.3 已授权 `Workspace.tsx`
extraFiles 写盘接线外的 owns 之外前端实现。
范围外问题只登记 deferred（见 §5）。

> 注：当前分支 `codex/studio-mvp1-wave2` 工作区内另有一批 copilot/settings（WS-4/WS-5）
> 未提交改动，**不属 WS-2，本轮不提交、不修改**。

### 1.1 本轮契约门 / 交接提交白名单（commit/交接，IR1）

工作区高度混杂（含 WS-4/WS-5 copilot/settings/backend/tauri/sidecar 改动）。本轮契约门 / 交接
**只允许**提交/交接以下 7 个文件，其余一律不进本轮 commit：

- `.kiro/specs/studio-mvp1/contract-gate-ws2-authoring-workbench.md`（本文件）
- `.kiro/specs/studio-mvp1/task-ws2-authoring-workbench.md`
- `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.test.ts`
- `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.test.ts`
- `apps/studio/frontend/src/components/studio/Panels.test.tsx`
- `apps/studio/frontend/src/components/studio/SubgraphInline.test.tsx`
- `apps/studio/frontend/src/components/studio/panels/panel-files.test.ts`

**不含** `apps/studio/tests-e2e/**`（已确认零改动）、WS-5/Copilot/Settings、backend、Tauri、
sidecar 相关改动。`apps/studio/tests-e2e/` 已复核：无 tracked diff、无 untracked、conftest 撤销干净。

### 1.2 owns 边界裁决（R12/R13 GREEN 授权点）

R1–R11、R14–R15 的生产实现都落在 owns 内（`GraphCanvas/canvas-authoring.ts`、
`studio/panels/phase-frontmatter.ts`、`studio/panels/PropertiesPanel.tsx`、
`studio/panels/panel-files.ts` + `InputPanel.tsx`；`studio/Panels.tsx` 仅 barrel 转出 `./panels/index`）。

**例外**：R12/R13 的实现体 `apps/studio/frontend/src/components/studio/SubgraphInline.tsx`
（mock `entry/execute/return` rows + missing-path recovery 都在此）**不在 `owns_files` 内**
（owns 只含 `studio/panels/`、`studio/SplitEditor.tsx`、`studio/LazyMonacoPanel.tsx`）。
它由 owns 内的 `nodes/SkillNode.tsx` 渲染，但 SkillNode 仅传 props，无法在 owns 内消化 R12/R13。

→ **裁决结果**：用户已在聊天窗口明确确认 (a)，给 `studio/SubgraphInline.tsx`
单文件锁 / 扩 owns。GREEN 阶段允许仅为 R12/R13 修改该文件；R12/R13 不登记 deferred，
本轮 GREEN 目标为完整 **32 passed**。

### 1.3 owns 边界裁决（R3 extraFiles 真实落盘返工授权点）

R3 要求 LOGIC scaffold 同时生成 `actions/<name>.py`。`createPhaseDraft()` 的 `extraFiles`
由 `GraphCanvas/canvas-authoring.ts` 返回，但真实新建 phase 的写盘入口在
`apps/studio/frontend/src/components/studio/Workspace.tsx`，该文件不在原始 `owns_files` 内。

→ **裁决结果**：用户已在聊天窗口明确确认给 `Workspace.tsx` 单文件锁。GREEN 返工阶段允许
仅为 `draft.extraFiles` 真实写盘接线，以及该接线引入的 `doWriteSkillFile` hook dependency
lint 清理修改 `Workspace.tsx`；不得扩散到 Workspace 其它 authoring/run/settings/copilot 行为。

## 2. 锁定的 mvp1 裁决（grounding）

字段/行为以下述上位裁决为准（已逐条核实 SSOT 与 engine 代码）：

- **节点类型 = 文件名**（FROZEN `01-physical-layout` + `02_authoring.md`）：
  `SKILL.md`=agent、`LOGIC.md`=logic、`SUBGRAPH.md`=subgraph；作者**不写** `mode:`。
  旧 `mode` / `topology.mode` 不得作为类型真相源。
- **Agent / Logic 字段** = 继承 FROZEN（`05-agent` / `03-logic`）+ engine MVP1：
  - Agent 顶层 `name/llm_role?/validator?/io/tools?/subagents?/subgraphs?/references?/examples?/max_iterations?`；
    body 仅 `<role>×1 <goal>×1 <step>* <protocol>* <example>*`。**禁** `mode`、`<system_prompt>`、`<exit_contract>`。
  - Logic `name/io/actions[≥1]/validator?`；body `<action>*`；action 为纯函数
    `def <action_name>(inputs) -> dict`。**禁** `mode`、`<python_callable>`、`def run(...)`。
- **Subgraph 以 Studio MVP1 D7/G2/GE3 为上位裁决**：源文件按本地 `path` 引用、无注册表、
  放松 io（不强制 1:1）。当前 engine AST/loader 的 `target_skill` + io 1:1 视为 **drift / deferred**（见 §5），WS-2 不在前端复制 engine resolver、也不为旧 loader 恢复 `target_skill`。
- **写入路径**：本地 source file 写入经 WS-1 native writer 契约（已落地：`lib/tauri.ts`
  `writeWorkspaceFile` + hash 冲突；`api/client.ts` Tauri 下走 native）。`graph/serialize`
  仅作 Python 纯序列化 compute，不作本地写盘真相源。

SSOT 指针见 requirements §2；engine 契约：`docs/engine/mvp1/` + 对应 mvp0 FROZEN 链接。

## 3. RED 测试清单（已先失败，IR3/IR4）

层级：**纯前端单测 / 组件测试 / 纯前端集成**（vitest，`renderToStaticMarkup`，无 jsdom）。
不 mock 本层核心事实源（native writer / SkillDetail / subgraph / I/O 数据均不被 mock 成假绿，IR：no-fake，对应 requirements §6.10）。

| # | 需求映射 | 文件 · 用例 | 杀掉的 MVP0 drift |
|---|---|---|---|
| R1 | §6.3 类型来源 | `GraphCanvas/canvas-authoring.test.ts` · derives phase ref node type from the file name, ignoring a misleading topology mode | `topology.mode` 当类型真相源 |
| R2 | §6.3 / serialize DTO | 同上 · derives an agent phase type from its SKILL.md file, not the stale topology mode "agent" | agent 被错位成 `logic` 进 serialize DTO |
| R3 | §6.2 脚手架 logic | 同上 · scaffolds a LOGIC.md as an mvp1 pure-action node | `mode:`/`<python_callable>`；action 非纯函数签名 |
| R4 | §6.2 脚手架 agent | 同上 · scaffolds a SKILL.md agent with mvp1 body | `mode:`/`<system_prompt>`/`<exit_contract>` |
| R5 | §6.2 脚手架 subgraph | 同上 · scaffolds a SUBGRAPH.md by local path | `mode:`/裸 `target_skill` |
| R6 | §6.4 白名单(序列化) logic | `studio/panels/phase-frontmatter.test.ts` · edits a logic node without emitting a mode field or a python_callable shell | 写回旧 `mode`/`<python_callable>` |
| R7 | §6.4 白名单(序列化) agent | 同上 · edits an agent node via role/goal body, never mode/system_prompt/exit_contract | 旧 prompt 壳作主编辑项 |
| R8 | §6.4 白名单(序列化) subgraph | 同上 · edits a subgraph node by local path, never a bare target_skill or mode | path 子图被误判 logic、写 `mode` |
| R9 | §6.4 白名单(渲染) logic | `studio/Panels.test.tsx` · renders an mvp1 logic phase without the legacy python_callable editor | 面板渲染 Python callable 编辑器 |
| R10 | §6.4 白名单(渲染) agent | 同上 · renders an mvp1 agent phase without legacy system_prompt/exit_contract editors | 面板渲染 System prompt / Exit contract |
| R11 | §6.4 / §6.5 白名单(渲染) subgraph | 同上 · renders an mvp1 subgraph phase by path, not a legacy target_skill editor | 面板渲染 Target skill、忽略 `path` |
| R12 | §6.5 subgraph path | `studio/SubgraphInline.test.tsx` · does not render hardcoded mock entry/execute/return rows | `SubgraphInline` mock 假数据 |
| R13 | §6.5 subgraph missing | 同上 · shows a workspace/assets recovery affordance when the child path does not resolve | 无 missing-path recovery 入口 |
| R14 | §6.6 I/O 真实数据 | `studio/panels/panel-files.test.ts` · does not fabricate an input/sample.json projection with no backing file on disk | 假投影 `input/sample.json`/`input/schema.json` |
| R15 | §6.6 I/O 真实数据 | 同上 · surfaces real workspace test-input files instead of a fixed sample | 不读真实 `.workspace/test_inputs` |

**旧 MVP0 测试处置（IR6/§4）**：

- 改写（旧断言锁 MVP0 → mvp1 RED）：`canvas-authoring.test.ts`、`phase-frontmatter.test.ts`、`studio/Panels.test.tsx`。
- 新增：`studio/SubgraphInline.test.tsx`、`studio/panels/panel-files.test.ts`。
- 复查后已 mvp1-clean、无需改：`edges/ContextEdge.test.tsx`（设计期占位、非 mock JSON）。
- 留待后续批次：`frontend/tests/e2e/canvas-v1.spec.ts`（旧 mock e2e），归 #9 / 旧测试清理批次，本轮不动。

## 4. 验证命令与结果（IR4）

```bash
cd apps/studio/frontend && npx vitest run \
  src/components/GraphCanvas/canvas-authoring.test.ts \
  src/components/studio/panels/phase-frontmatter.test.ts \
  src/components/studio/SubgraphInline.test.tsx \
  src/components/studio/panels/panel-files.test.ts \
  src/components/studio/Panels.test.tsx
```

结果：**15 failed | 17 passed (32)**。15 条 = 上表 R1–R15 RED，均因 mvp1 行为缺失而真实失败；
17 条 passed = 回归 / keep-green（连线/断连/序列覆盖冲突/invalid-yaml/subagents-by-path/AssetsPanel 等）。
前端 lint：已验证 0 errors / 0 warnings（含 `Workspace.tsx` 返工授权范围内的 hook-deps 清理）。

## 5. Deferred backend/engine drift（范围外，已登记，IR7）

以下为真实跑出来的一手证据，**不在 WS-2 修**（属 engine/backend），WS-2 仅消费/引用：

1. **engine 拒绝 subgraph `path`**：`SubgraphNodeAST`（`packages/graph-agent/.../manifest.py`，`extra=forbid`）报
   `target_skill Field required` + `path Extra inputs are not permitted`。Studio D7（path）落地需 engine 侧改契约。
2. **后端 canvas 序列化器不认保留入口字 `input`**：连线 serialize 返回
   `422 serializer_orphan: phase 'setup' depends_on unknown phase 'input'` → 真实连线当前不落盘。
   未经 MVP1 文档明确授权，**不做「前端去 input」workaround**（指令 #4）。
3. **`graph_topology` 发 `mode:"agent"` 与 serialize 请求 DTO 冲突**：DTO 只认 `logic/subgraph/skill`。
   （前端侧 R2 已对「agent 不得错位成 logic」的 DTO 正确性立 RED；后端 DTO 对齐属 deferred。）
4. **LOGIC action 签名**：mvp1 `def <name>(inputs) -> dict` 与当前引擎 `def run(...)` 不一致，纯 mvp1 种子编不过。

**e2e 例外说明**：本轮一度获批临时在 `apps/studio/tests-e2e/**` 写真实文件 e2e（#1/#7/#9）以取证据。
据用户最新指令，**真后端 e2e 暂停、不作 WS-2 验收门**；已写的 e2e/conftest/v0.3.0 seed 仅作诊断证据，
**已撤出本轮提交范围**（`apps/studio/tests-e2e/` 当前无改动）。#7 Editor conflict、#9 Playwright e2e
等 backend/engine MVP1 baseline 稳定后再开。

## 6. 退出标准映射（§8）

- [x] RED 先失败（15/15），PM 契约门通过、用户确认后才实现，GREEN 不削弱断言。
- [x] Canvas/Properties/Editor/I-O 的**前端可测目标行为**有 RED 覆盖（脚手架/类型来源/白名单/subgraph path/I-O 真实数据/serialize DTO）。
- [x] 写入走 WS-1 native writer 契约；无 FastAPI/Python 本地写盘回归（前端层）。
- [~] 真实文件 e2e（连线落盘真实 GRAPH.md、409 冲突文件态、窄视口）：**deferred**，因 backend/engine 未对齐 MVP1（§5）。
- [x] 未修改 Settings/LLM、Copilot、run/golden/debug、engine/gateway packages、backend 生产码。
- [x] 测试命令、外部契约 floating-draft 状态、deferred 范围、风险已记录（本文件）。

## 7. 实现（GREEN）阶段授权边界

PM 契约门通过后，实现仅允许：

- 在 owns 范围（含已授权的 `studio/SubgraphInline.tsx` 单文件锁、`Workspace.tsx`
  extraFiles 写盘返工单文件锁）把 R1–R15 转 GREEN：脚手架产出 mvp1 文件
  （含 logic 纯函数 action 文件并通过真实 create phase 路径写盘）、类型来源=文件种类、
  Properties/序列化白名单、subgraph path 渲染 + missing recovery、I/O 读真实数据。
- 不削弱任何 RED 断言；不 mock 本层核心事实源造假绿。
- 不碰 backend/engine/gateway/Tauri writer；§5 deferred 项保持 deferred，不在 WS-2 内强行绕过。

## 8. 交接（§12，契约门通过后给 Codex）

契约门通过后，据已批准 RED 写 `.kiro/specs/studio-mvp1/task-ws2-authoring-workbench.md` 并出 Gemini prompt，
必须含：owns_files、禁止触碰、验证命令（§4）、用户明确确认、backend 不适用说明、baseline 回写
（graph-authoring/phase-editing/conflict-overwrite/canvas/properties/input/editor，只写已验证现状）、
Codex 审与 PM 终审、§5 deferred 清单。Gemini 只能把已批准 RED 实现到 GREEN，不得删改 RED、不得扩到 WS-3/4/5。

## 9. PM 终审检查点（§11）

- RED 是否真实编码：文件驱动 authoring（前端层）、字段白名单、subgraph path、I/O 真实数据、serialize DTO、no-fake 边界 —— 已覆盖。
- 旧测试是否按 mvp1 清理 —— 已改写 3 / 新增 2 / ContextEdge 复查 clean / canvas-v1 留后续批次。
- 文件锁是否越界 —— 未越 owns；e2e 例外已撤回。
- baseline 回写诚实性 —— 待实现落地后回写，未做的 target 保持 target-design/deferred。
