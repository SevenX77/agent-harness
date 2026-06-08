/**
 * WS-5 RED: Copilot session model (copilot-assist F2, D8).
 *
 * Contract under test (settings spec §3.6 + copilot-assist F2):
 *  - A Copilot session is keyed by (workspace identity, skill id). One skill can
 *    hold multiple session tabs plus "new chat".
 *  - Switching workspace/skill must NOT leak sessions across contexts.
 *  - Appending a message persists the session through the WS-1 native writer
 *    (`writeWorkspaceFile` + `ensureWorkspaceSupportDirs`) — never localStorage.
 *  - A failed write must surface an explicit `persistenceError`, not be dropped.
 *
 * Cold-reopen restore (reading sessions back from disk) is DEFERRED:
 * blocked-on-WS-1 because Tauri exposes no `read_workspace_file` command yet.
 * See the `it.skip` at the bottom.
 *
 * This is RED on the current single-`messages[]` in-memory store, which has no
 * session/tab API and no persistence.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const writeWorkspaceFile = vi.fn()
const ensureWorkspaceSupportDirs = vi.fn()

vi.mock('../lib/tauri', () => ({
  writeWorkspaceFile: (...args: unknown[]) => writeWorkspaceFile(...args),
  ensureWorkspaceSupportDirs: (...args: unknown[]) => ensureWorkspaceSupportDirs(...args),
}))

import { copilotStore } from './copilotStore'
import type { CopilotMessage } from '../types/copilot'

function userMessage(content: string): CopilotMessage {
  return {
    id: `msg-${content}`,
    role: 'user',
    content,
    events: [],
    status: 'success',
    createdAt: 1,
  }
}

beforeEach(() => {
  writeWorkspaceFile.mockReset().mockResolvedValue({ path: 'p', hash: 'h' })
  ensureWorkspaceSupportDirs.mockReset().mockResolvedValue(undefined)
  copilotStore.reset(null)
})

describe('copilotStore session model', () => {
  it('supports multiple session tabs and a new chat under one skill', () => {
    copilotStore.setContext('/ws/root', 'skill-a')
    const first = copilotStore.newSession()
    const second = copilotStore.newSession()

    const snapshot = copilotStore.getSnapshot()
    expect(snapshot.sessions).toHaveLength(2)
    expect(snapshot.sessions.map((session) => session.id)).toEqual([first, second])
    expect(snapshot.activeSessionId).toBe(second)
  })

  it('switches the active session tab', () => {
    copilotStore.setContext('/ws/root', 'skill-a')
    const first = copilotStore.newSession()
    copilotStore.newSession()

    copilotStore.switchSession(first)
    expect(copilotStore.getSnapshot().activeSessionId).toBe(first)
  })

  it('isolates sessions across workspace and skill identity', async () => {
    copilotStore.setContext('/ws/root', 'skill-a')
    copilotStore.newSession()
    await copilotStore.appendMessage(userMessage('hello-a'))

    // Different skill in the same workspace must not see skill-a sessions.
    copilotStore.setContext('/ws/root', 'skill-b')
    expect(copilotStore.getSnapshot().sessions).toHaveLength(0)

    // Different workspace, same skill name must also be isolated.
    copilotStore.setContext('/other/ws', 'skill-a')
    expect(copilotStore.getSnapshot().sessions).toHaveLength(0)

    // Returning to the original context retains its in-run sessions.
    copilotStore.setContext('/ws/root', 'skill-a')
    const restored = copilotStore.getSnapshot()
    expect(restored.sessions).toHaveLength(1)
    expect(restored.sessions[0].messages.map((message) => message.content)).toEqual(['hello-a'])
  })

  it('persists appended messages through the native writer, not localStorage', async () => {
    copilotStore.setContext('/ws/root', 'skill-a')
    const sessionId = copilotStore.newSession()
    await copilotStore.appendMessage(userMessage('hello'))

    expect(ensureWorkspaceSupportDirs).toHaveBeenCalledWith('/ws/root')
    expect(writeWorkspaceFile).toHaveBeenCalled()
    const [workspaceRoot, relativePath, content] = writeWorkspaceFile.mock.calls[0]
    expect(workspaceRoot).toBe('/ws/root')
    expect(String(relativePath)).toContain('skill-a')
    expect(String(relativePath)).toContain(sessionId)
    expect(String(content)).toContain('hello')
  })

  it('surfaces an explicit error when the session write fails', async () => {
    writeWorkspaceFile.mockRejectedValueOnce(new Error('disk full'))
    copilotStore.setContext('/ws/root', 'skill-a')
    copilotStore.newSession()

    await copilotStore.appendMessage(userMessage('hello'))

    const error = copilotStore.getSnapshot().persistenceError
    expect(error).toBeTruthy()
    expect(String(error)).toContain('disk full')
  })

  it('caches the snapshot reference and invalidates it only when store emits', () => {
    copilotStore.setContext('/ws/root', 'skill-a')
    
    const snap1 = copilotStore.getSnapshot()
    const snap2 = copilotStore.getSnapshot()
    // Without any changes, getSnapshot MUST return the exact same object reference
    expect(snap1).toBe(snap2)

    // Triggering a mutation/emit should invalidate cache and return a new object reference
    copilotStore.newSession()
    const snap3 = copilotStore.getSnapshot()
    expect(snap3).not.toBe(snap1)
    
    const snap4 = copilotStore.getSnapshot()
    expect(snap3).toBe(snap4)
  })

  // DEFERRED — blocked-on-WS-1: restoring sessions on a cold app reopen needs a
  // native `read_workspace_file` / list command that Tauri does not expose yet
  // (lib.rs is WS-1 owned). MUST NOT be faked via localStorage. Re-enable once
  // WS-1 ships the native read path.
  it.skip('restores sessions from disk on cold reopen (blocked-on-WS-1)', () => {
    expect(true).toBe(true)
  })
})
