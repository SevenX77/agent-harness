---
module: 02_capabilities/file-editing
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；Monaco 编辑与 FastAPI 写文件 live；MVP1 D12 要求 Rust 唯一写者，当前写路径仍走 FastAPI ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave · apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel · apps/studio/frontend/src/api/client.ts:writeSkillFile · apps/studio/backend/app/services/skills.py:update_skill_file
units: [native-rust-writer]
---

# file-editing — Baseline（当下代码实现逻辑）

> **Scope**: Studio 打开、编辑、autosave、冲突处理与只读/可写编辑面的文件编辑能力。
> **现状一句话**: Monaco 编辑与 FastAPI 写文件 live；MVP1 D12 要求 Rust 唯一写者，当前写路径仍走 FastAPI ⚠️。

## UI/UX
Studio 打开、编辑、autosave、冲突处理与只读/可写编辑面的文件编辑能力。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Open file model | Workspace converts a skill file into an `OpenFile` with path/content/hash. | `apps/studio/frontend/src/components/studio/Workspace.tsx:toOpenFile（L103）` |
| File open | Workspace opens a file, focuses editor, and closes settings overlay. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handleFileOpen（L120）` |
| Phase save | Phase file save writes through `writeSkillFile`, updates open editor and skill detail, then clears conflict state. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave（L159）` |
| Monaco panel | `LazyMonacoPanel` renders the editor and receives skill/file/hash/save settings. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel（L52）` |
| Autosave | Editor changes debounce into save after 1500ms. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L165）` |
| Conflict | Save catches 409 conflicts and delegates to `onConflict`. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:saveNow（L99）` |
| Read-only flag | Monaco respects `readOnly: !saveEnabled`. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L217）` |
| Split view | Split editor combines Monaco with a mini graph canvas. | `apps/studio/frontend/src/components/studio/SplitEditor.tsx:primaryFile（L77）` |
| File tree source | Assets/file panels render from `skillDetail.files`. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:buildAssetTree（L37）`, `apps/studio/frontend/src/components/studio/panels/panel-files.ts:manifestFiles（L37）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend write | Single file write validates suffix/path and records API writes. | `apps/studio/backend/app/services/skills.py:update_skill_file（L410）` |

## 当前边界（file-editing 现在不是什么）
- 不拥有 Rust 写者实现；owner 是 `native-fs`。
- 不拥有冲突决策 UI；冲突面归 `conflict-overwrite`。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 写路径 | `writeSkillFile` / `handlePhaseFileSave` 走 FastAPI ⚠️ | 写盘经 Rust 唯一写者；HTTP 不再直接写本地文件 |
| autosave | 1500ms debounce + expected hash | 冲突时进入统一 SaveConflict，不静默覆盖 |
| 只读 trace | Monaco 支持 readOnly | trace/doc view 只读，context tamper 另走 debug 流 |
> **验"是否按目标改了"**：1. 写路径；2. autosave；3. 只读 trace。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/Workspace.tsx:handlePhaseFileSave` → `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel` → `apps/studio/frontend/src/api/client.ts:writeSkillFile` → `apps/studio/backend/app/services/skills.py:update_skill_file`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-file-editing)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `editor` · `conflict-overwrite` · `native-fs`
