import { useCallback, useEffect, useRef } from "react"
import { BACKEND_UNAVAILABLE_HTTP_EVENT, getApiBaseURL } from "@/api/client"
import { useStudioEventStream } from "./useStudioEventStream"

// Bounds how long a down-signal waits for its answer, nothing more. It is not
// a liveness threshold: reaching it is treated as "cannot tell", not "dead"
// (see `anythingAnswersOnTheSidecarPort`), so the exact value only decides how
// long the banner is delayed in the ambiguous case. The dead case never waits —
// a closed port on loopback refuses immediately.
const HEALTH_RECHECK_TIMEOUT_MS = 5000

// This hook only needs to know THAT something changed, never what — it never
// reads registry/roles truth, so a no-op pair satisfies useStudioEventStream's
// callback contract without pulling any data-refresh concern in here.
const NOOP_EVENT_CALLBACKS = {
  onRegistryChanged: (): void => {},
  onRolesChanged: (): void => {},
}

/**
 * `/health` is the sidecar's own liveness endpoint — unauthenticated
 * (`app/main.py`'s auth middleware whitelists it) and the SAME evidence the
 * Rust supervisor decides on (`apps/studio/tauri/src/sidecar.rs::wait_for_health`
 * polls `http://127.0.0.1:{port}/health`). Until this recheck existed, no
 * frontend code called it even once.
 *
 * It is reached by dropping the base URL's trailing `/api`, because `/health` is
 * the only registered route: `/api/health` also appears in the auth whitelist
 * but no router serves it, so it 404s. The Vite dev proxy forwards `/health`
 * alongside `/api` and `/ws` so the worktree preview reaches the real sidecar
 * too, instead of Vite's own SPA fallback.
 */
function healthProbeUrl(): string {
  const base = getApiBaseURL().replace(/\/+$/, "")
  return `${base.replace(/\/api$/, "")}/health`
}

/**
 * Ask whether anything is still serving on the sidecar's port.
 *
 * Uses `fetch`, deliberately NOT the shared axios instance: that client's
 * response interceptor dispatches `BACKEND_UNAVAILABLE_HTTP_EVENT` on a failed
 * call, so probing through it would have every failed probe re-enter this hook
 * as a fresh down-signal — a self-feeding loop.
 *
 * The question is deliberately the narrowest one that settles the decision at
 * hand, and it is NOT "is the backend well". It is "did we get an HTTP reply".
 * The signal being double-checked means exactly "a call received no HTTP
 * response at all", and the action being gated is "kill this process and start
 * another". So:
 *
 * - ANY HTTP status — 200, 500, 503 — means a process accepted the connection
 *   and answered. That refutes "the process is gone", which is the only claim
 *   the restart rests on. Judging a 503 as dead would restart a sidecar that
 *   just told us it is alive, and it would disagree with the Rust supervisor,
 *   whose own probe (`sidecar.rs::wait_for_health`) accepts any 2xx and never
 *   reads the body. Two components that disagree about liveness are worse than
 *   either rule alone.
 * - A TIMEOUT is ambiguous, not negative: the socket may well have been
 *   accepted by a process whose event loop is briefly blocked (Studio has
 *   `async` routes that run a synchronous compile, with no sub-second bound).
 *   No timeout value can separate "blocked" from "gone", so the tie goes to
 *   NOT restarting — the person still has Retry, which bypasses the automatic
 *   budget, and a delayed banner is cheaper than killing live work.
 * - Only a transport failure — connection refused, and on loopback that is
 *   immediate and unambiguous — confirms nothing is there.
 *
 * What this does NOT establish is identity: `/health` is unauthenticated and
 * carries no instance id, so another local process holding the port would pass.
 * That limit is the supervisor's too, and it is the reason this is a veto on a
 * destructive action rather than a health assertion.
 */
async function anythingAnswersOnTheSidecarPort(): Promise<boolean> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), HEALTH_RECHECK_TIMEOUT_MS)
  try {
    await fetch(healthProbeUrl(), {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    })
    return true
  } catch (error) {
    // Our own abort fired: no reply inside the budget, but nothing said the
    // port is closed either. Ambiguous — see above, the tie goes to alive.
    return error instanceof Error && error.name === "AbortError"
  } finally {
    clearTimeout(timeout)
  }
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
 *
 * confirm-before-you-kill — BOTH signals above are weak evidence, and neither
 * is allowed to fire `onDown` on its own any more. `/health` is asked first,
 * and only its refusal to answer confirms the outage.
 *
 * The weakness is structural, not incidental. `BACKEND_UNAVAILABLE_HTTP_EVENT`
 * says "this call got no HTTP RESPONSE", which is NOT the same fact as "the
 * process is gone": a 500 the browser discards for lacking
 * `Access-Control-Allow-Origin` reaches axios as ERR_NETWORK and looks, from
 * inside the interceptor, exactly like a dead port. `connectionLost` is weaker
 * still — a reconnect heuristic that also trips on a rotated auth token. Acting
 * on either alone had RuntimeGate auto-restarting sidecars that were serving
 * fine, and an unnecessary restart is expensive: it rotates the token and port
 * and drops every in-flight run.
 *
 * The recheck costs one request, on a path that only runs when something
 * already looks wrong, and it is the same question the Rust supervisor asks.
 * A veto does NOT spend the episode: `firedRef` is set when we actually FIRE,
 * never merely because we asked, so one early false alarm cannot blind
 * detection for the rest of the episode.
 */
