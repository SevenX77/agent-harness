---
module: 03_regions/local-history
doc: mvp1-alignment
status: drafted（HistoryPanel 只显示 git snapshot；RunDetailDrawer/BatchSummary 存在但未挂，这与最新归属一致但旧 alignment 曾留未决口径 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [local-history-snapshot]
aligns_with: 01_workflows/06_eval.md（autocommit/快照）· 01_workflows/04_run-and-verify.md（run detail 归属）
---

# local-history — MVP1 Alignment

> **Tier**: region | **Owns**: `local-history-snapshot`（快照列表/显示 owner） | **现状**: HistoryPanel 只显示 git snapshot；RunDetailDrawer/BatchSummary 存在但未挂，这与最新归属一致但旧 alignment 曾留未决口径 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `publish` · `native-fs` · `timeline`

## 1. 定义
`local-history` owns local workspace snapshots: successful-run autocommit visibility, manual/auto snapshot list, selecting a snapshot, and revert.

Source workflow basis: `01_workflows/06_eval.md:13`, `01_workflows/06_eval.md:24`, `01_workflows/04_run-and-verify.md:59`.

## 2. 数据流 / 机制（设计细节）
### F1. Snapshot List

- 机制: show local git snapshots with short sha, kind, author, timestamp, and message.
- 决策: local save is the MVP safety net.
- 原话/来源: `01_workflows/06_eval.md:16` marks autocommit live; `01_workflows/06_eval.md:27` keeps local autocommit.
- 测试: successful run creates an auto_run snapshot; manual snapshots show distinct kind.
- Status: live.
- 归属: region `local-history`; capability `publish`.

### F2. Revert Snapshot

- 机制: user selects a snapshot and reverts the skill to that sha.
- 决策: recovery should be local and explicit.
- 原话/来源: `01_workflows/06_eval.md:36` includes successful-run autocommit as a key test; revert is the recovery pair.
- 测试: disabled without selection; revert updates workspace files and refreshes skill detail.
- Status: live.
- 归属: region `local-history`; platform `native-fs`.

### F3. Run Detail Ownership Check

- 机制: RunDetailDrawer/BatchSummary 接在 run review 处(Timeline / i-o),**不归 Local History**(已决 PM 2026-06-04)。
- 决策: run detail is time/run semantics, not git snapshot semantics.
- 原话/来源: `01_workflows/04_run-and-verify.md:58` lists run detail under run history; `01_workflows/04_run-and-verify.md:54` lists batch under i/o/run.
- 测试: run row opens RunDetailDrawer from Timeline; batch progress opens from i/o panel.
- Status: 已决(见下「已决」)。
- 归属: Local History 只做 git snapshot;RunDetailDrawer / BatchSummary 归 `timeline` / `input`(已决 PM 2026-06-04)。

## 3. 接口契约
- Inputs: local git history items, current skill id, selected sha.
- Outputs: refresh, select snapshot, revert request.
- Capability links: `publish`, `run-execution`, `skill-workspace`.
- Platform link: `native-fs`.

## 4. 设计决策基础（PM 原话）
- Local History **只做 git 快照**;RunDetailDrawer / BatchSummary 属"运行/时间"语义、归 Timeline,不吸收进来。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| LOCAL_HISTORY-1 | scope | 单元 `local-history-snapshot`；**为什么**：Local History 只做 git snapshot 显示，RunDetail/BatchSummary 不归它(归 timeline/input) |
| LOCAL_HISTORY-2 | snapshot | 单元 `local-history-snapshot`；**为什么**：成功 run 自动 commit 快照 + 手动快照列表，可选中 revert |
| LOCAL_HISTORY-3 | 写机制 | 单元 `publish-artifact-autocommit`/`native-rust-writer`（引，非本单元；owner=publish-artifact-autocommit/native-fs）；**为什么**：快照写盘机制归发布/Rust 写者，Local History 只显示 |

## 6. 测试关键点
1. scope: baseline 现状为 旧文留 RunDetail/BatchSummary PM confirmation ⚠️；目标为 Local History 只做 git snapshot；RunDetail/BatchSummary 归 Timeline/I/O。
2. snapshot: baseline 现状为 HistoryPanel 显示 snapshot/revert live；目标为 快照列表/刷新/revert 可用且错误可见。
3. 写机制: baseline 现状为 快照写机制不在本 region；目标为 snapshot 写由 publish/native-fs 触发，本 region 只显示。

## 7. 涉及 region / platform
`publish` · `native-fs` · `timeline`

## 8. gaps / 报警
- 🚨 scope: 旧文留 RunDetail/BatchSummary PM confirmation ⚠️；目标 Local History 只做 git snapshot；RunDetail/BatchSummary 归 Timeline/I/O。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `publish` · `native-fs` · `timeline`
