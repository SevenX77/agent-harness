---
module: 01-contract/01-physical-layout
doc: mvp1-alignment
status: drafted（♻️ mvp0 FROZEN + mvp1 delta: golden→workspace）
aligns_with: ../../00-architecture-overview.md（§2 契约层 A）
---

# 01-physical-layout — 契约 A · 物理布局(整个磁盘文件结构)

> **Tier**: 契约层 A(声明式) | **Owns**: 磁盘上**所有文件放哪** = skill 源码树 + `.workspace` 运行时树 | **现状**: ♻️ mvp0 FROZEN + mvp1 delta(golden→workspace) | **Related**: `skill-syntax`(文件里写什么)· `compile-rules`(校验)· `06-golden-eval`/workspace · `invalidation`

## 1. 定义
定义磁盘上**文件放在哪**(目录树 + 文件命名 + 文件名→phase 类型推导)——**不管"文件里写什么"**(归 `skill-syntax`)。分两棵树:**skill 源码树**(作者写,进 git)+ **`.workspace` 运行时树**(引擎产出,临时)。

## 2. 两棵树
### 2.1 skill 源码树(♻️ mvp0 `01-physical-layout` FROZEN)
```
<skill_root>/
  GRAPH.md                              # 唯一入口(根 metadata/DAG/io)
  phases/<phase_id>/                    # 命名 ^[a-z][a-z0-9_-]*$ = GRAPH phases[].id
    LOGIC.md | SUBGRAPH.md | SKILL.md   # 三选一,文件名决定 phase 类型(无 mode 字段)
    validator.py                        # validator: true 时
    actions/<action_name>.py            # LOGIC 本地 action(可选)
  references/*.md  examples/*.md  subskills/   # 可选
  # ❌ 无 golden —— golden 不在 skill 源码
```
字段级权威 = mvp0 `01-physical-layout`(FROZEN);本域**只汇总 + 链接,不复制字段表**。

### 2.2 `.workspace` 运行时树(♻️ mvp0 `workspace-spec`)
```
<workspace_dir>/                        # Studio 决定在哪;Engine 只在里面盖固定户型
  runs/<run_id>/  trace.jsonl · result.json · final_state.json · metrics.json · artifacts/
  golden/                               # ✅ golden 临时产物(会失效)
  test_inputs/
```

## 3. 接口契约
- **文件名→类型**:`GRAPH.md`→root、`LOGIC.md`→logic、`SUBGRAPH.md`→subgraph、`SKILL.md`→agent(大小写精确;一目录恰一个节点文件,否则 `[F-v3-graph-phase-mode-ambiguous]`/`[F-v3-graph-phase-node-missing]`)。
- **workspace 入口**:`run_skill`/`predict_skill`/`evaluate_golden_baseline` 必须校验 `workspace_dir: Path`(绝对路径,拒相对/环境变量猜测)。
- **校验规则**(DAG/IO/mention 等)归 `compile-rules`,本域只定布局。

## 4. 设计决策基础(用户原话)
> golden→workspace(2026-06-03 PM):"golden不能写进skill , golden是会失效的临时产物, 他只是辅助优化skill的临时产物,不应该写进skill本体,应该留在.workspace"

> Studio/Engine 分工(mvp0 workspace-spec):"Studio 是土地局(决定地皮在哪),Engine 是施工队(只在传入的 workspace_dir 里盖固定户型)"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| PL1 | skill 源码树 ♻️ mvp0 FROZEN,本域只汇总+链接 | 布局稳定,SSOT 在 mvp0 |
| PL2 | golden 在 `.workspace/golden/`,**不进 skill 源码树** | golden 是会失效临时产物,非 skill 定义(反转决策 A) |
| PL3 | Studio 决定 workspace root,Engine 只认 `workspace_dir` | engine 不知道 studio 存在,可独立测试 |

## 6. 测试关键点
1. 文件名→类型:`SKILL.md`/`LOGIC.md` 各进对应 runtime;多/缺节点文件 FATAL。
2. `workspace_dir` 缺失/相对路径被拒;run/predict 产物都进 `runs/<run_id>/`。
3. golden 在 workspace、不在 skill 源码(grep skill 树无 golden.json)。

## 7. 涉及 region / platform
engine 全权定义两棵树;`.workspace` 户型被 studio/host 消费(`03-api-contract` C 引用产物落点)。

## 8. gaps / 待设计
1. golden 在 workspace 的**绑定键**(phase_id?)+ `06-golden-eval` 怎么按节点找(协同)。
2. mvp0 workspace-spec §3.2 的 `golden/` 子结构在 mvp1 是否调整(`baseline_id` vs `phase_id`)。

## 交叉引用(链接, 不复制)
00-architecture-overview §2 · `skill-syntax` · `compile-rules` · `05-run-inner/06-golden-eval` · mvp0/`01-physical-layout`(FROZEN)· mvp0/`workspace-spec`
