/**
 * Pure drill-down focus-stack logic for the subgraph in-place navigation (R9).
 *
 * The canvas keeps a LOCAL stack of subgraph levels the user has drilled into.
 * An empty stack means the root skill graph is shown (unchanged behaviour); a
 * non-empty stack means the canvas focuses INTO the child graph identified by
 * the top entry's absolute `path`, while the breadcrumb renders the full
 * root → child → … trail with each level clickable to pop back to it.
 *
 * Kept side-effect free (no React, no fetching) so the push/pop/pop-to-level
 * transitions are unit-testable in isolation.
 */

/** One drilled subgraph level: the absolute child-graph `path` plus its label. */
export interface DrillLevel {
  /** Absolute child-graph path consumed by the subgraph resolver. */
  path: string
  /** Human-readable label for the breadcrumb (the subgraph node's label). */
  label: string
}

export type DrillStack = readonly DrillLevel[]

export type DrillStackAction =
  /** Drill INTO a subgraph node, pushing a new level onto the stack. */
  | { type: 'push'; level: DrillLevel }
  /** Pop one level (go up a single step). No-op on an empty stack. */
  | { type: 'pop' }
  /**
   * Pop back to a breadcrumb index. `index === -1` (or any value < 0) returns
   * to the root graph (empty stack). `index >= length` is a no-op. Otherwise
   * the stack is truncated so `index` becomes the new top.
   */
  | { type: 'popTo'; index: number }
  /** Clear all drilled levels, returning to the root graph. */
  | { type: 'reset' }

/**
 * Reducer for the drill stack. Returns the SAME reference when an action would
 * not change the stack, so callers relying on identity (React state) avoid
 * needless re-renders.
 */
export function drillStackReducer(stack: DrillStack, action: DrillStackAction): DrillStack {
  if (action.type === 'push') {
    return [...stack, action.level]
  }
  if (action.type === 'pop') {
    if (stack.length === 0) return stack
    return stack.slice(0, -1)
  }
  if (action.type === 'popTo') {
    if (action.index < 0) {
      return stack.length === 0 ? stack : []
    }
    // Popping to the current top (index === length-1) or beyond changes
    // nothing — return the same reference so React skips the re-render.
    if (action.index >= stack.length - 1) {
      return stack
    }
    return stack.slice(0, action.index + 1)
  }
  // reset
  return stack.length === 0 ? stack : []
}

/** A breadcrumb entry. `index === -1` is the synthetic root level. */
export interface BreadcrumbItem {
  /** -1 for root, otherwise the drilled level's index in the stack. */
  index: number
  label: string
  /** True for the deepest (currently-focused) level — not clickable. */
  isCurrent: boolean
}

/**
 * Build the breadcrumb trail for a drill stack: root → level0 → level1 → …
 * The root is always present and clickable (pops to root) unless the stack is
 * empty, in which case root is the current level. The deepest level is marked
 * `isCurrent` so the UI can render it inert.
 */
export function breadcrumbItems(stack: DrillStack, rootLabel: string): BreadcrumbItem[] {
  const root: BreadcrumbItem = {
    index: -1,
    label: rootLabel,
    isCurrent: stack.length === 0,
  }
  const levels = stack.map((level, index) => ({
    index,
    label: level.label,
    isCurrent: index === stack.length - 1,
  }))
  return [root, ...levels]
}

/** The currently-focused level, or null when at the root. */
export function currentLevel(stack: DrillStack): DrillLevel | null {
  return stack.length === 0 ? null : stack[stack.length - 1]
}
