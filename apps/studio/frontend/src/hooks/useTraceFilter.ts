import { useMemo, useState } from 'react'
import type { CallbackEvent } from '../api/types'
import { traceEventCategory, type TraceCategory } from '../components/trace/trace-category'
import { eventMessage, eventPhase, RUN_SCOPE } from '../utils/trace'

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

function eventSearchText(event: CallbackEvent): string {
  return [
    event.event_type,
    eventPhase(event),
    eventMessage(event),
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
): IndexedTraceEvent[] {
  const normalizedSearch = criteria.searchTerm.trim().toLowerCase()
  return events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => {
      const phase = eventPhase(event)
      const matchesSearch = normalizedSearch.length === 0
        || eventSearchText(event).includes(normalizedSearch)
      const matchesCategory = criteria.selectedCategories.length === 0
        || criteria.selectedCategories.includes(traceEventCategory(event.event_type))
      const matchesPhase = criteria.selectedPhases.length === 0
        || criteria.selectedPhases.includes(phase)
      return matchesSearch && matchesCategory && matchesPhase
    })
}

export function useTraceFilter(events: CallbackEvent[]) {
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
    () => filterTraceEvents(events, { searchTerm, selectedCategories, selectedPhases }),
    [events, searchTerm, selectedCategories, selectedPhases],
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
