---
module: 02-mechanism/05-run-inner/06-golden-eval
doc: baseline
status: audited-ready（WS-E7 回写:live=逐节点回放(resolve_generation P0)+ engine 路径 diff(→success)+ prompt+schema 双哈希 warn(退役标的)+ Engine evaluate_golden_baseline 读 workspace_dir/golden 并产逐节点字段 diff/report;Studio 仍有整 final_state diff/整次快照;拦截仍在 gateway 包、engine interception 是未接线 skeleton）
binds_alignment: ./mvp1-alignment.md
binds_code: packages/graph-agent/src/graph_agent/core/runner.py:{resolve_generation, _warn_on_stale_golden_hashes_sdk, path diff(:335)} · core/_predict_internal/{models.py:GoldenCase, strategy.py:MockStrategy, interception.py(skeleton), path_diff.py, stub.py} · packages/graph-agent-gateway/src/graph_agent_gateway/{call/predict.py, resolver.py} · (studio) apps/studio/backend/app/services/{golden_diff.py, diagnostic_export.py, skills.py:golden_dir_for}
---

# 06-golden-eval — Baseline(当下代码实现逻辑)

> **Scope**: golden(各 agent 节点**期望输出**)的「回放 / 失效 / diff」的**现状代码**。WS-E7 已补上 Engine-first `evaluate_golden_baseline` 逐节点评估 API;Studio 渲染/HTTP/CRUD 仍只是消费者层,不定义 Engine。
> **现状一句话**:engine 的 predict mock 已**逐节点**(`GoldenCase.expected_traces` 按 phase 存、`resolve_generation` P0 按 phase 回放);WS-E7 又新增 `evaluate_golden_baseline` 从 `workspace_dir/golden/<baseline_id>` 读取 baseline/cases,真实运行 skill,按 phase output 做字段级 diff/score,并写 `report.json`。仍未完成的不是 Engine eval API,而是 predict mock 拦截搬回 engine、空 golden 模版、Studio HTTP/UI 薄接线,以及旧 hash warn 的退役。

## UI/UX
N/A —— golden diff 渲染在 studio;engine 只产回放 + (目标)逐节点 diff 数据。

## 前端逻辑
N/A(engine 无前端)—— golden 编辑 / diff 展示 / promote 在 studio 侧(`TracePanel.tsx` / `diff/DiffView.tsx`);engine 供 golden 回放与(路径)评估。

## 后端功能

### 1. 逐节点 golden 回放(live)
- `GoldenCase`(`core/_predict_internal/models.py:12`):`inputs` + `metadata`(`phase_name`/`prompt_hash`/`io_outputs_schema_hash`,:18)+ `expected_traces: dict[phase_name → expected_output]`(:20)——**已是逐节点结构**(一份 GoldenCase 天然按 phase 存多个期望输出)。
- `SDKPredictContext.resolve_generation`(`core/runner.py:84`):predict 时每个 phase 吐什么 mock,**4 级优先**——P0 `golden_case`(:94,`has_golden_case`→`get_golden_output`→`record_mock_source(…,"golden_case")`→return)→ P1 `copilot`(:99,`copilot_predict` 回调)→ P1 `manual_override`(:113)→ P2 `heuristic_stub`(:122,`generate_heuristic_stub(schema)`)。**P0 按 phase_name 逐节点回放**。
- mock 策略族(`core/_predict_internal/strategy.py`):抽象基类 `BaseMockStrategy`(:17,`has_golden_case`:24 / `get_golden_output`:28)+ `HeuristicStubStrategy`(:58)/ `OverrideStrategy`(:71)/ `GoldenCaseStrategy`(:103,`has_golden_case`:119 / `get_golden_output`:122 查 `expected_traces`)/ `BacktestStrategy`(:126);`MockStrategy.from_param`(:151)按 `mock_llm` 参数类型选策略。

### 2. golden 来源现状(engine = mock_llm 参数 + WS-E7 workspace eval;studio 整次快照仍存在)
- engine predict mock:golden 来源 = caller 经 `mock_llm` 参数传入的 **`Path`**(`MockStrategy.from_param`:151 → `_load_golden_case`:176 → `GoldenCaseStrategy`:160),**不**绑技能源码、不读 `phases/<id>/golden.json`。
- engine eval:WS-E7 `evaluate_golden_baseline` 读取 `<workspace_dir>/golden/<baseline_id>/baseline.json` 与 `cases/<case_id>.json`,case 用 `phase_id` 绑定节点,`expected_output` 与该节点实际输出做字段 diff,结果写 `<workspace_dir>/golden/<baseline_id>/report.json`。
- studio:`golden_diff.py:set_golden_baseline_for_run`(:34)把一次满意 run 的 `final_state.json` **整个 copy** 成快照 golden,落到 **`skill/.workspace/golden/<run_id>/final_state.json`**(`_golden_root_for`:113 → `skills.py:golden_dir_for`:775 = `.workspace/golden`;`_golden_dir_for`:117 加 `<run_id>`)——**整次快照**,非逐节点常驻。
- 故 `.workspace/golden`(`01-physical-layout §2.2` 落点)现在有两类事实:Studio 旧整次快照仍存在;Engine WS-E7 eval 路径已读写 `workspace_dir/golden/<baseline_id>` 的逐节点 case/report 户型。Studio 若继续提供 UI/HTTP,只能消费这个 Engine 户型,不能反向发明 Studio-only schema。

