---
module: 03_regions/input
doc: mvp1-alignment
status: FROZEN（2026-07-02 r3 定稿:PM 确认黑板优先配置树模型——面板=预览+Configure+文件 list,输入配置=黑板 context 第一行的字段勾选树+Add file 追加,输出配置=artifacts 文件清单×黑板字段勾选;golden 区从面板移除。样稿经 PM 三轮确认。；目标结构已按 R4-R8 retrofit）｜2026-07-03 r5 修订（PM 真机 4 点反馈,已实施 feat/io-node-scoped-config）:①「节点↔io」关系模型建对——**按角色收敛面板段**(Input 边界只 input、Output 边界只 output、phase 两段、空白=GRAPH.md 两段,见 F3 归属规则,原为代码 drift);②**io 字段全链路支持嵌套寻址**(engine 递归 required + backend field_supply 递归 + 前端配置树可展开、子字段 `chapter.aa_number` 独立勾选,见 F3);③**输入配置改内联**(可折叠段 + 紧凑树行,替换 F2「配置全在弹窗」;输出 artifacts 编辑因多卡片过宽保留 scoped modal);④**New file 改 ghost list 行**(F2/r4b 的 `variant=secondary` 暗色近黑,改透明底 hover 亮)。
binds_baseline: ./baseline.md
units: [io-panel-artifacts-test-inputs, golden-per-agent-node]
aligns_with: 01_workflows/02_authoring.md（i/o panel）· 01_workflows/04_run-and-verify.md（predict/run input/golden）
---

# input — MVP1 Alignment

> **Tier**: region | **Owns**: `io-panel-artifacts-test-inputs`（i/o 面板 owner）| **核心模型(PM 2026-07-02 r3)**: 数据主干是黑板,不是文件——节点输入本来自黑板,import file 只是**追加**字段;输入/输出配置都是「file↔field 映射」的勾选树。 | **Related**: [baseline](./baseline.md)（双向）· `phase-editing` · `predict` · `run-execution` · `golden-eval` · `assets`

## 1. 定义
`input` is the current folder name for the MVP1 i/o panel region. It owns the per-node i/o preview, the input/output configuration entries (config dialogs), input file imports, output artifact manifests, and single/batch input selection for Predict/Run.

Source workflow basis: `01_workflows/02_authoring.md:20`, `01_workflows/04_run-and-verify.md:21`, `01_workflows/04_run-and-verify.md:62`.

## 2. 数据流 / 机制（设计细节）

### F1. I/O Panel Identity
- 机制: rename visible panel semantics from Input to i/o and include output-side settings.
- 决策: input, validate, and batch are configuration; not separate predict products.
- 原话/来源: `01_workflows/04_run-and-verify.md:30` removes input/validate/batch as standalone predict issues; `01_workflows/04_run-and-verify.md:35` keeps PM wording.
- 测试: panel copy and affordances cover input and output; no separate PredictInputDialog appears.
- Status: target-design.
- 归属: region `input`; capabilities `predict`, `phase-editing`.

### F2. Panel Surface（实例预览 + Configure 入口 + 文件 list）
- 机制: 面板每侧(input/output)按角色渲染:① **实例预览**——按当前 io schema 推导的示例 JSON(清爽只读,嵌套递归展开到叶子);② **配置入口**——input 侧是**内联可折叠段**(点「Configure input」原地展开黑板勾选树,见 F3,不再弹大 modal);output 侧的 artifacts 编辑因是多卡片编辑器、窄面板塞不下,保留一个 scoped「Configure」modal(F7)。**文件 list**并入内联配置树的文件组(已导入文件 + 其字段),不再单列一段。
- 决策(2026-07-03 r5 修订): **配置默认内联,不再一律走弹窗**——PM 反馈「io config 收进选中节点的属性里,像 Properties 面板」;窄面板(约 320px)的问题用**可折叠段 + 紧凑缩进树行**解决,而非退回 modal。仅 output artifacts 这种多卡片编辑器确实塞不下时保留 scoped modal(PM 允许的兜底)。此条**替换** r2/r3「配置操作全在弹窗、面板不承载配置编辑」的旧决策。**面板不再有 golden 区**(PM 2026-07-02 r2 点1)、**不再有内联「创建 test input」表单**(PM 2026-07-02 r2 点3)不变。
- 原话/来源: PM 2026-07-02(原话见 §4)。
- 测试: 面板无 schema 表单、无 golden 区、无内联创建表单;实例预览由真实 io 声明推导;Configure 打开对应配置弹窗;文件 list 行显示文件名+路径。
- Status: target-design。
- 归属: region `input`; capability `predict`; platform `engine`.

