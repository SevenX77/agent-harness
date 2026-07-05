import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  copilotSessionDirectoryPath,
  copilotSessionRelativeDir,
  copilotStore,
  selectedCopilotSessionRelativePath,
} from './copilotStore'
import type { CopilotSession } from './copilotStore'

const readWorkspaceFile = vi.fn()
const writeWorkspaceFile = vi.fn()
const deleteWorkspacePath = vi.fn()

vi.mock('../lib/tauri', () => ({
  writeWorkspaceFile: (workspaceRoot: string, path: string, content: string) =>
    writeWorkspaceFile(workspaceRoot, path, content),
  deleteWorkspacePath: (workspaceRoot: string, path: string) =>
    deleteWorkspacePath(workspaceRoot, path),
  ensureWorkspaceSupportDirs: vi.fn().mockResolvedValue(undefined),
  readWorkspaceFile: (workspaceRoot: string, path: string) =>
    readWorkspaceFile(workspaceRoot, path),
}))

const WS = '/abs/workspace'
const WIN_WS = 'C:\\Users\\me\\workspace'
const SKILL = 'demo-skill'
const SESSION_DIR = `.workspace/copilot/sessions/${SKILL}`
const WINDOW_PATH = `${SESSION_DIR}/_window.json`

function diskSession(id: string, text: string): CopilotSession {
  return { id, messages: [{ id: `m-${id}`, role: 'user', content: text } as never] }
}

function windowState(openSessionIds: string[], activeSessionId: string | null) {
  return { openSessionIds, activeSessionId }
}

function readResult(path: string, value: unknown) {
  return { path, content: JSON.stringify(value), hash: 'h' }
}

async function settleWrites() {
  await Promise.resolve()
  await Promise.resolve()
}

function lastWrittenJson<T>(pathSuffix: string): T | null {
  const calls = writeWorkspaceFile.mock.calls as Array<[string, string, string]>
  for (let i = calls.length - 1; i >= 0; i -= 1) {
    const [, path, content] = calls[i]
    if (path.endsWith(pathSuffix)) {
      return JSON.parse(content) as T
    }
  }
  return null
}

function lastWrittenSession(sessionId: string): CopilotSession | null {
  return lastWrittenJson<CopilotSession>(`/${sessionId}.json`)
}

function lastWrittenWindow() {
  return lastWrittenJson<ReturnType<typeof windowState>>('/_window.json')
}

beforeEach(() => {
  copilotStore.reset(null)
  readWorkspaceFile.mockReset()
  writeWorkspaceFile.mockReset()
  writeWorkspaceFile.mockResolvedValue({ path: '', content: '', hash: '' })
  deleteWorkspacePath.mockReset()
  deleteWorkspacePath.mockResolvedValue(undefined)
})

describe('copilot session storage paths', () => {
  it('builds the skill-local session directory', () => {
    expect(copilotSessionRelativeDir(SKILL)).toBe(SESSION_DIR)
    expect(copilotSessionDirectoryPath(WS, SKILL)).toBe(`${WS}/${SESSION_DIR}`)
    expect(copilotSessionDirectoryPath(WIN_WS, SKILL)).toBe(
      `${WIN_WS}\\.workspace\\copilot\\sessions\\${SKILL}`,
    )
  })

  it('accepts only session json files from the current skill directory', () => {
    expect(
      selectedCopilotSessionRelativePath(
        WS,
        SKILL,
        `${WS}/${SESSION_DIR}/session-1.json`,
      ),
    ).toBe(`${SESSION_DIR}/session-1.json`)
    expect(
      selectedCopilotSessionRelativePath(
        WS,
        SKILL,
        `${WS}/.workspace/copilot/sessions/other/session-1.json`,
      ),
    ).toBeNull()
    expect(
      selectedCopilotSessionRelativePath(
        WS,
        SKILL,
        `${WS}/${SESSION_DIR}/_window.json`,
      ),
    ).toBeNull()
  })
})

