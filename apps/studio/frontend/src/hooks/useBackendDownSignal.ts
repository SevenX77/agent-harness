import { useEffect, useRef } from "react"
import { BACKEND_UNAVAILABLE_HTTP_EVENT } from "@/api/client"
import { useStudioEventStream } from "./useStudioEventStream"

// This hook only needs to know THAT something changed, never what — it never
// reads registry/roles truth, so a no-op pair satisfies useStudioEventStream's
// callback contract without pulling any data-refresh concern in here.
const NOOP_EVENT_CALLBACKS = {
  onRegistryChanged: (): void => {},
  onRolesChanged: (): void => {},
}

/**
 * Fires `onDown` at most once per "down episode" while `enabled` — the
 * edge-trigger a bounded-retry state machine needs (RuntimeGate): many
 * WS/HTTP failures during one outage must start the bounded auto-restart
 * sequence ONCE, not once per failed call or reconnect attempt.
 *
 * The two signals combined here are both PUSH-driven, reusing infrastructure
 * that already exists for other reasons:
 *   - `useStudioEventStream`'s `connectionLost` — the shared WebSocket event
 *     stream's own reconnect loop already computes this (with its own
 *     flicker-avoiding threshold: `event-stream-backoff.ts`), so subscribing
 *     here shares the ONE hub connection rather than opening a second socket.
 *   - `BACKEND_UNAVAILABLE_HTTP_EVENT` — dispatched by the axios response
 *     interceptor (`api/client.ts`) the moment any call gets no HTTP response
 *     at all, which on a loopback sidecar reliably means the process is gone.
 * Neither is a new timer/poller: AGENTS.md forbids re-fetching TRUTH data on a
 * schedule, and even though liveness is not truth data, there is no reason to
 * add a heartbeat when both signals already fire on their own.
 *
 * An episode ends only when `enabled` toggles off and back on — RuntimeGate
 * flips it off the instant it reacts (status leaves 'ready') and back on only
 * once a restart actually succeeds (status returns to 'ready').
 */
export function useBackendDownSignal(enabled: boolean, onDown: () => void): void {
  const { connectionLost } = useStudioEventStream(NOOP_EVENT_CALLBACKS, { enabled })
  const onDownRef = useRef(onDown)
  onDownRef.current = onDown
  const firedRef = useRef(false)

  // A fresh episode begins the moment we're re-enabled: forget that we already
  // fired for the PREVIOUS episode, so the next real failure fires again.
  useEffect(() => {
    if (enabled) firedRef.current = false
  }, [enabled])

  useEffect(() => {
    if (!enabled || !connectionLost || firedRef.current) return
    firedRef.current = true
    onDownRef.current()
  }, [enabled, connectionLost])

  useEffect(() => {
    if (!enabled) return undefined
    function handleHttpFailure(): void {
      if (firedRef.current) return
      firedRef.current = true
      onDownRef.current()
    }
    window.addEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handleHttpFailure)
    return () => window.removeEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handleHttpFailure)
  }, [enabled])
}
