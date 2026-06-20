import { describe, expect, it } from "vitest"
import type { GoldenBaseline, GoldenBaselineCase } from "@/api/types"
import { goldenStateByNode } from "./node-golden"

function goldenCase(nodeId: string, caseId = `${nodeId}-case`): GoldenBaselineCase {
  return {
    case_id: caseId,
    node_id: nodeId,
    phase_id: nodeId,
    expected_output_ref: `golden/${nodeId}/expected.json`,
  }
}

function baseline(id: string, cases: GoldenBaselineCase[]): GoldenBaseline {
  return {
    id,
    source_run_id: "run-1",
    source_run_results_ref: null,
    baseline_ref: null,
    linked_input_id: "input-1",
    created_at: "2026-06-16T00:00:00Z",
    locked: false,
    content_path: `golden/${id}/baseline.json`,
    cases,
  }
}

describe("goldenStateByNode", () => {
  it("marks every node_id present in a baseline's cases as has-golden", () => {
    const byNode = goldenStateByNode([
      baseline("b1", [goldenCase("draft"), goldenCase("review")]),
    ])
    expect(byNode).toEqual({ draft: "has-golden", review: "has-golden" })
  })

  it("aggregates node_ids across multiple baselines", () => {
    const byNode = goldenStateByNode([
      baseline("b1", [goldenCase("draft")]),
      baseline("b2", [goldenCase("expand")]),
    ])
    expect(Object.keys(byNode).sort()).toEqual(["draft", "expand"])
    expect(byNode.draft).toBe("has-golden")
    expect(byNode.expand).toBe("has-golden")
  })

  it("returns an empty map for null / empty / cases-less baselines (no client re-derivation)", () => {
    expect(goldenStateByNode(null)).toEqual({})
    expect(goldenStateByNode([])).toEqual({})
    // A baseline whose `cases` was omitted by an older backend payload contributes nothing.
    expect(goldenStateByNode([baseline("b1", [])])).toEqual({})
    const noCases = { ...baseline("b1", []) }
    delete (noCases as { cases?: unknown }).cases
    expect(goldenStateByNode([noCases as GoldenBaseline])).toEqual({})
  })

  it("ignores cases with a missing / empty node_id rather than fabricating a node", () => {
    const byNode = goldenStateByNode([
      baseline("b1", [
        goldenCase("draft"),
        { case_id: "blank", node_id: "", phase_id: "p", expected_output_ref: "r" },
      ]),
    ])
    expect(byNode).toEqual({ draft: "has-golden" })
  })
})
