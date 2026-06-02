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
- **handoff**: 下个 session 交接 = [`_reorg/NEXT-SESSION-PROMPT-v2.md`](NEXT-SESSION-PROMPT-v2.md)。

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
