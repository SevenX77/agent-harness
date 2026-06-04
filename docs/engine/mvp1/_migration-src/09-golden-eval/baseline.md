---
module: 09-golden-eval
doc: baseline
status: drafted
last_verified: 2026-06-03
aligns_with: ../../../studio/mvp1/02_capabilities/golden-eval.md
---

# 09-golden-eval — Baseline(现状)

核心结论:引擎 predict mock 层**已经是逐节点 golden**(`GoldenCase.expected_traces` 按 phase 存、`resolve_generation` 按 phase 回放、metadata 带 `io_outputs_schema_hash`、schema 漂移检测已在);**"整次运行快照"的旧 golden 模型只存在于 Studio 后端 `golden_diff.py`,不在引擎 mock 层**。字段级评分 diff 算法也已存在(只是作用在整 `final_state`)。

## 覆盖代码(含覆盖率)

覆盖率:100%。覆盖 studio golden-eval 设计对应的引擎现状(回放/失效检测/diff/守卫)+ 物理布局 FROZEN 边界。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| `GoldenCase`(用途:预测回测用例,绑一个输入 + 逐 phase 期望输出) | `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:12-23` | `inputs` + `metadata`(phase_name/prompt_hash/io_outputs_schema_hash)+ `expected_traces: dict[phase_name → expected_output]`——**已是逐节点结构** |
| `SDKPredictContext.resolve_generation`(用途:决定每个 phase predict 时吐什么 mock 输出) | `packages/graph-agent/src/graph_agent/core/runner.py:84-124` | 4 级优先:P0 `golden_case` → P1 `copilot` → P1 `manual` → P2 `heuristic_stub`,**P0 按 phase_name 逐节点回放** |
| mock 策略族 | `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py:58-173` | `HeuristicStubStrategy`/`GoldenCaseStrategy`/`BacktestStrategy`/`OverrideStrategy` + `MockStrategy.from_param`(按 mock_llm 参数类型选策略) |
| 逐节点 golden 查/取 | `strategy.py:119-123` | `GoldenCaseStrategy.has_golden_case(phase)=phase in expected_traces`;`get_golden_output=expected_traces[phase]` |
| schema 漂移检测(**只 warn**) | `runner.py:127-160` | `_warn_on_stale_golden_hashes_sdk` 比对 golden metadata 的 `io_outputs_schema_hash` vs 当前,**只 `logger.warning`,不报错** |
| 409 守卫 | `apps/studio/backend/app/services/diagnostic_export.py:25-55` | `assert_trace_can_be_promoted_to_golden`:predict trace(`is_predict=True`)→ 409 `PREDICT_TRACE_CANNOT_BE_GOLDEN` |
| 旧整次快照 golden(将被取代) | `apps/studio/backend/app/services/golden_diff.py:34-65` | `set_golden_baseline_for_run`:把 run 的 `final_state.json` copy 进 `golden/<run_id>/`——**整次快照** |
| 字段级评分 diff(算法已现成) | `golden_diff.py:130-216` | `_diff_value`/`_score`:递归字段 diff,文本用 `SequenceMatcher` 相似度、数值用比例、带分,**作用在整 final_state** |
| golden 存储(旧) | `docs/engine/mvp0/workspace-spec/baseline.md:81-105`(§3.2) | `golden/<baseline_id>/{baseline.json,report.json,cases/}`——整次结构;且 §3.2 文字"把 predict RunResult 固化为 baseline"与 409 守卫矛盾(stale) |
| 物理布局(FROZEN) | `docs/engine/mvp0/skill-spec/01-physical-layout.md:14-28` | `phases/<id>/` 含 `{SKILL\|LOGIC\|SUBGRAPH}.md` + 可选 `validator.py` / `actions/`——**当前无 golden 文件位** |

## 编号执行流程(现状)

