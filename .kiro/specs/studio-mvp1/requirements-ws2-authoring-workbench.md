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
  - docs/studio/mvp1/_impl/IMPL_PLAN.md §三/§五/§六/§七
  - docs/studio/mvp1/README.md
  - docs/studio/mvp1/01_workflows/02_authoring.md
  - docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/phase-editing/mvp1-alignment.md
  - docs/studio/mvp1/02_capabilities/conflict-overwrite/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/canvas/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/properties/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/input/mvp1-alignment.md
  - docs/studio/mvp1/03_regions/editor/mvp1-alignment.md
  - docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md
  - docs/development/FRONTEND_UI_SPEC.md §2/§3
status: ready-for-contract-gate
---

# WS-2 Authoring 工作台 — 需求书

本需求书是 WS-2 的契约输入。所有判断只以 Studio MVP1 设计文档、engine MVP1 契约文档和本文件列出的 SSOT 为准；当前代码和旧测试只能作为 baseline / drift 证据，不能反过来定义目标。实现前必须先有 RED 测试、PM 契约门，并等待用户在聊天窗口明确确认；系统自动审批不算确认。

## 1. 目标(intent + why)

把 Canvas、Properties、Editor、I/O 面板连成文件驱动的 authoring 工作台。用户在画布上建节点、连线、编辑 phase 字段、配置输入输出和 artifact 时，Studio 必须修改真实 skill 源文件或 `GRAPH.md`，再用 engine compile/lint 反馈验证结果；不能继续渲染只存在于前端 state、mock 文件、旧 MVP0 字段或 FastAPI 本地写盘路径里的假成功。

WS-2 是 WS-3 Compile/Predict/Run/Trace 的前置。它必须先稳定 authoring schema、文件保存路径、冲突处理和 I/O 配置，否则 WS-3 会接到旧 schema 并继续放大 MVP0 drift。

## 2. SSOT 指针(grounding,IR2/IR5)

- Studio 工作流权威：`docs/studio/mvp1/01_workflows/02_authoring.md`。重点结论是 `GRAPH.md` 无 `type` 字段；节点类型由文件名决定，`SKILL.md` / `LOGIC.md` / `SUBGRAPH.md` 三选一；subgraph 以 path 引用并放松父子 IO 严格 1:1；当前 `mode` / 旧 prompt / 旧 subgraph 字段属于 stale。
- Studio 能力权威：`graph-authoring`、`phase-editing`、`conflict-overwrite` 的 `mvp1-alignment.md`。对应 `baseline.md` 文件只用于确认当前代码差距，不定义目标。
- Studio 区域权威：`canvas`、`properties`、`input`、`editor` 的 `mvp1-alignment.md`。对应 `baseline.md` 文件记录当前 UI live / stale / placeholder 状态。
- Engine 契约权威：`docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md`、`02-skill-syntax/mvp1-alignment.md`、`02-mechanism/02-resolver/mvp1-alignment.md`。engine skill syntax / physical layout 当前是 drafted + 继承 mvp0 FROZEN，WS-2 只能消费和引用，不能在 Studio 里发明第二套 parser 或 resolver；不得只读 mvp0 `04-subgraph` 或当前 `manifest.py` 就推断 MVP1 仍要求 `target_skill` + 严格 1:1。
- UI 规则权威：`docs/development/FRONTEND_UI_SPEC.md` §2 和 §3。注意 §3 仍含较旧的字段描述；字段白名单冲突时，以本需求书上面的 Studio authoring / phase-editing / engine 契约为准，UI spec 只作为 layout、组件、样式、验证规则。
- WS 分区权威：`docs/studio/mvp1/_impl/IMPL_PLAN.md` §三/§五/§六/§七。当前 worktree 没有 `docs/studio/mvp1/DESIGN_UNITS_INDEX.md`；若旧 gate 或旧需求书提到 `DESIGN_UNITS_INDEX.md`，只能视为待修复的文档锚点，不得把不存在的文件当 SSOT。
- 实现前必读源码：frontmatter `owns_files` 中的 GraphCanvas、nodes、edges、panels、SplitEditor、LazyMonacoPanel 和 `api/client.ts`。如行号与 baseline 不一致，执行者必须重新核实。

## 3. 文件归属(并发锁,IR1)

本 WS owns frontmatter `owns_files`。`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx` 只能消费 WS-1 已释放的 native writer contract；不得恢复 FastAPI/Python 本地写盘，也不得绕开 `apps/studio/frontend/src/lib/tauri.ts` 去拼临时浏览器写盘。`apps/studio/frontend/src/api/client.ts` 只允许处理 authoring read/compute/API DTO 接线，不允许改 Settings、Copilot、run/golden/debug API。

