import type { CopilotMessage } from '../types/copilot'
import {
  writeWorkspaceFile,
  ensureWorkspaceSupportDirs,
  readWorkspaceFile,
} from '../lib/tauri'

type Listener = () => void

const COPILOT_SESSION_ROOT = '.workspace/copilot/sessions'

export interface CopilotSession {
  id: string
  messages: CopilotMessage[]
}

interface CopilotWindowState {
  openSessionIds: string[]
  activeSessionId: string | null
}

export function copilotSessionRelativeDir(skillId: string): string {
  return `${COPILOT_SESSION_ROOT}/${skillId}`
}

export function copilotSessionDirectoryPath(workspaceRoot: string, skillId: string): string {
  const trimmedRoot = workspaceRoot.replace(/[\\/]+$/, '')
  const separator = trimmedRoot.includes('\\') ? '\\' : '/'
  return `${trimmedRoot}${separator}${copilotSessionRelativeDir(skillId).replace(/\//g, separator)}`
}

function normalizePath(path: string): string {
  return path.trim().replace(/\\/g, '/').replace(/\/+$/, '')
}

function comparePath(path: string, caseInsensitive: boolean): string {
  return caseInsensitive ? path.toLowerCase() : path
}

function workspaceRelativePath(workspaceRoot: string, absolutePath: string): string | null {
  const root = normalizePath(workspaceRoot)
  const target = normalizePath(absolutePath)
  const caseInsensitive = /^[a-zA-Z]:\//.test(root) || root.startsWith('//')
  const cmpRoot = comparePath(root, caseInsensitive)
  const cmpTarget = comparePath(target, caseInsensitive)
  if (!cmpTarget.startsWith(`${cmpRoot}/`)) {
    return null
  }
  return target.slice(root.length + 1)
}

export function selectedCopilotSessionRelativePath(
  workspaceRoot: string,
  skillId: string,
  absolutePath: string,
): string | null {
  const relative = workspaceRelativePath(workspaceRoot, absolutePath)
  if (!relative) {
    return null
  }
  const dir = copilotSessionRelativeDir(skillId)
  if (!relative.startsWith(`${dir}/`)) {
    return null
  }
  const fileName = relative.slice(dir.length + 1)
  if (!fileName.endsWith('.json') || fileName.startsWith('_') || fileName.includes('/')) {
    return null
  }
  return relative
}

function sessionPath(skillId: string, sessionId: string): string {
  return `${copilotSessionRelativeDir(skillId)}/${sessionId}.json`
}

function windowStatePath(skillId: string): string {
  return `${copilotSessionRelativeDir(skillId)}/_window.json`
}

function isCopilotSession(value: unknown): value is CopilotSession {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as { id?: unknown; messages?: unknown }
  return typeof candidate.id === 'string' && Array.isArray(candidate.messages)
}

function isCopilotWindowState(value: unknown): value is CopilotWindowState {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as { openSessionIds?: unknown; activeSessionId?: unknown }
  return (
    Array.isArray(candidate.openSessionIds) &&
    candidate.openSessionIds.every((id) => typeof id === 'string') &&
    (candidate.activeSessionId === null || typeof candidate.activeSessionId === 'string')
  )
}

function normalizeWindowState(value: CopilotWindowState): CopilotWindowState {
  const openSessionIds: string[] = []
  const seen = new Set<string>()
  for (const id of value.openSessionIds) {
    if (id && !seen.has(id)) {
      seen.add(id)
      openSessionIds.push(id)
    }
  }
  const activeSessionId =
    value.activeSessionId && seen.has(value.activeSessionId) ? value.activeSessionId : openSessionIds.at(-1) ?? null
  return { openSessionIds, activeSessionId }
}

async function loadWindowState(workspaceId: string, skillId: string): Promise<CopilotWindowState | null> {
  try {
    const result = await readWorkspaceFile(workspaceId, windowStatePath(skillId))
    const parsed: unknown = JSON.parse(result.content)
    if (isCopilotWindowState(parsed)) {
      return normalizeWindowState(parsed)
    }
    console.warn(`copilot: skipping malformed window state for ${skillId}`)
  } catch {
    // Missing state is the first-run shape. Historical transcript files are not
    // window state and must not be auto-opened.
  }
  return null
}

async function loadSessionById(
  workspaceId: string,
  skillId: string,
  sessionId: string,
): Promise<CopilotSession | null> {
  try {
    const result = await readWorkspaceFile(workspaceId, sessionPath(skillId, sessionId))
    const parsed: unknown = JSON.parse(result.content)
    if (isCopilotSession(parsed) && parsed.id === sessionId) {
      return parsed
    }
    console.warn(`copilot: skipping malformed session file ${sessionId}.json`)
  } catch (err: unknown) {
    console.warn(
      `copilot: skipping unreadable session file ${sessionId}.json: ${
        err instanceof Error ? err.message : String(err)
      }`,
    )
  }
  return null
}

function activeForSessions(sessions: CopilotSession[], requested: string | null): string | null {
  if (requested && sessions.some((session) => session.id === requested)) {
    return requested
  }
  return sessions.at(-1)?.id ?? null
}