### 3. predict 拦截现状(gateway 包 live + engine skeleton 未接线)
- **Live 拦截在 gateway 包**:`packages/graph-agent-gateway/src/graph_agent_gateway/call/predict.py:17 PredictGatewayChatModel(GatewayChatModel)`,`_generate`(:34)短路 provider、调 `predict_context.resolve_generation`(:42);由同包 `resolver.py:119-122`(`predict_context` 非空时)接线。→ mock **内容**解析在 engine(`resolve_generation`),**拦截层**(短路 ChatModel)在**独立包 `graph-agent-gateway`**(**非** `graph-agent`)。
- **Engine skeleton 未接线**:`graph-agent` 内 `core/_predict_internal/interception.py:29` 同名 `PredictGatewayChatModel`,docstring 标 "skeleton"(:1);`_generate`(:61)走 `_select_mock_payload`(:142)**直接**调 `mock_strategy`(绕过 `resolve_generation`)。⚠️ 它走 golden_case / manual / heuristic 三路(:144-155),**缺 `copilot_predict` 回调这一层**——能借 manual override 的 `source="copilot"` 透出 copilot **标签**(`strategy.py:get_manual_source`:96),但无 `resolve_generation` 里**动态调 `copilot_predict` 回调**(`runner.py:99-111`)的能力;无 resolver 接线 → 现状不 live。= alignment G5"拦截搬进引擎"的目标骨架,记 refactor-target。

### 4. golden 失效现状(prompt+schema 双哈希 warn,退役标的;与 invalidation 共指)
- `_warn_on_stale_golden_hashes_sdk`(`core/runner.py:127`,predict 路径 `:246` 调用):逐 golden_case 比 metadata 的 `prompt_hash`(:146)+ `io_outputs_schema_hash`(:147)**两个独立哈希**,任一变即 `logger.warning`、**不 block**;仅当调用方传入 `current_hashes` 时才有比对对象。⚠️ 它只按每个 `GoldenCase.metadata.phase_name` 取**一个** phase 比,**不是**逐 `expected_traces` entry 校验(粒度粗)。
- ⚠️ = `invalidation` IV3 退役标的(改 prompt 即误报);旧"编译期硬错误 `[F-v3-golden-stale-fields]`"**从未落地**(error_registry 无任何 golden 码,见 `invalidation/baseline §2`)。反转后失效移 **eval 期**(compile 读不到 `.workspace`)。

### 5. diff 现状(engine 路径 diff + WS-E7 逐节点字段 diff;studio 字段 diff 整 final_state)
- **engine 路径 diff(live,逐 run)**:predict/backtest 时若 strategy 带 `expected_path`(`GoldenCaseStrategy.expected_path` strategy.py:114 / `BacktestStrategy`:132,来自 golden_case),`runner.py:335-346` 用 `path_diff.py:compute_diff`(:11,LCS / `SequenceMatcher` 比 phase 名序列)算 `missing`/`extra`/`order_mismatch` → `PathDiff`;**`RunResult.success` 由 path_diff 推导**(无 missing/extra/order_mismatch 才 success,`runner.py:348`)。这是 engine 已有的**逐 run 路径级**评估,**非字段级、非逐节点输出 diff**。
- **engine 字段 diff(live,逐节点 case)**:`core/_predict_internal/golden_eval.py:diff_outputs` / `calculate_score` 递归比较 actual output 与 expected output;`evaluate_golden_baseline_impl` 按 case 写 `status/score/diff/stale_fields`。新增 required output 缺失时 case 标为 `stale`,不让 compile fatal。
- **studio 字段 diff(live,整 final_state)**:`golden_diff.py:compare_run_to_golden`(:68)→ `_diff_value`(:130,递归字段 diff,文本 `SequenceMatcher` 相似度、数值比例、带分)/ `_score`(:201)。这是 Studio 旧整次快照 diff,后续 UI 应渲染 Engine report 而不是复制 Engine 评估规则。

