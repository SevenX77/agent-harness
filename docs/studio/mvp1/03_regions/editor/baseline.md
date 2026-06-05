---
module: 03_regions/editor
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；Monaco autosave live；写文件仍走 FastAPI，trace 只读文档未接，golden 详细 diff 归属曾残留 Properties 口径 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/SplitEditor.tsx:SplitEditor · apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel · apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave · apps/studio/frontend/src/components/TracePanel.tsx:TracePanel
units: [native-rust-writer, trace-dot-blackboard, golden-per-agent-node]
---

# editor — Baseline（当下代码实现逻辑）

> **Scope**: Monaco 编辑区 / split graph context / inline diagnostics / read-only trace document / writable debug context。
> **现状一句话**: Monaco autosave live；写文件仍走 FastAPI，trace 只读文档未接，golden 详细 diff 归属曾残留 Properties 口径 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| SplitEditor | Split editor renders Monaco plus mini GraphCanvas below. | `apps/studio/frontend/src/components/studio/SplitEditor.tsx:SplitEditor（L23）`, `apps/studio/frontend/src/components/studio/SplitEditor.tsx:primaryFile（L77）` |
| Monaco render | LazyMonacoPanel renders editor with file path/content/hash and save settings. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel（L52）` |
| Autosave | On change, editor schedules a 1500ms save. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L165）` |
| Save conflict | Save uses `writeSkillFile` and forwards 409 conflicts. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:saveNow（L99）` |
| Read-only | Monaco options set readOnly when save is disabled. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L217）` |
| Open file source | Workspace opens files from panels/canvas and syncs content/hash. | `apps/studio/frontend/src/components/studio/Workspace.tsx:toOpenFile（L103）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:handleFileOpen（L120）` |
| Phase save | Workspace phase save updates editor and skill detail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave（L159）` |
| Trace doc gap | TracePanel exists separately; it does not open a read-only Monaco document. | `apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| SplitEditor | Split editor renders Monaco plus mini GraphCanvas below. | `apps/studio/frontend/src/components/studio/SplitEditor.tsx:SplitEditor（L23）`, `apps/studio/frontend/src/components/studio/SplitEditor.tsx:primaryFile（L77）` |
| Monaco render | LazyMonacoPanel renders editor with file path/content/hash and save settings. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel（L52）` |
| Autosave | On change, editor schedules a 1500ms save. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L165）` |
| Save conflict | Save uses `writeSkillFile` and forwards 409 conflicts. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:saveNow（L99）` |
| Read-only | Monaco options set readOnly when save is disabled. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L217）` |
| Open file source | Workspace opens files from panels/canvas and syncs content/hash. | `apps/studio/frontend/src/components/studio/Workspace.tsx:toOpenFile（L103）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:handleFileOpen（L120）` |
| Phase save | Workspace phase save updates editor and skill detail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave（L159）` |
| Trace doc gap | TracePanel exists separately; it does not open a read-only Monaco document. | `apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）` |

## 后端功能
N/A。

## 当前边界（editor 现在不是什么）
- 写者 owner 是 `native-fs`，editor 不直接拥有落盘。
- trace/golden 数据流归对应能力，editor 只显示文档/diff。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 写路径 | editor save 仍经 `writeSkillFile` FastAPI ⚠️ | 保存经 Rust 唯一写者/编辑器 buffer 契约 |
| inline diagnostics | compile 字段/行 marker 未接 ⚠️ | Monaco 行内 marker 与 drawer/Properties 同源 |
| golden diff | 旧口径把摘要留 Properties ⚠️ | golden 详细 diff 在 editor，Properties 不承载 golden |
> **验"是否按目标改了"**：1. 写路径；2. inline diagnostics；3. golden diff。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/SplitEditor.tsx:SplitEditor` → `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel` → `apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave` → `apps/studio/frontend/src/components/TracePanel.tsx:TracePanel`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-editor)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `file-editing` · `native-fs` · `trace-observability` · `debug-resume` · `golden-eval`
