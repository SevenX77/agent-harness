---
doc: INDEX
status: drafted（轴③ 设计单元索引;2026-06-05 首版,据 00-architecture-overview §5/§6 + records/ 建立）
owns: engine mvp1 横切设计单元映射 · 模块×切面 owner · 单元锁状态 · 真空/重复/drift 总账
governed_by: ../../development/design-doc-standards/（00 三轴 · 02 R8 设计单元索引）
---

# Graph Agent MVP1 — 设计单元索引(INDEX · 轴③)

> 本文是 engine mvp1 的**轴③枢纽**:登记**横切设计单元**(横跨多个能力模块的 feature/决策)的「模块 × 切面 → owner + 锁 + 追溯」映射。
> **只记映射,不重述实现 / 决策**——实现 SSOT 在能力模块 baseline,决策原话在模块就近 + workflow 留底(见 [三轴总纲](../../development/design-doc-standards/00-three-axes.md))。
> 跨模块一致(审计 Q3)、单元级锁(R7)、去重(R8)全挂本表。

## 0. 三轴速览(engine 实例)

| 轴 | 在 engine 里是什么 | 载体 |
|---|---|---|
| **① Workflow**(决策脊柱 + 留底) | PM 设计决策旅程 | `00-architecture-overview.md §5`(9 条已锁决策)+ `_migration-src/records/`(跨切面模型留底)+ `../design/`(迁移叙事) |
| **② 能力模块**(代码对齐 + 自包含 SSOT) | **23 leaf 模块**:契约 A(5)/ 机制 B(17)/ API契约 C(1) | 各模块 `baseline.md` + `mvp1-alignment.md`;地图见 `00-architecture-overview §2–§4` |
| **③ 设计单元**(横切映射枢纽) | 跨模块的 feature/决策 | **本表 §1** |

## 所有权不变量(灭重叠)

- **实现规范**:一个切面只在**一个 owner 模块**写实现,其余模块只链接。扫本表「模块 × 切面」一眼照出重复(同切面两 owner = 违规)。
- **决策原话**:能力模块就近 + workflow(`overview §5` / `records/`)留底——**刻意冗余**,隐含假设护栏,非重复违规。
- **横跨 / 锁 / 追溯**:只在本 INDEX。

---

## 1. 横切设计单元登记表

> `◆` = 该切面的 **owner 模块**(实现 SSOT 在此);无 `◆` = 消费 / 受影响方(只链接)。`binds_code` 详情以 owner 模块 baseline 的 `binds_code` 为准,此处只给已核符号 + 落点。

