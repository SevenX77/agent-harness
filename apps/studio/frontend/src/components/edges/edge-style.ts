// Shared edge styling (decision 2026-08-13 D8): stroke geometry and color
// tokens for canvas connections live here, once. buildEdges was overriding
// ContextEdge's own base width through the style prop, so the "real" width
// existed in two files that had to agree by luck.

export const EDGE_STROKE_WIDTH = 1.5
export const EDGE_DOT_RADIUS = 7

export const EDGE_STROKE_BASE = 'var(--studio-canvas-edge, var(--color-border))'
export const EDGE_STROKE_ACCENT = 'var(--studio-canvas-accent, var(--primary))'

/**
 * How wide the invisible hit path around an edge is. React Flow's own default
 * is 20; the line itself is 1.5px, which is a target nobody can hit on purpose
 * (canvas design F6: "整条线可点,不只中点那颗 dot").
 */
export const EDGE_INTERACTION_WIDTH = 20

/**
 * What each edge run state is drawn in (canvas design F6). `idle` has no accent
 * layer at all — the base line is the whole drawing — so it is absent here
 * rather than mapped to a transparent stroke.
 */
export const EDGE_RUN_STATUS_STROKE: Readonly<Record<'running' | 'done' | 'failed' | 'paused', string>> = {
  running: EDGE_STROKE_ACCENT,
  done: EDGE_STROKE_ACCENT,
  failed: 'var(--studio-canvas-edge-failed, var(--destructive))',
  paused: 'var(--studio-canvas-edge-paused, var(--warning))',
}
