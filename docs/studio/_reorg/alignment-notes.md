> **[SUPERSEDED 2026-06-05]** 本文 PM 决策已逐条固化进 `docs/studio/mvp1/` 的 workflow 节点 + 能力/平台文档(原话就近 inline;finality 经 Gemini+codex 双审,PM 原话/🔒 不被更新的派生文档自动覆盖)。**mvp1 全树零引用本文**。固化裁决日志见 [`docs/design/studio-mvp1-reorg-consolidation.md`](../../design/studio-mvp1-reorg-consolidation.md)。**本文不再作 SSOT**;待 `_reorg/` 内部依赖(workflow-action-catalog / settings-action-catalog / handoff 等)一并退役后可 `deprecated` 删。

# Studio 文档重组 — 逐节点对齐笔记

> PM 对 AI 推导的 ~120 动作逐批对齐的**决策记录**, 原话留底(铁律: 不用提炼版替代原文)。
> 日期: 2026-06-01。配套: [workflow-derivation.md](workflow-derivation.md) · [../INDEX.md](../INDEX.md)

---

## 批次 1 — `01_init`

### D1 [架构·待锁] 取消注册表, 改 IDE/workspace 模型
> 原话: "skill 到底要不要注册表. 注册表(多了非常乱) vs ide方式(干净+自由,也很方便, 直接简化你第一个问题)"
> 截图: 当前 Studio skill 列表把系统上所有 skill(含 brainstorming/dispatching-parallel-agents 等 superpowers 插件 skill, 跨 resources/skills 与 5.1.0/skills 多根)全聚合成卡片 → 杂乱。Cursor Home = Open project / Recent projects。

- 决定方向: skill = 一个文件夹; Home = 打开文件夹 + Recent(MRU, localStorage); **无聚合注册表**。
- 注册表唯一的硬职责是**跨 skill 子图解析**(`target_skill` → 路径)。IDE 模型用 **workspace 根内 sibling 文件夹查找**替代(截图 2 所有 skill 都在 `.../skills/` 下, 天然就是 workspace)。
- 影响: `skill-registry` 能力 → 重塑为 `skill-workspace`; V0.3.0 需求1(子图注册导入) → 重写为 "未找到 → add-folder-to-workspace"(VS Code 风格); 后端 `SkillResolverProtocol` 在 workspace 根内解析。
- **待锁**: 此决策牵动 engine(SkillResolverProtocol)与在飞的 V0.3.0 cutover, 需与那条线对齐后锁。

### D2 [决策] 不卡导入校验
> 原话: "不用卡导入, 导入什么文件真不重要, 我们有compile, 有copilot, 屎都给你改成标准skill"
- 删 import 校验门 + `import-error-format`。开任意文件夹即用; 不合规由 compile 报错 + copilot 修成标准 skill。

### D3 [决策] 外部 IDE 联动全删
> 原话: "[Open in Cursor] 外部 IDE 联动 不需要了, 21、22、23都不需要了, 已经上copilot了"
- 删动作 21/22/23(open-external-ide/terminal/codex)。copilot 内置后无需外跳。

### D4 [决策] mod+n 快捷键删
> 原话: "24非常不常用,没必要"
- 删动作 24(shortcut-new-skill)。

### D5 [决策] copilot 建技能要后端 brainstorming 式 skill 支撑
> 原话: "Copilot 对话式建技能, 需要一个类似brainstorming的skill, 加入graph_skill背景知识(用途运作方式)+skill spec(渐进式暴露)+各种template few shot模版"
- `copilot-create-skill` 由一个专门 graph skill 驱动: graph_skill 背景知识 + skill spec(渐进式暴露)+ template few-shot。Studio copilot 自身用 graph skill 实现。

### D6 [跨切 NFR] 后端数据组件统一 skeleton + lazy load
> 原话: "后端相关所有组件需要skeleton、lazy load功能(available models, 巨长列表)"
- 所有由后端数据驱动的组件(available models 巨长列表、skill 列表、run 历史…)必须有 skeleton 加载态 + lazy load。写进 INDEX 跨切约定。

### 问题解答(已澄清, 见 chat)
- **Q3 退出/内存/settings/多窗口**: 当前 Back-to-Home → Workspace 卸载 → copilot 对话 + 面板/分屏/选中态全丢(localStorage 只留 Recent+主题, 文件已落盘)。**打开 Settings 不算退出**(center overlay, skill 态保留)。多窗口与否 = 待 PM 拍(见 chat 两条路径)。
- **Q4 无 skill 时 copilot**: 当前 copilot WS 绑定 `skill_id`, cwd=skill 目录; 无 skill 时 copilotOpen 强制 false(welcome 无 copilot)。决定: copilot 随 skill(含新建空 skill 内即可用), welcome 屏不放 copilot。**修正 AI 之前误判的"落地 gap"**——新建空 skill 后进入即有 copilot, 无矛盾(PM 指出)。
- **Q9 runtime-bootstrap**: 见 chat 解释(Tauri + Python sidecar 启动 gate)。是否补进 01_init "环境准备" 待 PM 拍。

### 01_init 动作净变更
- 删: 21/22/23/24。
- 合并: 6/7(import/import-resolve) + 16(import-error) → `open-folder`(IDE 模型, 无校验)。
- 改: 8 recent-skills → recent-folders(MRU); 11 skill-delete → remove-from-recent(不删盘); 12 config-drift-warn 在无注册表下存疑(待定)。
- 修正: 19 copilot-create-skill 非 gap(skill 内可用), 由 D5 支撑。
- 能力重塑: `skill-registry` → `skill-workspace`。

---

## 批次 1 续 — 架构决策(第 2 轮)

### D7 [决策·修正] 子图按显式 path 解析, 非注册表(AI 之前搞复杂了)
> 原话: "跨 skill 子图解析 不是你说的这样的,你搞复杂了. subgraph.md里面写path, 直接解析就好了, 随便放哪里. 唯一要注意的是copilot 的工作目录范围要把subgraph的子图path 加进去. 还有一个是注册在agent phase里的子图,也一样写path"
- 子图引用 = `SUBGRAPH.md`(及 agent phase 内子图配置)里**写死 path**, 直接解析, 放哪都行。无 id→path 注册表解析。
- 唯一要求: **copilot cwd scope 必须把被引用子图的 path 纳入**(否则 copilot 读不到/改不到子图)。
- 简化 V0.3.0: `SkillResolverProtocol.resolve` 退化为"读 path", 无注册表查找。

### D8 [硬需求] copilot 对话必须持久化
> 原话: "其他无所谓, copilot对话不能丢, 退出再进去要打开一摸一样的对话, session记录都要在, 和cursor一样, 这点必须要做到"
- copilot session 落盘(按 skill), 退出再进恢复一模一样的对话 + session 记录。其余工作态(面板/分屏/选中)可丢。
- 实现倾向: Rust(native-fs)拥有 session 文件(写在 skill 目录), gateway 无状态只流式; 重进 Rust 载回历史。天然跨窗口。

### D9 [决策] 多窗口: 不难就做
> 原话: "多窗口难不难, 不难就实现吧"
- 与 D10 联动: 3 块拆分(Rust 壳 + 共享无状态 sidecar)下多窗口不难 → 做。当前单体下较乱。

### D10 [架构·AI 判定可行, 待 PM 确认] 后端拆 3 块
> 原话: "后端应该分为3块: 1. gateway 包括 studio backend里面的llm gateway相关的后端部分代码要并入 gateway, 这部分全部用服务形式, python sidecar; 2. graph agent engine, 也是python, 用 sidecar; 前面两块都是 引擎真跑的时候需要调用的服务; 3. 大量的本地操作, 读写文件, 文件系统(打开文件夹)等等, 全部用rust本地操作. 判断这样是否可行?? 如果是这样的话, 应该不需要bootstrap. 调用后端的地方skeleton就行."
- 块1 **gateway**(Python sidecar): 并入 studio backend 现有 llm-gateway 代码; provider/role/credential/model + copilot chat。已有 `graph-agent-gateway` 雏形。
- 块2 **engine**(Python sidecar): `packages/graph-agent`; compile/lint/predict/run/eval/trace。
- 块3 **native-fs + 编排**(Rust): 打开文件夹/读写/file watch/MRU/reveal + runs 目录 + golden CRUD + 闭环编排 + sidecar 生命周期 + 调用块1/2。
- 块1/2 设计为**无状态服务**(引擎真跑时才调), 状态/FS/编排归 Rust。
- 推论: **取消全局 bootstrap(RuntimeGate)** → 壳+文件浏览/编辑(Rust)立即可用; 调 sidecar 处各自 skeleton。
- AI 判定: 可行且更优。待确认细节: ①compile 需 engine 起来(首次 skeleton 或保活); ②编排归 Rust(确认); ③copilot session 存储归 Rust/FS; ④file_watcher+冲突检测从 Python 迁 Rust; ⑤sidecar 生命周期 Rust 管。
- 详细拆分计划应过 Codex review 再实施(CCB)。

### D11 [锁] IDE/workspace 模型
> 原话: "锁 IDE/workspace 模型"
- 锁定。Home = 打开文件夹 + Recent(MRU); skill = 文件夹; 无注册表; 子图按 path(D7)。

### 待办: 平台层重构落 INDEX(等 D10 确认后一次性改, 避免反复 thrash)
- `04_platform` → gateway(py sidecar) / engine(py sidecar) / native-fs+orchestration(rust) / state-engine(前端 ipc 桥)。
- 删 runtime-bootstrap; 跨切 NFR: skeleton + lazy load + **copilot session 持久化**。

### 第 2 轮确认/修正 (2026-06-01)
- D10 ① 编排归 Rust: ✅ 确认。
  > 原话: "编排放rust,ok"
- D10 bootstrap 修正: **sidecar 启动期即拉起**(非懒加载)。
  > 原话: "启动程序时就后端拉起sidecar, 因为未来还要登陆用户呢, 还有setting 页面里api、llm role这些配置都需要服务端"
  - 两 sidecar 在 app 启动时由 Rust 即刻拉起(gateway 早期就要: settings 的 API/LLM role 配置 + 未来 login)。
  - 仍**非全屏 bootstrap gate**: 壳+FS 立即渲染, 调 sidecar 处 skeleton + 全局就绪指示; 未来 login 或加独立 auth gate。
  - **D10 全部确认 → 锁。已落 INDEX §6 平台表 + §11 NFR。**

---

## 批次 2 — `02_authoring` 核实(对照 FROZEN ground truth)

> 触发: PM 指出 batch-2 表用了过时字段, 命"先好好核实代码再聊"。已读 `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`(FROZEN, PM 逐条拍板)+ 02-graph/05-agent spec + 挂载表单 `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts`。
> 原话: "1.'配头部 name/description/type(simple/graph)'这类字段对齐ground truth没有? /docs/engine/skill-spec 2.'拖/粘 JSON 自动推导 io.inputs Schema' 这类都过时了吧? 先好好核实一下代码再来聊吧"

### 核实结论
- **Q1 manifest 头部**: GRAPH.md frontmatter 真相 = `name`+`schema_version:"v0.3.0"`+`llm_role`(默认 analyst)+`description`+`phases:list[str]`+`io:`(inline JSON Schema)+ body `<phase depends_on>` 拓扑。**无 `type: simple/graph`**(spec: "type:graph 不需要写")。batch-2 #4 错 2 处: (a) type 字段不存在; (b) 把 graph manifest 与 phase 编辑混为一谈。
- **Q2 schema-infer**: 过时。V0.3.0 io = frontmatter 内联手写 JSON Schema; 外部 io 文件退役(FATAL `[F-v3-graph-io-physical-file-deprecated]`)。

### 重大发现: 整个 phase 编辑表单 = stale-code
挂载的 `phase-frontmatter.ts` 写 V2.x 老格式, 与 FROZEN spec 全面冲突:
| 现状代码 | FROZEN spec |
|---|---|
| 写 `mode:` | 无 mode(文件名 SKILL/LOGIC/SUBGRAPH.md 决定类型) |
| agent `<system_prompt>` 块 | `<role>`+`<goal>`+`<step>`+`<protocol>`+`<example>`, 无 system_prompt |
| `<exit_contract>` 块 | **禁止**写进 SKILL.md(FATAL), hardcode 在 cognitive template |
| logic `<python_callable>` 块 | `actions:` frontmatter + `<action>` body |
| **删 validator/llm_role** | 每 phase 都有 `validator:bool`; agent 有 `llm_role` |
| 无 max_iterations/subagents/subgraphs/references/examples/io | spec 全要求 |
(另 `components/phaseform/` 未挂载孤儿, 稍新但仍含 `model_override`/`user_prompt_template` 非 spec 字段。)

### Ground-truth phase 编辑字段集(重建目标)
- **Agent(SKILL.md)**: fm: llm_role, validator(bool), max_iterations(1-50), io.inputs/outputs, tools[], subagents[{name,target_skill,description}], subgraphs[同], references[{id,path,summary}], examples[{id,path,summary}]; body: `<role>`必 `<goal>`必 `<step id name>`* `<protocol id>`* `<example id>`*。
- **Logic(LOGIC.md)**: fm: validator(bool), io.inputs/outputs, actions[]; body: `<action>`*。
- **Subgraph(SUBGRAPH.md)**: fm: target_skill(D7=path), validator(bool), io.inputs/outputs; 无 body。
- 类型 = 文件名, 非 mode 字段; "新建节点选类型" = 选建哪个文件。

### 决策/影响
- 新增 status `stale-code`(代码在跑但实现过时格式, 冲突 FROZEN spec)→ 已加 INDEX §4。
- `phase-editing` 能力 + `properties` region 文档须**按 FROZEN skill-spec 写目标**; 现表单标 stale-code 重建。
- **教训(铁律重申)**: 各 batch 的 spec 相关 action 必须对照 `docs/engine/skill-spec` 重新 ground; 不可信 derivation(它读了 stale code + stale workflow doc)。

