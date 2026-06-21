# N2 · Authoring（搭图与编辑）深化计划

> 工作流第 1 步：实施前计划。把 N2 从旧占位（`ui-review-N2.json` 的 4 个 children 审计稿）深化成 N0 同款页型。
> 北极星：零黑盒（AI agent 100% 照做）+ 人能审计。只做前端，后端只写契约 + 标实现状态。
> 真代码已逐条核实（见末尾「核实记录」），过时的审计/spec 结论一律以真代码为准纠正。

## 0. 设计权威与边界

- 设计最高裁判：`docs/studio/mvp1/01_workflows/02_authoring.md`（N2 = 编辑与编译，但**编译/lint 门控归 N3**，本节点只做 authoring 四面）+ 字段 SSOT engine `02-skill-syntax/mvp1-alignment.md`（§2.3 Logic / §2.4 Subgraph / §2.5 Agent 白名单）+ `phase-editing` 能力文档（F1–F5）。
- 方法论裁判：`frontend-page-authoring-methodology.md`（页型/卡系统/10 内容规则/一色一义/两轴状态/按名引用）。
- **边界切分**：compile-lint 三处投影、Compile drawer、绿灯门控解锁 = **N3 Compile**，本节点不写 compile 原子，只在画布 mech 里把「写回后触发 compile」作为指向 N3 的下游指针。

## 1. Surface 划分（4 张操作设计页，对齐真实 UI 面板）

handoff §8 提示 + spec + 真 UI 核准后，N2 实际有 4 个并列 surface（无独立壳层页，authoring 都在 Workspace 外壳里）：

| page_id | 标题（与左导航逐字一致） | 这页讲什么 |
|---|---|---|
| `n2_canvas_design` | N2.1 画布搭建 · 操作设计 | GraphCanvas：建节点=建文件、连断线、拓扑/环校验、冲突覆盖、子图 inline/下钻、TB 布局、L3 步骤 |
| `n2_properties_design` | N2.2 Properties 节点属性 · 操作设计 | 三类节点白名单字段、节点类型派生、只读 Mode 行、子图 path 迁移 |
| `n2_graphmd_design` | N2.3 GRAPH.md 宏观契约 · 操作设计 | 头部 name/schema_version/llm_role/description/phases（无 type）、裸编辑 + 保真 round-trip |
| `n2_iopanel_design` | N2.4 i/o 面板 · 操作设计 | io.inputs 字段编辑、input files 导入、output artifact 落盘、子图 io 1:1 |

## 2. 各页操作原子清单（func + 两轴状态）

> 两轴：前端实施状态（符合/偏差/未实施）× 后端契约状态（已实现/未实现/契约问题/n/a）。
> 编号 n 全局唯一、与 N0 隔离（N2 用 1–28），anchor 加 `n2-` 前缀防与 N0 撞 id。

### N2.1 画布搭建（13 原子）
1. canvas-projection · 进画布看到节点+连线=GRAPH.md 可视投影（同一棵可执行树，无双向转换层）· 符合 / 已实现
2. node-open-file · 双击节点进对应文件编辑（SKILL/LOGIC/SUBGRAPH/GRAPH.md）· 符合 / 已实现
3. create-node-is-file · 新建节点（右键/加号选 Agent/Logic/Subgraph）=建对应文件 + 脚手架 FROZEN-clean · 符合 / 已实现
4. connect-edge · 拖连线写回 target.depends_on · 符合 / 已实现
5. disconnect-edge · 右键 Disconnect 写回 depends_on · 符合 / 已实现
6. reconnect-drag-disconnect · 重连 / 拖拽断线（R4 四操作另两个）· 偏差 / n/a（纯前端，缺 onReconnect）
7. cycle-detection · 环检测（dagre isAcyclic）→ 全屏红遮罩阻断 · 符合 / 已实现
8. data-gap-viz · 数据断层可视化（REQ-2 黑板字段勾选、删类型相等红叉）· 偏差 / 契约问题（前端无供给断层校验，靠引擎 compile 回吐）
9. seq-overwrite-conflict · 顺序覆盖冲突 Allow/Cancel overlay · 符合 / 已实现
10. subgraph-inline-preview · 子图 inline 展开真子拓扑预览 · 符合 / 已实现（**纠偏**：已接 getChildGraphTopology 真数据，非旧审计说的 mock）
11. subgraph-drilldown · 子图下钻（就地聚焦不切工程）+ context 自动切片 · 偏差 / 契约问题（现仅就地聚焦无下钻）
12. tb-layout · 纵向 TB 自动布局（REQ-1）· 符合 / n/a（**纠偏**：rankdir 已 TB，非旧 LR）
13. l3-step-edit · L3 步骤 `<step>/<action>` 内联增删改序 · 未实施 / 未实现（走 Rust mutate_phase_body，现无 L3 内联）

