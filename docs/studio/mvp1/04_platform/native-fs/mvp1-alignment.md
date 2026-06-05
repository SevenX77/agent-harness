# native-fs MVP1 Alignment

## 定义

`native-fs` is the Rust/Tauri platform block for local workspace ownership: directory picking, file reads/writes, MRU, reveal/open, file watching, workspace storage, run/golden/artifact filesystem layout, and sidecar lifecycle.

Source workflow basis: `01_workflows/01_init.md:39`, `01_workflows/02_authoring.md:42`, `01_workflows/06_eval.md:41`.

## 接口契约

- Frontend calls Tauri/native commands for local filesystem operations.
- Python sidecars are for engine/gateway computation and HTTP surfaces, not local write authority.
- Sidecar runtime config provides API/WS URL and token to the frontend.
- Capability links: `skill-workspace`, `file-editing`, `graph-authoring`, `publish`, `golden-eval`.

## F1. Unique Local Writer

- 机制: all skill file/graph/golden/artifact writes route through Rust-native commands.
- 决策: D12 moves local writes to Rust while keeping graph-agent/gateway in Python sidecars.
- 原话/来源: `01_workflows/01_init.md:39` records the D12 quote; `01_workflows/02_authoring.md:42` repeats Rust writes for authoring.
- 测试: saving phase file and graph does not call FastAPI file-write endpoint; expected-hash conflict still works.
- Status: target-design.
- 归属: platform `native-fs`; capabilities `file-editing`, `graph-authoring`.

## F2. Workspace Folder Operations

- 机制: pick/open/reveal local folders and manage workspace membership/MRU.
- 决策: Studio behaves like an IDE workspace.
- 原话/来源: `01_workflows/01_init.md:35` locks IDE/workspace model.
- 测试: directory picker works in Tauri; reveal opens file manager; MRU survives restart.
- Status: partial live.
- 归属: platform `native-fs`; region `welcome`, `assets`.

## F3. Sidecar Lifecycle

- 机制: Tauri starts Python sidecars, passes token/config, waits for health, exposes stderr, and shuts down on app exit.
- 决策: engine/gateway remain Python sidecars for MVP1, managed by Rust.
- 原话/来源: `01_workflows/01_init.md:39` keeps only graph-agent/gateway Python sidecars.
- 测试: sidecar starts on one dynamic port; frontend receives base/ws URL; exit kills sidecar.
- Status: live.
- 归属: platform `native-fs`; platform `engine`, `gateway`.

## F4. Workspace Runtime Storage

- 机制: run traces, checkpoints, golden, test inputs, and artifacts have stable workspace storage paths.
- 决策: storage is part of local workspace, not remote registry state.
- 原话/来源: `01_workflows/04_run-and-verify.md:48` lists run artifacts; `01_workflows/06_eval.md:16` keeps local autocommit.
- 测试: run directories, trace, final state, golden, artifacts, and local history survive restart.
- Status: Python-owned today, Rust target.
- 归属: platform `native-fs`; capabilities `run-execution`, `golden-eval`, `publish`.

## F5. Scoped Backend Failure

- 机制: sidecar-dependent functions show scoped errors while shell/file surfaces remain available.
- 决策: no full-screen bootstrap gate for sidecar failure.
- 原话/来源: `_reorg/alignment-notes.md` D10(non-fullscreen sidecar gate)。
- 测试: app shell opens when sidecar fails; compile/copilot/settings show local errors.
- Status: partial; RuntimeGate still needs audit.
- 归属: platform `native-fs`; region `shell-layout`.

## 已决(PM 2026-06-04)

- **砍掉** `open_in_cursor` / `open_in_codex` / `open_in_terminal`(不进 MVP1 UI;现码 `apps/studio/frontend/src/lib/tauri.ts:26` 仍在,属待清 drift);`reveal_in_file_manager`(访达/资源管理器显示)= **保留**(正经工作区功能)。
