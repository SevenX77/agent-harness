# editor Baseline

Status: live for source editing and split editor; trace/debug editor uses are target-design.

Source workflows: `01_workflows/02_authoring.md`, `01_workflows/04_run-and-verify.md`, `01_workflows/05_debugging.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| SplitEditor | Split editor renders Monaco plus mini GraphCanvas below. | `apps/studio/frontend/src/components/studio/SplitEditor.tsx:23`, `apps/studio/frontend/src/components/studio/SplitEditor.tsx:77` |
| Monaco render | LazyMonacoPanel renders editor with file path/content/hash and save settings. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:52` |
| Autosave | On change, editor schedules a 1500ms save. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:165` |
| Save conflict | Save uses `writeSkillFile` and forwards 409 conflicts. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:99` |
| Read-only | Monaco options set readOnly when save is disabled. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:217` |
| Open file source | Workspace opens files from panels/canvas and syncs content/hash. | `apps/studio/frontend/src/components/studio/Workspace.tsx:103`, `apps/studio/frontend/src/components/studio/Workspace.tsx:120` |
| Phase save | Workspace phase save updates editor and skill detail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:159` |
| Trace doc gap | TracePanel exists separately; it does not open a read-only Monaco document. | `apps/studio/frontend/src/components/TracePanel.tsx:50` |

## Current Region Ownership

- Owns: Monaco editor surface, split editor layout, file save/read-only behavior, future virtual documents.
- Does not own: file tree, Properties field form, trace interpretation.

## Known Drift

- Compile inline markers are required but not wired to Monaco diagnostics (`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:217` only covers read-only).
- Run-after full trace should open as human-readable read-only document; no such editor flow is mounted (`apps/studio/frontend/src/components/TracePanel.tsx:50`).
