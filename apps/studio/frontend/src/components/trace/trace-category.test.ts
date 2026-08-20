import { describe, expect, it } from 'vitest'
import { ENGINE_EVENT_TYPES } from '../../utils/engine-event-types'
import { TRACE_CATEGORIES, traceEventCategory } from './trace-category'

describe('traceEventCategory', () => {
  // The filter must account for every event type the engine emits: one that
  // fell outside every bucket would be silently unfilterable. The list is read
  // from ENGINE_EVENT_TYPES rather than copied here, so this test cannot pass
  // by testing a stale idea of what the engine emits.
  it('sorts every event type the engine emits into exactly one bucket', () => {
    expect(ENGINE_EVENT_TYPES.length).toBeGreaterThan(0)
    for (const eventType of ENGINE_EVENT_TYPES) {
      const category = traceEventCategory(eventType)
      expect(TRACE_CATEGORIES).toContain(category)
    }
  })

  it('groups failures under errors', () => {
    expect(traceEventCategory('protocol_violation')).toBe('errors')
  })

  it('groups model interaction under llm', () => {
    expect(traceEventCategory('llm_call')).toBe('llm')
    expect(traceEventCategory('prompt_captured')).toBe('llm')
    expect(traceEventCategory('llm_route_decision')).toBe('llm')
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
