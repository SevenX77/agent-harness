---
ws_id: WS-2-authoring-workbench
doc: task
status: green-ready-approved
depends_on_requirements: requirements-ws2-authoring-workbench.md
depends_on_contract_gate: contract-gate-ws2-authoring-workbench.md
date: 2026-06-08
green_authorization: 用户已在聊天窗口明确确认（2026-06-08）；SubgraphInline 单文件锁已授权；Workspace extraFiles 写盘返工单文件锁已授权
---

# WS-2 Authoring 工作台 — 实现（GREEN）任务交接

本文件是契约门通过后给执行者（Gemini，Codex 审、PM 终审）的 GREEN 实现交接单。
唯一目标：把契约门已批准的 **R1–R15 RED 转 GREEN**，不删改 RED、不削弱断言、
不碰 backend/engine/Tauri，不扩到 WS-3/4/5。所有判断只以 Studio MVP1 / engine MVP1
设计文档与 FROZEN 契约为准（指针见 requirements §2、contract gate §2）。

## 1. 文件归属（owns_files，IR1）

WS-2 owns（requirements frontmatter）：

- `apps/studio/frontend/src/components/GraphCanvas/`
- `apps/studio/frontend/src/components/nodes/SkillNode.tsx`
- `apps/studio/frontend/src/components/edges/ContextEdge.tsx`
- `apps/studio/frontend/src/components/studio/panels/`
- `apps/studio/frontend/src/components/studio/SplitEditor.tsx`
- `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx`
- `apps/studio/frontend/src/api/client.ts`

**禁止触碰**：Settings/LLM、Copilot、backend run/golden/debug、Tauri writer、
`packages/graph-agent/**`、`packages/graph-agent-gateway/**`、`apps/studio/backend/**` 生产码，
以及除已授权 `SubgraphInline.tsx`、已授权 `Workspace.tsx` extraFiles 写盘返工外的 owns 之外一切前端实现。
范围外问题一律登记 deferred，不在 WS-2 内绕过。

### owns 边界例外（R12/R13 已授权）

R12/R13 的实现体 `apps/studio/frontend/src/components/studio/SubgraphInline.tsx`
**不在 owns_files 内**（owns 只含 `studio/panels/` 等）。它由 owns 内的 `nodes/SkillNode.tsx`
渲染，但 mock rows / missing-path recovery 逻辑都在 SubgraphInline.tsx 里，SkillNode 仅传 props。

用户已在聊天窗口明确确认给 `studio/SubgraphInline.tsx` 单文件锁 / 扩 owns。
GREEN 阶段允许仅为 R12/R13 修改该文件；R12/R13 不登记 deferred，本轮目标为完整
**32 passed**。

### owns 边界例外（R3 extraFiles 写盘返工已授权）

R3 要求 LOGIC scaffold 同时生成 `actions/<name>.py`。`createPhaseDraft()` 的 `extraFiles`
由 `GraphCanvas/canvas-authoring.ts` 返回，但真实新建 phase 的写盘入口在
`apps/studio/frontend/src/components/studio/Workspace.tsx`，该文件不在原始 `owns_files` 内。

用户已在聊天窗口明确确认给 `Workspace.tsx` 单文件锁。GREEN 返工阶段允许仅为
`draft.extraFiles` 真实写盘接线，以及该接线引入的 `doWriteSkillFile` hook dependency
lint 清理修改 `Workspace.tsx`；不得扩散到 Workspace 其它 authoring/run/settings/copilot 行为。

## 2. R1–R15 → 生产文件映射（GREEN 落点）

