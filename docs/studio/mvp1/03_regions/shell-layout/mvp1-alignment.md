---
module: 03_regions/shell-layout
doc: mvp1-alignment
status: FROZEN（Workspace shell live；RuntimeGate 已按 D10 局部化(2026-08-20 核实)，copilot prop 用 outer skillId 有下钻风险 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [shell-runtime-gate]
aligns_with: 01_workflows/01_init.md（D10 eager sidecar 决策留底）· 01_workflows/00_settings-ux-spec.md（settings overlay）
---

# shell-layout — MVP1 Alignment

> **Tier**: region | **Owns**: `shell-runtime-gate`（外壳即时渲染 / sidecar gate / slot 布局） | **现状**: Workspace shell live；RuntimeGate 已按 D10 局部化(2026-08-20 核实)，copilot prop 用 outer skillId 有下钻风险 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `welcome` · `settings` · `copilot` · `skill-workspace` · `state-engine`

## 1. 定义
`shell-layout` owns Studio's persistent app frame: Header, Toolbar, resizable panel slots, center routing, Copilot side slot, Settings overlay placement, and Back Home behavior.

Source workflow basis: `01_workflows/01_init.md:8`, `01_workflows/02_authoring.md:18`, `01_workflows/00_settings-ux-spec.md:497`.

## 2. 数据流 / 机制（设计细节）
### F1. Persistent IDE Shell

- 机制: keep Header/Toolbar/frame stable while the center swaps Home, Canvas, Editor, or Settings.
- 决策: Studio is an app shell, not a landing page; sidecar failures should be scoped to dependent functions.
- 原话/来源: `01_workflows/01_init.md:35` locks IDE/workspace model; `01_workflows/01_init.md` §3 D10 records non-fullscreen sidecar gate behavior.
- 测试: app shell renders before compile/copilot sidecar functions are ready; feature-specific errors stay local.
- Status: live。2026-08-20 核实 `components/RuntimeGate.tsx` 的 `RuntimeShell` 无条件渲染 `{children}`,
  失败只落成底部 banner——D10 要的局部化已经做到,此处不再是 gap;Retry 按下去要发生什么由 F5 定义。
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

### F5. Retry 真的重试(sidecar 起不来时)

- 机制: the Retry affordance on the runtime banner re-attempts THE THING THAT
  FAILED — starting the Python sidecar — instead of re-reading a cached answer
  about it. The shell owns the launch recipe (`SidecarLaunchConfig`)
  independently of whether a sidecar is currently running, so "start one" is
  available in all three states: the first start succeeded, it started and later
  died, or it never got off the ground. Every attempt replaces the recorded
  error with **that attempt's own** outcome; a success clears it and emits
  `sidecar-restarted`, which is what rotates port + token on the frontend.
- 决策: 一个按钮要么真的做它写着的那件事,要么不该出现。2026-08-19 的现场是
  `RuntimeGate` 的 Retry 只重跑了 `initializeRuntimeConfig()`,而 sidecar 没起来时
  `get_sidecar_config` 回的是**首次启动那一刻缓存下来的错误字符串**——按一万次,
  字面上同一条消息,用户看到的就是"点了没反应"。根因不是少调一个函数:启动
  sidecar 的配方 `launch_config` 当时存放在 `SidecarManager` **内部**,而
  `SidecarManager` 只能由一次**成功**的启动构造出来;首启失败,配方跟着陪葬,
  所以 `restart_sidecar` 只救得了一个还活着的 sidecar。修法是把配方的归属搬到
  外壳:能启动 sidecar 的本事不再是"已经启动成功"的副产品。
- 参考: Erlang/OTP supervisor 的 child spec 与 systemd 的 unit 文件都由**监督者**
  持有,而不是由正在跑的那个进程持有——所以 `restart_child` / `systemctl restart`
  对一个**没在跑**的子进程同样成立。本条借的就是这一点。**不借**它们的自动重启
  策略(`Restart=always`、restart intensity 限流):这里的触发器是用户按下 Retry,
  而在"vendor 缺失"这类永久性失败上自动重试只会把错误刷没,让用户更看不见原因。
- 原话/来源: 问题台账 P2「app 重启静默失败(Try again)」(`docs/development/PROBLEM_LEDGER.md`)。
  D10 定的是 gate 不全屏(见 F1),没有定 Retry 的语义;本条补齐这个缺口。
- 测试: 在一个从没起来过的 sidecar 上重试,报出的是**这次尝试**的失败原因,而不是
  "Python sidecar is not running"这条拒绝;成功后 banner 消失且新 token 生效。
- Status: 本次落地。
- 归属: region `shell-layout`; platform `native-fs`(sidecar 生命周期机制在那里)。

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
| SHELL_LAYOUT-1 | runtime gate | 单元 `shell-runtime-gate`；**为什么**：壳即时渲染、sidecar 失败只局部呈现，不全屏阻塞(D10) |
| SHELL_LAYOUT-2 | copilot slot | 单元 `shell-runtime-gate`；**为什么**：下钻时 CopilotPanel 用 currentSkillId，slots 不丢状态 |
| SHELL_LAYOUT-3 | settings overlay | 单元 `shell-runtime-gate`；**为什么**：Settings 中央 overlay 不卸载 copilot、不阻塞壳，防"跳出项目"感 |
| SHELL_LAYOUT-4 | retry 真的重启 sidecar | 单元 `shell-runtime-gate`；**为什么**：启动配方归外壳所有，才能重启一个从没起来过的 sidecar(F5) |

## 6. 测试关键点
1. runtime gate: 壳即时渲染、sidecar 状态局部呈现(D10)已落地；仍需锁的是 F5——Retry 在 sidecar 从没起来过时也要真的去启动它。
2. copilot slot: baseline 现状为 CopilotPanel 接 outer `skillId` ⚠️；目标为 下钻时用 currentSkillId，slots 不丢状态。
3. settings overlay: baseline 现状为 Settings 在 center slot 覆盖；目标为 Settings 不卸载 copilot，不阻塞壳。

## 7. 涉及 region / platform
`welcome` · `settings` · `copilot` · `skill-workspace` · `state-engine`

## 8. gaps / 报警
- 🚨 copilot slot: CopilotPanel 接 outer `skillId` ⚠️；目标 下钻时用 currentSkillId，slots 不丢状态。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `welcome` · `settings` · `copilot` · `skill-workspace` · `state-engine`
