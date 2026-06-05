---
module: 01-contract/01-physical-layout
doc: mvp1-alignment
status: drafted（mvp1 自写=唯一真理；子图 subgraph/ 默认落点 + golden→workspace；🚨 workspace 户型字段正文待从旧文档迁入,见 §8）
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 01-physical-layout — 契约 A · 物理布局(整个磁盘文件结构)

> **Tier**: 契约层 A(声明式) | **Owns**: 磁盘上**所有文件放哪** = skill 源码树 + `.workspace` 运行时树 | **现状**: 子图 subgraph/ + golden→workspace 已写清;🚨 workspace 户型字段待补(§8) | **Related**: `skill-syntax`(文件里写什么)· `02-mechanism/02-resolver`(子图 path 解析)· `compile-rules`(校验)· `06-golden-eval` · `invalidation`

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
```
<workspace_dir>/                        # Studio 决定在哪;Engine 只在里面盖固定户型
  runs/<run_id>/  trace.jsonl · result.json · final_state.json · metrics.json · artifacts/
  golden/                               # ✅ golden 临时产物(会失效)
  test_inputs/
```
> 🚨 这棵树的**字段级户型正文**(各文件含义、`golden/` 子结构)还没自写进 mvp1,见 §8。

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
1. 🚨 **workspace 户型字段正文待迁入 mvp1**:§2.2 各文件(trace.jsonl / result.json / …)的字段级含义、`golden/` 子结构正文目前仍散在旧文档、未自写进 mvp1——去-mvp0 债,必须补齐(否则 mvp0 弃用后真空)。
2. golden 绑定键 = `phase_id`(已定);其在 `.workspace/golden/` 下的确切文件名布局待 PM 最终敲定(与 `06-golden-eval` 协同)。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `skill-syntax`(子图 path 语法)· `02-mechanism/02-resolver`(子图 path 解析)· `compile-rules` · `05-run-inner/06-golden-eval`