| RED | 目标行为（mvp1） | 生产落点（owns 内；R12/R13 和 R3 extraFiles 写盘为已授权单文件锁） |
|---|---|---|
| R1 | phase 节点类型由文件名推导，忽略 `topology.mode` | `GraphCanvas/canvas-authoring.ts` · `phaseRefsFromSkillDetail` |
| R2 | agent phase 从 `SKILL.md` 推为 skill，不被错位成 logic 进 serialize DTO | `GraphCanvas/canvas-authoring.ts` · 同上 + serialize DTO 接线 |
| R3 | `LOGIC.md` 脚手架 = 纯函数 action 节点（无 `mode`/`<python_callable>`，签名 `def <action>(inputs) -> dict`），并通过真实 create phase 路径写入 `actions/<name>.py` | `GraphCanvas/canvas-authoring.ts` · `defaultPhaseMarkdown`/scaffold；`studio/Workspace.tsx`（**已授权单文件锁，仅 extraFiles 写盘**） |
| R4 | `SKILL.md` agent 脚手架 = role/goal body（无 `mode`/`<system_prompt>`/`<exit_contract>`） | 同上 |
| R5 | `SUBGRAPH.md` 脚手架 = 本地 `path` 引用（无 `mode`、无裸 `target_skill`） | 同上 |
| R6 | 编辑 logic 节点不写回 `mode`/`<python_callable>` 壳 | `studio/panels/phase-frontmatter.ts` |
| R7 | 编辑 agent 节点走 role/goal body，不写 `mode`/`system_prompt`/`exit_contract` | 同上 |
| R8 | 编辑 subgraph 节点按本地 path，不写裸 `target_skill`/`mode` | 同上 |
| R9 | logic 面板不渲染 legacy python_callable 编辑器 | `studio/panels/PropertiesPanel.tsx`（经 `studio/Panels.tsx` barrel 暴露） |
| R10 | agent 面板不渲染 system_prompt/exit_contract 编辑器 | 同上 |
| R11 | subgraph 面板按 path 渲染，不渲染 target_skill 编辑器 | 同上 |
| R12 | subgraph inline 不渲染 mock `entry/execute/return` | `studio/SubgraphInline.tsx`（**已授权单文件锁**） |
| R13 | path 不可解析时显示 workspace/assets recovery 入口 | 同上（**已授权单文件锁**） |
| R14 | I/O panel 不投影不存在的 `input/sample.json`/`input/schema.json` | `studio/panels/panel-files.ts`（+ `InputPanel.tsx`） |
| R15 | I/O panel 展示真实 `.workspace/test_inputs` 文件 | 同上 |

GREEN 只做让上述行为成立的最小实现；不得为了过测 mock 本层核心事实源（native writer /
SkillDetail / subgraph / I/O 数据），不得弱化任何断言（no-fake，requirements §6.10）。

## 3. 验证命令（IR4）

```bash
cd apps/studio/frontend && npx vitest run \
  src/components/GraphCanvas/canvas-authoring.test.ts \
  src/components/studio/panels/phase-frontmatter.test.ts \
  src/components/studio/SubgraphInline.test.tsx \
  src/components/studio/panels/panel-files.test.ts \
  src/components/studio/Panels.test.tsx
```

- GREEN 前基线：**15 failed | 17 passed (32)**（R1–R15 RED 真实失败）。
- GREEN 验收：SubgraphInline 已授权，目标 **32 passed**。
- 不得动其余 17 条 keep-green 回归用例的断言。
- 前端 lint：已验证 0 errors / 0 warnings（含 `Workspace.tsx` 返工授权范围内的 hook-deps 清理）。

## 4. backend 不适用说明

WS-2 本轮纯前端单测/组件测试/纯前端集成（vitest + `renderToStaticMarkup`，无 jsdom、无真后端）。
**不跑、不改 backend / engine / gateway / Tauri writer**。真后端 e2e（#1/#7/#9）本轮暂停、
不作验收门；已写的 e2e/conftest/seed 仅诊断证据，已撤出提交范围。

## 5. baseline 回写要求

GREEN 落地后，按事实回写对应 baseline（只写已验证现状，未做的 target 保持 target-design/deferred）：
`graph-authoring`、`phase-editing`、`conflict-overwrite`、`03_regions/{canvas,properties,input,editor}`。
不得把"已写 RED / 计划做"当成"已实现"回写。

## 6. Deferred backend/engine drift（范围外，不在 WS-2 修）

引自 contract gate §5，GREEN 阶段保持 deferred、不强行绕过：

