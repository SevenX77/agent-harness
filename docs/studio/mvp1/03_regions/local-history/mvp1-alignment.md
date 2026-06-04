# local-history MVP1 Alignment

## 定义

`local-history` owns local workspace snapshots: successful-run autocommit visibility, manual/auto snapshot list, selecting a snapshot, and revert.

Source workflow basis: `01_workflows/06_eval.md:13`, `01_workflows/06_eval.md:24`, `01_workflows/04_run-and-verify.md:59`.

## 接口契约

- Inputs: local git history items, current skill id, selected sha.
- Outputs: refresh, select snapshot, revert request.
- Capability links: `publish`, `run-execution`, `skill-workspace`.
- Platform link: `native-fs`.

## F1. Snapshot List

- 机制: show local git snapshots with short sha, kind, author, timestamp, and message.
- 决策: local save is the MVP safety net.
- 原话/来源: `01_workflows/06_eval.md:16` marks autocommit live; `01_workflows/06_eval.md:27` keeps local autocommit.
- 测试: successful run creates an auto_run snapshot; manual snapshots show distinct kind.
- Status: live.
- 归属: region `local-history`; capability `publish`.

## F2. Revert Snapshot

- 机制: user selects a snapshot and reverts the skill to that sha.
- 决策: recovery should be local and explicit.
- 原话/来源: `01_workflows/06_eval.md:36` includes successful-run autocommit as a key test; revert is the recovery pair.
- 测试: disabled without selection; revert updates workspace files and refreshes skill detail.
- Status: live.
- 归属: region `local-history`; platform `native-fs`.

## F3. Run Detail Ownership Check

- 机制: RunDetailDrawer/BatchSummary should be wired where run review happens unless PM wants Local History to own them.
- 决策: run detail is time/run semantics, not git snapshot semantics.
- 原话/来源: `01_workflows/04_run-and-verify.md:58` lists run detail under run history; `01_workflows/04_run-and-verify.md:54` lists batch under i/o/run.
- 测试: run row opens RunDetailDrawer from Timeline; batch progress opens from i/o panel.
- Status: ownership gap.
- 归属: likely `timeline` and `input`; PM confirmation needed.

## 待 PM 补 gap

- Confirm whether Local History should remain git-only or absorb RunDetailDrawer/BatchSummary as the old README implied.
