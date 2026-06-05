---
module: 03_regions/assets
doc: baseline
status: drafted（现状对齐 pinned 代码 0d9fbaf；文件树 live；subgraph 检测仍读旧 `mode/target_skill/sub_skill_ref`，且有本地假缓存/假 fallback 行 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetsPanel · apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels
units: [subgraph-path-inline-drilldown]
---

# assets — Baseline（当下代码实现逻辑）

> **Scope**: 左侧 Assets 面板的文件树、未解析子图提示、子图文件夹加入工作区与选中节点上下文。
> **现状一句话**: 文件树 live；subgraph 检测仍读旧 `mode/target_skill/sub_skill_ref`，且有本地假缓存/假 fallback 行 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| File tree | Assets builds a nested tree from `skillDetail.files`. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:buildAssetTree（L37）` |
| File open | File rows call workspace `onFileOpen`. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetTreeRows（L69）`, `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetsPanel（L88）` |
| Subgraph detection | Subgraphs are detected from old `mode`, `target_skill`, or `sub_skill_ref` fields. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:subgraphs（L95）` |
| Fake cache | Registered subgraphs are seeded from a local hardcoded cache. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:registeredSubgraphsCache（L86）` |
| Fake fallback rows | If no subgraphs exist, the panel displays hardcoded classifier/translation rows. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:displaySubgraphs（L120）` |
| Register action | Register picks a directory or browser fallback path, then only updates local cache/toast. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:handleRegisterSubgraph（L140）` |
| Panel routing | Panels routes active `assets` to `AssetsPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L31）` |

## 前端逻辑
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| File tree | Assets builds a nested tree from `skillDetail.files`. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:buildAssetTree（L37）` |
| File open | File rows call workspace `onFileOpen`. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetTreeRows（L69）`, `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetsPanel（L88）` |
| Subgraph detection | Subgraphs are detected from old `mode`, `target_skill`, or `sub_skill_ref` fields. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:subgraphs（L95）` |
| Fake cache | Registered subgraphs are seeded from a local hardcoded cache. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:registeredSubgraphsCache（L86）` |
| Fake fallback rows | If no subgraphs exist, the panel displays hardcoded classifier/translation rows. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:displaySubgraphs（L120）` |
| Register action | Register picks a directory or browser fallback path, then only updates local cache/toast. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:handleRegisterSubgraph（L140）` |
| Panel routing | Panels routes active `assets` to `AssetsPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels（L31）` |

## 后端功能
N/A。

## 当前边界（assets 现在不是什么）
- 不拥有 path 解析语义；resolver/path contract 引 engine。
- 不拥有 workspace MRU；加入工作区走 `skill-workspace`。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 子图检测 | `AssetsPanel` 仍读旧 `mode/target_skill/sub_skill_ref` ⚠️ | 按 engine MVP1 绝对 `path` 与 resolver 状态显示 |
| 假数据 | 本地 hardcoded cache / classifier fallback 行 ⚠️ | 无真实子图时显示空态，不造假行 |
| 加入工作区 | Register 只更新 local cache/toast ⚠️ | 触发 Open Folder/MRU/native-fs 路径并保留冲突反馈 |
> **验"是否按目标改了"**：1. 子图检测；2. 假数据；3. 加入工作区。

## 读代码主路径提示
`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetsPanel` → `apps/studio/frontend/src/components/studio/panels/Panels.tsx:Panels`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#03-regions-assets)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `graph-authoring` · `canvas` · `skill-workspace` · `native-fs` · `engine` resolver/skill-syntax
