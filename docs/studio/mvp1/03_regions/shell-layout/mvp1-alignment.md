# shell-layout MVP1 Alignment

## 定义

`shell-layout` owns Studio's persistent app frame: Header, Toolbar, resizable panel slots, center routing, Copilot side slot, Settings overlay placement, and Back Home behavior.

Source workflow basis: `01_workflows/01_init.md:8`, `01_workflows/02_authoring.md:18`, `01_workflows/00_settings-ux-spec.md:497`.

## 接口契约

- Header receives current skill id, nav stack, copilot state, and home/sync callbacks.
- Toolbar selects one left panel kind or opens Settings.
- Center slot renders Welcome, GraphCanvas, SplitEditor, or Settings.
- Side slots hold active panel and Copilot, not arbitrary nested cards.
- Capability links: `skill-workspace`, `studio-settings`, `copilot-assist`, `publish`.
- Platform link: `state-engine`.

## F1. Persistent IDE Shell

- 机制: keep Header/Toolbar/frame stable while the center swaps Home, Canvas, Editor, or Settings.
- 决策: Studio is an app shell, not a landing page; sidecar failures should be scoped to dependent functions.
- 原话/来源: `01_workflows/01_init.md:35` locks IDE/workspace model; `docs/studio/INDEX.md:221` records non-fullscreen sidecar gate behavior.
- 测试: app shell renders before compile/copilot sidecar functions are ready; feature-specific errors stay local.
- Status: mostly live, RuntimeGate still needs audit.
- 归属: region `shell-layout`; platform `state-engine`.

## F2. Header Navigation And Team Menu

- 机制: Header owns Home(Back Home)、Team dropdown、Copilot toggle。**子图下钻面包屑导航不在 Header**——改放画布左上角(见 `canvas` F4),Header 保持极简。
- 决策: publish/release remains minimal and low-priority under Team for MVP1;**面包屑(subgraph 下钻导航)刻意移出 Header**(理由同 Settings overlay:防"跳出项目"感,见下方已决)(PM 2026-06-04)。
- 原话/来源: `01_workflows/06_eval.md:17` places Release in Header Team; `01_workflows/06_eval.md:24` keeps publish minimal.
- 测试: Back Home clears workspace; breadcrumb click pops nav stack; Release disabled/status works while publishing.
- Status: live.
- 归属: region `shell-layout`; capabilities `skill-workspace`, `publish`.

## F3. Toolbar Panel Routing

- 机制: Toolbar selects Assets, Input, Timeline, Properties, Local History, or Settings.
- 决策: panels are work surfaces for capabilities; Toolbar owns routing only.
- 原话/来源: `01_workflows/02_authoring.md:3` maps authoring capabilities to regions; `01_workflows/04_run-and-verify.md:52` uses timeline for run history.
- 测试: selecting a panel mounts the correct region; switching panels preserves selected node and open file.
- Status: live.
- 归属: region `shell-layout`; child regions listed in `03_regions`.

## F4. Copilot Side Slot

- 机制: right resizable panel hosts the Copilot chat and can be toggled from Header.
- 决策: Copilot is a side assistant woven into the shell, not a modal.
- 原话/来源: `01_workflows/00_settings-ux-spec.md:433` makes Copilot a runtime-configured assistant; capability details live in `copilot-assist`.
- 测试: toggling Copilot preserves center width; skill switching resets context to the current skill id.
- Status: live with prop mismatch risk.
- 归属: region `shell-layout`; region `copilot`; capability `copilot-assist`.

## 已决(PM 2026-06-04)

- **Settings 维持中央 overlay,刻意不做全屏路由(连 P2 也不做)**。两条前因:
  1. **不让用户感觉"跳出了项目"**——Studio 是本地 app,全屏路由式跳转会触发"我项目还没保存、会不会丢"的恐慌;overlay 盖在工作区上,用户始终感觉人在项目里。
  2. **方便边调 copilot 连通边看**——overlay 不打断工作区/copilot 上下文,调 LLM/copilot 配置时不用一会儿开一会儿关、来回切页。
- **子图下钻面包屑放画布左上角(不在 Header)**,同因:避免"跳出项目"的页面切换感。