`apps/studio/frontend/src/components/studio/Workspace.tsx` 不在 WS-2 owns 内；如果 authoring 保存确实需要改 Workspace glue，必须先登记 deferred 或请求文件锁释放，不能在 WS-2 中悄悄改。`apps/studio/frontend/src/components/studio/panels/` 与 WS-4 的 Properties role shortcut 有潜在交叉，WS-2 只处理 phase authoring、I/O 和 conflict；role shortcut 等 WS-4/WS-2 串行协调后再接。

禁止触碰 Settings/LLM、Copilot、backend run/golden/debug、Tauri writer、`packages/graph-agent/**`、`packages/graph-agent-gateway/**`。发现范围外问题只登记 deferred。

## 4. 现状锚点(baseline)

当前 baseline 显示 Canvas、Properties、Input、Editor 都已有可见 UI，但多数 authoring 关键点仍是 MVP0 drift：新 phase scaffold 写旧 frontmatter/body，Properties 读写旧字段，Input panel 投影假文件，Subgraph inline 是 mock，ContextEdge 展示 mock JSON，graph persist 仍有旧 Python file API 痕迹。WS-2 的任务不是保护这些旧行为，而是用 RED 测试证明它们与 MVP1 冲突，然后按 MVP1 收口。

如果现有测试断言旧字段、mock 数据、前端-only 节点或 FastAPI 写盘成功，Codex 必须先把测试改成 MVP1 RED 断言并确认旧实现失败；不能为了旧测试恢复 MVP0 行为。

## 5. 目标行为(可测的契约)

- Canvas 从 `GRAPH.md` 和真实 phase 文件构建节点/边。新建 phase、连线、断连、子图下钻和节点选择不能只改前端 state；保存后必须刷新真实 `SkillDetail` 或等价文件视图。
- 新建节点按文件名选择类型：agent 写 `SKILL.md`，logic 写 `LOGIC.md`，subgraph 写 `SUBGRAPH.md`。脚手架不得写旧 `mode`、旧 prompt 字段、旧 subagent shape 或会被 engine AST 拒绝的字段。
- `GRAPH.md` 的根 metadata、phase list、`depends_on`、根 `io` 是宏观契约来源。画布连线必须持久化为 `depends_on`，环或非法拓扑要被阻断并保留原文件。
- Properties 只渲染 MVP1 允许的三类节点字段，并保存到对应 phase 文件；未知 frontmatter、正文和非编辑块必须保留。旧字段不能继续作为可编辑主路径；用户改旧 `mode` 不能改变节点类型。
- Subgraph 按 path 引用。path resolved 时可以 inline 展开或下钻；path missing 时必须有可见错误和 Assets / workspace recovery 入口，不允许用 mock rows 假装展开。父子 graph 的 IO 不做旧式严格 1:1 阻断；输入从共享状态按 schema 切片的目标语义只引用 engine/Studio MVP1 文档，不在 Studio 前端重写。
- I/O panel 要从当前 skill / workspace 读取真实输入、schema、output artifact path 和 test input 状态；schema inference 如果保留，必须能写回 MVP1 目标位置，不能只做只读 demo 或固定 `sample.json` 投影。
- 所有本地 source file 写入必须经 WS-1 Rust-mediated writer 或其前端 wrapper；冲突必须走 expected hash / content drift 流程，不能静默覆盖。
- Sequential overwrite、file conflict、compile/lint error 在 Canvas、Editor、Properties / I/O 中要有一致的用户反馈。允许 overwrite 必须显式记录，不允许用本地红色状态代替真实文件事实。
- UI 必须使用本地 `components/ui` wrapper、语义 token、lucide 图标和 `FRONTEND_UI_SPEC.md` §2 的桌面工具布局规则；不得硬编码 hex / Tailwind 具体色值。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，且 RED 要在旧实现上真实失败。最低覆盖如下：

