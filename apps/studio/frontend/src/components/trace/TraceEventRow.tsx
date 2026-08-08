import { AlertOctagon, AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Cpu, Hash, ListTree, MessageSquare, Plus, RotateCcw, TerminalSquare, Wrench } from 'lucide-react'
import { useState } from 'react'
import type { CallbackEvent } from '../../api/types'
import type { LlmFallbackDetails } from '../../utils/trace'
import {
  errorStack,
  eventColor,
  eventMessage,
  eventMockedSource,
  eventModelName,
  eventMessageIsRedundant,
  eventPhase,
  eventTimeLabel,
  llmFallbackDetails,
  mockedSourceClass,
  mockedSourceLabel,
  payloadPreview,
  retryBadge,
  tokenText,
  toolCallSummary,
} from '../../utils/trace'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { EventTypeBadge } from './EventTypeBadge'

interface TraceEventRowProps {
  event: CallbackEvent
  index: number
  eventId: string
  selected?: boolean
  expanded?: boolean
  onToggleExpanded?: () => void
  onSelectPrompt: (index: number) => void
  onSelectEvent?: (index: number, event: CallbackEvent) => void
}

export function TraceEventRow({
  event,
  index,
  eventId,
  selected = false,
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
  // trace-observability F7: provider fallback renders as an explicit amber block,
  // and rows that know which model served the call carry a model chip.
  const fallback = llmFallbackDetails(event)
  const modelName = eventModelName(event)
  // A timeline needs time: each row shows its wall-clock moment (muted mono,
  // secondary info one shade dimmer — same hierarchy as copilot tool activity).
  const timeLabel = eventTimeLabel(event)

  return (
    <div className="relative pl-5">
      <div className={`absolute -left-[7px] top-2 size-3 rounded-full border-2 border-background ${eventColor(event.event_type)}`} />
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
        className={`block w-full rounded-md border-0 px-2.5 py-1.5 text-left transition-colors ${
          selected
            ? 'bg-accent'
            : isError
              ? 'bg-destructive/10 hover:bg-destructive/15'
              : 'hover:bg-accent/50'
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2">
            {isExpanded ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
            <EventTypeBadge eventType={event.event_type} />
            {timeLabel ? (
              <span data-trace-time className="font-mono text-[10px] text-muted-foreground/80">{timeLabel}</span>
            ) : null}
          </span>
          {tokens ? (
            <span className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
              <Hash className="h-3 w-3" />
              {tokens}
            </span>
          ) : null}
          {modelName ? (
            <span
              data-trace-model-chip
              title={`Model: ${modelName}`}
              className="flex max-w-[180px] items-center gap-1 rounded-full border border-border bg-muted/40 px-2 py-0.5 font-mono text-xs text-muted-foreground"
            >
              <Cpu className="h-3 w-3 shrink-0" />
              <span className="truncate">{modelName}</span>
            </span>
          ) : null}
          {retry ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  aria-label={`Retry attempt ${retry.label}`}
                  className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${
                    retry.exhausted
                      ? 'border-destructive-border bg-destructive/10 text-destructive'
                      : 'border-warning-border bg-warning/10 text-warning'
                  }`}
                >
                  <RotateCcw className="h-3 w-3" />
                  {retry.label}
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {retry.exhausted ? `Final attempt (${retry.label})` : `Retry attempt ${retry.label}`}
              </TooltipContent>
            </Tooltip>
          ) : null}
          {mockedSource ? (
            <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${mockedSourceClass(mockedSource)}`}>
              {mockedSourceLabel(mockedSource)}
            </span>
          ) : null}
        </div>
        {eventMessageIsRedundant(event) ? null : (
          <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-foreground/80">
            {eventMessage(event)}
          </p>
        )}
        {isError && typeof event.error_message === 'string' ? (
          <p className="mt-2 rounded border border-destructive-border/60 bg-background px-2 py-1 text-xs text-destructive">
            {event.error_message}
          </p>
        ) : null}
        {fallback ? <FallbackBlock details={fallback} /> : null}
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
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-link hover:text-link/80"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Inspect prompt <ChevronRight className="h-3 w-3" />
          </span>
        ) : null}
        {toolCall ? (
          <span className="mt-2 flex items-center gap-2 text-xs">
            {toolCall.toolName === 'Bash' ? (
              <TerminalSquare className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
            )}
            <span className="font-medium text-foreground">{toolCall.headline}</span>
            {toolCall.durationLabel ? (
              <span className="text-muted-foreground">{toolCall.durationLabel}</span>
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
              className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 font-medium text-muted-foreground hover:bg-accent"
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

// trace-observability F7: the failing route → takeover route (with the models
// behind them) plus the gateway's failure reason. Mirrors the Error Stack
// pattern but in warning amber — a fallback degrades the run, it does not
// fail it.
function FallbackBlock({ details }: { details: LlmFallbackDetails }) {
  return (
    <div className="mt-2 rounded border border-warning-border/60 bg-warning/10 p-2">
      <div className="flex flex-wrap items-center gap-1.5 text-xs font-semibold text-warning">
        <AlertTriangle className="h-3.5 w-3.5" />
        Provider fallback
        {details.roleName ? (
          <span className="font-normal text-muted-foreground">role: {details.roleName}</span>
        ) : null}
        {details.statusCode !== null ? (
          <span className="font-normal text-muted-foreground">HTTP {details.statusCode}</span>
        ) : null}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-xs text-foreground">
        <span className="rounded border border-border bg-background px-1.5 py-0.5">
          {details.fromModel ?? details.fromProvider}
        </span>
        <ArrowRight className="h-3 w-3 shrink-0 text-warning" />
        {details.exhausted ? (
          <span className="rounded border border-destructive-border/60 bg-destructive/10 px-1.5 py-0.5 text-destructive">
            no remaining route
          </span>
        ) : (
          <span className="rounded border border-border bg-background px-1.5 py-0.5">
            {details.toModel ?? details.toProvider}
          </span>
        )}
      </div>
      {details.reason ? (
        <p className="mt-1.5 whitespace-pre-wrap text-xs text-muted-foreground">{details.reason}</p>
      ) : null}
    </div>
  )
}

// n4-trace #25: each prior attempt's failure reason, surfaced as an explicit
// Error Stack when retries are exhausted (retry_exhausted.final_errors) or for
// a single failed attempt (validation_fail.errors).
function ErrorStack({ failures }: { failures: string[] }) {
  return (
    <div className="mt-2 rounded border border-destructive-border/60 bg-destructive/10 p-2">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-destructive">
        <AlertOctagon className="h-3.5 w-3.5" />
        Error Stack ({failures.length})
      </div>
      <ol className="mt-1.5 space-y-1">
        {failures.map((reason, position) => (
          <li
            key={`${position}-${reason.slice(0, 24)}`}
            className="flex gap-2 rounded border border-destructive-border/60 bg-background px-2 py-1 text-xs text-destructive"
          >
            <span className="font-mono text-destructive/70">#{position + 1}</span>
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
    <div className="mt-2 rounded-md border border-border bg-muted/30 p-2 text-xs">
      <div className="flex items-center gap-1.5 font-medium text-foreground">
        <ListTree className="h-3.5 w-3.5" />
        {summary.headline}
      </div>
      {summary.args ? (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">Input</div>
          <pre className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-background/80 p-2 text-[11px] text-foreground">
            {summary.args}
          </pre>
        </div>
      ) : null}
      {summary.resultSummary ? (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">Result</div>
          <p className="mt-0.5 whitespace-pre-wrap leading-relaxed text-foreground">{summary.resultSummary}</p>
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
      <pre className="max-h-40 overflow-auto rounded-md border border-border bg-muted/30 p-3 text-xs leading-relaxed text-foreground shadow-sm">
        {body}
      </pre>
      {preview.truncated ? (
        <button
          type="button"
          onClick={(clickEvent) => {
            clickEvent.stopPropagation()
            setShowFull((open) => !open)
          }}
          className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-link hover:text-link/80"
        >
          {showFull ? 'Collapse payload' : `Show full payload (${preview.sizeLabel})`}
        </button>
      ) : null}
    </div>
  )
}
