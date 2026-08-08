import { describe, expect, it } from "vitest"

import { gateEventKey, parseSkillGateEvent, projectGateEvent, type SkillGateEvent } from "./gate-state"

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

describe("gateEventKey", () => {
  it("gives the same identity to a locally projected outcome and its broadcast", () => {
    const local = event({ outcome: "fail", errors: [{ file: null, line: null, field: null, severity: "fatal", message: "from the http response" }] })
    const broadcast = event({ outcome: "fail", errors: [{ file: null, line: null, field: null, severity: "fatal", message: "from the event bus" }] })

    expect(gateEventKey(local)).toBe(gateEventKey(broadcast))
  })

  it("separates outcomes of different skills, gates, artifacts and runs", () => {
    const base = event()
    expect(gateEventKey(base)).not.toBe(gateEventKey(event({ skillId: "other" })))
    expect(gateEventKey(base)).not.toBe(gateEventKey(event({ gate: "predict" })))
    expect(gateEventKey(base)).not.toBe(gateEventKey(event({ contentHash: "sha256:zzz" })))
    expect(gateEventKey(event({ gate: "run", runId: "r1" }))).not.toBe(
      gateEventKey(event({ gate: "run", runId: "r2" })),
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
    expect(gateEventKey(fromClick)).toBe(gateEventKey(fromBroadcast!))
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