function windowStateFromSessions(
  sessions: CopilotSession[],
  activeSessionId: string | null,
): CopilotWindowState {
  const openSessionIds = sessions.map((session) => session.id)
  return {
    openSessionIds,
    activeSessionId: activeForSessions(sessions, activeSessionId),
  }
}

async function writeWindowState(
  workspaceId: string,
  skillId: string,
  sessions: CopilotSession[],
  activeSessionId: string | null,
): Promise<void> {
  await ensureWorkspaceSupportDirs(workspaceId)
  await writeWorkspaceFile(
    workspaceId,
    windowStatePath(skillId),
    JSON.stringify(windowStateFromSessions(sessions, activeSessionId), null, 2),
  )
}

function persistWindowState(
  workspaceId: string,
  skillId: string,
  sessions: CopilotSession[],
  activeSessionId: string | null,
): void {
  const sessionsSnapshot = sessions.map((session) => ({ ...session, messages: session.messages }))
  void writeWindowState(workspaceId, skillId, sessionsSnapshot, activeSessionId).catch((err: unknown) => {
    state.persistenceError = err instanceof Error ? err.message : String(err)
    emit()
  })
}

async function persistSessionToDisk(
  workspaceId: string,
  skillId: string,
  session: CopilotSession,
): Promise<void> {
  try {
    await ensureWorkspaceSupportDirs(workspaceId)
    await writeWorkspaceFile(workspaceId, sessionPath(skillId, session.id), JSON.stringify(session, null, 2))
    state.persistenceError = null
  } catch (err: unknown) {
    state.persistenceError = err instanceof Error ? err.message : String(err)
  }
  emit()
}

function selectedSessionId(relativePath: string): string {
  const fileName = relativePath.slice(relativePath.lastIndexOf('/') + 1)
  return fileName.slice(0, -'.json'.length)
}

function contextKey(workspaceId: string, skillId: string): string {
  return `${workspaceId}::${skillId}`
}

export interface CopilotState {
  workspaceId: string | null
  skillId: string | null
  sessions: CopilotSession[]
  activeSessionId: string | null
  persistenceError: string | null
  messages: CopilotMessage[]
}

const state: Omit<CopilotState, 'messages'> = {
  workspaceId: null,
  skillId: null,
  sessions: [],
  activeSessionId: null,
  persistenceError: null,
}

const sessionsByContext: Record<string, CopilotSession[]> = {}
const activeByContext: Record<string, string | null> = {}
const hydratedKeys = new Set<string>()
const listeners = new Set<Listener>()

let cachedSnapshot: CopilotState | null = null

function emit() {
  cachedSnapshot = null
  listeners.forEach((listener) => listener())
}

function syncCurrentContext() {
  if (state.workspaceId && state.skillId) {
    const key = contextKey(state.workspaceId, state.skillId)
    sessionsByContext[key] = state.sessions
    activeByContext[key] = state.activeSessionId
  }
}

function replaceSessions(sessions: CopilotSession[], requestedActiveId: string | null) {
  state.sessions = sessions
  state.activeSessionId = activeForSessions(sessions, requestedActiveId)
  syncCurrentContext()
}

