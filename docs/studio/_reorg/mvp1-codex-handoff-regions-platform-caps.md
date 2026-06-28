---
doc: mvp1-codex-handoff-regions-platform-caps
audience: codex(executor，无对话历史，必须自包含)
status: handoff drafted 2026-06-03，待派发
scope: studio mvp1 补 23 个模块文档 = regions(12) + platform(4) + capabilities 缺口(7)
ground_truth:
  - docs/DESIGN-PROCESS.md（写作框架，必读）
  - docs/studio/INDEX.md（三维治理总纲 + §7 模板 + §6 注册表 + §4 status 词表，必读）
  - docs/engine/mvp1/03-api-contract/mvp1-alignment.md（引擎↔studio 接口契约 SSOT）
  - docs/studio/mvp1/01_workflows/00_settings-ux-spec.md §6.0（LLM/copilot 四层边界 SSOT）
  - apps/studio/{frontend,backend,tauri}（前端/后端/Rust 当前源码 = baseline 复核对象）
  - packages/graph-agent（引擎库）、packages/graph-agent-gateway（网关库）
related_monorepos:
  - docs/engine/mvp1/（引擎 11 关注点，已起草，studio engine 接缝只链接不重写）
  - docs/graph-agent-gateway/mvp1/（网关 14 模块，已起草，studio gateway 接缝只链接不重写）
---

# Studio MVP1 — Regions + Platform + Capabilities 缺口 写作 Handoff（codex 执行）

> **你是谁**: 你是被派来写文档的 executor，没有对话历史。本文是你的唯一任务源，必须自包含。
> **任务一句话**: 给 `docs/studio/mvp1/` 补 **23 个模块文档**，对齐 `docs/engine/`、`docs/graph-agent-gateway/` 两个 monorepo 的接口，互相引用不脱钩。
> **铁律**: 只写文档；代码问题记文末「待办/疑点」，不改代码。每条断言挂 `file:line`，来自**实际打开过的当前源码**，不照抄过时行号。

---

## 0. 写之前必读（按顺序，别跳）

> 🔴 **源优先级（PM 2026-06-03 锁，凌驾一切，必照）**：**最新权威 = `01_workflows/`(workflow) + `_reorg/workflow-action-catalog.md`(atom actions) + `_reorg/alignment-notes.md`（PM 一项项确认的决策日志）+ `00_settings-ux-spec.md`（settings SSOT）**。格式/字段 → FROZEN `docs/engine/skill-spec`；实现/接线状态 → 当前代码。**`.kiro/specs/studio-feature-*` = 过去的设计、只作参考**（曾是 2026-06-01 权威，已被 06-02/03 逐项走查覆盖/refine，**不得当现行权威**；与权威层冲突一律以 workflow/catalog/alignment-notes 为准）。**走查覆盖**：14 个能力 **全部已走查**(2026-06-04 全清,各 `01_workflows/` 节点 = 完整走查记录,见 §4.1)；写 alignment 时**从对应 workflow 节点取**(原话+决策+测试点都在那),别照 `.kiro/specs/`(过去设计)当现行。

