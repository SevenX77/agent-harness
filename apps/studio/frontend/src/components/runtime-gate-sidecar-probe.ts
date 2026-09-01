import { getApiBaseURL } from '@/api/client'

/**
 * The last question asked before the automatic restart kills a sidecar.
 *
 * Why it exists. RuntimeGate's two liveness signals are both WEAK.
 * `BACKEND_UNAVAILABLE_HTTP_EVENT` means "a call received no HTTP RESPONSE",
 * which is not the same fact as "the process is gone" — a 500 the browser
 * discards for lacking `Access-Control-Allow-Origin` arrives at axios as
 * ERR_NETWORK and is indistinguishable, from inside the interceptor, from a
 * dead port. `connectionLost` is weaker still: a reconnect heuristic that also
 * trips on a rotated auth token. Either alone was enough to restart a sidecar
 * that was serving fine, and that restart is expensive — it rotates the token
 * and port and drops every in-flight run.
 *
 * Why it gates the RESTART and not the detection. The banner and its Retry
 * button appear only once RuntimeGate leaves the 'ready' status, which only the
 * down-signal does. Confirming before reporting the outage would therefore
 * suppress the banner too, leaving a broken app with no message and no
 * affordance — strictly worse than a spurious restart. So detection stays
 * exactly as sensitive as it was, and only the destructive act asks for more
 * evidence.
 *
 * That split also settles what to do when the answer is unclear, because the
 * two directions are no longer symmetric. Skipping a restart we could have made
 * costs a delay, with the banner and Retry already on screen. Making a restart
 * we should have skipped destroys live work. So anything short of "nothing is
 * there" declines to restart.
 *
 * What it cannot do. `fetch` collapses several failures into one `TypeError` —
 * connection refused, connection reset, a CORS rejection — so this is evidence
 * against destroying the process, not proof of health. `/health` is also
 * unauthenticated and carries no instance id, so another local process holding
 * the port would pass; that limit is the Rust supervisor's too
 * (`sidecar.rs::wait_for_health` probes the same endpoint). Both limits are
 * survivable precisely because a wrong answer here means "did not restart".
 */

/**
 * Bounds the wait, and nothing more: reaching it means "cannot tell", never
 * "dead". The dead case does not consume it — a closed port on loopback refuses
 * immediately — so this value only decides how long a restart is delayed while
 * something is holding the port open without answering.
 */
const PROBE_TIMEOUT_MS = 5_000

/**
 * `/health` is the sidecar's own liveness endpoint: unauthenticated (the auth
 * middleware whitelists it) and the same one the Rust supervisor probes. It is
 * reached by dropping the base URL's trailing `/api`, because `/health` is the
 * only registered route — `/api/health` is in the auth whitelist but no router
 * serves it, so it 404s. The Vite dev proxy forwards `/health` alongside `/api`
 * so the worktree preview reaches the real sidecar rather than its own SPA
 * fallback.
 */
function healthProbeUrl(): string {
  const base = getApiBaseURL().replace(/\/+$/, '')
  return `${base.replace(/\/api$/, '')}/health`
}

/**
 * Resolves false ONLY when nothing answered at all.
 *
 * Any HTTP status counts as an answer, including 5xx: a process that replies
 * 503 has just proved it is running, which is the only claim the restart rests
 * on. This also keeps the verdict aligned with the supervisor's, and two
 * components disagreeing about liveness would be worse than either rule alone.
 *
 * Deliberately uses `fetch`, not the shared axios instance: that client's
 * response interceptor dispatches `BACKEND_UNAVAILABLE_HTTP_EVENT` on a failed
 * call, so probing through it would feed every failed probe back in as a fresh
 * down-signal.
 */
export async function sidecarPortAnswers(): Promise<boolean> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS)
  try {
    await fetch(healthProbeUrl(), {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
    })
    return true
  } catch (error) {
    // Our own abort fired: no reply inside the budget, but nothing said the port
    // is closed either. Ambiguous, so it declines to restart.
    return error instanceof Error && error.name === 'AbortError'
  } finally {
    clearTimeout(timeout)
  }
}
