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

  const filteredEvents = useMemo<IndexedTraceEvent[]>(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase()
    return events
      .map((event, index) => ({ event, index }))
      .filter(({ event }) => {
        const phase = eventPhase(event)
        const matchesSearch = normalizedSearch.length === 0
          || eventSearchText(event).includes(normalizedSearch)
        const matchesType = selectedTypes.length === 0 || selectedTypes.includes(event.event_type)
        const matchesPhase = selectedPhases.length === 0 || selectedPhases.includes(phase)
        const matchesActivePhase = !activePhase || phase === activePhase
        return matchesSearch && matchesType && matchesPhase && matchesActivePhase
      })
  }, [activePhase, events, searchTerm, selectedPhases, selectedTypes])

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
