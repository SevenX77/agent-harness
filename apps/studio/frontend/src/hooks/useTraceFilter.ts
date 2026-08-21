import { useMemo, useState } from 'react'
import type { CallbackEvent } from '../api/types'
import { traceEventCategory, type TraceCategory } from '../components/trace/trace-category'
import { eventHeadline, eventPhase, RUN_SCOPE } from '../utils/trace'
import { traceHeadlineText, useTraceCopy } from '../components/trace/trace-copy'

export interface IndexedTraceEvent {
  event: CallbackEvent
  index: number
}

export interface TraceFilterState {
  searchTerm: string
  selectedCategories: TraceCategory[]
  selectedPhases: string[]
}

/**
 * The active filter predicates the trace panel applies to its received events.
 *
 * All three are USER-driven (atom #13): the search box, the type chips, the
 * node chips. Canvas focus is deliberately absent — it used to narrow the list
 * silently, which made the trace unable to be read end to end (decision
 * 2026-08-09 D2). Focus now scrolls, and only the user hides anything.
 */
export interface TraceFilterCriteria {
  searchTerm: string
  selectedCategories: TraceCategory[]
  selectedPhases: string[]
}

/**
 * What a search term is matched against.
 *
 * The reader's own words are part of it: typing what a row SAYS has to find
 * that row, and what a row says depends on the reader's language. So the
 * headline arrives already rendered rather than being built here — this
 * projection stays pure and language-blind, and the hook below hands it the
 * same sentence the row shows.
 */
function eventSearchText(event: CallbackEvent, headline: string): string {
  return [
    event.event_type,
    eventPhase(event),
    headline,
    JSON.stringify(event),
  ].join(' ').toLowerCase()
}

/**
 * n5-trace atom #13 (trace-search-filter): the pure projection that backs the
 * Trace panel's client-side filter. It runs over the events the panel has
 * ALREADY received (no re-request) and keeps each surviving event's original
 * `index` so selection/scroll positions stay stable. An event survives when it
 * matches the search term AND the selected category set AND the selected phase
 * set — empty criteria are no-ops.
 */
export function filterTraceEvents(
  events: CallbackEvent[],
  criteria: TraceFilterCriteria,
  headlineOf: (event: CallbackEvent) => string,
): IndexedTraceEvent[] {
  const normalizedSearch = criteria.searchTerm.trim().toLowerCase()
  return events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => {
      const phase = eventPhase(event)
      const matchesSearch = normalizedSearch.length === 0
        || eventSearchText(event, headlineOf(event)).includes(normalizedSearch)
      const matchesCategory = criteria.selectedCategories.length === 0
        || criteria.selectedCategories.includes(traceEventCategory(event.event_type))
      const matchesPhase = criteria.selectedPhases.length === 0
        || criteria.selectedPhases.includes(phase)
      return matchesSearch && matchesCategory && matchesPhase
    })
}

export function useTraceFilter(events: CallbackEvent[]) {
  const t = useTraceCopy()
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<TraceCategory[]>([])
  const [selectedPhases, setSelectedPhases] = useState<string[]>([])

  // Only real nodes are offered as filters: the run scope is not a node, and a
  // chip for it would filter to "the two events that belong to no node".
  const phases = useMemo(
    () => Array.from(new Set(events.map((event) => eventPhase(event))))
      .filter((phase) => phase !== RUN_SCOPE)
      .sort(),
    [events],
  )

  const filteredEvents = useMemo<IndexedTraceEvent[]>(
    () => filterTraceEvents(
      events,
      { searchTerm, selectedCategories, selectedPhases },
      (event) => traceHeadlineText(eventHeadline(event), t),
    ),
    [events, searchTerm, selectedCategories, selectedPhases, t],
  )

  return {
    searchTerm,
    selectedCategories,
    selectedPhases,
    phases,
    filteredEvents,
    setSearchTerm,
    setSelectedCategories,
    setSelectedPhases,
  }
}
