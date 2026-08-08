import { useCallback, useState } from 'react'
import type { CallbackEvent } from '../api/types'

export function traceEventId(event: CallbackEvent, index: number): string {
  return `${event.timestamp}-${event.event_type}-${index}`
}

/**
 * The trace's own view state.
 *
 * `linkEnabled` decides whether canvas focus narrows the list — focus deciding
 * granularity is the designed behaviour (`docs/studio/mvp1/01_workflows/
 * 04_run-and-verify.md` D5), and this is the escape hatch from it.
 * `selectedEventId` is the row the user last opened.
 *
 * WHICH node is focused is deliberately NOT held here: `Workspace.selectedNodeId`
 * owns that, and a second copy would be a second truth to keep in sync.
 */
export function useTraceSelection() {
  const [linkEnabled, setLinkEnabled] = useState(true)
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)

  const selectEvent = useCallback((event: CallbackEvent, index: number) => {
    setSelectedEventId(traceEventId(event, index))
  }, [])

  return { linkEnabled, setLinkEnabled, selectedEventId, selectEvent }
}
