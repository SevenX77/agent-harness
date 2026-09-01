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
 * What the two outcomes are. Not "restart" versus "give up": a caller that
 * stopped on "the port answers" would leave RuntimeGate on 'error', which disarms
 * detection, so being gentle once would cost the app its ability to notice
 * anything afterwards. The outcomes are RESTART the sidecar or RECONNECT to it —
 * both of which end somewhere the state machine can leave. That is also what
 * makes the asymmetry usable: mistakenly reconnecting to a dead sidecar costs one
 * failed attempt and another cycle, while mistakenly restarting a live one
 * destroys in-flight work.
 *
 * How far that asymmetry can actually be pushed. Not all the way: `fetch`
 * collapses several outcomes into one `TypeError` — connection refused,
 * connection reset, a CORS rejection — and a dead port is IN that class. Declining
 * on the whole class would therefore decline always, which is not caution, it is
 * deleting the auto-restart. So the class permits a restart, and what the probe
 * buys is a real narrowing rather than certainty: from "one call failed / the
 * socket flapped" to "a fresh unauthenticated GET got no reply at all". The two
 * companions of a refused connection are not states worth protecting anyway — a
 * reset means the connection was torn down, and a CORS rejection on `/health`
 * means the page's origin is not one the backend allows (`config.py`'s
 * `CORS_ORIGINS` covers the origins Studio actually ships), which is a broken
 * configuration rather than a healthy backend to preserve.
 *
 * What stays outside its reach. `/health` is unauthenticated and carries no
 * instance id, so another local process holding the port would pass as our
 * sidecar; that limit is the Rust supervisor's too
 * (`sidecar.rs::wait_for_health` probes the same endpoint). And the check and the
 * kill are separate steps here, so a process that dies in between still gets
 * "restarted" — closing that window needs the check to happen inside the
 * supervisor that owns the process, which is where it ultimately belongs.
 */

/**
 * Bounds the wait, and nothing more: reaching it means "cannot tell", never
 * "dead". The dead case does not consume it — a closed port on loopback refuses
 * immediately — so this value only decides how long the decision waits while
 * something holds the port open without answering.
 *
 * "Cannot tell" is grouped with "answering", which is not a claim that a hung
 * process is healthy. It is the choice of which outcome to take when the probe
 * has nothing: reconnecting to a hung sidecar fails and comes back around on the
 * next attempt, and restarting a live one does not come back at all.
 */
const PROBE_TIMEOUT_MS = 5_000

/**
 * `/health` is the sidecar's own liveness endpoint: unauthenticated (the auth
 * middleware whitelists it) and the same one the Rust supervisor probes. It is
 * reached by dropping the base URL's trailing `/api`, because `/health` is the
 * only registered route — `/api/health` is in the auth whitelist but no router
 * serves it, so it 404s.
 *
 * In the desktop app this is an absolute `http://127.0.0.1:{port}` the shell
 * handed us, so the request reaches the sidecar directly. In a browser it is the
 * relative `/api`, and the Vite dev proxy (which forwards `/health` alongside
 * `/api`) sits in between — where a REFUSED upstream becomes Vite's own 502,
 * which this reads as "answering". Recorded rather than fixed, because outside
 * Tauri BOTH outcomes of this verdict are non-destructive: `performShellRestart`
 * has no shell to ask and falls back to re-reading the config, which is also what
 * the answering branch does. The dev preview cannot demonstrate the desktop
 * behaviour either way, and no amount of proxy configuration would change that.
 */
function healthProbeUrl(): string {
  const base = getApiBaseURL().replace(/\/+$/, '')
  return `${base.replace(/\/api$/, '')}/health`
}

/**
 * Resolves false only when the request produced no reply at all.
 *
 * Any HTTP status counts as an answer, including 5xx: a process that replies
 * 503 has just proved it is running, which is the only claim the restart rests
 * on.
 *
 * That is deliberately NOT the supervisor's threshold —
 * `sidecar.rs::wait_for_health` requires `status().is_success()`. The two ask
 * different questions of the same endpoint. The supervisor asks "has the process
 * I just launched come up ready to serve", where anything less than success
 * means keep waiting; this asks "is there still a process here to destroy",
 * where a 503 settles it. A single threshold would have to be wrong for one of
 * them.
 *
 * A `fetch` that throws is read as no reply — see the module docstring for why
 * that class cannot be narrowed further, and what it therefore does and does not
 * establish.
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
    // is closed either. Ambiguous, so it takes the recoverable outcome.
    return error instanceof Error && error.name === 'AbortError'
  } finally {
    clearTimeout(timeout)
  }
}
