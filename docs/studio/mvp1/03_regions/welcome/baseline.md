# welcome Baseline

Status: live for recent/create/import/delete shell; import policy is stricter than MVP1 target.

Source workflow: `01_workflows/01_init.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Welcome state | Welcome reads skill list and recent skills, then sorts visible cards by recent use. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:231`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:244` |
| Open card | Opening a skill remembers it and calls the parent `onSelectSkill`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:246` |
| New skill | New skill dialog posts to `/skills` with selected parent directory and opens the result. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:288`, `apps/studio/frontend/src/components/welcome/NewSkillDialog.tsx:39` |
| Import skill | Import uses directory picker then posts path/name to `/skills`. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:310`, `apps/studio/frontend/src/lib/tauri.ts:64` |
| Reveal/delete | Card menu can reveal in file manager or delete/unregister. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:270`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:274` |
| Error/empty state | Welcome renders list error and empty state. | `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:392`, `apps/studio/frontend/src/components/welcome/WelcomePage.tsx:524` |
| Backend import gate | Backend import rejects missing `GRAPH.md` and `SKILL.md`. | `apps/studio/backend/app/services/skills.py:512` |

## Current Region Ownership

- Owns: Home/Recent grid, New Skill dialog entry, Import Skill entry, reveal/delete card menu, empty/error states.
- Does not own: graph editor internals, settings forms, publish result pages.

## Known Drift

- MVP1 wants open/import to accept arbitrary folders and let compile/copilot repair; current backend blocks import before entering the workspace (`apps/studio/backend/app/services/skills.py:512`).
- Current button text says "Import skill"; target mental model may need "Open folder" for IDE/workspace framing (`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:350`).
