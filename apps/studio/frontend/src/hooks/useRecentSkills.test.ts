import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as recent from './useRecentSkills'

interface RecentWorkspaceEntry {
  absolutePath: string
  displayName: string
  identity: string
  lastOpenedAt: string
}

function stubLocalStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial))
  const localStorage = {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value)
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key)
    }),
  }
  vi.stubGlobal('window', { localStorage })
  vi.stubGlobal('localStorage', localStorage)
  return store
}

function recentWorkspaceApi() {
  const candidate = recent as unknown as {
    readRecentWorkspaces?: () => RecentWorkspaceEntry[]
    rememberRecentWorkspace?: (workspace: Pick<RecentWorkspaceEntry, 'absolutePath' | 'displayName'>) => RecentWorkspaceEntry
    removeRecentWorkspace?: (identity: string) => void
    pruneMissingRecentWorkspaces?: (exists: (absolutePath: string) => boolean) => RecentWorkspaceEntry[]
  }
  expect(typeof candidate.readRecentWorkspaces).toBe('function')
  expect(typeof candidate.rememberRecentWorkspace).toBe('function')
  expect(typeof candidate.removeRecentWorkspace).toBe('function')
  expect(typeof candidate.pruneMissingRecentWorkspaces).toBe('function')
  return candidate as Required<typeof candidate>
}

describe('recent workspace persistence', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('ignores legacy skill-id-only MRU entries and reads path-based workspaces', () => {
    const entry: RecentWorkspaceEntry = {
      absolutePath: '/Users/sevenx/Projects/plain-folder',
      displayName: 'plain-folder',
      identity: 'local:/Users/sevenx/Projects/plain-folder',
      lastOpenedAt: '2026-06-06T12:00:00.000Z',
    }
    stubLocalStorage({
      recentSkills: JSON.stringify(['demo-skill']),
      recentWorkspaces: JSON.stringify([entry]),
    })

    expect(recentWorkspaceApi().readRecentWorkspaces()).toEqual([entry])
  })

  it('adds and reorders path-based workspace entries with stable local identity', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-06T12:00:00.000Z'))
    const store = stubLocalStorage()
    const api = recentWorkspaceApi()

    const first = api.rememberRecentWorkspace({
      absolutePath: '/Users/sevenx/Projects/plain-folder',
      displayName: 'plain-folder',
    })
    vi.setSystemTime(new Date('2026-06-06T12:01:00.000Z'))
    const second = api.rememberRecentWorkspace({
      absolutePath: '/Users/sevenx/Projects/other-folder',
      displayName: 'other-folder',
    })
    vi.setSystemTime(new Date('2026-06-06T12:02:00.000Z'))
    const reopened = api.rememberRecentWorkspace({
      absolutePath: '/Users/sevenx/Projects/plain-folder',
      displayName: 'plain-folder',
    })

    expect(first.identity).toBe('local:/Users/sevenx/Projects/plain-folder')
    expect(second.identity).toBe('local:/Users/sevenx/Projects/other-folder')
    expect(reopened.identity).toBe(first.identity)
    expect(api.readRecentWorkspaces().map((workspace) => workspace.identity)).toEqual([
      first.identity,
      second.identity,
    ])
    expect(JSON.parse(store.get('recentWorkspaces') ?? '[]')).toEqual(api.readRecentWorkspaces())
  })

  it('removes a workspace from Studio without deleting the folder on disk', () => {
    const workspaceDir = mkdtempSync(join(tmpdir(), 'studio-recent-workspace-'))
    try {
      stubLocalStorage()
      const api = recentWorkspaceApi()
      const entry = api.rememberRecentWorkspace({
        absolutePath: workspaceDir,
        displayName: 'studio-recent-workspace',
      })

      api.removeRecentWorkspace(entry.identity)

      expect(api.readRecentWorkspaces()).toEqual([])
      expect(existsSync(workspaceDir)).toBe(true)
    } finally {
      rmSync(workspaceDir, { recursive: true, force: true })
    }
  })

  it('prunes missing workspace paths from the recent list', () => {
    const existingDir = mkdtempSync(join(tmpdir(), 'studio-existing-workspace-'))
    try {
      stubLocalStorage({
        recentWorkspaces: JSON.stringify([
          {
            absolutePath: existingDir,
            displayName: 'existing',
            identity: `local:${existingDir}`,
            lastOpenedAt: '2026-06-06T12:00:00.000Z',
          },
          {
            absolutePath: `${existingDir}-missing`,
            displayName: 'missing',
            identity: `local:${existingDir}-missing`,
            lastOpenedAt: '2026-06-06T12:01:00.000Z',
          },
        ]),
      })

      const remaining = recentWorkspaceApi().pruneMissingRecentWorkspaces(existsSync)

      expect(remaining.map((workspace) => workspace.absolutePath)).toEqual([existingDir])
      expect(recentWorkspaceApi().readRecentWorkspaces()).toEqual(remaining)
    } finally {
      rmSync(existingDir, { recursive: true, force: true })
    }
  })
})
