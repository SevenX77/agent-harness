import { describe, expect, it } from "vitest"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/nodes"
import { INPUT_ID, OUTPUT_ID } from "@/components/nodes"
import { resolveIoEditTarget, type SelectedNode } from "./io-target"

// Atom #28 (any-io-import-file): the per-node import affordance — drop a file in
// the i/o panel's "Infer input schema" box and Save — writes the imported
// io.inputs into the file resolved by resolveIoEditTarget. These tests pin the
// load-bearing wiring that makes the import reach ANY selected node's OWN phase
// file, not just GRAPH.md: if this resolver regressed to always returning
// GRAPH.md, importing on a mid-graph node would silently mutate the graph-level
// io instead of that node's io — exactly the #28 gap. So this is the
// producer→consumer contract for the affordance, exercised with real
// SkillDetail.files content (the same Record the backend ships and build-nodes
// reads), not a hand-injected field.

const PHASE_FILE = `---
io:
  inputs:
    type: object
    properties:
      seed:
        type: string
---
phase body
`

const GRAPH_FILE = `---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
---
<phase depends_on="input">enrich</phase>
`

function makeNode(id: string, data: Partial<SkillGraphNodeData>): SelectedNode {
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

const DETAIL = {
  files: {
    "GRAPH.md": GRAPH_FILE,
    "phases/enrich/LOGIC.md": PHASE_FILE,
  },
} as unknown as SkillDetail

describe("resolveIoEditTarget (atom #28 per-node import target)", () => {
  it("routes a selected mid-graph phase node's import to that node's own phase file", () => {
    const node = makeNode("enrich", { mode: "logic", filePath: "phases/enrich/LOGIC.md" })

    const target = resolveIoEditTarget(node, DETAIL)

    // The import (handleSave -> applyInputSchemaToGraph -> writeIoFile relPath)
    // lands in the PHASE file, not the graph-level contract.
    expect(target.relPath).toBe("phases/enrich/LOGIC.md")
    expect(target.content).toBe(PHASE_FILE)
    expect(target.isGraphLevel).toBe(false)
    expect(target.label).toBe("enrich")
  })

  it("derives the phase file from node kind when build-nodes did not supply filePath", () => {
    // No filePath on the node → resolver derives phases/<id>/<KIND>.md so the
    // import still reaches a per-node file rather than falling back to GRAPH.md.
    const node = makeNode("enrich", { mode: "logic" })

    const target = resolveIoEditTarget(node, DETAIL)

    expect(target.relPath).toBe("phases/enrich/LOGIC.md")
    expect(target.isGraphLevel).toBe(false)
  })

  it("keeps the global input/output nodes and the empty selection on graph-level io", () => {
    for (const selection of [
      null,
      makeNode(INPUT_ID, {}),
      makeNode(OUTPUT_ID, {}),
    ] satisfies SelectedNode[]) {
      const target = resolveIoEditTarget(selection, DETAIL)
      expect(target.relPath).toBe("GRAPH.md")
      expect(target.content).toBe(GRAPH_FILE)
      expect(target.isGraphLevel).toBe(true)
    }
  })
})
