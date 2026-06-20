import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  pruneMissingRecentWorkspaces,
  pruneMissingRecentWorkspacesAsync,
  readRecentWorkspaces,
  rememberRecentWorkspace,
  type RecentWorkspaceEntry,
} from './useRecentSkills'

// The default vitest environment here is node (no jsdom), and the MRU helpers
// guard on `typeof window` / use `localStorage`. Stub a minimal in-memory
// localStorage + a window global so the real helpers exercise their disk path.
function createMemoryStorage(): Storage {
  const store = new Map<string, string>()
  return {
    get length() {
      return store.size
    },
    clear: () => store.clear(),
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, value)
    },
    removeItem: (key: string) => {
      store.delete(key)
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
  } as Storage
}

const present: RecentWorkspaceEntry = {
  absolutePath: '/tmp/present',
  displayName: 'Present',
  identity: 'local:/tmp/present',
  lastOpenedAt: '2026-06-18T10:00:00.000Z',
}
const missing: RecentWorkspaceEntry = {
  absolutePath: '/tmp/missing',
  displayName: 'Missing',
  identity: 'local:/tmp/missing',
  lastOpenedAt: '2026-06-18T09:00:00.000Z',
}

let storage: Storage

beforeEach(() => {
  storage = createMemoryStorage()
  vi.stubGlobal('window', {})
  vi.stubGlobal('localStorage', storage)
  storage.setItem('recentWorkspaces', JSON.stringify([present, missing]))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('pruneMissingRecentWorkspacesAsync', () => {
  it('drops entries whose folder no longer exists and rewrites the MRU', async () => {
    const exists = vi.fn(async (path: string) => path === '/tmp/present')

    const next = await pruneMissingRecentWorkspacesAsync(exists)

    expect(next).toEqual([present])
    expect(readRecentWorkspaces()).toEqual([present])
    expect(exists).toHaveBeenCalledTimes(2)
  })

  it('leaves the MRU untouched when every folder still exists', async () => {
    const setItem = vi.spyOn(storage, 'setItem')
    const exists = vi.fn(async () => true)

    const next = await pruneMissingRecentWorkspacesAsync(exists)

    expect(next).toEqual([present, missing])
    // No rewrite when nothing was pruned, so the MRU store is not churned.
    expect(setItem).not.toHaveBeenCalled()
  })

  it('keeps the sync predicate variant working for callers that have one', () => {
    const next = pruneMissingRecentWorkspaces((path) => path === '/tmp/present')
    expect(next).toEqual([present])
    expect(readRecentWorkspaces()).toEqual([present])
  })

  it('rememberRecentWorkspace dedupes by identity and prepends most-recent', () => {
    storage.removeItem('recentWorkspaces')
    rememberRecentWorkspace({ absolutePath: '/tmp/a', displayName: 'A' })
    rememberRecentWorkspace({ absolutePath: '/tmp/b', displayName: 'B' })
    rememberRecentWorkspace({ absolutePath: '/tmp/a', displayName: 'A2' })

    const list = readRecentWorkspaces()
    expect(list.map((w) => w.absolutePath)).toEqual(['/tmp/a', '/tmp/b'])
    expect(list[0].displayName).toBe('A2')
  })
})
