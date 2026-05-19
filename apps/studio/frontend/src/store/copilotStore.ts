import type { CopilotMessage } from '../types/copilot'

type Listener = () => void

interface CopilotState {
  skillId: string | null
  messages: CopilotMessage[]
}

let state: CopilotState = {
  skillId: null,
  messages: [],
}

const listeners = new Set<Listener>()

function emit() {
  listeners.forEach((listener) => listener())
}

export const copilotStore = {
  getSnapshot: () => state,
  subscribe(listener: Listener) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  reset(skillId: string | null) {
    state = { skillId, messages: [] }
    emit()
  },
  appendMessage(message: CopilotMessage) {
    state = { ...state, messages: [...state.messages, message] }
    emit()
  },
  updateMessage(messageId: string, updater: (message: CopilotMessage) => CopilotMessage) {
    state = {
      ...state,
      messages: state.messages.map((message) => message.id === messageId ? updater(message) : message),
    }
    emit()
  },
  clearMessages() {
    state = { ...state, messages: [] }
    emit()
  },
}