---

## 批次 2 Half A — `02_authoring` 宏观+拓扑+子图(代码侧核实, 2026-06-01 续做)

> 接批次 2 spec 侧核实。本轮核实 Half A **真实前端代码状态**(macro manifest + io + 拓扑 + 子图)。
> 结论: 读取层 v030-aware(`CURRENT_SCHEMA_VERSION='v0.3.0'` 与 FROZEN 一致, `config/schema.ts:1`), 但**写入/脚手架/子图渲染层大面积 stale-code/mock**。已呈现给 PM, 决策原话待补(见末)。

### 动作核实表(动作 | capability | region | status | 证据 file:line)

**宏观 Macro(全局契约):**
- M1 头部 `name`/`schema_version`/`llm_role`/`description`/`phases`(**无 type**) | file-editing | editor | **stale-doc**: workflow doc 写 `type(simple/graph)` 但 FROZEN 无此字段; 且无结构化 header 表单, 只能裸编辑 GRAPH.md | spec `02-graph-md-spec.md:14-20`; `panel-files.ts:37`(manifestFiles 仅返回文件行); grep 无 manifest form
- M2 `io.inputs/outputs` 内联手写 JSON Schema | graph-authoring | canvas + editor | **读 live + InputPanel 投影 stale-code**: 双击 IO 节点开 GRAPH.md(✓); 但 InputPanel 把 io 投影成假文件 `input/schema.json`(违背 inline-io, 触 `F-v3-graph-io-physical-file-deprecated`) | `build-nodes.ts:108-120`; `GraphCanvas.tsx:423-429`; `panel-files.ts:70-97`
- M3 schema 自动推导(拖/粘 JSON→io) | file-editing | input | **stale-code/obsolete**: `SchemaInferPanel` 仅 `<pre>` 显示, 不写回 io; 与"io 内联手写"方向冲突 | `InputPanel.tsx:18-70`; `lib/schema-infer`
- M4 起点 Input / 终点 Output = 画布独立节点 | graph-authoring | canvas | **live**: globalInput/globalOutput 节点已渲染, 双击开 GRAPH.md | `build-nodes.ts:203-217`; `GraphCanvas.tsx:59-63,423-429`

**中观 Meso(拓扑 + 子图):**
- T1 节点连线 `depends_on`(串并行) | graph-authoring | canvas | **live**: 连线→serializeSkillGraph→写 GRAPH.md(hash 乐观并发 + 失败回滚) | `GraphCanvas.tsx:319-361`; `canvas-authoring.ts:68-98`; `Workspace.tsx:206-224`
- T2 断连 | graph-authoring | canvas | **live**: 右键 edge→Disconnect→重 serialize 写 GRAPH.md | `GraphCanvas.tsx:475-483`; `canvas-authoring.ts:100-127`; `Workspace.tsx:226-244`
- T3 连线校验 / 数据断层红叉 | graph-authoring | canvas | **环检测 live; 数据断层红叉 target-design(前端无); 后端 dataflow 校验 backend-only** | `GraphCanvas.tsx:217-243`(环检测+toast); `ContextEdge.tsx`(无 fault 渲染); spec `02-graph-md-spec.md:89-96`(`F-v3-graph-dataflow-source-missing`)
- T4 新建 phase(Agent/Logic/Subgraph) | graph-authoring | canvas | **接线 live, 脚手架内容 stale-code**: 右键 Add Phase→写文件+重 serialize(✓); 但 `defaultPhaseMarkdown` 写 `mode`/`<system_prompt>`/`<exit_contract>`/`<python_callable>`(违背 FROZEN, 与 phase-frontmatter.ts 同源问题) | `GraphCanvas.tsx:485-498`; `Workspace.tsx:186-204`; `canvas-authoring.ts:143-189`
- T5 子图 inline-expand(树状展开看脉络) | graph-authoring | canvas | **placeholder**: toggle 接线 live(SkillNode 展开按钮), 但 `SubgraphInline` 写死假数据(path + entry/execute/return 三假行), 不渲染真实子拓扑 | `SkillNode.tsx:116-130`; `SubgraphInline.tsx:8-25`; `GraphCanvas.tsx:184-194`
- T6 子图 drill-down + 面包屑 | graph-authoring | canvas | **target-design**: 双击 skill 节点只开 phase 文件 + properties, **无下钻子画布、无面包屑** | `GraphCanvas.tsx:423-435`
- T7 Context Bridge / context_mapping | — | — | **stale-doc/not-in-spec**: FROZEN SUBGRAPH.md 只有 name/target_skill/validator/io(严格 1:1 名字映射自动绑定), 无 context_bridge; io 由 StateMapper 按 io schema 自动切片, 无手写 mapping/bridge | spec `04-subgraph-md-spec.md:32-90`

### 跨切 stale 模式(authoring 通病: 读 v030 / 写 V2.x)
1. `defaultPhaseMarkdown` 新建 phase 写 stale 格式(`canvas-authoring.ts:143`)
2. InputPanel io-as-files 投影 `input/schema.json`(`panel-files.ts:70` inputFiles)
3. schema-infer 只读死路(`InputPanel.tsx:18`)
4. SubgraphInline mock(`SubgraphInline.tsx`)
5. `subagentsForPhase` 读 stale shape `phase_config.subagents{name,path,description}`(`build-nodes.ts:151-160`), spec 是 top-level `subagents{name,target_skill,description}`
6. (类型层)build-nodes 仍留 legacy `manifest.type='graph'/'agent'` 分支(`build-nodes.ts:35-67`)
- **layout 流派**: SplitEditor.tsx 是流派 B(Monaco + 随动 canvas)雏形; 纯 canvas 为流派 A。workflow doc 标"双线探索"未定。

### 待 PM 决策(已呈现, 原话待补)
- **Q-A 子图能力档位**: T5 inline 真实渲染 + T6 drill-down/面包屑 做到哪档?
- **Q-B 数据断层红叉(T3)**: 前端补可视化 or 仅 compile 面板列出?
- **Q-C schema-infer(M3)**: 删 / 改造成写回 io / 保留只读?
- **Q-D layout 流派**: A(canvas-first) vs B(VS-Code split) 锁哪个 / 都要 / 暂缓?
- ⚠️ **以上 4 问大部分已被新 spec 回答** —— 见下「设计权威源更新」。PM 当场 dismiss 这 4 问, 因为答案已在 `studio-feature-*` spec 里设计好。

---

## 设计权威源更新 — `.kiro/specs/studio-feature-*`(PM 2026-06-01 review 定稿, 5 份)

> PM 原话: "所有 kiro-spec 里带 studio-feature- 前缀的文档, 都是我刚刚 review 过一起设计的文档, 这会更新很多你看到的旧的设计"。
> 铁律(L1)适用: 这 5 份是 doc-reorg 的**新设计权威**, 取代 `docs/studio/02_features/*` 旧 baseline 与 workflow-derivation 的**目标设计**。今后 `02_capabilities`/`03_regions` 目标须从这 5 份派生(**spec=设计目标 / FROZEN skill-spec=格式 / 当前代码=status**)。

### spec → INDEX 注册表映射 + 权威文件(⚠️ 部分子文件已自我 stale)
| spec | 取代/吸收 | 映射 INDEX | 权威文件 | 已 stale 子文件 |
|---|---|---|---|---|
| canvas-topology | canvas-authoring-v1 + canvas-micro-topology-v1(吸收) | `graph-authoring` + `canvas` + 运行态 `trace-observability` 微观 + Rust 写管线 NFR | requirement + research | — |
| asset-explorer | 重定向(透明去黑盒/极简分屏) | `file-editing` + `assets`/`editor` + Copilot inline-diff(跨 spec) | **requirement** | design.md(旧过度设计, requirement §6 命重写) |
| skill-lifecycle(建议改名 test-inputs-batch) | 收敛(仅测试输入+批量运行) | `predict`/`run-execution` 的**一部分**(compile/predict/run 叙事仍归 skills.py) | design + requirement | review-2026-06-01.md(header 标"勿据此实现") |
| trace-inspector | trace-and-predict-visibility(改名合并) | `trace-observability` + `timeline` + `debug-resume`(resume=DEF-005 后端501) | requirement + design | — |
| copilot-chat | copilot-context-design(pm-pending 建议 supersede 归档) | `copilot-assist` + `copilot` | **design** + pm-pending | requirement.md(仍 chat-shell 取向, design §8 命重写) |

### 关键设计更新(影响 Half A 及各 batch)
- **canvas**: REQ-1 纵向 TB 布局; REQ-2 黑板可视化连线(**删类型相等红**, 字段按 io.inputs 切片高亮勾选); REQ-6 三层下钻(L1宏观 / L2 双击子图进**完整子 skill 工作台+面包屑** / L3 步骤级展开 body `<step>`/`<action>`); REQ-11 运行态只读展开(LangSmith 竖向时间轴); REQ-10 Properties 白名单对齐 FROZEN(**官方确认我 batch-2 stale 表单结论**)。
- **→ Half A 4 问已被 spec 回答**: Q-A 子图下钻= L2 做; Q-B 红叉→改黑板可视化(非红叉); Q-D 布局= TB(非 A/B 二选一); Q-C schema-infer 未被明确处置(REQ-2 改字段勾选, 倾向弃 paste-infer)。
- **trace**: REQ-1~6「现在可做」—— TracePanel + useRunStream 是 zombie(已实现零引用)需接线; 边 dot mock→真实黑板 state card→只读编辑器; 净化 PropertiesPanel `selectedEdge` JSON 倾倒。**confirms derivation 三大发现**。
- **copilot**: design 重构 —— chat-shell(@mention/pill/safe-write/diff)降级 deferred; MVP0=领域脑子(常驻薄层 system_prompt + engine-authoring plugin 渐进披露 + add_dirs 指向 skill-spec 唯一真相源不复制)。

### ⚠️→✅ 跨 spec 架构冲突 — 已裁定 [D12]: 写入全量 Rust(仅 engine/gateway 用 Python sidecar)
- canvas-topology DECISION-CANVAS-08: skill 源文件(GRAPH.md/SKILL.md/phases)写**全量迁 Rust** std::fs(收口一条写路径, 标为有成本重写)。
- skill-lifecycle D1: `.workspace` 文件写 **Python 独占**(Rust 只对话框); "Rust 独占裸 FS = 未来大重构, 不在本范围"; 双写者=本地凭空制造并发冲突。
- copilot-chat P0-A: 文件写入唯一权威 = **编辑器 save-compile 契约**(复用现有 Python `PUT/POST /skills/{id}/files`)。
- INDEX D10: native-fs(Rust)owns FS 读写 + runs 目录 + 闭环编排。
- **冲突点**: MVP0 内 canvas 要把 GRAPH.md 写迁 Rust, 但 copilot apply / 编辑器 save 走 Python 端点写**同一** GRAPH.md → 同文件双写者(正是 skill-lifecycle D1 警告的并发冲突)。

#### [D12] PM 裁定(2026-06-01): 本地操作全量 Rust, engine/gateway 才用 Python sidecar
> 原话: "因为这些 specs 关注的点不一样, 所以可能有些 spec 没有关注到底哪个写。我给你答案, 全量切 rust, 除了 graph agent 和 llm gateway 相关使用 python sidecar, 其他本地操作都用 rust"

- **本地操作 → Rust 命令**: skill 源文件(GRAPH.md/SKILL.md/LOGIC.md/SUBGRAPH.md)读写、`serialize_graph`、`mutate_phase_body`、`.workspace`(test_inputs/golden/runs/artifacts)读写、copilot patch apply 落盘、编辑器 save —— 全部 Rust。
- **仅两块走 Python sidecar**: ① graph-agent **engine**(compile/lint/predict/run/eval/trace); ② **llm-gateway**(provider/role/credential/model 解析 + copilot chat LLM 流)。
- **裁定覆盖**: skill-lifecycle D1(Python 独占 .workspace 写)、copilot-chat P0-A 的"复用 Python `POST /skills/files`"实现细节(这些 spec 各自只关注自己的点, 没统筹写归属)。**对齐**: canvas DECISION-08 + INDEX D10 + 后端三分(D10)。
- **copilot UX 不变**: "patch proposal → 编辑器内存 apply(变 dirty)→ 用户 save" 流程照旧, 只是最终 save 落盘命令换 **Rust**(不再走 Python `POST /skills/files`)。
- **对文档的影响**: `native-fs`(Rust)平台文档 = **唯一写者**收口; `graph-authoring`/`file-editing`/`phase-editing`/`predict`/`run-execution`/`golden-eval` 的所有写步骤统一标"经 Rust 文件命令"; Python 端点退为只读 + 编译/装配。需在 INDEX §6 平台表 + §11 NFR 补一句"写入唯一权威=Rust"。
- **2026-06-14 Copilot 例外**: PM 放行 Copilot SDK `Read/Write/Edit` 自行读写 workspace,不再把 SDK Write/Edit 直写列为 D12 阻断;D12 仍覆盖 Studio 自有写入(editor save / graph serialize / `.workspace` / publish package 等)。最终 SSOT 已回写 `docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md` 与 `docs/studio/mvp1/04_platform/native-fs/mvp1-alignment.md`。

---

## 画布 子图/下钻/io 设计细化(PM 2026-06-01, 讨论中 — 细化并部分覆盖 canvas REQ-2/6/7)

> PM 对 T5/T6/io-panel 的细化, 原话留底。**部分覆盖 canvas-topology spec**(下标注), 需回写该 spec。

