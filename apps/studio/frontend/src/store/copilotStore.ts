import type { CopilotMessage } from '../types/copilot'
import { writeWorkspaceFile, ensureWorkspaceSupportDirs } from '../lib/tauri'

type Listener = () => void

export interface CopilotSession {
  id: string
  messages: CopilotMessage[]
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
    emit()
  },
}

if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).copilotStore = copilotStore
}
