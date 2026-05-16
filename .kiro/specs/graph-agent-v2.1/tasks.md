# Section 1: Overview

V2.1 落实 R0：前端暂停到 Schema 冻结；pending 继续 pending；main 一刀硬切且无 schema 2.0 兼容。执行锚点为 Q-7 四角色物理命名：根 `GRAPH.md` 只做 manifest；`LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 分别是逻辑、子图、LLM ReAct 节点，并以文件名 + YAML `mode` 双校验。总工时估算 80-120 工时。Critical Path 10 条：T0.1、T0.2、T0.3、T0.5、T1.1、T1.2、T1.4、T1.5、T2.1、T2.2。

# Section 2: Phase 0 — 基础工具 (parser/codemod/文档框架)

| 编号 | 任务 | DoD | 依赖 | 工时 | 关联 R |
|---|---|---|---|---|---|
| T0.1 | parser/loader 按 `GRAPH.md`、`LOGIC.md`、`SUBGRAPH.md`、`SKILL.md` 路由；XML 用块级劫持 raw string。 | 根 `SKILL.md`、phase 内 `GRAPH.md`、mode 不符、缺根/缺 phases 均 FATAL 且含 `file:line`；静态断言 phases/*/{LOGIC,SUBGRAPH,SKILL}.md XML body 内不出现 `<phase>`/`<depends_on>`/`<edge>`/整图拓扑标签，命中即 FATAL。 | 无 | L | R1.1/R1.2/R1.3/R2.2/R2.3/Q-1/Q-7/Amendment #1/#3 |
| T0.2 | 加载校验 `io/inputs.json`、`outputs.json`，禁止 IO 回塞 YAML/XML。 | 缺文件、非法 JSON Schema、GRAPH 引用不存在均 FATAL；`hello-world` fixture 通过。 | T0.1 | M | R1.1/R2.2/R2.3/Q-4 |
| T0.3 | `GRAPH.md` 只解析 metadata、IO ref、phase src、`depends_on`，不建 AST 节点。 | 非起点 phase 必填 `depends_on`；循环、孤儿、重复 id、src 缺失 FATAL。 | T0.1/T0.2 | L | R1.2/R1.3/R3/Q-7/Amendment #1/#2/#10 |
| T0.4 | dry-run codemod：旧 `SKILL.md` 生成 `GRAPH.md`、`phases/*/SKILL.md`、`io/*.json` 雏形。 | 只产候选文件与审查标记；snapshot 覆盖简单/复杂/多 phase，输出符合 T0.5 AST schema；验证复杂 XML 节点注入 `<!--TODO: CODEMOD_REVIEW-->`；CI 扫描 phases/**/*.md 标记，命中即 FAIL block T3.3。 | T0.1/T0.2/T0.3/T0.5 | M | R0/R3/Q-3/Q-5/R5 |
| T0.5 | 定义 LOGIC/SUBGRAPH/SKILL 三类 AST model，稳定支持 `.model_json_schema()`。 | 三类 schema 有 golden snapshot；字段、required、discriminator 稳定。 | T0.1/T0.3 | M | R1.3/R2.5/Q-4/Q-7/Amendment #9 |
| T0.6 | 重写 SKILL_AUTHORING_GUIDE、TOOL_DEVELOPMENT_GUIDE、ARCHITECTURE。 | 作者指南含 GRAPH 章；工具指南区分 Tools/Actions；架构文档映射 6 红线。 | T0.1/T0.2/T0.3/T0.5 | L | R2.4/Q-7/Amendment #7 |

# Section 3: Phase 1 — 内核改造

