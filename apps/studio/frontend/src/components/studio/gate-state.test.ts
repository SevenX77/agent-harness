import { describe, expect, it } from "vitest"

import { createGateEffectFold } from "./gate-effect-fold"
import { parseSkillGateEvent, projectGateEvent, type SkillGateEvent } from "./gate-state"

function event(overrides: Partial<SkillGateEvent> = {}): SkillGateEvent {
  return {
    skillId: "demo",
    gate: "compile",
    outcome: "pass",
    contentHash: "sha256:abc",
    defectCount: 0,
    ...overrides,
  }
}

describe("a settled run announces itself the same way whether it was a run or a predict", () => {
  // Decision 2026-08-09 D7/D9: a predict produces a run record, streams the same
  // events, ends with the same `run_ended`, and appears in the same list. What
  // concludes a run must therefore conclude a predict; gating the conclusion on
  // `gate === "run"` left a finished predict with no outcome toast, no list row,
  // and node badges still reading "running" (observed 2026-08-09).
  it("finalizes a predict that passed", () => {
    const { effects } = projectGateEvent(
      event({ gate: "predict", outcome: "pass", runId: "predict-2026-08-09T01-40-49_7754a5e9" }),
    )

    expect(effects).toContainEqual({
      kind: "finalize-run",
      runId: "predict-2026-08-09T01-40-49_7754a5e9",
    })
  })

  it("finalizes a run that passed", () => {
    const { effects } = projectGateEvent(
      event({ gate: "run", outcome: "pass", runId: "2026-08-09T01-42-54_1fd5582d" }),
    )

    expect(effects).toContainEqual({ kind: "finalize-run", runId: "2026-08-09T01-42-54_1fd5582d" })
  })

  it("finalizes a predict that failed — how it ended is still how it ended", () => {
    const { effects } = projectGateEvent(event({ gate: "predict", outcome: "fail", runId: "predict-x" }))

    expect(effects).toContainEqual({ kind: "finalize-run", runId: "predict-x" })
  })

  it("does not finalize a gate that only just started", () => {
    const { effects } = projectGateEvent(event({ gate: "predict", outcome: "started", runId: "predict-x" }))

    expect(effects.some((effect) => effect.kind === "finalize-run")).toBe(false)
  })

  it("does not finalize a compile — it produces no run", () => {
    const { effects } = projectGateEvent(event({ gate: "compile", outcome: "pass", runId: "predict-x" }))

    expect(effects.some((effect) => effect.kind === "finalize-run")).toBe(false)
  })

  it("finalizes nothing when the event does not name a run", () => {
    const { effects } = projectGateEvent(event({ gate: "predict", outcome: "pass", runId: null }))

    expect(effects.some((effect) => effect.kind === "finalize-run")).toBe(false)
  })
})

describe("projectGateEvent", () => {
  it("advances the toolbar to Predict when compile passes", () => {
    expect(projectGateEvent(event()).stage).toBe("compile-pass")
  })

  it("advances the toolbar to Run when predict passes", () => {
    expect(projectGateEvent(event({ gate: "predict" })).stage).toBe("predict-pass")
  })

  it("opens the matching drawer with the aggregated defect set on failure", () => {
    const projection = projectGateEvent(
      event({
        outcome: "fail",
        defectCount: 2,
        errors: [
          { file: "GRAPH.md", line: 3, field: null, severity: "fatal", message: "first" },
          { file: null, line: null, field: null, severity: "fatal", message: "second" },
        ],
      }),
    )

    expect(projection.stage).toBe("compile-fail")
    expect(projection.effects).toEqual([
      {
        kind: "open-drawer",
        gate: "compile",
        errors: [
          { file: "GRAPH.md", line: 3, field: null, severity: "fatal", message: "first" },
          { file: null, line: null, field: null, severity: "fatal", message: "second" },
        ],
      },
    ])
  })

  it("points the trace stream at a run as soon as it starts", () => {
    const projection = projectGateEvent(
      event({ gate: "run", outcome: "started", runId: "2026-08-03T09-00-00_abc" }),
    )

    expect(projection.stage).toBe("running")
    expect(projection.effects).toContainEqual({
      kind: "follow-run",
      runId: "2026-08-03T09-00-00_abc",
    })
  })

  it("points the trace stream at a predict as soon as it starts", () => {
    // B-fix (decision 2026-08-07): predict streams events through the same run
    // websocket, so a started predict must re-point the stream — otherwise the
    // opened trace panel keeps showing the PREVIOUS run's events.
    const projection = projectGateEvent(
      event({ gate: "predict", outcome: "started", runId: "predict-abc" }),
    )

    expect(projection.effects).toContainEqual({
      kind: "follow-run",
      runId: "predict-abc",
    })
  })

  it("leaves a finished run on predict-pass so it stays immediately runnable", () => {
    expect(projectGateEvent(event({ gate: "run", outcome: "pass", runId: "r1" })).stage).toBe(
      "predict-pass",
    )
    expect(projectGateEvent(event({ gate: "run", outcome: "fail", runId: "r1" })).stage).toBe(
      "run-fail",
    )
  })
})

