import type { CallbackEvent } from '../api/types'
import type { IndexedTraceEvent } from '../hooks/useTraceFilter'
import { traceEventId } from '../hooks/useTraceSelection'
import type { RunVerdict } from './run-status-projection'
import { eventPhase, eventSeverity, routeDecisionDetails } from './trace'

/**
 * `severed` is a step whose closing half can never arrive: the run reached a
 * verdict while the step was still open (decision 2026-08-13 D7 铁律 — a run
 * at a terminal state leaves nothing running). It is not `done`: the reader
 * should see "this never finished", not a summary that looks complete.
 */
export type TraceStepStatus = 'running' | 'done' | 'severed'

/**
 * Which kind of run segment a step belongs to.
 *
 * A run is a sequence of segments, and an edge is one of them: the stretch
 * between one node's execution ending and the next one's starting (user ruling
 * 2026-08-15: 「tracing要把edge和node作为平级的运行分段，流中的一个节点」).
 * Peer, not nested — an edge segment is not a decoration on the node that
 * follows it.
 */
export type TraceSegmentKind = 'phase' | 'edge'

export interface TraceSegment {
  kind: TraceSegmentKind
  /**
   * The engine's identity for this segment — `phase_execution_id` for a node,
   * `edge_transition_id` for an edge. Grouping keys off THIS, not off the
   * phase name: one phase run three times by an outer loop is three segments,
   * and a name cannot tell them apart.
   */
  id: string
}

export interface TraceStep {
  /** Stable across the step's whole life: it is minted from the opening event. */
  key: string
  phase: string
  /**
   * Which run segment this step happened inside. Null for events that belong
   * to no segment — run-level frames, and anything emitted before the first
   * transition opened.
   */
  segment: TraceSegment | null
  /**
   * The engine's own identity for this step, when it has one. Distinct from
   * `key`, which is a position in THIS list: `stepId` is what the run itself
   * calls the step, so it is what live-output frames name.
   */
  stepId: string | null
  status: TraceStepStatus
  /** The event that opened the step — the row's identity and scroll anchor. */
  start: IndexedTraceEvent
  /** The event that closed it. Null while running, and null for a lone event. */
  end: IndexedTraceEvent | null
  /**
   * Which agent-loop turn the step belongs to (decision 2026-08-13 D1), from
   * the phase's `agent_loop_iteration` markers or the opening event's own
   * `loop_index`. Null in phases that never emit either — those stay flat.
   */
  iteration: number | null
  /**
   * Gateway verdicts (`llm_route_decision` / `llm_call_settings`) that arrived
   * while this was the ONLY open LLM step of its phase. They are the step's
   * final sub-entries (decision 2026-08-13 D1: … → 设置/路由判定); when the
   * attribution would be a guess — two open steps, or none — the verdict stays
   * its own row instead, because a wrong nesting is worse than a flat list.
   */
  verdicts: TraceVerdict[]
}

/** A gateway verdict, plus how many times this exact one has been seen. */
export interface TraceVerdict extends IndexedTraceEvent {
  /**
   * 1 the first time a degradation appears in the run, N for the Nth repeat.
   *
   * The gateway re-probes a dead endpoint on every call, so one outage is
   * reported once per LLM step — measured on run
   * `2026-08-19T06-58-15_179d1440`, where a single timed-out endpoint produced
   * a full "Probe failed" block on three consecutive steps. The repeats are
   * real events and stay in the record; what folds is the EXPLANATION, so the
   * reader reads the reason once and afterwards only learns that this call fell
   * back too. Same idea as syslog's "last message repeated N times".
   *
   * Always 1 for a healthy decision: which endpoint served THIS call is a
   * per-call fact, not a repeated complaint.
   */
  occurrence: number
}

/**
 * What makes two degradations "the same complaint" — the outcome, where it
 * happened, and why. A different outcome on the same endpoint (a probe failure
 * becoming an open circuit) is a new fact and explains itself again.
 */
