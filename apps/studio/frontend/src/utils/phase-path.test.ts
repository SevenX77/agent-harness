import { describe, expect, it } from "vitest"
import type { CallbackEvent } from "@/api/types"
import { childPhasePath, isRootPhasePath, phasePathOf } from "./phase-path"

function event(partial: Partial<CallbackEvent>): CallbackEvent {
  return { schema_version: "1.0", event_type: "phase_start", timestamp: "2026-08-20T00:00:00Z", ...partial } as CallbackEvent
}

describe("phasePathOf — a phase's identity inside one run", () => {
  it("is the bare name for a phase running at root level", () => {
    expect(phasePathOf(event({ phase_name: "draft" }))).toBe("draft")
    // The engine leaves the field null rather than empty at root level.
    expect(phasePathOf(event({ phase_name: "draft", subgraph_path: null }))).toBe("draft")
  })

  it("prefixes the enclosing subgraph chain the engine stamped", () => {
    expect(phasePathOf(event({ phase_name: "extract", subgraph_path: "event_timeline" })))
      .toBe("event_timeline.extract")
    expect(phasePathOf(event({ phase_name: "score", subgraph_path: "outer.inner" })))
      .toBe("outer.inner.score")
  })

  it("keeps two same-named phases in different subgraphs apart", () => {
    const left = phasePathOf(event({ phase_name: "review", subgraph_path: "timeline" }))
    const right = phasePathOf(event({ phase_name: "review", subgraph_path: "characters" }))

    expect(left).not.toBe(right)
  })

  it("falls back to current_phase, and answers null when the event names no phase", () => {
    expect(phasePathOf(event({ current_phase: "draft" }))).toBe("draft")
    expect(phasePathOf(event({ event_type: "run_ended" }))).toBeNull()
  })
})

describe("childPhasePath / isRootPhasePath", () => {
  it("extends a container's path with the child phase name", () => {
    expect(childPhasePath("event_timeline", "extract")).toBe("event_timeline.extract")
    expect(childPhasePath("outer.inner", "score")).toBe("outer.inner.score")
  })

  it("calls exactly the paths with no enclosing container root-level", () => {
    expect(isRootPhasePath("draft")).toBe(true)
    expect(isRootPhasePath("event_timeline.extract")).toBe(false)
  })
})
