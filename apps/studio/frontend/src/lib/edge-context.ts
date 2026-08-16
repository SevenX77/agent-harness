import type { CallbackEvent, EventEnvelope } from '@/api/types'
import type { EdgeContextJson } from '@/components/studio/WorkspaceContext'

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

function phaseMatches(eventPhase: unknown, edgePhase: string): boolean {
  return eventPhase === edgePhase
}

/**
 * An edge operation names the phases its transition joins as a LIST: a fan-in
 * transition genuinely has several upstreams, so asking "did this come from
 * that phase" is a membership question, not an equality one.
 */
function upstreamIncludes(event: CallbackEvent, fromPhase: string): boolean {
  const from = event.from_phases
  return Array.isArray(from) && from.includes(fromPhase)
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
  let match: CallbackEvent | null = null
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    if (!isInputDispatch(event)) {
      continue
    }
    if (upstreamIncludes(event, fromPhase) && phaseMatches(event.to_phase, toPhase)) {
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
    from_phase: fromPhase,
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
