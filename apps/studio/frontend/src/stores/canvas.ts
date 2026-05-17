import { create } from 'zustand'

export interface CanvasNavEntry {
  skillId: string
  skillName: string
}

export type CanvasNavRejectReason = 'cycle' | 'depth'

interface CanvasNavResult {
  ok: boolean
  reason?: CanvasNavRejectReason
}

interface CanvasState {
  navStack: CanvasNavEntry[]
  setRoot: (entry: CanvasNavEntry | null) => void
  push: (entry: CanvasNavEntry) => CanvasNavResult
  pop: () => void
  jumpTo: (index: number) => void
  reset: () => void
}

export function isCanvasReadOnly(navStack: CanvasNavEntry[]): boolean {
  return navStack.length > 1
}

export function currentCanvasEntry(navStack: CanvasNavEntry[]): CanvasNavEntry | null {
  return navStack.at(-1) ?? null
}

export const useCanvasStore = create<CanvasState>((set, get) => ({
  navStack: [],
  setRoot: (entry) => {
    set({ navStack: entry ? [entry] : [] })
  },
  push: (entry) => {
    const navStack = get().navStack
    if (navStack.some((item) => item.skillId === entry.skillId)) {
      return { ok: false, reason: 'cycle' }
    }
    if (navStack.length >= 5) {
      return { ok: false, reason: 'depth' }
    }
    set({ navStack: [...navStack, entry] })
    return { ok: true }
  },
  pop: () => {
    set((state) => ({
      navStack: state.navStack.length > 1 ? state.navStack.slice(0, -1) : state.navStack,
    }))
  },
  jumpTo: (index) => {
    set((state) => {
      if (index < 0 || index >= state.navStack.length) {
        return state
      }
      return { navStack: state.navStack.slice(0, index + 1) }
    })
  },
  reset: () => {
    set({ navStack: [] })
  },
}))