### T5 子图 inline 展开(原话) — 纠正我之前的误判
> "要在主画布inline 展开子拓扑, 下钻和inline不冲突, 点加号展开拓扑, 节点与父图节点无异, 文件都在assets tree的subgraph展示和父图无异; 需要小心的地方是一个层级多个subgraph展开会打架, subgraph 需要有一个自己的虚线容器, 可以整体的拖移, 点击打开后在父图的最右侧(父图也需要有一个group范围,而且是动态的, logic, agent节点的展开都会影响这个范围)之外打开, subgraph的group和subgraph节点的handle相连. 点击+ focus自动移到subgraph的group"
- inline 展开 **与** 下钻**并存不冲突**(纠正我之前"作废 inline 改下钻"的误判)。
- subgraph 展开 = 自己的**虚线容器**(整体可拖), 开在父图**动态 group bbox** 最右侧之外; 容器 ↔ subgraph 节点 handle 连线; 点 + 自动 focus 到容器; 容器内节点与父图节点无异; 子图文件在 assets tree 子图区与父图无异。
- 父图 group bbox **动态**: logic/agent 节点的 L3 步骤展开会改变它。
- 同层多 subgraph 展开**会打架** → 各自独立容器 + 防撞。
- **→ 回写**: canvas REQ-6 现仅 L2 下钻 + L3 步骤展开, **缺"编辑态子图 inline 容器展开"**, 需补进 REQ-6。

### T6 子图下钻(原话) — 覆盖 canvas REQ-6 L2 + 删一条跨 spec 依赖
> "子图下钻, 下钻不用完整打开子图的工程, 还是在父图工程里编辑, assets、 copilot 都不用动, 文件在subgraph里有了, copilot无缝衔接, 随时切回父图不用缓存"
- 下钻 = **就地**聚焦子图拓扑, **不切换工程**; assets/copilot **不动**(子图文件已在父 assets tree、copilot cwd 已含子图 path = D7), 随时切回, **无需缓存**。
- **→ 覆盖 canvas-topology REQ-6 L2**("切入完整子 skill 工作台 panel+canvas+copilot + 面包屑")**及** §0 cross_spec("L2 要求 copilot per-skill 会话缓存归 copilot spec")。**该跨 spec 依赖取消**。需回写 canvas REQ-6 + 删 canvas/copilot 的这条 cross_spec。

### input panel → i/o panel(原话)
> "input panel 改 i/o panel; 每个节点的 i/o 设置都在这里面展示; artifacts落盘, 每个节点都可以设置, 在哪个节点设置, 跑的时候就在哪个节点落盘; 你也可以在最后 output 节点设置(所有数据都在状态机)"
- `input` region 改名 **i/o panel**(INDEX region 表需改); 每节点 io 设置在此(= REQ-2 黑板字段勾选的落点)。
- artifact 落盘**逐节点**可设, 设在哪节点跑时就在哪落盘; output 节点也可设(黑板全量可达)。
- **→ 回写**: INDEX `input` region 重命名; M2/T7 的 UI 落点 = i/o panel。

### Claude 提的遗漏点(一起想, 待 PM 过)
1. **位置/展开态存哪(硬约束)**: FROZEN GRAPH.md 不能存坐标(未知字段 FATAL); 容器拖动位置/展开态/L3 态 = 纯视图态 → 需非 FROZEN 布局 sidecar(如 `.workspace/canvas-layout.json`, 走 Rust 落盘)或 localStorage, 否则刷新/重跑全塌(VS Code Outline 同款)。
2. **子图 io 改 ↔ 父 SUBGRAPH.md 1:1(硬约束)**: FROZEN 强制父子 io properties 1:1(`04-subgraph:74-90`); 在父图里改子图 io 会破契约(FATAL `F-v3-subgraph-io-mismatch`)→ 改时自动同步父 SUBGRAPH.md 或即时报。
3. **artifact 配置存哪+是什么(硬约束)**: FROZEN io.outputs 是纯 JSON Schema, 无"落盘"字段 → 要么改 FROZEN 加字段(同 REQ-8 "加字段须改契约"顾虑), 要么 studio 层非 FROZEN 配置; 须定 路径/命名/格式(JSON? 图片?); 且 io.outputs(写黑板)vs artifact(写磁盘)是**正交轴**(字段可只进黑板/只落盘/都要)。
4. **共享子图编辑副作用**: 子图 path 引用可多父图共用(D7); 父图里 inline 改子图 = 改本体, 影响所有引用者 → 要不要警告/标"共享子图"。
5. **递归嵌套深度**: 子图里还有子图, inline 无限往右铺会爆 → 定深度阈值, 超限强制只下钻(n8n; REQ-14 已暗示)。
6. **auto-layout vs 手动拖**: dagre TB 重排别冲掉用户拖好的容器位 → 容器位用户接管、排除出 dagre。
7. **坏子图/展开错误态**: target_skill 解析不到 → + 点不开, 给"修 path / 导入"; 展开后 io mismatch → 容器标红关联 FATAL。
8. **两个 + 语义差异**: subgraph + = 开外部容器; agent/logic + = 内部步骤就地展开(撑大节点/父 bbox)→ 视觉上要让用户一眼懂为何不同。
9. **编辑/运行态共用容器**(DECISION-CANVAS-09): 同一容器, 编辑态显示可改子拓扑 / 运行态显示子运行只读 trace(REQ-11)。

### G1–G9 PM 回应 + 新需求 + 动机(2026-06-02, 原话留底)
> **铁律新增**: 本 session 所有与 FROZEN 冲突的新需求 → **改 FROZEN(新版本)**。**记录纪律新增**: 每条 workflow 决策都要写清背后动机。

- **G1 布局态 ✅**: 非 FROZEN 布局 sidecar + Rust 落盘。
- **G2 子图 io / 文件导入 — 改 FROZEN**:
  > 原话: "数据流应该是单向不可逆的, 所以没有回写一说. 父子图的io关系不用绑死(伪需求), 和其他节点一样, 子图的input是从state状态机过滤字段拿的; 另外增加一点, 你可以在任何一个i/o界面导入文件, 就和第一个input节点导入文件一样. 导入文件就相当于导入这个文件的字段进状态机. 但是其背后的真实行为是: a.就在跑到当下节点时输入新字段给状态机. b.全部在第一个节点时就把所有节点的input文件一起导入. 这两者那种更好, 都不影响节点运行."
  - **删 FROZEN 子图 io 严格 1:1**(`04-subgraph` "IO 严格 1:1 映射"=伪需求): 子图 input = 从黑板过滤字段, 同任何节点。**动机**: 数据流单向不可逆 + 黑板单一真相, 1:1 绑定多余。
  - **新需求**: 任意 i/o 面板可导入文件 = 把文件字段注入黑板(同首 input 节点)。
  - **a vs b 时机 → Claude 建议 a(跑到该节点时注入)**。**动机**: 保持 DAG 单向 scoping(字段在作者挂载点才出现)、避免上游污染与同名碰撞、支持单节点重导入; b 把"导入位置"与"注入时机"解耦=语义泄漏。*待 PM 拍*。
- **G3 artifact 落盘 — 改 FROZEN**:
  > 原话: "黑板肯定都得进. 落盘是并行需求不影响状态机. 落盘的写法就在io.outputs 的schema顶层再加一个文件路径, xx/xx/xx.json(或者md), 下面是这个文件的schema; 也可以连续两个路径不同文件...一个schema落两个文件; 也可以不同路径各自下面加schema...不同schema落不同文件; 默认不用写前面的路径,只要写一个文件名,代表直接落盘在.workspace的artifacts(artifacts默认怎么组织也要想清楚); 格式:文字只允许md和json..."
  - **改 FROZEN io.outputs**: schema 顶层加 文件路径(`xx/xx/xx.json|md`)+ 其下 schema; 支持 一 schema 落多文件 / 多 schema 各落不同文件; 只写文件名=默认落 `.workspace/artifacts`。**动机**: 落盘与黑板正交的并行需求, 配置就近写在产出字段处最直观。
  - **待想清**: artifacts 默认目录组织。
  - **md 源 → Claude 建议直接用 agent 最终 validated `business_data_md`**(已过 md_to_json 强校验=格式已修正完整), **不做 json→md 回转**。**动机**: 最终 business_data_md 本就是合格 md(你拿得到), json 无 canonical md 渲染, 回转有损丢结构。json artifact = md_to_json 输出; logic 节点无 md 仅 json。⚠️ *待核实引擎在 artifact 写入点是否保留最终 business_data_md*。
- **G4 嵌套/性能**:
  > 原话: "我的想法是没有上限的...子节点的容器是独立的不和父节点冲突,靠在父节点的最右边...如果你担心canvas节点显示问题, 可以加上一个功能, focus到一个容器, 其他容器就半透明缓存成一张图片? 这样可不可行?"
  - **无深度上限**; 容器**扁平独立**(非容器套容器), 各自靠父图最右。
  - **focus+其他缓存为图 → 可行但偏重**; Claude 建议先用更轻的 **LOD**(off-focus 折叠成标题+节点数缩略)+ React Flow `onlyRenderVisibleElements` viewport culling + opacity dim; 光栅化成图作兜底。**动机**: 图快照有失效/模糊/交互死区成本, LOD+culling 更省心且拿 80% 收益; 无上限→画布会很宽, 配 G5 minimap/fit 导航。
- **G5 布局 ✅+扩**: dagre 只排新建节点; 手动位置实时保存; 右键空白→自动布局(整体重排); 右键菜单加 fit/100%/lock。
- **G6**: 两个 + 语义 → 不过度设计。
- **G7 共享子图 — 探索**:
  > 原话: "这确实是个问题, 能否引用git的什么机制来防止呢? 自动建分支? 如果有分支更新问你是否拉取, 可以点开看diff, 当然也可以让copilot直接帮你判断"
  - 根本张力: D7 是 **path 共享(单文件)**, 无副本→无"pull"; 真 git-ref 版本化会取代 path 解析=大改。
  - Claude 建议 **轻量版(MVP)**: 保留 path 共享 + "共享子图(N 引用者)"徽章 + 编辑前警告; git 作**安全网**(save 自动 commit)→ 共享子图变更时弹"S 改了, diff 在此, 影响 A/B, 复查/回滚?" + copilot 总结影响。**动机**: 这实现你要的"分支更新→问→diff→copilot判断"体验, 不引入 ref-based 依赖管理复杂度; 重量版(git-ref 子图版本化)留未来。*待 PM 拍*。
- **G8 ✅**。
- **G9 ✅**: 运行时 focus 跟随运行节点, 进子图 focus 到子图具体节点; 不需先展开。

### 🔒 锁定(PM 2026-06-02)
> 原话: "就按你说的做,没有问题,现在就锁+跑"
- G2 文件导入时机 = **a(跑到该节点才注入)**; G3 md 源 = **最终 validated `business_data_md`(不做 json→md 回转)**; G4 = **LOD + viewport culling(光栅化成图作兜底)**; G7 = **git 轻量安全网(path 共享 + 共享徽章 + auto-commit + 变更 diff + copilot 判断影响)**。全部锁定为决策。
- 唯一遗留核实(不阻塞): 引擎在 artifact 写入点是否保留最终 `business_data_md`(G3)→ 实现期核。

### FROZEN 新版本改动清单(本 session, 仅登记 — 文件本轮不动手)
1. 删 `04-subgraph` **io 严格 1:1 映射**(G2)。
2. `02`/`03`/`05` **io.outputs 加 artifact 落盘路径标注**(G3)。
3. (引擎/runtime)**节点级文件导入→黑板注入**(G2 新需求)。
4. (已记)canvas REQ-2 **黑板可视化连线 + 字段勾选 io.inputs**(影响 io 语义)。
> 待 scope/动作目录成型 + PM 确认改动集后, 统一出 FROZEN 新版本(改 `00/02/03/04/05/11/12`)。

### 记录纪律(PM 指示, 锁定)
> 原话: "我希望你把每个 workflow 决策的背后动机都写清楚"
- 今后每条决策 = **决策 + 动机(为什么)**; 回溯补齐已有决策动机。

### Workflow 动作目录已产出(2026-06-02)
- workflow `wf_1c266263-f42`(6 节点并行 + critic)→ [workflow-action-catalog.md](workflow-action-catalog.md): **119 个动作**, 每个带 capability/region/status/动机/file:line/FROZEN 改动。01/03/04/05/06 高质量(critic 抽检 ~20 处 file:line 零证伪); 02 agent 退化(probe-17)→ scope/跨切由 orchestrator 据 Half A 重建, 动作行保留。
- **critic 浮现、待 PM 拍的真缺口**:
  1. **settings 旅程无主**: 6 节点无一拥有 settings region, 但 publish/predict 硬依赖(API keys/LLM roles/产物路径)→ 是否立 `00_settings` 节点?
  2. **copilot 持久化失败退路缺失**(D8 MUST): 无动作覆盖 session 写盘失败/损坏 → 静默吞=对话丢失违铁律, 需补失败退路。
  3. **stage 机归属**: idle→compile→predict→run 门控归 `compile-lint` 单一拥有(03/04 重复描述需收口)。
  4. **region≠platform**: 04/05 误把 engine/native-fs/state-engine 当 region(已在 catalog 审校段纠正)。
- **整层定性(多节点独立佐证)**: 「后端实/前端虚」——predict/run/golden/publish 后端 live/backend-only, 但 TracePanel/DiffView/BatchRunner/PromptInspector/useRunStream/useGoldenDiff 全 orphan 零挂载, Eval 模式(view='eval')不可达。主要工程=接线孤儿。