function degradationIdentity(event: CallbackEvent): string | null {
  if (eventSeverity(event) === 'normal') return null
  const details = routeDecisionDetails(event)
  if (!details) return null
  return [
    details.decision,
    details.routeId ?? '',
    details.endpointId ?? '',
    details.reason,
    details.statusCode ?? '',
  ].join('|')
}

/**
 * Group a run's events into the steps a reader actually watches happen.
 *
 * An LLM call is one act with two events around it: the engine captures the
 * prompt on the way in (`prompt_captured`) and reports the result on the way
 * out (`llm_call`). Rendering those as two rows meant the panel said nothing
 * at all while the call was in flight — the slowest part of a run — and then
 * printed a finished summary. As one step it opens the moment the prompt
 * exists, shows what was asked, and settles into a summary when the answer
 * arrives (decision 2026-08-09 D4).
 *
 * Both kinds pair on an id the engine puts on both halves: `tool_call_id` for
 * a tool call (PR #655), `step_id` for an LLM call. An agent turn can have
 * several of either in flight, so neither position nor the phase can say which
 * return belongs to which start — pairing LLM calls by phase, as this did
 * before the engine minted step ids, put the first answer on whichever prompt
 * happened to still be open.
 *
 * `agent_loop_iteration` events do not become rows: they are the layer markers
 * the rows are grouped under (decision 2026-08-13 D1), so the marker's whole
 * rendering IS the iteration divider.
 *
 * Everything else is one step, unchanged. So is a completion whose opening half
 * is not in this list: a filter can hide it, and the answer to that is to show
 * the half you have, not to drop it.
 */
export function buildTraceSteps(
  events: IndexedTraceEvent[],
  verdict: RunVerdict = 'running',
): TraceStep[] {
  const steps: TraceStep[] = []
  const openLlmByStepId = new Map<string, TraceStep>()
  const openToolByCallId = new Map<string, TraceStep>()
  const openEdgeByTransitionId = new Map<string, TraceStep>()
  const iterationByPhase = new Map<string, number>()
  // The segment a phase's events belong to, learned from its `phase_start`.
  // Keyed by phase name because that is what the events inside a phase carry;
  // a later execution of the same phase overwrites it, which is correct — its
  // events come after.
  const phaseSegmentByPhase = new Map<string, TraceSegment>()
  // How many times each distinct degradation has been reported so far.
  const degradationCounts = new Map<string, number>()

  for (const entry of events) {
    const { event } = entry
    const phase = eventPhase(event)
    const callId = toolCallId(event)
    const stepId = traceStepId(event)
    const transitionId = edgeTransitionId(event)

    if (event.event_type === 'phase_start') {
      const executionId = phaseExecutionId(event)
      if (executionId !== null) {
        phaseSegmentByPhase.set(phase, { kind: 'phase', id: executionId })
        // A phase execution is its own iteration scope: the turn counter of a
        // previous execution of the same phase is not this one's.
        iterationByPhase.delete(phase)
      }
    }

    if (event.event_type === 'agent_loop_iteration') {
      const iteration = numericIteration(event.iteration)
      if (iteration !== null) {
        iterationByPhase.set(phase, iteration)
      }
      continue
    }

    if (event.event_type === 'edge_end' && transitionId !== null) {
      const open = openEdgeByTransitionId.get(transitionId)
      if (open) {
        open.end = entry
        open.status = 'done'
        openEdgeByTransitionId.delete(transitionId)
        continue
      }
    }

    if (isGatewayVerdict(event)) {
      const host = onlyOpenLlmStepOfPhase(openLlmByStepId, phase)
      if (host) {
        const identity = degradationIdentity(event)
        const occurrence = identity === null
          ? 1
          : (degradationCounts.get(identity) ?? 0) + 1
        if (identity !== null) degradationCounts.set(identity, occurrence)
        host.verdicts.push({ ...entry, occurrence })
        continue
      }
    }

    if (event.event_type === 'llm_call' && stepId !== null) {
      const open = openLlmByStepId.get(stepId)
      if (open) {
        open.end = entry
        open.status = 'done'
        openLlmByStepId.delete(stepId)
        continue
      }
    }

    if (event.event_type === 'tool_call' && callId !== null) {
      const open = openToolByCallId.get(callId)
      if (open) {
        open.end = entry
        open.status = 'done'
        openToolByCallId.delete(callId)
        continue
      }
    }

    const opensAStep = (event.event_type === 'prompt_captured' && stepId !== null)
      || (event.event_type === 'tool_call_started' && callId !== null)
      || (event.event_type === 'edge_start' && transitionId !== null)
    const step: TraceStep = {
      key: traceEventId(event, entry.index),
      phase,
      segment: segmentOf(event, transitionId, phaseSegmentByPhase.get(phase) ?? null),
      stepId,
      status: opensAStep ? 'running' : 'done',
      start: entry,
      end: null,
      // The ONLY source of the turn layer is `agent_loop_iteration`, carried
      // forward to the events that followed it. `prompt_captured.loop_index`
      // looks like the same number and is not: it counts LLM CALLS, and one
      // turn can spend several (engine fixture: three calls over two turns).
      iteration: iterationByPhase.get(phase) ?? null,
      verdicts: [],
    }
    steps.push(step)

    if (event.event_type === 'prompt_captured' && stepId !== null) {
      openLlmByStepId.set(stepId, step)
    } else if (event.event_type === 'tool_call_started' && callId !== null) {
      openToolByCallId.set(callId, step)
    } else if (event.event_type === 'edge_start' && transitionId !== null) {
      openEdgeByTransitionId.set(transitionId, step)
    }
  }

  // D7 铁律: a run at a terminal verdict leaves nothing running. A paused run
  // is the one non-terminal stop — its steps are suspended, not dead, and the
  // resume's closing half will still pair up.
  if (verdict !== 'running' && verdict !== 'paused') {
    for (const open of [
      ...openLlmByStepId.values(),
      ...openToolByCallId.values(),
      ...openEdgeByTransitionId.values(),
    ]) {
      open.status = 'severed'
    }
  }

  return steps
}

