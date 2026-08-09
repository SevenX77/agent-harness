import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../api/types'
import type { IndexedTraceEvent } from '../hooks/useTraceFilter'
import { buildTraceSteps } from './trace-steps'

function indexed(events: Partial<CallbackEvent>[]): IndexedTraceEvent[] {
  return events.map((event, index) => ({
    event: { schema_version: '1.0', timestamp: `2026-08-09T00:00:0${index}Z`, ...event } as CallbackEvent,
    index,
  }))
}

describe('buildTraceSteps (decision 2026-08-09 D4)', () => {
  it('opens an LLM step the moment the prompt is captured, before any answer exists', () => {
    // This is the whole point: the reader sees "this node is thinking, here is
    // what it was asked" while it happens, not a summary once it is over.
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].status).toBe('running')
    expect(steps[0].end).toBeNull()
  })

  it('closes that same step when the call comes back — one step, not two rows', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft' },
      { event_type: 'llm_call', phase_name: 'draft' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].status).toBe('done')
    expect(steps[0].start.event.event_type).toBe('prompt_captured')
    expect(steps[0].end?.event.event_type).toBe('llm_call')
  })

  it('does not let one node\'s answer close another node\'s prompt', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft' },
      { event_type: 'prompt_captured', phase_name: 'review' },
      { event_type: 'llm_call', phase_name: 'review' },
    ]))

    expect(steps).toHaveLength(2)
    expect(steps[0].phase).toBe('draft')
    expect(steps[0].status).toBe('running')
    expect(steps[1].phase).toBe('review')
    expect(steps[1].status).toBe('done')
  })

  it('pairs tool halves by tool_call_id, not by position', () => {
    // An agent turn can have several calls in flight; whichever returns first
    // must close ITS OWN step (engine contract, PR #655).
    const steps = buildTraceSteps(indexed([
      { event_type: 'tool_call_started', phase_name: 'draft', tool_call_id: 'a', tool_name: 'Read' },
      { event_type: 'tool_call_started', phase_name: 'draft', tool_call_id: 'b', tool_name: 'Bash' },
      { event_type: 'tool_call', phase_name: 'draft', tool_call_id: 'b', tool_name: 'Bash' },
    ]))

    expect(steps).toHaveLength(2)
    expect(steps[0].status).toBe('running')
    expect(steps[1].status).toBe('done')
    expect(steps[1].end?.event.tool_call_id).toBe('b')
  })

  it('leaves unpaired events exactly as they are, one row each', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'phase_start', phase_name: 'draft' },
      { event_type: 'validation_fail', phase_name: 'draft' },
      { event_type: 'phase_end', phase_name: 'draft' },
    ]))

    expect(steps).toHaveLength(3)
    expect(steps.every((step) => step.status === 'done')).toBe(true)
    expect(steps.every((step) => step.end === null)).toBe(true)
  })

  it('treats a completion with no start as a finished step of its own', () => {
    // A filter can hide the opening half, and a trace can be read from any
    // point. Neither is a reason to drop the event on the floor.
    const steps = buildTraceSteps(indexed([
      { event_type: 'llm_call', phase_name: 'draft' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].status).toBe('done')
    expect(steps[0].start.event.event_type).toBe('llm_call')
  })

  it('keeps steps in the order they started', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft' },
      { event_type: 'phase_start', phase_name: 'draft' },
      { event_type: 'llm_call', phase_name: 'draft' },
    ]))

    expect(steps.map((step) => step.start.index)).toEqual([0, 1])
  })
})