### F3. Input Config Tree（黑板优先的输入配置,PM 2026-07-02 r3 核心模型）
- 机制: 输入配置弹窗 = 一棵字段勾选树:**第一行永远是黑板 context**,展开为「跑到这个节点时黑板上有的字段」(嵌套对象按层级缩进展开;推导与 dot 静态推断共享同一套逻辑,见 trace-observability F4),打勾 = 该节点消费哪些字段(**即它的 io.inputs 声明**);黑板行下面是通过 **Add file** 按钮加进来的文件,每个文件下是它自己的 schema 字段树(后端扫描解析,见 F5),勾中的字段以 `source:'file'` 声明**追加**成黑板字段。文件行 = 文件名 + 灰色路径。
- **Input 伪节点特例**: 没有黑板(上游无物),配置树里只有文件;在 Input 节点勾选的文件字段,流到第一个 node 时**成为黑板初始字段**(= GRAPH.md `io.inputs`)。一套「文件 + 勾选」= 一份输入方案,存下来命名即 test input——schema 定义与数据来源在同一处闭环。**GRAPH.md io.inputs 已声明、但没有 `source:'file'` 支撑的字段 = 未接来源**,在配置树里以 missing 态置顶报错「declared graph input · no source supplied」——提醒作者这个图入口字段还没接文件/来源(PM 2026-07-02 r4b 点2:"第一个 input 节点要求输出 chapter 字段,但是没有输入,应该触发字段缺失警告")。
- **归属规则**: Input 节点只有输入配置,Output 节点只有输出配置,GRAPH.md 两者都有(两个伪节点即 GRAPH.md io 的投影);普通节点 = 输入配置(黑板+文件)+ 输出预览。
- **字段对账三态(PM 2026-07-02 r4)**: 配置树把「节点 md io.inputs 声明」与「实际黑板可用字段」对账,每行标一种状态:**matched**(声明了 + 黑板有 = 被消费)→ 整行 accent 高亮 + 左侧主色竖条;**available**(黑板有但本节点未声明消费)→ 普通行;**missing**(io.inputs 声明了、但上游黑板没供上该字段)→ 置顶,muted + danger 底 + ⚠ 图标 + 原因「required by io.inputs · not supplied by upstream」,不可勾选、不写回。`source:'file'` 字段来自文件注入不是黑板供应,永不算 missing。此对账把引擎运行期 `[F-v3-runtime-state-mapping-failed]`(StateMapper 缺 required 字段)提前到配置期可视化。
- **嵌套寻址三层贯通(PM 2026-07-03 r5 核心)**: object 字段(如 `chapter`)在配置树里按层级展开,子字段(`chapter.aa_number`)**可独立勾选**;勾选一条子路径 = 在节点 io.inputs 里把 `chapter` 声明成 object 且其 `aa_number` 进 `required`(勾父级=声明整块 object 必需;勾子级=父级自动成为必需 object + 该子字段必需)。这要求**全链路认识嵌套路径,否则前端画的展开树是会撒谎的 UI(勾了没运行语义)**,故本轮三层同时改:① **engine** `StateMapper.build_phase_input` 的 required 门禁改**递归遍历 schema 树**(顶层与嵌套 `required` 同一套,缺失即 `[F-v3-runtime-state-mapping-failed]`,`field_path` 为点路径,与 output 侧 Draft2020 校验器统一;见 `docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` slice 行);② **studio backend** `canvas_data_gap.field_supply` 投影**递归展开**嵌套 properties,子路径作独立可寻址条目(带各自 producer/consumer,整块 object 的 producer 供其子路径);③ **前端** io-config / edge-static-inference 从「按顶层 key」改「按树遍历」(`fieldPathRows` 共享层),配置树可展开勾选。**输出侧不对称**:artifacts 由 engine writer 按**顶层 key**落盘(`artifact_manifest.write_manifest_artifacts` 只认顶层),故输出配置树里嵌套子字段**仅展示形状、不独立勾选**——一个 artifact 携带的是整块顶层字段(含其子字段),没有「只装 `segmentation_result.bb_number`」的引擎语义。
- 决策: 导入文件不是 node input 的主源,黑板才是;import file 只是在黑板上额外增加字段(PM 2026-07-02 r3 点2)。配置界面的第一性结构是字段勾选树,不是导入向导。字段对账让作者一眼看清「声明了但没人给」的断链(PM 2026-07-02 r4)。嵌套子字段的 missing 只显示 subtree 顶层未满足项(不刷屏子孙),对账仍镜像引擎运行期 `[F-v3-runtime-state-mapping-failed]`,现在到嵌套粒度(PM 2026-07-03 r5)。
- 原话/来源: PM 2026-07-02 r3/r4(原话见 §4);样稿经 PM 确认(r3b + r4)。
- 测试: 黑板行字段与 dot 静态推断同源一致;勾选黑板字段写回节点 io.inputs;勾选文件字段写 `{type, source:'file', path}`;Input 节点树无黑板行;批量文件夹折叠为一行并记录编号列表;对账三态 matched/available/missing 分类正确(reconcileInputFields),missing 置顶、不写回。
- Status: target-design。
- 归属: region `input`; capabilities `phase-editing`, `graph-authoring`; platform `engine`, `native-fs`.

