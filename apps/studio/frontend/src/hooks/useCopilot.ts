import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { wsUrl } from '../api/client'
import { copilotStore } from '../store/copilotStore'
import type { CopilotBackend, CopilotEvent, CopilotMessage } from '../types/copilot'
import { normalizeCopilotEvent } from '../types/copilot'

type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error'

function nextId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createMessage(role: CopilotMessage['role'], content: string, status: CopilotMessage['status']): CopilotMessage {
  return {
    id: nextId(role),
    role,
    content,
    events: [],
    status,
    createdAt: Date.now(),
  }
}

export function useCopilot(skillId: string | null, backend: CopilotBackend = 'claude') {
  const snapshot = useSyncExternalStore(copilotStore.subscribe, copilotStore.getSnapshot)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [lastError, setLastError] = useState<string | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const assistantMessageIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (snapshot.skillId !== skillId || snapshot.backend !== backend) {
      copilotStore.reset(skillId, backend)
    }
  }, [backend, skillId, snapshot.backend, snapshot.skillId])

  useEffect(() => {
    if (!skillId) {
      setConnectionStatus('idle')
      return undefined
    }

    setConnectionStatus('connecting')
    const socket = new WebSocket(wsUrl(`/api/skills/${skillId}/copilot/ws`))
    socketRef.current = socket

    socket.onopen = () => {
      setConnectionStatus('open')
      setLastError(null)
    }
    socket.onerror = () => {
      setConnectionStatus('error')
      setLastError('Copilot WebSocket failed')
    }
    socket.onclose = () => {
      setConnectionStatus('closed')
    }
    socket.onmessage = (message) => {
      const event = normalizeCopilotEvent(JSON.parse(String(message.data)) as unknown, nextId('event'))
      appendAssistantEvent(event)
    }

    return () => {
      socket.close()
      if (socketRef.current === socket) {
        socketRef.current = null
      }
    }
  }, [skillId])

  const appendAssistantEvent = useCallback((event: CopilotEvent) => {
    let messageId = assistantMessageIdRef.current
    if (!messageId) {
      const message = createMessage('assistant', '', 'running')
      messageId = message.id
      assistantMessageIdRef.current = messageId
      copilotStore.appendMessage(message)
    }

    copilotStore.updateMessage(messageId, (message) => ({
      ...message,
      content: event.type === 'text_delta' ? `${message.content}${event.content}` : message.content,
      status: event.status,
      events: [...message.events, event],
    }))

    if (event.type === 'done' || event.type === 'error') {
      assistantMessageIdRef.current = null
    }
  }, [])

  const sendMessage = useCallback((content: string) => {
    const trimmed = content.trim()
    if (!trimmed || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      return false
    }

    assistantMessageIdRef.current = null
    copilotStore.appendMessage(createMessage('user', trimmed, 'success'))
    socketRef.current.send(JSON.stringify({ user_message: trimmed }))
    return true
  }, [])

  return {
    backend: snapshot.backend,
    messages: snapshot.messages,
    connectionStatus,
    lastError,
    sendMessage,
    clearMessages: copilotStore.clearMessages,
    setBackend: copilotStore.setBackend,
  }
}
