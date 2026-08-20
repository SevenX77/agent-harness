import type { CallbackEvent, EventEnvelope } from '@/api/types'
import type { EdgeContextJson } from '@/components/studio/WorkspaceContext'
import { eventCrossesEdge, GLOBAL_OUTPUT_NODE_ID } from '@/utils/edge-identity'

type TraceEventInput = CallbackEvent | EventEnvelope

function callbackPayload(event: TraceEventInput): CallbackEvent {
  const maybeEnvelope = event as EventEnvelope
  if (maybeEnvelope.schema_version === 'studio.event.v1' && maybeEnvelope.payload) {
    return maybeEnvelope.payload as CallbackEvent
  }
  return event as CallbackEvent
}

function plainObject(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/**
 * What the run handed out at the canvas Output boundary.
 *
 * That boundary is a canvas pseudo-node — no engine transition runs into it and
 * no event names it — so the only producer of "what did this run give back" is
 * the run itself, reporting once at `run_ended`. Reading that report is why the
 * dot can show real values here; making the engine emit a second event carrying
 * the same values would be one fact with two publishers, the defect this
 * module's own header describes (ledger E14).
 *
 * The slice shown is the OUTPUT PHASE's outputs, not the whole final blackboard:
 * every other dot shows what was dispatched INTO its downstream node, and what
 * goes into the output boundary is exactly the phase outputs the root
 * `io.outputs` declares.
 */
function runOutputContext(
  events: TraceEventInput[],
  fromPhase: string,
  toPhase: string,
): EdgeContextJson | null {
  let produced: Record<string, unknown> | null = null
  let runId: unknown
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    if (event.event_type !== 'run_ended') {
      continue
    }
    const phaseOutputs = plainObject(plainObject(event.final_context)?.phase_outputs)
    const slice = plainObject(phaseOutputs?.[fromPhase])
    if (slice) {
      produced = slice
      runId = event.run_id
    }
  }

  // Nothing produced by this phase — mid-run, or a run that ended before
  // reaching it. The caller falls back to the static inference, which is honest
  // about being a pre-run expectation.
  if (!produced) {
    return null
  }

  return {
    inputs: produced,
    from_phase: fromPhase,
    to_phase: toPhase,
    changed_keys: Object.keys(produced),
    branch_index: null,
    blackboard_snapshot: produced,
    run_id: runId,
  }
}

/**
 * Resolve the real transition data that flowed across one graph edge for the
 * selected run. Scans `events` for the LAST `input_dispatch` belonging to the
 * edge (source -> target) and maps its flat `blackboard_snapshot` into the
 * shape the Properties panel renders.
 *
 * Whether an event belongs to the edge is `edge-identity`'s answer, shared with
 * the trace scope — including the root edge, whose transition reports an empty
 * upstream list because the run input, not a phase, is what precedes it.
 *
 * Returns `null` when no matching transition exists (caller shows an empty
 * state instead of falling back to mock data).
 */
export function edgeContextFromEvents(
  events: TraceEventInput[],
  fromPhase: string,
  toPhase: string,
): EdgeContextJson | null {
  // Branch on the topology, not on "did the scan find anything": a skill may
  // declare a literal phase named `output`, and the edge INTO that phase is an
  // ordinary transition with ordinary dispatch events. Only the canvas
  // pseudo-node has no events of its own.
  if (toPhase === GLOBAL_OUTPUT_NODE_ID) {
    return runOutputContext(events, fromPhase, toPhase)
  }

  let match: CallbackEvent | null = null
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    if (event.event_type !== 'input_dispatch') {
      continue
    }
    if (eventCrossesEdge(event, fromPhase, toPhase)) {
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
