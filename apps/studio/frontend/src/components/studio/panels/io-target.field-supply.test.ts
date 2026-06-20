import { describe, expect, it } from "vitest"
import type { GraphTopologyItem, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/nodes"
import { INPUT_ID, OUTPUT_ID } from "@/components/nodes"
import { fieldSupplyByField, type SelectedNode } from "./io-target"

// n2-canvas#10 (data-gap-viz): fieldSupplyByField is the consumer of the REAL new
// backend field graph_topology[].field_supply (produced by the backend
// compute_field_supply in services/canvas_data_gap.py and attached per row in
// services/skills.py _topology_row). These tests pin the producer->consumer join:
// the selected node's id is the phase name, which keys into the graph_topology row
// carrying that phase's field_supply[]. If this join regressed (wrong key, or
// reading some hand-rolled client projection instead of the backend array), the
// i/o panel would mark the wrong fields as data gaps — exactly the gap this item
// closes. So the fixtures use the literal backend shape, not an invented one.

function makeNode(id: string, data: Partial<SkillGraphNodeData> = {}): SelectedNode {
  return {
    id,
    data: {
      skillId: "demo",
      label: id,
      mode: "logic",
      status: "idle",
      dependsOn: [],
      ...data,
    } as SkillGraphNodeData,
  }
}

// One real graph_topology array exactly as GET /skills/{id} now ships it: each row
// carries io_fields + field_supply. The "enrich" phase depends on "fetch" and has
// three inputs — one fed by an upstream phase, one by the run's graph input, one
// with no supplier at all (the data gap).
const TOPOLOGY: GraphTopologyItem[] = [
  {
    id: "fetch",
    src: "phases/fetch",
    depends_on: [],
    mode: "logic",
    io_fields: { inputs: {}, outputs: { doc: { type: "string" } } },
    field_supply: [],
  },
  {
    id: "enrich",
    src: "phases/enrich",
    depends_on: ["fetch"],
    mode: "logic",
    io_fields: {
      inputs: { doc: { type: "string" }, topic: { type: "string" }, orphan: { type: "string" } },
      outputs: { enriched: { type: "string" } },
    },
    field_supply: [
      { field: "doc", supplied: true, source: "phase", producer_phase: "fetch" },
      { field: "topic", supplied: true, source: "graph_input", producer_phase: null },
      { field: "orphan", supplied: false, source: "none", producer_phase: null },
    ],
  },
]

const DETAIL = { graph_topology: TOPOLOGY } as unknown as SkillDetail

describe("fieldSupplyByField (n2-canvas#10 per-node data-gap projection)", () => {
  it("maps each input field of the selected phase to its backend field_supply entry", () => {
    const map = fieldSupplyByField(makeNode("enrich"), DETAIL)

    expect(map.size).toBe(3)
    expect(map.get("doc")).toEqual({
      field: "doc",
      supplied: true,
      source: "phase",
      producer_phase: "fetch",
    })
    expect(map.get("topic")).toEqual({
      field: "topic",
      supplied: true,
      source: "graph_input",
      producer_phase: null,
    })
    // The data gap: an input field nothing upstream supplies.
    expect(map.get("orphan")?.supplied).toBe(false)
    expect(map.get("orphan")?.source).toBe("none")
  })

  it("joins on the phase id (node.id), not the label, so it reads the right row", () => {
    // The node carries a human label distinct from its phase id; the resolver must
    // key off the id that matches graph_topology[].id.
    const map = fieldSupplyByField(makeNode("enrich", { label: "Enrich Document" }), DETAIL)

    expect(map.get("doc")?.producer_phase).toBe("fetch")
  })

  it("returns an empty map for the global input/output nodes and no selection", () => {
    for (const selection of [
      null,
      makeNode(INPUT_ID),
      makeNode(OUTPUT_ID),
    ] satisfies SelectedNode[]) {
      expect(fieldSupplyByField(selection, DETAIL).size).toBe(0)
    }
  })

  it("returns an empty map when the backend row carries no field_supply (older payload)", () => {
    const detailNoSupply = {
      graph_topology: [{ id: "enrich", src: "phases/enrich", depends_on: [], mode: "logic" }],
    } as unknown as SkillDetail

    expect(fieldSupplyByField(makeNode("enrich"), detailNoSupply).size).toBe(0)
  })
})
