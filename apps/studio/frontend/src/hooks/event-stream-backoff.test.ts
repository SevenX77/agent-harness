import { describe, expect, it } from "vitest"
import {
  CONNECTION_LOST_FAILURE_THRESHOLD,
  CONNECTION_LOST_TIME_THRESHOLD_MS,
  RECONNECT_MAX_DELAY_MS,
  WS_AUTH_FAILURE_GIVEUP_THRESHOLD,
  WS_AUTH_REJECTED_CLOSE_CODE,
  isWsAuthRejection,
  nextReconnectDelay,
  nextReconnectDelayBase,
  shouldGiveUpOnAuthFailures,
  shouldShowConnectionLost,
} from "./event-stream-backoff"

/**
 * N0 Settings · Shell (atoms #5/#6) — pure backoff + connection-lost threshold.
 *
 * The reconnect schedule and the flicker-avoiding "connection lost" threshold
 * are unit-tested here without a live socket; the hook wiring is exercised by
 * the Playwright e2e (event refresh + warning indicator).
 */
describe("nextReconnectDelayBase", () => {
  it("doubles from 1s each attempt: 1s, 2s, 4s, 8s, 16s", () => {
    expect(nextReconnectDelayBase(0)).toBe(1_000)
    expect(nextReconnectDelayBase(1)).toBe(2_000)
    expect(nextReconnectDelayBase(2)).toBe(4_000)
    expect(nextReconnectDelayBase(3)).toBe(8_000)
    expect(nextReconnectDelayBase(4)).toBe(16_000)
  })

  it("caps at 30s and never exceeds it for large attempts", () => {
    expect(nextReconnectDelayBase(5)).toBe(RECONNECT_MAX_DELAY_MS)
    expect(nextReconnectDelayBase(6)).toBe(RECONNECT_MAX_DELAY_MS)
    expect(nextReconnectDelayBase(50)).toBe(RECONNECT_MAX_DELAY_MS)
  })

  it("treats negative / fractional attempts as the first attempt", () => {
    expect(nextReconnectDelayBase(-1)).toBe(1_000)
    expect(nextReconnectDelayBase(0.9)).toBe(1_000)
  })
})

describe("nextReconnectDelay (full jitter)", () => {
  it("returns 0 when random() is 0", () => {
    expect(nextReconnectDelay(2, () => 0)).toBe(0)
  })

  it("returns the full base when random() is 1", () => {
    expect(nextReconnectDelay(2, () => 1)).toBe(4_000)
    expect(nextReconnectDelay(10, () => 1)).toBe(RECONNECT_MAX_DELAY_MS)
  })

  it("stays within [0, base] for any random value (full jitter)", () => {
    for (const r of [0, 0.1, 0.37, 0.5, 0.99, 1]) {
      const base = nextReconnectDelayBase(3)
      const delay = nextReconnectDelay(3, () => r)
      expect(delay).toBeGreaterThanOrEqual(0)
      expect(delay).toBeLessThanOrEqual(base)
    }
  })

  it("clamps an out-of-range random into [0, 1] before scaling", () => {
    expect(nextReconnectDelay(2, () => -5)).toBe(0)
    expect(nextReconnectDelay(2, () => 5)).toBe(4_000)
  })
})

describe("shouldShowConnectionLost", () => {
  it("is false on a brief blip (few failures, little time) to avoid flicker", () => {
    expect(shouldShowConnectionLost(0, 0)).toBe(false)
    expect(shouldShowConnectionLost(1, 1_500)).toBe(false)
    expect(shouldShowConnectionLost(2, 9_000)).toBe(false)
  })

  it("is true once consecutive failures reach the threshold", () => {
    expect(shouldShowConnectionLost(CONNECTION_LOST_FAILURE_THRESHOLD, 0)).toBe(true)
    expect(shouldShowConnectionLost(CONNECTION_LOST_FAILURE_THRESHOLD + 5, 0)).toBe(true)
  })

  it("is true once cumulative time-without-connection exceeds the threshold", () => {
    expect(shouldShowConnectionLost(0, CONNECTION_LOST_TIME_THRESHOLD_MS)).toBe(true)
    expect(shouldShowConnectionLost(1, CONNECTION_LOST_TIME_THRESHOLD_MS + 2_000)).toBe(true)
  })

  it("returns to false immediately when both inputs reset to 0 (reconnect)", () => {
    expect(shouldShowConnectionLost(0, 0)).toBe(false)
  })
})

describe("isWsAuthRejection (R-F13)", () => {
  it("flags 4401 (sidecar auth-gate Unauthorized) as an auth rejection", () => {
    expect(isWsAuthRejection(WS_AUTH_REJECTED_CLOSE_CODE)).toBe(true)
    expect(isWsAuthRejection(4401)).toBe(true)
  })

  it("does NOT flag normal/abnormal transport closes as auth rejections", () => {
    // 1000 = normal, 1006 = abnormal (no close frame), 1011 = server error,
    // 1013 = try again later. Counting these as auth failures would falsely
    // give up the reconnect loop on a transient sidecar restart.
    expect(isWsAuthRejection(1000)).toBe(false)
    expect(isWsAuthRejection(1001)).toBe(false)
    expect(isWsAuthRejection(1006)).toBe(false)
    expect(isWsAuthRejection(1011)).toBe(false)
    expect(isWsAuthRejection(1013)).toBe(false)
  })

  it("treats undefined close code as non-auth (constructor failures, etc.)", () => {
    expect(isWsAuthRejection(undefined)).toBe(false)
  })
})

describe("shouldGiveUpOnAuthFailures (R-F13)", () => {
  it("does NOT give up before the threshold (5 consecutive 4401s)", () => {
    expect(shouldGiveUpOnAuthFailures(0)).toBe(false)
    expect(shouldGiveUpOnAuthFailures(1)).toBe(false)
    expect(shouldGiveUpOnAuthFailures(WS_AUTH_FAILURE_GIVEUP_THRESHOLD - 1)).toBe(false)
  })

  it("gives up at and beyond the threshold", () => {
    expect(shouldGiveUpOnAuthFailures(WS_AUTH_FAILURE_GIVEUP_THRESHOLD)).toBe(true)
    expect(shouldGiveUpOnAuthFailures(WS_AUTH_FAILURE_GIVEUP_THRESHOLD + 3)).toBe(true)
  })
})
