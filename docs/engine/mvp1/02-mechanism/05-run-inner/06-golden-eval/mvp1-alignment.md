---
module: 02-mechanism/05-run-inner/06-golden-eval
doc: mvp1-alignment
status: drafted（机制·运行内层;A 部分:已按 workspace 摘要改写,旧 G1-G5 未实质承载/退役）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 06-golden-eval — 机制 B · golden 评估(运行内层)

> **Tier**: 机制层 B · 运行·内层 | **Owns**: 各 agent 节点**期望输出**(在 `.workspace/golden`)的逐节点 diff/eval | **现状**: ⏳(按反转改写) | **Related**: `physical-layout`(`.workspace` golden 落点,双向)· `invalidation`(失效轴,双向)· `06-seam/01-models`(predict mock 回放)· `compile-rules`(原编译期码改 eval)

## 1. 定义
golden-eval = 拿各 agent 节点的**期望输出**(golden)和实际输出**逐节点 diff/打分**,辅助优化 skill。**golden 是会失效的临时产物,在 `.workspace/golden`,不写进 skill 本体**(反转决策 A)。

## 2. 数据流 / 机制
- golden 存 `.workspace/golden/`(归 `physical-layout`;**不在** skill 源码 `phases/<id>/golden.json`)。
- 回放:从 `.workspace` 按节点加载 golden,喂现有 `resolve_generation` P0(逻辑几乎不动);predict mock 拦截在 `06-seam/01-models`(model 接缝短路)。
- 逐节点 diff:复用 `_diff_value`/`_score`,换喂入粒度为单节点 output vs 单节点 golden(引擎 SDK 纯函数 `evaluate_golden_baseline`)。
- **失效校验在 eval 期**(不是编译期):compile 只读 skill 源码、读不到 `.workspace`,所以 golden 缺 `io.outputs` 必填字段 → **eval 期** staleness 提示(不再是编译期 `[F-v3-golden-stale-fields]`)。变更轴归 `invalidation`(双向)。

## 3. 接口契约
`evaluate_golden_baseline(..., workspace_dir)` 读 `.workspace/golden`(归 `physical-layout`/`03-api-contract`);golden 内容(expected_output/source/updated_at)= 临时产物 schema;Studio 只渲染 diff。

## 4. 设计决策基础(用户原话)
> golden→workspace(2026-06-03 PM,反转决策 A):"golden不能写进skill , golden是会失效的临时产物, 他只是辅助优化skill的临时产物,不应该写进skill本体,应该留在.workspace"

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| GD1 | golden 在 `.workspace/golden`,**不进 skill 源码** | 会失效临时优化产物,非 skill 定义(反转决策 A) |
| GD2 | golden 失效校验**从编译期移到 eval 期** | golden 在 workspace,compile 读不到 → 不是编译期码(见 `compile-rules` CR3 / `invalidation` IV2) |
| GD3 | 逐节点 diff = 引擎 SDK 纯函数,Studio 只渲染 | 复用算法,换喂入粒度 |

## 6. 测试关键点
1. golden 在 `.workspace`、不在 skill 源码(grep skill 树无 golden.json)。
2. 改 prompt 不失效;加 `io.outputs` 必填字段 → 该节点 golden stale(**eval 期**,非编译期)。
3. 逐节点 diff 字段级正确;predict mock 回放与真实运行一致。

## 7. 涉及 region / platform
engine 全权;golden/diff 对齐 studio。

## 8. gaps / 待设计
1. golden 在 `.workspace` 的**绑定键**(phase_id?)+ 加载路径(与 `physical-layout` 协同)。
2. 失效校验从编译期码迁到 **eval 期** staleness 的具体落地(原 `[F-v3-golden-stale-fields]` 归属调整)。
3. 空 golden 模版生成(按节点 io.outputs schema)。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `01-contract/01-physical-layout`(`.workspace` golden,双向)· `01-contract/05-invalidation`(失效轴,双向)· `01-contract/03-compile-rules`(CR3)· `06-seam/01-models`(predict mock)
