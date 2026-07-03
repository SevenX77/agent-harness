import { describe, expect, it } from 'vitest'
import {
  clampFabPosition,
  defaultFabPosition,
  FAB_MARGIN,
  FAB_SIZE,
  headerLogoTarget,
  isTapGesture,
  panelRect,
  travelSteps,
} from './copilot-fab-geometry'

const bounds = { width: 1000, height: 600 }

describe('defaultFabPosition', () => {
  it('anchors the FAB to the top-right corner inside the margin', () => {
    const p = defaultFabPosition(bounds)
    expect(p).toEqual({ x: 1000 - FAB_SIZE - FAB_MARGIN, y: FAB_MARGIN })
  })

  it('never goes negative on a tiny canvas', () => {
    const p = defaultFabPosition({ width: 20, height: 20 })
    expect(p.x).toBeGreaterThanOrEqual(FAB_MARGIN)
    expect(p.y).toBe(FAB_MARGIN)
  })
})

describe('clampFabPosition', () => {
  it('keeps the FAB fully inside the canvas with its margin', () => {
    expect(clampFabPosition({ x: -50, y: -50 }, bounds)).toEqual({ x: FAB_MARGIN, y: FAB_MARGIN })
    const maxX = bounds.width - FAB_SIZE - FAB_MARGIN
    const maxY = bounds.height - FAB_SIZE - FAB_MARGIN
    expect(clampFabPosition({ x: 9999, y: 9999 }, bounds)).toEqual({ x: maxX, y: maxY })
  })

  it('leaves an in-bounds position untouched', () => {
    expect(clampFabPosition({ x: 400, y: 200 }, bounds)).toEqual({ x: 400, y: 200 })
  })
})

describe('headerLogoTarget', () => {
  it('lands at the panel header logo — just inside the panel left edge, near the top', () => {
    const panelWidth = 360
    const t = headerLogoTarget(bounds, panelWidth)
    const panelLeft = bounds.width - panelWidth - FAB_MARGIN // ~= panel's left edge
    // The logo sits at the panel's start (left), so the FAB lands a little right
    // of the panel's left edge, and high up near the header row.
    expect(t.x).toBeGreaterThan(panelLeft - FAB_SIZE)
    expect(t.x).toBeLessThan(panelLeft + 60)
    expect(t.y).toBeLessThan(40)
  })
})

describe('travelSteps', () => {
  it('is an L-path: vertical first (to target y), then horizontal (to target x)', () => {
    const steps = travelSteps({ x: 900, y: 500 }, { x: 640, y: 24 })
    expect(steps).toEqual([
      { x: 900, y: 500 },
      { x: 900, y: 24 }, // moved up first
      { x: 640, y: 24 }, // then across
    ])
  })
})

describe('isTapGesture', () => {
  it('is a tap when the pointer barely moved', () => {
    expect(isTapGesture({ x: 100, y: 100 }, { x: 102, y: 101 })).toBe(true)
  })

  it('is a drag once it moves past the threshold', () => {
    expect(isTapGesture({ x: 100, y: 100 }, { x: 120, y: 100 })).toBe(false)
    expect(isTapGesture({ x: 100, y: 100 }, { x: 100, y: 130 })).toBe(false)
  })
})

describe('panelRect', () => {
  it('is the panel docked top/right/bottom with the given width', () => {
    expect(panelRect(bounds, 360)).toEqual({ left: 1000 - 360 - 12, top: 12, width: 360, height: 600 - 24 })
  })

  it('and headerLogoTarget lands inside that rect (the morph start-of-grow sits on the panel)', () => {
    const r = panelRect(bounds, 360)
    const logo = headerLogoTarget(bounds, 360)
    expect(logo.x).toBeGreaterThanOrEqual(r.left - FAB_SIZE)
    expect(logo.x).toBeLessThan(r.left + r.width)
    expect(logo.y).toBeGreaterThanOrEqual(r.top - FAB_SIZE)
  })
})
