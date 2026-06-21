import { describe, expect, it } from "vitest"
import {
  addAgentStep,
  nextStepId,
  parseAgentSteps,
  removeAgentStep,
  reorderAgentSteps,
  updateAgentStep,
} from "./agent-steps"

const BODY = `<role>
You are an editor.
</role>

<goal>
Segment the chapter.
</goal>

<step id="S1" name="read_reference">
Read @reference:R1.
</step>

<step id="S2" name="review">
Ask @subagent:echo_expert.
</step>

<step id="S3" name="finish">
Call @tool:finish_task.
</step>

<example id="E1">
A setting explanation is separate.
</example>
`

describe("parseAgentSteps", () => {
  it("extracts id, name and trimmed content for each step in order", () => {
    const steps = parseAgentSteps(BODY)
    expect(steps.map((s) => s.id)).toEqual(["S1", "S2", "S3"])
    expect(steps.map((s) => s.name)).toEqual(["read_reference", "review", "finish"])
    expect(steps[0].content).toBe("Read @reference:R1.")
  })

  it("returns an empty list when there are no steps", () => {
    expect(parseAgentSteps("<role>x</role>")).toEqual([])
  })
})

describe("reorderAgentSteps", () => {
  it("reorders step blocks while preserving role/goal/example and whitespace", () => {
    const next = reorderAgentSteps(BODY, ["S3", "S1", "S2"])
    expect(parseAgentSteps(next).map((s) => s.id)).toEqual(["S3", "S1", "S2"])
    // Non-step content is untouched.
    expect(next).toContain("<role>\nYou are an editor.\n</role>")
    expect(next).toContain("<example id=\"E1\">")
    // No content is lost: same set of step bodies, just reordered.
    expect(next).toContain("Call @tool:finish_task.")
    expect(next).toContain("Read @reference:R1.")
  })

  it("is a no-op when orderedIds is not a clean permutation", () => {
    expect(reorderAgentSteps(BODY, ["S1", "S2"])).toBe(BODY)
    expect(reorderAgentSteps(BODY, ["S1", "S2", "ghost"])).toBe(BODY)
  })
})

describe("removeAgentStep", () => {
  it("removes only the named step and keeps the rest", () => {
    const next = removeAgentStep(BODY, "S2")
    expect(parseAgentSteps(next).map((s) => s.id)).toEqual(["S1", "S3"])
    expect(next).not.toContain("Ask @subagent:echo_expert.")
    expect(next).toContain("<example id=\"E1\">")
  })

  it("is a no-op for an unknown id", () => {
    expect(removeAgentStep(BODY, "S9")).toBe(BODY)
  })
})

describe("addAgentStep", () => {
  it("appends after the last step and round-trips through the parser", () => {
    const id = nextStepId(parseAgentSteps(BODY).map((s) => s.id))
    expect(id).toBe("S4")
    const next = addAgentStep(BODY, { id, name: "wrap_up", content: "Summarise." })
    const ids = parseAgentSteps(next).map((s) => s.id)
    expect(ids).toEqual(["S1", "S2", "S3", "S4"])
    expect(parseAgentSteps(next)[3]).toMatchObject({ name: "wrap_up", content: "Summarise." })
    // example block stays after the steps.
    expect(next.indexOf("wrap_up")).toBeLessThan(next.indexOf("<example"))
  })

  it("inserts after <goal> when the body has no steps yet", () => {
    const body = "<role>r</role>\n\n<goal>g</goal>\n"
    const next = addAgentStep(body, { id: "S1", name: "first", content: "do it" })
    expect(parseAgentSteps(next).map((s) => s.id)).toEqual(["S1"])
    expect(next.indexOf("<goal>")).toBeLessThan(next.indexOf("<step"))
  })
})

describe("updateAgentStep", () => {
  it("rewrites name and content in place, keeping id and position", () => {
    const next = updateAgentStep(BODY, "S2", { name: "review_boundary", content: "New body." })
    const steps = parseAgentSteps(next)
    expect(steps.map((s) => s.id)).toEqual(["S1", "S2", "S3"])
    expect(steps[1]).toMatchObject({ id: "S2", name: "review_boundary", content: "New body." })
  })
})
