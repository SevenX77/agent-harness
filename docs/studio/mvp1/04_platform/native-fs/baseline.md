# native-fs Baseline

Status: Tauri owns sidecar lifecycle and some OS file helpers; local skill writes still mostly go through FastAPI/Python.

Source workflows: `01_workflows/01_init.md`, `01_workflows/02_authoring.md`, `01_workflows/06_eval.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Runtime config | Tauri exposes sidecar runtime config and stderr commands. | `apps/studio/tauri/src/lib.rs:19`, `apps/studio/tauri/src/lib.rs:39` |
| Directory picker | Tauri command selects a local directory with optional starting path. | `apps/studio/tauri/src/lib.rs:89` |
| Reveal/open tools | Tauri exposes reveal and external tool helpers. | `apps/studio/tauri/src/lib.rs:70`, `apps/studio/tauri/src/lib.rs:129` |
| Command handler | Tauri registers sidecar, picker, reveal, terminal, and external tool commands. | `apps/studio/tauri/src/lib.rs:306`, `apps/studio/tauri/src/lib.rs:308` |
| Sidecar startup | Tauri starts the Python sidecar unless disabled, stores manager or startup error. | `apps/studio/tauri/src/lib.rs:325`, `apps/studio/tauri/src/sidecar.rs:140` |
| Runtime URLs/token | Sidecar runtime config returns base URL, websocket URL, resource/config dirs, and API token. | `apps/studio/tauri/src/sidecar.rs:101`, `apps/studio/tauri/src/sidecar.rs:115` |
| Sidecar env/CORS | Sidecar process receives resource/config dirs, API token, CORS origins, and orphan-exit flag. | `apps/studio/tauri/src/sidecar.rs:317`, `apps/studio/tauri/src/sidecar.rs:331` |
| Current file writes | Frontend file writes call FastAPI `writeSkillFile`; backend writes and records API write. | `apps/studio/frontend/src/api/client.ts:176`, `apps/studio/backend/app/services/skills.py:410` |
| Current graph writes | Graph serialization goes through FastAPI and Python service. | `apps/studio/frontend/src/api/client.ts:95`, `apps/studio/backend/app/routers/skills.py:122` |
| Run/golden dirs | Python service currently defines `.workspace` run/golden/local/test input directories. | `apps/studio/backend/app/services/skills.py:762` |

## Current Coverage

- live: sidecar lifecycle, config/token, directory picker, reveal/open helpers, CORS origin injection.
- stale: local write authority is still Python-sidecar code.
- target gap: Rust-native read/write/watch/MRU/runs/golden/artifacts orchestration.

## Known Drift

- D12 target is "local writes all Rust, only engine/gateway remain Python sidecars"; current file and graph writes go through FastAPI (`apps/studio/backend/app/services/skills.py:410`).
- Some external IDE helpers may be outside the locked MVP1 shell model and need product confirmation (`apps/studio/tauri/src/lib.rs:70`).
