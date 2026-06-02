# multi-file-editor — Baseline (多文件编辑器基线对齐文档)

> **Status**: Completed (Aligned with V0.3.0)
> **Scope**: Focus Linking, Split Editor Panes, Sidebar File Browsing, Monaco Panel Integrations

---

## 1. Core Codebase Structures

The multi-file workspace and code views are driven by:

### Key Components
* **[Workspace.tsx](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend/src/components/studio/Workspace.tsx)**: Global container managing active tabs, left/right file views, compile calls, and panels split states.
* **[SplitEditor.tsx](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend/src/components/studio/SplitEditor.tsx)**: Visual grid displaying twin file editor tabs.
* **[AssetsPanel.tsx](file:///Users/sevenx/Documents/coding/agent-harness/apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx)**: Builds file and tree row items using `skillDetail.files`.

---

## 2. In-Code Editor Ingestion Flows

When a skill workspace launches:
1. The backend parses file content, delivering it to the client via `/api/skills/{skill_id}` into a flat string-dictionary `skillDetail.files`.
2. The `AssetsPanel` recursively parses path segments, constructing an in-memory `AssetTreeNode` (e.g. mapping `phases/phase1/LOGIC.md` to folders).
3. Monaco editor panels fetch content directly from these dictionary keys.

### Identified Logical Gaps
* **Lack of Workspace Runs Exposure**: The file browser in the sidebar *only* scans keys explicitly returned inside the skill's file record. The underlying physical `.workspace` directory, including execution `runs/` and output `artifacts/`, is completely hidden from the tree.
* **Rigid Split Grid**: The canvas and twin code panels split is toggled via a binary flag. There is no draggable splitter handler on the UI, locking the viewport ratio.
