export interface Point {
  x: number
  y: number
}

export interface Size {
  width: number
  height: number
}

/** Diameter of the FAB in px (kept small — PM: "圆不要那么大"). */
export const FAB_SIZE = 36
/** Gap the FAB keeps from the canvas edges. */
export const FAB_MARGIN = 12

// The copilot panel docks at top-3/right-3 with a px-4/py-3 header; the MoirAI
// mark sits at the header's start. These mirror those layout constants so the
// FAB can fly to exactly where the header logo will appear.
const PANEL_MARGIN = 12
const HEADER_PAD_X = 16
const HEADER_PAD_Y = 13
const LOGO_SIZE = 18

/** Top-right default anchor (PM: "button 默认放在右上方"). */
export function defaultFabPosition(bounds: Size, fabSize = FAB_SIZE, margin = FAB_MARGIN): Point {
  return { x: Math.max(margin, bounds.width - fabSize - margin), y: margin }
}

/** Clamp a position so the FAB stays fully inside the canvas, margin included. */
export function clampFabPosition(pos: Point, bounds: Size, fabSize = FAB_SIZE, margin = FAB_MARGIN): Point {
  const maxX = Math.max(margin, bounds.width - fabSize - margin)
  const maxY = Math.max(margin, bounds.height - fabSize - margin)
  return {
    x: Math.min(Math.max(pos.x, margin), maxX),
    y: Math.min(Math.max(pos.y, margin), maxY),
  }
}

/**
 * Where the FAB should land so it overlays the panel header logo — the FAB's
 * top-left, centred on the logo. Used as the end of the open-travel path.
 */
export function headerLogoTarget(bounds: Size, panelWidth: number, fabSize = FAB_SIZE): Point {
  const logoCenterX = bounds.width - PANEL_MARGIN - panelWidth + HEADER_PAD_X + LOGO_SIZE / 2
  const logoCenterY = PANEL_MARGIN + HEADER_PAD_Y + LOGO_SIZE / 2
  return { x: logoCenterX - fabSize / 2, y: logoCenterY - fabSize / 2 }
}

/**
 * The L-shaped open path (PM: "先垂直往上跑，再水平跑到 panel 上 logo 的位置"):
 * start → straight up/down to the target row → straight across to the target.
 */
export function travelSteps(from: Point, to: Point): Point[] {
  return [
    { x: from.x, y: from.y },
    { x: from.x, y: to.y },
    { x: to.x, y: to.y },
  ]
}

/** True when a pointer down→up barely moved, i.e. a tap (open) not a drag. */
export function isTapGesture(start: Point, end: Point, threshold = 4): boolean {
  return Math.abs(end.x - start.x) <= threshold && Math.abs(end.y - start.y) <= threshold
}

export interface Rect {
  left: number
  top: number
  width: number
  height: number
}

/**
 * The fully-expanded copilot panel rect (docks top-3 / right-3 / bottom-3). The
 * open animation grows the FAB circle into exactly this box (container transform),
 * so the circle literally becomes the panel rather than cross-fading.
 */
export function panelRect(bounds: Size, panelWidth: number, margin = PANEL_MARGIN): Rect {
  return {
    left: bounds.width - panelWidth - margin,
    top: margin,
    width: panelWidth,
    height: Math.max(0, bounds.height - margin * 2),
  }
}
