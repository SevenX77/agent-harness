import { describe, expect, it } from "vitest"
import { buildEdges, INPUT_ID, OUTPUT_ID } from "./buildEdges"
import {
  GLOBAL_INPUT_SOURCE_HANDLE_ID,
  GLOBAL_OUTPUT_TARGET_HANDLE_ID,
  SKILL_FLOW_SOURCE_HANDLE_ID,
  SKILL_FLOW_TARGET_HANDLE_ID,
} from "./subgraph-bridge-handles"
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
    const edges = buildEdges([node("entry", ["input"]), node("final", ["entry"], true)])
    const ids = edgeIds(edges)

    expect(ids).toEqual([`${INPUT_ID}->entry`, "entry->final", `final->${OUTPUT_ID}`])
    expect(edges).toEqual([
      expect.objectContaining({
        sourceHandle: GLOBAL_INPUT_SOURCE_HANDLE_ID,
        targetHandle: SKILL_FLOW_TARGET_HANDLE_ID,
      }),
      expect.objectContaining({
        sourceHandle: SKILL_FLOW_SOURCE_HANDLE_ID,
        targetHandle: SKILL_FLOW_TARGET_HANDLE_ID,
      }),
      expect.objectContaining({
        sourceHandle: SKILL_FLOW_SOURCE_HANDLE_ID,
        targetHandle: GLOBAL_OUTPUT_TARGET_HANDLE_ID,
      }),
    ])
  })

  it("keeps context controls on phase edges but folds boundary controls into the IO nodes", () => {
    const edges = buildEdges([node("entry", ["input"]), node("final", ["entry"], true)])

    expect(edges.find((edge) => edge.source === INPUT_ID)?.data?.showContextControl).toBe(false)
    expect(edges.find((edge) => edge.source === "entry" && edge.target === "final")?.data?.showContextControl).toBe(true)
    expect(edges.find((edge) => edge.target === OUTPUT_ID)?.data?.showContextControl).toBe(false)
  })

  it("keeps IO boundary edges reconnectable like ordinary canvas edges", () => {
    const edges = buildEdges([node("entry", ["input"]), node("final", ["entry"], true)])
    const inputEdge = edges.find((edge) => edge.source === INPUT_ID)
    const outputEdge = edges.find((edge) => edge.target === OUTPUT_ID)

    expect(inputEdge?.reconnectable).toBeUndefined()
    expect(inputEdge?.deletable).toBeUndefined()
    expect(outputEdge?.reconnectable).toBeUndefined()
    expect(outputEdge?.deletable).toBeUndefined()
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
