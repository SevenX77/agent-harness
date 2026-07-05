import type { Edge } from '@xyflow/react'
import type { CallbackEvent, EventEnvelope } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import { edgeContextFromEvents } from '@/lib/edge-context'
import {
  GLOBAL_INPUT_SOURCE_HANDLE_ID,
  GLOBAL_OUTPUT_TARGET_HANDLE_ID,
  SKILL_FLOW_SOURCE_HANDLE_ID,
  SKILL_FLOW_TARGET_HANDLE_ID,
} from './subgraph-bridge-handles'
import type { SkillGraphNode } from './types'

export const INPUT_ID = '__global_input__'
export const OUTPUT_ID = '__global_output__'

type TraceEventInput = CallbackEvent | EventEnvelope

export function createContextEdge(source: string, target: string, traceEvents: TraceEventInput[] = []): Edge<ContextEdgeData> {
  // hasTraceData reflects whether the run actually dispatched data across this
  // edge — i.e. a matching `input_dispatch` event exists in the stream. Without
  // a run (empty events) every edge is inert, replacing the old `!isGlobal`
  // design-time heuristic.
  const hasTraceData = edgeContextFromEvents(traceEvents, source, target) !== null
  return {
    id: `${source}->${target}`,
    source,
    target,
    sourceHandle: source === INPUT_ID ? GLOBAL_INPUT_SOURCE_HANDLE_ID : SKILL_FLOW_SOURCE_HANDLE_ID,
    targetHandle: target === OUTPUT_ID ? GLOBAL_OUTPUT_TARGET_HANDLE_ID : SKILL_FLOW_TARGET_HANDLE_ID,
    type: 'contextEdge',
    data: {
      hasTraceData,
      sourcePhaseId: source,
      targetPhaseId: target,
      showContextControl: true,
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
      edges.push(createContextEdge(source === 'input' ? INPUT_ID : source, node.id, traceEvents))
    }
    if (node.data.isOutput === true) {
      edges.push(createContextEdge(node.id, OUTPUT_ID, traceEvents))
    }
  }
  return edges
}
