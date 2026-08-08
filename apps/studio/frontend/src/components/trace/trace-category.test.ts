import { describe, expect, it } from 'vitest'
import { TRACE_CATEGORIES, traceEventCategory } from './trace-category'

// Every event type the engine can emit today. The filter must account for all of
// them: a type that fell outside every bucket would be silently unfilterable.
const KNOWN_EVENT_TYPES = [
  'run_started',
  'run_ended',
  'phase_start',
  'phase_end',
  'input_dispatch',
  'agent_loop_iteration',
  'predict_chain_start',
  'finish_task',
  'llm_call',
  'prompt_captured',
  'llm_fallback',
  'tool_call',
  'internal_error',
  'validation_fail',
]

describe('traceEventCategory', () => {
  it('sorts every known event type into exactly one bucket', () => {
    for (const eventType of KNOWN_EVENT_TYPES) {
      const category = traceEventCategory(eventType)
      expect(TRACE_CATEGORIES).toContain(category)
    }
  })

  it('groups failures under errors', () => {
    expect(traceEventCategory('internal_error')).toBe('errors')
    expect(traceEventCategory('validation_fail')).toBe('errors')
  })

  it('groups model interaction under llm', () => {
    expect(traceEventCategory('llm_call')).toBe('llm')
    expect(traceEventCategory('prompt_captured')).toBe('llm')
    expect(traceEventCategory('llm_fallback')).toBe('llm')
  })

  it('groups tool execution under tools', () => {
    expect(traceEventCategory('tool_call')).toBe('tools')
    expect(traceEventCategory('tool_result')).toBe('tools')
  })

  it('puts the run skeleton — and any event type it has never seen — under flow', () => {
    expect(traceEventCategory('run_started')).toBe('flow')
    expect(traceEventCategory('phase_end')).toBe('flow')
    expect(traceEventCategory('some_event_invented_next_week')).toBe('flow')
  })

  it('offers exactly four buckets, so the control never grows with the run', () => {
    expect([...TRACE_CATEGORIES]).toEqual(['errors', 'llm', 'tools', 'flow'])
  })
})