export const copilotStore = {
  getSnapshot(): CopilotState {
    if (!cachedSnapshot) {
      const activeSession = state.sessions.find((s) => s.id === state.activeSessionId)
      cachedSnapshot = {
        ...state,
        messages: activeSession ? activeSession.messages : [],
      }
    }
    return cachedSnapshot
  },
  subscribe(listener: Listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  setContext(workspaceId: string | null, skillId: string | null) {
    state.workspaceId = workspaceId
    state.skillId = skillId
    if (workspaceId && skillId) {
      const key = contextKey(workspaceId, skillId)
      state.sessions = sessionsByContext[key] || []
      state.activeSessionId = activeForSessions(state.sessions, activeByContext[key] ?? null)
    } else {
      state.sessions = []
      state.activeSessionId = null
    }
    state.persistenceError = null
    emit()
  },
  async hydrate(workspaceId: string, skillId: string): Promise<void> {
    const key = contextKey(workspaceId, skillId)
    if (hydratedKeys.has(key)) return
    hydratedKeys.add(key)

    const windowState = await loadWindowState(workspaceId, skillId)
    if (!windowState) {
      return
    }

    const memById = new Map((sessionsByContext[key] ?? []).map((session) => [session.id, session]))
    const restoredSessions: CopilotSession[] = []
    for (const sessionId of windowState.openSessionIds) {
      const inMemory = memById.get(sessionId)
      if (inMemory) {
        restoredSessions.push(inMemory)
        continue
      }
      const fromDisk = await loadSessionById(workspaceId, skillId, sessionId)
      if (fromDisk) {
        restoredSessions.push(fromDisk)
      }
    }

    const restoredActiveId = activeForSessions(restoredSessions, windowState.activeSessionId)
    sessionsByContext[key] = restoredSessions
    activeByContext[key] = restoredActiveId
    if (state.workspaceId === workspaceId && state.skillId === skillId) {
      replaceSessions(restoredSessions, restoredActiveId)
      emit()
    }
  },
  newSession(): string {
    const newId = `session-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    const newSession: CopilotSession = { id: newId, messages: [] }
    replaceSessions([...state.sessions, newSession], newId)
    if (state.workspaceId && state.skillId) {
      void persistSessionToDisk(state.workspaceId, state.skillId, newSession)
      persistWindowState(state.workspaceId, state.skillId, state.sessions, state.activeSessionId)
    }
    emit()
    return newId
  },
  switchSession(id: string) {
    if (!state.sessions.some((session) => session.id === id)) {
      return
    }
    state.activeSessionId = id
    syncCurrentContext()
    if (state.workspaceId && state.skillId) {
      persistWindowState(state.workspaceId, state.skillId, state.sessions, id)
    }
    emit()
  },
  async closeSession(id: string) {
    const index = state.sessions.findIndex((session) => session.id === id)
    if (index < 0) {
      return
    }
    const closedActive = state.activeSessionId === id
    const nextSessions = state.sessions.filter((session) => session.id !== id)
    const nextActiveId = closedActive
      ? nextSessions[Math.min(Math.max(index - 1, 0), nextSessions.length - 1)]?.id ?? null
      : state.activeSessionId
    replaceSessions(nextSessions, nextActiveId)

    if (state.sessions.length === 0) {
      emit()
      this.newSession()
      return
    }

    if (state.workspaceId && state.skillId) {
      persistWindowState(state.workspaceId, state.skillId, state.sessions, state.activeSessionId)
    }
    emit()
  },
  async restoreSessionFromFile(absolutePath: string): Promise<boolean> {
    if (!state.workspaceId || !state.skillId) {
      state.persistenceError = 'No current skill is available for Copilot session restore.'
      emit()
      return false
    }
    const relativePath = selectedCopilotSessionRelativePath(state.workspaceId, state.skillId, absolutePath)
    if (!relativePath) {
      state.persistenceError = 'Choose a Copilot session file from the current skill session directory.'
      emit()
      return false
    }

    try {
      const result = await readWorkspaceFile(state.workspaceId, relativePath)
      const parsed: unknown = JSON.parse(result.content)
      if (!isCopilotSession(parsed)) {
        throw new Error('Selected file is not a Copilot session.')
      }
      const expectedId = selectedSessionId(relativePath)
      if (parsed.id !== expectedId) {
        throw new Error(`Selected filename does not match stored session id: ${expectedId} != ${parsed.id}`)
      }
      const alreadyOpen = state.sessions.some((session) => session.id === parsed.id)
      replaceSessions(alreadyOpen ? state.sessions : [...state.sessions, parsed], parsed.id)
      persistWindowState(state.workspaceId, state.skillId, state.sessions, state.activeSessionId)
      state.persistenceError = null
      emit()
      return true
    } catch (err: unknown) {
      state.persistenceError = err instanceof Error ? err.message : String(err)
      emit()
      return false
    }
  },
  async appendMessage(message: CopilotMessage) {
    state.sessions = state.sessions.map((s) => {
      if (s.id === state.activeSessionId) {
        return { ...s, messages: [...s.messages, message] }
      }
      return s
    })
    syncCurrentContext()
    emit()

    const activeSession = state.sessions.find((s) => s.id === state.activeSessionId)
    if (state.workspaceId && state.skillId && activeSession) {
      await persistSessionToDisk(state.workspaceId, state.skillId, activeSession)
    }
  },
  updateMessage(messageId: string, updater: (message: CopilotMessage) => CopilotMessage) {
    state.sessions = state.sessions.map((s) => {
      if (s.id === state.activeSessionId) {
        return {
          ...s,
          messages: s.messages.map((m) => (m.id === messageId ? updater(m) : m)),
        }
      }
      return s
    })
    syncCurrentContext()
    emit()

    const activeSession = state.sessions.find((s) => s.id === state.activeSessionId)
    const updatedMessage = activeSession?.messages.find((m) => m.id === messageId)
    if (
      state.workspaceId &&
      state.skillId &&
      activeSession &&
      updatedMessage &&
      updatedMessage.status !== 'running' &&
      updatedMessage.status !== 'pending'
    ) {
      void persistSessionToDisk(state.workspaceId, state.skillId, activeSession)
    }
  },
  clearMessages() {
    state.sessions = state.sessions.map((s) => {
      if (s.id === state.activeSessionId) {
        return { ...s, messages: [] }
      }
      return s
    })
    syncCurrentContext()
    emit()
  },
  reset(skillId: string | null) {
    state.skillId = skillId
    state.sessions = []
    state.activeSessionId = null
    state.persistenceError = null
    for (const key in sessionsByContext) {
      delete sessionsByContext[key]
    }
    for (const key in activeByContext) {
      delete activeByContext[key]
    }
    hydratedKeys.clear()
    emit()
  },
}

if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).copilotStore = copilotStore
}
