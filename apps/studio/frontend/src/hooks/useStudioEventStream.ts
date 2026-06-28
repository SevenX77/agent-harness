import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { wsUrl } from "@/api/client"
import {
  isWsAuthRejection,
  nextReconnectDelay,
  shouldGiveUpOnAuthFailures,
  shouldShowConnectionLost,
} from "./event-stream-backoff"

/**
 * N0 Settings · Shell (atoms #5 ws-registry-refresh / #6 ws-roles-refresh).
 *
 * Single resilient subscription to the gateway sidecar's `/ws/events` channel.
 * It JSON-parses each message and dispatches by `event.type` to the caller's
 * callbacks (registry_changed → onRegistryChanged, roles_changed →
 * onRolesChanged), reconnects forever with exponential backoff + full jitter,
 * and on every successful (re)connect calls `onResync` so the caller refetches
 * once to fill any gap missed while disconnected.
 *
 * Resilience replaces the old SettingsPage inline WebSocket which had two empty
 * `catch {}` blocks (logging-rule violation) and no reconnect at all.
 *
 * `connectionLost` is debounced past a flicker threshold: it goes true only
 * after the backoff has consistently failed (≥3 consecutive failures OR >10s
 * with no connection) and returns to false immediately on reconnect.
 */
export interface StudioEventStreamCallbacks {
  /** A registry_changed event arrived (external credentials file change). */
  onRegistryChanged: () => void
  /** A roles_changed event arrived (external roles file change). */
  onRolesChanged: () => void
  /**
   * A (re)connection just opened. Caller should refetch once to fill any gap
   * that may have happened while the socket was down. Fires on the very first
   * connect too (harmless: it just re-confirms the current data).
   */
  onResync: () => void
}

const CONNECTION_LOST_TICK_MS = 1_000

interface StudioEventStreamState {
  connectionLost: boolean
}

/**
 * Subscribe to `/ws/events`. Pass stable-enough callbacks; the hook reads them
 * via a ref so changing callbacks never tears down the socket. The returned
 * `connectionLost` drives the shell's "connection lost" warning.
 *
 * R-F13 (token refresh on reconnect): the WebSocket URL is built by `wsUrl()`,
 * which reads `currentApiToken` from the api/client module at call time. Because
 * `connect()` re-invokes `wsUrl("/ws/events")` on every reconnect attempt, a token
 * rotated via `configureApiToken()` (e.g. when the sidecar restarts and emits
 * `sidecar-restarted` with a fresh token) is picked up automatically — there is
 * no closure-cached token here. After
 * `WS_AUTH_FAILURE_GIVEUP_THRESHOLD` consecutive 4401 closes the hook stops
 * reconnecting and toasts the user instead of silently spinning forever.
 */
