---
module: 02-mechanism/05-run-inner/06-golden-eval
doc: baseline
status: audited-ready（B 成段 + codex 复审修正:对 graph-agent + graph-agent-gateway + apps/studio grep 核 2026-06-05;live=逐节点回放(resolve_generation P0)+ engine 路径 diff(→success)+ prompt+schema 双哈希 warn(退役标的)+ studio 字段 diff(整 final_state)+ studio 写 .workspace/golden 整次快照;拦截在 gateway 包、engine interception 是未接线 skeleton;逐节点常驻 golden / eval 期失效 / engine SDK 逐节点字段 diff 未实现）
binds_alignment: ./mvp1-alignment.md
binds_code: packages/graph-agent/src/graph_agent/core/runner.py:{resolve_generation, _warn_on_stale_golden_hashes_sdk, path diff(:335)} · core/_predict_internal/{models.py:GoldenCase, strategy.py:MockStrategy, interception.py(skeleton), path_diff.py, stub.py} · packages/graph-agent-gateway/src/graph_agent_gateway/{predict_interception.py, resolver.py} · (studio) apps/studio/backend/app/services/{golden_diff.py, diagnostic_export.py, skills.py:golden_dir_for}
---

# 06-golden-eval — Baseline(当下代码实现逻辑)

> **Scope**: golden(各 agent 节点**期望输出**)的「回放 / 失效 / diff」的**现状代码**。alignment 的"逐节点常驻 golden + eval 期失效 + engine SDK 逐节点 diff"是**目标**(且按 2026-06-03 golden→workspace 反转),当前多为复用现成件、关键收口未实现。
> **现状一句话**:engine 的 predict mock 已**逐节点**(`GoldenCase.expected_traces` 按 phase 存、`resolve_generation` P0 按 phase 回放),但 ① golden **来源**是 caller 经 `mock_llm` 参数传入的 `Path` 或 studio run 快照,**不是**作者预定义常驻文件、engine 也**不读** `.workspace/golden`(该落点 `01-physical-layout §2.2` 已定义但 engine code 未读写);② **拦截**在 gateway(`predict_interception.py`),engine `interception.py` 是未接线 skeleton;③ 失效只有 schema-hash **warn**(退役标的),编译期硬错误从未落地;④ 字段级 diff 算法现成但在 **studio**、作用于**整 `final_state`**。

## UI/UX
N/A —— golden diff 渲染在 studio;engine 只产回放 + (目标)逐节点 diff 数据。

## 前端逻辑
N/A(engine 无前端)—— golden 编辑 / diff 展示 / promote 在 studio 侧(`TracePanel.tsx` / `diff/DiffView.tsx`);engine 供 golden 回放与(路径)评估。

## 后端功能

### 1. 逐节点 golden 回放(live)
- `GoldenCase`(`core/_predict_internal/models.py:12`):`inputs` + `metadata`(`phase_name`/`prompt_hash`/`io_outputs_schema_hash`,:18)+ `expected_traces: dict[phase_name → expected_output]`(:20)——**已是逐节点结构**(一份 GoldenCase 天然按 phase 存多个期望输出)。
- `SDKPredictContext.resolve_generation`(`core/runner.py:84`):predict 时每个 phase 吐什么 mock,**4 级优先**——P0 `golden_case`(:94,`has_golden_case`→`get_golden_output`→`record_mock_source(…,"golden_case")`→return)→ P1 `copilot`(:99,`copilot_predict` 回调)→ P1 `manual_override`(:113)→ P2 `heuristic_stub`(:122,`generate_heuristic_stub(schema)`)。**P0 按 phase_name 逐节点回放**。
- mock 策略族(`core/_predict_internal/strategy.py`):抽象基类 `BaseMockStrategy`(:17,`has_golden_case`:24 / `get_golden_output`:28)+ `HeuristicStubStrategy`(:58)/ `OverrideStrategy`(:71)/ `GoldenCaseStrategy`(:103,`has_golden_case`:119 / `get_golden_output`:122 查 `expected_traces`)/ `BacktestStrategy`(:126);`MockStrategy.from_param`(:151)按 `mock_llm` 参数类型选策略。

