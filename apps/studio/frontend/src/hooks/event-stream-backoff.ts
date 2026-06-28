/**
 * N0 Settings · Shell (atoms #5/#6) — pure, testable backoff + connection-lost
 * threshold math for the /ws/events reconnect logic in `useStudioEventStream`.
 *
 * Kept separate from the hook so the schedule and threshold are unit-tested
 * without a live WebSocket. The hook injects Math.random / Date.now around
 * these pure helpers.
 */

/** Initial reconnect delay, doubled each attempt up to the cap. */
export const RECONNECT_INITIAL_DELAY_MS = 1_000
/** Multiplier applied per attempt (exponential backoff). */
export const RECONNECT_FACTOR = 2
/** Upper bound for the (pre-jitter) backoff delay. */
export const RECONNECT_MAX_DELAY_MS = 30_000
/** Consecutive failures at/after which the connection counts as lost. */
export const CONNECTION_LOST_FAILURE_THRESHOLD = 3
/** Cumulative time without a connection at/after which it counts as lost. */
export const CONNECTION_LOST_TIME_THRESHOLD_MS = 10_000
/**
 * WebSocket close code emitted by the sidecar's `/ws/events` auth gate when the
 * bearer token is missing or invalid (apps/studio/backend/app/routers/websockets.py).
 * The 4000-4999 range is reserved for application-defined close codes per RFC 6455.
 */
export const WS_AUTH_REJECTED_CLOSE_CODE = 4401
/**
 * R-F13: consecutive 4401 closes at/after which we stop reconnecting and surface
 * a toast — at this point the cached token is provably stale and silently retrying
 * forever would hide the real failure (sidecar restarted with a new token, or the
 * user's session is gone). 5 attempts gives a brief grace window for transient
 * close races (e.g. sidecar mid-restart) before we give up loudly.
 */
export const WS_AUTH_FAILURE_GIVEUP_THRESHOLD = 5

/**
 * Pre-jitter exponential backoff base for a given (zero-based) attempt:
 * 1s, 2s, 4s, 8s, 16s, then capped at 30s. `attempt` 0 is the first retry
 * after the initial connection dropped.
 */
export function nextReconnectDelayBase(attempt: number): number {
  const safeAttempt = attempt < 0 ? 0 : Math.floor(attempt)
  const scaled = RECONNECT_INITIAL_DELAY_MS * RECONNECT_FACTOR ** safeAttempt
  return Math.min(scaled, RECONNECT_MAX_DELAY_MS)
}

/**
 * Apply FULL jitter: a uniform random value in [0, base]. `random` defaults to
 * Math.random and is injectable for deterministic tests. The returned delay is
 * always within [0, base], so it never exceeds the cap.
 */
export function nextReconnectDelay(attempt: number, random: () => number = Math.random): number {
  const base = nextReconnectDelayBase(attempt)
  const clampedRandom = Math.min(Math.max(random(), 0), 1)
  return Math.round(base * clampedRandom)
}

/**
 * Decide whether to surface the "connection lost" warning. We avoid flicker on
 * a brief blip: lost only once the reconnect backoff has CONSISTENTLY failed —
 * either ≥ CONNECTION_LOST_FAILURE_THRESHOLD consecutive failures, or the
 * cumulative time without a connection has exceeded
 * CONNECTION_LOST_TIME_THRESHOLD_MS. A successful (re)connect resets both
 * inputs to 0, immediately clearing the warning.
 */
export function shouldShowConnectionLost(consecutiveFailures: number, msWithoutConnection: number): boolean {
  return (
    consecutiveFailures >= CONNECTION_LOST_FAILURE_THRESHOLD ||
    msWithoutConnection >= CONNECTION_LOST_TIME_THRESHOLD_MS
  )
}

/**
 * R-F13: classify a WebSocket close as an auth-rejection (4401 from the sidecar's
 * `/ws/events` auth gate). Any other close code (1000/1006/1011/1013/etc.) is a
 * transient transport/server condition and must NOT increment the auth-failure
 * counter — only repeated 4401s indicate a stale token that justifies giving up.
 */
export function isWsAuthRejection(closeCode: number | undefined): boolean {
  return closeCode === WS_AUTH_REJECTED_CLOSE_CODE
}

/**
 * R-F13: decide whether to stop the reconnect loop and surface the toast after
 * N consecutive 4401 closes. Encapsulated as a pure helper so the threshold is
 * unit-testable without driving a live WebSocket through five rounds of
 * exponential backoff.
 */
export function shouldGiveUpOnAuthFailures(consecutiveAuthFailures: number): boolean {
  return consecutiveAuthFailures >= WS_AUTH_FAILURE_GIVEUP_THRESHOLD
}
