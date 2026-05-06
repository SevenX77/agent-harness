import { useCallback, useState } from 'react'
import type { CallbackEvent } from '../api/types'
import { eventPhase } from '../utils/trace'

export interface TraceSelectionState {
  linkEnabled: boolean
  selectedPhaseId: string | null
  selectedEventId: string | null
}

export function traceEventId(event: CallbackEvent, index: number): string {
  return `${event.timestamp}-${event.event_type}-${index}`
}

export function useTraceSelection() {
  const [state, setState] = useState<TraceSelectionState>({
    linkEnabled: true,
    selectedPhaseId: null,
    selectedEventId: null,
  })

  const setLinkEnabled = useCallback((linkEnabled: boolean) => {
    setState((current) => ({ ...current, linkEnabled }))
  }, [])

  const selectPhase = useCallback((phaseId: string | null) => {
    setState((current) => ({ ...current, selectedPhaseId: phaseId }))
  }, [])

  const selectEvent = useCallback((event: CallbackEvent, index: number) => {
    setState((current) => ({
      ...current,
      selectedEventId: traceEventId(event, index),
      selectedPhaseId: eventPhase(event),
    }))
  }, [])

  const clearSelection = useCallback(() => {
    setState((current) => ({ ...current, selectedPhaseId: null, selectedEventId: null }))
  }, [])

  return {
    ...state,
    setLinkEnabled,
    selectPhase,
    selectEvent,
    clearSelection,
  }
}