describe('copilotStore.hydrate', () => {
  it('restores only the tabs listed in _window.json, preserving window order and active tab', async () => {
    readWorkspaceFile.mockImplementation((_ws: string, path: string) => {
      if (path === WINDOW_PATH) {
        return Promise.resolve(readResult(path, windowState(['session-300', 'session-100'], 'session-100')))
      }
      if (path.endsWith('session-300.json')) {
        return Promise.resolve(readResult(path, diskSession('session-300', 'third')))
      }
      if (path.endsWith('session-100.json')) {
        return Promise.resolve(readResult(path, diskSession('session-100', 'first')))
      }
      throw new Error(`unexpected read ${path}`)
    })

    copilotStore.setContext(WS, SKILL)
    await copilotStore.hydrate(WS, SKILL)

    const snap = copilotStore.getSnapshot()
    expect(snap.sessions.map((s) => s.id)).toEqual(['session-300', 'session-100'])
    expect(snap.activeSessionId).toBe('session-100')
    expect(readWorkspaceFile).not.toHaveBeenCalledWith(WS, `${SESSION_DIR}/session-200.json`)
  })

  it('does not resurrect every historical transcript when _window.json is missing', async () => {
    readWorkspaceFile.mockImplementation((_ws: string, path: string) => {
      if (path === WINDOW_PATH) {
        return Promise.reject(new Error('not found'))
      }
      throw new Error(`unexpected read ${path}`)
    })

    copilotStore.setContext(WS, SKILL)
    await copilotStore.hydrate(WS, SKILL)

    expect(copilotStore.getSnapshot().sessions).toEqual([])
    expect(readWorkspaceFile).toHaveBeenCalledTimes(1)
    expect(readWorkspaceFile).toHaveBeenCalledWith(WS, WINDOW_PATH)
  })

  it('is idempotent: disk is read at most once per context', async () => {
    readWorkspaceFile.mockImplementation((_ws: string, path: string) => {
      if (path === WINDOW_PATH) {
        return Promise.resolve(readResult(path, windowState(['session-1'], 'session-1')))
      }
      return Promise.resolve(readResult(path, diskSession('session-1', 'x')))
    })

    copilotStore.setContext(WS, SKILL)
    await copilotStore.hydrate(WS, SKILL)
    await copilotStore.hydrate(WS, SKILL)

    expect(readWorkspaceFile).toHaveBeenCalledTimes(2)
  })
})

describe('copilotStore streamed-turn persistence', () => {
  it('persists new empty sessions and window state under the .workspace copilot support tree', async () => {
    copilotStore.setContext(WS, SKILL)
    const sessionId = copilotStore.newSession()
    await settleWrites()

    expect(writeWorkspaceFile).toHaveBeenCalledWith(
      WS,
      `${SESSION_DIR}/${sessionId}.json`,
      expect.any(String),
    )
    expect(lastWrittenSession(sessionId)).toEqual({ id: sessionId, messages: [] })
    expect(lastWrittenWindow()).toEqual(windowState([sessionId], sessionId))
  })

  it('updates window state when the active tab changes', async () => {
    copilotStore.setContext(WS, SKILL)
    const a = copilotStore.newSession()
    const b = copilotStore.newSession()
    await settleWrites()
    writeWorkspaceFile.mockClear()

    copilotStore.switchSession(a)
    await settleWrites()

    expect(copilotStore.getSnapshot().activeSessionId).toBe(a)
    expect(lastWrittenWindow()).toEqual(windowState([a, b], a))
  })

  it('remembers the active tab when switching away from a skill and back in the same process', () => {
    copilotStore.setContext(WS, SKILL)
    const a = copilotStore.newSession()
    copilotStore.newSession()

    copilotStore.switchSession(a)
    copilotStore.setContext(WS, 'other-skill')
    copilotStore.setContext(WS, SKILL)

    expect(copilotStore.getSnapshot().activeSessionId).toBe(a)
  })

  it('flushes the full assistant message to disk when the turn completes', async () => {
    copilotStore.setContext(WS, SKILL)
    const sessionId = copilotStore.newSession()

    await copilotStore.appendMessage({ id: 'u1', role: 'user', content: 'hi', events: [], status: 'success', createdAt: 1 } as never)
    await copilotStore.appendMessage({ id: 'a1', role: 'assistant', content: '', events: [], status: 'running', createdAt: 2 } as never)

    const writesBeforeDone = writeWorkspaceFile.mock.calls.length
    copilotStore.updateMessage('a1', (m) => ({ ...m, content: `${m.content}Hello `, status: 'running' }))
    copilotStore.updateMessage('a1', (m) => ({ ...m, content: `${m.content}world`, status: 'running' }))
    expect(writeWorkspaceFile.mock.calls.length).toBe(writesBeforeDone)

    copilotStore.updateMessage('a1', (m) => ({
      ...m,
      status: 'success',
      events: [...m.events, { id: 'e1', type: 'done', status: 'success', receivedAt: 3, raw: {} } as never],
    }))
    await settleWrites()

    const persisted = lastWrittenSession(sessionId)
    expect(persisted).not.toBeNull()
    const assistant = persisted?.messages.find((m) => m.id === 'a1')
    expect(assistant?.content).toBe('Hello world')
    expect(assistant?.events.some((e) => (e as { type: string }).type === 'done')).toBe(true)
  })

  it('hydrate round-trips persisted assistant content through _window.json', async () => {
    copilotStore.setContext(WS, SKILL)
    const sessionId = copilotStore.newSession()
    await copilotStore.appendMessage({ id: 'u1', role: 'user', content: 'q', events: [], status: 'success', createdAt: 1 } as never)
    await copilotStore.appendMessage({ id: 'a1', role: 'assistant', content: '', events: [], status: 'running', createdAt: 2 } as never)
    copilotStore.updateMessage('a1', (m) => ({ ...m, content: 'streamed answer', status: 'success' }))
    await settleWrites()

    const onDisk = lastWrittenSession(sessionId)
    expect(onDisk?.messages.find((m) => m.id === 'a1')?.content).toBe('streamed answer')

    copilotStore.reset(null)
    readWorkspaceFile.mockImplementation((_ws: string, path: string) => {
      if (path === WINDOW_PATH) {
        return Promise.resolve(readResult(path, windowState([sessionId], sessionId)))
      }
      return Promise.resolve(readResult(path, onDisk))
    })

    copilotStore.setContext(WS, SKILL)
    await copilotStore.hydrate(WS, SKILL)

    const restored = copilotStore
      .getSnapshot()
      .sessions.find((s) => s.id === sessionId)
      ?.messages.find((m) => m.id === 'a1')
    expect(restored?.content).toBe('streamed answer')
  })
})

