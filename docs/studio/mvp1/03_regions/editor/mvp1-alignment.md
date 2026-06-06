---
module: 03_regions/editor
doc: mvp1-alignment
status: FROZEN（Monaco autosave live；写文件仍走 FastAPI，trace 只读文档未接，golden 详细 diff 归属曾残留 Properties 口径 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [native-rust-writer, trace-dot-blackboard, golden-per-agent-node]
aligns_with: 01_workflows/02_authoring.md（editor）· 01_workflows/04_run-and-verify.md（trace/golden diff）
---

# editor — MVP1 Alignment

> **Tier**: region | **Owns**: 编辑 region 的文件编辑显示切面；消费 `native-rust-writer`、`trace-dot-blackboard`、`golden-per-agent-node` 的 editor 落点 | **现状**: Monaco autosave live；写文件仍走 FastAPI，trace 只读文档未接，golden 详细 diff 归属曾残留 Properties 口径 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `file-editing` · `native-fs` · `trace-observability` · `debug-resume` · `golden-eval`

## 1. 定义
`editor` owns the Monaco-based file and virtual-document surface: editable skill files, split graph view, read-only trace documents, writable debug context tamper documents, and inline diagnostics.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/04_run-and-verify.md:81`, `01_workflows/05_debugging.md:19`.

## 2. 数据流 / 机制（设计细节）
### F1. Editable Source Files

- 机制: open `.md`/allowed files, autosave edits with expected hash, and update workspace state.
- 决策: source remains available beside visual authoring.
- 原话/来源: `01_workflows/02_authoring.md:18` keeps file editing within authoring.
- 测试: autosave writes content; hash updates; conflict path prevents silent overwrite.
- Status: live.
- 归属: region `editor`; capability `file-editing`.

### F2. Split Graph Context

- 机制: when a file is open, keep a compact graph below/alongside editor context;**编辑器与图之间有一条可拖拽 handle(分隔条),用户自调两侧大小**。
- 决策: editing should not detach the user from graph structure;分屏比例由用户用 handle 自调(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:18` pairs graph and micro node editing.
- 测试: selected node remains visible; mini graph selection opens the matching file.
- Status: live.
- 归属: region `editor`; region `canvas`.

### F3. Inline Diagnostics

- 机制: compile errors mark editor lines/gutter like IDE diagnostics.
- 决策: error location should appear where the fix happens.
- 原话/来源: `01_workflows/03_compile.md:17` and `01_workflows/03_compile.md:34` define IDE-style editor errors.
- 测试: file/line engine errors create Monaco markers; markers clear on pass.
- Status: target-design.
- 归属: region `editor`; capability `compile-lint`.

### F4. Read-only Trace Document

- 机制: full trace opens as a formatted read-only virtual document and can jump to node ranges.
- 决策: trace document must be human-readable.
- 原话/来源: `01_workflows/04_run-and-verify.md:81` defines editor opening; `01_workflows/04_run-and-verify.md:104` says it is not raw jsonl.
- 测试: virtual tab is read-only; focus node jumps to that node section; long payloads are truncated with expand affordance.
- Status: target-design.
- 归属: region `editor`; capability `trace-observability`.

### F5. Writable Debug Context

- 机制: dot context can switch from read-only to writable JSON for context tamper, then save into a resume request.
- 决策: PM confirmed editor reuse.
- 原话/来源: `01_workflows/05_debugging.md:19` and `01_workflows/05_debugging.md:24` define the reuse.
- 测试: saved edited context is passed to downstream resume; original trace remains available read-only.
- Status: target-design.
- 归属: region `editor`; capability `debug-resume`.

## 3. 接口契约
- Inputs: open file or virtual document descriptor, save enabled flag, expected hash, diagnostics.
- Outputs: content save, conflict event, cursor/jump target.
- Capability links: `file-editing`, `phase-editing`, `compile-lint`, `trace-observability`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- 虚拟 trace/context 文档 = **具名只读 tab**(与正在编辑的文件并列,不临时替换当前编辑器)。
- **golden 详细 diff 也在编辑器分屏里看**(Monaco diff 文档,实际 vs golden)——做分屏就是为了看 diff;**golden 完全不在 Properties**(入口归 I/O output + Assets,见 `properties` 已决 / `input` F)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| EDITOR-1 | 写路径 | 单元 `native-rust-writer`（消费；owner=native-fs）；**为什么**：editor save 走 Rust 唯一写者(D12) |
| EDITOR-2 | inline diagnostics | 单元 `compile-lint-structured-error`（消费；owner=compile-lint）；**为什么**：Monaco 行内编译诊断标记，错误语义归 compile-lint，非写者 |
| EDITOR-3 | golden diff | 单元 `golden-per-agent-node`；**为什么**：编辑器分屏看 golden 完整 diff(Monaco diff)，是 golden 详细 diff 的落点 |

## 6. 测试关键点
1. 写路径: baseline 现状为 editor save 仍经 `writeSkillFile` FastAPI ⚠️；目标为 保存经 Rust 唯一写者/编辑器 buffer 契约。
2. inline diagnostics: baseline 现状为 compile 字段/行 marker 未接 ⚠️；目标为 Monaco 行内 marker 与 drawer/Properties 同源。
3. golden diff: baseline 现状为 旧口径把摘要留 Properties ⚠️；目标为 golden 详细 diff 在 editor，Properties 不承载 golden。

## 7. 涉及 region / platform
`file-editing` · `native-fs` · `trace-observability` · `debug-resume` · `golden-eval`

## 8. gaps / 报警
- 🚨 写路径: editor save 仍经 `writeSkillFile` FastAPI ⚠️；目标 保存经 Rust 唯一写者/编辑器 buffer 契约。
- 🚨 inline diagnostics: compile 字段/行 marker 未接 ⚠️；目标 Monaco 行内 marker 与 drawer/Properties 同源。
- 🚨 golden diff: 旧口径把摘要留 Properties ⚠️；目标 golden 详细 diff 在 editor，Properties 不承载 golden。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `file-editing` · `native-fs` · `trace-observability` · `debug-resume` · `golden-eval`
