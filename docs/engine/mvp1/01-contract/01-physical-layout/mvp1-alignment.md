---
module: 01-contract/01-physical-layout
doc: mvp1-alignment
status: audited-ready（mvp1 自写=唯一真理；子图 subgraph/ 默认落点 + golden→workspace；.workspace 户型字段正文已迁入 §2.2）
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 01-physical-layout — 契约 A · 物理布局(整个磁盘文件结构)

> **Tier**: 契约层 A(声明式) | **Owns**: 磁盘上**所有文件放哪** = skill 源码树 + `.workspace` 运行时树 | **现状**: 子图 subgraph/ + golden→workspace + workspace 户型字段已写清 | **Related**: `skill-syntax`(文件里写什么)· `02-mechanism/02-resolver`(子图 path 解析)· `compile-rules`(校验)· `06-golden-eval` · `invalidation`

> **唯一真理在 mvp1**:布局以本文为准;旧 mvp0 文档已弃用、不作 SSOT(唯一真相源)引用,缺的按 §8 🚨 报警补齐。

## 1. 定义
定义磁盘上**文件放在哪**(目录树 + 文件命名 + 文件名→phase 类型推导)——**不管"文件里写什么"**(归 `skill-syntax`)。分两棵树:**skill 源码树**(作者写,进 git)+ **`.workspace` 运行时树**(引擎产出,临时)。

## 2. 两棵树
### 2.1 skill 源码树
```
<skill_root>/
  GRAPH.md                              # 唯一入口(根 metadata/DAG/io)
  phases/<phase_id>/                    # 命名 ^[a-z][a-z0-9_-]*$ = GRAPH phases[].id
    LOGIC.md | SUBGRAPH.md | SKILL.md   # 三选一,文件名决定 phase 类型(无 mode 字段)
    validator.py                        # validator: true 时
    actions/<action_name>.py            # LOGIC 本地 action(可选)
  subgraph/<name>/                      # ✅ 子图默认落点(见 §2.1.1);每个子图是完整 graph skill
  references/*.md  examples/*.md        # 可选(领域资料 / 长示例)
  # ❌ 无 golden —— golden 是 .workspace 临时产物
```

#### 2.1.1 子图默认落点(`subgraph/`)
新建子图默认放在引用方 skill **自己根目录**的 `subgraph/<name>/` 下。每个子图本身是**完整 graph skill**(有自己的 `GRAPH.md` / `phases/`,以及它自己的 `subgraph/`),**递归自包含**——孙图落在 `<skill_root>/subgraph/<name>/subgraph/<name2>/`,层层下去,每个 skill 把自己的子图收在自己根的 `subgraph/`。子图用**绝对 path** 引用(语法见 `skill-syntax` §2.1、解析见 `02-resolver`),所以"默认放这"只是约定;要独立复用时可放工作区任意位置、path 指过去。子图相关目录在 engine **统一叫 `subgraph/`**(不再有 `subskills/` 这种旧概念——代码本就不消费它)。

### 2.2 `.workspace` 运行时树
`.workspace` 运行时树 = Engine SDK 在调用方传入的 `workspace_dir` 里创建 / 读取的固定户型。Studio / host 只决定这块地在哪里;Engine 不从 Studio 配置、环境变量、默认用户目录或 `skill_root` 猜 workspace root,也不在 `workspace_dir` 之外写 run / predict / golden artifacts。

```
<workspace_dir>/                        # Studio 决定在哪;Engine 只在里面盖固定户型
  runs/
    <run_id>/                           # run_skill / predict_skill 的统一 run-scoped 输出地
      trace.jsonl                       # typed CallbackEvent JSONL;一行一个事件
      result.json                       # serialized RunResult
      final_state.json                  # RunResult.context 快照
      metrics.json                      # RunResult.metrics 快照
      artifacts/                        # phase/tool/file-output sidecars
  golden/                               # ✅ golden 临时产物(会失效),不进 skill 源码
    <baseline_id>/
      baseline.json                     # baseline 主记录 / metadata
      report.json                       # evaluate_golden_baseline 评估报告
      cases/
        <case_id>.json                  # 单个 golden case
  test_inputs/
    <input_id>.json                     # 单个可复用输入样本
    index.json                          # 可选索引 / metadata cache
```

