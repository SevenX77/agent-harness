import { describe, expect, it } from 'vitest'
import {
  breadcrumbItems,
  currentLevel,
  drillStackReducer,
  type DrillLevel,
  type DrillStack,
} from './drill-stack'

const childA: DrillLevel = { path: 'skills/child-a', label: 'Child A' }
const childB: DrillLevel = { path: 'skills/child-b', label: 'Child B' }
const childC: DrillLevel = { path: 'skills/child-c', label: 'Child C' }

describe('drillStackReducer', () => {
  it('pushes a level onto an empty stack', () => {
    const next = drillStackReducer([], { type: 'push', level: childA })
    expect(next).toEqual([childA])
  })

  it('pushes deeper levels in order', () => {
    let stack: DrillStack = []
    stack = drillStackReducer(stack, { type: 'push', level: childA })
    stack = drillStackReducer(stack, { type: 'push', level: childB })
    expect(stack).toEqual([childA, childB])
  })

  it('pops the top level', () => {
    const next = drillStackReducer([childA, childB], { type: 'pop' })
    expect(next).toEqual([childA])
  })

  it('returns the same reference when popping an empty stack (no-op)', () => {
    const empty: DrillStack = []
    expect(drillStackReducer(empty, { type: 'pop' })).toBe(empty)
  })

  it('pops to a specific level index, truncating deeper levels', () => {
    const next = drillStackReducer([childA, childB, childC], { type: 'popTo', index: 0 })
    expect(next).toEqual([childA])
  })

  it('pops to root for a negative index', () => {
    const next = drillStackReducer([childA, childB], { type: 'popTo', index: -1 })
    expect(next).toEqual([])
  })

  it('is a no-op when popping to an index at or beyond the top', () => {
    const stack: DrillStack = [childA, childB]
    expect(drillStackReducer(stack, { type: 'popTo', index: 1 })).toBe(stack)
    expect(drillStackReducer(stack, { type: 'popTo', index: 5 })).toBe(stack)
  })

  it('resets to root and is a no-op when already at root', () => {
    expect(drillStackReducer([childA, childB], { type: 'reset' })).toEqual([])
    const empty: DrillStack = []
    expect(drillStackReducer(empty, { type: 'reset' })).toBe(empty)
  })

  it('returns the same reference when popTo root on an already-empty stack', () => {
    const empty: DrillStack = []
    expect(drillStackReducer(empty, { type: 'popTo', index: -1 })).toBe(empty)
  })
})

describe('breadcrumbItems', () => {
  it('shows only the root as current when the stack is empty', () => {
    const items = breadcrumbItems([], 'Root')
    expect(items).toEqual([{ index: -1, label: 'Root', isCurrent: true }])
  })

  it('builds root → child trail with the deepest level marked current', () => {
    const items = breadcrumbItems([childA, childB], 'Root')
    expect(items).toEqual([
      { index: -1, label: 'Root', isCurrent: false },
      { index: 0, label: 'Child A', isCurrent: false },
      { index: 1, label: 'Child B', isCurrent: true },
    ])
  })

  it('marks the single drilled level as current and root as clickable', () => {
    const items = breadcrumbItems([childA], 'Root')
    expect(items[0]).toEqual({ index: -1, label: 'Root', isCurrent: false })
    expect(items[1]).toEqual({ index: 0, label: 'Child A', isCurrent: true })
  })
})

describe('currentLevel', () => {
  it('returns null at the root', () => {
    expect(currentLevel([])).toBeNull()
  })

  it('returns the deepest level when drilled', () => {
    expect(currentLevel([childA, childB])).toBe(childB)
  })
})

describe('push → pop-to-level → root round trip', () => {
  it('navigates down then back up via breadcrumb indices', () => {
    let stack: DrillStack = []
    stack = drillStackReducer(stack, { type: 'push', level: childA })
    stack = drillStackReducer(stack, { type: 'push', level: childB })
    stack = drillStackReducer(stack, { type: 'push', level: childC })
    expect(breadcrumbItems(stack, 'Root').map((b) => b.label)).toEqual([
      'Root',
      'Child A',
      'Child B',
      'Child C',
    ])

    // Click "Child A" (index 0) in the breadcrumb → truncate to [childA].
    stack = drillStackReducer(stack, { type: 'popTo', index: 0 })
    expect(stack).toEqual([childA])

    // Click "Root" (index -1) → back to the root graph.
    stack = drillStackReducer(stack, { type: 'popTo', index: -1 })
    expect(stack).toEqual([])
    expect(currentLevel(stack)).toBeNull()
  })
})
