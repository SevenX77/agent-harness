# Research: Studio UX & Baseline Integration

> **Status**: Draft v0.1
> **Date**: 2026-05-17
> **Author**: a2 (Gemini)
> **Pattern reference**: VSCode / Cursor / Continue.dev auto-save + file watcher

## 业内参考：Auto-Save 与多端同步

参考 VS Code, Cursor 及 Continue.dev 的主流开发体验：

- **无感保存 (Auto-save)**：VS Code 的 `afterDelay` 模式能在用户暂停思考时将内容持久化至本地（Working Tree 产生改动，非 Git commit）。1500ms 是规避用户输入中途破坏 JSON/YAML 语法完整性的较优防抖阈值。
- **文件监听 (File Watcher)**：现代化 IDE 均具备物理文件系统监听。为防止自回环，需在文件写入系统层进行来源标识过滤（echo filter），一旦检测到外部改动立即触发前端重载；本地有未保存脏缓存时，必须采用类似 VS Code 的 "File modified externally" 弹窗阻断，供用户自行裁决。

## Stash Baseline 现有资产盘点

- **UI 框架体系**：具备完整的 Settings 3-tab 视图、LLM Roles 面板，以及基于 `LazyMonacoPanel` 和 `MonacoPanel` 的独立编辑器封装。
- **布局视图**：已存在 `SplitEditor` 双开结构与 `Workspace.tsx` 页面骨架；`AssetsPanel` 具备完备的左侧文件树能力（包含 `<PanelHeader>`, `<FileRow>`, `<FolderRow>`）。
- **算法核心**：`lib/layout.ts` 内包含手写的 94 行完整 Dagre DAG 布局算法与环检测 (`getAutoLayoutedElements` / `CycleDetectedError`)。
- **后端抽象层**：`core/ports/metadata.py` 具有 71 行的丰富 Ports/Adapters 雏形 (`SkillIndexEntry`, `list_skill_index` 等 12+ 接口)，承载力极大优于 main 分支 (main 仅 33 行)。

## 接口契约：GRAPH.md 作为 SSOT

V2.1 Engine 确立了以 `<skill_id>/GRAPH.md` 为核心的数据真相 (SSOT)，一切 Canvas UI 与文件树仅作为映射视图。后端需全面切换 `compile_skill` / `run_skill` 的输入与回传至 V2.1 签名，并对接新错误类型。

## 为什么弃用 main 分支基线实现

main 分支的 Studio 前端代码强依赖于错误的架构假设。其 `fa451b8` (Multifile Editor) 强行造了一套不兼容的 FileTree、EditorTabs 和 zustand workspace store。由于 Stash 的 AssetsPanel 及 React Context 机制已足够覆盖 V2.1 目录展示需求，强行整合会引发灾难性冲突，必须在 Stash 原生基线上重构 Tier 4 逻辑。