/**
 * The engine's identity for the call a frame belongs to.
 *
 * It is also what the live-output frames carry, which is how a piece of text
 * arriving on the other socket finds its row.
 */
export function traceStepId(event: CallbackEvent): string | null {
  const value = event.step_id
  return typeof value === 'string' && value !== '' ? value : null
}

/**
 * The segment an event happened in.
 *
 * An event that names a transition belongs to that edge segment — including
 * the edge operations, which is the whole point: they used to be read as
 * belonging to the phase that followed them. Everything else belongs to the
 * phase segment its `phase_start` opened.
 */
function segmentOf(
  event: CallbackEvent,
  transitionId: string | null,
  phaseSegment: TraceSegment | null,
): TraceSegment | null {
  if (transitionId !== null) {
    return { kind: 'edge', id: transitionId }
  }
  const executionId = phaseExecutionId(event)
  if (executionId !== null) {
    return { kind: 'phase', id: executionId }
  }
  return phaseSegment
}

function edgeTransitionId(event: CallbackEvent): string | null {
  const value = event.edge_transition_id
  return typeof value === 'string' && value !== '' ? value : null
}

function phaseExecutionId(event: CallbackEvent): string | null {
  const value = event.phase_execution_id
  return typeof value === 'string' && value !== '' ? value : null
}

function toolCallId(event: CallbackEvent): string | null {
  const value = event.tool_call_id
  return typeof value === 'string' && value.length > 0 ? value : null
}

function numericIteration(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 1 ? value : null
}

/** The gateway's per-call verdicts; they carry no step_id, only a phase. */
function isGatewayVerdict(event: CallbackEvent): boolean {
  return event.event_type === 'llm_route_decision' || event.event_type === 'llm_call_settings'
}

function onlyOpenLlmStepOfPhase(
  open: Map<string, TraceStep>,
  phase: string,
): TraceStep | null {
  let found: TraceStep | null = null
  for (const step of open.values()) {
    if (step.phase !== phase) {
      continue
    }
    if (found) {
      return null
    }
    found = step
  }
  return found
}
