# multi-file-editor — MVP0 Alignment (多文件编辑器改造对齐方案)

This document specifies the target architecture for split-pane handling, real-workspace directory browsing, and resizable layout interfaces.

---

## 1. Re-aligned Feature Targets

### target 1: Integration of `.workspace` & Outputs in the Tree Browser
* **Design Spec**: Expand the sidebar asset explorer beyond source code files.
  * The backend API scans and includes the internal `.workspace` root directory of the active skill.
  * The frontend `AssetsPanel` maps a dedicated folder node titled **`Workspace Workspace`** in the tree:
    * **`.workspace/runs/`**: User can expand and select past run folders, opening `run_metadata.json`, `final_state.json`, and parsed event trails directly in split text viewers.
    * **`.workspace/runs/latest/artifacts/`**: Exposes physical pipeline results (such as standardized novel chapter drafts).
* **Rationale**: Gives operators immediate visual visibility of running logs and artifact outputs without relying on external system terminal commands.

---

### target 2: Draggable Frosted Resizing Spliter (高阻尼磨砂分屏拖动阻尼器)
* **Design Spec**: 
  * Replace static grid frames with an interactive **Split Handle Component**.
  * A vertical drag-anchor is drawn between the Canvas and the SplitEditor code view:
    * **Styling**: Sleek 4px-wide frosted glass glare with backdrop-blur overlay, changing to vibrant indigo on hover.
    * **Interactions**:
      * Hovering presents a `col-resize` mouse cursor.
      * Left-mouse dragging adjusts canvas vs. code edit percentages.
      * Double-clicking the splitter collapses the split editor, restoring full focus to the graph.
