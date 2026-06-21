import { useMemo, useState } from 'react'
import type { CallbackEvent } from '../api/types'
import { eventMessage, eventPhase } from '../utils/trace'

export interface IndexedTraceEvent {
  event: CallbackEvent
  index: number
}

export interface TraceFilterState {
  searchTerm: string
  selectedTypes: string[]
  selectedPhases: string[]
}

/**
 * The active filter predicates the trace panel applies to its received events.
 * `activePhase` is the focused-node link narrowing (atom #17); the other three
 * are the user-driven search box / type chips / phase chips (atom #13).
 */
export interface TraceFilterCriteria {
  searchTerm: string
  selectedTypes: string[]
  selectedPhases: string[]
  activePhase: string | null
}

function includesValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]
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
 * matches the search term AND the selected type set AND the selected phase set
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
      const matchesType = criteria.selectedTypes.length === 0
        || criteria.selectedTypes.includes(event.event_type)
      const matchesPhase = criteria.selectedPhases.length === 0
        || criteria.selectedPhases.includes(phase)
      const matchesActivePhase = !criteria.activePhase || phase === criteria.activePhase
      return matchesSearch && matchesType && matchesPhase && matchesActivePhase
    })
}

export function useTraceFilter(events: CallbackEvent[], activePhase: string | null = null) {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedTypes, setSelectedTypes] = useState<string[]>([])
  const [selectedPhases, setSelectedPhases] = useState<string[]>([])

  const eventTypes = useMemo(
    () => Array.from(new Set(events.map((event) => event.event_type))).sort(),
    [events],
  )
  const phases = useMemo(
    () => Array.from(new Set(events.map((event) => eventPhase(event)))).sort(),
    [events],
  )

  const filteredEvents = useMemo<IndexedTraceEvent[]>(
    () => filterTraceEvents(events, { searchTerm, selectedTypes, selectedPhases, activePhase }),
    [activePhase, events, searchTerm, selectedPhases, selectedTypes],
  )

  const clearFilters = () => {
    setSearchTerm('')
    setSelectedTypes([])
    setSelectedPhases([])
  }

  return {
    searchTerm,
    selectedTypes,
    selectedPhases,
    eventTypes,
    phases,
    filteredEvents,
    setSearchTerm,
    toggleType: (eventType: string) => setSelectedTypes((values) => includesValue(values, eventType)),
    togglePhase: (phase: string) => setSelectedPhases((values) => includesValue(values, phase)),
    clearFilters,
  }
}
