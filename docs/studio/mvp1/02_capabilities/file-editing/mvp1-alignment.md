---
module: 02_capabilities/file-editing
doc: mvp1-alignment
status: drafted（Monaco 编辑与 FastAPI 写文件 live；MVP1 D12 要求 Rust 唯一写者，当前写路径仍走 FastAPI ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [native-rust-writer]
aligns_with: 01_workflows/02_authoring.md（file editing / save）
---

# file-editing — MVP1 Alignment

> **Tier**: capability | **Owns**: 消费 `native-rust-writer` 的文件编辑切面（写者 owner 在 `native-fs`） | **现状**: Monaco 编辑与 FastAPI 写文件 live；MVP1 D12 要求 Rust 唯一写者，当前写路径仍走 FastAPI ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `editor` · `conflict-overwrite` · `native-fs`

## 1. 定义
`file-editing` owns opening Studio files, editing them in Monaco, saving with conflict protection, and reusing the same editor surface for read-only trace/context views when another capability asks for it.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/04_run-and-verify.md:81`, `01_workflows/05_debugging.md:23`.

## 2. 数据流 / 机制（设计细节）
### F1. Open Source File From UI

- 机制: canvas double-click, assets selection, or property action opens a skill file in the editor.
- 决策: files remain inspectable/editable even when the graph view is the primary authoring UI.
- 原话/来源: `01_workflows/02_authoring.md:18` includes macro graph editing and micro node editing in one authoring journey.
- 测试: opening the same file focuses the existing tab/state; opening a phase file also selects the relevant node.
- Status: live.
- 归属: capability `file-editing`; regions `editor`, `canvas`, `assets`.

### F2. Autosave With Expected Hash

- 机制: Monaco changes debounce to save; expected hash protects against remote or watcher-driven edits.
- 决策: editing should feel local and low-friction, with explicit conflict recovery instead of silent overwrite.
- 原话/来源: `01_workflows/02_authoring.md:31` keeps compile/lint live while editing; file save must preserve a trustworthy current file.
- 测试: normal autosave updates hash; 409 leaves local content intact and opens resolution UI.
- Status: live through Python API.
- 归属: capability `file-editing`; capability `conflict-overwrite`; platform `native-fs`.

### F3. Read-only Trace Document

- 机制: after run, a human-readable trace document opens in Monaco with editing disabled and navigation to selected node ranges.
- 决策: full trace should be readable, lightly formatted, and not just raw jsonl.
- 原话/来源: `01_workflows/04_run-and-verify.md:81` states the full trace opens in a read-only editor; `01_workflows/04_run-and-verify.md:103` clarifies it must be human-readable.
- 测试: clicking "view full trace" opens read-only editor; node focus jumps to that node's trace range.
- Status: target-design.
- 归属: capability `trace-observability`; region `editor`, `timeline`.

### F4. Writable Context Tamper Editor

- 机制: debug flow can switch the reused Monaco surface from read-only trace context to writable JSON context for downstream resume.
- 决策: PM confirmed editor reuse for context tampering.
- 原话/来源: `01_workflows/05_debugging.md:23` records editor reuse; `01_workflows/05_debugging.md:31` tests context tamper and resume.
- 测试: dot context opens read-only first; enabling tamper allows save; downstream resume uses the modified context.
- Status: target-design.
- 归属: capability `debug-resume`; capability `trace-observability`; region `editor`.

### F5. Inline Compile Diagnostics

- 机制: compile/lint errors map into Monaco gutter and inline markers.
- 决策: compile errors should be shown like an IDE, while the drawer remains the full error list.
- 原话/来源: `01_workflows/03_compile.md:32` lists editor inline marking as one of the three required error locations.
- 测试: an engine error with file/line marks the matching editor line; clearing the error removes the marker.
- Status: target-design.
- 归属: capability `compile-lint`; region `editor`; platform `engine`.

## 3. 接口契约
- Open file shape: path, content, content hash, save mode, and optional read-only reason.
- Save contract: caller supplies expected hash; conflict returns remote content and a resolution choice.
- Native-fs target: all local reads/writes should move behind Rust commands.
- Region links: `editor`, `assets`, `properties`, `timeline`.
- Capability links: `compile-lint`, `conflict-overwrite`, `trace-observability`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- trace/context 文档 = **具名只读 tab**(与正在编辑的文件并列,不临时替换当前编辑器)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| FILE_EDITING-1 | 写路径 | 对齐 `native-rust-writer` 设计单元，保证实现与测试可回扣 |
| FILE_EDITING-2 | autosave | 对齐 `native-rust-writer` 设计单元，保证实现与测试可回扣 |
| FILE_EDITING-3 | 只读 trace | 对齐 `native-rust-writer` 设计单元，保证实现与测试可回扣 |

## 6. 测试关键点
1. 写路径: baseline 现状为 `writeSkillFile` / `handlePhaseFileSave` 走 FastAPI ⚠️；目标为 写盘经 Rust 唯一写者；HTTP 不再直接写本地文件。
2. autosave: baseline 现状为 1500ms debounce + expected hash；目标为 冲突时进入统一 SaveConflict，不静默覆盖。
3. 只读 trace: baseline 现状为 Monaco 支持 readOnly；目标为 trace/doc view 只读，context tamper 另走 debug 流。

## 7. 涉及 region / platform
`editor` · `conflict-overwrite` · `native-fs`

## 8. gaps / 报警
- 🚨 写路径: `writeSkillFile` / `handlePhaseFileSave` 走 FastAPI ⚠️；目标 写盘经 Rust 唯一写者；HTTP 不再直接写本地文件。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `editor` · `conflict-overwrite` · `native-fs`
