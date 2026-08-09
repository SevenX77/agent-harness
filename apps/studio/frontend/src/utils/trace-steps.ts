import type { CallbackEvent } from '../api/types'
import type { IndexedTraceEvent } from '../hooks/useTraceFilter'
import { traceEventId } from '../hooks/useTraceSelection'
import { eventPhase } from './trace'

export type TraceStepStatus = 'running' | 'done'

export interface TraceStep {
  /** Stable across the step's whole life: it is minted from the opening event. */
  key: string
  phase: string
  status: TraceStepStatus
  /** The event that opened the step — the row's identity and scroll anchor. */
  start: IndexedTraceEvent
  /** The event that closed it. Null while running, and null for a lone event. */
  end: IndexedTraceEvent | null
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
 * Tool calls work the same way, paired on `tool_call_id`: an agent turn can
 * have several calls in flight, so position cannot say which return belongs to
 * which start — the id can, and the engine puts it on both halves (PR #655).
 *
 * Everything else is one step, unchanged. So is a completion whose opening half
 * is not in this list: a filter can hide it, and the answer to that is to show
 * the half you have, not to drop it.
 */
export function buildTraceSteps(events: IndexedTraceEvent[]): TraceStep[] {
  const steps: TraceStep[] = []
  const openLlmByPhase = new Map<string, TraceStep>()
  const openToolByCallId = new Map<string, TraceStep>()

  for (const entry of events) {
    const { event } = entry
    const phase = eventPhase(event)
    const callId = toolCallId(event)

    if (event.event_type === 'llm_call') {
      const open = openLlmByPhase.get(phase)
      if (open) {
        open.end = entry
        open.status = 'done'
        openLlmByPhase.delete(phase)
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

    const opensAStep = event.event_type === 'prompt_captured'
      || (event.event_type === 'tool_call_started' && callId !== null)
    const step: TraceStep = {
      key: traceEventId(event, entry.index),
      phase,
      status: opensAStep ? 'running' : 'done',
      start: entry,
      end: null,
    }
    steps.push(step)

    if (event.event_type === 'prompt_captured') {
      openLlmByPhase.set(phase, step)
    } else if (event.event_type === 'tool_call_started' && callId !== null) {
      openToolByCallId.set(callId, step)
    }
  }

  return steps
}

function toolCallId(event: CallbackEvent): string | null {
  const value = event.tool_call_id
  return typeof value === 'string' && value.length > 0 ? value : null
}
