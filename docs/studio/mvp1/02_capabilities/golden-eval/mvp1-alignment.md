---
module: 02_capabilities/golden-eval
doc: mvp1-alignment
status: FROZEN（2026-07 对账:后端 golden 已落 per-agent-node cases（set_golden_baseline_for_run(node_id) + cases/{id}.json,golden_diff.py:58-79 / 186-208），旧"整次 run final_state 复制"已废；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [golden-per-agent-node]
aligns_with: 01_workflows/04_run-and-verify.md（golden-eval 段）
---

# golden-eval — MVP1 Alignment

> **Tier**: capability | **Owns**: `golden-per-agent-node`（Studio golden 编辑 / diff owner；落点/eval 引 engine） | **现状**: 2026-07 对账:后端 golden 已按 per-agent-node 管理(set_golden_baseline_for_run(node_id) 写 cases/{id}.json,golden_diff.py);旧整次 run final_state 复制已废;手动空模板链 + Properties per-node promote 已删(PM 2026-07-15,见 F3)。 | **Related**: [baseline](./baseline.md)（双向）· `predict` · `run-execution` · `input` · `assets` · `editor` · `copilot-assist` · `engine`

## 1. 定义
`golden-eval` owns per-agent-node expected outputs: node golden state, predict mock selection, golden creation（editor diff promote / copilot auto-write / trace per-node & run promote）, output-schema invalidation, and run-after actual-vs-golden diff.

Source workflow basis: `01_workflows/04_run-and-verify.md:118`, `01_workflows/04_run-and-verify.md:131`, `01_workflows/04_run-and-verify.md:135`.

## 2. 数据流 / 机制（设计细节）
### F1. Agent Node Golden State

- 机制: agent nodes move from untested to logic-ok to has-golden.
- 决策: golden is only for agent nodes; logic nodes already run deterministically in predict.
- 原话/来源: `01_workflows/04_run-and-verify.md:122` lists the three-state machine; `01_workflows/04_run-and-verify.md:133` says logic nodes do not participate.
- 测试: first successful predict marks no-golden agent as logic-ok; adding valid golden marks has-golden; logic nodes show no golden label.
- Status: target-design.
- 归属: capability `golden-eval`; regions `canvas`, `input`.

### F2. Automatic Mock Selection

- 机制: predict chooses placeholder mock when no golden exists and golden replay when golden exists.
- 决策: no manual mock selector.
- 原话/来源: `01_workflows/04_run-and-verify.md:123` defines mock by state; `01_workflows/04_run-and-verify.md:133` records g-b.
- 测试: no-golden predict emits schema-shaped placeholder; has-golden predict emits golden case; no real provider call occurs.
- Status: target-design/backend partial.
- 归属: capability `predict`; capability `golden-eval`; platform `engine`.

### F3. Create Golden Manually Or With Copilot

- 机制: per-node trace 按钮开单个 copilot chat;**批量入口 = Copilot 输入框上方分析 bar**(predict/run 后弹窗,自动写无 golden 节点)——旧 sonner 批量已细化为分析 bar,见 `copilot-assist` F7;editor diff `DiffView` Promote 与 TracePanel run/per-node promote 提供从真实输出创建 golden 的入口。
- 决策: contextual trace 按钮 + Copilot 分析 bar(batch);**旧 sonner 批量入口已被分析 bar 取代**。**PM 2026-07-15 裁决:i/o 空 JSON 模板手填链(create-path B:`GET /golden/template` + `POST /golden/manual/plan` + 前端 fetchGoldenTemplate/saveManualGolden)整链删除**——从未有 UI caller,manual golden 的价值场景已被 run-seed(F6)+ copilot 覆盖;golden 手填/编辑入口归 I/O 数据流设计方向(golden json 同构实例,2026-07-02 锁定、已搁置),`GET /golden/{id}/content` read path 保留为该方向脚手架。
- 原话/来源: `01_workflows/04_run-and-verify.md:124` and `01_workflows/04_run-and-verify.md:125` list the two creation paths; `01_workflows/04_run-and-verify.md:137` records "两者都要";手动模板链删除 = PM 2026-07-15 裁决("golden①② 删代码")。
- 测试: trace button opens one chat for one node; batch entry opens chats for all missing-golden agent nodes; 已删的 `GET /golden/template` 与 `POST /golden/manual/plan` 保持 404/405(tests/routers/test_golden_dead_entry_removal.py)。
- Status: live(editor diff `DiffView` "Promote to Golden"(Workspace.tsx→handlePromoteToGolden)+ Copilot analysis bar auto-write(`AnalysisBar`→`autoWriteGoldenIfAbsent`)+ TracePanel run/per-node promote 均接 `saveGoldenBaseline`;手动模板链已删)。
- 归属: capability `golden-eval`; capability `copilot-assist`; regions `input`, `timeline`, `copilot`.

