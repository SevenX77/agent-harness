import { describe, expect, it } from 'vitest'
import {
  AUTO_RESTART_DELAYS_MS,
  AUTO_RESTART_MAX_ATTEMPTS,
  AUTO_RESTART_WINDOW_MS,
  canAttemptAutoRestart,
  initialAutoRestartState,
  nextAutoRestartDelayMs,
  recordAutoRestartAttempt,
} from './runtime-gate-auto-restart'

describe('runtime-gate-auto-restart — bounded policy math', () => {
  it('admits up to AUTO_RESTART_MAX_ATTEMPTS attempts, then refuses', () => {
    let state = initialAutoRestartState()
    let now = 0

    for (let i = 0; i < AUTO_RESTART_MAX_ATTEMPTS; i += 1) {
      expect(canAttemptAutoRestart(state, now)).toBe(true)
      state = recordAutoRestartAttempt(state, now)
      now += 1
    }

    expect(canAttemptAutoRestart(state, now)).toBe(false)
  })

  it('uses the fixed 1s/4s/16s delay schedule, in order', () => {
    let state = initialAutoRestartState()
    const seen: number[] = []
    let now = 0

    for (let i = 0; i < AUTO_RESTART_MAX_ATTEMPTS; i += 1) {
      seen.push(nextAutoRestartDelayMs(state))
      state = recordAutoRestartAttempt(state, now)
      now += 1
    }

    expect(seen).toEqual([...AUTO_RESTART_DELAYS_MS])
  })

  it('refuses once the window has elapsed since the first attempt, even under the attempt cap', () => {
    // One attempt used — well under the cap — but the next ask arrives after
    // the window: still refused. The window is a hard ceiling on the whole
    // episode, not a per-attempt cooldown.
    let state = initialAutoRestartState()
    state = recordAutoRestartAttempt(state, 0)

    expect(canAttemptAutoRestart(state, AUTO_RESTART_WINDOW_MS - 1)).toBe(true)
    expect(canAttemptAutoRestart(state, AUTO_RESTART_WINDOW_MS)).toBe(false)
  })

  it('does NOT renew after being exhausted, no matter how much time passes', () => {
    // "到限就停,不再试" — exhausting the cap is a terminal state for this
    // episode. Unlike Restart=always, nothing here retries again on its own;
    // only a fresh `initialAutoRestartState()` (a manual Retry) resets it.
    let state = initialAutoRestartState()
    let now = 0
    for (let i = 0; i < AUTO_RESTART_MAX_ATTEMPTS; i += 1) {
      state = recordAutoRestartAttempt(state, now)
      now += 1
    }

    expect(canAttemptAutoRestart(state, now + AUTO_RESTART_WINDOW_MS * 100)).toBe(false)
  })

  it('a fresh episode from initialAutoRestartState() always permits a first attempt', () => {
    expect(canAttemptAutoRestart(initialAutoRestartState(), 0)).toBe(true)
    expect(canAttemptAutoRestart(initialAutoRestartState(), Number.MAX_SAFE_INTEGER)).toBe(true)
  })
})
