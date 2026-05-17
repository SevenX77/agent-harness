import type { Edge, Node } from 'reactflow'
import type { StudioNodeData } from '../CustomNodes'
import type { SerializeGraphPayload, SerializeGraphPhase, SerializeGraphResult, SkillDetail } from '../api/types'

export interface CanvasSaveApi {
  serializeGraph: (skillId: string, payload: SerializeGraphPayload) => Promise<SerializeGraphResult>
  updateSkillFiles: (skillId: string, files: Record<string, string>, expectedHash?: string | null) => Promise<SkillDetail>
}

export interface CanvasSaveResult {
  detail: SkillDetail
  markdown: string
  expectedHash: string
}

function modeForNode(node: Node<StudioNodeData>): SerializeGraphPhase['mode'] {
  if (node.type === 'subgraph' || node.data.mode === 'subgraph') {
    return 'subgraph'
  }
  return node.data.mode === 'logic' ? 'logic' : 'skill'
}

export function phasesFromCanvas(nodes: Node<StudioNodeData>[], edges: Edge[]): SerializeGraphPhase[] {
  const phaseIds = new Set(
    nodes
      .filter((node) => (node.type === 'agent' || node.type === 'subgraph') && !node.id.includes('::') && node.data.src)
      .map((node) => node.id),
  )
  const dependsOnByTarget = edges.reduce<Record<string, string[]>>((current, edge) => {
    if (!phaseIds.has(edge.target) || edge.source === 'input' || !phaseIds.has(edge.source)) {
      return current
    }
    current[edge.target] = [...(current[edge.target] ?? []), edge.source]
    return current
  }, {})

  return nodes
    .filter((node) => phaseIds.has(node.id) && node.data.src)
    .map((node) => ({
      id: node.id,
      src: String(node.data.src),
      depends_on: dependsOnByTarget[node.id] ?? [],
      mode: modeForNode(node),
    }))
}

export async function saveCanvasGraph(
  api: CanvasSaveApi,
  skillId: string,
  nodes: Node<StudioNodeData>[],
  edges: Edge[],
  files: Record<string, string>,
): Promise<CanvasSaveResult> {
  const serialized = await api.serializeGraph(skillId, {
    phases: phasesFromCanvas(nodes, edges),
  })
  const nextFiles = { ...files, 'GRAPH.md': serialized.markdown_content }
  const detail = await api.updateSkillFiles(skillId, nextFiles, serialized.current_hash)
  return {
    detail,
    markdown: serialized.markdown_content,
    expectedHash: serialized.current_hash,
  }
}