| # | 设计单元 | 源决策(轴①) | spans:模块 × 切面 → owner | binds_code(详情见 owner baseline) | unit-lock | 锁前置 / 真空 |
|---|---|---|---|---|---|---|
| **U1** | **子图(subgraph)** | studio graph-authoring;path 反转 2026-06-04 | 布局切面→`physical-layout`◆ · 语法切面→`skill-syntax`◆ · 解析切面→`02-resolver`◆ · 执行切面→`graph-exec`(SUBGRAPH 调用) | `graph_assembler.py:_build_subgraph_node:363` · resolver `SkillResolverProtocol`/`LocalWorkspaceResolver` | **locked**(2026-06-05) | 子图 facet 三 owner 就绪(physical-layout `subgraph/` 落点 + skill-syntax §2.1/§2.4 + 02-resolver 绝对 path);skill-syntax 批3真空(resource/example/iterate/io)是 AGENT/LOGIC facet、不阻 U1,只阻文件级 FROZEN |
| **U2** | **golden→workspace 反转** | `GOLDEN`(PM 2026-06-03 反转) | 布局切面(.workspace/golden)→`physical-layout`◆ · 评估切面→`06-golden-eval`◆ · 失效切面→`05-invalidation` · 编译规则切面→`compile-rules`(golden-stale 移出编译期) | `runner.py:resolve_generation:84`(predict 回放) · `_warn_on_stale_golden_hashes_sdk`(整哈希 warn,**退役标的、仍 live** runner.py:127/246,比 prompt_hash+schema_hash 两哈希)| **locked**(2026-06-05) | `physical-layout`/`compile-rules` 已按反转写;`06-golden-eval` baseline + alignment 均 codex 终审(alignment 补现状框/§8 归 kiro);源 09 baseline 6/6 迁入、旧 G1/G2(决策 A)已退役 |
| **U3** | **action/tool 不统一** | `ACTION-TOOL`→`TL2`(2026-06-04 拍板) | 执行切面(action)→`graph-exec`◆ · 工具切面(tool)→`04-tools`◆ | `actions.py:ActionDef:18`/`ActionRegistry:25` · `actions.py:ToolDef:49`/`ToolRegistry:60` | **可锁候选** | 决策 firm + 两域 status 已校正(2026-06-05);`04-tools` 数据流正文待成段 |
| **U4** | **LOGIC 干净契约(纯返回/硬禁/反写)** | LE1-3(2026-06-04 三问拍板) | 执行切面→`graph-exec`◆(LE1-3) · 编译规则切面→`compile-rules`(purity 扩展、硬禁 run_skill/FS) · 语法切面→`skill-syntax`(解冻 `03-logic-md-spec`、契约反写) | `graph_assembler.py:_build_logic_node:325`(live drift=refactor-target) | drafted | 契约已定;live drift(可变 Context/run_skill/FS)待重构归 kiro;反写解冻待做 |
| **U5** | **checkpoint 嵌套拓扑 + 存储纪律** | `CK1-6`(records/state-checkpoint,2026-06-03) | base 切面→`03-checkpoint`◆ · 内层 messages 切面→`08-messages-state`◆ · 迭代切面→`02-iterate` · agent 切面→`01-agent-loop`(经 ns 挂) · 数据切面→`data-contracts`(data delta reducer 待补) | `graph_assembler.py:151`(compile checkpointer) · `state.py:214`(messages DeltaChannel) · `cognitive_flow.py:292`(interrupt 依赖 checkpoint) | **locked**(2026-06-05) | records 深度(递归拓扑/delta-compact/durability/CK1-6/D-test/PM 原话)已回填 `03-checkpoint`+`08-messages-state`(codex 复审纠"目标当现状"、加现状框);live 仅外层 super-step checkpoint + WorkflowState.messages DeltaChannel,内层 ns/agent checkpoint/resume/compaction 全待实现 |
| **U6** | **变更→失效模型** | records/change-invalidation(Task2 C3,2026-06-03) | 失效契约切面(A1–A5 轴+矩阵)→`05-invalidation`◆ · golden 切面(A2a 反转后 eval 期)→`06-golden-eval` · checkpoint 切面(A2/A4/A5 置灰)→`03-checkpoint` · cache 切面(源 hash)→`01-compile` | `compiler.py:compile_skill:41`(cache 壳) · `diff_skill`(待实施) | **locked**(2026-06-05) | `05-invalidation` 已写变更轴(IV1-3,golden 失效 eval 期);`records/change-invalidation-model.md` 的 1 块“编译期硬错误”= 反转前旧模型,**已由 IV2(eval 期)取代退役**、非待迁;`06-golden-eval` baseline 已成段(codex 复审) |
| **U7** | **6 槽中间件链 + 域专槽** | `overview §6` 跨切点 | 链基础设施切面→`02-middleware`◆ · 认知槽→`03-cognitive`(CognitiveFlow) · 追踪槽→`02-observability`(Tracing) · 工具错误槽→`04-tools`(ToolError) · 并行→`02-iterate`(parallel_map,断层#3) | (middleware 工厂 + 各域;ToolError `middleware/tool_error.py` no-op) | drafted | 链+卫生槽✅;域专槽逻辑归各域(只写槽位+概述+双向链);ToolError 待实现 |
| **U8** | **退出闸(phase 不静默成功)** | `EXIT` 决策 | 退出闸切面→`05-exit-control`◆(after_agent + NudgeInjector) · 认知切面→`03-cognitive`(finish_task / goto=END 绕闸) | `NudgeInjector`(live);`after_agent` 退出闸(缺) | **locked**(2026-06-05) | ⏳ 迁自 `_migration-src/04-exit-control`;after_agent 闸未接 live(实现差距,归 kiro) |
| **U9** | **可观测事件流** | `overview §6` api 面 | 事件流切面(33 typed event)→`02-observability`◆ · 追踪中间件→`02-middleware`(Tracing 槽) · API 切面→`03-api-contract`(协议→trace.jsonl/WS) · 边操作事件→`graph-exec` | `callbacks/events.py` typed events + callbacks;内联 emit 待迁 Tracing 中间件 | drafted | 主 trace 事件已迁;`_migration-src/11-io-and-edge-ops` 边操作事件/黑板切片/artifact 已分发入 `graph-exec`(执行面)+ `observability`(3 边操作事件命名,codex 复审) |
| **U10** | **API 操作面(engine↔studio)** | `ARCH1`(C 层) | API 契约切面→`03-api-contract`◆ · 入口实现→`07-runtime` · 事件供给→`02-observability` · 形状供给→`data-contracts`(RunResult) | `runner.py:run_skill:376`/`predict_skill:163`(live) · `compiler.py:compile_skill:41` | drafted | `03-api-contract` 只有摘要,`api-engine-studio-contract.md` 17 块未迁;`07-runtime` 不是空白,但顶层契约/bootstrap 未成段 |
| **U11** | **图级 loop / iterate** | `GRAPH-LOOP`+`CK3` | 编排切面(batch/loop/图级)→`02-iterate`◆ · 执行切面→`graph-exec`(声明式替代 action run_skill) · 中间件→`02-middleware`(parallel_map) | `graph_assembler.py` batch live;图级 loop compile 实现待做 | drafted | `02-iterate` alignment 目标摘要成段;baseline 只有节点级 batch,`skill-syntax` iterate 声明仍真空,records 的 CK3/loop 深度未迁全 |
| **U12** | **purity(纯函数编译期防护)** | `SANDBOX`(运行期沙箱=伪需求) | 规则切面→`compile-rules`◆ · 扫描器实现切面→`01-compile`◆(purity 扫描器 + `module_sandbox`) | `01-compile` purity 扫描器(待 LE2 扩展硬禁 run_skill/FS) | **locked**(2026-06-05) | 规则↔扫描器双向;01-compile §2 成段、compile-rules CR2 purity 码;LE2 扩展(硬禁 run_skill/FS/sys.path)归 kiro |

---

## 2. 锁状态总账(lock-migration 骨架)

**当前(2026-06-05):U1/U2/U5/U6/U8/U12 单元 `locked`(6/12),其余 `drafted`;零文件级 `FROZEN`**(文件级 FROZEN 待该文件所有单元锁齐——如 `physical-layout` 参与 U1、`compile-rules` 参与 U4/U11、`03-checkpoint`/`08-messages-state` 参与 U6/U9,故只锁单元不冻文件)。 锁状态不得继承旧 `✅` 标签,只按 §3 的 W/B/A 三关判断。

### 锁就绪复评(2026-06-05,PM 定 A 达标线 = "写全目标 + 标清现状/gap,实现归 kiro")
按此线,"只差实现"的 A◐ 达标升 ✅,"目标真空/待设计/待成段"的 A◐ 不达标:
- **A 达标(✅,目标写全 + demarcated,只差 impl)**:`physical-layout`、`compile-rules`、`02-resolver`、`03-checkpoint`、`08-messages-state`、`02-middleware`、`05-exit-control`、`07-subagent`、`06-seam/01-models`(+ 既有 `data-contracts`/`invalidation`);`06-golden-eval` 达标但 alignment 未经 codex 审(锁前补审)。
- **A 不达标(真空/待设计/待成段,非 impl)**:`skill-syntax`(批3真空)、`04-tools`(ToolError 待设计)、`07-runtime`(顶层契约待成文)、`01-compile`(机制待成段化)、`graph-exec`(nudge 收口待成段)、`02-iterate`(iterate 真空)、`03-assemble`(reference/example 受 skill-syntax)、`06-seam/02-observability`(V4 trace 增补待设计)、`03-api-contract`(defer)。
- **B 仍 ◐(baseline 待补深,与 A 达标线无关)**:`02-iterate`、`03-checkpoint`、`02-middleware`、`08-messages-state`、`03-api-contract`。
- **W 仍 ◐(决策待补链)**:`03-assemble`、`01-agent-loop`、`03-cognitive`、`04-tools`。

**锁就绪单元(◆owner 三关全 ✅)**:**U6**(变更→失效,◆=invalidation)、**U8**(退出闸,◆=05-exit-control)已就绪;**U2**(golden→workspace,◆=physical-layout+06-golden-eval)待 golden-eval alignment 补 codex 审即就绪。锁前每单元做一次 demarcation/codex 终审再 `FROZEN`。
**仍阻塞**:U1(skill-syntax 真空)、U3/U7(04-tools)、U4(skill-syntax 解冻 + graph-exec nudge)、U5(checkpoint/messages B◐)、U9(observability V4)、U10(api-contract)、U11(02-iterate)、U12(01-compile)。

1. **mvp0 只允许说"契约已迁"**:
   - `skill-spec`/`workspace-spec` 的契约内容已迁入 mvp1 对应契约模块,旧契约文档可 deprecated、不作 SSOT。
   - **mvp0/engine 迁移:纯 engine 源已清,只剩 `api-engine-studio-contract`(17 块,牵 studio,defer)**:`09-golden-eval`(baseline 迁、alignment G1-G5 已退役)、`11-io-and-edge-ops`、`records/state-checkpoint-storage-model`、`records/uncovered-areas`(约束/D-test 已分发,codex 复审)、`records/change-invalidation`(1 块退役)均已清(见 §3.2)。api-contract 清完才能说"整域 deprecated"。
2. **锁迁移序(真实版)**:
   - 先清 **B stub**:~~`01-contract/04-data-contracts/baseline.md`~~(✅ Phase 1)、~~`01-contract/05-invalidation/baseline.md`~~(✅ Phase 2,codex 复审)、~~`02-mechanism/05-run-inner/06-golden-eval/baseline.md`~~(✅ Phase 2,codex 复审,含 engine 路径 diff)、`03-api-contract/baseline.md`。
   - 再清 **A 真空/摘要未迁**:`01-contract/02-skill-syntax` 的 resource/example、iterate、io 语法真空;~~`06-golden-eval` workspace 重写~~(✅ alignment 已反转重写,余 §8 实现级 gap+未经 codex 审);`03-api-contract` 完整表;~~`11-io-and-edge-ops` 归入 `graph-exec`/`observability`~~(✅ Phase 2,codex 复审);checkpoint/messages records 深度。
   - 最后才把可锁候选(U1/U3/U4 等)从 `drafted` 升为 `locked`;现在只能叫**候选**,不能叫已锁。
3. **当前阻塞锁的事实**:任一 owner 模块 W/B/A 仍为 `stub` 或 `partial` 时,对应 unit 不能 `locked`,文件不能 `FROZEN`。

## 3. 真空 / 重复 / drift 总账(R8 交叉检验产出)

判定符号:
- `W`:设计决策/PM 原话是否落档(`alignment` 决策段 / `_migration-src/records` / `docs/design`)。
- `B`:baseline 是否对当前 `packages/graph-agent` 写出现状,且有真实 `file:symbol`。
- `A`:alignment 是否对齐 W 且覆盖迁移源,不是只写摘要/stub。

### 3.1 逐模块 3-set 真实矩阵

| 模块 | W | B | A | 缺口 / 证据 |
|---|---|---|---|---|
| `01-contract/01-physical-layout` | ✅ `mvp1-alignment.md:115,123-126` | ✅ `baseline.md:6,12`; code `loader.py:146`, `runner.py:376/527/541`, `emit.py:15` | ◐ `mvp1-alignment.md:137-138` | `.workspace` 户型已写;`evaluate_golden_baseline`/`golden`/`test_inputs` Engine SDK 未落地。 |
| `01-contract/02-skill-syntax` | ✅ `mvp1-alignment.md:574,581-588` | ✅ `baseline.md:6,12`; code `loader.py:146/1499/1592`, `manifest.py:108/143/152/162`, `mentions.py:21` | ◐ `mvp1-alignment.md:28-31,604-605` | resource/example、iterate 声明、io 切片声明仍是真空。 |
| `01-contract/03-compile-rules` | ✅ `mvp1-alignment.md:326-332`; `00-architecture-overview.md:98` | ✅ `baseline.md:6`; code `error_registry.py:15`, `loader.py:146`, `purity.py:44` | ✅ `mvp1-alignment.md`(生命周期契约+93 码全表+delta,demarcated;U12 锁,U4/U11 共享) | 文档自承载;实现 delta 仍有新 golden/iterate 码和 LE2 purity 扩展(归 kiro)。 |
| `01-contract/04-data-contracts` | ✅ `mvp1-alignment.md:27,35-38` | ✅ `baseline.md`(Phase 1 成段 2026-06-05;code state.py/result.py/exceptions.py/error_registry.py/validator_contract.py/types.py + runtime/state.py) | ✅ `mvp1-alignment.md:15-24` | ✅ B 成段;核出 BlackboardState 落点(runtime/state.py 非 core/)+ surface drift,已记 baseline §1/§7。 |
| `01-contract/05-invalidation` | ✅ `mvp1-alignment.md:29,35-37` | ✅ `baseline.md`(Phase 2 成段 2026-06-05,codex 复审;code cache.py/compiler.py/runner.py) | ✅ `mvp1-alignment.md:32-37`(IV1-3) | ✅ B 成段;旧编译期硬错误码确认从未落地、整哈希 warn 退役标的(仍 live)已记 baseline §2;核出 cache key 缺 action/tool `.py` 缺口(refactor-target)。 |
| `02-mechanism/01-compile` | ✅ `mvp1-alignment.md:24,30-31` | ✅ `baseline.md:4,20-39`; code `compiler.py:41`, `loader.py:146`, `purity.py:44` | ✅ `mvp1-alignment.md`(§2 编译流水线成段、现状/目标 demarcate;U12 锁) | §2 已成段;死簇清理 + purity LE2 归 kiro。 |
| `02-mechanism/02-resolver` | ✅ `mvp1-alignment.md:29,36-39` | ✅ `baseline.md:4,20-30`; code `skill_resolver_protocol.py`, `local_workspace_resolver.py` | ✅ `mvp1-alignment.md`(绝对 path 解析 + DI 协议形状,demarcated;U1 锁) | path 目标已定;默认实现 LocalWorkspaceResolver 函数体旧语义待改(归 kiro)。 |
| `02-mechanism/03-assemble` | ◐ `mvp1-alignment.md:22-26`; design `agent-loop-planA-create-agent-migration.md:26,36,50` | ✅ `baseline.md:4,20-38`; code `graph_assembler.py:88/158/423` | ◐ `mvp1-alignment.md:10,42` | alignment 是摘要成段;模块内承认缺独立 PM 原话链,reference/example 机制还受 `skill-syntax` 真空影响。 |
| `02-mechanism/04-run-outer/01-graph-exec` | ✅ `mvp1-alignment.md:32,40-42`; overview `00-architecture-overview.md:113` | ✅ `baseline.md`(+11-io 现状:`loader.py:528` 子图 io 1:1、`io/manager.py:108` 落盘、`io/storage.py:149`);code `graph_assembler.py:325/363`, `state_mapper.py:37`, `actions.py:18/49` | ◐ `mvp1-alignment.md`(11-io 3 能力 E1-E4 已成段,codex 复审;仅 nudge 收口待成段) | LOGIC 决策已定;11-io 子图 io/黑板/artifact/edge 已吸收,余 nudge 收口 + LE 重构归 kiro。 |
| `02-mechanism/04-run-outer/02-iterate` | ✅ `mvp1-alignment.md:28,34-35`; records `state-checkpoint-storage-model.md:100-103` | ◐ `baseline.md:4,20-28` | ◐ `mvp1-alignment.md:10,44`; `skill-syntax/mvp1-alignment.md:29-31` | baseline 只有节点级 batch;iterate 语法真空;records 的 CK3/loop 深度未迁全。 |
| `02-mechanism/04-run-outer/03-checkpoint` | ✅ `mvp1-alignment.md`(CK1-6 + 6 段 PM 原话回填) | ✅ `baseline.md`(B 成段+codex 核;code `checkpointer.py:39`, `runner.py:663`, `graph_assembler.py:151/201`, `state.py:212/214`, `phase_executor.py:82`) | ✅ `mvp1-alignment.md`(records 深度回填:递归拓扑/delta-compact/durability/D-test;codex 纠"目标当现状"+加现状框;U5 锁) | 三关全 ✅、目标/现状 demarcate;live 仅外层 super-step checkpoint,内层 ns/agent checkpoint/resume/data delta 待实现(§8,归 kiro)。 |
| `02-mechanism/05-run-inner/01-agent-loop` | ◐ module says missing PM原话 `mvp1-alignment.md:21-25`; design doc has `agent-loop-planA-create-agent-migration.md:36,80` | ✅ `baseline.md:4,20-44`; code `graph_assembler.py:423` | ◐ `mvp1-alignment.md:10,40`; design doc `agent-loop-planA-create-agent-migration.md:50` | 设计依据在 design doc,模块内未补链;live 仍手写 ReAct loop,create_agent 是目标。 |
| `02-mechanism/05-run-inner/02-middleware` | ✅ `mvp1-alignment.md:21,27-28` | ◐ `baseline.md:21-34`; code `middleware/__init__.py:58`, `factory.py:29`, `tracing.py:11`, `tool_error.py:12`, `loop_detection.py:11` | ◐ `mvp1-alignment.md:10,37` | 链基础成段;live 只接单槽,后 3 槽 no-op,ToolError/Tracing/LoopDetection 逻辑归各域未实现。 |
| `02-mechanism/05-run-inner/03-cognitive` | ◐ `mvp1-alignment.md:24-29`; design `agent-loop-planA-create-agent-migration.md:74,80,101` | ✅ `baseline.md:12,22-31`; code `cognitive_flow.py:55`, `finish_task.py:21/30`, `md2json.py:26`, `md_to_json.py:515` | ◐ `mvp1-alignment.md:31-36,45` | 主体迁入;模块内 W 原话需补链;rich 三态校验存在但未接 live。 |
| `02-mechanism/05-run-inner/04-tools` | ◐ `mvp1-alignment.md:22-31`; graph-exec LE1-3 `04-run-outer/01-graph-exec/mvp1-alignment.md:38-42` | ✅ `baseline.md:4,20-28`; code `actions.py:49/60`, `tool_error.py:12` | ❌/◐ `mvp1-alignment.md:15-16,41` | action/tool 不统一已定;工具数据流、ToolError 正文仍待设计。 |
| `02-mechanism/05-run-inner/05-exit-control` | ✅ `mvp1-alignment.md:21,28-30` | ✅ `baseline.md:4,20-23`; code `nudge_injector.py:75`, `cognitive_flow.py:511`, `graph_assembler.py:527` | ✅ `mvp1-alignment.md:15-18,39`(目标成段,U8 锁) | 文档目标成段;live 无 after_agent 退出闸=实现差距(归 kiro)。 |
| `02-mechanism/05-run-inner/06-golden-eval` | ✅ `mvp1-alignment.md:24,30-32`; overview `00-architecture-overview.md:93` | ✅ `baseline.md`(成段+codex 复审 5 处修正);code `runner.py:84/127/335`, `strategy.py`, `interception.py:29`(skeleton), `path_diff.py:11`, (studio)`golden_diff.py`/`skills.py:775` | ✅ `mvp1-alignment.md`(反转重写 + codex 终审:现状框/§8 归 kiro;U2 锁) | B 成段(源 09 baseline 实质迁入+codex 修正);A codex 终审过,旧 G1/G2/Q-G1/FROZEN(决策 A)已退役。 |
| `02-mechanism/05-run-inner/07-subagent` | ✅ `mvp1-alignment.md:21,27-29`; uncovered `uncovered-areas.md:50-70` | ✅ `baseline.md:4,20-29`; code `graph_assembler.py:1057/1120/1158`, `subagents.py` | ✅/◐ `mvp1-alignment.md:15-18,38` | 迁移源 0 未迁;live 仍内联,未收进 wrap_tool_call 中间件。 |
| `02-mechanism/05-run-inner/08-messages-state` | ✅ `mvp1-alignment.md`(HS1-4 + PM 原话回填) | ✅ `baseline.md`(B 成段+codex 核;code `state.py:214/28`, `llm_phase_node.py:275/381/809`, `cognitive_flow.py:292`) | ✅ `mvp1-alignment.md`(records 深度回填:delta/compact 正交/snapshot_frequency=50/CK6;codex 纠"目标当现状"+现状框、AgentState→WorkflowState;U5 锁) | 三关全 ✅;DeltaChannel(`WorkflowState.messages`)live;summarization/compaction/resume/ns checkpoint 全目标态未 live(§8,归 kiro)。 |
| `02-mechanism/06-seam/01-models` | ✅ `mvp1-alignment.md:21,27-29`; design `agent-loop-planA-create-agent-migration.md:152,165` | ✅ `baseline.md:4,20-24`; code `graph_assembler.py:581`, `interception.py:29/61` | ✅/◐ `mvp1-alignment.md`(predict_context 透传/usage 归零/structured-output mock 约束已迁,源 uncovered #1;create_agent 标目标态,codex 复审) | 13-models 主体 + predict 约束已迁;余 predict mock 搬回引擎(D2)。 |
| `02-mechanism/06-seam/02-observability` | ✅ `mvp1-alignment.md:21,27-29` | ✅ `baseline.md`(33 类 event 订正;+11-io 边操作事件现状 `events.py:315`/`140`); code `events.py:56-443`, `emit.py:15`, `tracing.py:58` | ◐ `mvp1-alignment.md`(11-io 3 边操作事件 OB4 已命名成段,codex 复审;余微观拓扑/Prompt 三视图/reducer diff/subagent A2) | 边操作事件族已迁;余 V4 trace 其余增补未迁全。 |
| `02-mechanism/07-runtime` | ✅ `mvp1-alignment.md:23,29-30` | ✅ `baseline.md:10,20-29`; code `runner.py:163/376/623`, `__init__.py` public surface, `test_public_api_contract.py:131` | ◐ `mvp1-alignment.md:15-16,40` | 不是"完全没设计/代码空白";缺顶层契约成文与 bootstrap 文档化。 |
| `03-api-contract` | ✅ `mvp1-alignment.md:44,50-51` | ◐ `baseline.md:10-14`; code `runner.py:163/376`, `compiler.py:41`, `result.py:68` | ❌/◐ `mvp1-alignment.md:35`; source `api-engine-studio-contract.md:13,33` | 正式 alignment 明写"完整表见迁移源";迁移源 17 块未迁,完整签名/字段/端点/router/trace/golden/iterate/compile 细节未入正式文档。 |

### 3.2 未迁入 `_migration-src` 源清单(archive 前必须补)

| 迁移源 | 未迁状态 | 应归目标 | 证据 |
|---|---:|---|---|
| `_migration-src/api-engine-studio-contract.md` | 2/19 已迁,17 块未迁 | `03-api-contract/mvp1-alignment.md` | `api-engine-studio-contract.md:13,33,38,53,63,75,87,90,120,141,156,168,181,184,199,216,230,251` |
| `_migration-src/09-golden-eval/baseline.md` | 6/6 已迁(实质入 06 baseline 成段+codex 复审) | `02-mechanism/05-run-inner/06-golden-eval/baseline.md` | `09-golden-eval/baseline.md:8,10,15,33,45,57,69` |
| `_migration-src/09-golden-eval/mvp1-alignment.md` | 1/13 形式迁入;余 12 块为反转前决策 A(G1/G2/Q-G1/FROZEN),**已确认退役**(决策 A 经 2026-06-03 PM golden→workspace 反转作废,由 06 alignment GD1-3 取代;G3/G4/G5 摘要承载)——非待迁 | `02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment.md` | `09-golden-eval/mvp1-alignment.md:9,19,31,34,50,59,64,69,74,84,92,98,108` |
| `_migration-src/11-io-and-edge-ops/baseline.md` | 6/6 已迁(执行面→graph-exec、事件面→observability,codex 复审) | `02-mechanism/04-run-outer/01-graph-exec` + `02-mechanism/06-seam/02-observability` | `11-io-and-edge-ops/baseline.md:11,13,18,34,44,55,65` |
| `_migration-src/11-io-and-edge-ops/mvp1-alignment.md` | 9/9 已迁(E1-E4→graph-exec、OB4/3 边操作事件→observability;FROZEN 解冻归 skill-syntax/compile-rules/physical-layout) | `02-mechanism/04-run-outer/01-graph-exec` + `02-mechanism/06-seam/02-observability` | `11-io-and-edge-ops/mvp1-alignment.md:10,12,17,25,34,43,54,65,74,80` |
| `_migration-src/records/state-checkpoint-storage-model.md` | 14/14 已迁(深度回填 checkpoint+messages-state,codex 复审纠"目标当现状") | `02-mechanism/04-run-outer/03-checkpoint` + `02-mechanism/05-run-inner/08-messages-state` | `state-checkpoint-storage-model.md:15,25,28,57,77,82,95,107` |
| `_migration-src/records/uncovered-areas.md` | 19/19 已迁(predict 约束→models/golden、checkpointer×middleware 约束→checkpoint/messages,codex 复审) | `06-seam/01-models` + `05-run-inner/06-golden-eval` + `04-run-outer/03-checkpoint` + `05-run-inner/08-messages-state` | `uncovered-areas.md:6,43,76,93,98` |
| `_migration-src/records/change-invalidation-model.md` | 6/7 迁 + 1 块**退役**(§2 反转前“golden 失效=编译期硬错误”矩阵,经 IV2 eval 期反转作废,勿当现状) | `01-contract/05-invalidation` + `05-run-inner/06-golden-eval` | `change-invalidation-model.md:10,28` |

### 3.3 非 `_migration-src` 真空 / drift

- `01-contract/02-skill-syntax`:resource/example、iterate、io 切片语法仍真空(`mvp1-alignment.md:28-31,605`)。
- ~~`01-contract/04-data-contracts/baseline.md`:baseline 仍是待迁 stub~~ → ✅ Phase 1 已成段(2026-06-05)。
- `02-mechanism/07-runtime`:代码 live(`runner.py:163/376/623`),但顶层入口契约/bootstrap 未成段(`mvp1-alignment.md:15-16,40`)。
- `GraphAgentHarness` 旧名仍出现在旧注释/示例/测试文本中,但当前 public 入口走 `run_skill`/`predict_skill`;这属于 runtime 文档/注释债,不能反推 live 入口类仍存在(`rg GraphAgentHarness` 命中 examples/tests/callback docstrings)。

### 3.4 重复风险(同事实两处)

- `_migration-src/` 与正式 `01/02/03` 三层仍并存。凡 §3.2 未迁源未清,都不能把旧源归档,也不能声称正式模块完整 SSOT。
- `records/change-invalidation-model.md` 和 `records/state-checkpoint-storage-model.md` 已有留底 banner,但**仍含未迁深度/旧反转前内容**;重复风险未完全消失,只能说"已有警示,待迁/待退役"。

---

## 交叉引用(链接, 不复制)
[`00-architecture-overview`](./00-architecture-overview.md)(模块地图 + §5 决策 + §6 跨切点)· [`README`](./README.md)· [design-doc-standards](../../development/design-doc-standards/)(治理规范)· `_migration-src/records/`(U5/U6 留底)
