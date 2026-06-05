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
| **U1** | **子图(subgraph)** | studio graph-authoring;path 反转 2026-06-04 | 布局切面→`physical-layout`◆ · 语法切面→`skill-syntax`◆ · 解析切面→`02-resolver`◆ · 执行切面→`graph-exec`(SUBGRAPH 调用) | `graph_assembler.py:_build_subgraph_node:363` · resolver `SkillResolverProtocol`/`LocalWorkspaceResolver` | drafted | path 契约已定;但 `skill-syntax` 其余语法部件真空、`physical-layout` workspace 户型待迁 → 阻塞文件级 FROZEN |
| **U2** | **golden→workspace 反转** | `GOLDEN`(PM 2026-06-03 反转) | 布局切面(.workspace/golden)→`physical-layout`◆ · 评估切面→`06-golden-eval`◆ · 失效切面→`05-invalidation` · 编译规则切面→`compile-rules`(golden-stale 移出编译期) | `runner.py:_warn_on_stale_golden_hashes_sdk:127-160`(**退役**) | drafted | `06-golden-eval` 按反转改写中(⏳);`compile-rules` delta 待标 |
| **U3** | **action/tool 不统一** | `ACTION-TOOL`→`TL2`(2026-06-04 拍板) | 执行切面(action)→`graph-exec`◆ · 工具切面(tool)→`04-tools`◆ | `actions.py:ActionDef:18`/`ActionRegistry:25` · `actions.py:ToolDef:49`/`ToolRegistry:60` | **可锁候选** | 决策 firm + 两域 status 已校正(2026-06-05);`04-tools` 数据流正文待成段 |
| **U4** | **LOGIC 干净契约(纯返回/硬禁/反写)** | LE1-3(2026-06-04 三问拍板) | 执行切面→`graph-exec`◆(LE1-3) · 编译规则切面→`compile-rules`(purity 扩展、硬禁 run_skill/FS) · 语法切面→`skill-syntax`(解冻 `03-logic-md-spec`、契约反写) | `graph_assembler.py:_build_logic_node:325`(live drift=refactor-target) | drafted | 契约已定;live drift(可变 Context/run_skill/FS)待重构归 kiro;反写解冻待做 |
| **U5** | **checkpoint 嵌套拓扑 + 存储纪律** | `CK1-6`(records/state-checkpoint,2026-06-03) | base 切面→`03-checkpoint`◆ · 内层 messages 切面→`08-messages-state`◆ · 迭代切面→`02-iterate` · agent 切面→`01-agent-loop`(经 ns 挂) · 数据切面→`data-contracts`(data delta reducer 待补) | `graph_assembler.py:151`(compile checkpointer) · `state.py:214`(messages DeltaChannel) · `cognitive_flow.py:292`(interrupt 依赖 checkpoint) | drafted | ✅ 实现 SSOT 在 03-checkpoint/08-messages-state(成段完整,CK1/2/4/5);records 已加 🔖banner 降轴①留底(递归拓扑/CK3/CK6/D-test 深度备查)。锁前可选回填 CK3/CK6 |
| **U6** | **变更→失效模型** | records/change-invalidation(Task2 C3,2026-06-03) | 失效契约切面(A1–A5 轴+矩阵)→`05-invalidation`◆ · golden 切面(A2a 编译期硬错)→`06-golden-eval` · checkpoint 切面(A2/A4/A5 置灰)→`03-checkpoint` · cache 切面(源 hash)→`01-compile` | `compiler.py:38`(cache) · `diff_skill`(待实施) | drafted | ✅ 实现 SSOT 在 05-invalidation/06-golden-eval(成段,已按反转改 eval 期);records 已加 🔖banner 降轴①留底(§2 含反转前旧内容,已警告勿用) |
| **U7** | **6 槽中间件链 + 域专槽** | `overview §6` 跨切点 | 链基础设施切面→`02-middleware`◆ · 认知槽→`03-cognitive`(CognitiveFlow) · 追踪槽→`02-observability`(Tracing) · 工具错误槽→`04-tools`(ToolError) · 并行→`02-iterate`(parallel_map,断层#3) | (middleware 工厂 + 各域;ToolError `middleware/tool_error.py` no-op) | drafted | 链+卫生槽✅;域专槽逻辑归各域(只写槽位+概述+双向链);ToolError 待实现 |
| **U8** | **退出闸(phase 不静默成功)** | `EXIT` 决策 | 退出闸切面→`05-exit-control`◆(after_agent + NudgeInjector) · 认知切面→`03-cognitive`(finish_task / goto=END 绕闸) | `NudgeInjector`(live);`after_agent` 退出闸(缺) | drafted | ⏳ 迁自 `_migration-src/04-exit-control`;after_agent 闸未接 live |
| **U9** | **可观测事件流** | `overview §6` api 面 | 事件流切面(34 typed event)→`02-observability`◆ · 追踪中间件→`02-middleware`(Tracing 槽) · API 切面→`03-api-contract`(协议→trace.jsonl/WS) | 34 类 typed event + callbacks(内联 emit 待迁 Tracing 中间件) | drafted | ✅ 迁自 06-trace-observability + api §1;内联 emit→中间件待迁 |
| **U10** | **API 操作面(engine↔studio)** | `ARCH1`(C 层) | API 契约切面→`03-api-contract`◆ · 入口实现→`07-runtime` · 事件供给→`02-observability` · 形状供给→`data-contracts`(RunResult) | `runner.py:run_skill`/`predict_skill`(live) | drafted | ✅ 五节接口成段;§3/§4 target schema 待 FROZEN 解冻回填、§5 错误码=Task3;🚨 `07-runtime` 顶层契约❌完全没设计 |
| **U11** | **图级 loop / iterate** | `GRAPH-LOOP`+`CK3` | 编排切面(batch/loop/图级)→`02-iterate`◆ · 执行切面→`graph-exec`(声明式替代 action run_skill) · 中间件→`02-middleware`(parallel_map) | `graph_assembler.py`(引擎注入回边,待实施) | drafted | ✅ 机制成段;引擎包 loop-body 的 compile 实现待做(与 U5 同 thread+ns/iter) |
| **U12** | **purity(纯函数编译期防护)** | `SANDBOX`(运行期沙箱=伪需求) | 规则切面→`compile-rules`◆ · 扫描器实现切面→`01-compile`◆(purity 扫描器 + `module_sandbox`) | `01-compile` purity 扫描器(待 LE2 扩展硬禁 run_skill/FS) | drafted | 规则↔扫描器双向;LE2 扩展(硬禁 action 里 run_skill/FS/sys.path)待做 |

---

## 2. 锁状态总账(lock-migration 骨架)

**当前:全部 `drafted`,零 `FROZEN` / 零单元 `locked`。** 锁迁移序(见 [写作规范 §1.5](../../development/design-doc-standards/01-writing-standard.md)):

1. **去 mvp0 FROZEN 残留**(R1 唯一真理前置):
   - ✅ **compile-rules 已自承载(2026-06-05,codex 执行 + Claude 核验)**:mvp0 11(93 错误码全表)+ 12(三段生命周期)已迁入 `03-compile-rules/mvp1-alignment.md`;`error_registry.py` 93 个 `doc_link` 全指 mvp1(mvp0=0);baseline 改对代码(`ERROR_REGISTRY`/`SkillLoader.compile_skill`/`scan_python_purity`)。mvp0 11/12 已划线留档(FROZEN→superseded 待 mvp0 全域处置)。
   - ⏳ 剩余:`README.md` / `00-architecture-overview.md` 的 `ground_truth` + `01-compile`/`03-assemble` alignment 仍有指向 mvp0 `12` 的链接 → 下游收尾(重定向到 mvp1 compile-rules)。
2. **可优先锁的单元**(决策 firm、争议已收敛):**U3**(action/tool 不统一)· **U4**(LOGIC 契约,文档侧)· **U1**(subgraph path 契约)。
3. **阻塞锁的真空**(见 §3),清空后才能盖单元 `locked` → 文件级 `FROZEN`。

## 3. 真空 / 重复 / drift 总账(R8 交叉检验产出)

### 🚨 真空(SSOT 缺 / 待迁,阻塞 FROZEN)
- `07-runtime`:**❌ 完全没设计**——顶层入口契约(`run_skill`/`predict_skill`/bootstrap/public API 均 live,缺契约文档)。
- `01-contract/02-skill-syntax`:子图 path 已写清,**其余语法部件(四 phase 字段/body XML/mention/iterate 声明/cognitive 模板)真空**。(连带:compile-rules 迁入后 68 个错误码 `doc_link` 暂只能指到 skill-syntax §2 概览;skill-syntax 写细后精化。)
- `01-contract/01-physical-layout`:`.workspace` 户型字段正文待从旧文档迁入(§8)。
- `05-run-inner` 多模块:`05-exit-control`/`06-golden-eval`/`07-subagent` 标 ⏳ 迁自 `_migration-src`,正文待成段。

### 🔁 重复风险(同事实两处,需确认退役)
- **U5 / U6:已核实 + 已处理(2026-06-05)。** 正式模块(`03-checkpoint`/`08-messages-state`/`05-invalidation`/`06-golden-eval`)经逐份读取确认**已成段、是当前真相 SSOT**(非"只摘要承载")。两份 records 已加 🔖 banner 降为**轴①决策留底**:`change-invalidation`(§2 含反转前旧内容=编译期硬错误,已警告勿用)、`state-checkpoint`(保留递归拓扑/CK1-6/D-test 深度,锁前回填备查)。**重复歧义已消**;深度细节未丢(留底可查)。
- `_migration-src/`(13 域 + api-contract + records):整目录是**迁移源**,与正式 `01/02/03` 三层并存。迁移核对(划线法)完成前,是最大的"同事实两处"来源——**用户已明确 records 先别删**,核对完再退役。

### ⚠️ 已记的 drift / refactor-target(已在模块文档登记,归 kiro,非真空)
- **U4** live drift:11 action 用可变 Context、3 个跑 `run_skill`、5 个碰 FS、黑板塞 `BatchAccumulator`、死簇 `code_phase_node`/`phase_executor`(见 `graph-exec` baseline 差异表 + alignment §8 + 🚨已知代码债)。
- **U5** delta:`data` 通道 delta reducer 待补;summarization middleware 从 legacy 死簇搬回 live。

---

## 交叉引用(链接, 不复制)
[`00-architecture-overview`](./00-architecture-overview.md)(模块地图 + §5 决策 + §6 跨切点)· [`README`](./README.md)· [design-doc-standards](../../development/design-doc-standards/)(治理规范)· `_migration-src/records/`(U5/U6 留底)
