import type { CallbackEvent, EventEnvelope } from '@/api/types'
import type { EdgeContextJson } from '@/components/studio/WorkspaceContext'

// The graph canvas models the two ends of a run with synthetic global node ids.
// Mirror them here (rather than importing from buildEdges) to keep this selector
// free of a cycle with the nodes module that consumes it.
const INPUT_ID = '__global_input__'
const OUTPUT_ID = '__global_output__'

// The engine emits one InputDispatchEvent per transition with the flat dict it
// dispatched into the downstream phase. The engine reports the graph-entry
// transition with `from_phase` null or "input", so normalise the canvas's
// INPUT_ID boundary to the same logical source before matching.
const GRAPH_ENTRY_ALIASES = new Set([INPUT_ID, 'input'])

type TraceEventInput = CallbackEvent | EventEnvelope

function callbackPayload(event: TraceEventInput): CallbackEvent {
  const maybeEnvelope = event as EventEnvelope
  if (maybeEnvelope.schema_version === 'studio.event.v1' && maybeEnvelope.payload) {
    return maybeEnvelope.payload as CallbackEvent
  }
  return event as CallbackEvent
}

function isInputDispatch(event: CallbackEvent): boolean {
  return event.event_type === 'input_dispatch'
}

function isEdgeTransition(event: CallbackEvent): boolean {
  return event.event_type === 'edge_transition'
}

function phaseMatches(eventPhase: unknown, edgePhase: string): boolean {
  const normalisedEdge = typeof edgePhase === 'string' ? edgePhase : ''
  if (eventPhase === normalisedEdge) {
    return true
  }
  // Graph entry: the canvas uses INPUT_ID for the source while the engine emits
  // `from_phase` = null/"input". Treat them as the same boundary.
  if (GRAPH_ENTRY_ALIASES.has(normalisedEdge)) {
    return eventPhase == null || eventPhase === 'input' || eventPhase === INPUT_ID
  }
  return false
}

/**
 * Resolve the real transition data that flowed across one graph edge for the
 * selected run. Scans `events` for the LAST `input_dispatch` event whose
 * from/to phases match the edge (source -> target) and maps its flat
 * `blackboard_snapshot` into the shape the Properties panel renders.
 *
 * Returns `null` when no matching transition exists (caller shows an empty
 * state instead of falling back to mock data).
 */
export function edgeContextFromEvents(
  events: TraceEventInput[],
  fromPhase: string,
  toPhase: string,
): EdgeContextJson | null {
  // The OUTPUT_ID boundary is the graph exit; the engine does not dispatch into
  // it, so a `to_phase` aimed at OUTPUT_ID never has a matching event.
  if (toPhase === OUTPUT_ID) {
    return null
  }

  let match: CallbackEvent | null = null
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    if (!isInputDispatch(event) && !isEdgeTransition(event)) {
      continue
    }
    if (phaseMatches(event.from_phase, fromPhase) && phaseMatches(event.to_phase, toPhase)) {
      match = event
    }
  }

  if (!match) {
    return null
  }

  const after = (match.after ?? null) as Record<string, unknown> | null
  const diff = (match.diff ?? null) as Record<string, unknown> | null
  const snapshot = (after ?? match.blackboard_snapshot ?? {}) as Record<string, unknown>
  const changedKeys = Array.isArray(match.changed_keys)
    ? match.changed_keys
    : Array.isArray(diff?.changed_keys)
      ? diff.changed_keys
      : []

  // `blackboard_snapshot` is the flat dict dispatched INTO `toPhase`, so it maps
  // to the panel's Inputs subsection. A dispatch event carries no downstream
  // outputs, so `phase_outputs` stays empty. The raw snapshot is kept under
  // `blackboard_snapshot` for the full-frame view.
  return {
    inputs: snapshot,
    phase_outputs: {},
    from_phase: match.from_phase ?? null,
    to_phase: match.to_phase ?? toPhase,
    changed_keys: changedKeys,
    branch_index: match.branch_index ?? null,
    blackboard_snapshot: snapshot,
    edge_transition_id: match.edge_transition_id,
    run_id: match.run_id,
    execution_id: match.execution_id,
    attempt: match.attempt,
    checkpoint_id: match.checkpoint_id,
    checkpoint_ns: match.checkpoint_ns,
    before: match.before,
    after: match.after,
    diff: match.diff,
    tamper_diff: match.tamper_diff,
    resume_tamper_diff: match.resume_tamper_diff,
    tamper_audit: match.tamper_audit,
    resume_audit: match.resume_audit,
    resume_validity: match.resume_validity,
  }
}