describe('closeSession', () => {
  function seedThree(): string[] {
    copilotStore.setContext(WS, SKILL)
    const a = copilotStore.newSession()
    const b = copilotStore.newSession()
    const c = copilotStore.newSession()
    return [a, b, c]
  }

  it('closing a non-active session keeps the active one and preserves the transcript file', async () => {
    const [a, b, c] = seedThree()
    await settleWrites()
    writeWorkspaceFile.mockClear()
    await copilotStore.closeSession(a)

    const snapshot = copilotStore.getSnapshot()
    expect(snapshot.sessions.map((s) => s.id)).toEqual([b, c])
    expect(snapshot.activeSessionId).toBe(c)
    expect(deleteWorkspacePath).not.toHaveBeenCalled()
    expect(lastWrittenWindow()).toEqual(windowState([b, c], c))
  })

  it('closing the active session activates its previous neighbor', async () => {
    const [a, b, c] = seedThree()
    await settleWrites()
    writeWorkspaceFile.mockClear()
    await copilotStore.closeSession(c)

    const snapshot = copilotStore.getSnapshot()
    expect(snapshot.sessions.map((s) => s.id)).toEqual([a, b])
    expect(snapshot.activeSessionId).toBe(b)
    expect(lastWrittenWindow()).toEqual(windowState([a, b], b))
  })

  it('closing the last remaining session leaves one fresh empty chat', async () => {
    copilotStore.setContext(WS, SKILL)
    const only = copilotStore.newSession()
    writeWorkspaceFile.mockClear()

    await copilotStore.closeSession(only)
    await settleWrites()

    const snapshot = copilotStore.getSnapshot()
    expect(snapshot.sessions).toHaveLength(1)
    expect(snapshot.sessions[0].id).not.toBe(only)
    expect(snapshot.sessions[0].messages).toEqual([])
    expect(snapshot.activeSessionId).toBe(snapshot.sessions[0].id)
    expect(deleteWorkspacePath).not.toHaveBeenCalled()
    expect(lastWrittenWindow()).toEqual(windowState([snapshot.sessions[0].id], snapshot.sessions[0].id))
  })

  it('ignores unknown session ids', async () => {
    const [a, b, c] = seedThree()
    await settleWrites()
    writeWorkspaceFile.mockClear()
    await copilotStore.closeSession('nope')
    expect(copilotStore.getSnapshot().sessions.map((s) => s.id)).toEqual([a, b, c])
    expect(writeWorkspaceFile).not.toHaveBeenCalled()
  })
})

describe('restoreSessionFromFile', () => {
  it('loads a selected session file from this skill, opens it, and activates it', async () => {
    copilotStore.setContext(WS, SKILL)
    const existing = copilotStore.newSession()
    await settleWrites()
    writeWorkspaceFile.mockClear()
    const restored = diskSession('session-restored', 'bring this back')
    readWorkspaceFile.mockResolvedValue(readResult(`${SESSION_DIR}/session-restored.json`, restored))

    await expect(
      copilotStore.restoreSessionFromFile(`${WS}/${SESSION_DIR}/session-restored.json`),
    ).resolves.toBe(true)

    const snapshot = copilotStore.getSnapshot()
    expect(snapshot.sessions.map((s) => s.id)).toEqual([existing, 'session-restored'])
    expect(snapshot.activeSessionId).toBe('session-restored')
    expect(readWorkspaceFile).toHaveBeenCalledWith(WS, `${SESSION_DIR}/session-restored.json`)
    expect(lastWrittenWindow()).toEqual(windowState([existing, 'session-restored'], 'session-restored'))
  })

  it('rejects files outside the current skill session directory', async () => {
    copilotStore.setContext(WS, SKILL)

    await expect(
      copilotStore.restoreSessionFromFile(`${WS}/.workspace/copilot/sessions/other/session-1.json`),
    ).resolves.toBe(false)

    expect(readWorkspaceFile).not.toHaveBeenCalled()
    expect(copilotStore.getSnapshot().persistenceError).toContain('current skill')
  })

  it('rejects session files whose filename does not match the stored session id', async () => {
    copilotStore.setContext(WS, SKILL)
    readWorkspaceFile.mockResolvedValue(
      readResult(`${SESSION_DIR}/session-1.json`, diskSession('session-2', 'wrong file')),
    )

    await expect(
      copilotStore.restoreSessionFromFile(`${WS}/${SESSION_DIR}/session-1.json`),
    ).resolves.toBe(false)

    expect(copilotStore.getSnapshot().sessions).toEqual([])
    expect(copilotStore.getSnapshot().persistenceError).toContain('does not match')
  })
})