export function useStudioEventStream(callbacks: StudioEventStreamCallbacks): StudioEventStreamState {
  const callbacksRef = useRef(callbacks)
  callbacksRef.current = callbacks

  const [connectionLost, setConnectionLost] = useState(false)

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | null = null
    let attempt = 0
    let consecutiveAuthFailures = 0
    let gaveUpOnAuth = false
    let reconnectTimer: number | undefined
    let lostTicker: number | undefined
    let disconnectedSince: number | null = null

    const evaluateConnectionLost = () => {
      if (cancelled) return
      const msWithoutConnection = disconnectedSince === null ? 0 : Date.now() - disconnectedSince
      const lost = shouldShowConnectionLost(attempt, msWithoutConnection)
      setConnectionLost((current) => (current === lost ? current : lost))
    }

    const stopLostTicker = () => {
      if (lostTicker !== undefined) {
        window.clearInterval(lostTicker)
        lostTicker = undefined
      }
    }

    const startLostTicker = () => {
      if (lostTicker !== undefined) return
      // While disconnected, the time-based threshold must keep advancing even if
      // no further failure events fire, so re-evaluate on a steady tick.
      lostTicker = window.setInterval(evaluateConnectionLost, CONNECTION_LOST_TICK_MS)
    }

    const scheduleReconnect = () => {
      if (cancelled || gaveUpOnAuth) return
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

    const giveUpOnAuth = () => {
      // R-F13: 5 consecutive 4401 closes means the cached token is stale and
      // silent reconnects will spin forever. Stop the loop and surface the
      // failure so the user can restart Studio (which re-runs the sidecar
      // bootstrap and configures a fresh api token via get_sidecar_config IPC).
      gaveUpOnAuth = true
      stopLostTicker()
      // Force the "connection lost" banner true regardless of the time/failure
      // thresholds — we have explicit evidence the link is unrecoverable.
      setConnectionLost((current) => (current ? current : true))
      console.error(
        "phase=studio-event-stream action=give-up reason=auth-rejected-threshold consecutive=%d",
        consecutiveAuthFailures,
      )
      toast.error("与 sidecar 连接已断开，请重启 Studio")
    }

    const handleDrop = (reason: string, closeCode?: number) => {
      if (cancelled) return
      if (disconnectedSince === null) disconnectedSince = Date.now()
      console.warn(
        "phase=studio-event-stream action=disconnect reason=%s close_code=%s consecutive_auth_failures=%d",
        reason,
        closeCode === undefined ? "n/a" : String(closeCode),
        consecutiveAuthFailures,
      )
      if (socket) {
        socket.onopen = null
        socket.onclose = null
        socket.onerror = null
        socket.onmessage = null
        socket = null
      }
      // R-F13: 4401 from the sidecar's /ws/events auth gate is the signal that
      // the bearer token is stale or wrong. Track it separately from generic
      // transport drops so a transient 1006/1011 never trips the give-up logic.
      if (isWsAuthRejection(closeCode)) {
        consecutiveAuthFailures += 1
        if (shouldGiveUpOnAuthFailures(consecutiveAuthFailures)) {
          giveUpOnAuth()
          return
        }
      }
      scheduleReconnect()
    }

    const connect = () => {
      if (cancelled || gaveUpOnAuth) return
      // R-F13: wsUrl() reads `currentApiToken` from api/client at call time, so
      // a token rotated between reconnect attempts (e.g. after the sidecar
      // restarts and emits sidecar-restarted -> configureApiToken(new)) is
      // picked up here without any extra plumbing. Do NOT capture the URL into
      // a closure variable outside `connect()` or the freshness guarantee breaks.
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
        if (cancelled) return
        console.info("phase=studio-event-stream action=connect attempt=%d", attempt + 1)
        // Successful (re)connect: reset backoff + connection-lost tracking and
        // refetch once to fill any gap missed while the socket was down.
        // The auth-failure counter resets too — getting an OPEN frame proves
        // the current token was accepted, so any prior 4401s are stale.
        attempt = 0
        consecutiveAuthFailures = 0
        disconnectedSince = null
        stopLostTicker()
        setConnectionLost((current) => (current ? false : current))
        callbacksRef.current.onResync()
      }

      nextSocket.onmessage = (message) => {
        if (cancelled) return
        let event: { type?: string }
        try {
          event = JSON.parse(String(message.data)) as { type?: string }
        } catch (error) {
          console.error(
            "phase=studio-event-stream action=parse-failed data=%s error=%o",
            String(message.data).slice(0, 200),
            error,
          )
          return
        }
        if (event.type === "registry_changed") {
          console.info("phase=studio-event-stream action=dispatch type=registry_changed")
          callbacksRef.current.onRegistryChanged()
        } else if (event.type === "roles_changed") {
          console.info("phase=studio-event-stream action=dispatch type=roles_changed")
          callbacksRef.current.onRolesChanged()
        }
      }

      nextSocket.onerror = () => {
        // onerror is always followed by onclose; defer the drop handling to
        // onclose so we schedule exactly one reconnect. Log so the error path
        // is observable (no silent swallow).
        console.warn("phase=studio-event-stream action=socket-error")
      }

      nextSocket.onclose = (event) => {
        // The browser hands us a CloseEvent with `code` so we can distinguish
        // a 4401 auth rejection (R-F13) from a normal/abnormal transport close.
        // `event` may be a plain Event in test environments; coerce defensively.
        const closeCode = typeof (event as CloseEvent).code === "number" ? (event as CloseEvent).code : undefined
        handleDrop("socket-closed", closeCode)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      stopLostTicker()
      if (socket) {
        socket.onopen = null
        socket.onclose = null
        socket.onerror = null
        socket.onmessage = null
        socket.close()
      }
    }
  }, [])

  return { connectionLost }
}
