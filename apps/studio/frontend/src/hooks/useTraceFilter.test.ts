import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../api/types'
import { filterTraceEvents, useTraceFilter } from './useTraceFilter'

// n5-trace atom #13 (trace-search-filter): the trace panel filters the events it
// has ALREADY received — client-side, no re-request. These tests pin the three
// design clauses against the pure projection that backs the hook:
//   1. a search term shows only matching events,
//   2. selecting a phase shows only that phase's events,
//   3. filtering applies to the already-received event list (in-place, no fetch).

function event(overrides: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-13T00:00:00Z',
    ...overrides,
  } as CallbackEvent
}

// A realistic mixed batch: two phases (draft / review) and assorted event types,
// mirroring what useRunStream flushes into the panel during a live run.
function sampleEvents(): CallbackEvent[] {
  return [
    event({ event_type: 'phase_start', phase_name: 'draft' }),
    event({ event_type: 'llm_call', phase_name: 'draft' }),
    event({ event_type: 'phase_end', phase_name: 'draft' }),
    event({ event_type: 'phase_start', phase_name: 'review' }),
    event({ event_type: 'phase_end', phase_name: 'review' }),
  ]
}

describe('filterTraceEvents (n5-trace #13 client-side projection)', () => {
  it('keeps original positions and order when no filter is active', () => {
    const events = sampleEvents()
    const result = filterTraceEvents(events, {
      searchTerm: '',
      selectedTypes: [],
      selectedPhases: [],
      activePhase: null,
    })

    expect(result).toHaveLength(events.length)
    expect(result.map(({ index }) => index)).toEqual([0, 1, 2, 3, 4])
    // The projection carries the SAME event objects — it is a view, not a copy.
    expect(result[1].event).toBe(events[1])
  })

  it('clause 1: a search term shows only matching events', () => {
    const events = sampleEvents()
    // "llm_call" appears in exactly one event's serialized text.
    const result = filterTraceEvents(events, {
      searchTerm: 'llm_call',
      selectedTypes: [],
      selectedPhases: [],
      activePhase: null,
    })

    expect(result.map(({ event }) => event.event_type)).toEqual(['llm_call'])
    expect(result.map(({ index }) => index)).toEqual([1])
  })

  it('clause 1: search is case-insensitive and trims surrounding whitespace', () => {
    const events = sampleEvents()
    const result = filterTraceEvents(events, {
      searchTerm: '  REVIEW  ',
      selectedTypes: [],
      selectedPhases: [],
      activePhase: null,
    })

    // Both review-phase events match (phase name is part of the search text).
    expect(result.map(({ index }) => index)).toEqual([3, 4])
  })

  it('clause 2: selecting a phase shows only that phase\'s events', () => {
    const events = sampleEvents()
    const result = filterTraceEvents(events, {
      searchTerm: '',
      selectedTypes: [],
      selectedPhases: ['review'],
      activePhase: null,
    })

    expect(result.every(({ event }) => event.phase_name === 'review')).toBe(true)
    expect(result.map(({ index }) => index)).toEqual([3, 4])
  })

  it('clause 2: the active (focused) phase narrows the trace to that phase', () => {
    const events = sampleEvents()
    const result = filterTraceEvents(events, {
      searchTerm: '',
      selectedTypes: [],
      selectedPhases: [],
      activePhase: 'draft',
    })

    expect(result.map(({ index }) => index)).toEqual([0, 1, 2])
  })

  it('combines search + phase as an AND, both applied to the same received batch', () => {
    const events = sampleEvents()
    const result = filterTraceEvents(events, {
      searchTerm: 'phase_start',
      selectedTypes: [],
      selectedPhases: ['draft'],
      activePhase: null,
    })

    // Only the draft phase_start survives both predicates.
    expect(result.map(({ index }) => index)).toEqual([0])
  })
})

describe('useTraceFilter (hook surface over the pure projection)', () => {
  it('clause 3: filtering applies to the already-received events in place', () => {
    let hook: ReturnType<typeof useTraceFilter> | null = null
    const events = sampleEvents()

    function Probe() {
      hook = useTraceFilter(events)
      return null
    }

    renderToStaticMarkup(createElement(Probe))

    expect(hook).not.toBeNull()
    // Default: everything received is shown (no fetch, no drop).
    expect(hook!.filteredEvents).toHaveLength(events.length)
    expect(hook!.phases).toEqual(['draft', 'review'])
    expect(hook!.eventTypes).toContain('llm_call')
  })

  it('narrows to the active phase passed by the focused-node link', () => {
    let hook: ReturnType<typeof useTraceFilter> | null = null
    const events = sampleEvents()

    function Probe() {
      hook = useTraceFilter(events, 'review')
      return null
    }

    renderToStaticMarkup(createElement(Probe))

    expect(hook).not.toBeNull()
    expect(hook!.filteredEvents.map(({ index }) => index)).toEqual([3, 4])
  })
})
