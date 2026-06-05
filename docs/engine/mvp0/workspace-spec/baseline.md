# workspace-spec (engine) — Baseline (Round 31)

> **迁移状态**: ✅ 本文件 §1–§5 已迁入 mvp1 [`01-contract/01-physical-layout/mvp1-alignment.md §2.2`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#22-workspace-运行时树) 与 [`baseline.md`](../../mvp1/01-contract/01-physical-layout/baseline.md)。本文件只作 mvp0 留档,不再作 SSOT。
> **Status**: ~~Created by a1 (Codex), 2026-05-30; synced for T3 trace.jsonl cutover, 2026-05-31~~ → 已迁入 mvp1 physical-layout。
> **Scope**: ~~Engine 接收 `workspace_dir: Path` 后，在该目录内创建和读取的固定子结构。~~ → mvp1 落点:physical-layout §2.2。
> **配套**: ~~Studio root 定位见 [studio workspace-file-system](../../studio/system-level/workspace-file-system/baseline.md)。~~ → Engine / Studio 边界已迁入 mvp1 physical-layout §2.2 / baseline「当前边界」。

## ~~1. 范围界定~~

> ✅ 已迁入 mvp1 [`physical-layout §2.2`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#22-workspace-运行时树) 与 [`baseline 当前边界`](../../mvp1/01-contract/01-physical-layout/baseline.md#当前边界这个模块现在不是什么)。

~~Studio 是土地局：它决定地皮在哪，也就是当前 skill 的 workspace root 绝对路径。~~

~~Engine 是施工队：它只在传入的 `workspace_dir: Path` 里盖固定户型，不知道、也不关心这个目录来自 `~/.studio`、导入 skill、临时测试目录还是线上 runner。~~

~~本文件只定义 Engine 子结构。宿主应用负责创建或选择 workspace root，并把它传给 SDK。~~

## ~~2. 核心入口契约~~

> ✅ 已迁入 mvp1 [`physical-layout §2.2.1`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#221-入口契约workspace_dir) 与 [`baseline §3`](../../mvp1/01-contract/01-physical-layout/baseline.md#3-workspace-入口现状workspace_dir)。

~~以下 SDK API 必须强制校验 `workspace_dir`:~~

- ~~`run_skill(..., workspace_dir: Path, ...)`~~
- ~~`predict_skill(..., workspace_dir: Path, ...)`~~
- ~~`evaluate_golden_baseline(..., workspace_dir: Path, ...)`~~

~~约束:~~

- ~~`workspace_dir` 必须是 `Path` 语义的绝对目录位置。~~
- ~~SDK 不从环境变量、Studio 配置或默认用户目录猜 workspace。~~
- ~~SDK 不在 workspace root 之外写 run、predict、golden artifacts。~~
- ~~`run_skill` 缺失 `workspace_dir` 会由 Python keyword-only 签名报错；相对路径会被 SDK 拒绝。~~

~~现状实证:~~

- ~~当前 `run_skill` 已要求 keyword-only `workspace_dir: Path`，并移除 public `trace_dir` 参数。~~
- ~~当前 V0.3 主线用 `workspace_dir / "runs" / run_id` 作为 trace 与 run artifact 输出根，不再从 `inputs["output_dir"] / "traces"` 推导 trace 目录。~~
- ~~当前 `output_dir` 只保留为显式 file output 覆盖项；未显式传入时，path-less `target: file` 输出默认落本次 run 的 `artifacts/`。~~

## ~~3. 引擎子目录写入规范~~

> ✅ 已迁入 mvp1 [`physical-layout §2.2.2–§2.2.4`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#222-runsrun_id) 与 [`baseline §4–§6`](../../mvp1/01-contract/01-physical-layout/baseline.md#4-runsrun_id-写盘现状)。

### ~~3.1 `runs/<run_id>/`~~

> ✅ 已迁入 mvp1 [`physical-layout §2.2.2`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#222-runsrun_id) 与 [`baseline §4`](../../mvp1/01-contract/01-physical-layout/baseline.md#4-runsrun_id-写盘现状)。

~~`runs/<run_id>/` 是 Run 与 Predict 的统一输出地。~~

~~每次 `run_skill` 与 `predict_skill` 都创建:~~

```text
~~<workspace_dir>/runs/<run_id>/~~
```

~~必备文件:~~

| 文件 | 写入方 | 内容 |
|---|---|---|
| ~~`trace.jsonl`~~ | ~~SDK~~ | ~~one JSON `CallbackEvent` per line~~ |
| ~~`result.json`~~ | ~~SDK~~ | ~~serialized `RunResult`~~ |
| ~~`final_state.json`~~ | ~~SDK~~ | ~~final `RunResult.context` snapshot~~ |
| ~~`metrics.json`~~ | ~~SDK~~ | ~~serialized `RunResult.metrics`~~ |
| ~~`artifacts/`~~ | ~~SDK / tool runtime~~ | ~~phase/tool generated sidecars~~ |

~~字段级落点:~~

- ~~`trace.jsonl` 是固定名 typed event stream；T3 已取代旧 `tracing.jsonl` / summary JSON 主线。~~
- ~~`result.json` 是 SDK 返回结果的 JSON 形态，给宿主按 run id 重新读取。~~
- ~~`final_state.json` 是 `RunResult.context` 快照，给 Golden/Compare 等后续流程复用。~~
- ~~`metrics.json` 是 `RunResult.metrics` 快照。~~
- ~~`artifacts/` 承接 phase/tool sidecar；声明 `target: file` 且没有显式 `path` / `output_dir` 时默认写到这里。~~

~~Predict 不再有特殊输出目录。Predict 与真实 Run 同样写入 `<workspace_dir>/runs/<run_id>/`；区别由上层结果语义区分。~~

```text
~~RunResult.source = "predict"~~
~~RunResult.source = "run"~~
```

~~现状实证:~~

- ~~当前 `RunResult` 已有 run 结果核心字段：`packages/graph-agent/src/graph_agent/core/result.py`~~
- ~~当前 private predict model 仍有 `PredictResult`，Studio predict 编排会把结果写入 run-scoped `result.json`。~~
- ~~当前 Studio run dir helper 已指向 `.workspace/runs/<run_id>`。~~ → Studio helper 不迁入 engine physical-layout baseline。
- ~~当前 Studio run worker 会创建 run dir 和 artifacts dir，并调用 SDK 时传入 workspace root。~~ → Studio 编排不迁入 engine physical-layout baseline。

### ~~3.2 `golden/`~~

> ✅ 已迁入 mvp1 [`physical-layout §2.2.3`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#223-golden) 与 [`baseline §6`](../../mvp1/01-contract/01-physical-layout/baseline.md#6-golden--test_inputs-现状)。机制语义见 mvp1 [`06-golden-eval`](../../mvp1/02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment.md)。

~~`golden/` 是 Golden Baseline 数据集根目录。~~

~~目标结构:~~

```text
~~<workspace_dir>/golden/~~
~~  <baseline_id>/~~
~~    baseline.json~~
~~    report.json~~
~~    cases/~~
~~      <case_id>.json~~
```

~~用途:~~

- ~~Studio HTTP golden CRUD 可把一次满意的 `RunResult(source="predict")` 固化为 baseline。~~ → CRUD 属 Studio 编排;Engine 户型只规定 `.workspace/golden/` 结构。
- ~~`evaluate_golden_baseline` 读取 dataset，执行或比较后写报告。~~
- ~~Golden 结构属于 Engine workspace 规范；Studio 负责用户操作和 HTTP 编排。~~

~~现状实证:~~

- ~~当前 Studio `golden_dir_for(skill_dir)` 指向 `.workspace/golden`：`apps/studio/backend/app/services/skills.py:742-743`~~ → Studio helper 不迁入 engine physical-layout baseline。
- ~~当前后端会把 run 的 `final_state.json` copy 到 golden baseline：`apps/studio/backend/app/services/golden_diff.py:34-64`~~ → Studio 旧整次快照实现不作为 engine baseline 证据。
- ~~当前 compare 会从 run final state 与 golden final state 计算 diff：`apps/studio/backend/app/services/golden_diff.py:68-110`~~ → diff 机制归 mvp1 `06-golden-eval`。

### ~~3.3 `test_inputs/`~~

> ✅ 已迁入 mvp1 [`physical-layout §2.2.4`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#224-test_inputs) 与 [`baseline §6`](../../mvp1/01-contract/01-physical-layout/baseline.md#6-golden--test_inputs-现状)。

~~`test_inputs/` 是可复用输入数据集根目录。~~

~~目标结构:~~

```text
~~<workspace_dir>/test_inputs/~~
~~  <input_id>.json~~
~~  index.json~~
```

~~字段:~~

- ~~`<input_id>.json`: 单个可复用输入样本。~~
- ~~`index.json`: 可选 metadata cache，用于 label、更新时间、绑定 baseline 等索引信息。~~

~~`evaluate_golden_baseline` 可以读取这些输入样本；Studio 可以继续提供 Test Inputs CRUD，但不应把 Engine 子结构写在 Studio 文档里作为另一份规范。~~

~~现状实证:~~

- ~~当前 Studio helper `test_inputs_dir_for_skill()` 指向 `.workspace/test_inputs`：`apps/studio/backend/app/services/skills.py:754-755`~~ → Studio helper 不迁入 engine physical-layout baseline。
- ~~当前 test inputs router 从 run manager 取该目录：`apps/studio/backend/app/routers/test_inputs.py:12-24`~~ → HTTP router 属 Studio 编排。
- ~~Round 31 后，字段级结构以本文件为准。~~ → 字段级结构现以 mvp1 physical-layout 为准。

## ~~4. 废除项声明~~

> ✅ 已迁入 mvp1 [`physical-layout §2.2.5`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#225-不变式--废除项) 与 [`baseline 差异表`](../../mvp1/01-contract/01-physical-layout/baseline.md#baseline--alignment-差异测试锚点)。

~~旧 Predict 专用子目录彻底过期失效。~~

~~废除项:~~

- ~~Studio `predict_dir_for()`~~
- ~~API response 里的 `file_paths.predict_dir`~~
- ~~旧 `latest_predict.json`~~
- ~~`STUDIO_GITIGNORE` template 对旧 Predict 子目录的放行项~~

~~不做平滑兼容:~~

- ~~旧 `latest_predict.json` 不迁移。~~
- ~~切轨后重新生成 Predict 结果。~~
- ~~调用方改读 `RunResult(source="predict")` 以及 `<workspace_dir>/runs/<run_id>/` 下的 artifacts。~~

~~现状实证:~~

- ~~`predict_dir_for()` 已从 Studio skill path helpers 中删除。~~ → Studio helper 不迁入 engine baseline。
- ~~API response 的 `file_paths.predict_dir` 已删除。~~ → Studio HTTP 面不迁入 engine baseline。
- ~~Predictor 不再写 `.workspace/predict/latest_predict.json`，改写 `<workspace_dir>/runs/<run_id>/result.json`。~~ → Engine 证据见 mvp1 baseline `runner.py:predict_skill` / `_write_workflow_result_artifacts`。
- ~~`STUDIO_GITIGNORE` template 不再放行旧 Predict 子目录。~~ → Studio gitignore 不迁入 engine baseline。

## ~~5. 不变式~~

> ✅ 已迁入 mvp1 [`physical-layout §2.2.5`](../../mvp1/01-contract/01-physical-layout/mvp1-alignment.md#225-不变式--废除项)。

- ~~Engine 只认传入的 `workspace_dir: Path`。~~
- ~~Engine 不知道 Studio 存在。~~
- ~~`run_skill` / `predict_skill` / `evaluate_golden_baseline` 都必须校验 `workspace_dir`。~~
- ~~Run 与 Predict 的结果和日志统一进入 `<workspace_dir>/runs/<run_id>/`。~~
- ~~Golden 数据集统一进入 `<workspace_dir>/golden/`。~~
- ~~Test input 数据集统一进入 `<workspace_dir>/test_inputs/`。~~
- ~~`run_id` 是 run-scoped artifacts 的唯一索引；Predict 没有 latest 文件。~~
