// P-6 (DELIVERY_LEDGER 2026-07-31): the copilot panel tracks the window — its
// width is stored as a share of the canvas host and re-derived on resize,
// clamped to the drag-handle bounds. These tests pin the pure math.
import { describe, expect, it } from 'vitest'
import {
  RIGHT_PANEL_DEFAULT_RATIO,
  RIGHT_PANEL_MAX_WIDTH,
  RIGHT_PANEL_MIN_WIDTH,
  rightPanelRatioFromPx,
  rightPanelWidthPx,
} from './WorkspaceRightPanelOverlay'

describe('rightPanelWidthPx', () => {
  it('keeps the historical 352px default before the host is measured', () => {
    expect(rightPanelWidthPx(RIGHT_PANEL_DEFAULT_RATIO, null)).toBe(352)
    expect(rightPanelWidthPx(RIGHT_PANEL_DEFAULT_RATIO, 0)).toBe(352)
  })

  it('scales with the host width at the same ratio', () => {
    expect(rightPanelWidthPx(RIGHT_PANEL_DEFAULT_RATIO, 2000)).toBe(550)
    expect(rightPanelWidthPx(RIGHT_PANEL_DEFAULT_RATIO, 1280)).toBe(352)
  })

  it('clamps to the drag-handle minimum on narrow hosts', () => {
    expect(rightPanelWidthPx(RIGHT_PANEL_DEFAULT_RATIO, 600)).toBe(RIGHT_PANEL_MIN_WIDTH)
  })

  it('clamps to the drag-handle maximum on very wide hosts', () => {
    expect(rightPanelWidthPx(RIGHT_PANEL_DEFAULT_RATIO, 4000)).toBe(RIGHT_PANEL_MAX_WIDTH)
  })
})

describe('rightPanelRatioFromPx', () => {
  it('round-trips a drag size within the clamp bounds', () => {
    const hostWidth = 1600
    const dragged = 500
    const ratio = rightPanelRatioFromPx(dragged, hostWidth)
    expect(rightPanelWidthPx(ratio, hostWidth)).toBe(dragged)
  })

  it('falls back to the reference host when unmeasured', () => {
    // 352px against the 1280px reference host = the default ratio.
    expect(rightPanelRatioFromPx(352, null)).toBeCloseTo(RIGHT_PANEL_DEFAULT_RATIO)
  })
})
