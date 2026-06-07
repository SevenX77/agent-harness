---
module: 02_capabilities/publish
doc: mvp1-alignment
status: FROZEN（Artifact Registry zip 发布路径 live；zip 构建仍在 Python 后端，D12 Rust 写者未收口 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [publish-artifact-autocommit]
aligns_with: 01_workflows/06_eval.md（publish / artifact registry）
---

# publish — MVP1 Alignment

> **Tier**: capability | **Owns**: `publish-artifact-autocommit`（发布/Artifact Registry；快照写机制引 native-fs/local-history） | **现状**: Artifact Registry zip 发布路径 live；zip 构建仍在 Python 后端，D12 Rust 写者未收口 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `native-fs` · `local-history` · `skill-workspace`

## 1. 定义
`publish` owns the end-of-loop save and release behavior after a successful run/golden check: local autocommit as the MVP safety net, and low-priority Artifact Registry release as the external distribution hook.

Source workflow basis: `01_workflows/06_eval.md:1`, `01_workflows/06_eval.md:13`, `01_workflows/06_eval.md:24`.

## 2. 数据流 / 机制（设计细节）
### F1. Successful Run Autocommit

- 机制: after a successful run, Studio commits the local workspace state for recovery/history.
- 决策: local save is enough for MVP1; team/Gitea is a future placeholder.
- 原话/来源: `01_workflows/06_eval.md:16` marks successful-run autocommit live; `01_workflows/06_eval.md:30` records that local save is enough for now.
- 测试: successful run records committed/locked/failed git status; failed run does not autocommit.
- Status: live.
- 归属: capability `publish`; capability `run-execution`; platform `native-fs`.

### F2. Release To Artifact Registry

- 机制: Header Release posts to publish API; backend zips the skill and uploads package + metadata.
- 决策: publish is low priority but keeps the external artifact hook alive.
- 原话/来源: `01_workflows/06_eval.md:6` says publish is low-priority and Artifact Registry based, not git push; `01_workflows/06_eval.md:31` says keep it minimal.
- 测试: missing user/registry settings gives a clear error; success returns artifact id; network failure does not mutate local draft.
- Status: live minimal.
- 归属: capability `publish`; region `shell-layout`; platform `native-fs`.

### F3. Remove Stale Publish UX

- 机制: do not implement commit-message prompt, git push path, confetti, or separate heavy release flow in MVP1.
- 决策: those were stale-doc virtual requirements, not current PM priority.
- 原话/来源: `01_workflows/06_eval.md:21` and `01_workflows/06_eval.md:22` explicitly delete commit message UI and confetti.
- 测试: release flow has no commit-message modal and no celebration dependency.
- Status: target rule, current UI already does not show them.
- 归属: capability `publish`; region `shell-layout`.

### F4. Return Home Loop

- 机制: after save/release, user can return to Home and start a new exploration.
- 决策: publish belongs to the loop close, not golden/diff authoring.
- 原话/来源: `01_workflows/06_eval.md:9` defines save/release then return Home.
- 测试: Back Home after release clears workspace state and keeps the published skill in Recent.
- Status: partial live; no automatic redirect.
- 归属: capability `skill-workspace`; region `welcome`, `shell-layout`.

## 3. 接口契约
- Run manager emits successful-run autocommit status.
- Header Release calls publish endpoint and displays success/error.
- Publish endpoint validates identity and registry settings, builds package, uploads artifact.
- Region links: `shell-layout`, `welcome`, `settings`.
- Platform links: `native-fs`, `gateway` only for settings/auth dependencies.

## 4. 设计决策基础（PM 原话）
- 发布前置不满足时**加一个跳 Settings 的快捷入口**(一键去配)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| PUBLISH-1 | 发布口径 | 单元 `publish-artifact-autocommit`；**为什么**：发布≠git push;本地 git autocommit 存档 + Artifact Registry 最小发布(PM 2026-06-04 低优先) |
| PUBLISH-2 | 打包写者 | 单元 `publish-artifact-autocommit`；**为什么**：publish package 打包/写盘边界收口到 native-fs(Rust)，非 Python zip |
| PUBLISH-3 | autocommit | 单元 `publish-artifact-autocommit`；**为什么**：成功 run 自动 commit 本地存档，作恢复安全网 |

## 6. 测试关键点
1. 发布口径: baseline 现状为 发布为 Artifact Registry zip；非 git push；目标为 UI 不再把 Publish 等同 Gitea push。
2. 打包写者: baseline 现状为 `build_publish_package` Python 打 zip ⚠️；目标为 打包/本地写动作经 D12 Rust 写者或明确适配边界。
3. autocommit: baseline 现状为 成功 run auto-commit live；目标为 publish 前能看到本地存档/快照状态。

## 7. 涉及 region / platform
`native-fs` · `local-history` · `skill-workspace`

## 8. gaps / 报警
- 🚨 打包写者: `build_publish_package` Python 打 zip ⚠️；目标 打包/本地写动作经 D12 Rust 写者或明确适配边界。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `native-fs` · `local-history` · `skill-workspace`
