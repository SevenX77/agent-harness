// Shared edge styling (decision 2026-08-13 D8): stroke geometry and color
// tokens for canvas connections live here, once. buildEdges was overriding
// ContextEdge's own base width through the style prop, so the "real" width
// existed in two files that had to agree by luck.

export const EDGE_STROKE_WIDTH = 1.5
export const EDGE_DOT_RADIUS = 7

export const EDGE_STROKE_BASE = 'var(--studio-canvas-edge, var(--color-border))'
export const EDGE_STROKE_ACCENT = 'var(--studio-canvas-accent, var(--primary))'
