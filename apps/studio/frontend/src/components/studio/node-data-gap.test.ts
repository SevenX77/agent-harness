import { describe, expect, it } from "vitest"
import type { FieldSupplyEntry, GraphTopologyItem } from "@/api/types"
import { dataGapErrorsByNode } from "./node-compile-errors"

// n2-canvas#10 (data-gap-viz, PM 2026-06-20): the canvas node's ONLY data-gap job is
// to show a compile-style CONFLICT ERROR when a required input field is NOT supplied by
// the upstream blackboard — NO checkbox UI, NO type-equality red-X. This pure helper
// projects the backend `graph_topology[].field_supply` (each row keyed by phase id;
// `supplied=false` = a data gap) onto the SAME CompileError-by-node shape the canvas
// already renders, so a node shows data gaps alongside compile + lint errors.

function supply(field: string, supplied: boolean, source: FieldSupplyEntry["source"]): FieldSupplyEntry {
  return { field, supplied, source, producer_phase: null }
}

function row(id: string, fieldSupply: FieldSupplyEntry[] | undefined): GraphTopologyItem {
  return { id, src: "", depends_on: [], mode: "logic", field_supply: fieldSupply }
}

describe("dataGapErrorsByNode (n2-canvas#10 — unsupplied input field → node conflict error)", () => {
  it("emits a node error for each input field whose supply is false", () => {
    const byNode = dataGapErrorsByNode([
      row("review", [supply("summary", false, "none"), supply("title", true, "phase")]),
    ])
    expect(Object.keys(byNode)).toEqual(["review"])
    expect(byNode.review).toHaveLength(1)
    const error = byNode.review[0]
    expect(error.field).toBe("summary")
    expect(error.severity).toBe("fatal")
    expect(error.message).toContain("summary")
    expect(error.message.toLowerCase()).toContain("upstream")
  })

  it("emits NO error when every input field is supplied (phase or graph input)", () => {
    const byNode = dataGapErrorsByNode([
      row("draft", [supply("topic", true, "graph_input"), supply("seed", true, "phase")]),
    ])
    expect(byNode).toEqual({})
  })

  it("collects multiple unsupplied fields on the same node", () => {
    const byNode = dataGapErrorsByNode([
      row("merge", [supply("a", false, "none"), supply("b", false, "none"), supply("c", true, "phase")]),
    ])
    expect(byNode.merge).toHaveLength(2)
    expect(byNode.merge.map((e) => e.field).sort()).toEqual(["a", "b"])
  })

  it("keeps gaps on separate node ids", () => {
    const byNode = dataGapErrorsByNode([
      row("first", [supply("x", false, "none")]),
      row("second", [supply("y", false, "none")]),
    ])
    expect(Object.keys(byNode).sort()).toEqual(["first", "second"])
  })

  it("skips rows with no field_supply projection and empty input", () => {
    expect(dataGapErrorsByNode([row("noproj", undefined)])).toEqual({})
    expect(dataGapErrorsByNode(null)).toEqual({})
    expect(dataGapErrorsByNode([])).toEqual({})
  })

  it("produces a file-less, line-less CompileError (data gap is not a source-location error)", () => {
    const byNode = dataGapErrorsByNode([row("review", [supply("summary", false, "none")])])
    const error = byNode.review[0]
    expect(error.file).toBeNull()
    expect(error.line).toBeNull()
  })
})
