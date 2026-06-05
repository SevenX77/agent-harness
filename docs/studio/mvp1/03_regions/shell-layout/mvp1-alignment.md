---
module: 03_regions/shell-layout
doc: mvp1-alignment
status: drafted（Workspace shell live；RuntimeGate 仍可全屏 gate，copilot prop 用 outer skillId 有下钻风险 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [shell-runtime-gate]
aligns_with: 01_workflows/01_init.md（D10 eager sidecar 决策留底）· 01_workflows/00_settings-ux-spec.md（settings overlay）
---

# shell-layout — MVP1 Alignment

> **Tier**: region | **Owns**: `shell-runtime-gate`（外壳即时渲染 / sidecar gate / slot 布局） | **现状**: Workspace shell live；RuntimeGate 仍可全屏 gate，copilot prop 用 outer skillId 有下钻风险 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `welcome` · `settings` · `copilot` · `skill-workspace` · `state-engine`

## 1. 定义
`shell-layout` owns Studio's persistent app frame: Header, Toolbar, resizable panel slots, center routing, Copilot side slot, Settings overlay placement, and Back Home behavior.

Source workflow basis: `01_workflows/01_init.md:8`, `01_workflows/02_authoring.md:18`, `01_workflows/00_settings-ux-spec.md:497`.

## 2. 数据流 / 机制（设计细节）
### F1. Persistent IDE Shell

- 机制: keep Header/Toolbar/frame stable while the center swaps Home, Canvas, Editor, or Settings.
- 决策: Studio is an app shell, not a landing page; sidecar failures should be scoped to dependent functions.
- 原话/来源: `01_workflows/01_init.md:35` locks IDE/workspace model; `01_workflows/01_init.md` §3 D10 records non-fullscreen sidecar gate behavior.
- 测试: app shell renders before compile/copilot sidecar functions are ready; feature-specific errors stay local.
- Status: mostly live, RuntimeGate still needs audit.
- 归属: region `shell-layout`; platform `state-engine`.

### F2. Header Navigation And Team Menu

- 机制: Header owns Home(Back Home)、Team dropdown、Copilot toggle。**子图下钻面包屑导航不在 Header**——改放画布左上角(见 `canvas` F4),Header 保持极简。
- 决策: publish/release remains minimal and low-priority under Team for MVP1;**面包屑(subgraph 下钻导航)刻意移出 Header**(理由同 Settings overlay:防"跳出项目"感,见下方已决)(PM 2026-06-04)。
- 原话/来源: `01_workflows/06_eval.md:17` places Release in Header Team; `01_workflows/06_eval.md:24` keeps publish minimal.
- 测试: Back Home clears workspace; Release disabled/status works while publishing。（面包屑下钻导航测试归 `canvas` F4，不在 Header）
- Status: live.
- 归属: region `shell-layout`; capabilities `skill-workspace`, `publish`.

### F3. Toolbar Panel Routing

- 机制: Toolbar selects Assets, Input, Timeline, Properties, Local History, or Settings.
- 决策: panels are work surfaces for capabilities; Toolbar owns routing only.
- 原话/来源: `01_workflows/02_authoring.md:3` maps authoring capabilities to regions; `01_workflows/04_run-and-verify.md:52` uses timeline for run history.
- 测试: selecting a panel mounts the correct region; switching panels preserves selected node and open file.
- Status: live.
- 归属: region `shell-layout`; child regions listed in `03_regions`.

### F4. Copilot Side Slot

- 机制: right resizable panel hosts the Copilot chat and can be toggled from Header.
- 决策: Copilot is a side assistant woven into the shell, not a modal.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` makes Copilot a runtime-configured assistant; capability details live in `copilot-assist`.
- 测试: toggling Copilot preserves center width; skill switching resets context to the current skill id.
- Status: live with prop mismatch risk.
- 归属: region `shell-layout`; region `copilot`; capability `copilot-assist`.

## 3. 接口契约
- Header receives current skill id, nav stack, copilot state, and home/sync callbacks.
- Toolbar selects one left panel kind or opens Settings.
- Center slot renders Welcome, GraphCanvas, SplitEditor, or Settings.
- Side slots hold active panel and Copilot, not arbitrary nested cards.
- Capability links: `skill-workspace`, `studio-settings`, `copilot-assist`, `publish`.
- Platform link: `state-engine`.

## 4. 设计决策基础（PM 原话）
- **Settings 维持中央 overlay,刻意不做全屏路由(连 P2 也不做)**。两条前因:
  1. **不让用户感觉"跳出了项目"**——Studio 是本地 app,全屏路由式跳转会触发"我项目还没保存、会不会丢"的恐慌;overlay 盖在工作区上,用户始终感觉人在项目里。
  2. **方便边调 copilot 连通边看**——overlay 不打断工作区/copilot 上下文,调 LLM/copilot 配置时不用一会儿开一会儿关、来回切页。
- **子图下钻面包屑放画布左上角(不在 Header)**,同因:避免"跳出项目"的页面切换感。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| SHELL_LAYOUT-1 | runtime gate | 对齐 `shell-runtime-gate` 设计单元，保证 region 切面能被测试回扣 |
| SHELL_LAYOUT-2 | copilot slot | 对齐 `shell-runtime-gate` 设计单元，保证 region 切面能被测试回扣 |
| SHELL_LAYOUT-3 | settings overlay | 对齐 `shell-runtime-gate` 设计单元，保证 region 切面能被测试回扣 |

## 6. 测试关键点
1. runtime gate: baseline 现状为 RuntimeGate 全屏 loading/error gate ⚠️；目标为 shell 即时渲染，sidecar 状态局部呈现。
2. copilot slot: baseline 现状为 CopilotPanel 接 outer `skillId` ⚠️；目标为 下钻时用 currentSkillId，slots 不丢状态。
3. settings overlay: baseline 现状为 Settings 在 center slot 覆盖；目标为 Settings 不卸载 copilot，不阻塞壳。

## 7. 涉及 region / platform
`welcome` · `settings` · `copilot` · `skill-workspace` · `state-engine`

## 8. gaps / 报警
- 🚨 runtime gate: RuntimeGate 全屏 loading/error gate ⚠️；目标 shell 即时渲染，sidecar 状态局部呈现。
- 🚨 copilot slot: CopilotPanel 接 outer `skillId` ⚠️；目标 下钻时用 currentSkillId，slots 不丢状态。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `welcome` · `settings` · `copilot` · `skill-workspace` · `state-engine`
