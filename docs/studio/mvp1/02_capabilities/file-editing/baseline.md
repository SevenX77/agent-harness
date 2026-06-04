# file-editing Baseline

Status: live for Monaco edit/save and conflict callbacks; target read-only trace/editor behaviors are not yet connected.

Source workflows: `01_workflows/02_authoring.md`, `01_workflows/04_run-and-verify.md`, `01_workflows/05_debugging.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Open file model | Workspace converts a skill file into an `OpenFile` with path/content/hash. | `apps/studio/frontend/src/components/studio/Workspace.tsx:103` |
| File open | Workspace opens a file, focuses editor, and closes settings overlay. | `apps/studio/frontend/src/components/studio/Workspace.tsx:120` |
| Phase save | Phase file save writes through `writeSkillFile`, updates open editor and skill detail, then clears conflict state. | `apps/studio/frontend/src/components/studio/Workspace.tsx:159` |
| Monaco panel | `LazyMonacoPanel` renders the editor and receives skill/file/hash/save settings. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:52` |
| Autosave | Editor changes debounce into save after 1500ms. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:165` |
| Conflict | Save catches 409 conflicts and delegates to `onConflict`. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:99` |
| Read-only flag | Monaco respects `readOnly: !saveEnabled`. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:217` |
| Split view | Split editor combines Monaco with a mini graph canvas. | `apps/studio/frontend/src/components/studio/SplitEditor.tsx:77` |
| File tree source | Assets/file panels render from `skillDetail.files`. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:37`, `apps/studio/frontend/src/components/studio/panels/panel-files.ts:37` |
| Backend write | Single file write validates suffix/path and records API writes. | `apps/studio/backend/app/services/skills.py:410` |

## Current Coverage

- live: open, autosave, manual save via callback, expected-hash conflict path, read-only editor option.
- stale: write path goes through Python, not Rust/native-fs target.
- missing: trace read-only document view, writable context-tamper editor for debug-resume, editor gutter diagnostics.

## Known Drift

- D12 says local writes should be Rust/native-fs; current file writes route through FastAPI (`apps/studio/backend/app/services/skills.py:410`).
- Compile errors should appear inline like an IDE; Monaco diagnostics are not wired (`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:217` only toggles read-only).
- Trace wants a human-readable read-only trace document; existing trace components are not mounted into the editor flow (`apps/studio/frontend/src/components/TracePanel.tsx:50`).