### 续做(2026-06-02): PM 决策 + 可疑项核实 + 文档重组
- **PM 拍**: ① settings → 立 `00_settings` 节点(承载 API keys/LLM roles/copilot 配置/产物路径旅程); ② copilot 持久化 → 补「session 写盘/读回失败→显式告警不静默」失败退路动作(D8 MUST 配套)。
- **可疑项核实(已做)**: events.py **34** 事件类✓; 最终 `business_data_md` 在 `cognitive_flow.py:482` 保留 → G3 md artifact 直接取不回转✓; `useGoldenDiff` GET `/compare` vs 后端 POST `/compare`+GET `/diff` mismatch✓(orphan 潜伏 bug, 接线时修)。
- **节点 PM 确认状态**: ✅ `01_init` / `02_authoring`(+ 跨 session 决策 D12/FROZEN-1..4/00_settings/copilot 失败退路)已过 PM; ⏳ `03_prediction`/`04_execution`/`05_debugging`/`06_eval` **未过 PM**, 下个 session 逐节点走查。
- **文档重组(旧/新分离, mvp0/mvp1; PM 纠正方向 = 旧→mvp0, 新→mvp1)**:
  - `docs/studio/mvp0/` = **旧设计 baseline**(`02_features`/`03_platform` 移入), 迁移后按需删, 见 [mvp0/README](../mvp0/README.md)。
  - `docs/studio/mvp1/` = **新设计·重设计目标**(`01_workflows`/`02_capabilities`/`03_regions`/`04_platform` 移入), 见 [mvp1/README](../mvp1/README.md); MVP1 内延后项(brain/REQ-8/REQ-7/DEF-005)在文档内标 target-design。
  - `INDEX.md` + `_reorg/` 留根(治理 + 工作区); V0.3.0 暂存需求移入 `_reorg/`; INDEX §5 已更新。
- **handoff**: 下个 session 交接 prompt 在 `temp/studio-reorg-handoff.md`(gitignored 临时区, 不入正式 docs)。

---

## 方法与教训(2026-06-01, 锁定)

### M1 [方法] 往下每批先核实再讲, 对齐 FROZEN spec + 真实代码
- 每个 batch 的 spec 相关动作, 先对照 `docs/engine/skill-spec`(及 执行/trace/gateway 相关 spec)+ 核实当前前后端代码, 再呈现给 PM。
- batch 表 = "**FROZEN spec 目标 + 真实实现状态**"(live/placeholder/orphan-unmounted/backend-only/target-design/stale-doc/stale-code), 不是"现状描述"。
- `workflow-derivation.md` 的 6 张表已证明**字段细节不可信**(基于 stale code + stale workflow doc); 仅可用作"动作清单骨架", 字段真相以本文件逐批修正版为准。

### L1 [教训·铁律] 文档默认可能过时, 采信前交叉验证
> PM 原话: "吸取教训, 看任何文档时要长个心眼, 这文档是不是过时了? 要去读代码、读其他文档甚至看git交叉验证, 确认什么是最新的"
- 看任何文档先问"它过时了吗?"; 采信前交叉验证: FROZEN spec + 当前代码 + 其他文档 + git history。
- **权威序(按关注点)**: skill 格式/字段 → `00-FORMAT-GROUND-TRUTH.md`(FROZEN) > 代码 > workflow-doc/derivation; "实际实现/接线状态" → 当前代码 > 文档。
- 这是"核实优先于提问"铁律的延伸: 不仅核实再提问, 还要**核实文档时效再采信**。

### 下一步
- 本轮**不动手**(PM 将清 context 后做)。交接 prompt 已写: `docs/studio/_reorg/NEXT-SESSION-PROMPT.md`。

---

## 00_settings 节点 — 结构决策 + 起草(PM 2026-06-02, AskUserQuestion 拍板)

> 起草 00_settings 前撞到两个结构 / 命名决策。按"结构别假设先确认"铁律, 已自核(读 INDEX §6 确认无 settings capability; survey settings 前端代码 + 6 份 specs + gateway mvp1 模块)后请 PM 拍。

### S1 [决策] 节点产物 = 01_workflows 散文节点(非 catalog 动作表)
- PM 选: **"01_workflows 散文节点"** —— 写 `mvp1/01_workflows/00_settings.md`, 与 01_init / 02_authoring 同散文体(业务目标 / 核心范式 / 旅程 / 失败退路 / 下游流转), 非 catalog 的 status + file:line 动作表。
- **动机**: 00_settings 是 PM 面向的旅程叙事, 沿用既有节点散文体例保持一致; 工程级 status / 证据留待 catalog / capabilities 阶段。
- ⚠️ 注意: 既有 01_init / 02_authoring 散文**含 stale 残留**(01 还写 `[Open in Cursor]`/D3 已删; 02 还写 `type simple/graph`/M1 已标 stale)→ 00_settings 写**新设计 grounded 版, 不带 stale**。

