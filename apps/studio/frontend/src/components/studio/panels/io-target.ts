import type { FieldSupplyEntry, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { INPUT_ID, OUTPUT_ID } from "@/components/nodes"

/**
 * Atom #27 (per-node i/o): the i/o panel edits io.inputs/io.outputs of ONE
 * authoritative markdown-with-frontmatter file. Which file depends on the
 * selected node:
 *
 *  - no node selected, or the global input/output node (`__global_input__` /
 *    `__global_output__`) → the GRAPH-level io lives in `GRAPH.md` frontmatter.
 *  - a phase node selected → that phase's io lives in its own phase file's
 *    frontmatter (`phases/<id>/SKILL.md | LOGIC.md | SUBGRAPH.md`), the same
 *    shape the engine validates per phase.
 *
 * The schema-infer field writebacks (add/rename/remove/setType/applyInput/
 * applyArtifactPath) are file-agnostic — they parse `io.<side>` from whatever
 * frontmatter they receive — so per-node editing is a target-selection concern,
 * not a writeback-logic change. This resolver names the relative path + supplies
 * its current content so the panel reads the right io and writes back the right
 * file.
 */
export interface IoEditTarget {
  /** Relative path under the skill root, e.g. "GRAPH.md" or "phases/foo/SKILL.md". */
  relPath: string
  /** Current file content (frontmatter source), or undefined if not loaded. */
  content: string | undefined
  /** Human label for the panel header, e.g. "Graph" or the phase id. */
  label: string
  /** True when this target is the graph-level io (GRAPH.md), false for a phase. */
  isGraphLevel: boolean
}

/** The selected node shape threaded down from the canvas selection. */
export type SelectedNode = { id: string; data: SkillGraphNodeData } | null

function isGlobalIoNode(node: NonNullable<SelectedNode>): boolean {
  return node.id === INPUT_ID || node.id === OUTPUT_ID
}

// Node KIND is owned by the physical phase file on disk; mirror the same
// projection the canvas (build-nodes) and PropertiesPanel use so the i/o panel
// resolves a phase's file the same way. Prefer the `filePath` build-nodes
// already computed for the node; fall back to deriving it from the node kind.
function phaseKindFile(data: Pick<SkillGraphNodeData, "mode" | "subgraphPath">): "LOGIC.md" | "SKILL.md" | "SUBGRAPH.md" {
  if (data.subgraphPath || data.mode === "subgraph") {
    return "SUBGRAPH.md"
  }
  if (data.mode === "agent" || data.mode === "skill" || data.mode === "llm") {
    return "SKILL.md"
  }
  return "LOGIC.md"
}

/**
 * Resolve which file the i/o panel should read/write for the current selection.
 * Falls back to GRAPH.md for no selection or the global input/output nodes; for
 * a real phase node, resolves its phase file (preferring the `filePath`
 * build-nodes already computed, else deriving it from the node kind).
 */
export function resolveIoEditTarget(
  selectedNode: SelectedNode,
  skillDetail: SkillDetail | undefined,
): IoEditTarget {
  const files = skillDetail?.files
  if (!selectedNode || isGlobalIoNode(selectedNode)) {
    return {
      relPath: "GRAPH.md",
      content: files?.["GRAPH.md"],
      label: "Graph",
      isGraphLevel: true,
    }
  }
  const relPath = selectedNode.data.filePath ?? `phases/${selectedNode.id}/${phaseKindFile(selectedNode.data)}`
  return {
    relPath,
    content: files?.[relPath],
    label: selectedNode.data.label || selectedNode.id,
    isGraphLevel: false,
  }
}

/**
 * n2-canvas#10 (data-gap-viz): resolve the per-input-field supply/demand
 * projection for the i/o panel to render data-gap markers + producers.
 *
 * The selected node's `id` is the phase name, which is the join key into the
 * backend's `graph_topology[].field_supply` (each row keyed by phase id, see
 * services/skills.py `_topology_row`). This returns that REAL backend array so
 * the panel can mark `supplied=false` input fields as data gaps and name the
 * `producer_phase` of supplied ones — no second source of truth on the client.
 *
 * Graph-level io (no node / global input/output node) has no upstream producers
 * to chart, so this returns an empty map there: the data-gap view is per-node.
 */
export function fieldSupplyByField(
  selectedNode: SelectedNode,
  skillDetail: SkillDetail | undefined,
): Map<string, FieldSupplyEntry> {
  if (!selectedNode || isGlobalIoNode(selectedNode)) {
    return new Map()
  }
  const row = skillDetail?.graph_topology?.find((phase) => phase.id === selectedNode.id)
  const supply = row?.field_supply ?? []
  return new Map(supply.map((entry) => [entry.field, entry]))
}
