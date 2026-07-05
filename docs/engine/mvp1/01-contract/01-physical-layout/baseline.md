---
module: 01-contract/01-physical-layout
doc: baseline
status: audited-ready（现状对齐 WS-E7:skill 树按 loader 校验；run/predict 写 runs/<run_id>；evaluate_golden_baseline 读写 workspace_dir/golden；import_files engine SDK CRUD 尚未落地）
binds_alignment: ./mvp1-alignment.md
binds_code: packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill · packages/graph-agent/src/graph_agent/core/loader.py:_PHASE_FILE_TO_MODE · packages/graph-agent/src/graph_agent/core/runner.py:run_skill · packages/graph-agent/src/graph_agent/core/runner.py:predict_skill · packages/graph-agent/src/graph_agent/core/runner.py:_validate_workspace_dir · packages/graph-agent/src/graph_agent/core/runner.py:_write_workflow_result_artifacts · packages/graph-agent/src/graph_agent/callbacks/emit.py:_TraceJsonlSink · packages/graph-agent/src/graph_agent/core/result.py:RunResult
---

# 01-physical-layout — Baseline(当下代码实现逻辑)

> **Scope**: 磁盘文件结构的**现状代码**:skill 源码树校验(loader 从根向下)+ Engine SDK 在 `workspace_dir` 下写出的 run-scoped 产物。Studio root 选择、HTTP CRUD、helper/router 不作为本 baseline 代码证据。
> **现状一句话**:skill 源码树由 loader 校验(`loader.py:SkillLoader.compile_skill` / `_guard_v030_root` / `_PHASE_FILE_TO_MODE`)。workspace 侧,`run_skill` / `predict_skill` / `evaluate_golden_baseline` 都要求 keyword-only `workspace_dir` 并经 `_validate_workspace_dir` 拒绝相对路径;run / predict 产物写入 `<workspace_dir>/runs/<run_id>/`,其中 `trace.jsonl` 由 event sink 创建,`result.json` / `final_state.json` / `metrics.json` 由 `_write_workflow_result_artifacts` 固定写出。WS-E7 后,`evaluate_golden_baseline` 读 `<workspace_dir>/golden/<baseline_id>/{baseline.json,cases/*.json}` 并写 `report.json`;`.workspace/import_files/` 的 Engine SDK CRUD 仍未落地。

## UI/UX
N/A。

## 前端逻辑
N/A —— 本模块是 Engine 物理布局契约;Studio 文件树消费不作为本 baseline 代码证据。

## 后端功能

### 1. skill 源码树校验现状(loader 从根向下)
- root 入口 `GRAPH.md`:`packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill` 从 skill root 读取根图;`packages/graph-agent/src/graph_agent/core/loader.py:_guard_v030_root` 拒绝非 V0.3 skill root。
- phase 节点:`phases/<id>/` 下 `LOGIC.md`/`SUBGRAPH.md`/`SKILL.md` 三选一;文件名→类型表在 `packages/graph-agent/src/graph_agent/core/loader.py:_PHASE_FILE_TO_MODE`;缺/多报 `[F-v3-graph-phase-node-missing]`/`[F-v3-graph-phase-mode-ambiguous]`。
- 配套目录:references/、examples/(可选)。**代码现状无 `subskills/` 目录**(`grep subskills` 在 `src/` 下为空——`subskills` 仅是 mvp0 spec 遗留概念,代码不消费;engine 统一用 `subgraph/`)。

### 2. 子图物理现状(无 subgraph/ 约定)
- **现状无 `subgraph/` 目录约定**:子图不靠物理位置,靠 `target_skill`(逻辑 id,`packages/graph-agent/src/graph_agent/core/manifest.py:SubgraphNodeAST`)经 resolver 找 root——物理位置由 resolver/registry 决定、**不在 skill 源码树布局里**。
- mvp1 反转:子图默认落 `<skill_root>/subgraph/<name>/`、绝对 path、递归自包含。

