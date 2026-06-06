---
module: 02_capabilities/conflict-overwrite
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；顺序覆盖与文件保存冲突都有实现痕迹，但还是两套 UX，没有统一冲突呈现 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:checkSequentialOverwrites · apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas · apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel · apps/studio/backend/app/services/skills.py:update_skill_file
units: [conflict-overwrite-resolution]
---

# conflict-overwrite — Baseline（当下代码实现逻辑）

> **Scope**: 文件保存冲突与顺序输出覆盖的用户可见冲突处理。
> **现状一句话**: 顺序覆盖与文件保存冲突都有实现痕迹，但还是两套 UX，没有统一冲突呈现 ⚠️。

## UI/UX
文件保存冲突与顺序输出覆盖的用户可见冲突处理。 当前在 UI 上的可见入口、提示、面板或状态详见下方前端证据；带 ⚠️ 的项是已验真的 code↔design drift。

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Sequential overwrite scan | Canvas scans graph phases for sequential output overwrites and stores a pending conflict. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:canvasRef（L104）`, `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:checkSequentialOverwrites（L237）` |
| Allow overwrite | Confirming adds `allow_sequential_overwrite` to the phase file and saves it. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:handleAllowSequentialOverwrite（L134）`, `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:addSequentialOverwriteField（L339）` |
| Cancel overwrite | Canceling marks the conflicting node red locally. | `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:handleCancelWarning（L168）` |
| Node popover | Skill node can show sequential overwrite warning and allow/cancel actions. | `apps/studio/frontend/src/components/nodes/SkillNode.tsx:nodeContent（L136）` |
| File conflict | Workspace stores save conflicts and offers use-remote/view-diff style handlers. | `apps/studio/frontend/src/components/studio/Workspace.tsx:handleUseRemote（L264）` |
| Save conflict source | `LazyMonacoPanel` detects 409 response and passes conflict payload to Workspace. | `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:saveNow（L99）` |

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Backend write guard | Backend single-file write checks expected content hash and raises conflict on mismatch. | `apps/studio/backend/app/services/skills.py:update_skill_file（L410）` |
| Graph write guard | Graph serialization also returns 409 on stale writes. | `apps/studio/backend/app/routers/skills.py:compile_skill_endpoint_endpoint（L122）` |

## 当前边界（conflict-overwrite 现在不是什么）
- 不拥有通用文件写者；写盘归 `native-fs` / 文件编辑链路。
- 不拥有 graph 语义校验，只负责冲突 UX 与用户决策。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 冲突呈现 | 文件冲突与顺序覆盖是两条 UI 路径 ⚠️ | 共享一个冲突面：diff/use-remote/keep-local/allow overwrite 语义清楚 |
| 顺序覆盖 | 可标红并写 `allow_sequential_overwrite` | 不得静默覆盖；允许后写入显式标记 |
| 保存冲突 | 409 payload 传给 Workspace | 冲突决策后按同一路径重试/取消 |
> **验"是否按目标改了"**：1. 冲突呈现；2. 顺序覆盖；3. 保存冲突。

## 读代码主路径提示
`apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:checkSequentialOverwrites` → `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:GraphCanvas` → `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:LazyMonacoPanel` → `apps/studio/backend/app/services/skills.py:update_skill_file`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#02-capabilities-conflict-overwrite)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `canvas` · `editor` · `file-editing`