### N2.2 Properties 节点属性（6 原子）
14. node-type-derivation · 选中节点显示节点类型（应由文件类型定）· 偏差 / n/a（phaseKindLabel 读 data.mode，违 F1）
15. agent-whitelist · Agent 节点白名单 llm_role/tools/subagents · 符合 / n/a
16. logic-whitelist · Logic 节点白名单 actions/validator · 符合 / n/a（io.outputs 边界归 i/o 面板）
17. subgraph-whitelist · Subgraph 节点白名单 path/validator + legacy 迁移提示 · 偏差 / 契约问题（path 找不到标红 + OS 选文件夹导入入口 F4/R5 缺）
18. whitelist-roundtrip-save · 保存只写白名单，保留 name/io/未知键/body · 符合 / 已实现
19. readonly-mode-row · 底部只读 DetailRow 暴露 "Mode" 行 · 偏差 / n/a（与「类型=文件名」口径冲突，应删/改述）

### N2.3 GRAPH.md 宏观契约（3 原子）
20. macro-contract-form · 头部 name/schema_version/llm_role/description/phases（无 type）结构化编辑 · 偏差 / 已实现（现裸编辑 GRAPH.md，target 结构化表单 M1）
21. graphmd-raw-roundtrip · 双击开 GRAPH.md 裸编辑 + 保真 round-trip 保存（hash 乐观锁）· 符合 / 已实现
22. no-type-field · GRAPH 头部无 type 字段（FROZEN）· 符合 / 已实现

### N2.4 i/o 面板（6 原子）
23. input-field-edit · io.inputs 字段增删/改名/改类型直写 GRAPH.md（非投影假文件）· 符合 / 已实现（**纠偏**：假文件已清）
24. input-files-import · 拖 JSON 文本/文件 → schema-infer → 写 io.inputs（R3）· 符合 / 已实现
25. output-artifact-path · io.outputs 字段配文件路径 → 落 .workspace/artifacts（G3）· 符合 / 已实现
26. any-io-import-file · 任意 i/o 界面导入文件=导入字段进状态机（G2 新增）· 偏差 / 契约问题（现仅 input 节点可导入）
27. io-panel-perfield · input→i/o panel 改名、逐节点 io+artifact 可设（PM 锁 target）· 偏差 / 已实现
28. subgraph-io-no-1to1 · 子图 io 改动不触发严格 1:1 校验（G2 删 1:1）· 偏差 / 契约问题（引擎 loader 仍 FATAL 比 outputs，读旧 target_skill，待后端删）

## 3. 后端接口契约页（机制）

一页 `n2_contract`，含两块机制（各挂到对应 surface 的 mechs）：

### mech_graph（挂 canvas）—— graph 搭图读写与序列化机制（设计）
- overview：画布↔源码是「同一棵可执行树」，无双向转换层；横跨 ① 前端 ②③a Studio sidecar（gateway/engine 承载层）③b graph-agent 引擎内核 ③ Rust native-fs。
- 子模块：① 画布↔源码投影（build-nodes/buildEdges + 引擎 _graph_topology）② serialize 保真 round-trip（_preserve_graph_markdown_topology 只换 phases 块 + `<phase>` 标签）③ 拓扑校验（Studio _validate_canvas_topology + 引擎 _validate_graph_topology：orphan/self-cycle/cycle）④ native-fs 写（Rust write_workspace_file，D12 单一写者）⑤ hash 冲突两道拦（serialize 409 snapshot_conflict + Rust HashConflict）。
- 数据文件（前端视角）：GRAPH.md（frontmatter phases + io + body `<phase depends_on>` 标签）、phase 文件 frontmatter（三类白名单）。
- 接口分类：数据读写类（GET /skills/{id} detail、POST /skills/{id}/graph/serialize、GET child-graph-topology、native-fs write_workspace_file Rust command）+ 动作类（POST /skills/{id}/compile 指向 N3，不在此详写）。
- 后端状态（引后端实施手册 D8/D12）：d8.1 roundtrip 一致=ok、d8.2 Canvas 写回=partial、d8.3 UI metadata 不进 fingerprint=partial、d8.4 Subgraph 绝对 path=partial、d12.1 native-fs 写=ok、d12.3 expected-hash 冲突保护=ok。

