import type { Edge } from '@xyflow/react'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import type { SkillGraphNode } from './types'

export const INPUT_ID = '__global_input__'
export const OUTPUT_ID = '__global_output__'

function contextEdge(source: string, target: string): Edge<ContextEdgeData> {
  return {
    id: `${source}->${target}`,
    source,
    target,
    type: 'contextEdge',
    data: {
      hasTraceData: false,
      sourcePhaseId: source,
      targetPhaseId: target,
    },
    style: { strokeWidth: 1.5 },
  }
}

export function buildEdges(phaseNodes: SkillGraphNode[]): Edge<ContextEdgeData>[] {
  if (phaseNodes.length === 0) {
    return [contextEdge(INPUT_ID, OUTPUT_ID)]
  }

  const dependents = new Map<string, Set<string>>()
  for (const node of phaseNodes) {
    for (const dependency of node.data.dependsOn) {
      const targets = dependents.get(dependency) ?? new Set<string>()
      targets.add(node.id)
      dependents.set(dependency, targets)
    }
  }

  const edges: Edge<ContextEdgeData>[] = []
  for (const node of phaseNodes) {
    for (const source of node.data.dependsOn) {
      edges.push(contextEdge(source, node.id))
    }
    if (node.data.dependsOn.length === 0) {
      edges.push(contextEdge(INPUT_ID, node.id))
    }
    if (!dependents.has(node.id) || dependents.get(node.id)?.size === 0) {
      edges.push(contextEdge(node.id, OUTPUT_ID))
    }
  }
  return edges
}
