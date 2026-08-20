import type { CallbackEvent } from '../api/types'

// ————————————————————————————————————————————————————————————————————————————
// edge-identity: the ONE answer to "does this event belong to the edge that
// runs source → target".
//
// It exists because two surfaces used to answer it independently and disagreed.
// The trace scope read an empty `from_phases` as the root transition; the
// canvas edge-dot required membership in that list, so the root edge never
// matched, `edgeContextFromEvents` returned null, and the dot fell back to the
// pre-run static guess — "Run the skill to see the real dispatched values" was
// still on screen after a green run (ledger T6 缺陷① / IO1). Two answers to one
// question is not redundancy, it is a coin flip about which one a given screen
// happens to call.
// ————————————————————————————————————————————————————————————————————————————

/**
 * The two pseudo-nodes the CANVAS mints to show where a run's data enters and
 * leaves the graph. Neither exists in the engine, the gateway or the studio
 * backend — grep either id there and you get nothing — so no runtime event can
 * ever name them. Anything a reader wants to know about them has to come from
 * the run's own report, not from an event addressed to them.
 */
export const GLOBAL_INPUT_NODE_ID = '__global_input__'
export const GLOBAL_OUTPUT_NODE_ID = '__global_output__'

/**
 * The canvas ids of the boundary pseudo-nodes. Both aliases are live: the
 * pseudo-node ids above, and a literal `input` / `output` phase that a skill
 * may declare and the engine then reports by that name.
 */
const INPUT_NODE_IDS: ReadonlySet<string> = new Set([GLOBAL_INPUT_NODE_ID, 'input'])
const OUTPUT_NODE_IDS: ReadonlySet<string> = new Set([GLOBAL_OUTPUT_NODE_ID, 'output'])

export function isInputBoundaryId(id: string): boolean {
  return INPUT_NODE_IDS.has(id)
}

export function isOutputBoundaryId(id: string): boolean {
  return OUTPUT_NODE_IDS.has(id)
}

/**
 * Everything the engine emits as part of one edge segment: the two brackets
 * plus the operations they enclose (decision 2026-08-15, edge-as-run-segment).
 *
 * The brackets belong here as much as their contents do — `edge_start` /
 * `edge_end` carry the segment's own summary (`changed_keys`,
 * `operation_count`, snapshot), so a reader who selects the edge and is shown
 * only its interior has been handed the parts and denied the whole.
 *
 * `artifact_saved` is deliberately absent: it names only a `phase_name`, so it
 * is matched separately, by the phase that persisted it.
 */
export const EDGE_SEGMENT_EVENT_TYPES: ReadonlySet<string> = new Set([
  'edge_start',
  'edge_end',
  'blackboard_reduce',
  'input_dispatch',
  'input_file_injected',
])

/**
 * Which phases this event's transition came from, as the compiled topology
 * names them — never an inference from whichever phase was current when the
 * operation ran.
 */
export function upstreamPhasesOf(event: CallbackEvent): string[] {
  return Array.isArray(event.from_phases) ? (event.from_phases as string[]) : []
}

export function downstreamPhaseOf(event: CallbackEvent): string | null {
  return typeof event.to_phase === 'string' && event.to_phase !== '' ? event.to_phase : null
}

/**
 * An empty upstream list means the run INPUT is upstream.
 *
 * `wrap_edge_transition` sets `from_phases = list(upstream_phases)` from the
 * compiled graph, and the first phase of a graph has no predecessor — so
 * "empty" is a statement about the topology, not a missing field. Treating it
 * as "unknown, therefore no match" is the single mistake this module removes.
 */
export function crossesInputBoundary(event: CallbackEvent): boolean {
  if (!EDGE_SEGMENT_EVENT_TYPES.has(event.event_type)) return false
  const upstream = upstreamPhasesOf(event)
  return upstream.length === 0 || upstream.some(isInputBoundaryId)
}

/** Does this event belong to the edge running `source` → `target`? */
export function eventCrossesEdge(event: CallbackEvent, source: string, target: string): boolean {
  if (event.event_type === 'artifact_saved') {
    return event.phase_name === source
  }
  if (!EDGE_SEGMENT_EVENT_TYPES.has(event.event_type)) return false

  const downstream = downstreamPhaseOf(event)
  const arrivesAtTarget = downstream === target
    || (isOutputBoundaryId(target) && downstream !== null && isOutputBoundaryId(downstream))
  if (!arrivesAtTarget) return false

  if (isInputBoundaryId(source)) return crossesInputBoundary(event)
  return upstreamPhasesOf(event).includes(source)
}
