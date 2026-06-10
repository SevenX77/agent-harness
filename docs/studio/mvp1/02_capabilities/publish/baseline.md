---
module: 02_capabilities/publish
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；Artifact Registry zip 发布路径 live；zip 构建仍在 Python 后端，D12 Rust 写者未收口 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/hooks/usePublishSkill.ts:usePublishSkill · apps/studio/backend/app/routers/skills.py:publish_skill · apps/studio/backend/app/services/artifact_registry.py:build_publish_package · apps/studio/backend/app/services/run_manager.py:_auto_commit_successful_run
units: [publish-artifact-autocommit]
---

# publish — Baseline（当下代码实现逻辑）

> **Scope**: 成功 run 本地存档/autocommit、Artifact Registry 发布、返回 Home 的发布闭环。
> **现状一句话**: Artifact Registry zip 发布路径 live；zip 构建仍在 Python 后端，D12 Rust 写者未收口 ⚠️。

## UI/UX
成功 run 本地存档/autocommit、Artifact Registry 发布、返回 Home 的发布闭环。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Header entry | Team dropdown exposes Save to Team, Sync, Submit for Review, and Release. | `apps/studio/frontend/src/components/studio/Header.tsx:prTitle（L98）`, `apps/studio/frontend/src/components/studio/Header.tsx:prTitle（L119）` |
| Publish hook | `usePublishSkill` manages idle/publishing/success/error state and toast feedback. | `apps/studio/frontend/src/hooks/usePublishSkill.ts:usePublishSkill（L6）`, `apps/studio/frontend/src/hooks/usePublishSkill.ts:executePublishSkill（L31）` |
| API call | Frontend posts to `/skills/{skill_id}/publish`. | `apps/studio/frontend/src/api/client.ts:publishSkill（L78）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Publish route | Backend validates request/settings, builds package, uploads artifact, and returns result. | `apps/studio/backend/app/routers/skills.py:sync_skill（L246）`, `apps/studio/backend/app/routers/skills.py:publish_skill（L286）` |
| Package build | Artifact package is built as a zip from the skill directory. | `apps/studio/backend/app/services/artifact_registry.py:build_publish_package（L91）` |
| Upload | Registry upload posts metadata and zip package to `/api/v1/artifacts`. | `apps/studio/backend/app/services/artifact_registry.py:upload_artifact（L46）` |
| Metadata | Publish metadata requires non-empty `user_id` and version. | `apps/studio/backend/app/services/artifact_registry.py:build_publish_metadata（L130）` |
| Autocommit | Run manager auto-commits successful runs and records git status. | `apps/studio/backend/app/services/run_manager.py:_auto_commit_successful_run（L445）` |

## 当前边界（publish 现在不是什么）
- 不拥有 Gitea/git push 工作流；MVP1 publish 是 Artifact Registry。
- 快照展示归 `local-history`，写机制归 `native-fs`/publish。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 发布口径 | 发布为 Artifact Registry zip；非 git push | UI 不再把 Publish 等同 Gitea push |
| 打包写者 | `build_publish_package` Python 打 zip ⚠️ | 打包/本地写动作经 D12 Rust 写者或明确适配边界 |
| autocommit | 成功 run auto-commit live | publish 前能看到本地存档/快照状态 |
> **验"是否按目标改了"**：1. 发布口径；2. 打包写者；3. autocommit。

## 读代码主路径提示
`apps/studio/frontend/src/hooks/usePublishSkill.ts:usePublishSkill` → `apps/studio/backend/app/routers/skills.py:publish_skill` → `apps/studio/backend/app/services/artifact_registry.py:build_publish_package` → `apps/studio/backend/app/services/run_manager.py:_auto_commit_successful_run`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-publish)（迁移期安全网，代码实现验证后删）。

## WS-6 Studio-only Closeout Update

- **Artifact Registry Release & History Record**: Live. Artifact Registry minimal release is functional, and recording publish events in local history is live. Silent failure when recording local history is blocked; it is rejected with 500 `LOCAL_HISTORY_RECORD_FAILED`.
- **Deferred Items**: Team collaboration features, git push, commit-message UI, and completion confetti remain deferred.

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `native-fs` · `local-history` · `skill-workspace`
