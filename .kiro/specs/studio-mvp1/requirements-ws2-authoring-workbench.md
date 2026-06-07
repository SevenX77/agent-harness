---
ws_id: WS-2-authoring-workbench
modules: [02_capabilities/graph-authoring, 02_capabilities/phase-editing, 02_capabilities/conflict-overwrite, 03_regions/canvas, 03_regions/properties, 03_regions/input, 03_regions/editor]
depends_on: [WS-0, WS-1]
blocks: [WS-3]
owns_files:
  - apps/studio/frontend/src/components/GraphCanvas/
  - apps/studio/frontend/src/components/nodes/SkillNode.tsx
  - apps/studio/frontend/src/components/edges/ContextEdge.tsx
  - apps/studio/frontend/src/components/studio/panels/
  - apps/studio/frontend/src/components/studio/SplitEditor.tsx
  - apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx
  - apps/studio/frontend/src/api/client.ts
spec_ssot:
  - docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/phase-editing/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/conflict-overwrite/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/canvas/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/properties/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/input/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/editor/mvp1-alignment.md
  - docs/studio/mvp1/01_workflows/02_authoring.md
  - docs/studio/mvp1/DESIGN_UNITS_INDEX.md
status: drafted
---

# WS-2 Authoring 工作台 — 需求书

本需求书是 WS-2 的契约输入。实现前必须先有 RED 测试、PM 契约门和用户在聊天窗口明确确认。

## 1. 目标(intent + why)

把 Canvas、Properties、Editor、Input 面板连成文件驱动的 authoring 工作台：节点和字段编辑必须落到真实 skill 文件或 GRAPH，冲突可见，I/O/test input 入口不再是假数据。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标真理：frontmatter `spec_ssot` 中各 `mvp1-alignment.md` 与 `docs/studio/mvp1/01_workflows/02_authoring.md`。
- 现状起点：`docs/studio/mvp1/02_capabilities/graph-authoring/baseline.md`、`phase-editing/baseline.md`、`conflict-overwrite/baseline.md`、`docs/studio/mvp1/03_regions/canvas/baseline.md`、`properties/baseline.md`、`input/baseline.md`、`editor/baseline.md`。
- 全局索引：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 中 `subgraph-path-inline-drilldown`、`phase-field-whitelist`、`conflict-overwrite-resolution`、`io-panel-artifacts-test-inputs`。
- 外部契约状态：engine skill syntax、resolver 和 physical layout 当前按 `DESIGN_UNITS_INDEX.md` 视为 floating-draft，WS-2 只引用，不复制 engine 内核。
- UI 规则：`docs/development/FRONTEND_UI_SPEC.md` §2 和 §3；实现前先查 `apps/studio/frontend/src/components/ui/`，使用语义 token。
- 必读源码：frontmatter `owns_files` 中的 GraphCanvas、nodes、edges、panels、SplitEditor、LazyMonacoPanel 和 API client。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx` 与 WS-1 有顺序关系，必须等 WS-1 native writer contract 释放后再处理 editor authoring。`apps/studio/frontend/src/api/client.ts` 只允许处理 authoring compute/API 接线；WS-1 的 local writer 与 runtime fallback 不在本 WS 内。所有共享策略以 `docs/studio/mvp1/_impl/IMPL_PLAN.md` 为准，必要时排队或拆分。

禁止触碰 `apps/studio/frontend/src/components/studio/Workspace.tsx` 的 run/resume 逻辑、Settings/LLM、Copilot、backend run/golden/debug 和 packages。范围外问题登记 deferred。

## 4. 现状锚点(baseline)

现状 baseline 显示 Canvas、Properties、Input、Editor 已有可见 UI，但仍存在旧字段、假数据、只在前端 state 存在的节点或保存冲突表现不统一等 drift。

## 5. 目标行为(可测的契约)

- Canvas 新建 phase、连线、subgraph path 和节点属性编辑必须以文件或 GRAPH 为源，不渲染只存在前端 state 的假节点。
- Properties 只编辑 engine MVP1 明确支持的字段，保存时保留未知字段和正文。
- I/O panel 和 test input 入口必须展示真实 workspace artifact/test input 状态，不写死样例数据。
- 冲突覆盖必须显式提示 hash/content drift，不静默覆盖用户编辑。
- UI 必须遵守 `FRONTEND_UI_SPEC.md`，使用 `components/ui` wrapper、Playwright 或浏览器点击验证、窄宽度检查和语义 token。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，覆盖 Canvas 文件驱动新建/连线、Properties 字段白名单、subgraph path 引用、I/O/test input 真实数据、conflict overlay、Editor 保存与刷新、GraphCanvas 节点即时反馈。至少一条真实 e2e 或手动验证必须打开 authoring 工作台，点击 Canvas、Properties、Input 和 Editor 成功路径与明显失败路径；不许 fake mock 到绿。

## 7. 硬依赖约束

WS-2 依赖 WS-1 native writer。engine skill syntax/resolver 未 pinned 的部分只能按 floating-draft contract 写测试边界，不能在 Studio 中发明 engine 规则。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后实现到 GREEN。
- [ ] Canvas/Properties/Editor/Input 的目标行为全部有自动化测试覆盖。
- [ ] 无回归：既有 skill detail 读取、GraphCanvas 基础渲染、Monaco 面板仍可用。
- [ ] Playwright 或浏览器真实 e2e 覆盖点击、保存、冲突、窄宽度。
- [ ] 测试命令、风险和 blocked 外部契约状态在 Codex 审查中记录。

## 9. 不做(范围锁定,IR7)

不接 compile/predict/run/trace，不做 Settings/LLM/Copilot，不做 golden/publish/resume，不复制 engine resolver 或 gateway 内核。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现落地后按真实代码回写 graph-authoring、phase-editing、conflict-overwrite、canvas、properties、input、editor 的 `baseline.md`。

## 11. 评审检查点

PM 契约门审 RED 是否真实编码文件驱动 authoring、字段白名单和冲突。Codex 审查退出以 §8 为准。PM 终审检查 baseline 回写和测试是否非假绿。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws2-authoring-workbench.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、baseline 回写和 PM 终审。
