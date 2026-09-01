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
 * Fires `onDown` at most once per "down episode" while `armed` — the
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
 * recovery-stops-when-it-succeeds (2026-08-24) — the WS subscription below is
 * now unconditionally live for as long as this hook is mounted; `armed` no
 * longer gates it. The previous design passed `armed` straight through as
 * `useStudioEventStream`'s `enabled` option, tearing the subscription down on
 * every episode and rebuilding it on re-arm. A brand-new subscription
 * snapshots WHATEVER `connectionLost` reads on the shared hub at that exact
 * instant (see `subscribe()` in `useStudioEventStream.ts`) — and real-machine
 * verification found that snapshot is, almost always, stale: a sidecar
 * restart rotates the auth token, the hub's own reconnect can still be
 * holding the OLD token in that same instant, and re-arming read
 * `connectionLost === true` (the old token's rejection, not a new failure)
 * and fired `onDown` again immediately — livelocking the bounded restart
 * budget against its own successful recoveries.
 *
 * The fix is edge-triggering, not a settle-time guess: `onDown` fires only on
 * an OBSERVED transition of `connectionLost` from false to true while armed,
 * never on its level. The instant `armed` turns true, whatever
 * `connectionLost` reads right then becomes the new baseline — "already
 * known," never "new" — so a lagging-but-already-known signal can no longer
 * be mistaken for a fresh failure, however long the reconnect actually takes.
 * A connection that genuinely goes down again afterward still produces a real
 * transition and still fires — detection is never permanently blinded.
 */
export function useBackendDownSignal(armed: boolean, onDown: () => void): void {
  const { connectionLost } = useStudioEventStream(NOOP_EVENT_CALLBACKS)
  const onDownRef = useRef(onDown)
  onDownRef.current = onDown
  const firedRef = useRef(false)
  const previousArmedRef = useRef(armed)
  const previousConnectionLostRef = useRef(connectionLost)

  useEffect(() => {
    const wasArmed = previousArmedRef.current
    previousArmedRef.current = armed
    const justArmed = armed && !wasArmed

    if (justArmed) {
      // A fresh episode begins: forget that we already fired for the
      // PREVIOUS episode, and reset the edge-detection baseline to whatever
      // connectionLost happens to read RIGHT NOW — that reading is "already
      // known as of arming," so it can never itself count as the new edge
      // that opens this episode.
      firedRef.current = false
      previousConnectionLostRef.current = connectionLost
      return
    }

    const wasLost = previousConnectionLostRef.current
    previousConnectionLostRef.current = connectionLost

    if (!armed || !connectionLost || wasLost || firedRef.current) return
    firedRef.current = true
    onDownRef.current()
  }, [armed, connectionLost])

  useEffect(() => {
    if (!armed) return undefined
    function handleHttpFailure(): void {
      if (firedRef.current) return
      firedRef.current = true
      onDownRef.current()
    }
    window.addEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handleHttpFailure)
    return () => window.removeEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handleHttpFailure)
  }, [armed])
}
