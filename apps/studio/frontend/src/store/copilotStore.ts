import type { CopilotMessage } from '../types/copilot'
import {
  writeWorkspaceFile,
  ensureWorkspaceSupportDirs,
  readWorkspaceFile,
  listWorkspaceDir,
} from '../lib/tauri'

type Listener = () => void

export interface CopilotSession {
  id: string
  messages: CopilotMessage[]
}

function sessionsDir(skillId: string): string {
  return `.gemini/copilot/sessions/${skillId}`
}

function isCopilotSession(value: unknown): value is CopilotSession {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as { id?: unknown; messages?: unknown }
  return typeof candidate.id === 'string' && Array.isArray(candidate.messages)
}

/**
 * Load every persisted session for a workspace/skill from disk via the native
 * read commands. Non-Tauri runtimes return an empty list (listWorkspaceDir is a
 * no-op there), so this is inert in web/test builds. A single corrupt session
 * file is skipped with a warning rather than aborting the whole hydrate —
 * losing one history shouldn't hide the rest.
 */
export async function loadCopilotSessionsFromDisk(
  workspaceId: string,
  skillId: string,
): Promise<CopilotSession[]> {
  const dir = sessionsDir(skillId)
  const entries = await listWorkspaceDir(workspaceId, dir)
  const sessions: CopilotSession[] = []
  for (const entry of entries) {
    if (entry.kind !== 'file' || !entry.name.endsWith('.json')) continue
    try {
      const result = await readWorkspaceFile(workspaceId, `${dir}/${entry.name}`)
      const parsed: unknown = JSON.parse(result.content)
      if (isCopilotSession(parsed)) {
        sessions.push(parsed)
      } else {
        console.warn(`copilot: skipping malformed session file ${entry.name}`)
      }
    } catch (err: unknown) {
      console.warn(
        `copilot: skipping unreadable session file ${entry.name}: ${
          err instanceof Error ? err.message : String(err)
        }`,
      )
    }
  }
  return sessions
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

// Contexts already hydrated from disk this process — so we hit the filesystem
// at most once per workspace/skill, not on every context switch.
const hydratedKeys = new Set<string>()

const listeners = new Set<Listener>()

let cachedSnapshot: CopilotState | null = null

function emit() {
  cachedSnapshot = null
  listeners.forEach((listener) => listener())
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
      const key = `${workspaceId}::${skillId}`
      state.sessions = sessionsByContext[key] || []
    } else {
      state.sessions = []
    }
    state.activeSessionId = state.sessions.length > 0
      ? state.sessions[state.sessions.length - 1].id
      : null
    state.persistenceError = null
    emit()
  },
  /**
   * Cold-start recovery (copilot F2): load any sessions persisted to disk for
   * this workspace/skill and merge them into the in-memory store. In-memory
   * sessions win on id collision (they carry the live, still-streaming
   * messages); disk-only sessions are restored so a restart no longer wipes
   * history. Idempotent per context — disk is read at most once per process.
   */
  async hydrate(workspaceId: string, skillId: string): Promise<void> {
    const key = `${workspaceId}::${skillId}`
    if (hydratedKeys.has(key)) return
    hydratedKeys.add(key)

    let diskSessions: CopilotSession[]
    try {
      diskSessions = await loadCopilotSessionsFromDisk(workspaceId, skillId)
    } catch (err: unknown) {
      // Transient read failure — allow a later retry and surface it.
      hydratedKeys.delete(key)
      state.persistenceError = err instanceof Error ? err.message : String(err)
      emit()
      return
    }
    if (diskSessions.length === 0) return

    const memSessions = sessionsByContext[key] ?? []
    const byId = new Map<string, CopilotSession>()
    for (const session of diskSessions) byId.set(session.id, session)
    for (const session of memSessions) byId.set(session.id, session)
    // Session ids embed Date.now(), so lexical sort ≈ chronological.
    const merged = [...byId.values()].sort((a, b) =>
      a.id < b.id ? -1 : a.id > b.id ? 1 : 0,
    )
    sessionsByContext[key] = merged

    // Only touch live state if this is still the active context.
    if (state.workspaceId === workspaceId && state.skillId === skillId) {
      state.sessions = merged
      const activeStillValid =
        state.activeSessionId !== null &&
        merged.some((session) => session.id === state.activeSessionId)
      if (!activeStillValid) {
        state.activeSessionId = merged[merged.length - 1].id
      }
      emit()
    }
  },
  newSession(): string {
    const newId = `session-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
    const newSession: CopilotSession = {
      id: newId,
      messages: [],
    }
    state.sessions = [...state.sessions, newSession]
    state.activeSessionId = newId
    if (state.workspaceId && state.skillId) {
      const key = `${state.workspaceId}::${state.skillId}`
      sessionsByContext[key] = state.sessions
    }
    emit()
    return newId
  },
  switchSession(id: string) {
    state.activeSessionId = id
    emit()
  },
  async appendMessage(message: CopilotMessage) {
    state.sessions = state.sessions.map((s) => {
      if (s.id === state.activeSessionId) {
        return { ...s, messages: [...s.messages, message] }
      }
      return s
    })
    if (state.workspaceId && state.skillId) {
      const key = `${state.workspaceId}::${state.skillId}`
      sessionsByContext[key] = state.sessions
    }
    emit()

    const activeSession = state.sessions.find((s) => s.id === state.activeSessionId)
    if (state.workspaceId && state.skillId && activeSession) {
      try {
        await ensureWorkspaceSupportDirs(state.workspaceId)
        const relativePath = `.gemini/copilot/sessions/${state.skillId}/${activeSession.id}.json`
        await writeWorkspaceFile(
          state.workspaceId,
          relativePath,
          JSON.stringify(activeSession, null, 2)
        )
        state.persistenceError = null
      } catch (err: unknown) {
        state.persistenceError = err instanceof Error ? err.message : String(err)
      }
      emit()
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
    if (state.workspaceId && state.skillId) {
      const key = `${state.workspaceId}::${state.skillId}`
      sessionsByContext[key] = state.sessions
    }
    emit()
  },
  clearMessages() {
    state.sessions = state.sessions.map((s) => {
      if (s.id === state.activeSessionId) {
        return { ...s, messages: [] }
      }
      return s
    })
    if (state.workspaceId && state.skillId) {
      const key = `${state.workspaceId}::${state.skillId}`
      sessionsByContext[key] = state.sessions
    }
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
    hydratedKeys.clear()
    emit()
  },
}

if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).copilotStore = copilotStore
}
