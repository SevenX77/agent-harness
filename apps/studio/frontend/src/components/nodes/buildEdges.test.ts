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
  it("renders declared phase dependencies plus graph boundary edges", () => {
    const ids = edgeIds(buildEdges([node("step1", []), node("step2", ["step1"])]))

    expect(ids).toContain("step1->step2")
    expect(ids).toContain(`${INPUT_ID}->step1`)
    expect(ids).toContain(`step2->${OUTPUT_ID}`)
    expect(ids).toHaveLength(3)
  })

  it("synthesizes input and output edges for a single phase", () => {
    expect(edgeIds(buildEdges([node("solo", [])]))).toEqual([
      `${INPUT_ID}->solo`,
      `solo->${OUTPUT_ID}`,
    ])
  })

  it("synthesizes output edges for leaf phases", () => {
    const ids = edgeIds(buildEdges([node("a", []), node("b", ["a"])]))

    expect(ids).toEqual([`${INPUT_ID}->a`, "a->b", `b->${OUTPUT_ID}`])
  })

  it("preserves real phase->phase fan-in", () => {
    const ids = edgeIds(
      buildEdges([
        node("a", []),
        node("b", ["a"]),
        node("c", ["a"]),
        node("d", ["b", "c"]),
      ]),
    )

    expect(ids).toContain("a->b")
    expect(ids).toContain("a->c")
    expect(ids).toContain("b->d")
    expect(ids).toContain("c->d")
    expect(ids).toContain(`${INPUT_ID}->a`)
    expect(ids).toContain(`d->${OUTPUT_ID}`)
    expect(ids).toHaveLength(6)
  })

  it("connects input directly to output for an empty graph", () => {
    expect(edgeIds(buildEdges([]))).toEqual([`${INPUT_ID}->${OUTPUT_ID}`])
  })
})