1. engine `SubgraphNodeAST`（`extra=forbid`）拒 subgraph `path`、要求 `target_skill`（D7 落地需 engine 改契约）。
2. 后端 canvas 序列化器不认保留入口字 `input` → `422 serializer_orphan`；未经 MVP1 文档授权 **不做"前端去 input" workaround**。
3. `graph_topology` 发 `mode:"agent"` 与 serialize DTO 冲突（DTO 只认 logic/subgraph/skill）；R2 已对前端 DTO 正确性立 RED，后端 DTO 对齐属 deferred。
4. LOGIC action 签名 mvp1 `def <name>(inputs) -> dict` 与当前引擎 `def run(...)` 不一致；纯 mvp1 种子编不过属 deferred。

## 7. 审查与终审

- **Codex 审**：GREEN diff 是否只在 owns（+ 已授权的 SubgraphInline、Workspace extraFiles 写盘返工）落地、是否弱化/删改 RED、是否 mock 核心事实源、是否越界碰 backend/engine/Tauri。
- **PM 终审**：验证命令结果、no-fake 守恒、deferred 项保持 deferred、baseline 回写诚实、契约门 / 交接提交白名单（7 文件，见 contract gate §1.1）无越界。

## 8. Gemini GREEN prompt（复制即用）

```text
ROLE: 你是 WS-2 Authoring 工作台的 GREEN 实现执行者。Studio 前端，TypeScript + React + vitest。

SubgraphInline 锁=已授权。
Workspace extraFiles 写盘返工锁=已授权。

GOAL: 把契约门已批准的 R1–R15 RED 测试转 GREEN。只做让目标行为成立的最小实现。

HARD CONSTRAINTS（违反即拒收）:
- 不得新增、删除、改写或弱化任何 RED 测试断言。测试文件是契约，只读不改。
- 只允许改 owns_files 内的生产代码:
  - apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts
  - apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts
  - apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx
  - apps/studio/frontend/src/components/studio/panels/panel-files.ts
  - apps/studio/frontend/src/components/studio/panels/InputPanel.tsx
  - apps/studio/frontend/src/components/nodes/SkillNode.tsx（仅必要的 props 接线）
  - apps/studio/frontend/src/components/studio/SubgraphInline.tsx（仅 R12/R13，已授权单文件锁）
  - apps/studio/frontend/src/components/studio/Workspace.tsx（仅 R3 extraFiles 写盘接线及相关 hook dependency lint 清理，已授权单文件锁）
- 禁止触碰: backend、engine、gateway packages、Tauri writer、Settings/LLM、Copilot、
  apps/studio/tests-e2e/**，以及任何未授权 owns 外文件。
- R12/R13 的实现体 studio/SubgraphInline.tsx 已获单文件锁，只允许为移除 mock rows
  和 missing-path recovery 修改它，不得扩散到其它 owns 外文件。
- 不得 mock 本层核心事实源(native writer / SkillDetail / subgraph / I/O 数据)来骗过测试。
- §6 deferred backend/engine drift 保持 deferred，绝不做「前端去 input」之类 workaround。
- 不扩到 WS-3/WS-4/WS-5。

TRUTH SOURCE: 只以 Studio MVP1 / engine MVP1 设计文档与 FROZEN 契约为准（见 contract gate §2
锁定裁决）。当前代码/旧行为只是 drift 证据，不能反过来定义目标。节点类型=文件名
(SKILL.md=agent / LOGIC.md=logic / SUBGRAPH.md=subgraph)，作者不写 mode；subgraph 按本地 path 引用。

R1–R15 落点见 task §2 表。逐条对照目标行为实现。

VERIFY（每改一处都跑，最终必须贴完整输出）:
cd apps/studio/frontend && npx vitest run \
  src/components/GraphCanvas/canvas-authoring.test.ts \
  src/components/studio/panels/phase-frontmatter.test.ts \
  src/components/studio/SubgraphInline.test.tsx \
  src/components/studio/panels/panel-files.test.ts \
  src/components/studio/Panels.test.tsx
基线 15 failed|17 passed。SubgraphInline 已授权，目标 32 passed。其余 17 条回归用例必须保持 passed。

DELIVER: 改动文件清单 + 完整 vitest 输出 + 每条 R 的转绿说明 + 任何 deferred 登记。
不得声称完成而未贴验证输出。
```