#### 2.2.1 入口契约(`workspace_dir`)
- `run_skill(..., *, workspace_dir: Path, ...)`、`predict_skill(..., *, workspace_dir: Path, ...)`、`evaluate_golden_baseline(..., *, workspace_dir: Path, ...)` 都必须把 `workspace_dir` 当作**必填 keyword-only 参数**。
- `workspace_dir` 必须是 `Path` 语义的**绝对路径**;相对路径、`../escape` 这类相对逃逸、依赖环境变量猜测、从 Studio 配置反推 root 都不属于 Engine 契约。
- Engine 可以创建 `workspace_dir/runs/<run_id>/...` 等子目录,但不得把 run / predict / golden artifacts 写到 `workspace_dir` 之外。
- Studio / host 可以创建或选择 workspace root,也可以提供 CRUD UI;这些是宿主编排,不是 physical-layout 的 engine 户型正文。

#### 2.2.2 `runs/<run_id>/`
`runs/<run_id>/` 是 Run 与 Predict 的统一输出地。每次 `run_skill` 与 `predict_skill` 都写同一种 run-scoped 户型:

| 文件 / 目录 | 写入方 | 内容 / 语义 |
|---|---|---|
| `trace.jsonl` | Engine SDK event sink | 固定文件名的 typed event stream;一行一个 JSON `CallbackEvent`,供历史回放 / Studio 事件消费。 |
| `result.json` | Engine SDK | SDK 返回的 `RunResult` JSON 形态;`source` 区分 `"run"` / `"predict"`。 |
| `final_state.json` | Engine SDK | `RunResult.context` 快照;Golden / Compare / 后续流程可以按 run id 复用。 |
| `metrics.json` | Engine SDK | `RunResult.metrics` 快照。 |
| `artifacts/` | Engine SDK / tool runtime | phase/tool sidecar;声明 `target: file` 且没有显式 `path` / `output_dir` 时默认写入这里。 |

Predict **不**有专属输出目录。Predict 与真实 Run 都写 `<workspace_dir>/runs/<run_id>/`;调用方读 `result.json` 或 SDK 返回值里的 `RunResult.source` 区分语义:

```text
RunResult.source = "run"
RunResult.source = "predict"
```

#### 2.2.3 `golden/`
`golden/` 是 Golden Baseline 数据集根目录,属于 `.workspace` 临时产物。它辅助优化 skill,会随 schema / 输出契约变化而 stale,所以**不进入 skill 源码树**。

| 路径 | 内容 / 语义 |
|---|---|
| `golden/<baseline_id>/baseline.json` | 一个 baseline 的主记录 / metadata;标识 baseline、来源、创建时间、绑定信息等。 |
| `golden/<baseline_id>/report.json` | `evaluate_golden_baseline` 对该 baseline 执行 / diff 后写出的评估报告。 |
| `golden/<baseline_id>/cases/<case_id>.json` | 单个 golden case;用于承载输入样本、期望输出 / trace、case metadata 等评估材料。 |

golden 的失效语义归 `05-invalidation`,评估 / diff 机制归 `05-run-inner/06-golden-eval`;本域只规定它在磁盘上落在 `.workspace/golden/`。

#### 2.2.4 `test_inputs/`
`test_inputs/` 是可复用输入数据集根目录,供 run / predict / golden eval 复用输入样本。

| 路径 | 内容 / 语义 |
|---|---|
| `test_inputs/<input_id>.json` | 单个可复用输入样本。 |
| `test_inputs/index.json` | 可选 metadata cache;可记录 label、更新时间、绑定 baseline / case 等索引信息。 |

Studio 可以继续提供 Test Inputs CRUD,但不得把 HTTP 编排 / helper 路径写成另一份 Engine physical-layout SSOT。

