import { describe, expect, it } from "vitest"

import { createGateEffectFold } from "./gate-effect-fold"
import type { GateProjection } from "./gate-state"

const compilePass: GateProjection = {
  stage: "compile-pass",
  effects: [{ kind: "close-drawers" }],
}

function compileFail(message: string): GateProjection {
  return {
    stage: "compile-fail",
    effects: [
      {
        kind: "open-drawer",
        gate: "compile",
        errors: [{ file: "GRAPH.md", line: 1, field: null, severity: "fatal", message }],
      },
    ],
  }
}

function runStarted(runId: string): GateProjection {
  return {
    stage: "running",
    effects: [
      { kind: "follow-run", runId },
      { kind: "close-drawers" },
      { kind: "open-trace" },
    ],
  }
}

const compileStarted: GateProjection = {
  stage: "compiling",
  effects: [{ kind: "close-drawers" }],
}

describe("createGateEffectFold", () => {
  it("folds the second arrival of one occurrence", () => {
    // The click handler projects the HTTP response and the event stream projects the
    // backend broadcast. Both describe the SAME compile, so both project identically
    // — the drawer must not pop twice (决议 2026-08-09 D2).
    const fold = createGateEffectFold()

    expect(fold.shouldRunEffects("demo", compilePass)).toBe(true)
    expect(fold.shouldRunEffects("demo", compilePass)).toBe(false)
  })

  it("runs the effects of a second compile that produced the identical artifact", () => {
    // The reported defect: compiling unchanged source twice yields the same content
    // hash, and the old ledger read that as "already handled". The `started` event
    // separates the two occurrences, so the second pass is not an adjacent repeat.
    const fold = createGateEffectFold()

    expect(fold.shouldRunEffects("demo", compilePass)).toBe(true)
    expect(fold.shouldRunEffects("demo", compileStarted)).toBe(true)
    expect(fold.shouldRunEffects("demo", compilePass)).toBe(true)
  })

  it("runs the effects of a second failure carrying a different defect set", () => {
    // Two failures both land on `compile-fail`; only the drawer payload differs.
    // Comparing the projection sees that difference, comparing the stage would not.
    const fold = createGateEffectFold()

    expect(fold.shouldRunEffects("demo", compileFail("first"))).toBe(true)
    expect(fold.shouldRunEffects("demo", compileFail("second"))).toBe(true)
  })

  it("follows a second run that started while the stage was already running", () => {
    // `run_manager` keys its records by run_id with no per-skill mutual exclusion, so
    // two runs of one skill can be live at once. Both project stage `running`; only
    // the follow-run payload distinguishes them. Folding here would leave the Trace
    // panel pinned to the previous run (决议 2026-08-09 D2).
    const fold = createGateEffectFold()

    expect(fold.shouldRunEffects("demo", runStarted("run-1"))).toBe(true)
    expect(fold.shouldRunEffects("demo", runStarted("run-2"))).toBe(true)
  })

  it("compares key-for-key rather than by serialised field order", () => {
    // The two transports build their error objects independently; a difference in key
    // order describes the same defect and must still fold.
    const fold = createGateEffectFold()
    const fromClick: GateProjection = {
      stage: "compile-fail",
      effects: [
        {
          kind: "open-drawer",
          gate: "compile",
          errors: [{ file: "GRAPH.md", line: 1, field: null, severity: "fatal", message: "boom" }],
        },
      ],
    }
    const fromBroadcast: GateProjection = {
      stage: "compile-fail",
      effects: [
        {
          kind: "open-drawer",
          gate: "compile",
          errors: [{ message: "boom", severity: "fatal", field: null, line: 1, file: "GRAPH.md" }],
        },
      ],
    }

    expect(fold.shouldRunEffects("demo", fromClick)).toBe(true)
    expect(fold.shouldRunEffects("demo", fromBroadcast)).toBe(false)
  })

  it("keeps one skill's outcomes from folding another's", () => {
    const fold = createGateEffectFold()

    expect(fold.shouldRunEffects("demo", compilePass)).toBe(true)
    expect(fold.shouldRunEffects("other", compilePass)).toBe(true)
    expect(fold.shouldRunEffects("demo", compilePass)).toBe(false)
  })
})
