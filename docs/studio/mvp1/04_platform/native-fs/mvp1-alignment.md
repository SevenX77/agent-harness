---
module: 04_platform/native-fs
doc: mvp1-alignment
status: FROZEN（Tauri sidecar/picker/reveal live；Studio 自有 skill/graph/package 写入仍经 FastAPI/Python，多处未收敛到 Rust 唯一写者 ⚠️；Copilot SDK Write/Edit 为 MVP1 明确例外。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [native-rust-writer, workspace-open-folder-mru, subgraph-path-inline-drilldown, publish-artifact-autocommit, local-history-snapshot, copilot-session-persistence]
aligns_with: 01_workflows/01_init.md（D10/D12 决策留底）· 01_workflows/02_authoring.md
---

# native-fs — MVP1 Alignment

> **Tier**: platform | **Owns**: `native-rust-writer`（Studio 自有本地写入唯一写者；Copilot SDK Write/Edit 例外）+ workspace/open-folder/storage 相关 platform 切面 | **现状**: Tauri sidecar/picker/reveal live；Studio 自有 skill/graph/package 写入仍经 FastAPI/Python，多处未收敛到 Rust 唯一写者 ⚠️；Copilot SDK Write/Edit 为 MVP1 明确例外。 | **Related**: [baseline](./baseline.md)（双向）· `file-editing` · `editor` · `publish` · `skill-workspace` · `welcome` · `shell-layout`

## 1. 定义
`native-fs` is the Rust/Tauri platform block for Studio-owned local workspace operations: directory picking, file reads/writes, MRU, reveal/open, file watching, workspace storage, run/golden/artifact filesystem layout, and sidecar lifecycle. MVP1 carves out Copilot SDK `Read/Write/Edit`, which may read/write the workspace directly as an external agent runtime path.

Source workflow basis: `01_workflows/01_init.md:39`, `01_workflows/02_authoring.md:42`, `01_workflows/06_eval.md:41`.

## 2. 数据流 / 机制（设计细节）
### F1. Unique Local Writer

- 机制: Studio-owned skill file/graph/golden/artifact writes route through Rust-native commands; Copilot SDK `Read/Write/Edit` is explicitly excluded for MVP1.
- 决策: D12 moves Studio local writes to Rust while keeping graph-agent/gateway in Python sidecars; PM 2026-06-14 allows Copilot SDK Write/Edit to read/write workspace directly.
- 原话/来源: `01_workflows/01_init.md:39` records the D12 quote; `01_workflows/02_authoring.md:42` repeats Rust writes for authoring.
- 测试: saving phase file and graph does not call FastAPI file-write endpoint; expected-hash conflict still works; Copilot SDK Write/Edit direct writes are not reported as D12 violations.
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
- 原话/来源: 本文 §4 D10(non-fullscreen sidecar gate)+ `01_workflows/01_init.md` §3。
- 测试: app shell opens when sidecar fails; compile/copilot/settings show local errors.
- Status: partial; RuntimeGate still needs audit.
- 归属: platform `native-fs`; region `shell-layout`.

## 3. 接口契约
- Frontend calls Tauri/native commands for Studio-owned local filesystem operations.
- Python sidecars are for engine/gateway computation and HTTP surfaces, not Studio local write authority.
- Copilot SDK `Read/Write/Edit` is an MVP1 exception owned by `copilot-assist`: it may read/write within workspace/cwd/add_dirs directly and is not mediated by `native-fs`.
- Sidecar runtime config provides API/WS URL and token to the frontend.
- Capability links: `skill-workspace`, `file-editing`, `graph-authoring`, `publish`, `golden-eval`.

