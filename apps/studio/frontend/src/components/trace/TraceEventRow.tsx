import { AlertOctagon, ChevronDown, ChevronRight, Hash, ListTree, MessageSquare, Plus, RotateCcw, TerminalSquare, Wrench } from 'lucide-react'
import { useState } from 'react'
import type { CallbackEvent } from '../../api/types'
import {
  errorStack,
  eventColor,
  eventMessage,
  eventMockedSource,
  eventPhase,
  mockedSourceClass,
  mockedSourceLabel,
  payloadPreview,
  retryBadge,
  tokenText,
  toolCallSummary,
} from '../../utils/trace'
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
  const [subtreeOpen, setSubtreeOpen] = useState(false)
  const isExpanded = expanded ?? localExpanded
  const tokens = tokenText(event)
  const mockedSource = eventMockedSource(event)
  const retry = retryBadge(event)
  const inspectable = event.event_type === 'prompt_captured' || event.event_type === 'llm_call'
  const isError = event.event_type === 'internal_error' || event.event_type === 'validation_fail'
  // n4-trace #16/#24: agent tool_call events fold under a semantic verb and
  // expose an inline subtree (args → result) instead of a raw JSON dump.
  const toolCall = toolCallSummary(event)
  // n4-trace #25: retries-exhausted (and per-attempt validation_fail) carry a
  // list of failure reasons surfaced as an explicit Error Stack.
  const failures = errorStack(event)

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
          {retry ? (
            <span
              aria-label={`Retry attempt ${retry.label}`}
              title={retry.exhausted ? `Final attempt (${retry.label})` : `Retry attempt ${retry.label}`}
              className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${
                retry.exhausted
                  ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300'
                  : 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
              }`}
            >
              <RotateCcw className="h-3 w-3" />
              {retry.label}
            </span>
          ) : null}
          {mockedSource ? (
            <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${mockedSourceClass(mockedSource)}`}>
              {mockedSourceLabel(mockedSource)}
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
        {toolCall ? (
          <span className="mt-2 flex items-center gap-2 text-xs">
            {toolCall.toolName === 'Bash' ? (
              <TerminalSquare className="h-3.5 w-3.5 text-emerald-500" />
            ) : (
              <Wrench className="h-3.5 w-3.5 text-emerald-500" />
            )}
            <span className="font-medium text-gray-700 dark:text-gray-200">{toolCall.headline}</span>
            {toolCall.durationLabel ? (
              <span className="text-gray-400 dark:text-gray-500">{toolCall.durationLabel}</span>
            ) : null}
            <span
              role="button"
              tabIndex={0}
              aria-label={subtreeOpen ? 'Collapse execution subtree' : 'Expand execution subtree'}
              onClick={(clickEvent) => {
                clickEvent.stopPropagation()
                setSubtreeOpen((open) => !open)
              }}
              onKeyDown={(keyEvent) => {
                if (keyEvent.key === 'Enter' || keyEvent.key === ' ') {
                  keyEvent.preventDefault()
                  keyEvent.stopPropagation()
                  setSubtreeOpen((open) => !open)
                }
              }}
              className="inline-flex items-center gap-1 rounded border border-emerald-300 px-1.5 py-0.5 font-medium text-emerald-600 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-900/30"
            >
              {subtreeOpen ? <ListTree className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
              {subtreeOpen ? 'Subtree' : 'Expand'}
            </span>
          </span>
        ) : null}
        {failures.length > 0 ? <ErrorStack failures={failures} /> : null}
      </button>
      {toolCall && subtreeOpen && !isExpanded ? <ToolCallSubtree summary={toolCall} /> : null}
      {isExpanded ? <ExpandedPayload event={event} /> : null}
    </div>
  )
}

// n4-trace #25: each prior attempt's failure reason, surfaced as an explicit
// Error Stack when retries are exhausted (retry_exhausted.final_errors) or for
// a single failed attempt (validation_fail.errors).
function ErrorStack({ failures }: { failures: string[] }) {
  return (
    <div className="mt-2 rounded border border-red-200 bg-red-50/70 p-2 dark:border-red-800 dark:bg-red-900/20">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-red-700 dark:text-red-300">
        <AlertOctagon className="h-3.5 w-3.5" />
        Error Stack ({failures.length})
      </div>
      <ol className="mt-1.5 space-y-1">
        {failures.map((reason, position) => (
          <li
            key={`${position}-${reason.slice(0, 24)}`}
            className="flex gap-2 rounded border border-red-200 bg-white px-2 py-1 text-xs text-red-700 dark:border-red-800 dark:bg-slate-950 dark:text-red-300"
          >
            <span className="font-mono text-red-400 dark:text-red-500">#{position + 1}</span>
            <span className="whitespace-pre-wrap">{reason}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

// n4-trace #16/#24: in-place execution subtree for an agent tool_call — the
// verb-classified call with its args (input) and result (output), so the agent
// is not a black box and the user never has to read raw JSON.
function ToolCallSubtree({ summary }: { summary: NonNullable<ReturnType<typeof toolCallSummary>> }) {
  return (
    <div className="mt-2 rounded-md border border-emerald-200 bg-emerald-50/60 p-2 text-xs dark:border-emerald-900/60 dark:bg-emerald-900/15">
      <div className="flex items-center gap-1.5 font-medium text-emerald-700 dark:text-emerald-300">
        <ListTree className="h-3.5 w-3.5" />
        {summary.headline}
      </div>
      {summary.args ? (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase text-emerald-600/80 dark:text-emerald-400/80">Input</div>
          <pre className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-white/80 p-2 text-[11px] text-gray-700 dark:bg-slate-950 dark:text-slate-200">
            {summary.args}
          </pre>
        </div>
      ) : null}
      {summary.resultSummary ? (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase text-emerald-600/80 dark:text-emerald-400/80">Result</div>
          <p className="mt-0.5 whitespace-pre-wrap leading-relaxed text-gray-700 dark:text-slate-200">{summary.resultSummary}</p>
        </div>
      ) : null}
    </div>
  )
}

function ExpandedPayload({ event }: { event: CallbackEvent }) {
  // n4-trace #16: agent tool_call events fold under their classified subtree
  // (verb · tool, input, result) instead of a raw JSON dump.
  const toolCall = toolCallSummary(event)
  if (toolCall) {
    return <ToolCallSubtree summary={toolCall} />
  }
  return <GenericPayload event={event} />
}

function GenericPayload({ event }: { event: CallbackEvent }) {
  // §4: long payloads default to a collapsed ~2KB head; only the user opts in to
  // the full dump so a multi-megabyte trace event never floods (or OOMs) the panel.
  const [showFull, setShowFull] = useState(false)
  const preview = payloadPreview(event)
  const body = showFull ? JSON.stringify(event, null, 2) : preview.text
  return (
    <div className="mt-2">
      <pre className="max-h-40 overflow-auto rounded-md border border-gray-200 bg-slate-950 p-3 text-xs leading-relaxed text-slate-100 shadow-sm dark:border-slate-800">
        {body}
      </pre>
      {preview.truncated ? (
        <button
          type="button"
          onClick={(clickEvent) => {
            clickEvent.stopPropagation()
            setShowFull((open) => !open)
          }}
          className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-sky-600 hover:text-sky-700 dark:text-sky-400 dark:hover:text-sky-300"
        >
          {showFull ? 'Collapse payload' : `Show full payload (${preview.sizeLabel})`}
        </button>
      ) : null}
    </div>
  )
}
