import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import i18n from '../i18n'
import { toast } from 'sonner'
import { closeCopilotSession, interruptCopilot, wsUrl } from '../api/client'
import { nextBackoffMs } from '../lib/websocket'
import { selectFile } from '../lib/tauri'
import { copilotSessionDirectoryPath, copilotStore } from '../store/copilotStore'
import type {
  CopilotEvent,
  CopilotImageAttachment,
  CopilotMention,
  CopilotMessage,
  CopilotTextDeltaEvent,
  CopilotThinkingDeltaEvent,
} from '../types/copilot'
import { normalizeCopilotEvent, readToolApprovalExpiry } from '../types/copilot'
import type { CopilotAttachmentRecord } from '../types/copilot'
import { decodedByteLength } from '../components/copilot/composer/attachment-intake'
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
  // 会话身份契约(COPILOT_ASSIST-5):消息归属的前端会话标签;后端以
  // (skill, session) 隔离 SDK 对话,缺失会被边界拒绝(ws close 4400)。
  session_id: string
  model_override?: string
  role?: string
  workspace_root?: string
  judge_context?: CopilotJudgeContext
  // F4 ②: the objects the user picked in THIS composer, and the images they
  // attached to THIS message. Nothing else may ride along — no current
  // selection, no recently-opened file (F4 ③).
  mentions?: CopilotMention[]
  attachments?: CopilotImageAttachment[]
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

/** Everything a turn may carry besides the message itself. */
export interface CopilotSendOptions {
  modelOverride?: string | null
  role?: string | null
  workspaceRoot?: string | null
  judgeContext?: CopilotJudgeContext | null
  mentions?: CopilotMention[]
  attachments?: CopilotImageAttachment[]
}

/** Build the ws send payload, attaching each optional field only when present. */
export function buildCopilotSendPayload(
  userMessage: string,
  sessionId: string,
  options: CopilotSendOptions = {},
): CopilotSendPayload {
  const payload: CopilotSendPayload = { user_message: userMessage, session_id: sessionId }
  if (options.modelOverride) {
    payload.model_override = options.modelOverride
  }
  if (options.role) {
    payload.role = options.role
  }
  const trimmedWorkspaceRoot = options.workspaceRoot?.trim()
  if (trimmedWorkspaceRoot) {
    payload.workspace_root = trimmedWorkspaceRoot
  }
  if (options.judgeContext) {
    payload.judge_context = options.judgeContext
  }
  if (options.mentions?.length) {
    payload.mentions = options.mentions
  }
  if (options.attachments?.length) {
    payload.attachments = options.attachments
  }
  return payload
}

/**
 * Whether this turn is worth delivering.
 *
 * The single authority on the question, shared by the send button, the send
 * handler and the socket write — three places that each used to decide it
 * alone, which is how the composer came to light a send button for a turn the
 * socket layer then silently dropped.
 */
export function turnCarriesSomething(
  content: string,
  attachments: CopilotImageAttachment[] = [],
): boolean {
  return content.trim().length > 0 || attachments.length > 0
}

/**
 * What the transcript remembers about the images a turn carried.
 *
 * Descriptors only: the session file is rewritten in full on every message, so
 * keeping the base64 would add megabytes per turn to a file no reader ever
 * wants the bytes from — the image itself has already reached the model.
 */
