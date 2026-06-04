# publish Baseline

Status: minimal live. Release exists as a Header menu action and uploads an Artifact Registry zip; successful runs autocommit locally. Publish is intentionally low priority.

Source workflow: `01_workflows/06_eval.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Header entry | Team dropdown exposes Save to Team, Sync, Submit for Review, and Release. | `apps/studio/frontend/src/components/studio/Header.tsx:98`, `apps/studio/frontend/src/components/studio/Header.tsx:119` |
| Publish hook | `usePublishSkill` manages idle/publishing/success/error state and toast feedback. | `apps/studio/frontend/src/hooks/usePublishSkill.ts:6`, `apps/studio/frontend/src/hooks/usePublishSkill.ts:31` |
| API call | Frontend posts to `/skills/{skill_id}/publish`. | `apps/studio/frontend/src/api/client.ts:78` |
| Publish route | Backend validates request/settings, builds package, uploads artifact, and returns result. | `apps/studio/backend/app/routers/skills.py:246`, `apps/studio/backend/app/routers/skills.py:286` |
| Package build | Artifact package is built as a zip from the skill directory. | `apps/studio/backend/app/services/artifact_registry.py:91` |
| Upload | Registry upload posts metadata and zip package to `/api/v1/artifacts`. | `apps/studio/backend/app/services/artifact_registry.py:46` |
| Metadata | Publish metadata requires non-empty `user_id` and version. | `apps/studio/backend/app/services/artifact_registry.py:130` |
| Autocommit | Run manager auto-commits successful runs and records git status. | `apps/studio/backend/app/services/run_manager.py:445` |

## Current Coverage

- live: Release action, Artifact Registry zip upload, user/registry precondition checks, local run autocommit.
- stale-doc deleted by workflow: git push, commit-message UI, confetti.
- target gap: package build should move to Rust/native-fs if D12 is applied strictly.

## Known Drift

- Publish is hidden under Team menu and does not close the loop back to Home automatically (`apps/studio/frontend/src/components/studio/Header.tsx:98`).
- Packaging is Python-sidecar code today, while D12 targets Rust-native local packaging (`apps/studio/backend/app/services/artifact_registry.py:91`).
