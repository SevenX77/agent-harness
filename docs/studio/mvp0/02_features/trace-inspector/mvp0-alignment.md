# trace-visualization — MVP0 Alignment (追踪可视化改造对齐方案)

This document establishes the specifications for real-time debugger panels, theme overrides, and artifacts output configs.

---

## 1. Re-aligned Feature Targets

### target 1: Standalone Debugger & Trace Panel (独立调试与追踪面板)
* **Design Spec**: Segregate static property editing from dynamic runtime tracing.
  * Clicking an **Edge Center Pin** no longer mutates the `PropertiesPanel` sidebar.
  * Instead, it opens a dedicated **Debugger Panel** (or an overlay drawer at the bottom).
  * **Visual Presentation**:
    * **Inputs vs. Outputs Diff**: High-fidelity side-by-side JSON comparison showing value translations.
    * **Active Log Stream**: High-performance scrolling console displaying raw print traces and subagent invocations.

---

### target 2: Responsive Canvas Themes (画布亮暗模式联动)
* **Design Spec**: 
  * The canvas React Flow viewport and grids register listeners to `themeStore.ts` using the external state hook `useThemeValue()`.
  * Grids, backdrops, custom edge SVG path properties (`stroke`, `strokeDasharray`), and node bounding box glowing styles automatically redraw upon theme change.
  * Ensures 100% legibility (no hardcoded dark hex lines on black backgrounds).

---

### target 3: Output Artifacts Path Configurations (输出路径目标绑定)
* **Design Spec**: 
  * In the main Settings panel, a new **Outputs & Artifacts Manager** widget is introduced.
  * Users can configure a custom destination folder for generated outputs (e.g. `/Users/sevenx/Desktop/novel_outputs`).
  * The backend `run_manager.py` respects this setting, executing an atomic write copying all physical segmentation logs and `.md` files out of `.workspace/runs` to the target user path once an execution completes successfully.