### F4. Output Schema Invalidation

- 机制: changing output schema so a golden lacks required fields raises warning and compile error until fixed.
- 决策: prompt/internal agent changes do not invalidate golden; output shape changes do.
- 原话/来源: `01_workflows/04_run-and-verify.md:127` defines the invalidation trigger; `01_workflows/04_run-and-verify.md:137` keeps the PM wording.
- 测试: prompt edit keeps golden valid; adding required output field blocks compile/predict until golden contains it.
- Status: target-design.
- 归属: capability `golden-eval`; capability `compile-lint`; platform `engine`.

### F5. Run-after Field Diff

- 机制: after real run, compare actual agent output to per-node golden at field level.
- 决策: golden is for acceptance quality after Run, not a prerequisite for Run.
- 原话/来源: `01_workflows/04_run-and-verify.md:128` lists field diff; `01_workflows/04_run-and-verify.md:136` records run-after diff.
- 测试: changed/missing/extra fields show scores and values; route mismatch between frontend and backend is fixed.
- Status: 后端 per-node golden 已落(golden_diff.py:58-79 / 186-208)+ compare 端点 live(runs.py:42-65);前端 useGoldenDiff 已挂载(Workspace.tsx:701,非 orphan);字段级 diff 编辑器渲染完善度以代码逐项核。(2026-07 对账)
- 归属: capability `golden-eval`; regions `editor`(详细 diff), `input`(入口); platform `engine`。**不在 `properties`**(PM 2026-06-04:golden 完全不在 Properties)。

### F6. Predict 不可入 golden,但 Run 输出可做默认种子

- 机制: **golden 本身随时可写**(从 schema 模板 / copilot 设计 / 手填,**predict 之前也行**)。guard 很窄——**只挡"把 predict 的 mock 输出值直接提升成 golden"**(假数据无参考价值,409),**不限制 golden 的创建时机**。**Run 的真实输出可作 golden 默认种子**:agent 节点**无 golden / 空模板 / 坏文件(schema 完全不符)**时,默认用该节点 Run 输出填充、在其上编辑;**已有有效 golden 不被 Run 自动覆盖**。
- 决策: 区分 predict 与 run——predict=假数据不可入 golden;run=真实输出可做起点。UX 心智:用户先 Run、觉得某节点结果"还行"就跳过,挑不行的去做 golden,所以拿 run 输出当默认基底最省力(PM 2026-06-04)。
- 原话/来源: `01_workflows/04_run-and-verify.md:129`(predict 409 guard);run 输出 seed golden = PM 2026-06-04 UX 心智澄清。
- 测试: predict 提升返回 409;无/空/坏 golden 节点 Run 后 golden 默认以 run 输出填充且可编辑;有效 golden 不被自动覆盖。
- Status: predict-guard backend live;run-seed-golden target-design。
- 归属: capability `golden-eval`; capability `run-execution`; platform `engine`。

