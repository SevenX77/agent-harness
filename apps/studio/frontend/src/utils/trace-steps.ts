import type { CallbackEvent } from '../api/types'
import type { IndexedTraceEvent } from '../hooks/useTraceFilter'
import { traceEventId } from '../hooks/useTraceSelection'
import { eventPhase } from './trace'

export type TraceStepStatus = 'running' | 'done'

export interface TraceStep {
  /** Stable across the step's whole life: it is minted from the opening event. */
  key: string
  phase: string
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
  verdicts: IndexedTraceEvent[]
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
export function buildTraceSteps(events: IndexedTraceEvent[]): TraceStep[] {
  const steps: TraceStep[] = []
  const openLlmByStepId = new Map<string, TraceStep>()
  const openToolByCallId = new Map<string, TraceStep>()
  const iterationByPhase = new Map<string, number>()

  for (const entry of events) {
    const { event } = entry
    const phase = eventPhase(event)
    const callId = toolCallId(event)
    const stepId = traceStepId(event)

    if (event.event_type === 'agent_loop_iteration') {
      const iteration = numericIteration(event.iteration)
      if (iteration !== null) {
        iterationByPhase.set(phase, iteration)
      }
      continue
    }

    if (isGatewayVerdict(event)) {
      const host = onlyOpenLlmStepOfPhase(openLlmByStepId, phase)
      if (host) {
        host.verdicts.push(entry)
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
    const step: TraceStep = {
      key: traceEventId(event, entry.index),
      phase,
      stepId,
      status: opensAStep ? 'running' : 'done',
      start: entry,
      end: null,
      iteration: numericIteration(event.loop_index) ?? iterationByPhase.get(phase) ?? null,
      verdicts: [],
    }
    steps.push(step)

    if (event.event_type === 'prompt_captured' && stepId !== null) {
      openLlmByStepId.set(stepId, step)
    } else if (event.event_type === 'tool_call_started' && callId !== null) {
      openToolByCallId.set(callId, step)
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
