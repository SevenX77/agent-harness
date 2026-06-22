import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  buildRecentEntry,
  loadRecentWorkspaces,
  mergeRecent,
  recentWorkspaceIdentity,
  RECENT_CAP,
  type RecentLoadDeps,
  type RecentWorkspaceEntry,
} from './useRecentSkills'

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

function makeDeps(over: Partial<RecentLoadDeps> = {}): RecentLoadDeps {
  return {
    list: vi.fn(async () => [present, missing]),
    exists: vi.fn(async () => true),
    remove: vi.fn(async () => undefined),
    ...over,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('mergeRecent (dedupe + prepend most-recent + cap)', () => {
  it('prepends a new entry', () => {
    const next = mergeRecent([present], { ...missing })
    expect(next.map((w) => w.absolutePath)).toEqual(['/tmp/missing', '/tmp/present'])
  })

  it('dedupes by identity, keeping the freshly-prepended copy', () => {
    const updated = { ...present, displayName: 'Present v2' }
    const next = mergeRecent([present, missing], updated)
    expect(next.map((w) => w.absolutePath)).toEqual(['/tmp/present', '/tmp/missing'])
    expect(next[0].displayName).toBe('Present v2')
  })

  it('caps the list at RECENT_CAP, dropping the oldest', () => {
    const list: RecentWorkspaceEntry[] = Array.from({ length: RECENT_CAP }, (_, i) => ({
      absolutePath: `/tmp/skill-${i}`,
      displayName: `Skill ${i}`,
      identity: `local:/tmp/skill-${i}`,
      lastOpenedAt: '2026-06-18T00:00:00.000Z',
    }))
    const fresh = buildRecentEntry({ absolutePath: '/tmp/new', displayName: 'New' }, '2026-06-19T00:00:00.000Z')
    const next = mergeRecent(list, fresh)
    expect(next).toHaveLength(RECENT_CAP)
    expect(next[0].absolutePath).toBe('/tmp/new')
    expect(next.map((w) => w.absolutePath)).not.toContain(`/tmp/skill-${RECENT_CAP - 1}`)
  })
})

describe('buildRecentEntry / recentWorkspaceIdentity', () => {
  it('derives the local: identity from the absolute path', () => {
    expect(recentWorkspaceIdentity('/tmp/x')).toBe('local:/tmp/x')
  })

  it('builds an entry with the local identity and the given timestamp', () => {
    const entry = buildRecentEntry({ absolutePath: '/tmp/x', displayName: 'X' }, '2026-06-20T00:00:00.000Z')
    expect(entry).toEqual({
      absolutePath: '/tmp/x',
      displayName: 'X',
      identity: 'local:/tmp/x',
      lastOpenedAt: '2026-06-20T00:00:00.000Z',
    })
  })
})

describe('loadRecentWorkspaces (Rust store = single source of truth)', () => {
  it('returns the native MRU on a clean read with no error', async () => {
    const deps = makeDeps({ exists: vi.fn(async () => true) })
    const result = await loadRecentWorkspaces(deps)

    expect(result.error).toBeNull()
    expect(result.entries).toEqual([present, missing])
    expect(deps.remove).not.toHaveBeenCalled()
  })

  it('drops entries whose folder is gone AND prunes them from the native store', async () => {
    const remove = vi.fn(async () => undefined)
    const deps = makeDeps({
      exists: vi.fn(async (path: string) => path === '/tmp/present'),
      remove,
    })

    const result = await loadRecentWorkspaces(deps)

    expect(result.entries).toEqual([present])
    expect(remove).toHaveBeenCalledTimes(1)
    expect(remove).toHaveBeenCalledWith('local:/tmp/missing')
  })

  it('keeps an entry when its existence check throws (flaky check never hides a live workspace)', async () => {
    const deps = makeDeps({
      exists: vi.fn(async (path: string) => {
        if (path === '/tmp/missing') throw new Error('fs hiccup')
        return true
      }),
    })

    const result = await loadRecentWorkspaces(deps)

    expect(result.entries).toEqual([present, missing])
    expect(deps.remove).not.toHaveBeenCalled()
  })

  it('caps the native list at RECENT_CAP', async () => {
    const big: RecentWorkspaceEntry[] = Array.from({ length: RECENT_CAP + 5 }, (_, i) => ({
      absolutePath: `/tmp/skill-${i}`,
      displayName: `Skill ${i}`,
      identity: `local:/tmp/skill-${i}`,
      lastOpenedAt: '2026-06-18T00:00:00.000Z',
    }))
    const deps = makeDeps({ list: vi.fn(async () => big) })

    const result = await loadRecentWorkspaces(deps)

    expect(result.entries).toHaveLength(RECENT_CAP)
  })

  it('surfaces a non-null error (and logs it) instead of swallowing a read failure', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const deps = makeDeps({
      list: vi.fn(async () => {
        throw new Error('native list unavailable')
      }),
    })

    const result = await loadRecentWorkspaces(deps)

    expect(result.entries).toEqual([])
    expect(result.error).toContain('native list unavailable')
    expect(warnSpy).toHaveBeenCalled()
  })
})
