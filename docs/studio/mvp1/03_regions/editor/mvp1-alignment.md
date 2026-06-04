# editor MVP1 Alignment

## 定义

`editor` owns the Monaco-based file and virtual-document surface: editable skill files, split graph view, read-only trace documents, writable debug context tamper documents, and inline diagnostics.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/04_run-and-verify.md:81`, `01_workflows/05_debugging.md:19`.

## 接口契约

- Inputs: open file or virtual document descriptor, save enabled flag, expected hash, diagnostics.
- Outputs: content save, conflict event, cursor/jump target.
- Capability links: `file-editing`, `phase-editing`, `compile-lint`, `trace-observability`, `debug-resume`.

## F1. Editable Source Files

- 机制: open `.md`/allowed files, autosave edits with expected hash, and update workspace state.
- 决策: source remains available beside visual authoring.
- 原话/来源: `01_workflows/02_authoring.md:18` keeps file editing within authoring.
- 测试: autosave writes content; hash updates; conflict path prevents silent overwrite.
- Status: live.
- 归属: region `editor`; capability `file-editing`.

## F2. Split Graph Context

- 机制: when a file is open, keep a compact graph below/alongside editor context;**编辑器与图之间有一条可拖拽 handle(分隔条),用户自调两侧大小**。
- 决策: editing should not detach the user from graph structure;分屏比例由用户用 handle 自调(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:18` pairs graph and micro node editing.
- 测试: selected node remains visible; mini graph selection opens the matching file.
- Status: live.
- 归属: region `editor`; region `canvas`.

## F3. Inline Diagnostics

- 机制: compile errors mark editor lines/gutter like IDE diagnostics.
- 决策: error location should appear where the fix happens.
- 原话/来源: `01_workflows/03_compile.md:17` and `01_workflows/03_compile.md:34` define IDE-style editor errors.
- 测试: file/line engine errors create Monaco markers; markers clear on pass.
- Status: target-design.
- 归属: region `editor`; capability `compile-lint`.

## F4. Read-only Trace Document

- 机制: full trace opens as a formatted read-only virtual document and can jump to node ranges.
- 决策: trace document must be human-readable.
- 原话/来源: `01_workflows/04_run-and-verify.md:81` defines editor opening; `01_workflows/04_run-and-verify.md:104` says it is not raw jsonl.
- 测试: virtual tab is read-only; focus node jumps to that node section; long payloads are truncated with expand affordance.
- Status: target-design.
- 归属: region `editor`; capability `trace-observability`.

## F5. Writable Debug Context

- 机制: dot context can switch from read-only to writable JSON for context tamper, then save into a resume request.
- 决策: PM confirmed editor reuse.
- 原话/来源: `01_workflows/05_debugging.md:19` and `01_workflows/05_debugging.md:24` define the reuse.
- 测试: saved edited context is passed to downstream resume; original trace remains available read-only.
- Status: target-design.
- 归属: region `editor`; capability `debug-resume`.

## 已决(PM 2026-06-04)

- 虚拟 trace/context 文档 = **具名只读 tab**(与正在编辑的文件并列,不临时替换当前编辑器)。
- **golden 详细 diff 也在编辑器分屏里看**(Monaco diff 文档,实际 vs golden)——做分屏就是为了看 diff;Properties 只留字段级摘要(见 `properties` F4)。