## 3. 接口契约
- Golden unit: one agent node's expected output, not a whole-run captured snapshot.
- Storage/UI target: golden settings and JSON files live with i/o output configuration.
- Predict: agent nodes mock from placeholder or golden automatically.
- Run: actual output compares against golden after real execution.
- Region links: `input`, `timeline`, `canvas`, `copilot`.（golden **不在** `properties`，见 F5）
- Platform links: `engine`, `native-fs`, `gateway` through copilot design.

## 4. 设计决策基础（PM 原话）
- **golden 物理布局 = `.workspace/golden/`,不写进 skill 源码树**(PM 2026-06-03 反转旧决策 A:golden 是会失效的临时优化产物、非 skill 定义)。绑定键 = phase_id(随 engine `01-physical-layout` 收口);失效校验从编译期移到 eval 期。详见 `docs/engine/mvp1/01-contract/01-physical-layout`。
- **Copilot 设计 golden 的 prompt(描述驱动)**:先读 `GRAPH.md` 每个节点的 `description`(懂每个节点在整个 workflow 里的作用)+ 读 `SKILL.md`(懂这节点具体要干嘛、user 怎么设计的)→ 综合分析后产出。**严禁把 input/output schema 当黄金标准**(user 的输入输出标准本身可能有问题);但提示词须提示:**要改 schema 须谨慎、贯穿上下文看**。停止条件 = 产出可用 golden 且用户接受。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| GOLDEN_EVAL-1 | 粒度 | 单元 `golden-per-agent-node`；**为什么**：golden = 单个 agent 节点的期望输出，非整次 run 快照 |
| GOLDEN_EVAL-2 | 入口 | 单元 `golden-per-agent-node`；**为什么**：golden 设置/文件归 I/O output 区、详细 diff 在编辑器分屏，不在 Properties |
| GOLDEN_EVAL-3 | predict guard | 单元 `golden-per-agent-node`；**为什么**：predict 假数据不可提升成 golden(409)，run 真实输出可做默认种子 |

## 6. 测试关键点
1. 粒度: `set_golden_baseline_for_run` 已按 agent node 管 golden case(node_id 参数 + cases/{id}.json,golden_diff.py:58-79 / 186-208);旧"复制整次 final_state"已废。(2026-07 对账)
2. 入口: sonner 批量已删;editor diff(DiffView Promote)+ Copilot analysis bar(auto-write)+ TracePanel run/per-node promote 已 live;手动模板链(fetchGoldenTemplate/saveManualGolden + template/manual-plan 端点)与 Properties per-node promote(NodeGoldenSection)已按 PM 2026-07-15 裁决删除,removal lock 测试守住(PropertiesPanel.golden-lock.test.tsx / test_golden_dead_entry_removal.py)。
3. predict guard: baseline 现状为 predict trace promotion 被 409 挡；目标为 predict 不可入 golden；run 输出可做默认种子。

## 7. 涉及 region / platform
`predict` · `run-execution` · `input` · `assets` · `editor` · `copilot-assist` · `engine`

## 8. gaps / 报警
- ✅ 粒度(2026-07 对账清除旧报警): `set_golden_baseline_for_run` 已按 agent node 管 golden case/output(node_id + cases/{id}.json,golden_diff.py:58-79 / 186-208);旧"复制整次 final_state"报警清除。
- ✅ 入口(2026-07-15 清账): editor diff(`DiffView` "Promote to Golden")+ Copilot analysis bar(auto-write)+ TracePanel run/per-node promote 已 live 接 `saveGoldenBaseline`;sonner 批量入口已删;旧 drift 两项——I/O output 手动模板链(无 UI caller)与 Properties per-node promote(`NodeGoldenSection`,违反 F5)——已按 PM 2026-07-15 裁决整链删除并加 removal lock 测试。golden 手填/编辑入口留给 I/O 数据流方向(已搁置),`GET /golden/{id}/content` read path 保留为脚手架。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `predict` · `run-execution` · `input` · `assets` · `editor` · `copilot-assist` · `engine`