| 编号 | 任务 | DoD | 依赖 | 工时 | 关联 R |
|---|---|---|---|---|---|
| T1.1 | 解析 `<exit_contract>`，每轮 ReAct 在 messages 末尾追加独立 User Message。 | 单测断言最后一条为 User 且含契约；长 Prompt 不再触发 visibility 警告。 | T0.1 | M | R1.4/Q-2/Amendment #4/#5 |
| T1.2 | 新增 `phases/*/actions/*.py` loader 与 context 门面；Tools 继续 StructuredTool。 | Action 可读写黑板；grep 审计 `tools/` 0 个 ctx/context/state/blackboard 签名，现存违规 Tool 搬为 Action 并替换调用；AST 扫描 `actions/*.py`/`tools/*.py` 本地写盘 API 命中即 FATAL。 | T0.1/T0.5 | L | R1.5/R1.3/Q-7/Axiom 6/Amendment #6 |
| T1.3 | reviewer/auditor/critic 作为 ReAct 内 Tool，不进入 graph macro topology。 | Critic 不在 `depends_on`；同 phase 内有调用指标与通过/拒绝测试。 | T1.2 | M | R1.6/Axiom 5 |
| T1.4 | `finish_task(markdown)` 经 md2json 转 dict，失败静默拉起 md-patch。 | 残缺 Markdown、多余围栏、字段类型偏差均可修复；失败返回结构化错误。 | T0.2/T1.1 | M | R1.7/R1.1 |
| T1.5 | 用 manifest 拓扑 + 三类 AST 装配 LangGraph，三类节点独立 builder。 | hello-world、Tier 1、subgraph fixture e2e pass；实现基于 file mtime/stat 的 AST 缓存，首次编译增量 ≤200ms；缓存失效覆盖 GRAPH.md/phases 任一文件变更；旧根 `SKILL.md` crash。 | T0.1/T0.2/T0.3/T0.5/T1.1/T1.2/T1.4 | L | R1.2/R1.3/R2.1/R2.2/R5/Q-6/R-5 |

# Section 4: Phase 2 — 真实 in-scope 11 份 SKILL 迁移 (Tier 1/2/3, 按 Q-5)

| 编号 | 任务 | DoD | 依赖 | 工时 | 关联 R |
|---|---|---|---|---|---|
| T2.1 | Tier 1 `text-segmentation`：拆为 GRAPH、phases、io，优先恢复高频链路。 | 原测试 + V2.1 e2e pass；GRAPH 无 Prompt；SKILL phase 含 `<exit_contract>`。 | T1.5 | M | R3/Q-5/R-6/Amendment #8 |
| ~~T2.2~~ **SKIP** | ~~Tier 1 `story-deconstruction`：迁移拆解主流程。~~ | **SKIP 理由**: `skills/story-deconstruction/` 顶层 source 在 V2.1 立项时 R0 决策 2 已移入 `skills/_v2_pending/` 维持 pending, 不属 V2.1 hard cutover in-scope. tasks.md 起草时未同步剥离, 实际执行阶段确认 SKIP. 与 R-6 "in-scope 全 break by design" 不冲突 (pending skill 不属 in-scope). | — | — | R0决策2 |
| T2.3 | Tier 2 `batch-analysis`：批处理编排移入 `GRAPH.md depends_on`。 | 原测试 + e2e pass；批次输入输出走 `io/*.json`。 | T2.1/T2.2 | M | R3/Q-5/Axiom 2/Amendment #8 |
| T2.4 | Tier 2 `event-extraction`：分离抽取 Prompt 与输出 schema。 | 原测试 + e2e pass；残缺 Markdown 可由 md-patch 修复。 | T1.4/T2.1 | M | R1.7/R3/Q-5/Amendment #8 |
| T2.5 | Tier 2 `global-synthesis`：用全局黑板约定承接跨阶段变量。 | 原测试 + e2e pass；断言 `io/inputs.json` + `io/outputs.json` 显式声明全部上下游变量字段；核对 `GRAPH.md depends_on` 与 io schema 字段流向一致。 | T2.1/T2.2 | M | R3/Q-5/Axiom 4/Amendment #8 |
| T2.6 | Tier 2 `producer`：生产者审核流程改 Actor-Critic Tool，含 review subskill 内化入口。 | 原测试 + e2e pass；critic 不进 `depends_on`；`producer/review` 不再作为独立 skill 调度。 | T1.3/T2.2 | M | R1.6/R3/Q-5/Amendment #8 |
| T2.7 | Tier 2 `product-manual`：中频迁移，恢复格式与 artifact 输出。 | 原测试 + e2e pass；输出由 `outputs.json` 声明。 | T2.3/T2.4/T2.5/T2.6 | S | R3/Q-5/R-6/Amendment #8 |
| T2.8 | Tier 3 `hello-world`：迁移为最小 V2.1 示例与 smoke fixture。 | 原测试 + e2e pass；Python 单测验证 SKILL_AUTHORING_GUIDE 中 GRAPH.md 最小示例可被 parser 解析，且输出等价于 `skills/hello-world/`。 | T0.6/T1.5 | S | R1.1/R2.4/R3/Amendment #8 |
| T2.9 | Tier 3 `producer/review` subskill 内化 phase。 | `skills/producer/review/SKILL.md` 迁入 producer phase 或 Tool；grep 断言全 codebase 内无 `skills/producer/review` 路径字符串调用；producer 原测试套件 + V2.1 e2e pass；不作为独立 skill 出现在 GRAPH。 | T2.6 | S | R1.6/R3/Q-5/Amendment #8 |
| ~~T2.10~~ **SKIP** | ~~Tier 3 `examples/broken-fixtures/story-deconstruction-inline-phase` fixture 迁移。~~ | **SKIP 理由**: `skills/examples/broken-fixtures/` source **不存在** (filesystem 实证 `git log --all -- 'skills/examples/broken-fixtures*'` 完全空, git history 从未 commit 过). 仅 `apps/studio/tauri/target/debug/_up_/_up_/_up_/skills/examples/broken-fixtures/` 这种 build artifact 残留. research.md §2.2 引用为 phantom. 与 R-6 不冲突 (in-scope 11 份 SKILL.md filesystem 实证不含此 fixture). | — | — | (phantom) |
| T2.11 | Tier 3 `examples/subgraph-sample/story-deconstruction` fixture 迁移。 | smoke + e2e pass；保留 subgraph sample 覆盖；`GRAPH.md` 拓扑与 SUBGRAPH phase 可解析。 | T2.2/T0.3 | S | R1.2/R3/Q-5/Amendment #8 |

