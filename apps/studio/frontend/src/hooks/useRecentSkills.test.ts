import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  pruneMissingRecentWorkspaces,
  pruneMissingRecentWorkspacesAsync,
  readRecentWorkspaces,
  readRecentWorkspacesResult,
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

describe('readRecentWorkspacesResult (N1 atom #9 local error fallback)', () => {
  it('returns the parsed MRU with no error on a clean read', () => {
    const result = readRecentWorkspacesResult()

    expect(result.error).toBeNull()
    expect(result.entries).toEqual([present, missing])
  })

  it('surfaces a read error instead of silently swallowing a corrupt MRU blob', () => {
    // A corrupt localStorage blob used to be caught and swallowed into [] (a
    // zero-silent-failure violation). It must now surface a non-null error so
    // Home can render the local red box, while still degrading entries to [].
    storage.setItem('recentWorkspaces', '{not valid json')
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const result = readRecentWorkspacesResult()

    expect(result.entries).toEqual([])
    expect(result.error).not.toBeNull()
    expect(typeof result.error).toBe('string')
    // The failure is logged, never silently swallowed.
    expect(warnSpy).toHaveBeenCalled()
  })

  it('surfaces a read error when localStorage.getItem itself throws', () => {
    const throwingStorage = {
      ...storage,
      getItem: () => {
        throw new Error('SecurityError: localStorage blocked')
      },
    } as Storage
    vi.stubGlobal('localStorage', throwingStorage)
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const result = readRecentWorkspacesResult()

    expect(result.entries).toEqual([])
    expect(result.error).toContain('localStorage blocked')
    expect(warnSpy).toHaveBeenCalled()
  })
})
