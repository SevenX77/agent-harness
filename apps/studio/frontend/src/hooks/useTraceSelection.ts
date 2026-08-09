import { useCallback, useState } from 'react'
import type { CallbackEvent } from '../api/types'

export function traceEventId(event: CallbackEvent, index: number): string {
  return `${event.timestamp}-${event.event_type}-${index}`
}

/**
 * The trace's own view state: `selectedEventId` is the row the user last opened.
 *
 * There is no link switch any more — canvas focus scrolls the trace instead of
 * narrowing it (decision 2026-08-09 D2), so there is nothing left to switch off.
 *
 * WHICH node is focused is deliberately NOT held here: `Workspace.selectedNodeId`
 * owns that, and a second copy would be a second truth to keep in sync.
 */
export function useTraceSelection() {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)

  const selectEvent = useCallback((event: CallbackEvent, index: number) => {
    setSelectedEventId(traceEventId(event, index))
  }, [])

  return { selectedEventId, selectEvent }
}