1. `docs/DESIGN-PROCESS.md` — 设计文档模板（§2）、接口契约七项（§3）、双向引用（§3.5）、SSOT（§5）、反模式（§6）。
2. `docs/studio/INDEX.md` — 三维模型（§1）、所有权不变量（§2，**灭重叠的关键**）、status 词表（§4）、权威注册表（§6，**只能用这里的名字**）、四套文档模板（§7）、cross-link 规范（§8）。
3. `docs/engine/mvp1/03-api-contract/mvp1-alignment.md`（引擎↔studio 执行/事件/HTTP-WS 三接口面 SSOT）— region/platform 接口段的 SSOT。
4. `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §6.0 — LLM/copilot **四层边界**（settings region + gateway/engine 平台块必读）。
5. 已写好的 7 个 capability 文档（`docs/studio/mvp1/02_capabilities/*.md`）— **作为格式范本**，你补的 7 个对齐它们的模板（⚠️ 已写 7 个形态**不完全一致**，以 §1 模板为准、顺带补齐差异，别照抄某一篇的偏差；`trace-observability.md` 最完整可参考）。

---

## 1. 三种 tier 的文件形态（别搞混）

studio mvp1 是**三维治理体系**（不是 engine/gateway 那种纯扁平编号）。本批三组模块形态**不同**：

| 组 | 形态 | 内容模板 | 为什么 |
|---|---|---|---|
| **capabilities(14,含缺口)** | **文件夹** `<cap>/baseline.md` + `mvp1-alignment.md` | baseline=对齐代码现状(file:line)；alignment=DESIGN-PROCESS §2 模板 | 能力 = **真功能、对齐代码**(PM 2026-06-03 + DESIGN-PROCESS §2.1),必须 baseline(现状)+ mvp1-alignment(目标),同 regions/platform/engine/gateway。**已写的 7 个平铺单文件要转成文件夹** |
| **regions(12)** | **文件夹** `<region>/baseline.md` + `mvp1-alignment.md` | baseline=INDEX §7 region 模板套**现状**；alignment=目标+差异+接口+测试点+原话 | region = 真实 UI 组件（有当前代码现状可 baseline），用 engine/gateway 同款 baseline现状/alignment目标 拆分 |
| **platform(4)** | **文件夹** `<block>/baseline.md` + `mvp1-alignment.md` | baseline=INDEX §7 platform 模板套**现状**；alignment=目标+接口+反向依赖 | platform = 真实后端服务/Rust/前端 store（有当前代码现状） |

> **baseline.md 写什么**: 只写当前源码现状 + 覆盖率，编号执行流程，每条挂 `file:line`。范本见 `docs/engine/mvp1/06-trace-observability/baseline.md`。
> **mvp1-alignment.md 写什么**: 目标设计 + 已实现/差异 + 决策（对比被否决做法）+ 接口契约（链接 SSOT 不复制）+ 测试关键点 + 代码索引 + 覆盖率 + 待办。
> **capability 文件夹写什么(DESIGN-PROCESS §2.1)**: `<cap>/baseline.md` = 对齐代码现状(覆盖代码 + file:line + 编号执行流程 + 现状 gap,只写"现在是什么");`<cap>/mvp1-alignment.md` = **以每个功能为索引**:frontmatter(Tier/Owns/Status/Related) → 模块级「定义」+「接口契约」总览 → **然后每个功能一段(F1/F2/…),把该功能的 机制 / 决策+动机 / 原话 / 测试点 / status / 归属 全收在自己段里** → gaps → 双向交叉引用。⚠️ **别写成按 DESIGN-PROCESS 章节归纳的总结文(决策全塞一段/原话全塞一段)** —— PM 2026-06-03 定:**除「定义」「接口契约」模块级,其余按功能为索引**。**已写的 7 个平铺单文件(compile-lint/predict/run-execution/trace-observability/golden-eval/debug-resume/phase-editing)要拆成文件夹**。**范例 = `02_capabilities/copilot-assist/mvp1-alignment.md`(照它的逐功能形态)**。⚠️ **§5.1 铁律:正式文档绝不引 `.kiro`/`temp`/工作日志,原话/决策完整写进;跨模块只引 mvp + 双向 `[[link]]`**。

---

## 2. 写作 bar（逐条强制，违反即返工）

1. **每个类/函数/组件/文件名 → 紧跟一句话说清它干什么，禁止只丢名字**（PM 看不到代码，靠名字猜 = 浪费时间）。
2. 执行逻辑用**编号步骤**（输入→中间→输出，关键分支走哪条、为什么）。
3. 讲**决策原因**（对比被否决做法），不只写「是什么」。
4. 每个论断挂 `file:func` 或 `:行号`（证据），来自实际打开的当前源码。
5. **接口契约单独成段**（DESIGN-PROCESS §3）：跨边界的签名·schema·错误·归属·稳定性，不混进「数据流/机制」。跨模块共享契约**只链接 SSOT，不复制**（见 §3、§5）。
6. **原话不许编（铁律）**: capability/alignment 的「设计依据(PM 原话)」**必须从已有文档挖**（workflow 节点 / `_reorg` catalog / ux-spec / mvp0），逐字引用（`>` 引用格式）。**挖不到的不许杜撰**，标 `gap: 待 PM 补原话`。
7. **所有权不变量（INDEX §2，灭重叠的关键）**: region 文档**拥有组件**（结构/state/props/API/file:line）；capability **只链接 region，绝不重述组件内部**；platform 用**反向链接**登记「被哪些 capability 依赖」。同一事实只在一处写实现，其余只链接。
8. **status 必标**（INDEX §4 词表）: `live` / `placeholder` / `orphan-unmounted` / `backend-only` / `target-design` / `stale-doc` / `stale-code`。每个组件/动作带 status。
9. 标题 == 文件夹名（INDEX §2，杜绝改名漂移）。
10. 单文件 >~400 行 → 在本模块文件夹再拆一级并登记。

---

## 3. SSOT 铁律：gateway / engine 两个平台块是「薄接缝」，不准重写

`04_platform/gateway` 和 `04_platform/engine` 各自**已有整套独立 monorepo 文档**：
- 引擎: `docs/engine/mvp1/`（11 关注点全已起草）+ `api-engine-studio-contract.md`（接口 SSOT）。
- 网关: `docs/graph-agent-gateway/mvp1/`（14 模块全已起草）。

**所以这两块只写 studio 这一侧的「消费面 + 接缝」**，内部一律**链接**过去，**禁止把引擎/网关内部职责复制进来**（违反 DESIGN-PROCESS §5 SSOT，会漂移打架）。

**四层边界（SSOT = `00_settings-ux-spec.md` §6.0「2026-06-03 第四轮判据校准」+ `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`；写 gateway/settings/studio-settings 必照此，别用旧口径）**:

> ⚠️ **判据已反转/精确**：从「领域 vs 领域无关」改成「**公共能力内核 vs 应用加工四件事**」。一句话判据：**换个 app 还原样能用吗? 能 = ③b 公共能力内核, 不能（绑死下面四件事之一）= ③a 应用加工**。

- **① 前端 (ts)** `apps/studio/frontend` — UI + 前端业务逻辑（拖拽/投影渲染/默认选择算法/family 折叠/弃用区/可搜索选组/draft 态展示）。**只投影、不持第二份真相**。
- **② 后端 (rust)** `apps/studio/tauri` = native-fs — Roles/Copilot 数据**几乎不碰**（凭证/角色永不 Rust）；只 General 选目录 / sidecar 生命周期+IPC 桥 / copilot 聊天 session 落盘（D8，属 skill 工作台 region，**非设置页**）。
- **③a Studio 适配层（应用加工四件事）** `apps/studio/backend` — **只这四件**：① UI 交互/展示 ② 产品策略（默认推荐/动态浮出 opus4.8/弃用区/family 折叠）③ 实际调用方式（copilot 用 `ClaudeSDKClient` 拿 route 自己调 + session）④ 存储介质（凭证/知识库存哪个文件）+ HTTP `/api/llm`·`/api/copilot` 适配壳。
- **③b gateway 库（公共能力内核）** `packages/graph-agent-gateway` — 富能力公共内核：凭证&端点 schema+读写+**base_url 归一化**+**原始→标准 endpoint list（拆分+canonical id）** / available models（**model_group 分组** · identity · **draft 知识库** · notable）/ capability 归一化+对比+lint / 客观状态+熔断+**6 态标准总结** / 角色→fallback 链（**materialize 编排内核**）/ 两级调用+错误分类+原生 ChatX。
- **铁律（第四轮反转，最易写反）**：③b **不是**「不能碰 model group/6 态/draft」——**它们的能力内核（分组/状态标准总结/知识库/materialize 编排）恰属 ③b 公共**。绝不上浮 ③b 的只有**应用加工四件事**。**别再写「领域需求/model group 不下沉 ③b 库」「库永不见 model group」——旧口径已作废**。
- **现状 vs 目标（写 gateway/studio-settings baseline 必标）**：这些能力内核**现码多数还散在 ③a `apps/studio/backend`**（materialize/model_groups/6 态/draft/identity/notable/熔断持久化）→ baseline 写「现散 ③a」，alignment 写「判据归 ③b 公共 + 规划下沉（下沉是后续工程，本轮不动代码）」。逐模块处置 = **链接** `module-disposition-revised.md`，不复制。
- **握手三处**：①↔③a = HTTP /api/llm·/api/copilot（DTO：`ModelGroup`/`ProviderModelOption.ui_state`(6 态)/`RoleTestResponse`）；③a↔③b（进程内）= ③a 把「角色编排结构+意图」交 ③b `materialize`→fallback 链→`resolve_routes(role)`→`ResolvedRole`（③b 看得到编排结构+意图，看不到「用户怎么拖拽出它」）；③b↔provider = 真实调用（graph-agent 原生 ChatX；**copilot 例外**：③b 只 `resolve_routes("copilot_chat")`+capability，SDK 调用/测试/session 全在 ③a，**库不知 copilot 是什么**）。

---

## 4. 模块清单（23）— 逐个 spec

> **名字只能用 INDEX §6 注册表里的**（capability 14 / region 12 / platform 5）。下表「baseline 源」= 读哪些 mvp0 旧文档当先验 + 复核哪块当前代码。

### 4.1 capabilities（含缺口 7）— **文件夹 baseline+mvp1-alignment**（DESIGN-PROCESS §2.1），**先写这组**（regions 要链接它们）

> **源（PM 走查全清 2026-06-04，最新权威）**：14 个能力**全部已走查**,每个的权威设计 = **它对应的 `01_workflows/` 节点(走查完整记录:原话+决策+测试点)** + `_reorg/alignment-notes.md`(决策日志) + `00_settings-ux-spec.md`(settings)。`.kiro/specs/studio-feature-*` = **过去设计、只作走查参考线索**(§5.1:正式文档**绝不引**,内容写进)。**别再「以 .kiro design.md 为权威」、别写 chat-shell deferred**——范例 [`copilot-assist/`](../mvp1/02_capabilities/copilot-assist/) 已是「做全」。

> **待写清单（13 个;`copilot-assist` 已写 = 范例,照它逐功能形态）**。「新建」=无现有文档;「转」=已有平铺 `<cap>.md` → 拆成 `<cap>/baseline.md` + `mvp1-alignment.md`,旧内容并入后删:

| 文件夹 `02_capabilities/<cap>/` | 新建/转 | Owns（一句话边界） | 主源 = workflow 节点 · 必链 region |
|---|---|---|---|
| `skill-workspace/` | 新建 | 打开文件夹/Recent(MRU)/新建/移除/reveal；无注册表;子图按 path | `01_init` · `welcome` `shell-layout` `assets` |
| `graph-authoring/` | 新建 | 画布拓扑: IO 节点/连线·断连/校验/新建 phase/子图展开+下钻/dot | `02_authoring`(M/T/G1-G9/R4/P6-P7) · `canvas` `properties` |
| `file-editing/` | 新建 | Monaco 全文/分屏/schema 推断/保存冲突/file-watch | `02_authoring`(M2/M3) · `editor` `input` |
| `conflict-overwrite/` | 新建 | 顺序覆盖 overlay/白名单/cancel 标红 | `02_authoring`(顺序覆盖) · `canvas` `center-action-bar` |
| `publish/` | 新建 | 保存与发布:autocommit 存档 + Artifact Registry(占坑低优先,**非 git**) | `06_eval` · `shell-layout` `local-history` |
| `studio-settings/` | 新建 | provider 凭证/LLM roles/copilot 配置/身份产物路径;测试→持久化→6 态投影;数据走 gateway 永不 Rust | `00_settings` + `00_settings-ux-spec`(细粒度权威) · `settings` |
| `compile-lint/` | 转 | 实时 lint + 手动 compile + 错误面板 + stage 门控 | `03_compile` · `center-action-bar` |
| `predict/` | 转 | 试飞:测试输入/远程校验/mock/golden 守卫 | `04_run-and-verify` · `center-action-bar` `canvas` |
| `run-execution/` | 转 | 真跑/状态/WS 流/autocommit/batch+loop/模型对比/run 历史 | `04_run-and-verify` · `center-action-bar` `timeline` |
| `trace-observability/` | 转 | trace 读取/metrics/filter/Prompt 透视/edge-dot/节点灯/微观拓扑 | `04_run-and-verify`(P2) · `timeline` `properties` `canvas` |
| `golden-eval/` | 转 | golden 固化/Diff/字段得分/Copilot Judge/导出/打磨编排 | `04_run-and-verify`(g-a..g-f) · `properties` `copilot` |
| `debug-resume/` | 转 | HitL 问题框/节点级 Resume/checkpoint 续跑/脏状态失效/context 篡改 | `05_debugging`(F1-F8) · `properties` `canvas` `timeline` |
| `phase-editing/` | 转 | 节点属性表单全字段编辑 + 保存(FROZEN 白名单) | `02_authoring`(字段集) · `properties` `input(→i/o panel)` |

> `.kiro/specs/studio-feature-*`(canvas-topology/asset-explorer/skill-lifecycle/copilot-chat 等)可作**走查参考线索**,但**最终权威 = workflow 节点**,且正式文档**不留 `.kiro` 路径引用**(§5.1)。
> `studio-settings`/`gateway` 涉及 ③a/③b 处用 §3 第四轮边界 + §6.0,别抄旧划分。
> capability 的「依赖 platform 服务」段链接 `04_platform/{engine,gateway,native-fs,state-engine}`;接口字段链接 §5 锚点不复制。

> **PM 走查覆盖（权威 = `01_workflows/INDEX.md` 走查状态，PM 2026-06-03 — 别再用 alignment-notes 那张中途自审表）**：
> - **✅ 全 14 个能力已走查·可定稿**（2026-06-04 全清）：`skill-workspace`(01) · `graph-authoring` `phase-editing` `file-editing` `conflict-overwrite`(02) · `compile-lint`(03) · `predict` `run-execution` `trace-observability` `golden-eval`(04) · `debug-resume`(05) · `publish`(06,占坑低优先) · `studio-settings`(00) · `copilot-assist`。**每个对应 workflow 节点 = 走查完整记录(原话+决策+测试点),写 alignment 时从它取**。走查阶段全清,可批量定稿。
> （各 cap 的源 = 上表「主源 = workflow 节点」那列;`.kiro/specs/` 仅作走查参考线索、不进正式文档,§5.1。）

### 4.2 regions（12）— 文件夹 baseline.md + mvp1-alignment.md

> baseline 复核区都在 `apps/studio/frontend/src/`（components / hooks / store / api）。Owns 一句话取自 INDEX §6 注册表。

| 文件夹 `03_regions/` | 关键组件（INDEX §6）| baseline 源 = mvp0 旧文档 + 前端代码区 | 承载 capability（mvp1-alignment 链接）| 接口契约锚点（§5 详）|
|---|---|---|---|---|
| `welcome/` | WelcomePage, NewSkillDialog | mvp0 `system-layout` + `workspace-fs`(前端) | `skill-workspace` | native-fs(选目录/MRU) |
| `shell-layout/` | Workspace, Header, Toolbar, Resizable, 面包屑, 路由, 主题 | mvp0 `system-layout/baseline`(535 行富源) | `skill-workspace`(容器) | state-engine(路由/主题 store) |
| `center-action-bar/` ⚠ | center-action-bar, CompileErrorPanel | mvp0 `system-layout` + `skill-lifecycle`(状态语义) | `compile-lint` `predict` `run-execution` `conflict-overwrite` `publish` | api-contract §2(run/predict) §5(compile/lint) |
| `canvas/` ⚠ | GraphCanvas, ContextEdge, SkillNode | mvp0 `canvas-topology/{baseline,mvp0-alignment}` | `graph-authoring` `trace-observability`(dot/红灯) `conflict-overwrite` | api-contract §5.2(ErrorPayload 四轴→节点标记) §5.3(graph/serialize) |
| `editor/` | SplitEditor, LazyMonacoPanel | mvp0 `asset-explorer`(编辑器/split) | `file-editing` `trace-observability`(只读 trace 文档) | api-contract §5.2(source_path→编辑器行) |
| `assets/` | AssetsPanel | mvp0 `asset-explorer`(文件树) + `system-layout`(panels) | `skill-workspace` | native-fs(FS 读写/watch) |
| `input/` | InputPanel, PredictInputDialog | mvp0 `asset-explorer`(笼统，实为无主) | `predict` `file-editing`(schema infer) | api-contract §5.3(validate_input) |
| `properties/` ⚠（最严重重叠热点）| PropertiesPanel, phase-frontmatter | mvp0 `asset-explorer` + `trace-inspector`(分) | `phase-editing` `trace-observability`(edge-context 只读) `golden-eval`(未来 Diff) | api-contract §5.2(field_path→属性标记) §5(validate_input) |
| `timeline/` ⚠ | TimelinePanel(历史), TracePanel(流式·未挂载) | mvp0 `trace-inspector`(组件) | `trace-observability` `run-execution` | api-contract §1(WS /ws/runs/{id} + GET /runs/{id}.events) §2 |
| `local-history/` | BatchSummary, RunDetailDrawer | mvp0 `workspace-fs`(前端，薄) | `run-execution`(batch/replay) `publish` | api-contract §2(batch) §4(resume) |
| `copilot/` | CopilotPanel, ModelPicker | mvp0 `copilot-chat`(组件) | `copilot-assist` | studio copilot-assist + 04_platform/llm-copilot-http-api + backend `/api/copilot` |
| `settings/` | SettingsPage, ProviderCard, LlmRolesTab | **无旧 region 源**（旧 `llm-gateway` 只覆盖后端）；复核 `frontend/src` settings 组件 | `studio-settings` | 四层边界 §6.0 + gateway monorepo 08(6 态)+01(handoff) + backend `/api/llm` |

> ⚠ = INDEX 标的冲突热点（properties/canvas/timeline/center-action-bar）：写时**严守所有权不变量**——组件结构归 region，跨组件流程只链接 capability。范例见 INDEX §2 的 `ContextEdge → Properties` 正确切分。

### 4.3 platform（4）— 文件夹 baseline.md + mvp1-alignment.md

| 文件夹 `04_platform/` | 形态 | baseline 源 + 复核区 | 写法要点 |
|---|---|---|---|
| `native-fs/` | Rust(Tauri) | mvp0 `workspace-fs`(后端→Rust) + 复核 `apps/studio/tauri` | **真·新写**。INDEX §6 D12「唯一写者」+ §11 NFR(sidecar 生命周期 eager-spawn 非全屏 gate / copilot session 落盘恢复 / 多窗口)。FS 读写/打开文件夹/watch/MRU/reveal + runs/golden/artifacts 目录 + 闭环编排。反向链接被依赖的 capability。|
| `state-engine/` | 前端 | mvp0 `state-engine/{event-bus,ipc-bridge,state-mgmt}-baseline`(3 份共 654 行富源) + 复核 `frontend/src/store` | **真·新写**（把旧 3 份整合进新结构）。前端状态 + WS / Rust-event ipc 桥。接口链接 api-contract §1(WS 事件喂 store)。|
| `engine/` | Python sidecar | **薄接缝**：复核 `apps/studio/backend`(run_manager / routers) 怎么进程内调引擎 | **§3 铁律**：只写 studio 消费面（`run_skill`/`predict_skill`/`compile_skill` 进程内调用 + WS/trace 转发 + 异步 spawn 接缝），内部**全链接** `docs/engine/mvp1/` + `api-engine-studio-contract.md`。引擎同步 RunResult ↔ studio 异步 RunMetadata 的接缝在 run_manager（api-contract §2.3）。|
| `gateway/` | Python sidecar | **薄接缝 + ③a/③b 边界（按第四轮判据）**：复核 `apps/studio/backend`(③a) 现散落哪些「本应 ③b」的能力内核 | **§3 铁律 + 第四轮四层边界**：写 studio 这侧怎么消费 gateway 库（③a 把「角色编排结构+意图」交 ③b `materialize`→`resolve_routes`；copilot SDK 调用/session 留 ③a）。**baseline** 标「materialize/model_groups/6 态/draft/identity/notable/熔断持久化等能力内核现散 ③a `apps/studio/backend` 待下沉」；**alignment** 标「判据归 ③b 公共 + 规划下沉（本轮不动代码）」。库内部 + 逐模块处置**全链接** `docs/graph-agent-gateway/mvp1/` + `module-disposition-revised.md`。**禁写「领域需求不下沉库」（旧口径已反转）**。|

> `04_platform/i18n.md` 已写（102 行，横切 NFR 保持平铺，**不动**）。
> `04_platform/llm-copilot-http-api/` **已写成文件夹**(baseline+alignment)= **③a 的 copilot/llm HTTP API 壳**(正是 §3 说的「HTTP 适配壳归 ③a」那块)→ **别重写、别塞进 gateway/engine 薄接缝**;它和 gateway/engine 是不同模块。
> ⚠️ **platform tier 在并行演进**:写前先 `ls docs/studio/mvp1/04_platform/` + 读 INDEX §6,确认当前模块清单 + 哪些已成文件夹,**只写缺的**(native-fs/state-engine/engine/gateway…),别照本表当全集。**同理 02_capabilities/03_regions 写前也 ls 一遍**(仓库在并行改)。

---

## 5. 接口契约对齐索引（region/platform → SSOT 锚点，只链接不复制）

每个 region/platform 的「接口契约」段，**链接**下面对应锚点，**抄形状会漂移**：

- **引擎执行/事件/编译** → `api-engine-studio-contract.md`：§1 Trace(WS `/ws/runs/{run_id}` + GET `/runs/{id}`.events + 34 类事件) / §2 执行(`run_skill`/`predict_skill` 进程内 + `POST .../runs` 202 异步 + RunResult) / §3 Golden / §4 Resume(`resume_run` 现 501 桩) / §5 Compile(`compile_skill` + `ErrorPayload` 四轴 `phase_id`/`field_path`/`source_path`/`level`)。
- **错误码标记三处**（canvas 节点 / properties 属性 / editor 行）→ `ErrorPayload` 四轴（api-contract §5.2）；四字段都已存在（均 `|None`），Task 3 审计是否填全。
- **网关 role→route** → `docs/graph-agent-gateway/mvp1/01-handoff-interface/mvp1-alignment.md`（`ResolvedRoute` 契约;01-handoff-interface 是**文件夹**）+ `08-orch-test-status-ssot/mvp1-alignment.md` + studio copilot-assist（copilot SDK 调用 = ③a）。**6 态 canonical enum = `00_settings-ux-spec.md §4.2`(line 262 明文权威)**：`ready`(🟢,旧称 `verified`) / `historical_ready`(🔵 以前联通过) / `untested`(⚪) / `failed`(🔴,带 reason: `missing_config`|`endpoint_unreachable`|`model_failed`) / `cooling_down` / `off`(旧称 `disable`)。取消了旧 `needs_setup`(并入 failed)。⚠️ **现码 `ProviderUiState`(`llm_state_projection.py:12`)还是旧 5 态 `["ready","untested","cooling_down","needs_setup","off"]`**——目标去 `needs_setup`、补 `historical_ready` + `failed(reason)`;**别抄现码旧枚举,以 ux-spec §4.2 canonical 为准**。
- **四层边界** → `00_settings-ux-spec.md §6.0`。

> api-contract §7 待办 1 已要求 engine 各 alignment 的接口段改为「链接本文」。studio engine/gateway 接缝**同样只链接**，形成双向：studio→契约，契约↔引擎。

---

## 6. cross-ref 双向收口清单（DESIGN-PROCESS §3.5，最后一道，别漏）

写完所有文档后跑一遍**双向登记**（A↔B 两侧都登记，任一侧改对端立刻可见）：

1. **region → capability**: region 的「承载的能力」段链接 capability；**capability → region**: capability 的「涉及 region」段反向链接同一 region。两侧都要有。
2. **capability → platform**: capability「依赖的 platform 服务」链接 `04_platform/*`；**platform → capability**: platform「被哪些 capability 依赖」反向登记。
3. **workflow → cap/region**: 7 个 `01_workflows/*.md` 节点动作表里，把链接补到**新建的** capability/region（现在很多是待建占位，现在能落实了）。
4. **悬空链接归零**: 本批正是为了消除 region→缺失 capability 的悬空链接（graph-authoring/copilot-assist/studio-settings 等）。收口后**全仓搜一遍死链**（指向不存在的 `.md`/锚点），清零。
5. 链接到 mvp0 legacy 文档时标 `(legacy, 迁移源)`，不依赖它存活。
6. **外部 SSOT 双向锚点检查（跨 monorepo，别只查 studio 内部）**：`04_platform/engine` ↔ `api-engine-studio-contract.md` / `docs/engine/mvp1/`；`04_platform/gateway` ↔ `docs/graph-agent-gateway/mvp1/` + `module-disposition-revised.md`。Studio 侧链接外部 SSOT；外部文档当前无法反链时（跨仓），在收口表里**显式登记该单向缺口**，不当已闭合。

---

## 7. 写作顺序（codex 按此推进，减少返工）

0. **Step 0 — 边界校准前置（blocker，先于一切写作）**：先按本 handoff 修订版 §3/§5 对齐「第四轮四层边界（公共能力内核 vs 应用加工四件事）+ 6 态（无 needs_setup）」；凡 `studio-settings` / `gateway` 涉及 ③a/③b 归属处，**必须以 `00_settings-ux-spec §6.0` + `module-disposition-revised.md` 为准**，否则这两块先天串错、连累下游。
1. **capabilities（13:6 新建 + 7 转文件夹）** 先写 —— region 要链接它们。源 = §4.1 表的 workflow 节点（走查完整记录）；照范例 `copilot-assist/` **逐功能**写 baseline+alignment；「转」的把旧平铺 `<cap>.md` 内容并入新文件夹后删。
2. **regions(12)** —— baseline 复核 `frontend/src` 当前组件；alignment 链接 §4.2 的 capability + §5 接口锚点。严守所有权不变量（组件归 region，流程只链接）。
3. **platform(4)** —— native-fs/state-engine 真写；engine/gateway 薄接缝（§3 铁律，只链接）。
4. **cross-ref 收口(§6)** + 更新三个 README（`02_capabilities` / `03_regions` / `04_platform` 的「状态」从「待创建/骨架」改为实际）+ INDEX §10 迁移分期勾掉 P2。

---

## 8. 验收清单

- [ ] 模块齐（全文件夹 baseline+mvp1-alignment）：capabilities **13 个文件夹**(6 新建 + 7 转;`copilot-assist` 已写=范例)×2 + regions **12**×2 + platform **4**×2(`i18n` 平铺不动) = **26 + 24 + 8 = 58 个文件**；其中 7 个 cap 是**转换**(旧平铺 `<cap>.md` 内容并入新文件夹后删,非纯新增)。
- [ ] 每条断言挂 `file:line`，来自实际打开的当前源码（不照抄旧行号）。
- [ ] 每个代码名有一句话解释（写作 bar 1）。
- [ ] 接口段**只链接 SSOT 不复制**（§5）；gateway/engine 是薄接缝（§3）。
- [ ] capability/alignment 的 PM 原话**是挖来的**，挖不到的标 `gap`，**无杜撰**。
- [ ] status 全标（INDEX §4 词表）；所有权不变量无重叠（INDEX §2）。
- [ ] cross-ref 双向闭合（§6）；全仓无新增死链。
- [ ] 三个 tier README + INDEX 状态更新。
- [ ] 文末「待办/疑点」登记代码问题，未改代码。

> 完成后回报：新建文件清单 + 每个模块覆盖率 + 待 PM 补的 `gap`/原话缺口清单 + 发现的代码问题。
