import { describe, expect, it } from "vitest"
import { buildEdges, INPUT_ID, OUTPUT_ID } from "./buildEdges"
import type { SkillGraphNode } from "./types"

function node(id: string, dependsOn: string[]): SkillGraphNode {
  return {
    id,
    type: "skill",
    position: { x: 0, y: 0 },
    data: {
      skillId: "demo",
      label: id,
      mode: "logic",
      role: null,
      tools: [],
      subagents: [],
      filePath: `phases/${id}/LOGIC.md`,
      status: "idle",
      dependsOn,
      subgraphPath: null,
      isExpanded: false,
    },
  } as unknown as SkillGraphNode
}

function edgeIds(edges: ReturnType<typeof buildEdges>): string[] {
  return edges.map((edge) => `${edge.source}->${edge.target}`)
}

describe("buildEdges", () => {
  it("maps the reserved 'input' dependency to the global Input node (not a dangling 'input' source)", () => {
    // <phase depends_on="input">step1</phase> — step1 is input-rooted.
    const ids = edgeIds(buildEdges([node("step1", ["input"]), node("step2", ["step1"])]))
    expect(ids).toContain(`${INPUT_ID}->step1`) // the fix: real global node, not "input"
    expect(ids).not.toContain("input->step1") // the bug: dangling source
    expect(ids).toContain("step1->step2")
  })

  it("links a disconnected phase (no deps) to the Input node", () => {
    const ids = edgeIds(buildEdges([node("solo", [])]))
    expect(ids).toContain(`${INPUT_ID}->solo`)
    expect(ids).toContain(`solo->${OUTPUT_ID}`) // also a leaf -> Output
  })

  it("links leaf phases (no dependents) to the Output node", () => {
    const ids = edgeIds(buildEdges([node("a", ["input"]), node("b", ["a"])]))
    // b is the only leaf.
    expect(ids).toContain(`b->${OUTPUT_ID}`)
    expect(ids).not.toContain(`a->${OUTPUT_ID}`)
  })

  it("preserves real phase->phase fan-in", () => {
    const ids = edgeIds(
      buildEdges([
        node("a", ["input"]),
        node("b", ["a"]),
        node("c", ["a"]),
        node("d", ["b", "c"]),
      ]),
    )
    expect(ids).toContain("b->d")
    expect(ids).toContain("c->d")
    expect(ids).toContain(`${INPUT_ID}->a`)
  })

  it("connects Input straight to Output for an empty graph", () => {
    expect(edgeIds(buildEdges([]))).toEqual([`${INPUT_ID}->${OUTPUT_ID}`])
  })
})