1. Canvas 文件驱动：构造一个真实 skill，连接两个 phase 后断言 `GRAPH.md` 的 `depends_on` 改变；再制造非法环，断言文件未被改写且 UI/错误状态可见。
2. 新 phase scaffold：分别新增 agent / logic / subgraph，断言产物是 `SKILL.md` / `LOGIC.md` / `SUBGRAPH.md`，且不含旧 `mode`、旧 prompt、旧 subagent 字段；compile/lint 能消费。
3. 节点类型来源：给 phase 文件写入会误导旧实现的 `mode` 值，断言渲染类型仍由文件名决定。
4. Properties 字段白名单：选中 agent / logic / subgraph 分别只显示 MVP1 允许字段；保存后保留未知字段和正文；旧字段不再作为主编辑项出现。
5. Subgraph path：resolved path 展示真实 child graph 或可下钻；missing path 标红并出现 recovery 入口；不允许 `SubgraphInline` mock 数据通过。
6. Subgraph IO 放松：构造父子 IO 不严格 1:1 的 subgraph，断言 Studio 不因旧 mvp0 1:1 假设阻断 authoring；任何校验必须来自 MVP1 engine compile/lint 契约，而不是前端旧推断。
7. I/O panel：真实 `GRAPH.md` io/schema/artifact/test input 状态进入面板；修改 artifact path 或 schema 后写回目标文件；没有真实数据时显示空态，不许 fake mock。
8. Editor 保存与 conflict：autosave 带 expected hash；stale save 触发 conflict flow；选择 cancel / remote / retry 后文件状态可验证。
9. Frontend regression：GraphCanvas 基础渲染、node click、double click open file、SplitEditor / Monaco 保存仍可用。
10. 真实 e2e：用 Playwright 或等价浏览器打开 authoring 工作台，点击 Canvas、Properties、I/O、Editor 的成功路径和明显失败路径；至少覆盖一个窄宽度视口，检查无横向溢出、按钮/tooltip/Badge 不互相遮挡。
11. No-fake 边界：测试不得通过 mock 掉 native writer、mock 掉 `SkillDetail` 刷新或 mock 掉 subgraph/I/O 数据来制造假绿；必须至少有一条真实文件读写路径。

## 7. 硬依赖约束

WS-2 依赖 WS-1 native writer 和 Python 写者退场。若 writer wrapper、hash conflict 或 workspace identity 未释放，WS-2 必须把保存类子项标为 blocked 或条件放行，只能先做纯渲染 RED，不得恢复 FastAPI 写盘。

Engine physical layout / skill syntax / resolver 是 floating-draft + mvp0 FROZEN 继承状态。WS-2 只能引用 `docs/engine/mvp1/` 和对应 mvp0 FROZEN 链接，不在 Studio 前端复制 engine parser、resolver 或 compile 内核。遇到 mvp0 FROZEN 与 Studio MVP1 authoring 文档冲突时，需求书和 RED 必须以 MVP1 authoring / phase-editing 的当前裁决为准，并把当前 engine 未更新部分登记为 drift。

## 8. 验收标准(硬退出,IR4)

- [ ] RED 测试先失败，PM 契约门通过后才允许实现，且最终 GREEN 不削弱断言。
- [ ] Canvas/Properties/Editor/I/O 的目标行为全部有自动化测试覆盖。
- [ ] 所有本地 source file 写入都走 WS-1 native writer contract；没有 FastAPI/Python 本地写盘回归。
- [ ] 无回归：既有 skill detail 读取、GraphCanvas 基础渲染、Monaco 面板和 compile/lint 入口仍可用。
- [ ] Playwright 或浏览器真实 e2e 覆盖点击、保存、冲突、空态和窄宽度。
- [ ] MVP0 旧测试已审计；被改写、删除或保留的旧测试及理由已记录，且没有旧测试继续要求恢复 stale 行为。
- [ ] 没有修改 Settings/LLM、Copilot、run/golden/debug、engine/gateway packages。
- [ ] 测试命令、外部契约 floating-draft 状态、deferred 范围和风险在 Codex 审查中记录。

## 9. 不做(范围锁定,IR7)

不接 compile/predict/run/trace 执行链，不做 Settings/LLM/Copilot，不做 golden/publish/resume，不复制 engine resolver / parser / compile 内核，不修改 gateway/engine packages，不为了过旧测试恢复 MVP0 字段或 Python 写盘。范围外问题登记 deferred。

## 10. baseline 回写指令(IR6)

实现落地后按真实代码状态回写 graph-authoring、phase-editing、conflict-overwrite、canvas、properties、input、editor 的 `baseline.md`。只能写已经实现并验证的现状；未做的 target 继续保留 target-design / deferred，不得提前写成 live。

## 11. 评审检查点

PM 契约门重点审 RED 是否真实编码文件驱动 authoring、字段白名单、subgraph path、I/O artifact、conflict 和 no-fake 边界。Codex 审查退出以 §8 为准。PM 终审检查 baseline 回写是否诚实、旧测试是否已按 MVP1 清理、文件锁是否未越界。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准 RED 测试写 `.kiro/specs/studio-mvp1/task-ws2-authoring-workbench.md` 并输出 Gemini prompt。交接必须包含 owns_files、禁止触碰、验证命令、用户明确确认、backend 不适用说明、baseline 回写、Codex 审和 PM 终审。Gemini 只能把已批准 RED 实现到 GREEN；不得删改 RED、不得扩大到 WS-3/WS-4/WS-5。
