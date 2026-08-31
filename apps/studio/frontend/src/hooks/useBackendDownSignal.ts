import { useCallback, useEffect, useRef } from "react"
import { BACKEND_UNAVAILABLE_HTTP_EVENT, getApiBaseURL } from "@/api/client"
import { useStudioEventStream } from "./useStudioEventStream"

// This number is close to free, which is why it is generous. A sidecar that is
// actually GONE does not consume it: connecting to a closed port on loopback
// fails immediately with ECONNREFUSED, so the dead case — the common one — is
// answered in milliseconds either way. The timeout governs only the other
// shape: the port is open but no reply comes, which is what a sidecar whose
// event loop is momentarily blocked looks like. Studio has such paths (`async`
// routes that run a synchronous compile, e.g. `routers/lint.py::lint_skill`),
// and they have no sub-second response bound. Timing out on one of those and
// concluding "dead" would restart a sidecar in the middle of real work — the
// exact failure this recheck exists to prevent. So waiting longer costs almost
// nothing and buys real protection.
//
// It is not unbounded, because the wait does delay a genuine outage banner. The
// Rust supervisor's 30s budget for the same endpoint is not the comparison: that
// one covers a COLD START (interpreter boot + imports), not a live process.
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
 * Ask the sidecar directly whether it is alive.
 *
 * Uses `fetch`, deliberately NOT the shared axios instance: that client's
 * response interceptor dispatches `BACKEND_UNAVAILABLE_HTTP_EVENT` on a failed
 * call, so probing through it would have every failed probe re-enter this hook
 * as a fresh down-signal — a self-feeding loop.
 *
 * "Healthy" means something answered with the health endpoint's own body, not
 * merely that something returned 200. The body check is what stops an unrelated
 * 200 — a dev server's SPA fallback serving index.html for an unproxied
 * `/health`, say — from reading as a live sidecar and suppressing detection
 * forever. It is a check on the SHAPE of the reply, not proof of identity:
 * `/health` is unauthenticated and carries no instance id, so another local
 * process holding the port and answering the same JSON would pass. That is the
 * same evidence, and the same limit, as the Rust supervisor's own probe.
 */
async function sidecarAnswersHealthProbe(): Promise<boolean> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), HEALTH_RECHECK_TIMEOUT_MS)
  try {
    const response = await fetch(healthProbeUrl(), {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    })
    if (!response.ok) return false
    const body = (await response.json()) as { status?: unknown } | null
    return body?.status === "ok"
  } catch {
    // Network error, abort on timeout, or a body that is not the health JSON —
    // every one of them means we did NOT get the sidecar's own confirmation.
    return false
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
    const episode = episodeRef.current
    try {
      // Re-probe as long as another signal came in while the last one was in
      // flight. This cannot spin: each pass performs a real request (or waits
      // out its timeout), and it exits as soon as one completes with nothing
      // new behind it.
      do {
        signalArrivedDuringProbeRef.current = false
        const alive = await sidecarAnswersHealthProbe()
        if (!mountedRef.current || episode !== episodeRef.current || !armedRef.current) return
        if (!alive) {
          if (firedRef.current) return
          firedRef.current = true
          onDownRef.current()
          return
        }
        console.warn(
          `[studio] ${latestSignalRef.current} looked like a dead backend, but /health still answers — not reporting it down`,
        )
      } while (signalArrivedDuringProbeRef.current)
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
