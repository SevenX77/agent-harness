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
