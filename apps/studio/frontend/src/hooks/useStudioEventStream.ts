import { useEffect, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react"
import { toast } from "sonner"
import { wsUrl } from "@/api/client"
import {
  isWsAuthRejection,
  nextReconnectDelay,
  shouldGiveUpOnAuthFailures,
  shouldShowConnectionLost,
} from "./event-stream-backoff"

export interface StudioEventStreamCallbacks {
  /** A registry_changed event arrived after credentials truth changed. */
  onRegistryChanged: () => void
  /** A roles_changed event arrived after roles truth changed. */
  onRolesChanged: () => void
  /** An endpoint generation probe reported its currently active model atoms. */
  onLlmProbeActive?: (event: { endpointId: string; activeModelIds: string[] }) => void
}

const CONNECTION_LOST_TICK_MS = 1_000

interface StudioEventStreamOptions {
  enabled?: boolean
}

interface StudioEventStreamState {
  connectionLost: boolean
}

interface StudioEventSubscriber {
  callbacksRef: MutableRefObject<StudioEventStreamCallbacks>
  setConnectionLost: Dispatch<SetStateAction<boolean>>
}

const subscribers = new Map<number, StudioEventSubscriber>()
let nextSubscriberId = 1
let hubConnectionLost = false
let socket: WebSocket | null = null
let reconnectTimer: number | undefined
let openResetTimer: number | undefined
let lostTicker: number | undefined
let attempt = 0
let consecutiveAuthFailures = 0
let gaveUpOnAuth = false
let disconnectedSince: number | null = null
let running = false

function setHubConnectionLost(next: boolean): void {
  if (hubConnectionLost === next) return
  hubConnectionLost = next
  for (const subscriber of subscribers.values()) {
    subscriber.setConnectionLost((current) => (current === next ? current : next))
  }
}

function stopLostTicker(): void {
  if (lostTicker !== undefined) {
    window.clearInterval(lostTicker)
    lostTicker = undefined
  }
}

function evaluateConnectionLost(): void {
  if (!running) return
  const msWithoutConnection = disconnectedSince === null ? 0 : Date.now() - disconnectedSince
  setHubConnectionLost(shouldShowConnectionLost(attempt, msWithoutConnection))
}

function startLostTicker(): void {
  if (lostTicker !== undefined) return
  lostTicker = window.setInterval(evaluateConnectionLost, CONNECTION_LOST_TICK_MS)
}

function resetHubState(): void {
  if (reconnectTimer !== undefined) {
    window.clearTimeout(reconnectTimer)
    reconnectTimer = undefined
  }
  if (openResetTimer !== undefined) {
    window.clearTimeout(openResetTimer)
    openResetTimer = undefined
  }
  stopLostTicker()
  if (socket) {
    socket.onopen = null
    socket.onclose = null
    socket.onerror = null
    socket.onmessage = null
    socket.close()
    socket = null
  }
  attempt = 0
  consecutiveAuthFailures = 0
  gaveUpOnAuth = false
  disconnectedSince = null
  setHubConnectionLost(false)
}

function dispatchEvent(event: { type?: string } & Record<string, unknown>): void {
  if (event.type === "registry_changed") {
    console.info("phase=studio-event-stream action=dispatch type=registry_changed")
    for (const subscriber of subscribers.values()) {
      subscriber.callbacksRef.current.onRegistryChanged()
    }
    return
  }
  if (event.type === "roles_changed") {
    console.info("phase=studio-event-stream action=dispatch type=roles_changed")
    for (const subscriber of subscribers.values()) {
      subscriber.callbacksRef.current.onRolesChanged()
    }
    return
  }
  if (event.type === "llm_probe_active") {
    const endpointId = typeof event.endpoint_id === "string" ? event.endpoint_id : ""
    const activeModelIds = Array.isArray(event.active_model_ids)
      ? event.active_model_ids.filter((item): item is string => typeof item === "string" && item.length > 0)
      : []
    if (!endpointId) return
    console.info(
      "phase=studio-event-stream action=dispatch type=llm_probe_active endpoint_id=%s active=%d",
      endpointId,
      activeModelIds.length,
    )
    for (const subscriber of subscribers.values()) {
      subscriber.callbacksRef.current.onLlmProbeActive?.({ endpointId, activeModelIds })
    }
  }
}

function giveUpOnAuth(): void {
  gaveUpOnAuth = true
  stopLostTicker()
  setHubConnectionLost(true)
  console.error(
    "phase=studio-event-stream action=give-up reason=auth-rejected-threshold consecutive=%d",
    consecutiveAuthFailures,
  )
  toast.error("与 sidecar 连接已断开，请重启 Studio")
}

function scheduleReconnect(): void {
  if (!running || gaveUpOnAuth || subscribers.size === 0) return
  const delay = nextReconnectDelay(attempt)
  console.warn(
    "phase=studio-event-stream action=schedule-reconnect attempt=%d delay_ms=%d",
    attempt + 1,
    delay,
  )
  attempt += 1
  startLostTicker()
  evaluateConnectionLost()
  reconnectTimer = window.setTimeout(connect, delay)
}

function handleDrop(reason: string, closeCode?: number): void {
  if (!running) return
  if (disconnectedSince === null) disconnectedSince = Date.now()
  console.warn(
    "phase=studio-event-stream action=disconnect reason=%s close_code=%s consecutive_auth_failures=%d",
    reason,
    closeCode === undefined ? "n/a" : String(closeCode),
    consecutiveAuthFailures,
  )
  if (openResetTimer !== undefined) {
    window.clearTimeout(openResetTimer)
    openResetTimer = undefined
  }
  if (socket) {
    socket.onopen = null
    socket.onclose = null
    socket.onerror = null
    socket.onmessage = null
    socket = null
  }
  if (isWsAuthRejection(closeCode)) {
    consecutiveAuthFailures += 1
    if (shouldGiveUpOnAuthFailures(consecutiveAuthFailures)) {
      giveUpOnAuth()
      return
    }
  }
  scheduleReconnect()
}

function connect(): void {
  reconnectTimer = undefined
  if (!running || gaveUpOnAuth || subscribers.size === 0 || socket) return

  let nextSocket: WebSocket
  try {
    nextSocket = new WebSocket(wsUrl("/ws/events"))
  } catch (error) {
    console.error("phase=studio-event-stream action=connect-failed error=%o", error)
    handleDrop("constructor-threw")
    return
  }
  socket = nextSocket

  nextSocket.onopen = () => {
    if (!running) return
    console.info("phase=studio-event-stream action=connect attempt=%d", attempt + 1)
    disconnectedSince = null
    stopLostTicker()
    setHubConnectionLost(false)

    openResetTimer = window.setTimeout(() => {
      if (running && socket === nextSocket) {
        attempt = 0
        consecutiveAuthFailures = 0
      }
    }, 2000)
  }

  nextSocket.onmessage = (message) => {
    if (!running) return
    let event: { type?: string } & Record<string, unknown>
    try {
      event = JSON.parse(String(message.data)) as { type?: string } & Record<string, unknown>
    } catch (error) {
      console.error(
        "phase=studio-event-stream action=parse-failed data=%s error=%o",
        String(message.data).slice(0, 200),
        error,
      )
      return
    }
    dispatchEvent(event)
  }

  nextSocket.onerror = () => {
    console.warn("phase=studio-event-stream action=socket-error")
  }

  nextSocket.onclose = (event) => {
    const closeCode = typeof (event as CloseEvent).code === "number" ? (event as CloseEvent).code : undefined
    handleDrop("socket-closed", closeCode)
  }
}

function subscribe(subscriber: StudioEventSubscriber): () => void {
  const id = nextSubscriberId
  nextSubscriberId += 1
  subscribers.set(id, subscriber)
  subscriber.setConnectionLost((current) => (current === hubConnectionLost ? current : hubConnectionLost))
  if (!running) {
    running = true
    connect()
  }
  return () => {
    subscribers.delete(id)
    if (subscribers.size === 0) {
      running = false
      resetHubState()
    }
  }
}

export function useStudioEventStream(
  callbacks: StudioEventStreamCallbacks,
  options: StudioEventStreamOptions = {},
): StudioEventStreamState {
  const callbacksRef = useRef(callbacks)
  callbacksRef.current = callbacks
  const enabled = options.enabled ?? true

  const [connectionLost, setConnectionLost] = useState(hubConnectionLost)

  useEffect(() => {
    if (!enabled) {
      setConnectionLost(false)
      return undefined
    }
    return subscribe({ callbacksRef, setConnectionLost })
  }, [enabled])

  return { connectionLost }
}
