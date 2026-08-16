import type { CallbackEvent } from '../api/types'
import { eventPhase } from './trace'

// 选中即范围 (decision 2026-08-13 D6, overturning 2026-08-09 D2/#657): the
// canvas selection IS the trace's display scope. The filter is visibly
// anchored to the selection ring, announced by the panel's scope chip, and
// exits with one click (or a blank-canvas click) — the three objections that
// killed the previous invisible filter are answered, not dodged.

export type TraceScope =
  | { kind: 'node'; phase: string }
  | { kind: 'edge'; source: string; target: string }
  | { kind: 'input' }
  | { kind: 'output' }

/** The canvas ids of the boundary pseudo-nodes (buildEdges.ts mints them). */
const INPUT_NODE_IDS = new Set(['__global_input__', 'input'])
const OUTPUT_NODE_IDS = new Set(['__global_output__', 'output'])

/**
 * The edge-op family: what the engine records BETWEEN one phase's end and the
 * next one's start. Each such event now names its transition's upstream phases
 * outright (decision 2026-08-15 edge-as-run-segment), so matching an edge is a
 * lookup, not a reconstruction. `artifact_saved` still carries only
 * `phase_name` and is attributed to the edge whose upstream phase persisted it.
 */
const EDGE_OP_TYPES = new Set(['blackboard_reduce', 'input_dispatch', 'input_file_injected'])

/**
 * Which phases the event's transition came from. The engine names them from the
 * compiled topology, so this is the graph's answer, not an inference from
 * whichever phase happened to be current when the operation ran.
 */
function fromPhasesOf(event: CallbackEvent): string[] {
  return Array.isArray(event.from_phases) ? (event.from_phases as string[]) : []
}

function toPhaseOf(event: CallbackEvent): string | null {
  return typeof event.to_phase === 'string' && event.to_phase !== '' ? event.to_phase : null
}

function crossesInputBoundary(event: CallbackEvent): boolean {
  if (!EDGE_OP_TYPES.has(event.event_type)) return false
  // A transition with no upstream phases is one leaving the Input boundary:
  // the first phase of a graph has no predecessor to join.
  const from = fromPhasesOf(event)
  return from.length === 0 || from.some((phase) => INPUT_NODE_IDS.has(phase))
}

function matchesEdge(event: CallbackEvent, source: string, target: string): boolean {
  if (event.event_type === 'artifact_saved') {
    return event.phase_name === source
  }
  if (!EDGE_OP_TYPES.has(event.event_type)) return false
  const to = toPhaseOf(event)
  if (to !== target && !(OUTPUT_NODE_IDS.has(target) && to !== null && OUTPUT_NODE_IDS.has(to))) {
    return false
  }
  const from = fromPhasesOf(event)
  if (INPUT_NODE_IDS.has(source)) {
    return from.length === 0 || from.some((phase) => INPUT_NODE_IDS.has(phase))
  }
  return from.includes(source)
}

export function eventInScope(event: CallbackEvent, scope: TraceScope): boolean {
  switch (scope.kind) {
    case 'node':
      return eventPhase(event) === scope.phase
    case 'edge':
      return matchesEdge(event, scope.source, scope.target)
    case 'input':
      return crossesInputBoundary(event)
    case 'output': {
      const to = toPhaseOf(event)
      return to !== null && OUTPUT_NODE_IDS.has(to)
    }
  }
}

function boundaryAwareName(id: string): string {
  if (INPUT_NODE_IDS.has(id)) return 'Input'
  if (OUTPUT_NODE_IDS.has(id)) return 'Output'
  return id
}

/** What the scope chip says — the same names the canvas shows. */
export function scopeLabel(scope: TraceScope): string {
  switch (scope.kind) {
    case 'node':
      return scope.phase
    case 'edge':
      return `${boundaryAwareName(scope.source)} → ${boundaryAwareName(scope.target)}`
    case 'input':
      return 'Input'
    case 'output':
      return 'Output'
  }
}