describe("parseSkillGateEvent", () => {
  it("reads the backend payload", () => {
    const parsed = parseSkillGateEvent({
      type: "skill_gate",
      skill_id: "demo",
      gate: "run",
      outcome: "started",
      content_hash: "sha256:abc",
      run_id: "r1",
      defect_count: 0,
    })

    expect(parsed).toEqual({
      skillId: "demo",
      gate: "run",
      outcome: "started",
      contentHash: "sha256:abc",
      runId: "r1",
      defectCount: 0,
      errors: undefined,
      predictExport: null,
    })
  })

  it("ignores payloads that are not gate outcomes or name no skill", () => {
    expect(parseSkillGateEvent({ type: "roles_changed" })).toBeNull()
    expect(parseSkillGateEvent({ type: "skill_gate", gate: "compile", outcome: "pass" })).toBeNull()
    expect(
      parseSkillGateEvent({ type: "skill_gate", skill_id: "demo", gate: "bogus", outcome: "pass" }),
    ).toBeNull()
  })
})

describe("two-path parity", () => {
  it("projects a human click and a copilot broadcast identically", () => {
    // Same outcome, two origins: the click handler builds the event from its HTTP
    // response, the event stream parses it off the bus. 决议验收判据 1 says the
    // resulting state and side effects must be indistinguishable.
    const fromClick: SkillGateEvent = {
      skillId: "demo",
      gate: "compile",
      outcome: "fail",
      contentHash: "sha256:abc",
      defectCount: 1,
      errors: [{ file: null, line: null, field: null, severity: "fatal", message: "boom" }],
    }
    const fromBroadcast = parseSkillGateEvent({
      type: "skill_gate",
      skill_id: "demo",
      gate: "compile",
      outcome: "fail",
      content_hash: "sha256:abc",
      run_id: null,
      defect_count: 1,
      errors: [{ file: null, line: null, field: null, severity: "fatal", message: "boom" }],
    })

    expect(fromBroadcast).not.toBeNull()
    expect(projectGateEvent(fromClick)).toEqual(projectGateEvent(fromBroadcast!))
  })

  it("projects one occurrence identically enough for the effect fold to collapse it", () => {
    // This is what lets `gate-effect-fold` recognise a redelivery without any event
    // id: the two transports must project the same thing, byte differences in how
    // each built its payload included. If this ever diverges, the drawer pops twice.
    const fold = createGateEffectFold()
    const fromClick: SkillGateEvent = {
      skillId: "demo",
      gate: "compile",
      outcome: "fail",
      contentHash: "sha256:abc",
      defectCount: 1,
      errors: [{ file: null, line: null, field: null, severity: "fatal", message: "boom" }],
    }
    const fromBroadcast = parseSkillGateEvent({
      type: "skill_gate",
      skill_id: "demo",
      gate: "compile",
      outcome: "fail",
      content_hash: "sha256:abc",
      run_id: null,
      defect_count: 1,
      errors: [{ file: null, line: null, field: null, severity: "fatal", message: "boom" }],
    })

    expect(fold.shouldRunEffects("demo", projectGateEvent(fromClick))).toBe(true)
    expect(fold.shouldRunEffects("demo", projectGateEvent(fromBroadcast!))).toBe(false)
  })
})

describe("trace panel follows both gates", () => {
  it("puts the trace on screen when predict or run starts", () => {
    // The click path opened the timeline itself, so a copilot-driven gate left the
    // human on whatever panel they had open while events streamed out of sight.
    for (const gate of ["predict", "run"] as const) {
      const { effects } = projectGateEvent({
        skillId: "s",
        gate,
        outcome: "started",
        runId: gate === "run" ? "run-1" : "predict-1",
      })

      expect(effects.some((effect) => effect.kind === "open-trace")).toBe(true)
    }
  })

  it("leaves the panel alone once a gate finishes", () => {
    for (const outcome of ["pass", "fail"] as const) {
      const { effects } = projectGateEvent({ skillId: "s", gate: "run", outcome, runId: "run-1" })

      expect(effects.some((effect) => effect.kind === "open-trace")).toBe(false)
    }
  })

  it("does not open the trace for a compile", () => {
    const { effects } = projectGateEvent({ skillId: "s", gate: "compile", outcome: "started" })

    expect(effects.some((effect) => effect.kind === "open-trace")).toBe(false)
  })
})
