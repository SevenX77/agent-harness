# publish MVP1 Alignment

## 定义

`publish` owns the end-of-loop save and release behavior after a successful run/golden check: local autocommit as the MVP safety net, and low-priority Artifact Registry release as the external distribution hook.

Source workflow basis: `01_workflows/06_eval.md:1`, `01_workflows/06_eval.md:13`, `01_workflows/06_eval.md:24`.

## 接口契约

- Run manager emits successful-run autocommit status.
- Header Release calls publish endpoint and displays success/error.
- Publish endpoint validates identity and registry settings, builds package, uploads artifact.
- Region links: `shell-layout`, `welcome`, `settings`.
- Platform links: `native-fs`, `gateway` only for settings/auth dependencies.

## F1. Successful Run Autocommit

- 机制: after a successful run, Studio commits the local workspace state for recovery/history.
- 决策: local save is enough for MVP1; team/Gitea is a future placeholder.
- 原话/来源: `01_workflows/06_eval.md:16` marks successful-run autocommit live; `01_workflows/06_eval.md:30` records that local save is enough for now.
- 测试: successful run records committed/locked/failed git status; failed run does not autocommit.
- Status: live.
- 归属: capability `publish`; capability `run-execution`; platform `native-fs`.

## F2. Release To Artifact Registry

- 机制: Header Release posts to publish API; backend zips the skill and uploads package + metadata.
- 决策: publish is low priority but keeps the external artifact hook alive.
- 原话/来源: `01_workflows/06_eval.md:6` says publish is low-priority and Artifact Registry based, not git push; `01_workflows/06_eval.md:31` says keep it minimal.
- 测试: missing user/registry settings gives a clear error; success returns artifact id; network failure does not mutate local draft.
- Status: live minimal.
- 归属: capability `publish`; region `shell-layout`; platform `native-fs`.

## F3. Remove Stale Publish UX

- 机制: do not implement commit-message prompt, git push path, confetti, or separate heavy release flow in MVP1.
- 决策: those were stale-doc virtual requirements, not current PM priority.
- 原话/来源: `01_workflows/06_eval.md:21` and `01_workflows/06_eval.md:22` explicitly delete commit message UI and confetti.
- 测试: release flow has no commit-message modal and no celebration dependency.
- Status: target rule, current UI already does not show them.
- 归属: capability `publish`; region `shell-layout`.

## F4. Return Home Loop

- 机制: after save/release, user can return to Home and start a new exploration.
- 决策: publish belongs to the loop close, not golden/diff authoring.
- 原话/来源: `01_workflows/06_eval.md:9` defines save/release then return Home.
- 测试: Back Home after release clears workspace state and keeps the published skill in Recent.
- Status: partial live; no automatic redirect.
- 归属: capability `skill-workspace`; region `welcome`, `shell-layout`.

## 待 PM 补 gap

- Whether MVP1 should add a settings shortcut when publish preconditions fail.
