import { describe, expect, it } from "vitest"
import { parseAgentSteps } from "./agent-steps"

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

  it("reads single-quoted attributes and keeps source offsets", () => {
    const body = `<step id='S9' name='solo'>Do it.</step>`
    const [step] = parseAgentSteps(body)
    expect(step.id).toBe("S9")
    expect(step.name).toBe("solo")
    expect(body.slice(step.start, step.end)).toBe(step.raw)
  })
})