### 2. golden 来源现状(engine = mock_llm 参数;studio 整次快照写 `.workspace/golden`)
- engine:golden 来源 = caller 经 `mock_llm` 参数传入的 **`Path`**(`MockStrategy.from_param`:151 → `_load_golden_case`:176 → `GoldenCaseStrategy`:160),**不**绑技能源码;**engine 自身不读写 `.workspace/golden`**、不读 `phases/<id>/golden.json`。
- studio:`golden_diff.py:set_golden_baseline_for_run`(:34)把一次满意 run 的 `final_state.json` **整个 copy** 成快照 golden,落到 **`skill/.workspace/golden/<run_id>/final_state.json`**(`_golden_root_for`:113 → `skills.py:golden_dir_for`:775 = `.workspace/golden`;`_golden_dir_for`:117 加 `<run_id>`)——**整次快照**,非逐节点常驻。
- 故 `.workspace/golden`(`01-physical-layout §2.2` 落点)**已被 studio 真实读写(整次快照)**;但反转后目标的**逐节点常驻 golden**(每 agent 节点期望输出)**尚未实现**——engine 不从 `.workspace/golden` 逐节点加载,studio 写的也是整次 `final_state`、非逐节点。

### 3. predict 拦截现状(gateway 包 live + engine skeleton 未接线)
- **Live 拦截在 gateway 包**:`packages/graph-agent-gateway/src/graph_agent_gateway/predict_interception.py:17 PredictGatewayChatModel(GatewayChatModel)`,`_generate`(:34)短路 provider、调 `predict_context.resolve_generation`(:42);由同包 `resolver.py:119-122`(`predict_context` 非空时)接线。→ mock **内容**解析在 engine(`resolve_generation`),**拦截层**(短路 ChatModel)在**独立包 `graph-agent-gateway`**(**非** `graph-agent`)。
- **Engine skeleton 未接线**:`graph-agent` 内 `core/_predict_internal/interception.py:29` 同名 `PredictGatewayChatModel`,docstring 标 "skeleton"(:1);`_generate`(:61)走 `_select_mock_payload`(:142)**直接**调 `mock_strategy`(绕过 `resolve_generation`)。⚠️ 它走 golden_case / manual / heuristic 三路(:144-155),**缺 `copilot_predict` 回调这一层**——能借 manual override 的 `source="copilot"` 透出 copilot **标签**(`strategy.py:get_manual_source`:96),但无 `resolve_generation` 里**动态调 `copilot_predict` 回调**(`runner.py:99-111`)的能力;无 resolver 接线 → 现状不 live。= alignment G5"拦截搬进引擎"的目标骨架,记 refactor-target。

### 4. golden 失效现状(prompt+schema 双哈希 warn,退役标的;与 invalidation 共指)
- `_warn_on_stale_golden_hashes_sdk`(`core/runner.py:127`,predict 路径 `:246` 调用):逐 golden_case 比 metadata 的 `prompt_hash`(:146)+ `io_outputs_schema_hash`(:147)**两个独立哈希**,任一变即 `logger.warning`、**不 block**;仅当调用方传入 `current_hashes` 时才有比对对象。⚠️ 它只按每个 `GoldenCase.metadata.phase_name` 取**一个** phase 比,**不是**逐 `expected_traces` entry 校验(粒度粗)。
- ⚠️ = `invalidation` IV3 退役标的(改 prompt 即误报);旧"编译期硬错误 `[F-v3-golden-stale-fields]`"**从未落地**(error_registry 无任何 golden 码,见 `invalidation/baseline §2`)。反转后失效移 **eval 期**(compile 读不到 `.workspace`)。

### 5. diff 现状(engine 路径 diff 逐 run → success;studio 字段 diff 整 final_state)
- **engine 路径 diff(live,逐 run)**:predict/backtest 时若 strategy 带 `expected_path`(`GoldenCaseStrategy.expected_path` strategy.py:114 / `BacktestStrategy`:132,来自 golden_case),`runner.py:335-346` 用 `path_diff.py:compute_diff`(:11,LCS / `SequenceMatcher` 比 phase 名序列)算 `missing`/`extra`/`order_mismatch` → `PathDiff`;**`RunResult.success` 由 path_diff 推导**(无 missing/extra/order_mismatch 才 success,`runner.py:348`)。这是 engine 已有的**逐 run 路径级**评估,**非字段级、非逐节点输出 diff**。
- **studio 字段 diff(live,整 final_state)**:`golden_diff.py:compare_run_to_golden`(:68)→ `_diff_value`(:130,递归字段 diff,文本 `SequenceMatcher` 相似度、数值比例、带分)/ `_score`(:201)。**算法现成**,但 ① 在 **studio** 侧 ② 作用于**整 `final_state`**(非逐节点)。mvp1 复用此算法、换喂入粒度为单节点、做成 engine SDK 纯函数(alignment GD3)。

### 6. 409 守卫(studio)+ 空模版骨架(engine,可复用)
- 409 守卫:`diagnostic_export.py:assert_trace_can_be_promoted_to_golden`(:25),predict 来源 trace(`is_predict=True`,`_is_predict_trace`:45)→ 409 `PREDICT_TRACE_CANNOT_BE_GOLDEN`(:36)——防 predict mock 产物被固化成 golden。
- 空 golden 模版骨架:`stub.py:generate_heuristic_stub`(:12)+ `_value_for_schema`(:30)/ `_object_value_for_schema`(:76)按 schema 遍历生成占位——alignment G4 空 golden 模版复用此骨架。