## 4. 设计决策基础（PM 原话）
- **D10 后端三分**(native-fs = 第三块「本地操作」,🔒锁 PM 2026-06-01)> "后端应该分为3块: 1. gateway 包括 studio backend里面的llm gateway相关的后端部分代码要并入 gateway, 这部分全部用服务形式, python sidecar; 2. graph agent engine, 也是python, 用 sidecar; 前面两块都是 引擎真跑的时候需要调用的服务; 3. 大量的本地操作, 读写文件, 文件系统(打开文件夹)等等, 全部用rust本地操作. 判断这样是否可行?? 如果是这样的话, 应该不需要bootstrap. 调用后端的地方skeleton就行";sidecar 启动期 eager-spawn(非全屏 gate)> "启动程序时就后端拉起sidecar, 因为未来还要登陆用户呢, 还有setting 页面里api、llm role这些配置都需要服务端"。
- **D12 本地操作全量 Rust(唯一写者,🔒PM 裁定 2026-06-01)**> "全量切 rust, 除了 graph agent 和 llm gateway 相关使用 python sidecar, 其他本地操作都用 rust";Studio 自有 skill 源文件 / `.workspace` / 编辑器 save / graph serialize / publish package 全走 Rust 命令,Python 端点退为只读 + 编译装配。
- **Copilot Write/Edit 例外(PM 2026-06-14)**: Copilot SDK `Read/Write/Edit` 在 MVP1 允许自行读写 workspace,不作为 D12 违规;Studio 负责工具事件回显、diff/summary 和视图刷新。该例外只覆盖 SDK 工具 runner,不覆盖编辑器保存、脚手架、test_inputs/golden/runs/artifacts、publish 打包等 Studio 自有写入。
- **砍掉** `open_in_cursor` / `open_in_codex` / `open_in_terminal`(D3,不进 MVP1 UI;现码 `apps/studio/frontend/src/lib/tauri.ts:openInCursor（L26）` 仍在,属待清 drift);`reveal_in_file_manager`(访达/资源管理器显示)= **保留**(正经工作区功能)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| NATIVE_FS-1 | Studio 自有写入唯一写者 | 单元 `native-rust-writer`；**为什么**：Studio 自有本地写走 Rust 唯一写者(D12)，避免双写者并发冲突；Copilot SDK Write/Edit 是 MVP1 例外 |
| NATIVE_FS-2 | 打包写者 | 单元 `native-rust-writer`（+`publish-artifact-autocommit`）；**为什么**：publish package 打包/写盘收口 native-fs，非 Python zip |
| NATIVE_FS-3 | sidecar gate | 单元 `shell-runtime-gate`（消费；owner=shell-layout）；**为什么**：sidecar 失败局部显示、不全屏阻塞(D10)，壳/runtime 状态归 shell-runtime-gate |

## 6. 测试关键点
1. 唯一写者: baseline 现状为 file/graph writes 仍走 FastAPI/Python ⚠️；目标为 Studio 自有本地写走 Rust/Tauri writer 或明确的 Rust-mediated path；Copilot SDK Write/Edit 直写不算违规。
2. 打包写者: baseline 现状为 `build_publish_package` Python zip ⚠️；目标为 publish package 写入/打包边界收口到 native-fs。
3. sidecar gate: baseline 现状为 旧 non-fullscreen gate 引用需对齐 D10 ⚠️；目标为 shell 即时渲染，sidecar 错误局部显示。

## 7. 涉及 region / platform
`file-editing` · `editor` · `publish` · `skill-workspace` · `welcome` · `shell-layout`

## 8. gaps / 报警
- 🚨 唯一写者: file/graph writes 仍走 FastAPI/Python ⚠️；目标 Studio 自有本地写走 Rust/Tauri writer 或明确的 Rust-mediated path；Copilot SDK Write/Edit 直写为 MVP1 允许例外。
- 🚨 打包写者: `build_publish_package` Python zip ⚠️；目标 publish package 写入/打包边界收口到 native-fs。
- 🚨 sidecar gate: 旧 non-fullscreen gate 引用需对齐 D10 ⚠️；目标 shell 即时渲染，sidecar 错误局部显示。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `file-editing` · `editor` · `publish` · `skill-workspace` · `welcome` · `shell-layout`
