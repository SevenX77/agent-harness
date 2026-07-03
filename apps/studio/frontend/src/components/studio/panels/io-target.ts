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

/**
 * Which "node" the i/o panel is scoped to. The two boundary pseudo-nodes are
 * projections of GRAPH.md io, so they reuse the graph-level data but constrain
 * WHICH sections render (input region F3 归属规则, PM 2026-07-03):
 *  - `input-boundary`  → only the input section (graph io.inputs + files + test inputs)
 *  - `output-boundary` → only the output section (graph io.outputs + artifacts)
 *  - `phase`           → input section (consumed blackboard slice) + output section (produced fields)
 *  - `graph`           → both sections (nothing selected = GRAPH.md overview)
 */
export type IoNodeRole = 'graph' | 'input-boundary' | 'output-boundary' | 'phase'

/** Which boundary pseudo-node is selected on the canvas, if any. */
export type IoBoundarySelection = 'input' | 'output' | null

export interface IoPanelScope {
  role: IoNodeRole
  /** Render the input section (io.inputs config tree + file import). */
  showInput: boolean
  /** Render the output section (io.outputs preview). */
  showOutput: boolean
  /** Render the run-payload test-inputs list (graph-entry roles only). */
  showTestInputs: boolean
  /** Render the artifacts config (graph-output roles only). */
  showArtifacts: boolean
}

/**
 * Resolve the panel role from the canvas selection. A selected boundary
 * pseudo-node wins (it clears any phase selection on click); otherwise a
 * selected phase is `phase`; nothing selected is the graph overview.
 */
export function resolveIoNodeRole(
  selectedNode: SelectedNode,
  boundary: IoBoundarySelection,
): IoNodeRole {
  if (boundary === 'input') {
    return 'input-boundary'
  }
  if (boundary === 'output') {
    return 'output-boundary'
  }
  return selectedNode ? 'phase' : 'graph'
}

export function ioPanelScope(role: IoNodeRole): IoPanelScope {
  switch (role) {
    case 'input-boundary':
      // Graph entry: io.inputs config + run-payload test inputs; no output side.
      return { role, showInput: true, showOutput: false, showTestInputs: true, showArtifacts: false }
    case 'output-boundary':
      // Graph exit: io.outputs preview + artifacts config; no input side.
      return { role, showInput: false, showOutput: true, showTestInputs: false, showArtifacts: true }
    case 'phase':
      // Interior node: consumes a blackboard slice (input config) + produces
      // fields (output preview). Test inputs / artifacts are graph-level, not here.
      return { role, showInput: true, showOutput: true, showTestInputs: false, showArtifacts: false }
    default:
      // graph overview (nothing selected): everything.
      return { role, showInput: true, showOutput: true, showTestInputs: true, showArtifacts: true }
  }
}

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