### 6. 409 守卫(studio)+ 空模版骨架(engine,可复用)
- 409 守卫:`diagnostic_export.py:assert_trace_can_be_promoted_to_golden`(:25),predict 来源 trace(`is_predict=True`,`_is_predict_trace`:45)→ 409 `PREDICT_TRACE_CANNOT_BE_GOLDEN`(:36)——防 predict mock 产物被固化成 golden。
- 空 golden 模版骨架:`stub.py:generate_heuristic_stub`(:12)+ `_value_for_schema`(:30)/ `_object_value_for_schema`(:76)按 schema 遍历生成占位——alignment G4 空 golden 模版复用此骨架。

## API
- golden 回放入口:`resolve_generation`(`runner.py:84`,经 gateway `PredictGatewayChatModel._generate` 调用)。
- golden 加载:`MockStrategy.from_param`(`Path` → `_load_golden_case`)。
- 路径评估(engine 现有,逐 run):`runner.py` path diff(:335)→ `RunResult.success`。
- 逐节点字段评估(engine live):`graph_agent.evaluate_golden_baseline(...)` → `core/_predict_internal/golden_eval.py:evaluate_golden_baseline_impl`。

## Data Model / State
- `GoldenCase`(`models.py:12`):`inputs` + `metadata`(phase_name / prompt_hash / io_outputs_schema_hash)+ `expected_traces`(逐节点)。
- golden eval case schema(live):`case_id` / `phase_id` / `inputs` / `expected_output`;report case 输出 `status` / `score` / `diff` / `stale_fields`。
- studio 快照 golden:`_golden_root_for(skill_id)/run_id`(整次)。

## 当前边界(这个模块现在不是什么)
- **非 Studio 产品闭环**:Engine 已提供 workspace golden eval API;Studio HTTP/UI/promote 仍需消费该 report,旧整次快照不能作为 Engine truth。
- **空 golden 模版未实现**:当前 eval 读取既有 baseline/cases,不负责生成空 case。
- **拦截非在 engine**:在 gateway;engine skeleton 未接线(且缺 copilot 级)。
- **失效非 eval 期 / 非编译期硬错误**:现状是运行期 prompt+schema 双哈希 warn;编译期硬错误从未落地。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标(alignment,**反转后**) |
|---|---|---|
| golden 来源 | predict mock 仍可 caller 传 `Path`;Engine eval 读取 `workspace_dir/golden/<baseline_id>/cases` | 作者 / copilot 预定义常驻 |
| golden 落点 | Engine eval 读写 `workspace_dir/golden/<baseline_id>`;Studio 旧整次快照仍存在 | `.workspace/golden` **逐节点常驻**(反转决策 A;**非** `phases/<id>/golden.json`) |
| 回放 | ✅ 已逐节点(`expected_traces[phase]` P0) | 不变,只换来源(从 `.workspace` 逐节点加载) |
| diff | engine 路径 diff(逐 run→success)+ Engine `evaluate_golden_baseline` 逐节点字段 diff + studio 旧整次 diff | engine SDK **逐节点字段** diff(算法复用换粒度) |
| 失效 | Engine eval case 标 `stale`;旧 prompt+schema 双哈希 warn 仍 live 且属退役标的 | **eval 期** staleness(只看 `io.outputs` 必填字段;**非编译期**) |
| 拦截 | gateway 包 `PredictGatewayChatModel`(engine skeleton 未接线、缺 copilot 回调层) | 搬进 engine(`06-seam/01-models`) |

> **验"是否按 mvp1 改了"**:① golden 从 workspace `golden/<baseline_id>/cases` **逐节点**加载(非 skill 源码 golden.json);② diff 是 engine SDK **逐节点字段**纯函数(`evaluate_golden_baseline`);③ 失效在 eval 期、只看 `io.outputs` 必填字段(非编译期)。仍未完成:engine interception 搬迁 + `copilot_predict` 回调层、`_warn_on_stale_golden_hashes_sdk` 退役、Studio HTTP/UI 薄接线。

## 读代码主路径提示
回放:`runner.py:resolve_generation`(:84,P0 :94)← gateway `call/predict.py:_generate`(:34,`resolver.py:119` 接线)。策略选择:`strategy.py:MockStrategy.from_param`(:151)→ `GoldenCaseStrategy`(:103)。engine 路径 diff:`runner.py:335` → `path_diff.py:compute_diff`(:11)→ `RunResult.success`。失效 warn(退役):`runner.py:_warn_on_stale_golden_hashes_sdk`(:127,调用 :246)。studio 字段 diff(待复用):`golden_diff.py:_diff_value`(:130)。engine 拦截 skeleton(G5 标的):`_predict_internal/interception.py:29`。

## 交叉引用(链接, 不复制)
[mvp1-alignment](./mvp1-alignment.md)· `01-contract/01-physical-layout`(`.workspace/golden` 落点,双向)· `01-contract/05-invalidation`(失效轴 / 退役标的,双向)· `06-seam/01-models`(predict mock 拦截搬引擎 G5)· `01-contract/03-compile-rules`(CR3 golden-stale 码归属)
