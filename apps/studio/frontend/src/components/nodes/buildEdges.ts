import type { Edge } from '@xyflow/react'
import type { CallbackEvent, EventEnvelope } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import { edgeContextFromEvents } from '@/lib/edge-context'
import type { SkillGraphNode } from './types'

export const INPUT_ID = '__global_input__'
export const OUTPUT_ID = '__global_output__'

type TraceEventInput = CallbackEvent | EventEnvelope

function contextEdge(source: string, target: string, traceEvents: TraceEventInput[]): Edge<ContextEdgeData> {
  // hasTraceData reflects whether the run actually dispatched data across this
  // edge — i.e. a matching `input_dispatch` event exists in the stream. Without
  // a run (empty events) every edge is inert, replacing the old `!isGlobal`
  // design-time heuristic.
  const hasTraceData = edgeContextFromEvents(traceEvents, source, target) !== null
  const isBoundaryEdge = source === INPUT_ID || source === OUTPUT_ID || target === INPUT_ID || target === OUTPUT_ID
  return {
    id: `${source}->${target}`,
    source,
    target,
    type: 'contextEdge',
    reconnectable: isBoundaryEdge ? false : undefined,
    deletable: isBoundaryEdge ? false : undefined,
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
  traceEvents: TraceEventInput[] = [],
): Edge<ContextEdgeData>[] {
  const edges: Edge<ContextEdgeData>[] = []
  for (const node of phaseNodes) {
    for (const source of node.data.dependsOn) {
      edges.push(contextEdge(source === 'input' ? INPUT_ID : source, node.id, traceEvents))
    }
    if (node.data.isOutput === true) {
      edges.push(contextEdge(node.id, OUTPUT_ID, traceEvents))
    }
  }
  return edges
}
