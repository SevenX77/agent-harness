import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { wsUrl } from '../api/client'
import { nextBackoffMs } from '../lib/websocket'
import { copilotStore } from '../store/copilotStore'
import type { CopilotEvent, CopilotMessage } from '../types/copilot'
import { normalizeCopilotEvent } from '../types/copilot'
import { resolveWorkspaceIdentity } from '../components/studio/workspace-identity'

type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'reconnecting' | 'error'

let messageIdFallbackCounter = 0

function nextId(prefix: string) {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  messageIdFallbackCounter += 1
  return `${prefix}-${Date.now()}-${messageIdFallbackCounter}`
}

export interface CopilotSendPayload {
  user_message: string
  model_override?: string
  role?: string
  workspace_root?: string
  judge_context?: CopilotJudgeContext
}

export interface CopilotJudgeContext {
  compare_result_ref: string
  judge_context_ref: string
  baseline_ref: string
  diff_summary: {
    baseline_id: string
    run_results_ref: string
    total_score: number
    node_group_count: number
    failed_node_count: number
  }
}

/** Build the ws send payload, attaching model_override / role only when present. */
export function buildCopilotSendPayload(
  userMessage: string,
  modelOverride?: string | null,
  role?: string | null,
  workspaceRoot?: string | null,
  judgeContext?: CopilotJudgeContext | null,
): CopilotSendPayload {
  const payload: CopilotSendPayload = { user_message: userMessage }
  if (modelOverride) {
    payload.model_override = modelOverride
  }
  if (role) {
    payload.role = role
  }
  const trimmedWorkspaceRoot = workspaceRoot?.trim()
  if (trimmedWorkspaceRoot) {
    payload.workspace_root = trimmedWorkspaceRoot
  }
  if (judgeContext) {
    payload.judge_context = judgeContext
  }
  return payload
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

/**
 * Drain queued text deltas into the store, coalescing by message. Shared by the
 * 75ms flush timer and the terminal-event path: draining before applying
 * done/error guarantees the persisted snapshot (R16/D8) includes every trailing
 * text token, not just whatever happened to flush before the turn settled.
 */
function flushTextQueue(
  queue: Array<{ messageId: string; content: string; event: CopilotEvent }>,
): void {
  if (queue.length === 0) {
    return
  }
  const batch = queue.splice(0)
  const byMessage = new Map<string, { content: string; events: CopilotEvent[] }>()
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
}

export function useCopilot(skillId: string | null, workspaceRootOverride?: string | null) {
  const snapshot = useSyncExternalStore(copilotStore.subscribe, copilotStore.getSnapshot)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [reconnectInMs, setReconnectInMs] = useState<number | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const assistantMessageIdRef = useRef<string | null>(null)
  const textQueueRef = useRef<Array<{ messageId: string, content: string, event: CopilotEvent }>>([])

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
      // Terminal events (done/error) trigger an on-disk flush in the store. Drain
      // any still-queued text deltas first so the persisted transcript carries the
      // complete assistant answer, not a truncated one (R16/D8).
      if (event.type === 'done' || event.type === 'error') {
        flushTextQueue(textQueueRef.current)
      }
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

  const workspaceRoot = workspaceRootOverride?.trim() || resolveWorkspaceIdentity(skillId).workspaceRoot || ''

  useEffect(() => {
    if (!skillId) {
      return
    }
    if (workspaceRoot) {
      // Multi-session context: load (or create) sessions for this workspace/skill pair.
      copilotStore.setContext(workspaceRoot, skillId)
      // Cold-start recovery (F2): pull any disk-persisted sessions first, and
      // only mint a fresh session if none survive on disk — otherwise a restart
      // would silently discard prior conversations.
      let cancelled = false
      void copilotStore.hydrate(workspaceRoot, skillId).finally(() => {
        if (cancelled) return
        if (copilotStore.getSnapshot().sessions.length === 0) {
          copilotStore.newSession()
        }
      })
      return () => {
        cancelled = true
      }
    }
    // Fallback (web / no workspace identity): main's single-session reset on skill change.
    if (snapshot.skillId !== skillId) {
      copilotStore.reset(skillId)
      copilotStore.newSession()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skillId, workspaceRoot])

  useEffect(() => {
    if (!skillId) {
      setConnectionStatus('idle')
      return undefined
    }

    let closed = false
    let attempt = 0
    let reconnectTimer: number | undefined

    const flushTimer = window.setInterval(() => {
      flushTextQueue(textQueueRef.current)
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
  }, [skillId, appendAssistantEvent])

  const sendMessage = useCallback((
    content: string,
    modelOverride?: string | null,
    role?: string | null,
    judgeContext?: CopilotJudgeContext | null,
  ) => {
    const trimmed = content.trim()
    if (!trimmed || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      return false
    }

    assistantMessageIdRef.current = null
    copilotStore.appendMessage(createMessage('user', trimmed, 'success'))
    socketRef.current.send(JSON.stringify(buildCopilotSendPayload(trimmed, modelOverride, role, workspaceRoot, judgeContext)))
    return true
  }, [workspaceRoot])

  return {
    messages: snapshot.messages,
    connectionStatus,
    reconnectInMs,
    lastError,
    sendMessage,
    clearMessages: copilotStore.clearMessages,
    persistenceError: snapshot.persistenceError,
    activeSessionId: snapshot.activeSessionId,
    sessions: snapshot.sessions,
    newSession: () => copilotStore.newSession(),
    switchSession: (id: string) => copilotStore.switchSession(id),
  }
}