### mech_io（挂 iopanel）—— io 契约 / artifact 落盘 / 子图引用机制（设计）
- overview：io.inputs/outputs 是 GRAPH.md frontmatter 里的 inline JSON Schema；artifact 落盘和子图 path 解析归引擎 io/manager + loader。
- 子模块：① io 契约（GRAPH.md io.inputs/outputs，引擎 io schema）② artifact 落盘（io.outputs target:artifact → 引擎 io/manager → .workspace/runs/<id>/artifacts，G3）③ 子图 path 解析（resolveSubgraphReference resolved/missing/migration-required；引擎 loader 读 path）④ 子图 io 1:1 校验（引擎 loader F-v3-subgraph-io-mismatch，仅比 outputs、读旧 target_skill，待删，G2）。
- 接口：io 随 GRAPH.md serialize 走（无独立端点，指针指向 mech_graph 的 serialize）；GET child-graph-topology（子图预览）；引擎 io/manager（运行期，指向 N4）。
- 后端状态：d8.4 子图 path=partial、G2 1:1 未删=partial（契约问题）、G3 artifact=ok。

## 4. 前端复用模块页（N2 自己的，节点间不共享通用组件）

`n2-femods`（合并去重）：
- `graph-roundtrip-client`（前端发 serialize/落盘的编排：Workspace serializeSkillGraph + doWriteSkillFile + graphHash 乐观锁）—— 被 #1/#4/#5/#21 用。
- `canvas-authoring`（连断线/建节点草稿/脚手架纯函数：connectPhaseRefs/disconnectPhaseRefs/createPhaseDraft/defaultPhaseMarkdown/phaseFilePath）—— 被 #3/#4/#5 用。
- `phase-kind-derivation`（节点类型派生：phaseKindLabel/phaseKindFile/build-nodes mode）—— 被 #1/#14 用（**含 F1 违例**）。
- `phase-frontmatter`（phase 文件 frontmatter 解析/白名单序列化：parsePhaseFrontmatter/applyPhaseFrontmatterForm/frontmatterFromForm）—— 被 #15/#16/#17/#18 用。
- `subgraph-path`（子图 path 解析/迁移判定：resolveSubgraphReference/normalizeAbsoluteSubgraphPath/legacySubgraphTargetSkill）—— 被 #17/#28 用。
- `io-schema-infer`（io 推断/写回纯函数：inferJsonSchemaFromText/applyInputSchemaToGraph/applyOutputArtifactPathToGraph）—— 被 #23/#24/#25 用。
- `subgraph-inline-preview`（子图真子拓扑预览组件：SubgraphInline + childPhaseRows + getChildGraphTopology）—— 被 #10 用。
- `命名弹框`（跨节点共享 UI 组件，与 N0 同一个 RoleNameDialog）—— 被 #3 新建命名用。标 kind=共享 UI 组件（跨节点）。

## 5. 实施页 + 测试页

`n2-impl`（逐功能现状/差距 + 按依赖排序计划）+ tests（两层，每条对应一原子）：
- 实施计划排序轴 = 后端先于前端：前端独立项（#6 reconnect、#13 L3 内联前端骨架、#14/#19 类型派生/Mode 行、#17 子图 path 标红入口）先做；等后端项（#8 数据断层 REQ-2、#11 子图下钻、#26 任意 io 导入、#28 删子图 io 1:1）排在后端契约（引擎 loader/io manager/下钻 context 切片）落地之后。
- 测试涵盖 28 原子，偏差项 layer1 RED 待转 GREEN；涉及真连通（建节点真落盘、serialize round-trip、native-fs 写）的 layer2 用真工作区真跑取证。

