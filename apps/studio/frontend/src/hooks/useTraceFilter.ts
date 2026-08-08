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
 * `activePhase` is the focused-node link narrowing (atom #17); the other three
 * are the user-driven search box / type chips / phase chips (atom #13).
 */
export interface TraceFilterCriteria {
  searchTerm: string
  selectedCategories: TraceCategory[]
  selectedPhases: string[]
  activePhase: string | null
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
 * matches the search term AND the selected category set AND the selected phase set
 * AND the focused-node active phase — empty criteria are no-ops.
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
      const matchesActivePhase = !criteria.activePhase || phase === criteria.activePhase
      return matchesSearch && matchesCategory && matchesPhase && matchesActivePhase
    })
}

export function useTraceFilter(events: CallbackEvent[], activePhase: string | null = null) {
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
    () => filterTraceEvents(events, { searchTerm, selectedCategories, selectedPhases, activePhase }),
    [activePhase, events, searchTerm, selectedCategories, selectedPhases],
  )

  const clearFilters = () => {
    setSearchTerm('')
    setSelectedCategories([])
    setSelectedPhases([])
  }

  return {
    searchTerm,
    selectedCategories,
    selectedPhases,
    phases,
    filteredEvents,
    setSearchTerm,
    setSelectedCategories,
    setSelectedPhases,
    clearFilters,
  }
}