### 3. workspace 入口现状(`workspace_dir`)
- `packages/graph-agent/src/graph_agent/core/runner.py:run_skill` 的签名要求 `workspace_dir: Path` 为 keyword-only 必填参数;缺失时 Python 签名直接报 `TypeError`。
- `packages/graph-agent/src/graph_agent/core/runner.py:predict_skill` 同样要求 `workspace_dir: Path`,并在进入执行前调用 `_validate_workspace_dir`。
- `packages/graph-agent/src/graph_agent/core/runner.py:_validate_workspace_dir` 只做绝对路径校验:相对路径触发 `ValueError("workspace_dir must be an absolute path")`;当前代码不从环境变量 / Studio 配置 / 默认用户目录猜 workspace root。
- `packages/graph-agent/src/graph_agent/core/runner.py:evaluate_golden_baseline` 已在 `graph_agent.__all__` 导出,并复用 `_validate_workspace_dir`。它把 `workspace_dir` 视为 Engine 可见的 workspace root;Studio 场景中的 `.workspace/golden` 对应 Engine 入参 `<workspace_dir>/golden`。

### 4. `runs/<run_id>/` 写盘现状
- `packages/graph-agent/src/graph_agent/core/runner.py:_run_v030_skill_dict` 计算 `trace_output = workspace_dir / "runs" / run_id`,真实 run 的 trace / file-output 默认目录都挂在这里。
- `packages/graph-agent/src/graph_agent/core/runner.py:predict_skill` 计算同样的 `trace_output = workspace_root / "runs" / run_id`;Predict 不写 `.workspace/predict/` 专用目录。
- `packages/graph-agent/src/graph_agent/callbacks/emit.py:_TraceJsonlSink` 在初始化时创建 run dir,并创建 / 清空固定文件 `trace.jsonl`;后续每个事件追加一行 JSON。
- `packages/graph-agent/src/graph_agent/core/runner.py:_write_workflow_result_artifacts` 固定写三份 JSON:`result.json` = `RunResult.model_dump(mode="json")`;`final_state.json` = `RunResult.context`;`metrics.json` = `RunResult.metrics.model_dump(mode="json")`。
- `packages/graph-agent/src/graph_agent/core/runner.py:_save_v030_declared_file_outputs` 对 `target: file` 且未显式 `output_dir` 的输出使用 `default_output_dir=trace_output / "artifacts"`。

### 5. RunResult / Predict 语义现状
- `packages/graph-agent/src/graph_agent/core/result.py:RunResult` 是 run / predict 的统一返回模型,核心字段包括 `success`、`run_id`、`skill_id`、`context`、`metrics`、`trace_path`、`error`、`source`、`phases`、`path_diff`。
- `packages/graph-agent/src/graph_agent/core/result.py:RunResult.source` 取值为 `"run"` / `"predict"`;`predict_skill` 构造结果时显式写 `source="predict"`,真实 run 使用默认 `"run"`。
- `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py:PredictResult` 仍是 private predict 内部模型;不是 `.workspace` 物理布局的输出户型。

### 6. golden / import_files 现状
- `evaluate_golden_baseline` 读取 `<workspace_dir>/golden/<baseline_id>/baseline.json` 与 `cases/<case_id>.json`,并写回 `<workspace_dir>/golden/<baseline_id>/report.json`。
- `.workspace/import_files/` 是 target physical-layout 户型;Engine SDK CRUD 还未落地。现有 Test Inputs 与导入文件 CRUD/helper 主要在 Studio 后端,不挂为本 baseline 的 engine code evidence。

## API
- skill 物理校验入口:`packages/graph-agent/src/graph_agent/core/loader.py:SkillLoader.compile_skill`。
- workspace 写盘入口:`packages/graph-agent/src/graph_agent/core/runner.py:run_skill`、`packages/graph-agent/src/graph_agent/core/runner.py:predict_skill`。

