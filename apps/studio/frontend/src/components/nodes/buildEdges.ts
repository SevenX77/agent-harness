import type { Edge } from '@xyflow/react'
import type { CallbackEvent, EventEnvelope } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import { EDGE_STROKE_WIDTH } from '@/components/edges/edge-style'
import { edgeContextFromEvents } from '@/lib/edge-context'
import type { EdgeRunStatus } from '@/utils/edge-status-projection'
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

/**
 * What the ACTIVE RUN, and the reader's selection, say about individual edges.
 *
 * One object rather than a growing tail of positional arguments, and for the
 * same reason `NodeRunProjection` is one: these are three views of the same
 * run, and supplying two of them while forgetting the third is how a board ends
 * up with an edge animating for a run it is not showing.
 */
export interface EdgeRunProjection {
  /** The viewed run's events — what the dot opens (dispatched values). */
  traceEvents?: TraceEventInput[]
  /** Per-edge segment state, keyed by `source->target` (deriveEdgeStatuses). */
  statusByEdgeId?: Record<string, EdgeRunStatus>
  /** The edge whose scope the trace is currently showing, if any. */
  selectedEdgeId?: string | null
}

export function createContextEdge(
  source: string,
  target: string,
  run: EdgeRunProjection = {},
): Edge<ContextEdgeData> {
  const id = `${source}->${target}`
  // Two different facts, kept apart on purpose. `runStatus` is whether the run
  // TRAVERSED this edge — an empty transition (operation_count 0) still opens
  // and closes, and "nothing happened between these two nodes" is an
  // observation, not a gap. `hasTraceData` is whether it DISPATCHED anything
  // here, which is what the dot can open.
  const hasTraceData = edgeContextFromEvents(run.traceEvents ?? [], source, target) !== null
  return {
    id,
    source,
    target,
    sourceHandle: source === INPUT_ID ? GLOBAL_INPUT_SOURCE_HANDLE_ID : SKILL_FLOW_SOURCE_HANDLE_ID,
    targetHandle: target === OUTPUT_ID ? GLOBAL_OUTPUT_TARGET_HANDLE_ID : SKILL_FLOW_TARGET_HANDLE_ID,
    type: 'contextEdge',
    data: {
      hasTraceData,
      runStatus: run.statusByEdgeId?.[id] ?? 'idle',
      isSelected: run.selectedEdgeId === id,
      sourcePhaseId: source,
      targetPhaseId: target,
      showContextControl: true,
    },
    style: { strokeWidth: EDGE_STROKE_WIDTH },
  }
}

export function buildEdges(
  phaseNodes: SkillGraphNode[],
  run: EdgeRunProjection = {},
): Edge<ContextEdgeData>[] {
  const edges: Edge<ContextEdgeData>[] = []
  for (const node of phaseNodes) {
    for (const source of node.data.dependsOn) {
      edges.push(createContextEdge(source === 'input' ? INPUT_ID : source, node.id, run))
    }
    if (node.data.isOutput === true) {
      edges.push(createContextEdge(node.id, OUTPUT_ID, run))
    }
  }
  return edges
}