1. `predict_skill(..., mock_llm=...)` 把 mock_llm 参数交 `MockStrategy.from_param` → 得到一个策略:`None`→Heuristic、`Path`→GoldenCase、`list`→Backtest、`dict`→Override,见 `strategy.py:150-173`。
2. predict 跑到一个 agent phase 时,gateway 的 `PredictGatewayChatModel._generate`(**注:拦截在 gateway**)短路调 `SDKPredictContext.resolve_generation(phase_name, role, messages)`,见 `runner.py:84`。
3. `resolve_generation` 先查 P0:`strategy.has_golden_case(phase_name)` 命中 → `get_golden_output(phase_name)` 直接当输出,`mocked_source="golden_case"`,见 `runner.py:94-97`。
4. 无 golden → 依次 P1 copilot / P1 manual / P2 `generate_heuristic_stub(schema)`(按该 phase 的 `io.outputs` schema 生成占位),见 `runner.py:99-124`。
5. `GoldenCase.expected_traces` 是 `dict[phase_name → expected_output]`,所以一份 GoldenCase 已天然按节点存多个期望输出,见 `models.py:20-23`。
6. `_warn_on_stale_golden_hashes_sdk` 逐 golden_case 比对 metadata 的 `prompt_hash`/`io_outputs_schema_hash` 与传入 `current_hashes`,不一致 **只打 warning**,见 `runner.py:148-160`。
7. Studio 侧把一次满意 run 的 `final_state.json` 整个 copy 成 golden baseline(`set_golden_baseline_for_run`),compare 时 diff 整 final_state(`compare_run_to_golden` → `_diff_value`),见 `golden_diff.py:34-110`。
8. 固化前过 409 守卫:predict 来源 trace 被拒,见 `diagnostic_export.py:33-42`。

## Baseline / Alignment 差异

| 维度 | baseline 现状 | mvp1 目标 |
|---|---|---|
| golden 来源 | 「输入绑定的 GoldenCase」当 `mock_llm` 参数传入 / Studio 从 run 快照固化 | **每节点常驻、作者/copilot 填、随技能提交**,不绑特定输入、不当参数传 |
| 回放 | 已逐节点(`expected_traces[phase]`) | 不变(只换 golden 来源:从 workspace skill 源码逐节点加载) |
| 失效 | 运行期比 schema_hash、**只 warn** | **编译期**:golden 缺 `io.outputs` 新必填字段 → **编译错误** |
| diff | 整 `final_state`(算法现成) | **逐节点**(算法复用,换喂入粒度) |
| 存储 | `.workspace/golden/<baseline_id>/`(整次) | `phases/<phase_id>/golden.json`(逐节点、随技能进 git,**决策 A**) |
| 拦截 | mock 内容解析在引擎,拦截在 **gateway**(`PredictGatewayChatModel`) | 拦截搬进引擎(接上轮 D2) |

## 代码索引(clues)

- `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:12-23`:`GoldenCase`(逐节点 `expected_traces`)。
- `packages/graph-agent/src/graph_agent/core/runner.py:84-124`:`resolve_generation` 4 级 mock。
- `packages/graph-agent/src/graph_agent/core/runner.py:127-160`:`_warn_on_stale_golden_hashes_sdk`(只 warn)。
- `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py:103-144`:`GoldenCaseStrategy`/`BacktestStrategy` 逐 phase 查取。
- `apps/studio/backend/app/services/golden_diff.py:34-216`:旧整次快照固化 + 字段级 diff 算法。
- `apps/studio/backend/app/services/diagnostic_export.py:25-55`:409 守卫。
- `docs/engine/mvp0/skill-spec/01-physical-layout.md:14-28`:FROZEN 物理布局(待加 golden.json 位)。
- `docs/engine/mvp0/workspace-spec/baseline.md:81-105`:旧 golden 整次结构(待改)。

## 待办/疑点

1. 现 golden 失效检测按整 `io_outputs_schema_hash`,粒度太粗(改 prompt 不该触发但 schema_hash 可能也变);新模型要改为字段级 + 编译期硬错误(见 alignment §G2)。
2. 现 golden 来源含「输入绑定的 GoldenCase」与「Studio run 快照」两路,与新「逐节点作者定」模型并存,迁移时要退役旧两路。
3. `golden.json` 落进 `phases/<id>/`(决策 A)需改 FROZEN `01-physical-layout`,属解冻项(见 alignment)。
