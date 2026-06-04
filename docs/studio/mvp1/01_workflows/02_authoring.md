# Node 2: 编辑与编译 (Authoring & Compile)

> Tier: workflow · Owns: 把业务逻辑装配成严谨 graph_skill 的旅程(宏观契约 / 中观拓扑 / 微观节点编辑 / 实时 compile 门控)· 能力 `graph-authoring` `phase-editing` `file-editing` `compile-lint` `conflict-overwrite` · 区域 `canvas` `editor` `input(→i/o panel)` `properties` `center-action-bar` · 平台 `native-fs`(Rust 写) / `engine`(compile)
> Status: ✅ PM 已确认(批次2 + Half A + G1–G9 + R3–R5;Half B 现在设计)
> 设计权威: `.kiro/specs/studio-feature-canvas-topology`(canvas REQ) + **FROZEN `docs/engine/mvp0/skill-spec`**(字段/格式) + 决策 D7/G2/G3/D12/REQ-10。原话依据: [`_reorg/alignment-notes.md` 批次2 + Half A + G1-G9](../../_reorg/alignment-notes.md)。字段唯一真相源 = 能力文档 [`phase-editing`](../02_capabilities/phase-editing/mvp1-alignment.md)(只链接不复制)。
> 本文 = 该节点**最终设计**(atom action 决策 + file:line 依据);迁移源 = `_reorg/workflow-action-catalog.md` §02_authoring。

## 1. 用户旅程目标
把脑子里的业务逻辑转成**严谨可编译的 graph_skill**:宏观全局契约(GRAPH.md `name`/`schema_version`/`llm_role`/`description`/`phases`/`io`,**无 `type` 字段**)→ 中观拓扑(连线/断连/新建 phase/子图 inline 展开+下钻)→ 微观节点编辑(Properties 白名单字段 + L3 步骤)→ 实时 compile/lint 门控(绿灯才解锁 Predict)。

> ⚠️ **节点类型 = 文件名,非 `mode`/`type` 字段**(FROZEN):Agent=`SKILL.md` / Logic=`LOGIC.md` / Subgraph=`SUBGRAPH.md`;"新建节点选类型"=选建哪个文件。旧 UX 散文里的 `type(simple/graph)` / `<system_prompt>` / `<user_prompt_builder>` / `max_retries`/`max_nudges` 等**全部违 FROZEN**,已废。

## 2. atom action 决策表
> ⚠️ 跨切定性:**读取层已 v030-aware**(`CURRENT_SCHEMA_VERSION='v0.3.0'`),但**写入/脚手架/子图渲染层多为 V2.x stale-code**(违 FROZEN)。详尽 M/T/V 动作及证据见 alignment-notes 批次2 Half A。

