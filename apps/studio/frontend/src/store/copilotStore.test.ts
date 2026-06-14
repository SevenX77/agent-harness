import { beforeEach, describe, expect, it, vi } from 'vitest'

import { copilotStore, loadCopilotSessionsFromDisk } from './copilotStore'
import type { CopilotSession } from './copilotStore'

const listWorkspaceDir = vi.fn()
const readWorkspaceFile = vi.fn()

vi.mock('../lib/tauri', () => ({
  writeWorkspaceFile: vi.fn().mockResolvedValue({ path: '', content: '', hash: '' }),
  ensureWorkspaceSupportDirs: vi.fn().mockResolvedValue(undefined),
  readWorkspaceFile: (workspaceRoot: string, path: string) =>
    readWorkspaceFile(workspaceRoot, path),
  listWorkspaceDir: (workspaceRoot: string, dir: string) =>
    listWorkspaceDir(workspaceRoot, dir),
}))

const WS = '/abs/workspace'
const SKILL = 'demo-skill'

function diskSession(id: string, text: string): CopilotSession {
  return { id, messages: [{ id: `m-${id}`, role: 'user', content: text } as never] }
}

function fileEntry(name: string) {
  return { name, kind: 'file' as const }
}

beforeEach(() => {
  copilotStore.reset(null)
  listWorkspaceDir.mockReset()
  readWorkspaceFile.mockReset()
})

describe('loadCopilotSessionsFromDisk', () => {
  it('reads every .json session and skips non-json + malformed files', async () => {
    listWorkspaceDir.mockResolvedValue([
      fileEntry('session-1.json'),
      fileEntry('README.md'), // skipped: not .json
      { name: 'sub', kind: 'dir' as const }, // skipped: dir
      fileEntry('session-2.json'),
      fileEntry('broken.json'), // skipped: bad JSON
      fileEntry('not-a-session.json'), // skipped: shape invalid
    ])
    readWorkspaceFile.mockImplementation((_ws: string, path: string) => {
      if (path.endsWith('session-1.json')) {
        return Promise.resolve({ path, content: JSON.stringify(diskSession('session-1', 'a')), hash: 'h' })
      }
      if (path.endsWith('session-2.json')) {
        return Promise.resolve({ path, content: JSON.stringify(diskSession('session-2', 'b')), hash: 'h' })
      }
      if (path.endsWith('broken.json')) {
        return Promise.resolve({ path, content: '{not json', hash: 'h' })
      }
      return Promise.resolve({ path, content: JSON.stringify({ foo: 'bar' }), hash: 'h' })
    })

    const sessions = await loadCopilotSessionsFromDisk(WS, SKILL)

    expect(sessions.map((s) => s.id)).toEqual(['session-1', 'session-2'])
    expect(listWorkspaceDir).toHaveBeenCalledWith(WS, `.gemini/copilot/sessions/${SKILL}`)
  })

  it('returns empty when the sessions dir is missing (listWorkspaceDir -> [])', async () => {
    listWorkspaceDir.mockResolvedValue([])
    expect(await loadCopilotSessionsFromDisk(WS, SKILL)).toEqual([])
    expect(readWorkspaceFile).not.toHaveBeenCalled()
  })
})

describe('copilotStore.hydrate', () => {
  it('restores disk sessions on cold start (in-memory empty)', async () => {
    listWorkspaceDir.mockResolvedValue([fileEntry('session-100.json'), fileEntry('session-200.json')])
    readWorkspaceFile.mockImplementation((_ws: string, path: string) =>
      Promise.resolve({
        path,
        content: JSON.stringify(
          path.includes('100') ? diskSession('session-100', 'older') : diskSession('session-200', 'newer'),
        ),
        hash: 'h',
      }),
    )

    copilotStore.setContext(WS, SKILL)
    expect(copilotStore.getSnapshot().sessions).toHaveLength(0)

    await copilotStore.hydrate(WS, SKILL)

    const snap = copilotStore.getSnapshot()
    expect(snap.sessions.map((s) => s.id)).toEqual(['session-100', 'session-200'])
    // Active session defaults to the most recent (last) restored session.
    expect(snap.activeSessionId).toBe('session-200')
  })

  it('merges disk sessions without losing a live in-process session', async () => {
    // A session was created + chatted in this process; disk also holds an older
    // session from a previous run. Hydrate must surface BOTH, with the live
    // session's messages intact (in-memory wins).
    listWorkspaceDir.mockResolvedValue([fileEntry('session-1.json')])
    readWorkspaceFile.mockResolvedValue({
      path: 'session-1.json',
      content: JSON.stringify(diskSession('session-1', 'older-run')),
      hash: 'h',
    })

    copilotStore.setContext(WS, SKILL)
    const liveId = copilotStore.newSession()
    await copilotStore.appendMessage({ id: 'live-msg', role: 'user', content: 'live' } as never)
    const liveMessages = copilotStore.getSnapshot().messages.length

    await copilotStore.hydrate(WS, SKILL)

    const snap = copilotStore.getSnapshot()
    const live = snap.sessions.find((s) => s.id === liveId)
    expect(live?.messages.length).toBe(liveMessages)
    expect(snap.sessions.some((s) => s.id === 'session-1')).toBe(true)
  })

  it('is idempotent — disk is read at most once per context', async () => {
    listWorkspaceDir.mockResolvedValue([fileEntry('session-1.json')])
    readWorkspaceFile.mockResolvedValue({
      path: 'session-1.json',
      content: JSON.stringify(diskSession('session-1', 'x')),
      hash: 'h',
    })

    copilotStore.setContext(WS, SKILL)
    await copilotStore.hydrate(WS, SKILL)
    await copilotStore.hydrate(WS, SKILL)

    expect(listWorkspaceDir).toHaveBeenCalledTimes(1)
  })

  it('restores the last-viewed tab from _active.json, not the newest session (F2/D8)', async () => {
    // session-100 (older) was the last-viewed tab; session-200 is just newer.
    listWorkspaceDir.mockResolvedValue([fileEntry('session-100.json'), fileEntry('session-200.json')])
    readWorkspaceFile.mockImplementation((_ws: string, path: string) => {
      if (path.endsWith('_active.json')) {
        return Promise.resolve({ path, content: JSON.stringify({ activeSessionId: 'session-100' }), hash: 'h' })
      }
      return Promise.resolve({
        path,
        content: JSON.stringify(diskSession(path.includes('100') ? 'session-100' : 'session-200', 'x')),
        hash: 'h',
      })
    })

    copilotStore.setContext(WS, SKILL)
    await copilotStore.hydrate(WS, SKILL)

    // Active is the persisted last-viewed tab, even though session-200 is newer.
    expect(copilotStore.getSnapshot().activeSessionId).toBe('session-100')
  })

  it('ignores the _active.json marker file when loading sessions', async () => {
    listWorkspaceDir.mockResolvedValue([fileEntry('session-1.json'), fileEntry('_active.json')])
    readWorkspaceFile.mockImplementation((_ws: string, path: string) => {
      if (path.endsWith('_active.json')) {
        return Promise.resolve({ path, content: JSON.stringify({ activeSessionId: 'session-1' }), hash: 'h' })
      }
      return Promise.resolve({ path, content: JSON.stringify(diskSession('session-1', 'x')), hash: 'h' })
    })

    const sessions = await loadCopilotSessionsFromDisk(WS, SKILL)
    // _active.json is a marker, not a session — it must not appear as a session.
    expect(sessions.map((s) => s.id)).toEqual(['session-1'])
  })
})
