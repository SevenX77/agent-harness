import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { wsUrl } from '../api/client'
import { nextBackoffMs } from '../lib/websocket'
import { copilotStore } from '../store/copilotStore'
import type {
  CopilotEvent,
  CopilotMessage,
  CopilotTextDeltaEvent,
  CopilotThinkingDeltaEvent,
} from '../types/copilot'
import { normalizeCopilotEvent } from '../types/copilot'
import { resolveWorkspaceIdentity } from '../components/studio/workspace-identity'

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'reconnecting' | 'error'

let messageIdFallbackCounter = 0

export function visibleCopilotSocketError(status: ConnectionStatus, transportError: string | null): string | null {
  return status === 'error' ? transportError : null
}

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

/** Token deltas that stream through the 75ms coalescing queue (F8-5). */
export type CopilotDeltaEvent = CopilotTextDeltaEvent | CopilotThinkingDeltaEvent

/**
 * F8-4: the assistant message status is a lifecycle (`running → success|error`)
 * driven ONLY by terminal events. Intermediate events (context_resolved /
 * tool_* / thinking) must not overwrite it — R5 root cause: context_resolved's
 * event-level 'success' flipped the message to success and killed the thinking
 * indicator while the turn was still streaming.
 */
export function assistantMessageAfterEvent(
  message: CopilotMessage,
  event: CopilotEvent,
): CopilotMessage {
  const status: CopilotMessage['status'] =
    event.type === 'done' ? 'success' : event.type === 'error' ? 'error' : message.status
  return { ...message, status, events: [...message.events, event] }
}

/**
 * Drain queued token deltas (text AND thinking, F8-5) into the store,
 * coalescing by message: same-type runs merge into one event, and the first
 * incoming run also merges into the message's trailing event of the same type,
 * so a long streamed answer stays a handful of events instead of one per
 * token. Shared by the 75ms flush timer and the terminal-event path: draining
 * before applying done/error guarantees the persisted snapshot (R16/D8)
 * includes every trailing token.
 */
export function flushDeltaQueue(
  queue: Array<{ messageId: string; event: CopilotDeltaEvent }>,
): void {
  if (queue.length === 0) {
    return
  }
  const batch = queue.splice(0)
  const byMessage = new Map<string, { text: string; events: CopilotDeltaEvent[] }>()
  batch.forEach(({ messageId, event }) => {
    const current = byMessage.get(messageId) ?? { text: '', events: [] }
    const last = current.events[current.events.length - 1]
    if (last && last.type === event.type) {
      current.events[current.events.length - 1] = { ...last, content: last.content + event.content }
    } else {
      current.events.push(event)
    }
    if (event.type === 'text_delta') {
      current.text += event.content
    }
    byMessage.set(messageId, current)
  })
  byMessage.forEach((value, messageId) => {
    copilotStore.updateMessage(messageId, (message) => {
      const events = [...message.events]
      const incoming = [...value.events]
      const tail = events[events.length - 1]
      const head = incoming[0]
      if (
        tail &&
        head &&
        (tail.type === 'text_delta' || tail.type === 'thinking_delta') &&
        tail.type === head.type
      ) {
        events[events.length - 1] = { ...tail, content: tail.content + head.content }
        incoming.shift()
      }
      return {
        ...message,
        content: `${message.content}${value.text}`,
        events: [...events, ...incoming],
      }
    })
  })
}

export function useCopilot(skillId: string | null, workspaceRootOverride?: string | null) {
  const snapshot = useSyncExternalStore(copilotStore.subscribe, copilotStore.getSnapshot)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [reconnectInMs, setReconnectInMs] = useState<number | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const assistantMessageIdRef = useRef<string | null>(null)
  const deltaQueueRef = useRef<Array<{ messageId: string, event: CopilotDeltaEvent }>>([])

  const appendAssistantEvent = useCallback((event: CopilotEvent) => {
    let messageId = assistantMessageIdRef.current
    if (!messageId) {
      const message = createMessage('assistant', '', 'running')
      messageId = message.id
      assistantMessageIdRef.current = messageId
      copilotStore.appendMessage(message)
    }

    if (event.type === 'text_delta' || event.type === 'thinking_delta') {
      deltaQueueRef.current.push({ messageId, event })
    } else {
      // Terminal events (done/error) trigger an on-disk flush in the store. Drain
      // any still-queued deltas first so the persisted transcript carries the
      // complete assistant answer, not a truncated one (R16/D8).
      if (event.type === 'done' || event.type === 'error') {
        flushDeltaQueue(deltaQueueRef.current)
      }
      copilotStore.updateMessage(messageId, (message) => assistantMessageAfterEvent(message, event))
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
      flushDeltaQueue(deltaQueueRef.current)
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
      deltaQueueRef.current = []
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
    lastError: visibleCopilotSocketError(connectionStatus, lastError),
    sendMessage,
    clearMessages: copilotStore.clearMessages,
    persistenceError: snapshot.persistenceError,
    activeSessionId: snapshot.activeSessionId,
    sessions: snapshot.sessions,
    newSession: () => copilotStore.newSession(),
    switchSession: (id: string) => copilotStore.switchSession(id),
    closeSession: (id: string) => { void copilotStore.closeSession(id) },
  }
}