#### 2.2.5 不变式 + 废除项
- Engine 只认传入的 `workspace_dir: Path`;Studio 是 root 的提供者,不是 Engine 户型的一部分。
- Run 与 Predict 的结果和日志统一进入 `<workspace_dir>/runs/<run_id>/`。
- Golden 数据集统一进入 `<workspace_dir>/golden/`;Test Inputs 统一进入 `<workspace_dir>/test_inputs/`。
- `run_id` 是 run-scoped artifacts 的唯一索引;Predict 没有 `latest` 文件。
- 旧 Predict 专用目录废除:`predict_dir`、`.workspace/predict/latest_predict.json`、API response 中的 `file_paths.predict_dir`、旧 `.gitignore` 对 `.workspace/predict/` 的放行项都不再是 Engine 契约。

## 3. 接口契约
- **文件名→类型**:`GRAPH.md`→root、`LOGIC.md`→logic、`SUBGRAPH.md`→subgraph、`SKILL.md`→agent(大小写精确;一目录恰一个节点文件,否则 `[F-v3-graph-phase-mode-ambiguous]` / `[F-v3-graph-phase-node-missing]`)。
- **子图落点**:`<skill_root>/subgraph/<name>/`(默认),子图节点 `SUBGRAPH.md` 用绝对 `path` 指向它(解析归 `02-resolver`)。
- **workspace 入口**:`run_skill` / `predict_skill` / `evaluate_golden_baseline` 必须校验 `workspace_dir: Path`(绝对路径,拒相对 / 环境变量猜测)。
- **校验规则**(DAG/IO/mention 等)归 `compile-rules`,本域只定布局。

## 4. 设计决策基础(用户原话)
> 子图默认落点(PM 2026-06-05 拍):子图默认放父 skill 自己根的 `subgraph/`(用户选"父 skill 自己的根")、递归自包含(用户确认),避免多层嵌套难找;path 写绝对路径("随便放哪里")。
> golden→workspace(2026-06-03 PM):"golden不能写进skill , golden是会失效的临时产物, 他只是辅助优化skill的临时产物,不应该写进skill本体,应该留在.workspace"
> Studio/Engine 分工:"Studio 是土地局(决定地皮在哪),Engine 是施工队(只在传入的 workspace_dir 里盖固定户型)"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| PL1 | skill 源码树由 mvp1 自写为唯一真理(不引用 mvp0) | mvp0 弃用,真理只在 mvp1 |
| PL2 | golden 在 `.workspace/golden/`,**不进 skill 源码树** | golden 是会失效临时产物,非 skill 定义 |
| PL3 | Studio 决定 workspace root,Engine 只认 `workspace_dir` | engine 不知道 studio 存在,可独立测试 |
| PL4 | 子图默认落 `<skill_root>/subgraph/<name>/`、递归自包含;**绝对 path** 引用、无 registry | 子图集中在每个 skill 自己根下、好找;path 即物理地址(PM 2026-06-02 / 06-05) |

## 6. 测试关键点
1. 文件名→类型:`SKILL.md` / `LOGIC.md` / `SUBGRAPH.md` 各进对应 runtime;多 / 缺节点文件 FATAL。
2. `workspace_dir` 缺失 / 相对路径被拒;run/predict 产物都进 `runs/<run_id>/`。
3. golden 在 workspace、不在 skill 源码(grep skill 树无 golden.json)。
4. **子图**:新建子图默认落 `<skill_root>/subgraph/<name>/`、是完整 graph skill;孙图递归在 `<name>/subgraph/<name2>/`。

## 7. 涉及 region / platform
engine 全权定义两棵树;`.workspace` 户型被 studio/host 消费(`03-api-contract` C 引用产物落点)。

## 8. gaps / 待设计 + 报警
1. ⚠️ **实现 drift**:`evaluate_golden_baseline` 作为目标入口尚未在 engine public API 落地;`.workspace/golden/` / `test_inputs/` 的 CRUD 现主要由 Studio 编排。Engine SDK 实现需按 §2.2 户型补齐。
2. golden 绑定键 = `phase_id`(已定);`golden/<baseline_id>/cases/<case_id>.json` 内部 schema 与逐节点 stale 报告字段仍需与 `06-golden-eval` 协同落地。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `skill-syntax`(子图 path 语法)· `02-mechanism/02-resolver`(子图 path 解析)· `compile-rules` · `05-run-inner/06-golden-eval`
