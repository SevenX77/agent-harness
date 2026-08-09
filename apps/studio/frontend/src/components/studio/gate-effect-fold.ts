/**
 * Decides whether a freshly computed gate projection must run its side effects.
 *
 * One gate occurrence reaches the frontend twice: the click handler projects its own
 * HTTP response, and the event stream projects the backend's `skill_gate` broadcast
 * of that same occurrence. Both describe one thing, so both project identically —
 * folding the second is what keeps the error drawer from popping twice.
 *
 * What counts as "the same" is the whole projection: the stage plus every effect and
 * its payload. Never the artifact's content hash. A content hash identifies a BUILD,
 * not an OCCURRENCE — compiling unchanged source twice produces one hash — and the
 * ledger that used it read the second compile as already handled, which stranded the
 * toolbar (决议 2026-08-09 D2). Two occurrences that project identically are asking
 * the UI for the same result, so running their effects once is indistinguishable
 * from running them twice; two that differ anywhere, including in a payload the
 * stage alone cannot see, both run.
 *
 * Only the latest projection per skill is kept. This is deliberately NOT a history:
 * the question is whether this arrival repeats the one before it, and a longer memory
 * would start swallowing genuine repeats again.
 */

import type { GateProjection } from "./gate-state"

export interface GateEffectFold {
  /**
   * True when this projection's effects must run. Records the projection as the
   * skill's latest either way, so the next arrival is compared against this one.
   */
  shouldRunEffects(skillId: string, projection: GateProjection): boolean
}

/**
 * Key-order-independent serialisation.
 *
 * The two transports build their payloads independently — one from an HTTP response
 * body, one from a websocket frame — so the same defect can arrive with its fields in
 * a different order. That describes the same thing and must still fold.
 */
function fingerprint(projection: GateProjection): string {
  return JSON.stringify(projection, (_key, value: unknown) => {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return value
    }
    const entries = Object.entries(value as Record<string, unknown>)
    entries.sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
    return Object.fromEntries(entries)
  })
}

export function createGateEffectFold(): GateEffectFold {
  const latestBySkill = new Map<string, string>()

  return {
    shouldRunEffects(skillId, projection) {
      const current = fingerprint(projection)
      if (latestBySkill.get(skillId) === current) {
        return false
      }
      latestBySkill.set(skillId, current)
      return true
    },
  }
}