## Data Model / State
- skill 源码树 → loader 校验 → AST。
- run 结果 → `packages/graph-agent/src/graph_agent/core/result.py:RunResult` → `result.json` / `final_state.json` / `metrics.json`。

## 当前边界(这个模块现在不是什么)
- 现状**无 subgraph/ 约定目录**——子图物理位置不在 skill 布局里(靠 target_skill + resolver)。
- Studio 决定 workspace root 放哪;Engine baseline 不挂 Studio helper / router / HTTP CRUD 作为物理布局真相。
- `.workspace/golden/` 的 Engine eval 读写已由 `evaluate_golden_baseline` 落地;`.workspace/import_files/` dataset CRUD 仍未作为 Engine SDK 落地。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标 |
|---|---|---|
| 子图落点 | 无约定目录;靠 target_skill 逻辑 id + resolver | `<skill_root>/subgraph/<name>/` 默认 + 绝对 path + 递归自包含 |
| workspace 入口 | `run_skill` / `predict_skill` / `evaluate_golden_baseline` 均校验绝对 `workspace_dir` | 三个入口都要求绝对 `workspace_dir` |
| run / predict 输出 | 两者都写 `<workspace_dir>/runs/<run_id>/`;Predict 用 `RunResult.source="predict"` 区分 | 保持统一 `runs/<run_id>/`,废除 predict 专用目录 |
| `trace.jsonl` | `_TraceJsonlSink` 固定写 run dir 下 `trace.jsonl` | 一行一个 typed `CallbackEvent` |
| `result/final_state/metrics` | `_write_workflow_result_artifacts` 固定写三份 JSON | 与 alignment §2.2 文件语义一致 |
| `artifacts/` | path-less `target: file` 默认写 `runs/<run_id>/artifacts/` | 保持为 phase/tool sidecar 目录 |
| `golden/` | Engine `evaluate_golden_baseline` 读 baseline/cases 并写 report;Studio CRUD 仍是消费者/host 侧 | `<workspace_dir>/golden/<baseline_id>/{baseline.json,report.json,cases/<case_id>.json}` |
| `import_files/` | Engine SDK 未落地;现有 CRUD 主要在 Studio | `<workspace_dir>/import_files/{<input_id>.json,<input_import_name>/...,<node_id>/<node_import_name>/...}` |
| 废除项 | SDK Predict 不写 `.workspace/predict/latest_predict.json`;Studio 侧废除项不挂为 engine 证据 | predict_dir / latest_predict / file_paths.predict_dir 全废 |

> **验"是否按 mvp1 改了"**:① 新建子图默认落 `<skill_root>/subgraph/<name>/`、是完整 graph skill;② 孙图递归在 `<name>/subgraph/<name2>/`;③ 子图位置由物理 path 定;④ `evaluate_golden_baseline` 进入 public API 并校验绝对 `workspace_dir`;⑤ golden Engine eval 读写按 alignment §2.2 户型落地;⑥ Predict 不产生 `.workspace/predict/latest_predict.json`。`import_files` Engine CRUD 仍是后续 backlog。

## 读代码主路径提示
skill 树: `loader.py:SkillLoader.compile_skill` → `_guard_v030_root` → `_PHASE_FILE_TO_MODE` → resolver(归 `02-resolver`)。
workspace: `runner.py:run_skill` / `predict_skill` → `_validate_workspace_dir` → `_run_v030_skill_dict` / predict run loop → `_TraceJsonlSink` → `_write_workflow_result_artifacts` → `RunResult`。

## 交叉引用(链接, 不复制)
[mvp1-alignment](./mvp1-alignment.md)(目标)· `02-skill-syntax`(子图 path 语法)· `02-mechanism/02-resolver`(子图解析)· `05-run-inner/06-golden-eval`(workspace golden / eval drift)· `03-api-contract`(run/predict 操作面)