export function recordedAttachments(
  attachments: CopilotImageAttachment[] | undefined,
): CopilotAttachmentRecord[] | undefined {
  if (!attachments?.length) {
    return undefined
  }
  return attachments.map((attachment) => ({
    mediaType: attachment.media_type,
    name: attachment.name,
    byteSize: decodedByteLength(attachment.data),
  }))
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
  // R7-I: true while a turn is streaming, so the composer shows a stop button.
  const [isStreaming, setIsStreaming] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const assistantMessageIdRef = useRef<string | null>(null)
  const deltaQueueRef = useRef<Array<{ messageId: string, event: CopilotDeltaEvent }>>([])
  // 会话身份契约(COPILOT_ASSIST-5):每次发送把归属会话 id 入队;后端在一条
  // 连接内串行处理查询,所以流式事件按 FIFO 归属队首会话,与"当前激活标签"
  // 无关——切标签不串流。done/error 结束一轮时出队。
  const pendingQuerySessionsRef = useRef<string[]>([])

  const appendAssistantEvent = useCallback((event: CopilotEvent) => {
    let messageId = assistantMessageIdRef.current
    if (!messageId) {
      const message = createMessage('assistant', '', 'running')
      messageId = message.id
      assistantMessageIdRef.current = messageId
      const owningSessionId = pendingQuerySessionsRef.current[0] ?? copilotStore.ensureActiveSession()
      void copilotStore.appendMessage(message, owningSessionId)
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
      pendingQuerySessionsRef.current.shift()
      setIsStreaming(false)
    }
  }, [])

  const workspaceRoot = workspaceRootOverride?.trim() || resolveWorkspaceIdentity(skillId).workspaceRoot || ''

  useEffect(() => {
    if (!skillId) {
      copilotStore.reset(null)
      return
    }
    if (workspaceRoot) {
      // Multi-session context: load the persisted window for this workspace/skill
      // pair. Empty state is valid; the draft materializes only on first send.
      copilotStore.setContext(workspaceRoot, skillId)
      // Cold-start recovery (F2): restore only the last persisted window state
      // (`_window.json`). Historical transcript files stay on disk but are not
      // auto-opened unless the user chooses Restore chat.
      let cancelled = false
      void copilotStore.hydrate(workspaceRoot, skillId).finally(() => {
        if (cancelled) return
      })
      return () => {
        cancelled = true
      }
    }
    // Fallback (web / no workspace identity): keep the chat empty until the
    // first outgoing/incoming message materializes an in-memory session.
    if (snapshot.skillId !== skillId) {
      copilotStore.reset(skillId)
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
        const record = JSON.parse(String(message.data)) as unknown
        // An expired hold is not a new thing to show — it is the ending of a
        // card already on screen, so it settles that card instead of appending
        // below it. Appending would leave the original still saying "Waiting
        // for approval." with live buttons, which is the state this event
        // exists to end (problem ledger CP7).
        const expiry = readToolApprovalExpiry(record)
        if (expiry) {
          copilotStore.timeOutToolApproval(expiry)
          return
        }
        appendAssistantEvent(normalizeCopilotEvent(record, nextId('event')))
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
      pendingQuerySessionsRef.current = []
    }
  }, [skillId, appendAssistantEvent])

  const sendMessage = useCallback((
    content: string,
    options: Omit<CopilotSendOptions, 'workspaceRoot'> = {},
  ) => {
    const trimmed = content.trim()
    if (
      !turnCarriesSomething(trimmed, options.attachments)
      || !socketRef.current
      || socketRef.current.readyState !== WebSocket.OPEN
    ) {
      return false
    }

    const sessionId = copilotStore.ensureActiveSession()
    assistantMessageIdRef.current = null
    pendingQuerySessionsRef.current.push(sessionId)
    void copilotStore.appendMessage(
      { ...createMessage('user', trimmed, 'success'), attachments: recordedAttachments(options.attachments) },
      sessionId,
    )
    socketRef.current.send(JSON.stringify(buildCopilotSendPayload(trimmed, sessionId, { ...options, workspaceRoot })))
    setIsStreaming(true)
    return true
  }, [workspaceRoot])

  // R7-I stop button: interrupt the active turn via the SDK-native backend
  // endpoint. The interrupted turn ends its stream (a done event), which also
  // clears isStreaming — so the composer flips back to send on its own.
  const interrupt = useCallback(async () => {
    if (!skillId) {
      return
    }
    try {
      await interruptCopilot(skillId)
    } catch {
      // Best-effort stop: if the request fails the turn keeps streaming and the
      // next terminal event still settles the UI; nothing extra to surface.
    }
  }, [skillId])

  const restoreSession = useCallback(async () => {
    if (!skillId || !workspaceRoot) {
      toast.error(i18n.t('toast.noWorkspace', { ns: 'copilot' }))
      return
    }
    const selectedPath = await selectFile(copilotSessionDirectoryPath(workspaceRoot, skillId))
    if (!selectedPath) {
      return
    }
    const restored = await copilotStore.restoreSessionFromFile(selectedPath)
    if (!restored) {
      toast.error(i18n.t('toast.restoreFailed', { ns: 'copilot' }), {
        description: copilotStore.getSnapshot().persistenceError ?? undefined,
      })
    }
  }, [skillId, workspaceRoot])

  return {
    messages: snapshot.messages,
    connectionStatus,
    reconnectInMs,
    lastError: visibleCopilotSocketError(connectionStatus, lastError),
    sendMessage,
    isStreaming,
    interrupt,
    clearMessages: copilotStore.clearMessages,
    persistenceError: snapshot.persistenceError,
    activeSessionId: snapshot.activeSessionId,
    sessions: snapshot.sessions,
    newSession: () => copilotStore.newSession(),
    restoreSession,
    switchSession: (id: string) => copilotStore.switchSession(id),
    closeSession: (id: string) => {
      // 关标签 = 结束它的后端 SDK 对话(每条对话一个 CLI 子进程)。尽力而为:
      // 调用失败时 ws 断连的 reset_session 仍会兜底回收整个 skill 的会话。
      if (skillId) {
        void closeCopilotSession(skillId, id).catch(() => undefined)
      }
      void copilotStore.closeSession(id)
    },
  }
}

export type CopilotController = ReturnType<typeof useCopilot>
