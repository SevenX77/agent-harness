---
module: 03_regions/shell-layout
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；Workspace shell live；RuntimeGate 仍可全屏 gate，copilot prop 用 outer skillId 有下钻风险 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace · apps/studio/frontend/src/components/studio/Header.tsx:Header · apps/studio/frontend/src/components/studio/Toolbar.tsx:Toolbar · apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels · apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate
units: [shell-runtime-gate]
---

# shell-layout — Baseline（当下代码实现逻辑）

> **Scope**: Studio IDE shell：header、toolbar、left/center/right slots、settings overlay、copilot slot 与 sidecar/runtime gate。
> **现状一句话**: Workspace shell live；RuntimeGate 仍可全屏 gate，copilot prop 用 outer skillId 有下钻风险 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Workspace state | Workspace owns current panels, copilot open state, selected node/edge, compile state, and open editor files. | `apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace（L39）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentSkillId（L55）` |
| Enter/clear skill | Skill id changes reset panels/nav/copilot and default a skill to Assets + Copilot open. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentSkillId（L44）` |
| Header | Header renders Back Home, breadcrumb stack, Team menu, and Copilot toggle. | `apps/studio/frontend/src/components/studio/Header.tsx:prTitle（L56）`, `apps/studio/frontend/src/components/studio/Header.tsx:prTitle（L98）` |
| Toolbar | Toolbar owns left panel mode buttons and Settings entry. | `apps/studio/frontend/src/components/studio/Toolbar.tsx:Toolbar（L7）`, `apps/studio/frontend/src/components/studio/Toolbar.tsx:isActive（L80）` |
| Panel slot | Workspace mounts `Panels` in a resizable left panel when activePanel exists. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L474）`, `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L20）` |
| Center slot | Center switches between Settings, SplitEditor, Welcome, and GraphCanvas. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L494）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L512）` |
| Copilot slot | Copilot panel opens as a right resizable panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L545）` |
| Copilot prop issue | Copilot receives outer `skillId` prop instead of `currentSkillId`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L554）` |
| Runtime gate | RuntimeGate initializes app config and shows loading/error/children. | `apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate（L8）`, `apps/studio/frontend/src/components/RuntimeGate.tsx:cancelled（L31）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Workspace state | Workspace owns current panels, copilot open state, selected node/edge, compile state, and open editor files. | `apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace（L39）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentSkillId（L55）` |
| Enter/clear skill | Skill id changes reset panels/nav/copilot and default a skill to Assets + Copilot open. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentSkillId（L44）` |
| Header | Header renders Back Home, breadcrumb stack, Team menu, and Copilot toggle. | `apps/studio/frontend/src/components/studio/Header.tsx:prTitle（L56）`, `apps/studio/frontend/src/components/studio/Header.tsx:prTitle（L98）` |
| Toolbar | Toolbar owns left panel mode buttons and Settings entry. | `apps/studio/frontend/src/components/studio/Toolbar.tsx:Toolbar（L7）`, `apps/studio/frontend/src/components/studio/Toolbar.tsx:isActive（L80）` |
| Panel slot | Workspace mounts `Panels` in a resizable left panel when activePanel exists. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L474）`, `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L20）` |
| Center slot | Center switches between Settings, SplitEditor, Welcome, and GraphCanvas. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L494）`, `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L512）` |
| Copilot slot | Copilot panel opens as a right resizable panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L545）` |
| Copilot prop issue | Copilot receives outer `skillId` prop instead of `currentSkillId`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L554）` |
| Runtime gate | RuntimeGate initializes app config and shows loading/error/children. | `apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate（L8）`, `apps/studio/frontend/src/components/RuntimeGate.tsx:cancelled（L31）` |

## 后端功能
N/A。

## 当前边界（shell-layout 现在不是什么）
- 不拥有各 panel 业务逻辑，只拥有槽位/导航/生命周期。
- sidecar 生命周期资源归 Tauri/platform，shell 显示状态。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| runtime gate | RuntimeGate 全屏 loading/error gate ⚠️ | shell 即时渲染，sidecar 状态局部呈现 |
| copilot slot | CopilotPanel 接 outer `skillId` ⚠️ | 下钻时用 currentSkillId，slots 不丢状态 |
| settings overlay | Settings 在 center slot 覆盖 | Settings 不卸载 copilot，不阻塞壳 |
> **验"是否按目标改了"**：1. runtime gate；2. copilot slot；3. settings overlay。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/Workspace.tsx:Workspace` → `apps/studio/frontend/src/components/studio/Header.tsx:Header` → `apps/studio/frontend/src/components/studio/Toolbar.tsx:Toolbar` → `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels` → `apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-shell-layout)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `welcome` · `settings` · `copilot` · `skill-workspace` · `state-engine`
