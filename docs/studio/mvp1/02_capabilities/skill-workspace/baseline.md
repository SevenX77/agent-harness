# skill-workspace Baseline

Status: mixed. The welcome/home workflow exists, but the current implementation is still registry/API centered; MVP1 wants an IDE-like local workspace model.

Source workflows: `01_workflows/01_init.md`, `01_workflows/02_authoring.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Welcome data | Home reads the skills list and recent skills, then sorts visible skills by MRU. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:231`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:244` |
| Recent open | Opening a skill records it in localStorage-backed MRU before entering the workspace. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:246`, `apps/studio/frontend/src/hooks/useRecentSkills.ts:16` |
| Folder picker | Create/import flows use a directory picker helper; browser fallback cannot really pick a folder. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:258`, `apps/studio/frontend/src/lib/tauri.ts:64` |
| Create skill | New skill posts to `/skills`, then opens the created skill. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:288`, `apps/studio/backend/app/routers/skills.py:81` |
| Import existing | Import posts name/path to `/skills`; backend rejects folders missing `GRAPH.md` and `SKILL.md`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:310`, `apps/studio/backend/app/services/skills.py:512` |
| Delete | The UI offers delete; backend unregisters rather than recursively deleting the skill directory. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:274`, `apps/studio/backend/app/services/skills.py:436` |
| Workspace enter/exit | `Workspace` resets panels and copilot when no skill is active; opening a skill defaults to Assets + Copilot. | `apps/studio/frontend/src/components/studio/Workspace.tsx:44`, `apps/studio/frontend/src/components/studio/Workspace.tsx:439` |
| Nested navigation | Subgraph-like navigation is tracked in a local `navStack`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:301` |
| Backend list model | Skill list merges registry, public paths, workspace paths, and metadata; this conflicts with the MVP1 no-registry IDE model. | `apps/studio/backend/app/services/skills.py:183` |
| Native reveal | Tauri exposes reveal/open folder primitives already. | `apps/studio/tauri/src/lib.rs:90`, `apps/studio/tauri/src/lib.rs:129` |

## Current Coverage

- live: Home list, recent skills, folder picker path, create/import/delete API path, reveal in file manager.
- stale: registry/public workspace aggregation and strict import gate.
- target gap: open any local folder first, then let compile/copilot repair the skill into standard form.

## Known Drift

- D11 expects an IDE/workspace model with no registry as the primary user mental model; current backend still treats a saved index/registry as central (`apps/studio/backend/app/services/skills.py:183`).
- D2 says import should not be blocked by file shape; current import rejects folders without both root docs (`apps/studio/backend/app/services/skills.py:512`).
- D12 says local writes should move to Rust/native-fs; create/import/write still go through FastAPI/Python (`apps/studio/backend/app/routers/skills.py:81`).
