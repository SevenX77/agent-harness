import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { wsUrl } from '../api/client'
import { nextBackoffMs } from '../lib/websocket'
import { copilotStore } from '../store/copilotStore'
import type { CopilotEvent, CopilotMessage } from '../types/copilot'
import { normalizeCopilotEvent } from '../types/copilot'

type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'reconnecting' | 'error'

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

export function useCopilot(skillId: string | null) {
  const snapshot = useSyncExternalStore(copilotStore.subscribe, copilotStore.getSnapshot)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [reconnectInMs, setReconnectInMs] = useState<number | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const assistantMessageIdRef = useRef<string | null>(null)
  const textQueueRef = useRef<Array<{ messageId: string, content: string, event: CopilotEvent }>>([])

  useEffect(() => {
    if (snapshot.skillId !== skillId) {
      copilotStore.reset(skillId)
    }
  }, [skillId, snapshot.skillId])

  useEffect(() => {
    if (!skillId) {
      setConnectionStatus('idle')
      return undefined
    }

    let closed = false
    let attempt = 0
    let reconnectTimer: number | undefined

    const flushTimer = window.setInterval(() => {
      if (textQueueRef.current.length === 0) {
        return
      }
      const batch = textQueueRef.current.splice(0)
      const byMessage = new Map<string, { content: string, events: CopilotEvent[] }>()
      batch.forEach((item) => {
        const current = byMessage.get(item.messageId) ?? { content: '', events: [] }
        current.content += item.content
        current.events.push(item.event)
        byMessage.set(item.messageId, current)
      })
      byMessage.forEach((value, messageId) => {
        copilotStore.updateMessage(messageId, (message) => ({
          ...message,
          content: `${message.content}${value.content}`,
          status: 'running',
          events: [...message.events, ...value.events],
        }))
      })
    }, 75)

    const connect = () => {
      attempt += 1
      setConnectionStatus(attempt === 1 ? 'connecting' : 'reconnecting')
      setReconnectInMs(null)
      const socket = new WebSocket(wsUrl(`/api/skills/${skillId}/copilot/ws`))
      socketRef.current = socket

      socket.onopen = () => {
        attempt = 0
        setConnectionStatus('open')
        setReconnectInMs(null)
        setLastError(null)
      }
      socket.onerror = () => {
        setConnectionStatus('error')
        setLastError('Copilot WebSocket failed')
      }
      socket.onclose = () => {
        if (closed) {
          setConnectionStatus('closed')
          return
        }
        const delay = nextBackoffMs(attempt + 1)
        setConnectionStatus('reconnecting')
        setReconnectInMs(delay)
        reconnectTimer = window.setTimeout(connect, delay)
      }
      socket.onmessage = (message) => {
        const event = normalizeCopilotEvent(JSON.parse(String(message.data)) as unknown, nextId('event'))
        appendAssistantEvent(event)
      }
    }

    connect()

    return () => {
      closed = true
      window.clearInterval(flushTimer)
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer)
      }
      socketRef.current?.close()
      socketRef.current = null
      textQueueRef.current = []
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

    if (event.type === 'text_delta') {
      textQueueRef.current.push({ messageId, content: event.content, event })
    } else {
      copilotStore.updateMessage(messageId, (message) => ({
        ...message,
        status: event.status,
        events: [...message.events, event],
      }))
    }

    if (event.type === 'done' || event.type === 'error') {
      assistantMessageIdRef.current = null
    }
  }, [])

  const sendMessage = useCallback((content: string, modelOverride?: string | null) => {
    const trimmed = content.trim()
    if (!trimmed || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      return false
    }

    assistantMessageIdRef.current = null
    copilotStore.appendMessage(createMessage('user', trimmed, 'success'))
    const payload: { user_message: string, model_override?: string } = { user_message: trimmed }
    if (modelOverride) {
      payload.model_override = modelOverride
    }
    socketRef.current.send(JSON.stringify(payload))
    return true
  }, [])

  return {
    messages: snapshot.messages,
    connectionStatus,
    reconnectInMs,
    lastError,
    sendMessage,
    clearMessages: copilotStore.clearMessages,
  }
}
