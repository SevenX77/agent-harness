import type { CallbackEvent, EventEnvelope } from '@/api/types'
import type { EdgeContextJson, EdgeOperation } from '@/components/studio/WorkspaceContext'

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

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

/**
 * Map one micro-op callback event into the rendered operation-log entry, or
 * `null` when the event is not one of the four node-to-node operation types.
 * The engine already emits each of these on the run stream (see
 * graph_agent/callbacks/events.py); this only reshapes them for the dot view.
 */
function operationFromEvent(event: CallbackEvent): EdgeOperation | null {
  switch (event.event_type) {
    case 'blackboard_reduce':
      return {
        kind: 'reduce',
        reducer: typeof event.reducer === 'string' ? event.reducer : 'unknown',
        changed_keys: stringArray(event.changed_keys),
      }
    case 'input_dispatch':
      return {
        kind: 'dispatch',
        dispatched_keys: stringArray(event.dispatched_keys),
        changed_keys: stringArray(event.changed_keys),
      }
    case 'input_file_injected':
      return {
        kind: 'inject',
        file_ref: typeof event.file_ref === 'string' ? event.file_ref : '',
        target_field: typeof event.target_field === 'string' ? event.target_field : '',
      }
    default:
      return null
  }
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
 * Collect, in stream order, the node-to-node operation log for one edge: the
 * reduce / dispatch / file-inject / artifact-persist micro operations the
 * engine recorded between the upstream phase end and the downstream phase
 * start. reduce/dispatch/inject events are matched by their from/to phases;
 * `artifact_saved` carries only `phase_name`, so it is attributed to the edge
 * whose UPSTREAM phase persisted it (the source phase's end-of-phase output).
 */
function collectEdgeOperations(
  events: TraceEventInput[],
  fromPhase: string,
  toPhase: string,
): EdgeOperation[] {
  const operations: EdgeOperation[] = []
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    if (event.event_type === 'artifact_saved') {
      if (phaseMatches(event.phase_name, fromPhase)) {
        operations.push({
          kind: 'persist',
          name: typeof event.name === 'string' ? event.name : '',
          path: typeof event.path === 'string' ? event.path : '',
          size_bytes: typeof event.size_bytes === 'number' ? event.size_bytes : null,
        })
      }
      continue
    }
    const operation = operationFromEvent(event)
    if (!operation) {
      continue
    }
    if (phaseMatches(event.from_phase, fromPhase) && phaseMatches(event.to_phase, toPhase)) {
      operations.push(operation)
    }
  }
  return operations
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

  // The ordered node-to-node operation log (reduce / dispatch / inject /
  // persist) the engine recorded for this transition window. Empty array when
  // the run only carried the dispatch snapshot.
  const operations = collectEdgeOperations(events, fromPhase, toPhase)

  // `blackboard_snapshot` is the flat dict dispatched INTO `toPhase`, so it maps
  // to the panel's Inputs subsection. A dispatch event carries no downstream
  // outputs, so `phase_outputs` stays empty. The raw snapshot is kept under
  // `blackboard_snapshot` for the full-frame view.
  return {
    inputs: snapshot,
    phase_outputs: {},
    operations,
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
