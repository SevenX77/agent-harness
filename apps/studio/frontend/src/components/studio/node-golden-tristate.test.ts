import { describe, expect, it } from "vitest"
import type { GoldenBaseline, GoldenBaselineCase, GraphTopologyItem } from "@/api/types"
import {
  goldenTriStateByNode,
  ranAgentNodesFromPredict,
  templatableAgentNodeIds,
} from "./node-golden"

function goldenCase(nodeId: string): GoldenBaselineCase {
  return {
    case_id: `${nodeId}-case`,
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
    created_at: "2026-06-18T00:00:00Z",
    locked: false,
    content_path: `golden/${id}/baseline.json`,
    cases,
  }
}

describe("goldenTriStateByNode", () => {
  it("marks has-golden nodes 🟢 from baseline cases", () => {
    const byNode = goldenTriStateByNode([baseline("b1", [goldenCase("draft")])], new Set())
    expect(byNode.draft).toBe("has-golden")
  })

  it("marks ran agent nodes without golden as 🟡 logic-ok", () => {
    const byNode = goldenTriStateByNode([], new Set(["draft", "expand"]))
    expect(byNode.draft).toBe("logic-ok")
    expect(byNode.expand).toBe("logic-ok")
  })

  it("gives 🟢 has-golden precedence over 🟡 logic-ok for the same node", () => {
    const byNode = goldenTriStateByNode(
      [baseline("b1", [goldenCase("draft")])],
      new Set(["draft", "expand"]),
    )
    expect(byNode.draft).toBe("has-golden")
    expect(byNode.expand).toBe("logic-ok")
  })

  it("emits nothing (🔘 untested) for nodes neither golden nor ran", () => {
    const byNode = goldenTriStateByNode([], new Set())
    expect(byNode).toEqual({})
    expect(byNode.never).toBeUndefined()
  })

  it("clears 🟡 when the ran-agent-node set is emptied (session clear)", () => {
    const ran = goldenTriStateByNode([], new Set(["draft"]))
    expect(ran.draft).toBe("logic-ok")
    const cleared = goldenTriStateByNode([], new Set())
    expect(cleared.draft).toBeUndefined()
  })
})

describe("ranAgentNodesFromPredict (agent-only filter from phases presence)", () => {
  it("keeps only llm phases (agent nodes) present in phases, drops logic nodes", () => {
    const ran = ranAgentNodesFromPredict({
      is_predict: true,
      status: "success",
      path_diff: null,
      phases: [
        { phase_name: "setup", type: "logic", inputs: {}, outputs: {}, mocked_source: null },
        { phase_name: "draft", type: "llm", inputs: {}, outputs: {}, mocked_source: "heuristic_stub" },
        { phase_name: "expand", type: "llm", inputs: {}, outputs: {}, mocked_source: "manual" },
      ],
    })
    expect(ran).toEqual(new Set(["draft", "expand"]))
    expect(ran.has("setup")).toBe(false)
  })

  it("returns an empty set for null / phases-less payloads", () => {
    expect(ranAgentNodesFromPredict(null)).toEqual(new Set())
    expect(
      ranAgentNodesFromPredict({ is_predict: true, status: "success", path_diff: null, phases: [] }),
    ).toEqual(new Set())
  })
})

function topo(id: string, mode: string): GraphTopologyItem {
  return { id, src: `phases/${id}`, depends_on: [], mode }
}

describe("templatableAgentNodeIds (manual-template gating #33)", () => {
  const topology: GraphTopologyItem[] = [
    topo("setup", "logic"),
    topo("draft", "agent"),
    topo("expand", "agent"),
    topo("sub", "subgraph"),
  ]

  it("returns only agent nodes that lack golden (excludes logic/subgraph and 🟢)", () => {
    const ids = templatableAgentNodeIds(topology, [baseline("b1", [goldenCase("draft")])])
    // draft has golden -> excluded; setup/sub are not agent -> excluded; expand stays.
    expect(ids).toEqual(["expand"])
  })

  it("returns all agent nodes when no golden exists yet", () => {
    expect(templatableAgentNodeIds(topology, [])).toEqual(["draft", "expand"])
  })

  it("returns nothing for null/empty topology", () => {
    expect(templatableAgentNodeIds(null, [])).toEqual([])
    expect(templatableAgentNodeIds([], [])).toEqual([])
  })
})