| 动作 | 最终决策 / status | 能力·区域 | 依据(file:line)+ FROZEN |
|---|---|---|---|
| M1 头部 `name/schema_version/llm_role/description/phases`(**无 type**) | **target-design**:需结构化表单,现无 panel 只能裸编辑 GRAPH.md(旧 doc 写 type=stale) | graph-authoring · canvas | `GraphCanvas.tsx:397-405,423-429`;FROZEN `02-graph-md-spec.md:12-20` |
| M2+M3 io 内联手写 JSON Schema / schema-infer | **stale-code**:双击 IO 开 GRAPH.md=live;InputPanel 投影 io 成假文件 + schema-infer 只读不写回=stale(违 inline-io) | file-editing · input | `GraphCanvas.tsx:423-429`/`panel-files.ts:70-97`/`InputPanel.tsx:18-70`;FROZEN `02-graph:60,86-87` |
| i/o panel 改名 + artifact 逐节点设 | **target-design**(PM 锁:input→i/o panel,每节点 io+artifact 可设) | phase-editing · input(→i/o panel) | `InputPanel.tsx:78`。**FROZEN/G3**:io.outputs 顶层加文件路径+schema,默认落 `.workspace/artifacts`;md 源=最终 validated `business_data_md`(不回转) |
| M4 起点 Input / 终点 Output = 画布独立节点 | **live**(已渲染、可双击开 GRAPH.md) | graph-authoring · canvas | `build-nodes.ts:203-217`;FROZEN `02-graph:44` |
| REQ-1 纵向 TB 布局 | **target-design**:现 LR 挤瘪面板,目标 TB | graph-authoring · canvas | `lib/layout.ts:31`(rankdir LR)/`SkillNode.tsx:82,132` |
| T1+T2 连线 / 断连(`depends_on`)| **live**(serialize 写回带 hash 乐观并发+回滚)→ **写迁 Rust(D12)**;连线=建链/改链重连/拖拽断链/菜单断**四操作**(R4,现仅菜单断) | graph-authoring · canvas | `GraphCanvas.tsx:319-361,475-483`/`canvas-authoring.ts:68-127`→`skills.py:122,366` |
| T3 拓扑校验(环 / 数据断层) | **环检测 live;数据断层=改黑板可视化(REQ-2,删旧类型红叉)= target** | graph-authoring · canvas | `GraphCanvas.tsx:217-243`/`ContextEdge.tsx`;FROZEN `02-graph:89-96` |
| T4 新建 phase(Agent/Logic/Subgraph,=选建哪个文件) | **接线 live,脚手架 stale-code**(`defaultPhaseMarkdown` 写 mode/system_prompt/exit_contract/python_callable 违 FROZEN)→ 脚手架=logic→agent 模板(D-1-4) | graph-authoring · canvas | `canvas-authoring.ts:143-189`;FROZEN `05-agent:40-55`,`00:114` |
| T5 子图 inline 展开(虚线容器、动态 group bbox) | **placeholder**:toggle live 但 `SubgraphInline` 渲染假数据 | graph-authoring · canvas | `SkillNode.tsx:116-131`/`SubgraphInline.tsx:19-23`。**FROZEN/G2**:删 `04-subgraph` io 严格 1:1 |
| T6 子图下钻(就地聚焦,不切工程)+ T7 context_bridge | **target-design**:现仅就地聚焦无下钻;T7 FROZEN SUBGRAPH.md 无 context_bridge(io 由 StateMapper 按 schema 自动切片) | graph-authoring · canvas | `GraphCanvas.tsx:423-435`;FROZEN `04-subgraph:32-38` |
| Properties 编辑保存 | **stale-code**:保存 live 但字段集全过时、与 FROZEN 全冲突 | phase-editing · properties | `PropertiesPanel.tsx:293-305`/`phase-frontmatter.ts:8-16` |
| Properties 白名单重建(按 FROZEN 三类节点字段集) | **target-design**(REQ-10 确认 batch-2 stale 结论) | phase-editing · properties | FROZEN `05-agent:14-26`/`03-logic`/`04-subgraph`;`build-nodes.ts:151-160`(subagents 读过时 shape)。**FROZEN/G2**:删 io 1:1;**D7**:子图 path |
| L3 步骤(`<step>`/`<action>`)增删改序 | **target-design**:右缘加号展开 body,走 Rust `mutate_phase_body`,现无 L3 | phase-editing · canvas | `SkillNode.tsx:116-131`;canvas REQ-6 L3;FROZEN `05-agent:48` |
| Lint + Compile + 错误面板 | **live**(防抖 lint + `compileSkill` 引擎真编译,CompileErrorPanel 渲染) | compile-lint · center-action-bar | `useDebouncedLint.ts:48-49`/`Workspace.tsx:432-435`→`skills.py:109` |
| Predict 门控解锁(Compile 绿灯→解锁 Predict) | **门控 live;点击进试飞=桩**(归 03_run-and-verify) | compile-lint · center-action-bar | `center-action-bar.tsx:31-50,76-85` |
| 顺序覆盖冲突保存(overlay Allow/Cancel) | **live** | conflict-overwrite · canvas | `canvas-authoring.ts:237-337`/`GraphCanvas.tsx:105-119` |
| [失败退路] 写失败回滚 / 拒写 / YAML 坏 error+Open file / 环全屏阻断 | **live** | graph-authoring · canvas | `GraphCanvas.tsx:354-360,217-226,381-387`/`phase-frontmatter.ts:46-72` |
| (R5)assets subgraph 类目 ↔ 节点文件同步;子图 path 找不到→标红→OS 选文件夹导入工作区 | **target-design**(R5 + D7) | graph-authoring · canvas/assets | alignment-notes R5;D7 path 解析 |

