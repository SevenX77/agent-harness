---
module: 02_capabilities/predict
doc: mvp1-alignment
status: drafted（后端链路 live；前端入口 + predict-pass = target-design）
binds_baseline: ./baseline.md
units: [predict-execution]
aligns_with: 01_workflows/04_run-and-verify.md（E. predict）
---

# predict — MVP1 Alignment

> **Tier**: capability（compile 后 / run 前的试飞）| **Owns**: `predict-execution`——按节点 i/o 跑图、验 schema/逻辑、确定性跑 logic、agent mock 不烧 token | **现状**: 后端 live、前端入口桩 ⚠️ | **Related**: [baseline](./baseline.md)（双向）· `compile-lint`(gate) · `golden-eval`(mock/guard) · `input`(输入) · `engine`(`predict_skill`)

## 1. 定义
`predict` = 编译后、运行前的"试飞"：按节点 i/o 配置跑图、验 schema 与逻辑、确定性执行 logic 节点、mock agent 节点而不烧真 token。是 Run 的硬前置。

## 2. 数据流 / 机制（设计细节）
1. **触发**：compile-pass 后 Predict 点亮 → 用户在 i/o 面板选已导入输入 → 点 Predict → `onPredict` 调 `postPredictRun` → 后端 `predict_run` → `dispatch_predict_job` → 引擎 `predict_skill`。
2. **校验**：验 input schema → 确定性跑 logic 节点 → 验 output schema 兼容（schema 缺字段 → 编译 / predict 错误）。
3. **agent mock by golden**：agent 节点不调真模型；按节点 **golden 状态**选 mock —— 无 golden → 占位 mock；有 golden → golden case。**golden 非前置**，只换 mock 源（golden 内容归 `golden-eval`）。
4. **predict-pass**：成功 predict 置 `predict-pass`、解锁 Run；失败保持 Run 锁 + 就近报错。
5. **guard**：predict 轨迹（假数据）**不可入 golden**（409）；但 **Run 真实输出可作 golden 默认种子**（见 `golden-eval`）。

## 3. 接口契约
- 入口：`postPredictRun(skillId, inputData)` → `POST /skills/{id}/runs/predict` → `predict_run`。
- 输入：i/o 面板选已导入测试输入（单输入先做，批量低优先归 `run-execution`）。
- 产物：run-like diagnostic（`RunResult`，`source="predict"`）；不入 golden。

## 4. 设计决策基础（PM 原话）
> golden 非前置（`04_run-and-verify:29`）：有 golden 按 golden 输出、无则占位 mock。
> predict 轨迹不可入 golden、run 可（PM 2026-06-04）：guard 只挡 predict、不挡 run。
> i/o 面板先做单输入选择（下拉）；批量低优先、留占位（批量属 `run-execution`）。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| PR1 | predict 是 Run 硬前置（predict-pass 才解锁 Run） | 先证逻辑 / schema 跑通，再烧真 token |
| PR2 | agent mock by golden 状态，golden 非前置 | 试飞不烧 token；golden 只换 mock 源 |
| PR3 | predict 轨迹不入 golden（409），run 输出可作种子 | predict 是假数据；run 是真实，可做 golden 起点 |

## 6. 测试关键点
1. 点 Predict 真发请求、出 diagnostic（非 `console.info`）。
2. 成功 predict 置 predict-pass、解锁 Run；失败 Run 仍锁。
3. agent 节点零真 token；无 golden 出占位、有 golden 出 golden case。
4. predict 轨迹提升 golden 返 409；手动 / copilot 建 golden 仍允许。

## 7. 涉及 region / platform
capability `predict`（owner）；region `input`（输入选择）/ `center-action-bar`（触发）；platform `engine`（`predict_skill`）。consume：`compile-lint`（gate）、`golden-eval`（mock/guard）。

## 8. gaps / 报警
- 🚨 前端 predict 主入口 + predict-pass 置位未实现（`Workspace.tsx:onPredict` 桩，见 baseline 测试锚点）；**接线 / 签名实施归 kiro**。
- F1 输入来源待接 i/o 面板（`io-panel-artifacts-test-inputs`）。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `compile-lint`（`compile-stage-gate`）· `golden-eval`（`golden-per-agent-node`）· `input` region（`io-panel-artifacts-test-inputs`）· `engine`（`predict_skill`）
