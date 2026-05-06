import { ChevronDown, ChevronRight, Hash, MessageSquare } from 'lucide-react'
import { useState } from 'react'
import type { CallbackEvent } from '../../api/types'
import { eventColor, eventMessage, eventPhase, tokenText } from '../../utils/trace'
import { EventTypeBadge } from './EventTypeBadge'

interface TraceEventRowProps {
  event: CallbackEvent
  index: number
  eventId: string
  selected?: boolean
  highlighted?: boolean
  expanded?: boolean
  onToggleExpanded?: () => void
  onSelectPrompt: (index: number) => void
  onSelectEvent?: (index: number, event: CallbackEvent) => void
}

export const TRACE_EVENT_ROW_HEIGHT = 128

export function TraceEventRow({
  event,
  index,
  eventId,
  selected = false,
  highlighted = false,
  expanded,
  onToggleExpanded,
  onSelectPrompt,
  onSelectEvent,
}: TraceEventRowProps) {
  const [localExpanded, setLocalExpanded] = useState(false)
  const isExpanded = expanded ?? localExpanded
  const tokens = tokenText(event)
  const inspectable = event.event_type === 'prompt_captured' || event.event_type === 'llm_call'
  const isError = event.event_type === 'internal_error' || event.event_type === 'validation_fail'

  return (
    <div className="relative pl-6" style={{ minHeight: TRACE_EVENT_ROW_HEIGHT - 20 }}>
      <div className={`absolute -left-[9px] top-1 h-4 w-4 rounded-full border-2 border-white dark:border-slate-900 ${eventColor(event.event_type)}`} />
      <button
        type="button"
        data-trace-event-id={eventId}
        aria-label={`Trace event ${event.event_type} in ${eventPhase(event)}`}
        aria-expanded={isExpanded}
        onClick={() => {
          if (onToggleExpanded) {
            onToggleExpanded()
          } else {
            setLocalExpanded((open) => !open)
          }
          onSelectEvent?.(index, event)
        }}
        className={`block w-full rounded-md border p-3 text-left shadow-sm transition-colors ${
          selected
            ? 'border-sky-300 bg-sky-50 dark:border-sky-700 dark:bg-sky-900/30'
            : highlighted
              ? 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/20'
              : isError
                ? 'border-red-200 bg-red-50 hover:border-red-400 dark:border-red-800 dark:bg-red-900/20 dark:hover:border-red-600'
                : 'border-gray-200 bg-white hover:border-gray-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700'
        }`}
      >
        <div className="mb-1 flex items-center justify-between gap-3">
          <span className="flex min-w-0 items-center gap-2">
            {isExpanded ? <ChevronDown className="h-3.5 w-3.5 text-gray-400" /> : <ChevronRight className="h-3.5 w-3.5 text-gray-400" />}
            <EventTypeBadge eventType={event.event_type} />
          </span>
          {tokens ? (
            <span className="flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-600 dark:bg-violet-900/40 dark:text-violet-300">
              <Hash className="h-3 w-3" />
              {tokens}
            </span>
          ) : null}
        </div>
        <div className="text-xs font-medium uppercase text-gray-400 dark:text-gray-500">{eventPhase(event)}</div>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{eventMessage(event)}</p>
        {isError && typeof event.error_message === 'string' ? (
          <p className="mt-2 rounded border border-red-200 bg-white px-2 py-1 text-xs text-red-700 dark:border-red-800 dark:bg-slate-950 dark:text-red-300">
            {event.error_message}
          </p>
        ) : null}
        {inspectable ? (
          <span
            role="button"
            tabIndex={0}
            onClick={(clickEvent) => {
              clickEvent.stopPropagation()
              onSelectPrompt(index)
            }}
            onKeyDown={(keyEvent) => {
              if (keyEvent.key === 'Enter' || keyEvent.key === ' ') {
                keyEvent.preventDefault()
                keyEvent.stopPropagation()
                onSelectPrompt(index)
              }
            }}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-violet-500 hover:text-violet-700 dark:text-violet-400 dark:hover:text-violet-300"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Inspect prompt <ChevronRight className="h-3 w-3" />
          </span>
        ) : null}
      </button>
      {isExpanded ? (
        <pre className="mt-2 max-h-40 overflow-auto rounded-md border border-gray-200 bg-slate-950 p-3 text-xs leading-relaxed text-slate-100 shadow-sm dark:border-slate-800">
          {JSON.stringify(event, null, 2)}
        </pre>
      ) : null}
    </div>
  )
}