## 3. 设计决策基础(原话依据,锁定决策)
- **D7 子图按 path** > "subgraph.md里面写path, 直接解析就好了, 随便放哪里…注册在agent phase里的子图也一样写path";`SkillResolverProtocol.resolve` 退化为读 path,无注册表。
- **G2 删子图 io 严格 1:1**(FROZEN-1)> "父子图的io关系不用绑死(伪需求)…子图的input是从state状态机过滤字段拿的";+ 任意 i/o 面板可导入文件注入黑板(时机=a 跑到该节点才注入)。
- **G3 artifact 落盘**(FROZEN-2)> io.outputs schema 顶层加文件路径(`xx/xx.json|md`),默认落 `.workspace/artifacts`;md 用最终 `business_data_md` 不回转。
- **REQ-10 Properties 白名单对齐 FROZEN**(官方确认 batch-2 stale 表单结论);**REQ-1 TB 布局**;**REQ-2 黑板可视化连线**(FROZEN-4,删类型相等红、改 io.inputs 字段勾选)。
- **D12 写全量 Rust**;**D-1-4 脚手架 logic→agent 模板**;**R3** i/o panel 加 input files 导入(FROZEN-3);**R4** 连线四操作;**R5** assets 同步 + 子图 path 标红导入。
- **Half B 现在设计**(不留实现期):三类节点字段集 + 子图 path 引用 + io.outputs artifact + 删子图 io 1:1,已落能力文档 [phase-editing](../02_capabilities/phase-editing/mvp1-alignment.md)。

## 4. 失败退路 + 节点间流转
- **失败退路**:写失败→回滚(hash 乐观并发);YAML 坏→error + Open file;环→全屏阻断;拒写。
- **上游**:[01_init](./01_init.md)(进入 workspace + copilot 初始化 SKILL.md)。
- **下游**:Compile 绿灯 → [03_run-and-verify](./03_run-and-verify.md)(predict 试飞解锁);copilot inline-diff → copilot-assist;文件树/.workspace → asset-explorer(file-editing)。

## 5. 测试关键点
- 新建 phase 脚手架产出**合 FROZEN**(logic/agent,无 mode/system_prompt/exit_contract/python_callable),可直接编译。
- io 内联手写 JSON Schema(非投影假文件);schema-infer 弃用或改写回 io。
- 子图 io 改动**不**触发严格 1:1 校验(G2);子图按 path 解析、path 找不到→标红+导入入口。
- artifact:io.outputs 配文件路径 → 跑时落 `.workspace/artifacts`;md 取 `business_data_md` 不回转。
- 所有写(serialize_graph/mutate_phase_body/新建 phase/Properties 保存)走 **Rust** 文件命令(非 Python)。
- Compile 绿灯才解锁 Predict;改 prompt 不破门控,改 io schema 缺字段触发编译错误。

## 6. 跨切 / 已知债
- **[D12] 写全量 Rust**:serialize_graph / mutate_phase_body / 新建 phase 写文件 / Properties 保存 → Rust(现走 Python `writeSkillFile`+`graph/serialize`,标迁移)。
- **读 v030 / 写 V2.x stale-code**:`defaultPhaseMarkdown`、`phase-frontmatter.ts`、`SubgraphInline` mock、`subagentsForPhase` 读过时 shape。
- **FROZEN 改动落点集中本节点**:FROZEN-1 删子图 io 1:1、FROZEN-2 io.outputs artifact、FROZEN-4 REQ-2 字段勾选(待统一出 FROZEN 新版本)。
- **canvas REQ 覆盖**:REQ-7 结构化 diff → 归 trace(03_run-and-verify);REQ-8 运行时策略开关(prompt_cache/compaction)= engine 未落地 ⏭️ 延后;REQ-9 右键新建节点 = T4(已覆盖)。
