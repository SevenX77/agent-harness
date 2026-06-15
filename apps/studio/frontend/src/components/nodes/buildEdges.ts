import type { Edge } from '@xyflow/react'
import type { CallbackEvent } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import { edgeContextFromEvents } from '@/lib/edge-context'
import type { SkillGraphNode } from './types'

export const INPUT_ID = '__global_input__'
export const OUTPUT_ID = '__global_output__'

function contextEdge(source: string, target: string, traceEvents: CallbackEvent[]): Edge<ContextEdgeData> {
  // hasTraceData reflects whether the run actually dispatched data across this
  // edge — i.e. a matching `input_dispatch` event exists in the stream. Without
  // a run (empty events) every edge is inert, replacing the old `!isGlobal`
  // design-time heuristic.
  const hasTraceData = edgeContextFromEvents(traceEvents, source, target) !== null
  return {
    id: `${source}->${target}`,
    source,
    target,
    type: 'contextEdge',
    data: {
      hasTraceData,
      sourcePhaseId: source,
      targetPhaseId: target,
    },
    style: { strokeWidth: 1.5 },
  }
}

export function buildEdges(
  phaseNodes: SkillGraphNode[],
  traceEvents: CallbackEvent[] = [],
): Edge<ContextEdgeData>[] {
  if (phaseNodes.length === 0) {
    return [contextEdge(INPUT_ID, OUTPUT_ID, traceEvents)]
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
      edges.push(contextEdge(source, node.id, traceEvents))
    }
    if (node.data.dependsOn.length === 0) {
      edges.push(contextEdge(INPUT_ID, node.id, traceEvents))
    }
    if (!dependents.has(node.id) || dependents.get(node.id)?.size === 0) {
      edges.push(contextEdge(node.id, OUTPUT_ID, traceEvents))
    }
  }
  return edges
}