# Section 5: Phase 3 — Studio 对接 + cutover

| 编号 | 任务 | DoD | 依赖 | 工时 | 关联 R |
|---|---|---|---|---|---|
| T3.1 | Studio 后端 `compile_skill`/`run_skill` 改收 V2.1 skill root。 | backend 测试通过；preview 返回 GRAPH 拓扑、三类节点 schema、IO schema。 | T1.5/T0.5 | M | R3/Q-4/Q-6 |
| T3.2 | canvas deferred work 中 `depends_on` Optional→Required，并以 GRAPH parser 为真源。 | 后端 schema、导出 JSON Schema、样例均 required；旧 Optional 输入报错。 | T0.3/T3.1 | M | R3/Amendment #10 |
| T3.3 | feature branch 全量完成后一次性 PR 回 main，执行硬切。 | e2e 全过；11 skill 全迁 (实际 9 迁 + 2 SKIP-R0决策: T2.2 story-deconstruction 维持 pending, T2.10 broken-fixtures phantom)；旧根 `SKILL.md` 全阻断 (`find skills -maxdepth 2 -name SKILL.md` 0 命中)；提供 dual-run 影子比对脚本且 Tier 1 强制跑 (T3.3 prep `821da85` ✅)；单 skill rollback CI SOP (V21_ROLLBACK_SOP.md ✅)；PR 含停摆公告、验收 checklist、rollback 操作书 (V21_PR_META.md ✅)。 | T2.1/T2.3/T2.4/T2.5/T2.6/T2.7/T2.8/T2.11/T3.1/T3.2 (T2.2/T2.10 SKIP) | L | R0/R5/Q-5/Q-6/R-6 |

# Section 6: 风险 + 应急

- **R-1 解析硬切宕机**: feature branch 全量 e2e 后切 main；旧 main 保持到 cutover。
- **R-2 Action 低估**: 先交付同步 loader + context 门面；异步/沙箱/并发后置。
- **R-3 前端脱节**: T0.5 导出 JSON Schema；前端暂停，后端 preview 先可用。
- **R-4 测试断层**: 先铺 T1.5 e2e 与 fatal matrix，再迁 Tier 1；旧 AST 断言废弃。
- **R-5 IO 性能损耗**: 加 manifest 缓存与基准；超 200ms 则缓存 stat/AST。
- **R-6 业务停摆**: Tier 1 优先、dual-run 影子验证、单 skill rollback；main 无兼容分支。
