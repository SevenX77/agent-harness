---
module: 04_platform/native-fs
doc: mvp1-alignment
status: drafted（Tauri sidecar/picker/reveal live；实际 skill/graph/package 写入仍经 FastAPI/Python，多处未收敛到 Rust 唯一写者 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [native-rust-writer, workspace-open-folder-mru, subgraph-path-inline-drilldown, publish-artifact-autocommit, local-history-snapshot, copilot-session-persistence]
aligns_with: docs/studio/_reorg/alignment-notes.md（D10/D12）· 01_workflows/01_init.md · 01_workflows/02_authoring.md
---

# native-fs — MVP1 Alignment

> **Tier**: platform | **Owns**: `native-rust-writer`（唯一写者）+ workspace/open-folder/storage 相关 platform 切面 | **现状**: Tauri sidecar/picker/reveal live；实际 skill/graph/package 写入仍经 FastAPI/Python，多处未收敛到 Rust 唯一写者 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `file-editing` · `editor` · `publish` · `skill-workspace` · `welcome` · `shell-layout`

## 1. 定义
`native-fs` is the Rust/Tauri platform block for local workspace ownership: directory picking, file reads/writes, MRU, reveal/open, file watching, workspace storage, run/golden/artifact filesystem layout, and sidecar lifecycle.

Source workflow basis: `01_workflows/01_init.md:39`, `01_workflows/02_authoring.md:42`, `01_workflows/06_eval.md:41`.

## 2. 数据流 / 机制（设计细节）
### F1. Unique Local Writer

- 机制: all skill file/graph/golden/artifact writes route through Rust-native commands.
- 决策: D12 moves local writes to Rust while keeping graph-agent/gateway in Python sidecars.
- 原话/来源: `01_workflows/01_init.md:39` records the D12 quote; `01_workflows/02_authoring.md:42` repeats Rust writes for authoring.
- 测试: saving phase file and graph does not call FastAPI file-write endpoint; expected-hash conflict still works.
- Status: target-design.
- 归属: platform `native-fs`; capabilities `file-editing`, `graph-authoring`.

### F2. Workspace Folder Operations

- 机制: pick/open/reveal local folders and manage workspace membership/MRU.
- 决策: Studio behaves like an IDE workspace.
- 原话/来源: `01_workflows/01_init.md:35` locks IDE/workspace model.
- 测试: directory picker works in Tauri; reveal opens file manager; MRU survives restart.
- Status: partial live.
- 归属: platform `native-fs`; region `welcome`, `assets`.

### F3. Sidecar Lifecycle

- 机制: Tauri starts Python sidecars, passes token/config, waits for health, exposes stderr, and shuts down on app exit.
- 决策: engine/gateway remain Python sidecars for MVP1, managed by Rust.
- 原话/来源: `01_workflows/01_init.md:39` keeps only graph-agent/gateway Python sidecars.
- 测试: sidecar starts on one dynamic port; frontend receives base/ws URL; exit kills sidecar.
- Status: live.
- 归属: platform `native-fs`; platform `engine`, `gateway`.

### F4. Workspace Runtime Storage

- 机制: run traces, checkpoints, golden, test inputs, and artifacts have stable workspace storage paths.
- 决策: storage is part of local workspace, not remote registry state.
- 原话/来源: `01_workflows/04_run-and-verify.md:48` lists run artifacts; `01_workflows/06_eval.md:16` keeps local autocommit.
- 测试: run directories, trace, final state, golden, artifacts, and local history survive restart.
- Status: Python-owned today, Rust target.
- 归属: platform `native-fs`; capabilities `run-execution`, `golden-eval`, `publish`.

### F5. Scoped Backend Failure

- 机制: sidecar-dependent functions show scoped errors while shell/file surfaces remain available.
- 决策: no full-screen bootstrap gate for sidecar failure.
- 原话/来源: `_reorg/alignment-notes.md` D10(non-fullscreen sidecar gate)。
- 测试: app shell opens when sidecar fails; compile/copilot/settings show local errors.
- Status: partial; RuntimeGate still needs audit.
- 归属: platform `native-fs`; region `shell-layout`.

## 3. 接口契约
- Frontend calls Tauri/native commands for local filesystem operations.
- Python sidecars are for engine/gateway computation and HTTP surfaces, not local write authority.
- Sidecar runtime config provides API/WS URL and token to the frontend.
- Capability links: `skill-workspace`, `file-editing`, `graph-authoring`, `publish`, `golden-eval`.

## 4. 设计决策基础（PM 原话）
- **砍掉** `open_in_cursor` / `open_in_codex` / `open_in_terminal`(不进 MVP1 UI;现码 `apps/studio/frontend/src/lib/tauri.ts:openInCursor（L26）` 仍在,属待清 drift);`reveal_in_file_manager`(访达/资源管理器显示)= **保留**(正经工作区功能)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| NATIVE_FS-1 | 唯一写者 | 对齐 `native-rust-writer` 设计单元并保护四层边界 |
| NATIVE_FS-2 | 打包写者 | 对齐 `native-rust-writer` 设计单元并保护四层边界 |
| NATIVE_FS-3 | sidecar gate | 对齐 `native-rust-writer` 设计单元并保护四层边界 |

## 6. 测试关键点
1. 唯一写者: baseline 现状为 file/graph writes 仍走 FastAPI/Python ⚠️；目标为 所有本地写走 Rust/Tauri writer 或明确的 Rust-mediated path。
2. 打包写者: baseline 现状为 `build_publish_package` Python zip ⚠️；目标为 publish package 写入/打包边界收口到 native-fs。
3. sidecar gate: baseline 现状为 旧 non-fullscreen gate 引用需对齐 D10 ⚠️；目标为 shell 即时渲染，sidecar 错误局部显示。

## 7. 涉及 region / platform
`file-editing` · `editor` · `publish` · `skill-workspace` · `welcome` · `shell-layout`

## 8. gaps / 报警
- 🚨 唯一写者: file/graph writes 仍走 FastAPI/Python ⚠️；目标 所有本地写走 Rust/Tauri writer 或明确的 Rust-mediated path。
- 🚨 打包写者: `build_publish_package` Python zip ⚠️；目标 publish package 写入/打包边界收口到 native-fs。
- 🚨 sidecar gate: 旧 non-fullscreen gate 引用需对齐 D10 ⚠️；目标 shell 即时渲染，sidecar 错误局部显示。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `file-editing` · `editor` · `publish` · `skill-workspace` · `welcome` · `shell-layout`