export function useBackendDownSignal(armed: boolean, onDown: () => void): void {
  const { connectionLost } = useStudioEventStream(NOOP_EVENT_CALLBACKS)
  const onDownRef = useRef(onDown)
  onDownRef.current = onDown
  const firedRef = useRef(false)
  const previousArmedRef = useRef(armed)
  const previousConnectionLostRef = useRef(connectionLost)
  const armedRef = useRef(armed)
  armedRef.current = armed
  // Identifies the down episode a probe was started for, so a verdict that
  // lands after RuntimeGate disarmed (or after a whole new episode opened)
  // cannot be applied to the wrong one.
  const episodeRef = useRef(0)
  const probeInFlightRef = useRef(false)
  const signalArrivedDuringProbeRef = useRef(false)
  // Cleared on unmount. A probe that lands afterwards must not call `onDown`:
  // RuntimeGate's own timer cleanup has already run by then, so the restart it
  // would schedule is a timer nobody is left to cancel.
  const mountedRef = useRef(true)
  // Which signal the CURRENT probe round is answering — updated when a signal
  // coalesces in, so the log line names the reason we are still probing rather
  // than whichever signal happened to open the round.
  const latestSignalRef = useRef("")

  const confirmOutageThenFire = useCallback(async (signal: string): Promise<void> => {
    if (firedRef.current) return
    if (probeInFlightRef.current) {
      // COALESCE, never drop. The probe already running may come back healthy
      // while THIS signal is the real outage — and the WS signal cannot be
      // re-offered: `connectionLost` is edge-triggered off a false→true
      // transition whose baseline has already advanced, and a level that stays
      // true produces no second edge. Dropping the signal here would therefore
      // blind detection for the rest of the episode, which is exactly the
      // failure this hook's edge-trigger design was written to avoid. Same
      // shape as the repo's settings-autosave rule: an in-flight request does
      // not discard the newer demand, it supersedes into a pending one.
      signalArrivedDuringProbeRef.current = true
      latestSignalRef.current = signal
      return
    }
    probeInFlightRef.current = true
    latestSignalRef.current = signal
    try {
      // Loop while signals keep arriving mid-probe. This cannot spin: every pass
      // performs a real request (or waits out its budget), and it exits as soon
      // as one finishes with nothing new behind it.
      for (;;) {
        signalArrivedDuringProbeRef.current = false
        // Captured per PASS, not per call. A verdict may only be applied to the
        // episode whose probe produced it — but a signal that arrived while that
        // probe was running is evidence for whatever episode is current when it
        // lands, so the two decisions have to be made separately.
        const episode = episodeRef.current
        const answered = await anythingAnswersOnTheSidecarPort()
        if (!mountedRef.current) return

        if (episode === episodeRef.current && armedRef.current) {
          if (!answered) {
            if (firedRef.current) return
            firedRef.current = true
            onDownRef.current()
            return
          }
          // Vetoed. Note what this does NOT restore: the WS branch's consumed
          // edge. Once `connectionLost` is true it stays true until a reconnect,
          // and React only re-runs that effect when the value CHANGES — so
          // rewinding the baseline here would be a line that reads like a fix
          // and does nothing. Detection in the interim rides on the HTTP branch,
          // which is level-driven and fires on every call that gets no response;
          // the WS branch resumes as soon as the connection actually transitions
          // (reconnect, then a real loss), which is covered by test. Closing the
          // stuck-true window itself would take a re-check timer, and this hook
          // deliberately has no timers.
          console.warn(
            `[studio] ${latestSignalRef.current} looked like a dead backend, but the sidecar port still answers — not reporting it down`,
          )
        }
        // Reached either after applying a veto, or after DISCARDING a verdict
        // that belonged to a finished episode. Both leave a pending signal
        // unanswered, and dropping it here is the same blindness the coalesce
        // exists to prevent — so keep going while one is outstanding.
        if (!signalArrivedDuringProbeRef.current || !armedRef.current) return
      }
    } finally {
      probeInFlightRef.current = false
    }
  }, [])

  useEffect(() => {
    // Set on the way IN as well as cleared on the way out. `main.tsx` wraps the
    // app in `<StrictMode>`, which deliberately runs mount → cleanup → mount
    // again on the SAME instance (so the same refs). Only clearing it would
    // latch this instance to "unmounted" for the rest of its life in dev, and
    // silently disable down-detection entirely.
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

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
      episodeRef.current += 1
      previousConnectionLostRef.current = connectionLost
      return
    }

    const wasLost = previousConnectionLostRef.current
    previousConnectionLostRef.current = connectionLost

    if (!armed || !connectionLost || wasLost || firedRef.current) return
    void confirmOutageThenFire("WebSocket connectionLost")
  }, [armed, connectionLost, confirmOutageThenFire])

  useEffect(() => {
    if (!armed) return undefined
    function handleHttpFailure(): void {
      void confirmOutageThenFire("An HTTP call got no response")
    }
    window.addEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handleHttpFailure)
    return () => window.removeEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handleHttpFailure)
  }, [armed, confirmOutageThenFire])
}
