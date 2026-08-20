import type { Edge } from '@xyflow/react'
import type { CallbackEvent, EventEnvelope } from '@/api/types'
import type { ContextEdgeData } from '@/components/edges/ContextEdge'
import { EDGE_STROKE_WIDTH } from '@/components/edges/edge-style'
import { edgeContextFromEvents } from '@/lib/edge-context'
import { GLOBAL_INPUT_NODE_ID, GLOBAL_OUTPUT_NODE_ID } from '@/utils/edge-identity'
import type { EdgeRunStatus } from '@/utils/edge-status-projection'
import {
  GLOBAL_INPUT_SOURCE_HANDLE_ID,
  GLOBAL_OUTPUT_TARGET_HANDLE_ID,
  SKILL_FLOW_SOURCE_HANDLE_ID,
  SKILL_FLOW_TARGET_HANDLE_ID,
} from './subgraph-bridge-handles'
import type { SkillGraphNode, SkillNodeStatus } from './types'

export const INPUT_ID = GLOBAL_INPUT_NODE_ID
export const OUTPUT_ID = GLOBAL_OUTPUT_NODE_ID

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

/**
 * What the segment INTO the Output boundary shows, given the phase that
 * produces it.
 *
 * That segment is the one edge on the board with no bracket of its own: the
 * engine emits a transition per real graph hop, and the endpoint is not a hop —
 * verified across the whole event stream of run `predict-2026-08-20T04-09-33`,
 * where every `edge_end` names a real downstream phase. So it reads the same
 * truth its endpoint does (`outputBoundaryStatus`): a phase marked `output`
 * finishing IS the graph delivering that output. Looking it up by edge id
 * instead left it permanently gray under a green Output endpoint — one board
 * telling the reader two different things about the same delivery.
 */
export function outputEdgeStatus(producerStatus: SkillNodeStatus | undefined): EdgeRunStatus {
  return EDGE_STATUS_FROM_NODE[producerStatus ?? 'idle']
}

const EDGE_STATUS_FROM_NODE: Readonly<Record<SkillNodeStatus, EdgeRunStatus>> = {
  idle: 'idle',
  running: 'running',
  success: 'done',
  error: 'failed',
  paused: 'paused',
  breakpoint: 'paused',
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
      const edge = createContextEdge(node.id, OUTPUT_ID, run)
      edges.push({ ...edge, data: { ...edge.data!, runStatus: outputEdgeStatus(node.data.status) } })
    }
  }
  return edges
}