## API
- golden 回放入口:`resolve_generation`(`runner.py:84`,经 gateway `PredictGatewayChatModel._generate` 调用)。
- golden 加载:`MockStrategy.from_param`(`Path` → `_load_golden_case`)。
- 路径评估(engine 现有,逐 run):`runner.py` path diff(:335)→ `RunResult.success`。
- (逐节点**字段** diff 的 engine SDK 纯函数 `evaluate_golden_baseline` 待实现——alignment §3。)

## Data Model / State
- `GoldenCase`(`models.py:12`):`inputs` + `metadata`(phase_name / prompt_hash / io_outputs_schema_hash)+ `expected_traces`(逐节点)。
- golden 内容 schema(目标,临时产物):`expected_output` / `source`(manual|copilot)/ `updated_at`——见 alignment §3;**现状无此常驻文件**。
- studio 快照 golden:`_golden_root_for(skill_id)/run_id`(整次)。

## 当前边界(这个模块现在不是什么)
- **非"逐节点常驻 golden 文件"**:golden 来源现状 = caller 传 `Path` / studio run 快照,**不是**作者预定义、留 `.workspace/golden` 的常驻文件(那是 alignment 目标)。
- **逐节点字段 diff 未实现**:engine 现有的是**逐 run 路径 diff**(→ success);**字段级** diff 在 studio、作用于整 `final_state`;两者都不是"逐节点输出字段 diff"。
- **拦截非在 engine**:在 gateway;engine skeleton 未接线(且缺 copilot 级)。
- **失效非 eval 期 / 非编译期硬错误**:现状是运行期 prompt+schema 双哈希 warn;编译期硬错误从未落地。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标(alignment,**反转后**) |
|---|---|---|
| golden 来源 | caller 传 `Path`(`mock_llm`)/ studio run 快照 | 作者 / copilot 预定义常驻 |
| golden 落点 | mock 参数 / studio 写 `.workspace/golden/<run_id>`(整次快照) | `.workspace/golden` **逐节点常驻**(反转决策 A;**非** `phases/<id>/golden.json`) |
| 回放 | ✅ 已逐节点(`expected_traces[phase]` P0) | 不变,只换来源(从 `.workspace` 逐节点加载) |
| diff | engine 路径 diff(逐 run→success)+ studio 字段 diff(整 `final_state`) | engine SDK **逐节点字段** diff(算法复用换粒度) |
| 失效 | 运行期 prompt+schema 双哈希 warn(退役标的) | **eval 期** staleness(只看 `io.outputs` 必填字段;**非编译期**) |
| 拦截 | gateway 包 `PredictGatewayChatModel`(engine skeleton 未接线、缺 copilot 回调层) | 搬进 engine(`06-seam/01-models`) |

> **验"是否按 mvp1 改了"**:① golden 从 `.workspace/golden` **逐节点**加载(非 mock 参数 / 非 studio 整次快照);② diff 是 engine SDK **逐节点字段**纯函数(`evaluate_golden_baseline`);③ 失效在 eval 期、只看 `io.outputs` 必填字段(非双哈希 warn、非编译期);④ engine interception 接线且补齐 `copilot_predict` 回调层、去 gateway 依赖;⑤ `_warn_on_stale_golden_hashes_sdk` 退役。

## 读代码主路径提示
回放:`runner.py:resolve_generation`(:84,P0 :94)← gateway `predict_interception.py:_generate`(:34,`resolver.py:119` 接线)。策略选择:`strategy.py:MockStrategy.from_param`(:151)→ `GoldenCaseStrategy`(:103)。engine 路径 diff:`runner.py:335` → `path_diff.py:compute_diff`(:11)→ `RunResult.success`。失效 warn(退役):`runner.py:_warn_on_stale_golden_hashes_sdk`(:127,调用 :246)。studio 字段 diff(待复用):`golden_diff.py:_diff_value`(:130)。engine 拦截 skeleton(G5 标的):`_predict_internal/interception.py:29`。

## 交叉引用(链接, 不复制)
[mvp1-alignment](./mvp1-alignment.md)· `01-contract/01-physical-layout`(`.workspace/golden` 落点,双向)· `01-contract/05-invalidation`(失效轴 / 退役标的,双向)· `06-seam/01-models`(predict mock 拦截搬引擎 G5)· `01-contract/03-compile-rules`(CR3 golden-stale 码归属)· `_migration-src/09-golden-eval`(源;§G1-G5 含反转前旧决策 A,勿当现状)