### S2 [决策·动注册表] 新增 `studio-settings` 能力(第 14 个 capability)
- PM 选: **"新增 studio-settings 能力"** —— 一个宽口径 capability 覆盖整个 settings 页(LLM 配置 + 路径 + 身份), 而非窄 `llm-config` 或不设 capability。
- **动机**: settings 有 region(§6 #12)却无对应 capability, 三维链路(节点 → 能力 → 区域)断了一环; 宽口径"一节点 = 一能力 = 一页"最简单直观, PM 取舍倾向整页内聚。
- 归属: 能力 `studio-settings` · 区域 `settings` · 平台 `gateway`(Python sidecar)。已登记 INDEX §6(13 → 14)。

### 00_settings 起草已落(2026-06-02)
- 产物: [`../mvp1/01_workflows/00_settings.md`](../mvp1/01_workflows/00_settings.md) —— 四旅程(General 身份/路径 · API Keys 凭证 · LLM Roles 角色→Model Group 映射 · Copilot 配置)+ 测试→持久化→投影(后端 SSOT 五态)+ 失败退路(含 D8 copilot session 失败退路)+ 下游硬依赖(predict/run/publish)。
- 接 API 方向已对齐 gateway mvp1: 编排(role→ResolvedRoute)/调用分离; base_url 归一化(头号根因); credential 不落明文(redact + secret 端点); 测试状态后端 SSOT(`project_provider_model_state` 五态 + SQLite health store); **数据层永不 Rust 化**(settings 不适用 D12 全量 Rust, 仅 OS 选目录走 native)。
- 现状落差(接线主工程): 后端 SSOT 已具雏形, 前端仍残留易失测试态(刷新即丢)需删除改投影; Copilot tab 仍 demo/mock 桩 + "假测试"(AsyncAnthropic ≠ ClaudeSDKClient)。
- 未过 PM 走查的 03–06 仍待下一步逐节点过(任务 A 不变)。

### 00_settings §3 细化 — 全 tab UX 动作目录 + PM 设计意图(2026-06-02)
- 产出工作目录: [`settings-action-catalog.md`](settings-action-catalog.md) —— 65 动作按用户 UX 流编号(壳层9 / General6 / API Keys16 / LLM Roles22 / Copilot12), 2 个 workflow 编目 + 对抗校验(分叉/status 全部坐实)。
- **PM 拍板设计意图(原话留底)**:
  > "2. Copilot必须做到全部功能齐全, 配置+真测试+存取draft, ux workflow用到的所有功能; 1. 全部; 7. ??全都要做完"
  - **Copilot(必须全功能)**: 不延后, 做到 = 配置 + **真测试(修假测试: 探针 AsyncAnthropic → 运行 ClaudeSDKClient 对齐)** + **draft 存取** + UX workflow 用到的所有功能。动机: copilot 是一等能力, 现状 mock/桩/假测试/分流 bug 不可接受。
  - **测试态 SSOT(全部)**: provider 测试 + role 测试结果全部后端 SSOT 落盘回填, 删前端易失层(roleTestStates / 前端 test_results 副本)。
  - **API Keys 7 个现状 vs 目标差(全做完)**: Manual probing 切方案 B(`/routes/{id}/probe`)/ Eye-mask 改 CSS 不切 native password / inline 一次填全 / Protocol 按目标处置 / 清 4 孤儿 / base_url 口径统一 / 状态术语统一(`ProviderUiState`)。
  - **推论**: 00_settings §3 写**目标态(全功能)**, 现状的桩/易失/假测试/孤儿一律标「现状 gap → 接线工程」, 不作已接受限制。
- **走查方式(PM 指示)**: 一个 stage 一个 stage 抛全文在 chat 过(不看文档), 逐块确认后再并入 00_settings.md §3。

#### ⚠️ 权威源链 + 认知纠正(2026-06-02, 读完真实 spec 后 —— 关键)
> PM 原话: "我写过好几遍整套api key + llm role 的用户ux workflow了, 为啥还是不同步呢" / "首先你得去看代码真的是长什么样的, 不能只看文档…其次, 你要去读 gateway相关的后端实现mvp1 对齐的部分"
- **教训(铁律重申)**: 之前从「现行(已漂移)代码 + baseline 摘要 + 子 agent 转述」倒推 settings, **没读 PM 亲手写的权威 UX spec** → 反复不同步、拿 drift 当设计。
- **权威源链(锁定)**:
  - **v4 registry 生产契约** = `.kiro/specs/llm-provider-intelligence-v2/`(provider_endpoints + provider_routes + route_id;`GET/PUT /api/llm/registry`、`POST /endpoints/{id}/test`、`POST /routes/{id}/probe`)。
  - **API Keys UX 最新权威** = `.kiro/specs/studio-api-keys-regression-hardening/`(2026-05-25 Implementing)。`studio-api-keys-redesign/`(v2.1 flat-credentials)**仅作删除前 UX 参考**, v3 路径(`/providers/test`、`/credentials`)不恢复。
  - **LLM Roles UX 权威** = `.kiro/specs/studio-llm-roles-model-groups/design.md`(Model Group 两级 + 三状态源域 + 5/4/3 态)。前端切换 = `studio-llm-roles-frontend-cutover`。
- **认知纠正(我之前错的,以 spec 为准)**:
  1. **「official 异步批量 job / tp 同步单发」不是设计意图, 是现行代码 drift**。权威 = **统一一条 `POST /endpoints/{id}/test`**(models-list → upsert routes → 刷新 registry 投影), 官/tp 同一流程。
  2. **mask**: 权威要 `type=text` + **CSS mask** + 显示/隐藏 + 复制(本地 InputGroup, regression Req5.3/5.4);现行代码 `type=password` 切换是**已知 deviation**(regression design.md:51 自列)。
  3. **official/third-party 物理分区是设计意图**(Req5.1/5.2: official 预渲染 5 厂商隐藏 name/base_url + 稳定 endpoint id, tp 用户自增可编辑), 非 drift。
  4. **状态标准 roles design 已定义, 对齐不重发明**: 三源域 **Identity / Capability / Health**;Provider UI **5 态**(route 级, 优先级 Off>NeedsSetup>CoolingDown>Ready/Untested);Role Fit **4 态**(role-local 派生, 从不改全局 health);Admission **3 态**;reason_code 仅细节;legacy RouteStatus 仅兼容投影。铁律: 「单个 status enum 不得当 UI/测试/admission/health 的统一真相」。
  5. **SSOT**: 前端不持第二份业务真相, 全从 v4 registry 投影(test 状态←endpoint record;available_models←provider_routes by endpoint_id;route status/cap←route record)。
- **我列的"7 个 open question"实为这套 spec 的 deviation 修复清单**(Manual probing 切方案 B=Req5.7;mask=Req5.3;official/tp parity=Req5.1/5.2;SSOT=UX Amendment;state 投影=roles design)。PM 已拍"全做完"=按 regression-hardening Phase1/2 落地。
- **endpoint 身份**: 一个 endpoint = 一个 base_url(host 推出稳定 endpoint_id)+ 一个 protocol(`Available SDKs`=`[endpoint.protocol]` 单协议);endpoint→route 1:N。"一张 card 两个 URL"= 两个 endpoint(数据模型支持), 但**未在已读 spec 找到明文 UX 要求** → 待 PM 指来源/确认是否立规格。

#### PM 口述权威 UX 落地 + 第三轮(2026-06-02)
- PM 亲手写了 [`00_settings-ux-spec.md`](../mvp1/01_workflows/00_settings-ux-spec.md)(§0 verbatim 原话)= settings 三页**权威细粒度 UX**;`00_settings.md` §3 已链接。我反复不同步的根因到此闭环。
- 关键补正(以此 spec 为准):① **official 只 get-models 不 probe**(我"official 异步批量探测建档"描述作废, 是漂移代码);② **route 级状态新增第 6 态 🔵蓝「以前联通过」**(draft 回填的历史连通, 介于 untested 与 verified)→ gateway `project_provider_model_state` 从 5 态补 6 态;③ **draft 赋能/写回**是核心机制(拉 draft 回填已证实资料 + diff 写回), 我之前当旁路 advisory 低估了;④ **测试落点**: endpoint 验证在 API key 页(轻量: 连通/get-models;第三方加一次单模型测), model「保证能用」真 probe 在 role 页。
- **#B(Claude 待核实, 不问 PM)**: list-models 是否每 protocol 都带 capability, 还是只 anthropic → 查各 provider list-models 文档后回填 spec §5。初判: gemini 带 token 上限/方法、anthropic/openai 基本只 id(待文档确认, 不凭记忆写进权威)。
- **#D 多 URL per card(PM 第三轮新增, optional)**: 第三方 card 多 base_url → 各成独立 endpoint(探协议+验证)+ 模型合并。Claude 评估: 不难, 但与 model-group 跨 endpoint 合并的兜底能力**重叠** → 标可选/低优先。已记 spec §1.2 + §5 #D。

#### Stage 0(壳层)走查结论(PM 2026-06-02, 原话留底)
> "1. 做一个适应, 打开setting时, 如果窗口比较小就自动收起两边的侧边栏, 这样比较方便; 打开setting page时, 再点击一次toolbar的setting图标, 关闭setting页面; 2. …这不必要吧? 这个应该不需要用户感知. 但是如果拉取不了,网络连不上之类的, 可以显示一个网络连接不上警告标志; 3. A.是这么设计的; 4. B.我上面说了, 没说的就没问题"
- **#1 overlay**: 保留 center overlay 不卸载工作区(设计意图)。**新增**: (a) 打开 settings 时窗口较小则自动收起两侧栏(文件树 + copilot); (b) settings 打开时再点 Toolbar Settings 图标 = 关闭(toggle)。
- **#4 保存反馈**: ✘ 不做全局保存徽章 —— 正常保存**静默**、用户无需感知。**改为**: 仅在拉取失败 / 网络连不上时显示「网络连接警告」标志。动机: 自动保存是后台行为, 用户只需感知失败不需感知成功。
- **#2/#5/#6/#9**: 壳层统一骨架/就绪态、WS 重连 + 日志(违 logging 铁律须补)、四 tab 全包错误边界 —— 均按目标补齐(PM "没说的就没问题")。WS/拉取失败的用户面出口 = #4 的网络连接警告标志。

#### Stage 1(General)走查结论 + git/publish 定调(PM 2026-06-02, 原话留底)
> "整套gitea 部署起来麻烦吗? 这个功能其实我现在还没有碰过, 因为现在没那么紧急, 保存在本地够用, 只是占了个坑"
- **核实(亲验 file:line)**: "git/发布"是 3 套独立机制 —— ① **Gitea** 团队协作(host + token + user_id=owner; push 靠系统 git 凭据)② **Artifact Registry** 发布(host + token; publish 走这条**不走 git**, 亲验 `skills.py:266-283`)③ 系统 git 推拉凭据。现状 UI 只有 `gitea_host` + `user_id`; registry host/token + gitea token 全是 `STUDIO_*` env、**无 UI**(`backends.py:38-41`)。
- **PM 定调**: 团队协作(Gitea)+ 发布(Registry)= **占坑 / 低优先**, 现在只用本地 git commit 保存即够。→ 00_settings 把「团队协作 / 发布 / 其鉴权」标 **target-design(占坑, 先不全做)**, 不现在扩 Gitea/Registry token UI; §6 的 publish 依赖相应降级为「占坑/未启用」不写硬依赖。
- **General 现役字段(保留, 非占坑)**:
  - `user_id`: **本地保存也在用** —— 本地 git commit author = user_id(`git_local.py:309-313`)+ 未来 Gitea owner / 发布 author。强制非空(publish/team-save 空则 400)。
  - `default_skills_directory`: 新建 skill 默认落点(`skills.py:495-499,577-581`; WelcomePage 默认父目录), 新模型仍用、非注册表遗留。
  - `gitea_host`: 占坑字段, 留位不深做。注: 现有 env(`backends.py:110`)+ app_settings 双源, 未来真做时统一到一处。
- 注: skill CRUD/workspace 隔离那条 user_id 来自**认证层**(`get_auth_user_id`→现 auth_type=none 返回 env default_user_id), 与 app_settings.user_id 两个来源; 未来上 login 须理清。

---

## 批次 1+2 残留确认 + 子图 path / .workspace / 字段对齐 (PM 2026-06-02 续)

> 触发: PM 逐条确认 01_init / 02_authoring 的「待定」残留 + 抛 3 个新校正。本轮先核实代码+文档再落决策。
> ⚠️ 教训复盘: Claude 两次未核实就下结论(① 1-4 误判"空文件夹+copilot", 实际 `create_skill` 本就建模板; ② 误称 .workspace "规范没定义", 实际在 `workspace-spec/baseline.md`)→ 违 verify-before-concluding, PM 两次纠正。
> PM 原话留底:
> - "1-1删;1-2A;1-3删;1-4 init不是空文件夹, 还是要建一个模版文件夹的, 和copilot没关系, 不会自动调copilot; 1. git init; 2. .workspace 文件夹必然要用到的文件结构树; 3. 一个graph.md 必然要用的, 里面yaml 的基础配置那name,还有啥?; phase文件夹"
> - "1-4 a我觉得要用1个logic节点 接一个 1个agent节点, 算是初始化模版吧, 比较常用的组合; b修;c 要"
> - "子图还有一个需求是, 现在没有注册表, 所以子图需要指定path才能导入到工作区里面, 这应该是subgraph节点里面要新增的, 还有agent phase里面的子图也是一样."
> - ".workspace 肯定有spec 的, 仔细找, 但他不是最新的, 需要根据最新需求更新" / "字段可能会有更新要根据最新的功能设计关联" / "关联功能要互相引用, 才不会丢失认知; 链接一份文档, 唯一真相源"

### 01_init 待定 → 决策
- **D-1-1 删 Config drift 徽章**: 去注册表后 git-remote 比对告警(`config_arbitration.py` + `WelcomePage.tsx:431-457`)失触发点。动机: 注册表时代产物, IDE 模型下无落点。
- **D-1-2 Recent 卡片极简(选 A)**: 只存路径+名(MRU localStorage), 不再后端 `GET /skills` 聚合富元数据。动机: Home=纯入口, 极简够用且省后端调用(对齐 D6)。
- **D-1-3 import 校验门全删**: `services/skills.py:517-525` 打开时 GRAPH/SKILL 存在校验 + 非阻断 lint 一并删, 开任意文件夹零校验, 全交 compile+copilot。动机: D2"屎都改成标准 skill"。
- **D-1-4 新建 = 模板文件夹(非空、不调 copilot)**: 纠正前版"空文件夹+copilot"错判。落地 = git init + `.workspace/`(空,运行时填) + `GRAPH.md` + `phases/`。起始模板 = **1 个 logic 节点 → 1 个 agent 节点**(常用组合)。
  - (a) 起始结构 = logic→agent 串接(非单 init)。
  - (b) 修脚手架: 现 `_SCAFFOLD_FILES` 的 LOGIC.md 缺 03-logic 必填 `name`/`actions`(不合 FROZEN)→ 按新模板重写。
  - (c) `.workspace/` 入 `.gitignore`(运行产物不污染 git)。
  - 动机: 新 skill 立即可编辑/可编译、不依赖 copilot 在场; logic(确定性预处理)→agent(LLM 主体)是最常见起手式。
  - 代码佐证: `create_skill` 已 git init+建 .workspace+写 scaffold(`skills.py:558-560`), 方向本就对, 仅模板内容按 FROZEN 重写。

### GRAPH.md 字段真相(答 PM "name 还有啥", 权威=02-graph-md-spec FROZEN)
必填: `name` / `schema_version:"v0.3.0"` / `io`(inputs+outputs inline JSON Schema) / `phases:list[str]` + body `<phase depends_on>` 拓扑。可选: `llm_role`(默认 analyst) / `description`。**无 `type:simple/graph`**(伪字段)。

### 新需求: 子图 path 引用 + 导入(去注册表化) — 新 FROZEN 改动 #5
- **冲突**: FROZEN `04-subgraph` 的 `target_skill`=skill id(靠 SkillResolverProtocol/注册表解析), 与 D1/D7/D11 无注册表冲突。
- **决策(对齐 D7)**: 子图改**按 path 引用**(直接写子图文件夹路径, 无 id→path 注册表)。两处落点: ① `SUBGRAPH.md` 节点字段; ② Agent 节点 `subgraphs[]` 每项(subagents[] 同为 cross-skill 引用, 是否一并待确认)。
- **导入流程(V0.3.0 需求1 去注册表重写)**: 按 path 解析; 不在工作区→assets 面板 subgraph 类目标红→点击弹 OS 选文件夹→add-folder-to-workspace。归 `skill-workspace` 能力 + `assets` region。
- **动机**: 无注册表下 path 即物理地址(D7); 导入=把被引用子图纳入工作区(同 IDE "add folder to workspace")。
- ✅ **PM 拍(2026-06-02)**: `target_skill` → **改名 `path`**(直接写子图文件夹路径)。落地见 [phase-editing 能力文档](../mvp1/02_capabilities/phase-editing.md)。

### 字段对齐最新功能设计(G2/G3 已锁)
- **G2**: 子图 io 删严格 1:1, 改黑板字段过滤(同任何节点)→ 子图节点 io 校验按放宽写; 关联 canvas REQ-2 字段勾选。
- **G3**: 所有节点 `io.outputs` 加可选 artifact 落盘路径标注(产出写成 .json/.md)→ Agent/Logic/Subgraph io.outputs 表单都含此项; 关联 .workspace artifacts。
- **G2 文件导入**: 任意 i/o 面板可导入文件→注入黑板(时机 a: 跑到该节点才注入)。

### .workspace 规范定位 + 更新点
- **唯一真相源** = `docs/engine/mvp0/workspace-spec/baseline.md`(Round 31)。结构: `runs/<run_id>/`(trace.jsonl/result.json/final_state.json/metrics.json/artifacts/) + `golden/<baseline_id>/` + `test_inputs/`。
- **过时点(PM "需更新")**: G3 要作者声明产出默认落 `.workspace/artifacts`(顶层持久), 现规范只有 `runs/<run_id>/artifacts/`(per-run 临时 sidecar), **缺顶层 artifacts**。G3 自标"artifacts 默认目录组织待想清"。→ **更新点**: workspace-spec 加顶层 `artifacts/`(作者声明持久产物)区别 runs 内临时; 语义边界待定稿。

### 唯一真相源 + 交叉引用原则(PM 锁)
- **字段定义 SSOT**=引擎 FROZEN skill-spec(02/03/04/05); **.workspace SSOT**=workspace-spec。Studio 文档**只链接不复制**(防 drift, 对齐 L1 + INDEX §2 所有权不变量)。
- **交叉引用网**(关联功能互引, 防丢认知): 节点字段→FROZEN spec; io.outputs 落盘→G3 + workspace-spec(artifacts); 子图 path→D7 + skill-workspace(导入) + assets(subgraph 类目) + V0.3.0 需求1; 子图 io 过滤→G2 + canvas REQ-2。
- **FROZEN 改动清单更新**: 原 4 条 + 本轮 **#5 子图 target_skill→path(去注册表)** + **#6 workspace-spec 顶层 artifacts(G3 配套)**。

### catalog 待定状态
- 01_init 4 条 + 02_authoring 脚手架/Half B 本轮已解决; 待并入 catalog 各节点章节(子图 path 字段微选择确认后统一改)。

---

## 01/02 完整动作表 review — 5 条修正 (PM 2026-06-02)

> 触发: PM 审完 01_init(18)/02_authoring(17+1)完整动作表后抛 5 条。原话留底:
> "1. 'Delete...' 抄cursor, 现在不需要删除skill 功能, 要删的话用户自己去系统文件夹删, recent skill 如果这条记录的dir path消失该怎么办, 自动消失, 还是点击报错? 2. 设计阶段标注整个欢迎屏逻辑确保抄cursor/VS code, atom actions没问题 3. #3 还有input files选项, input路径(新增engin功能, 任何节点都可以导入新文件) 4. #6 需要完整设计, 现在拉开线的一头, 不会自动断链 5. 提醒:asset里面的subgraph文件夹要和subgraph节点文件同步, 删掉subgraph节点时, asset也要对应的删掉"

### R1 [决策] 删除「删 skill」功能(抄 Cursor)
- 01_init 动作9「Delete(从最近移除)」**整条移除** —— Studio 不提供删 skill 功能; 要删让用户自己去系统文件夹删。动机: Cursor/VS Code 都不在 IDE 内删项目, Recent 只是入口列表不是文件管理器。
- ✅ **PM 拍(2026-06-02)**: Recent 记录的 dir path 消失(文件夹被外部删/移)→ **点击报错 + 自动从 Recent 移除**(VS Code 式)。理由: 极简 Recent 不预先读盘(D-1-2), 失效只在点击时发现; 弹"文件夹不存在/已移动, 已从最近移除", 既透明又自清理, 正好替代被删掉的手动删除功能。备选: 加载时 Rust 轻量 stat 置灰/静默剔除(预先读盘, 稍违极简)。

### R2 [决策] 欢迎屏逻辑 = 抄 Cursor/VS Code(设计准则)
- 01_init 整个 Home/欢迎屏交互逻辑**对齐 Cursor/VS Code**(Open folder / Recent / 强隔离工作区)。atom actions 已 PM 确认无问题。→ 写 01_init / skill-workspace 文档时标此准则。

### R3 [需求] i/o panel 加「导入文件」选项(= G2/FROZEN-3, 任意节点)
- 02_authoring 动作3(i/o panel)除 io/artifact 设置外, **加 input files 导入选项 + input 路径**: 任意节点都能导入新文件 → 文件字段注入黑板(新引擎能力, FROZEN-3, 时机 a=跑到该节点才注入)。非首 input 节点专属。落 phase-editing §5 [G2 文件导入]。

### R4 [需求·待设计] 连线/断连完整交互
- 现状核实: 建链=拖端口到端口(`onConnect`, GraphCanvas.tsx:319 live); 断链**仅右键边 Disconnect 菜单**(`onDisconnectConnection`:478); **无边端拖拽**(无 onReconnect/edgesReconnectable)→"拉开线一头不断链"属实。
- **设计(✅ PM 确认 2026-06-02)**: ① 建链(拖端口→端口, 已 live); ② **改链/重连**[新] 拖已有边的一端到另一节点端口 → 改 depends_on(旧删新加); ③ **拖拽断链**[新] 拖边端松手在空白 → 删 depends_on(直觉"拽开即断"); ④ 菜单断链(保留)。全经 Rust(D12)+ 改完触发 compile 重校验数据流。技术 = 启用 React Flow `onReconnect`+`onReconnectEnd`(空落=删边)。归 graph-authoring。

### R5 [需求] assets subgraph 类目 ↔ subgraph 节点文件 双向同步
- assets 面板的 subgraph 类目必须与各 `phases/<id>/SUBGRAPH.md` 节点同步: **删 subgraph 节点 → assets 对应条目同步删除**(反之新增/改 path 也同步)。防"节点删了 assets 还挂幽灵子图"。归 graph-authoring(删节点)+ skill-workspace(assets 渲染)。

---

## Part 3 (03_prediction) review — scope 质疑 + golden 机制设计 (PM 2026-06-02)

> PM 审 03 后抛 4 点。原话留底:
> "1. scope 范围确认, 原来skill lifecycle可能应该包含compile、predict、run、git保存分发? 现在关注predict , 我觉得 test input batch也很奇怪; 剩下的scope有没有其他part承载??
> 2. 3-2 看不懂. 为什么老是说事情没头没尾的,我说了不要默认我读过代码读过文档, 我不方便读
> 4. validate应该归这个scope管吗?"
> **point 3 逐字(关键 golden 机制, 勿用提炼替代)**:
> "我来模拟一下用户心智: 设计完compile没问题,第一次点击predict, 测试逻辑链路跑通没问题, agent node 状态从未测试变成逻辑OK(根据io设置), 测试完弹出popover 问你需不需要现在copilot帮你一起完成golden设计(?icon,解释一下golden是什么, 这套机制怎么运作的, 没有golden时, 只要运行一次predict或者run,都会弹一次), 用户选择要, 自动新建一个chat发送prompt(需设计) 给copilot, 帮你预测结果(copilot根据你的整个graph: 1. 分析你需要什么结果; 2.这个节点预计真跑起来会得到什么结果; 3. 分析差距, 建议修改方案), 直到你和copilot讨论出来golden是什么, 改变这个node的golden参数. 如果有多个agent 节点, popover依次弹出,确认完一个, 弹下一个; agent节点需要一个新状态标签, 有没有golden? 有的情况下predict按照golden输出走; golden相关设置放在i/o 面板, 因为和输出什么直接相关; 没有golden时,会根据输出schema自动创建一个符合schema的golden模版, 你可以通过i/o panel, 打开golden的json文件, 手动填入golden数据; 一旦golden有数据了, 状态自动切换到golden, predict按照golden输出运行. run运行后可以进行实际结果和golden的diff对比."

### 回应 R-scope [厘清] skill 生命周期已拆分, 无遗漏
- 旧 `skill-lifecycle` spec = 历史大杂烩。现拆分映射: compile→`compile-lint`(node 02); predict→`predict`(node 03); run→`run-execution`(node 04); git 保存/发布→`publish`(node 06)+ autocommit(run-execution); golden 验收→`golden-eval`(node 06); 测试输入管理→`predict` 输入侧; validate(输入校验)→`predict`(node 03)。
- **PM 直觉对**: `test-inputs-batch` 名怪, 因它=「输入管理(predict 输入侧)+ 批量(run-execution)」两件事跨两能力拼凑。**建议解散此 spec**: 输入管理并进 predict 的 i/o 面板; 批量并进 run-execution。待 PM 拍。
- validate(point 4): 属 predict scope(试飞前校验输入合 schema), 归 `predict`(node 03)。

### golden 机制(point 3)— 组织 + gaps(待 PM 确认)
- **状态机(agent 节点新增标签)**: 未测试 → 逻辑OK(首次 predict 链路跑通) → 有golden。
- **mock 由 golden 状态自动决定**(取代手动 mock 选择器, 原 3-3 自动解决): 无 golden→启发式占位(免费验链路); 有 golden→predict 吐 golden(golden_case)。
- **golden 创建两路**: ① copilot 协作(popover→新 chat→分析图+预测真跑结果+差距建议→定 golden); ② 手动(按 io.outputs schema 自动生成空模版 json, i/o 面板打开填)。
- **golden 设置/文件**: 归 i/o 面板(因 golden=输出什么)。
- **diff**: run 真跑后 实际 vs golden 对比 → 归 golden-eval(node 06)。
- **关键 gaps(已在 chat 提 PM)**: (G-a)[最大架构] PM 模型 golden=per-node 作者期望值 vs 现后端 golden=whole-run 捕获快照, 两套模型需裁定取代/并存; (G-b) logic 节点真跑不需 golden; (G-c) golden 失效(节点编辑后旧 golden 标过时?); (G-d) popover 疲劳(每次弹→需"不再提醒/跳过"?); (G-e) 全节点有 golden 后 predict=纯回放, 价值在测未定 golden 的节点; (G-f) copilot golden-design prompt 待设计; (G-g) 现 409 守卫(predict trace 不可晋升 golden)与本模型一致——golden 是作者定/手填, 非从 predict trace 捕获。

### Part 3 review 续 — PM 修正 scope + golden 决策 (2026-06-02)
> PM 原话留底:
> "1. '输入', 输入什么文件不是已经在io里面设置了嘛? 每个节点都有自己的input配置, 输入什么文件. 为什么还要单独设置呢?...还有input validate为什么要单独拿出来讲, predict本来不就在validate整个流程吗?
> 2. scope的问题, 这个阶段就叫predict啊, 有什么问题? input 和batch 都是节点配置问题, 和predict无关, predict和run就是按照配置来跑就行了
> 3. ...存档应该和发布分发放一起, 都是git的功能. golden验收怎么又和发部分放放一块了呢?
> 4. g-a 取代; g-b对;g-c不用;g-d 看改什么, 改prompt,改agent内部设置都没事, 只有改输出schema后, golden字段缺失需要的字段, 需要弹警告⚠️,触发编译错误, 必须补上才能跑predict; [g-e 见下]; g-f OK
> 5. 作为workflow的scope, 我觉得predict+run+golden可以放在一起"
> g-e 原话: "把他放到tracing里面, predict的tracing, 如果agent 的节点用的是占位, 旁边多一个按钮, 直接让copilot设计golden; 再一种方案, 用sonner弹出确认框, 是否让copilot设计, 点确认一次性新建多个chat, 同时开始分析设计没有golden的节点"

#### [纠正] predict scope = 纯"按配置试飞"; input/validate/batch 不是 predict 独立议题
- **input(输入什么文件)= 每个节点的 io 配置**(i/o 面板, phase-editing 已覆盖); predict 按配置跑, 不单独设。
- **validate = predict 流程内的一步**(跑前校验输入合 schema), 非独立议题。
- **batch = run 配置**, 与 predict 无关。
- ⇒ 之前给 03 列的 3-1(改名)/3-2(输入入口)/3-5(validate) 均为 Claude 过度复杂化造出的**伪问题, 撤回**。predict 阶段就叫 predict; 03 真正内容 = golden 机制。

#### [重组] workflow 阶段后半段(待 PM 定 debug 归属)
- **纠正**: golden 验收**不跟 publish**(之前错误把 golden+publish 塞进 06_eval); 存档**跟** publish(都是 git/分发)。
- **运行与验收** = predict(试飞)+ run(真跑)+ trace(看结果)+ golden 验收对比(= 旧 03+04 + 06 的 golden 部分)。
- **保存与发布** = git 存档(成功 run autocommit)+ 发布分发 publish(= 旧 04 autocommit + 06 publish 部分)。
- 注: 仅重组"旅程阶段"归类; 底层能力(predict/run-execution/golden-eval/publish)仍各自独立。
- ✅ PM 定(2026-06-03): debug(trace 去黑盒+续跑)**并进"运行与验收"**(选 A)。→ "运行与验收" = predict + run + trace + golden 验收 + debug 续跑。

#### golden 机制决策(g-a..g-f 已拍)
- **g-a 取代**: per-node 作者期望值 golden 取代现后端 whole-run 快照。
- **g-b 对**: mock 由 golden 状态自动决定(无→占位 / 有→吐 golden); 不要手动 mock 选择器。
- **g-c 不用**: logic 节点不要 golden。
- **g-d golden 失效条件**: 改 prompt / agent 内部设置**不失效**; **仅改输出 schema 致 golden 缺新要求字段** → ⚠️警告 + 触发编译错误, 必须补齐缺字段才能跑 predict。(golden 绑输出 schema, 不绑 prompt。)
- **g-e popover 替代 ✅ PM 定(2026-06-03)= 两者都要**: ① trace 内占位节点旁挂"让 copilot 设计 golden"按钮(默认·单点·不打断); ② sonner 确认框 → 一次性开 N 个 chat 批量设计所有未定 golden 节点(批量入口)。
- **g-f OK**: 全节点有 golden 后 predict=纯回放, 价值在测未定 golden 节点。

### 04 run/trace/batch review — PM 深度设计 8 点 (2026-06-03)
> PM 审 run 后抛 8 点。**关键纠正**: predict 是真跑硬前提(Claude 上轮 run #1 说反)。**核心新设计**: batch≠loop 两机制 + 顶层 range 级联 + 模型对比测试。原话逐字留底:
> **P1 动画统一**: "运行时加线的动画(已有)和节点边框的动画(再setting里面的role test, 测试时的边框动画统一)"
> **P2 trace 入口+行为**: "'Trace Timeline' 按钮 这应该是trace的入口; run行时自动打开这个panel, 实时看到tracing的返回结果(流式输出, agent也需要流式输出, 输出内容为摘要折叠, 点开可以看具体内容, 就和所有的copilot输出一样); run完,变成看trace的入口: 每一次predict、run的列表, 点击展开概要(focus在空白canvas), 点击button(看完整trace),trace面板变成完整的trace timeline, 并打开edit窗口, 只读看完整trace文档; 点击一个node, tracing变成该node(start-->end)最近的一次trace timeline记录, 编辑器文档直接跳到该node范围(node中间的过程点击线中间的dot)"
> **P3 batch vs loop(逐字关键)**: "批量运行的逻辑要总体重新设计; story-deconstruction: 1.整体: 100章(chapter001.md...或chapter001-010.md+metadata.json标行号, 或json)→节点1 ABC分段→100章segment; 节点2整合event-timeline; 节点3解构分析; 每节点都是subgraph, 流程线性无batch. 2.深入subgraph: (a)分段 batch100次每章不参考上章并发(每批xx章); (b)event-timeline 第一步每章分段合并成event并发100章, 第二步把100章event合起来整合成一条timeline(章节断层处分析是否合并)需loop一章一章往上拼非并发; (c)story-analysis 多并行节点各负责不同任务(情绪节奏/时空元素/伏笔埋收/角色资产...)复杂节点又是subgraph; 两种方式: ①每个并行节点互不相关独立loop n次(按event或某字段分, 已不是按最初100章分); ②每节点相关整体loop n次每次7节点全跑完下次每节点输入整个loop完成后所有节点结果. 3.batch和loop是两个不同机制, loop每次输出进下次输入, 状态机怎么存储、节点怎么配置都需仔细设计"
> **P4 顶层 range(逐字)**: "最顶层设置跑'多少章'放最显眼位置频繁改动: 先测1章→2-3→10-20→全量100. 这数字整体影响后面所有设置, 顶层graph设10则所有子节点/subgraph按10章batch/loop; 甚至可设第50-70章, 可设这50章是否从之前数据拿第49章接着跑还是从50章从0跑; predict默认1-1, run默认覆盖所有"
> **P5**: "需要能够自动探测哪个字段是作为batch/loop的线索"
> **P6**: "predict是硬前提, 但是golden不是. predict的任务是把逻辑跑通确认逻辑、输入输出schema等真的没问题才能进入run; 有没有golden的区别只在于predict在agent节点拿哪个mock数据输出而已"
> **P7**: "单次Run和批量Run的入口 在io panel OK; 但模式变成两种, ①序列化batch/loop, ②单线程跑只是给不同输入(非必要可有, 增复杂度?没有也不影响, 换输入再测即可; 有且UI不增复杂度最好, 可自动探测或归一化?)"
> **P8 模型对比测试(逐字)**: "run的properties设置里加模型对比测试: 这节点设了用哪role跑, 下方点击添加对比测试的llm(不写入skill.md, 后续节点仍拿设好的role结果, 纯对比这节点不同llm的不同输出); 点加号弹选择框, 可选设好的role, 也可选单独model group/bundle→选哪个endpoint/自动fallback(解析成临时包装的role加入model group/bundle和其endpoints); 看该节点tracing时可切换看不同llm结果"

#### 决策 + 纠正
- **[纠正] predict = run 硬前提(P6)**: compile→**predict(验证逻辑+输入输出 schema 真通)**→run。golden 非前提, 仅决定 predict 在 agent 节点用哪份 mock(无→占位/有→golden)。**上轮 run #1「predict 非硬锁」作废**。
- **[确认] P1 动画统一**: 运行态节点边框动画 = settings role-test 边框动画。
- **[确认] P2 trace 入口正名**: Toolbar 'Trace Timeline' = trace 入口(非 run 历史)。
- **[确认] P7 run 入口在 io panel**。

#### 核实: 引擎无图层级 batch/loop 通用原语
- 引擎 "loop" 仅 = LoopDetectionMiddleware(检测 agent 卡死)+ ReAct 内循环; **无"batch N / loop N 累积"图层原语**。
- story-deconstruction 现为**手写 phase `batch_loop`** 硬实现。⇒ 通用 batch/loop = 真设计需求, 跨 engine+studio+状态机。

#### 四大机制 organize + gaps(待逐个深设计)
- **A. batch vs loop(最核心, P3/P5/P7)**: batch=并发独立各跑各(每批 xx); loop=串行上次输出→下次输入(需状态机累积)。gaps: 节点配置(once/batch/loop?)、迭代线索字段自动探测(P5)、loop 状态机存储、story-analysis 两模式(独立 loop vs 整体 loop 全节点)、引擎需补图层原语、P7 单输入模式归一化。
- **B. 顶层 range 级联(P4)**: 顶层设"跑多少/哪段"→级联所有子节点/subgraph 范围; 子段(50-70)+续跑(从第49章数据接 vs 从0); predict 默认 1-1, run 默认全量。gaps: 级联怎么传到子图、续跑数据从哪取、与线索字段关系。
- **C. trace 行为(P2)**: run 时自动开 panel + 流式(agent 也流式, 摘要折叠, 同 copilot); run 后 = 回看入口(predict/run 列表→展开概要 focus 空白 canvas→button 看完整 trace timeline + 只读 editor→点 node 看该 node start-end 最近 trace + editor 跳该 node 范围, 中间过程点线上 dot)。
- **D. 模型对比测试(P8, 新核心)**: run properties 加对比 llm(不写 skill.md, 不影响下游, 纯比本节点不同 llm 输出); 加号选 role 或 model-group/bundle→endpoint/fallback(临时包装成 role); trace 切换看不同 llm 结果。gaps: 临时 role 包装、对比运行触发/存储、trace 多结果切换 UI。

### run review 续 — 7 点 + 元要求 (2026-06-03)
> PM 原话留底:
> "1. 我觉得要把compile也放到这个scope范围, 前面我都没有什么印象确认过compile的内容
> 5. batch/loop设计想法: 设置开关两处: 1.graph.md整个graph batch/loop; 2.每个节点的batch/loop; 3.复杂结构用subgraph解耦, 在subgraph的节点subgraph.md设置batch/group, 子图自动继承这个参数但不会保存到子图的graph.md(通过父图batch/loop调用子图, 子图本身只运行1次; 如果父图subgraph.md设了10次, 子图graph.md也设了10次, 嵌套调用总共100次)
> 6. 并联节点连线问题, 并联节点的出发点应该不是上一个节点的handle, 而是中间的点, 连线时的操作还是连节点的handle,但是显示线是从dot出来的, 这样也符合逻辑; output同理
> 7. input/output 直接改成大一点的原点, 不要用节点的形式了, 这样和graph.md的phase语义对齐"
> (元要求 2/3/4 = 原话永久化 / 测试关键点 / 框架 → 落 [DESIGN-PROCESS 框架](../../DESIGN-PROCESS.md))

#### P1' [scope] compile 并入「运行与验收」+ 待走查
- compile 是 run pipeline 的入口门(compile→predict→run), 归「运行与验收」scope。**其内容 PM 未走查过, 待逐块走查。** 02_authoring 保留编辑期实时 lint; compile 门控移入运行验收(边界走查时定)。

#### P5' [batch/loop 配置模型] 三处开关 + 嵌套(deep-dive 输入)
- 开关三处: ① **GRAPH.md** 整图 batch/loop; ② **每个节点** batch/loop; ③ **SUBGRAPH.md 节点**设 batch/loop → 子图**继承但不写进子图 GRAPH.md**(父图通过 batch/loop 调子图, 子图本身跑 1 次)。
- **嵌套**: 父 SUBGRAPH.md=10 且 子 GRAPH.md=10 → 嵌套 10×10=100 次。
- ⇒ batch/loop deep-dive 的核心配置模型, 下一轮展开。

#### P6' [canvas] 并联连线从 dot 出, 不从 handle
- 并联节点连线**视觉上从中间 dot 出发**(非上一节点 handle); 操作仍连 handle, 显示从 dot。output 同理。归 graph-authoring(canvas); 关联 R4 连线设计 + P2 线上 dot。

#### P7' [canvas] input/output = 大原点, 非节点形
- input/output 渲染成**大圆点**(非矩形节点), 与 GRAPH.md 语义对齐(input/output 是 `depends_on="input"`/`output` 标记, 非 phase)。归 graph-authoring。

### 走查覆盖审计 (PM 质疑"前两趴怎么过的", 2026-06-03)
> PM: "'它的内容你确实没走查过' 那怎么前两趴就这么过了呢? 还有没有这样的情况"
> 诚实结论: 节点级 table-review 会让"夹在表里的能力"(尤其 compile)skate by。

| capability | 走查深度 | 说明 |
|---|---|---|
| skill-workspace (01) | ✅ 充分 | 残留逐条 + PM 明说"atom actions 没问题"(R2) |
| phase-editing (02) | ✅ 充分 | 字段集 / golden-eval 深设计 |
| graph-authoring (02) | 🟡 部分 | 连线 R4 / 画布 P6-P7 已查; 拓扑/新建节点仅表级接受 |
| **compile-lint** | ❌ **未走查** | 02 表里 2 行(Lint+Compile / Predict门控)skate by; **PM 捉到**, 归运行与验收待走查 |
| **file-editing** | ❌ 未走查 | Monaco 编辑器仅表级出现 |
| **conflict-overwrite** | ❌ 未走查 | 顺序覆盖 1 行, 表级接受 |
| **copilot-assist** | ❌ 未聚焦 | 01 仅"出现时机/D8"; chat/建技能/judge 能力未单独走 |
| predict (03) | ✅ | predict + golden |
| run-execution | ✅ | run 表 + 3 决策 |
| golden-eval | ✅ | 机制深设计 |
| studio-settings (00) | ✅ | S1/S2 + stages |
| trace-observability / debug-resume / publish | ⏳ 待走查 | 明确 pending |

- **教训(并入 [DESIGN-PROCESS](../../DESIGN-PROCESS.md) 反模式)**: 节点级走查必须按 capability 逐项点名, 否则跨能力内容(compile)被当一行带过。
- **补走查 backlog**: compile-lint(运行与验收时一并)、file-editing、conflict-overwrite、copilot-assist。

### P2'' [术语] input/output = 一对端点标记, 区别于 phase 间 depends_on
- 入口表述为 **input**(配对 **output**), 不写成 `depends_on="input"` —— input/output 是图的端点, 与 phase↔phase 的 depends_on 两回事。关联 P7(input/output 大圆点)。⚠️ 现 FROZEN GRAPH.md 用 `depends_on="input"`; 本条是概念/UI 表述, 是否改 spec 语法待 batch/loop 深挖定(input 端点是 batch/loop 迭代施加点)。

### batch/loop 深挖 — Phase 1 现状核实 (2026-06-03)
- **无声明式 batch/loop**: story-deconstruction `batch_loop` = 手写 Python LOGIC action(`run_batch_loop.py`): 硬编码 batch_size=10、硬编码维度、手动 for 循环批次调 `run_skill(batch-analysis)`、手动 `accumulated_context` 累积。= 要替换的 ad-hoc。
- **引擎有并行 fan-out 原语**: `graph_assembler.py:1249` `asyncio.gather(*[_run_one(i,item)...])`(subagent 并行跑一组 input)——"并发跑一组"引擎能做, 未暴露为可配置节点能力。
- **loop 累积手写**: 无声明式"上次输出→下次输入"状态机。
- ⇒ 核心挑战: 把"手写 Python + 引擎内部原语"变成**声明式可配置 batch/loop**(graph/node/subgraph 三处 + 迭代字段自动探测 + loop 状态机)。

### batch/loop 深挖 — Phase 3 范围模型纠正 + 转 Gemini 分析 (2026-06-03)
> PM 纠正 Claude Q3(range 与 batch/loop 非正交)+ 转 Gemini。原话:
> "1. 这需要engine去设计 [loop 状态机]
> 2. (图级 loop 写在 GRAPH.md,节点级写在节点)? 对
> 3. 我的理解是顶层range设置的是这个图整体的batch和loop: 图3节点/input10个/图设batch/loop范围3-6 → batch:并发跑3、4、5、6,每个进程顺着3节点走一遍; loop:3输入顺着3节点走输出, 4拿3的结果和4的输入顺着3节点走...直到最后. 图没设而第2节点设范围1-2: 这节点自己跑1-2的输入batch/loop. 图和节点都设: 嵌套, 每个进程走到第2节点时第2节点自己跑完batch/loop再继续下一节点."
> "我希望你深度思考这个问题, 同时写一个prompt写清楚情况和你没法想通的难点, 我让Gemini分析怎么解决怎么设计"
- **[纠正] range 不与 batch/loop 正交**: range+mode 一起作用在一个 **scope**(图级/节点级)。**图级** = 整图当迭代单元(每次迭代跑完所有节点); **节点级** = 单节点迭代; **嵌套** = 图级进程走到某节点时该节点再子迭代(父 N × 子 M)。
- **[确认 P2]** 图级 loop 写 GRAPH.md, 节点级写节点(两种都支持)。
- **[P1] loop 状态机归 engine 设计**。
- **决策: 转 Gemini 深度分析(PM 指定)**。prompt 存档 [gemini-prompt-batch-loop.md](gemini-prompt-batch-loop.md), 含 4 难点: ①loop 累积态结构/传递/持久化续跑 ②迭代粒度沿图变化(章→事件) ③图级 vs 节点级 loop + 嵌套 ④落到"跑一遍 DAG"的现有引擎。

---

## 00_settings §2 LLM Roles — 原子动作全量走查(PM 2026-06-03 第二轮)

> 触发: PM 纠正"别用锁定跳过, 上一 part 底层改动 + gateway 最新 mvp1 设计影响这两页, 全局重过; 按 workflow 原子动作顺序全量走; 代码校对自己做或 Codex, 别甩 PM"。
> 方式: 整合三股改动(ux-spec 6 态/draft + 上一 part P8/D10/D12 + gateway mvp1 契约)重走 Roles。**12 条裁定原话 verbatim 已全量进** [`00_settings-ux-spec.md` §2.0](../mvp1/01_workflows/00_settings-ux-spec.md)(SSOT, 本日志只记决策+动机+指针, 不复制原话防漂移)。
> 现码地基(亲验 file:line, 非转述): Roles 前端 cutover **已落地**(`AvailableModelsSidebar` 真读后端 `model_groups`, `:57`);gap 在后端(`project_provider_model_state` 5 态不读 draft `:12`、`probe_import_draft` 桩 `llm.py:872`)。gateway 已读 03/05 对齐(base_url 保存时归一化、`build_runtime_setting_descriptors` 驱动 intent 控件)。

### 12 条裁定 → 决策 + 动机(原话见 ux-spec §2.0)
1. **#1 model family 折叠**: 侧栏按 family 分区可整体折叠(anthropic 等), 隐藏其下模型。动机: 长列表收纳。视图态(localStorage), 不入后端。
2. **#2 thinking 三档换控件**: off/preferred/required 互斥 → **单一三态控件**(非两开关)。动机: 三档互斥用两开关表达不了。现码只 off/preferred 需换。
3. **#3 downgrade 默认策略无 UI**: 保持默认 allow, 不暴露 block/warn 控件。动机: 默认策略不需用户感知 → **撤回我上轮"补 downgrade UI"建议**。
4. **#4 intent 布局轻优化**: 只调布局不改逻辑。动机: 现布局偏丑。
5. **#5 删 RoleTestResultPanel + 清 tooltip**: 该面板 PM 已删不要(加重复杂度); fail 信息进 tooltip; provider row **嵌套 tooltip 冲突**清成**一个顶层 tooltip**。→ **推翻我上轮"挂载 RoleTestResultPanel"**。
6. **#6/#7/#8/#9/#12 bundle 与 role 高度统一**: Add Bundle 按钮与 Add Role 同位(#6); 束 Test 复用 role(#7); 束改名删除与 role 统一(#9); **束拖进角色=引用(同步)非快照**(#8/#12)——改束→所有引用角色跟着变。动机: 同录入/测试/生命周期 UI; 引用=共享组件语义。**覆盖 765 设计的"拖入=快照复制"。**
7. **#10 needs_setup 定义**(PM 问, 我答非反问): = **endpoint/credential 级硬缺口**(缺/错 key、base_url、protocol、model id)→"去 API Keys 页把 provider 配通才能用"。正交于: cooling_down(临时网络/限流自过期)、failed(endpoint 通但单模型 route 探失败)、disabled(用户关/模型下线)。两轴: needs_setup=provider 还没配通(endpoint 级); failed/disabled=配通但模型不行(route 级)。→ needs_setup **不进可用模型**。显示待 PM 点头(我建议组内灰显+引导修, 替代现状静默过滤)。
8. **#11 跨页 role 状态+快捷 Test**: 节点 Properties 面板每 role 旁加 Test 键 + 展示状态, 不必切 settings。动机: 在用 role 处就能验。复用 role 测试+状态投影, 跨 phase-editing region。
9. **#11 P8 认可**: run 模型对比测试复用 model-group/bundle→临时 role(复用 materializer + 临时 role 路径; run 引用 settings 的 bundle/group 不另存)。

### 落盘
- ux-spec §2 已从骨架**重写为细化定稿**(§2.0 原话 + §2.1~§2.9)。§6.2 层次表 ①② 行已更新。
- 代码校对纪律: Roles 现码落差(failed 被滤 `:385`/无弃用区/无蓝态/5 态投影/thinking 两态)均**亲验 file:line**, 未甩 PM; 残留可疑(modality 过滤是否已在 `_include_route_in_model_groups`)标"我待核 / 必要时 Codex"。
- 下一步: §3 Copilot 同样全量走查(桩/mock/假测试/分流 bug 更多)。

### §2 收尾确认(PM "都对")
- **needs_setup 显示 = 灰显引导(不隐藏)** ✅ PM 确认: 组内灰显 + 标「Needs Setup」+ 点击引导去 API Keys 修, 不静默过滤、不默认选。ux-spec §2.1 已加四态区分表(needs_setup/cooling/failed/disabled)+ §2.9 测试点同步。
- **#11 快捷 Test = 节点 Properties 面板** ✅ PM 确认: 不在设置页, 在用 role 的节点 Properties 面板(画布/运行), 跨 phase-editing region。

---

## 00_settings §3 Copilot — 原子动作全量走查(PM 2026-06-03 第二轮)

> 方式同 §2。**4 条裁定原话 verbatim 已进** [`00_settings-ux-spec.md` §3.0](../mvp1/01_workflows/00_settings-ux-spec.md)(SSOT)。现状定性: 桩/mock/假测试/bug 最多, 但 PM 早前拍"copilot 必须全功能不延后"→ 一律标接线工程非可接受限制。
> 现码 bug 全部亲验 file:line(非转述): 假测试 `_probe_copilot_sdk_tool_call` `llm.py:2150` 用 `AsyncAnthropic`≠运行 `ClaudeSDKClient` `copilot.py:242`; copilot_ 前缀分流 bug `selectModelGroup` `CopilotTab.tsx:219/232/242` 丢前缀 vs 后端 `_is_copilot_role` `llm.py:905` 认前缀; `void saveStatus` `:70`; mock 默认 props `:58`; `_resolve_copilot_route` 只取首条 `copilot.py:445`; 假徽章 `:79/:302`。

### 4 条裁定 → 决策 + 动机(原话见 ux-spec §3.0)
1. **#1 C10 选组器可搜索**: 选 model group 用**可搜索选项卡**(同 §2.1 可用模型搜索), 非裸下拉。动机: copilot 兼容模型可能多, 搜更快。
2. **#2 内置角色动态浮出 + family 偏好阶梯**: 不写死 2 个; **默认只浮出 Claude+DeepSeek 在 available 里最新最好的模型**: Claude 优先 opus4.8→退 opus4.7; DeepSeek 优先 V4Pro→退 V3.2Pro; 都没有则不浮出、用户自建。动机: 始终用当前最强默认 copilot, 不锁死旧型号。
3. **#3 eligible 判据对, 但未测不预过滤**: 用后端 capability(route 是否 anthropic-messages 兼容)判 eligible, 取代前端 `isClaudeAgentSdkCompatibleRoute` 名字启发式; **但 SDK 能力未测=未知, 不能据此滤掉**, 未测 route **仍显示在 available**(just keep them in there), 真 SDK 测试才确证。动机: 同 §2"untested 不滤"原则——未知不等于不可用。
4. **#4 "Backend Integration" 徽章 → 换统一 save-status badge**(PM 校正我"删"的答复): 不是删, 是把那个 header trailing slot 换成**和前两页一样的保存状态标签**, 接 Copilot 真 `saveStatus`(顺手修 `void saveStatus` `:70` 丢弃)。**依据 `FRONTEND_UI_SPEC.md:76`**("Settings 表单字段变更实时保存并显示保存状态、不放独立 Save 按钮")= "之前文档定过要统一"的规则。现状是**三份近重复** badge(`SaveStatusBadge` `ApiKeysTab.tsx:19` / `RoleSaveStatusBadge` `RoleBadges.tsx:5` / `AppSettingsSaveStatusBadge` `GeneralTab.tsx:12`)→ 应合并成一个共享组件, 四页共用。状态集 idle→静默不显 / pending/saving/saved/failed 才显(`RoleBadges.tsx:5`)——**与 Stage 0 #4"正常保存静默"不冲突**(idle 即静默, 仅过程态短暂显示)。我答错(说删)已纠正。

### 落盘
- ux-spec §3 已从 3 行骨架**重写为细化定稿**(§3.0 原话 + §3.1 同/不同 + §3.2 eligible/动态浮出 + §3.3 配角色/可搜索选组 + §3.4 真 SDK 测试修假测试 + §3.5 现状 gap 接线清单 + §3.6 session 持久化边界 + §3.7 测试关键点)。§6.3 层次表 ①②③ 行已更新。
- **§2+§3 两页细化定稿完成**。下一步: 把 [`00_settings.md`](../mvp1/01_workflows/00_settings.md) §3.3(LLM Roles)/§3.4(Copilot)旧高层叙事对齐到细化版(高层指针, 细节链 ux-spec); 跨页项(P8 / 节点 Properties 快捷 Test / copilot session D8)是别的 region 的待接活, 登记交叉引用。
- ✅ §3.3/§3.4 已对齐; DEF-013(节点 Properties 快捷 Test 跨 region)已登记。

---

## 00_settings — 层次边界重过 + 多模态大需求(PM 2026-06-03 第三轮)

> PM 指令原话留底:
> "刚才根据每个原子操作把所有的功能过了一遍, 但是这个部分是非常依赖 gateway服务的, 所以必须从头到位重新过一遍, 哪些是前端(ts), 哪些是后段(rust), 那些是gateway(API服务), 把他们分清楚, 每个part需要守好自己的边界, 哪些是要求gateway需要做到的,希望通过什么样的方式握手; 另外要注意的是, gateway是一个不参杂特定业务领域的编排和模型调用的库, 不要把特定领域的需求交给他;"
> "多模态生成式模型的测试, 该怎么做, 我想有前面llm 和 copilot 之后, 有非常多的借鉴之处; 多模态集中在生成图片、视频、 tts、音乐等模型; 还有一点, 视频分析, 图片识别分析这类多模态输入, 文字输出的模型, 是放在多模态还是llm范围"

### 任务 A: 按层次边界从头重过两页(我之前 §6 的错: 把 Studio 后端 Python 和 gateway 库混成一层)
- **Claude 提的四层模型(待 PM 确认)**:
  1. **前端 (ts)** `apps/studio/frontend`: UI + 前端业务逻辑(拖拽/投影渲染/默认选择算法/family 折叠/弃用区/可搜索选组/draft 态)。只投影不持第二份。
  2. **后端 (rust)** native-fs: 对 Roles/Copilot **几乎不碰数据**(凭证/角色数据"永不 Rust 化")。Rust 只: General 选目录 / sidecar 生命周期+IPC / copilot **聊天 session** 落盘(D8, 属 chat region 非设置页)。
  3. **gateway 服务(API)** Python sidecar, **内分两层**:
     - **3a Studio 适配层(领域)** `apps/studio/backend`: model_groups 投影 / materialize(model_groups→fallback_chain)/ bundle / draft+证据 / **6 态 UI 投影** / copilot service / HTTP `/api/llm`+`/api/copilot`。**Studio 业务, 不是通用库。**
     - **3b gateway 库(领域无关)** `packages/graph-agent-gateway`: role→route 解析(`resolve_routes`)/ `ResolvedRoute`/`ResolvedRole` 契约 / ChatX 调用工厂 / capability 归一化+lint / 熔断+probe / 错误分类。**只懂 route/endpoint/credential/capability, 不懂 model group/bundle/draft/copilot/6 态。**
- **铁律(PM 核心)**: 领域需求绝不下沉 3b gateway 库。现码已守住(model_groups/materialize/draft/projection/copilot 全在 3a `apps/studio/backend`, 库里没有)——重过时每个原子操作确认这条线没被越。
- **握手**: FE↔3a = HTTP `/api/llm`+`/api/copilot`(DTO: ModelGroup/ProviderModelOption/RoleTestResponse/6 态 ui_state); 3a↔3b = 进程内, 适配层先 materialize model_groups→`RegistrySnapshot`(RoleEntry.fallback_chain), 调库 `resolve_routes`→拿 `ResolvedRole`(**库永不见 model group**); 3b↔provider = 真实调用(graph-agent 原生 ChatX; copilot 例外, 库只给 route, 调用交回 Studio copilot.py 用 ClaudeSDKClient)。
- **✅ 已完成 v1(PM 2026-06-03 确认四层模型 + 边界)**: ux-spec §6 重做为四层 —— §6.0 四层模型 + 领域无关铁律 + 三处握手;§6.1 加映射注;§6.2 Roles R1–R25;§6.3 Copilot C1–C12;§6.4 横切四层。
- **✅ 已完成 v2(PM 2026-06-03 第三轮续：§6 全重做，重点 API↔前端握手)**:
  - **本轮指令原话留底**: 「把它们全部列出来、你的建议」/「setting页面相关的部分, 把它们加入进去后, 完整的功能过一遍; 不同的是, 这次需要重点放在API, 怎么与前端握手. 需要与前端的设计对照」/「§6 全重做(四层模型 + Roles/Copilot 逐操作归属表 + 三处握手 + 两处守边界检查)」/「现在就跑起来」/「范围没有变」。
  - **改动**: ① **§6.1 API Keys 从旧三列重做为完整四层**(① FE-ts / ② Rust N/A / ③a Studio 适配 / ③b gateway 库 + 三处握手 API 契约 + A1–A12 逐操作归属表), 顺带把审计薄项(list-models 解析 per protocol、密码管理器抑制属性、窄视口不溢出)落进对应层; ② **新增 §6.5「两处守边界检查」**——把散落 ✓ 注收拢成两条正式不变量: **检查 1 @③a↔③b = gateway 库领域无关**(现状 ✓ 守住)、**检查 2 @①↔③a = 前端只投影不持第二份真相**(现状 ✗ 未守住: 残留 `roleTestStates`/`routeStatusOverrides`/`mock-copilot-data` → 本次接线工程删)。
  - **守边界结论**: 四页 ③b 列全是通用能力(resolve/capability/lint/probe/ChatX/协议探测/base_url 归一化), 无一条领域需求; 唯一未守住 = 检查 2(前端并行真相), 列为本次接线主工作。

### 任务 B: 多模态生成式模型测试(大需求, 见 [deferred DEF-014]) — 见下
- 分类问(我答, 见 DEF-014): **按输出模态分** —— 输出文字/推理(含多模态输入: 图片/视频识别分析)→ **LLM 范围**(复用 role/copilot 机制, 多模态输入只是 capability flag); 输出生成资产(图/视频/TTS/音乐)→ **多模态生成范围**(新机制)。

---

## 补记 — API Keys 深挖走查(本 thread)原话留底 + 实测证据(2026-06-03)

> 自查发现: 这几轮 API Keys 走查的**设计结论已全进权威 ux-spec**(批量探测/命名/两类失败/disabled可逆/层次分离/qiniu实测), 但 **verbatim PM 原话 + 实测证据当时只进了 chat + ux-spec(转述), 没进本工作日志** → 按原话留底铁律补记, 防 chat 清空丢失。

### PM 原话留底(verbatim, 不改一字)
> **[qiniu]** "qiniu就是一个key + 两个URL啊, 你怎么还没搞清楚状况 , 一个provider +多个URL, 一个provider= 一个key啊…我问你的是qiniu没有anthropic成功的配置数据吗?? 之前测过很多次了, 同一个api 怎么可能一个连通一个连不通呢, 肯定是配置的问题啊"
> **[批量探测]** "你必须用模型测试连通性, 才能测试出endpoint是否真正连通…因为像qiniu可能你选的protocol和你填的url不匹配, 导致虽然可以get model(表明apikey和url的连通性没有问题), 但是没有测试url和sdk的匹配性…为什么一定要手选一个模型来测试, 为的是让用户选一个看起来就比较靠谱的常用模型, 成功率会高. 如果让系统自动选模型, 可能会因为选的模型连不通, 误判整个endpoint不通; 但是, 现在已经改成了完全自动匹配和测试endpoint, 所以测试逻辑必须换成: 批量选择模型进行probe(不要太多3个吧, 也不要一个一个测, 如果一连串失败会很浪费时间), 一批一批测,直到有一批中有一个模型连通,代表这个endpoint是可以用的, 或者所有模型失败, 代表这个endpoint是不能用的. (自我怀疑: 如果endpoint不能用, 比如url 和 protocol 错配, 是否会有明确的错误码?? 而不用把所有模型都试一遍??)"
> **[结果展示]** "测试时间长了之后, 测试结果一出来sonner就马上消失了, 看不到结果…加一个把错误提示同时写在绿色小勾的位置" / "单个模型测试结果还在用旧的model badge样式, 改掉" / "这几次的测试结果都要加入draft, 不要浪费"
> **[拆分归属]** "「一 provider 多 URL→多 endpoint」这是前端业务逻辑, 不是后端该管的, 后端不应该对card有感知, 应该是前端自己拆分好告诉后端要存哪些, 要测试哪些" / "如果2个url+2个protocol都能用呢? 产生4个endpoints, 命名是否冲突了"
> **[两类失败]** "单模型probe连不上后的显示状态, 分两种: 1. 失败原因为: 模型不再提供、弃用, 显示为禁用(之前显示成failed, 红色); 2. 其他失败显示为红色failed(表示该模型+endpoint, 也就是routed链接失败), failed不阻塞他进入available models"
> **[命名统一]** "为什么不是统一的先protocol, 再编号的格式?"
> **[disabled 可逆]** "disabled(灰、不可选), hover变成禁用的图标, 但是点击仍然可以复制模型名称, 可以做单模型probe, 如果再次连通, 那么就从弃用区捞回来了"

### 实测证据(用 app key 真机, key 未外泄)
- qiniu-anthropic `deepseek-r1`: 先前裸探 401 → 照 gateway 配方 + 真实模型复测 **200**(同请求)= **瞬时抖动**, 非 key/endpoint 坏; `deepseek-v3-0324`→200; `minimax/glm`→间歇超时; `zzz-假模型`→400 invalid_request。→ **单探不可靠 = 批量探测的直接依据**。
- 错误码: openai 打 anthropic URL→`500 "Use /v1/messages instead"`; anthropic 打 openai URL→`404`; 未知模型→`400 invalid_request`(结构错可短路); `401/429/超时`(瞬时, 不可短路)。
- auth header: anthropic 兼容第三方(openrouter)走 `Authorization: Bearer`(实测 200), 非 native `x-api-key`(401)。

### 决策(均已进 ux-spec 权威, 此处仅索引防 drift)
- 批量模型探测(每批 ~3、批批打、命中即停/全失败判死、结构错短路、瞬时不短路) → ux-spec §1.2 item 2。
- 两类失败(弃用→`disabled` 可逆捞回 / 其他→`failed` 红不阻塞 available) → §4.2。
- 命名统一 `{slug}-{protocol}[-{n}]`(序号永在 protocol 后) → §1.2 item 4。
- 拆分 + endpoint_id 生成 = 前端职责, 后端不感知卡 → §1.2 item 4 + §6.1。
- 结果常驻 inline + 全进 draft(含失败) + 单模型 badge 换样式 → §1.4 + §4.1。
- qiniu #1 真相(瞬时抖动非坏) → §5 #1。