## 6. 生成器泛化（一次性公共改动，保持 N0 与未深化节点行为不变）

`build_template_slice.py` 现把 N0 硬编码在 `PAGES_N0` + N1–N6 走 `render_node_legacy`。泛化方案：
- 引入「节点上下文」`nctx`（code/页面 id 映射/anchor 前缀），N0 用 `nctx0`（页面 id 保持裸 `contract/fe_modules/impl/tests/n0_overview`、anchor 裸 `atom-N/fn-N/mod-N`，**N0 输出字节不变**），N2 用 `nctx2`（页面 id `n2_contract/n2_fe_modules/n2_impl/n2_tests/n2_overview`、anchor 前缀 `n2-`）。
- 把 `render_design/render_contract/render_fe_modules/render_impl_all/render_tests_all/render_node_overview/render_impl/render_tests` 的 N0 硬编码（页面 id、标题 "N0"、`#fe_modules`/`#contract` 链接、`atom-/fn-/mod-` anchor）改成读 nctx。
- `render_handbook_overview` 的「7 节点入口」改成遍历节点注册表：full 节点（N0、N2）渲 full 卡（rollup + 页面链接），legacy 节点渲待深化卡。
- `main()` 的装配循环 + 导航 TOC 改成遍历节点注册表，full 节点输出「主页 + 设计页×surface + 契约 + 复用模块 + 实施 + 测试」，legacy 节点走 `render_node_legacy`。
- N2 的 PAGES_N2 清单：4 个 surface 元组（design/mechs/impl/femods）。

## 7. 验收（自检）

`python3 build_template_slice.py` → 跑 §7 自检脚本：0 重复 id、0 断链、div 平衡；左导航 N2 子页标签 = 各页正文标题；N0 渲染字节不变（diff index.html 的 N0 段）。post-audit subagent 判「只拿 N2 手册+spec 能否 100% 实现、无 BLOCKER」。

## 8. 核实记录（真代码逐条核对，file 名+对象名）

- Properties 三类白名单：`PhaseFrontmatterForm` kind 分支 agent/logic/subgraph（PropertiesPanel.tsx），`frontmatterFromForm` 白名单 set（phase-frontmatter.ts：agent→llm_role/tools/subagents、logic→actions/validator、subgraph→path/validator）—— 已重建，符合。✅
- mode 派生违 F1：`phaseKindLabel/phaseKindFile` 读 `data.mode`/`subgraphPath`（PropertiesPanel.tsx）、`mode = topology?.mode ?? phase.mode`（build-nodes.ts）—— 真未修。✅
- 只读 Mode 行：`DetailRow label="Mode"`（PropertiesPanel.tsx）存在。✅
- 脚手架 FROZEN-clean：`defaultPhaseMarkdown` 三模板用 `path:` 非 target_skill、无 system_prompt（canvas-authoring.ts）。✅
- 连断线/缺重连：`onConnect`/`onDisconnectConnection` 有、无 `onReconnect`/`edgesReconnectable`（GraphCanvas.tsx）。✅
- 环检测 + TB：`graphlib.alg.isAcyclic` 抛 `CycleDetectedError`、`rankdir:'TB'`（lib/layout.ts）—— **TB 已落地，纠正 spec LR**。✅
- 子图 inline 真数据：`SubgraphInline` 用 `getChildGraphTopology`、`childPhaseRows` 注释「Never fabricates」（SubgraphInline.tsx）—— **纠正旧审计 mock**。✅
- io 假文件已清 + artifact：`IoContractView`（panel-files.ts）不再投影假文件；`applyInputSchemaToGraph/applyOutputArtifactPathToGraph/inferJsonSchemaFromText`（InputPanel.tsx 导入）。✅
- 子图 path 解析：`resolveSubgraphReference`（subgraph-path.ts）出 resolved/missing/migration-required；PropertiesPanel subgraph 渲 Path Input + legacy 迁移提示，但**无 OS 选文件夹导入入口**（无 folder picker）—— F4 部分。✅
- 子图 io 1:1 未删：引擎 loader F-v3-subgraph-io-mismatch（仅比 outputs、读旧 target_skill）—— 据 deepdive C/D，标 partial 待后端删。
