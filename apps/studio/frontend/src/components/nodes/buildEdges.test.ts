import { describe, expect, it } from "vitest"
import { buildEdges, INPUT_ID, OUTPUT_ID } from "./buildEdges"
import type { SkillGraphNode } from "./types"

function node(id: string, dependsOn: string[], isOutput = false): SkillGraphNode {
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
      isOutput,
    },
  } as unknown as SkillGraphNode
}

function edgeIds(edges: ReturnType<typeof buildEdges>): string[] {
  return edges.map((edge) => `${edge.source}->${edge.target}`)
}

describe("buildEdges", () => {
  it("renders declared phase dependencies only", () => {
    const ids = edgeIds(buildEdges([node("step1", []), node("step2", ["step1"])]))

    expect(ids).toEqual(["step1->step2"])
  })

  it("does not synthesize input or output edges for an isolated phase", () => {
    expect(edgeIds(buildEdges([node("solo", [])]))).toEqual([])
  })

  it("keeps leaf phases unconnected unless the document marks them as output", () => {
    const ids = edgeIds(buildEdges([node("a", []), node("b", ["a"])]))

    expect(ids).toEqual(["a->b"])
  })

  it("renders explicit input and output declarations", () => {
    const ids = edgeIds(buildEdges([node("entry", ["input"]), node("final", ["entry"], true)]))

    expect(ids).toEqual([`${INPUT_ID}->entry`, "entry->final", `final->${OUTPUT_ID}`])
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
    expect(ids).toHaveLength(4)
  })

  it("renders no edges for an empty graph", () => {
    expect(edgeIds(buildEdges([]))).toEqual([])
  })
})
