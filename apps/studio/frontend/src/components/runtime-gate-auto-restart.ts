/**
 * Bounded automatic sidecar-restart policy for `RuntimeGate` — the frontend
 * half of the dead-sidecar-says-so fix (2026-08-24).
 *
 * WHEN to retry (the 1s/4s/16s delays below) is a frontend concern: only the
 * frontend can observe the two free liveness signals (the shared WebSocket
 * event stream dropping, or an HTTP call getting no response at all — see
 * `useBackendDownSignal`). HOW MANY times is independently enforced a second
 * time on the Rust side (`apps/studio/tauri/src/sidecar.rs`,
 * `SidecarSupervisor::restart_automatic`) — the same count/window ceiling,
 * kept in sync deliberately rather than trusted to only one layer, exactly
 * because a systemd unit's own start-limit is enforced by the unit and not by
 * whatever asked for the restart.
 *
 * "到限就停,不再试": once `AUTO_RESTART_MAX_ATTEMPTS` is spent, or
 * `AUTO_RESTART_WINDOW_MS` has elapsed since the first attempt, this refuses
 * PERMANENTLY for the episode — it does not renew on a timer. That is the
 * difference between this and `Restart=always`: a transient blip gets a few
 * quiet attempts, a permanent failure lands on a visible terminal state
 * (RuntimeGate's persistent banner) instead of retrying forever in the
 * background. Only a manual Retry (`RuntimeGate`'s `onRetry`) starts a fresh
 * episode — see `initialAutoRestartState`.
 */

/** Fixed backoff schedule — NOT exponential-with-jitter (the WS reconnect in
 * `event-stream-backoff.ts` already owns that concern for the transport
 * layer); this is a short, fixed sequence for restarting the sidecar PROCESS
 * itself. */
export const AUTO_RESTART_DELAYS_MS = [1_000, 4_000, 16_000] as const

/** At most this many automatic attempts per episode. */
export const AUTO_RESTART_MAX_ATTEMPTS = AUTO_RESTART_DELAYS_MS.length

/** Hard ceiling on one episode's total elapsed time, from the first attempt. */
export const AUTO_RESTART_WINDOW_MS = 120_000

export interface AutoRestartState {
  attemptsUsed: number
  windowStartedAtMs: number | null
}

/** A fresh episode: no attempts used yet, no window open. */
export function initialAutoRestartState(): AutoRestartState {
  return { attemptsUsed: 0, windowStartedAtMs: null }
}

/**
 * Whether another automatic attempt may be scheduled right now. `false` is
 * permanent for this episode (see module doc) — the caller's only way back to
 * `true` is starting a new episode via `initialAutoRestartState()`.
 */
export function canAttemptAutoRestart(state: AutoRestartState, nowMs: number): boolean {
  if (state.attemptsUsed >= AUTO_RESTART_MAX_ATTEMPTS) return false
  if (state.windowStartedAtMs !== null && nowMs - state.windowStartedAtMs >= AUTO_RESTART_WINDOW_MS) {
    return false
  }
  return true
}

/** Delay before the NEXT attempt, based on how many have been used so far. */
export function nextAutoRestartDelayMs(state: AutoRestartState): number {
  return AUTO_RESTART_DELAYS_MS[state.attemptsUsed] ?? AUTO_RESTART_DELAYS_MS[AUTO_RESTART_DELAYS_MS.length - 1]
}

/** Records one attempt taken at `nowMs`, opening the window on the first one. */
export function recordAutoRestartAttempt(state: AutoRestartState, nowMs: number): AutoRestartState {
  return {
    attemptsUsed: state.attemptsUsed + 1,
    windowStartedAtMs: state.windowStartedAtMs ?? nowMs,
  }
}
