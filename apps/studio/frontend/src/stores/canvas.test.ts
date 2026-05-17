import { beforeEach, describe, expect, it } from 'vitest'
import { currentCanvasEntry, isCanvasReadOnly, useCanvasStore } from './canvas'

describe('useCanvasStore', () => {
  beforeEach(() => {
    useCanvasStore.getState().reset()
  })

  it('sets the root canvas entry', () => {
    useCanvasStore.getState().setRoot({ skillId: 'root', skillName: 'Root' })

    expect(useCanvasStore.getState().navStack).toEqual([{ skillId: 'root', skillName: 'Root' }])
    expect(currentCanvasEntry(useCanvasStore.getState().navStack)?.skillId).toBe('root')
    expect(isCanvasReadOnly(useCanvasStore.getState().navStack)).toBe(false)
  })

  it('pushes and pops subgraph entries with read-only derived state', () => {
    const store = useCanvasStore.getState()
    store.setRoot({ skillId: 'root', skillName: 'Root' })

    expect(store.push({ skillId: 'child', skillName: 'Child' })).toEqual({ ok: true })
    expect(useCanvasStore.getState().navStack.map((entry) => entry.skillId)).toEqual(['root', 'child'])
    expect(isCanvasReadOnly(useCanvasStore.getState().navStack)).toBe(true)

    useCanvasStore.getState().pop()
    expect(useCanvasStore.getState().navStack.map((entry) => entry.skillId)).toEqual(['root'])
  })

  it('jumps to a breadcrumb entry', () => {
    const store = useCanvasStore.getState()
    store.setRoot({ skillId: 'root', skillName: 'Root' })
    store.push({ skillId: 'child', skillName: 'Child' })
    store.push({ skillId: 'grandchild', skillName: 'Grandchild' })

    useCanvasStore.getState().jumpTo(1)

    expect(useCanvasStore.getState().navStack.map((entry) => entry.skillId)).toEqual(['root', 'child'])
  })

  it('rejects cycles and deep drill-down stacks', () => {
    const store = useCanvasStore.getState()
    store.setRoot({ skillId: 'root', skillName: 'Root' })

    expect(store.push({ skillId: 'root', skillName: 'Root' })).toEqual({ ok: false, reason: 'cycle' })
    expect(store.push({ skillId: 'one', skillName: 'One' })).toEqual({ ok: true })
    expect(store.push({ skillId: 'two', skillName: 'Two' })).toEqual({ ok: true })
    expect(store.push({ skillId: 'three', skillName: 'Three' })).toEqual({ ok: true })
    expect(store.push({ skillId: 'four', skillName: 'Four' })).toEqual({ ok: true })
    expect(store.push({ skillId: 'five', skillName: 'Five' })).toEqual({ ok: false, reason: 'depth' })
  })
})