### F4. Predict/Run Input Selection
- 机制: selected file/config becomes the input payload for Predict and Run;面板 test inputs list 选中项即 payload。
- 决策: Predict and Run execute according to configuration.
- 原话/来源: `01_workflows/04_run-and-verify.md:34` and `01_workflows/04_run-and-verify.md:67`.
- 测试: changing selected input changes predict/run payload; missing selection produces scoped panel error.
- Status: live(2026-07-02 #304 挂通)。
- 归属: region `input`; capabilities `predict`, `run-execution`.

### F5. File Scan And Recognition（导入扫描,后端纯读）
- **导入入口 = 原生 OS 选择器(PM 2026-07-02 r4b 点3)**: 弹窗里是「Import file…」/「Import folder…」两个按钮,点击调 Rust `select_file`/`select_directory` 弹**系统原生文件/文件夹对话框**拿绝对路径——**不让用户手打 path**("直接用原生 file 组件选择文件或者文件夹啊,怎么会让用户输入 path 呢")。选完的绝对路径交给下面的扫描/导入端点。
- 机制: 选中文件/文件夹后,后端扫描端点解析:`.json` → 顶层字段名+类型+样本值;`.jsonl` → 首行对象字段;`.md`/`.txt` → 整体一个文本候选字段(大文件只记路径+大小,**不内联内容**);子文件夹递归一层。**批量识别**:同 stem 只差编号的文件群(`chapter_001…chapter_060`)折叠成一个批量条目(`chapter_[001–060] ×N`),**编号列表提取并记录**;`latest`/`_v<时间戳>` 识别为版本修饰,自动取 latest、`history/` 忽略。识别用鲁棒的连续数字段正则,**不假定自产固定格式**(外来格式也要能认,PM 2026-07-02 r2 点7「输出固定、输入鲁棒」)。
- 决策: 扫描放 studio backend(读盘+JSON 解析本来就是后端职责;Rust sole-writer 原则只管写)。
- 原话/来源: PM 2026-07-02 r2 点4/点7(原话见 §4)。
- 测试: 真实 material-prep 文件夹(异构 11 文件)与 node1_output(iterate 批量 60 文件)扫描出正确字段树;批量编号列表完整;超大文件不内联。
- Status: target-design。
- 归属: region `input`; platform `llm-copilot-http-api`(studio backend HTTP).

### F6. Batch Input Selection
- 机制: select multiple inputs, start batch, and show progress/per-item failures.
- 决策: batch is run input configuration.
- 原话/来源: `01_workflows/04_run-and-verify.md:54` to `:57`.
- 测试: multiple selected inputs create batch; failed item is visible.
- Status: backend/orphan frontend.
- 归属: region `input`; capability `run-execution`.

### F7. Output Artifacts Config（与输入对称的产物清单,PM 2026-07-02 r3 点5）
- 机制: 输出配置弹窗 = artifacts 文件清单:**Add artifact** 添加要输出的文件,每个文件卡 = stem 名 + single/per-item 紧凑分段钮 + **黑板全部字段的勾选列表(每个文件下同一套清单,只是勾选不同)** + 固定格式文件名实时预览。per-item 数量从 iterate range 设置推断并显示(`per-item ×N`)。single 与 per-item 的区别只在**取值时机与落盘方式**(per-item 每轮迭代落一个编号文件,single 只落最终值),字段清单同一套。
- **固定落盘格式(engine artifact writer 规范)**: 单产物 `<stem>_latest_<YYYYMMDD_HHMMSS>.json` + 旧版归档 `history/<stem>_v<ts>.json`;per-item `<stem>/<item>_<NNN>_latest_<ts>.json`(编号零填充,**继承输入批量编号**,无则用轮次号)。自产永远这个格式 → 下游导入扫描一眼认出;输入侧对外来格式保持鲁棒(F5)。
- **声明形状**: GRAPH.md io 增加 `artifacts:` 清单声明(list of {stem, fields, mode}),**整体替换** per-field `target:'artifact'` 路径(含 `artifact_manager` legacy 别名),同轮删旧不留兼容。
- **字段对账三态(PM 2026-07-02 r4,与输入同理)**: 每个 artifact 卡的字段清单 = 黑板全字段全集(根 io.inputs ∪ 各 phase io.outputs)。**matched**(该字段是 GRAPH.md io.outputs 声明的图产出)→ 高亮 + 左侧竖条,提醒作者「这是必需产出,记得挑个文件装它」;**available**(黑板有但非声明产出)→ 普通行;**missing**(io.outputs 声明了、但没有任何 phase 产出它)→ 置顶一次(dialog 级,非每卡重复)muted + danger + ⚠ +「required by io.outputs · no phase produces it」。
- 决策: artifacts 是一个 list,用户创建要输出哪些文件、每个文件包含 output 的哪些字段(PM 2026-07-02 r2 点5);固定格式参考既有 pipeline 产物(`<stem>_latest_<ts>` + `history/`,PM 2026-07-02 r2 点7)。字段对账让作者一眼看清「声明要输出、却无人产出」的断链(PM 2026-07-02 r4)。
- 原话/来源: PM 2026-07-02 r2/r3/r4(原话见 §4);样稿经 PM 确认(r3b + r4)。
- 测试: artifacts 清单写回 GRAPH.md io;engine writer 按固定格式落盘;per-item 编号继承输入批量编号;旧 per-field target 路径已删;对账三态分类正确(reconcileOutputFields),missing 置顶。
- Status: target-design。
- 归属: region `input`; capability `phase-editing`; platform `engine`, `native-fs`.

### F8. Golden（入口迁出面板）
- 机制: golden JSON 与 F2 实例预览同构(都是 `io.outputs` schema 的实例,差别只在生命周期);**面板不再设 golden 区**;golden 的创建(跑完存实际输出)与 diff 展示归 run/trace 侧,与 golden-eval 后端逐节点粒度改造同轮设计(后续轮)。
- 决策: 面板不要 golden,「Generate template」两连点无意义(PM 2026-07-02 r2 点1,修订 2026-06-04「golden 主入口=Assets+I/O output」决策中 I/O 入口部分;Assets 文件树直接打开 golden 文件的入口不变)。
- 原话/来源: PM 2026-07-02 r2(原话见 §4)。
- 测试: 面板无 golden 区;Assets 树仍可打开 golden 文件。
- Status: target-design(面板收敛本轮;run/trace 侧 golden 交互后续轮)。
- 归属: region `input`(收敛)· capability `golden-eval`(后续轮 owner)。

## 3. 接口契约
- Inputs: selected node, skill files, node i/o schema, blackboard static inference(与 trace-observability F4 同源), file scan results, iterate range.
- Outputs: io.inputs/`source:'file'` 声明写回(节点文件/GRAPH.md), `artifacts:` 清单写回(GRAPH.md), selected predict/run input, batch input list, file open。
- Capability links: `phase-editing`, `graph-authoring`, `predict`, `run-execution`, `golden-eval`.
- Platform links: `native-fs`(声明写盘), `engine`(artifacts writer / source:file 注入), studio backend(扫描端点)。

## 4. 设计决策基础（PM 原话,2026-07-02）
- **r2 点1(golden 出面板)**:"不是说了面板不要golden了吗？？你这两个创建模板一定要用户去点两下？有什么意义？？"
- **r2 点3(test input 心智)**:"没有人会在io面板里面创建一个test inputs，那么小的面板，太反人类了；要么导入一个文件/文件夹，要么在.workspace创建一个文件（在输入不复杂的时候），在编辑器里面编辑"
- **r2 点4(导入识别)**:"导入文件必须识别出这些文件，并识别出这些文件有哪些字段，哪些内容，并且在这些文件中推断，是否有input需要的字段，是否匹配"(真实样例:`D:\coding\test_data\013_躺赢\01_material-prep\20260416_030517` 异构 artifacts、`…\02_story-deconstruction\node1_output` iterate 批量)
- **r2 点5(artifacts list)**:"output artifacts应该是一个list，用户创建要输出哪些文件，文件要包含output的哪些字段"
- **r2 点7(编号与格式)**:"如果输入有批量文件，要把批量的数字提取出来并且记下来，自己输出的artifacts要有一个固定格式……input可能会不是这个格式，要有鲁棒性。但是自己输出的固定格式，再给其他输入就比较好认了。"
- **r3 点2(黑板主源)**:"导入文件不是node input 数据的主要来源，黑板才是，impot file只是在黑板上额外增加了数据字段"
- **r3 点3(归属)**:"input node只有输入设置， output node 只有输出设置，graph.md才有输入输出设置"
- **r3 点4(配置树)**:"输入的配置面板，应该是一个文件树一样的list……第一行永远是黑板context，下面才是import附加的文件和文件带来的字段；input节点没有黑板，只有文件；到了input链接的第一个node，input从文件勾选的字段就成了黑板上的字段"
- **r3 点5(输出对称)**:"通过add button添加需要输出的artifacts文件，下面列的是黑板上所有的字段，这个文件在其中勾选需要输出的字段"
- **r3b 修订**:文件名后附路径;输出配置各文件下黑板字段清单完全一样;模式切换用小分段钮,per-item 带 iterate range 推断数量;面板用专用 list 行列输入文件与输出文件。
- **r4 字段对账**:"高亮整行，提示与写在md文档中匹配的字段。md文档中没有的字段用muted颜色加在最上方并加上报错标志，表示要求有这个input字段，但实际输入没有。output同理"——matched 行高亮、missing(声明了但实际无供应)置顶 muted + 报错;input=io.inputs vs 黑板,output=io.outputs vs 产出全集。
- **r4b 收尾**(PM 2026-07-02):① "new file button，统一样式，全局都没有用过黑色按钮；还有这个list的样式，我们panel里面已经有固定的list样式了"——New file/Run-as-batch 改用 shadcn `Button variant=secondary`,test-inputs list 行改用 FileRow 同款无边框 ghost 行(选中 `bg-accent`);② "第一个input节点要求输出chapter字段，但是没有输入，不应该触发字段缺失的警告吗？"——Input 伪节点声明的图入口字段无 `source:'file'` 支撑时报 missing(见 F3);③ "add file设计简直反人类啊，直接用原生file组件选择文件或者文件夹啊，怎么会让用户输入path呢"——改原生 OS 选择器(见 F5)。
- **r5 真机 4 点反馈(PM 2026-07-03,根因收敛=「画布节点↔io config」关系模型没建对)**:① "在 GRAPH.md input 的 chapter 里临时加了 aa_number(加在 chapter 对象内部),config 弹窗没同步显示" + ② "output 的 segmentation_result 里加了 bb_number,config 也没同步"——根因:预览递归到叶子、config 只枚举顶层键,粒度差;且 io 字段全链路扁平,嵌套子字段没有运行语义 → 三层加嵌套寻址(见 F3 嵌套寻址三层贯通)。③ "定过选 input 节点只显示 input、output 节点只显示 output,现在选中 Input 节点后面板下面还挂着 output 段"——根因:面板无条件全渲染 + 边界伪节点点击一律 deselect(点 Input/Output/空白在状态层是同一件事),没有「边界节点身份」→ 选中态承载 input-boundary/output-boundary/phase/graph 四态 + 按角色收敛段(F3 归属规则本就有,属代码 drift 补齐)。④ "Test inputs 的 New file 按钮还是黑色,list 样式没对齐 panel 已有的 list"——`variant=secondary` 暗色近黑(`--secondary: oklch(0.274…)`),改**透明底 hover 亮的 ghost list 行**(对齐 test-input item 行),修订 r4b「New file 用 secondary」。方向:config 内联进节点属性(像 Properties 面板)、按角色 scoped,窄面板用可折叠段/紧凑树行解决(见 F2 r5 修订)。
- (存续)面板可见名 = **"I/O"**(文件夹路径 `input` 不变);**I/O 面板 = 实例预览,schema 编辑走 copilot/文件**(PM 2026-07-02 r1);**golden JSON 与推导实例同构**(PM 2026-07-02 r1)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| INPUT-1 | 黑板优先配置树 | 单元 `io-panel-artifacts-test-inputs`；**为什么**：数据主干是黑板,file 只是追加;勾选树 = io 声明的直接投影,一处配置三处受益(io.inputs/source:file/test input) |
| INPUT-2 | Predict/Run 输入 | 单元 `io-panel-artifacts-test-inputs`；**为什么**：predict/run 的输入选择落在 i/o 面板(live) |
| INPUT-3 | artifacts 清单替换 per-field target | 单元 `io-panel-artifacts-test-inputs`；**为什么**：文件×字段是多对多,per-field path 表达不了"一个文件装多个字段";固定格式让下游导入零成本识别 |

## 6. 测试关键点
1. 面板收敛: 无 golden 区/内联表单/schema 表单;预览+Configure+文件 list(文件名+灰色路径)。
2. 输入配置树: 黑板行与 dot 静态推断同源;勾选写回 io.inputs / `source:'file'`;Input 节点无黑板行。
3. 扫描: 真实 material-prep + node1_output 两个文件夹形状的字段树/批量折叠/编号提取正确;大文件不内联。
4. artifacts: 清单写回 GRAPH.md;engine writer 固定格式落盘(latest+history+per-item 编号继承);旧 per-field target 路径删净。
5. Predict/Run 输入: 面板选中项 = payload(live,回归)。

## 7. 涉及 region / platform
`phase-editing` · `graph-authoring` · `predict` · `run-execution` · `golden-eval` · `assets`

## 8. gaps / 报警
- 🚨 全部 F2/F3/F5/F7/F8 为 2026-07-02 r3 新定稿,实施进行中(worktree feat/io-config-tree);实施完成后按代码真相回填状态。
- 🚨 golden run/trace 侧交互 + 后端逐节点粒度:后续轮(与 golden-eval 单元一并)。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `phase-editing` · `graph-authoring` · `predict` · `run-execution` · `golden-eval` · `assets`
