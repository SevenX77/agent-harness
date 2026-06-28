import type { FieldSupplyEntry, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"

/**
 * The I/O panel edits one markdown file at a time:
 * no selected phase targets GRAPH.md, while a selected phase targets its own
 * SKILL.md / LOGIC.md / SUBGRAPH.md file.
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

/** The selected phase node shape threaded down from the canvas selection. */
export type SelectedNode = { id: string; data: SkillGraphNodeData } | null

function phaseKindFile(data: Pick<SkillGraphNodeData, "mode" | "subgraphPath">): "LOGIC.md" | "SKILL.md" | "SUBGRAPH.md" {
  if (data.subgraphPath || data.mode === "subgraph") {
    return "SUBGRAPH.md"
  }
  if (data.mode === "agent" || data.mode === "skill" || data.mode === "llm") {
    return "SKILL.md"
  }
  return "LOGIC.md"
}

export function resolveIoEditTarget(
  selectedNode: SelectedNode,
  skillDetail: SkillDetail | undefined,
): IoEditTarget {
  const files = skillDetail?.files
  if (!selectedNode) {
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

export function fieldSupplyByField(
  selectedNode: SelectedNode,
  skillDetail: SkillDetail | undefined,
): Map<string, FieldSupplyEntry> {
  if (!selectedNode) {
    return new Map()
  }
  const row = skillDetail?.graph_topology?.find((phase) => phase.id === selectedNode.id)
  const supply = row?.field_supply ?? []
  return new Map(supply.map((entry) => [entry.field, entry]))
}
