import { AlertOctagon, AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Cpu, Hash, ListTree, Loader2, RotateCcw, TerminalSquare, Wrench } from 'lucide-react'
import { useState } from 'react'
import type { CallbackEvent } from '../../api/types'
import type { RouteDecisionDetails, TraceSeverity } from '../../utils/trace'
import {
  errorStack,
  eventColor,
  eventSeverity,
  eventMessage,
  eventMockedSource,
  eventModelName,
  eventMessageIsRedundant,
  eventPhase,
  eventTimeLabel,
  jsonText,
  routeDecisionDetails,
  mockedSourceClass,
  mockedSourceLabel,
  payloadPreview,
  retryBadge,
  tokenText,
  toolCallSummary,
} from '../../utils/trace'
import type { StepOutput } from '../../hooks/useRunDeltas'
import type { TraceStep } from '../../utils/trace-steps'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { EventTypeBadge } from './EventTypeBadge'

interface TraceStepRowProps {
  step: TraceStep
  eventId: string
  selected?: boolean
  expanded: boolean
  onToggleExpanded: () => void
  onSelectEvent?: (index: number, event: CallbackEvent) => void
  /**
   * What this step has produced so far, while it is producing it. Absent once
   * the step is done — the finished answer is on the closing event, and showing
   * both would be the same text twice from two sources that can disagree.
   */
  liveOutput?: StepOutput
}

/**
 * One step of a run: what is happening, or what happened.
 *
 * While the step runs it shows the work going in — the prompt for an LLM call,
 * the arguments for a tool call — because that is the only thing there is to
 * show yet, and showing nothing for the duration of the slowest part of a run
 * is what made the panel feel dead. When the step finishes it settles into a
 * one-line summary (decision 2026-08-09 D4). The caller owns expansion so the
 * default can follow the step's status while a deliberate toggle still sticks.
 */
export function TraceStepRow({
  step,
  eventId,
  selected = false,
  expanded,
  onToggleExpanded,
  onSelectEvent,
  liveOutput,
}: TraceStepRowProps) {
  const running = step.status === 'running'
  // Chips describe the outcome, so they read from the half that HAS one.
  const settled = step.end?.event ?? step.start.event
  const tokens = tokenText(settled)
  const mockedSource = eventMockedSource(settled)
  const retry = retryBadge(settled)
  const isError = settled.event_type === 'internal_error' || settled.event_type === 'validation_fail'
  const failures = errorStack(settled)
  const routeDecision = routeDecisionDetails(settled)
  const severity = eventSeverity(settled)
  const modelName = eventModelName(settled)
  const timeLabel = eventTimeLabel(step.start.event)

  return (
    <div className="relative pl-5">
      <div className={`absolute -left-[7px] top-2 size-3 rounded-full border-2 border-background ${eventColor(settled)}`} />
      <button
        type="button"
        data-trace-event-id={eventId}
        data-trace-step-status={step.status}
        aria-label={`Trace step ${settled.event_type} in ${eventPhase(settled)}`}
        aria-expanded={expanded}
        onClick={() => {
          onToggleExpanded()
          onSelectEvent?.(step.start.index, step.start.event)
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
            {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
            <EventTypeBadge eventType={settled.event_type} severity={severity} />
            {running ? (
              <Loader2 aria-label="Step in progress" className="h-3 w-3 animate-spin text-muted-foreground" />
            ) : null}
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
        {eventMessageIsRedundant(settled) ? null : (
          <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-foreground/80">
            {eventMessage(settled)}
          </p>
        )}
        {isError && typeof settled.error_message === 'string' ? (
          <p className="mt-2 rounded border border-destructive-border/60 bg-background px-2 py-1 text-xs text-destructive">
            {settled.error_message}
          </p>
        ) : null}
        {routeDecision ? <RouteDecisionBlock details={routeDecision} severity={severity} /> : null}
        {running && liveOutput ? <LiveOutput output={liveOutput} /> : null}
        <ToolHeadline step={step} />
        {failures.length > 0 ? <ErrorStack failures={failures} /> : null}
      </button>
      {expanded ? <StepBody step={step} /> : null}
    </div>
  )
}

/** The tool call named on the collapsed row, so a folded step still says what it did. */
function ToolHeadline({ step }: { step: TraceStep }) {
  const summary = toolCallSummary(step.end?.event ?? step.start.event)
  const startedName = typeof step.start.event.tool_name === 'string' ? step.start.event.tool_name : null
  const headline = summary?.headline ?? startedName
  if (!headline) {
    return null
  }
  return (
    <span className="mt-2 flex items-center gap-2 text-xs">
      {headline.includes('Bash') ? (
        <TerminalSquare className="h-3.5 w-3.5 text-muted-foreground" />
      ) : (
        <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
      )}
      <span className="font-medium text-foreground">{headline}</span>
      {summary?.durationLabel ? (
        <span className="text-muted-foreground">{summary.durationLabel}</span>
      ) : null}
    </span>
  )
}

function StepBody({ step }: { step: TraceStep }) {
  const opener = step.start.event
  if (opener.event_type === 'prompt_captured' || opener.event_type === 'llm_call') {
    return <PromptSections step={step} />
  }
  const summary = toolCallSummary(step.end?.event ?? opener)
  if (summary) {
    return <ToolCallSubtree summary={summary} />
  }
  if (opener.event_type === 'tool_call_started') {
    return <ToolArguments event={opener} />
  }
  return <GenericPayload event={step.end?.event ?? opener} />
}

/**
 * The prompt, where it belongs: inside the step that sent it (decision
 * 2026-08-09 D5). This used to be a separate modal reached from a link on the
 * row, which is a second home for something the step already has to show the
 * moment it opens.
 */
function PromptSections({ step }: { step: TraceStep }) {
  const prompt = step.start.event
  const answered = step.end?.event
  const rendered = jsonText(prompt.resolved_prompt)
  return (
    <div className="mt-2 space-y-2 rounded-md border border-border bg-muted/30 p-2 text-xs">
      <PromptSection label="Template">{prompt.template_source ?? 'inline'}</PromptSection>
      <PromptSection label="Variables">{jsonText(prompt.variables)}</PromptSection>
      <PromptSection label="Rendered">{rendered}</PromptSection>
      {answered ? (
        <PromptSection label="Response">{jsonText(answered.response_data ?? undefined)}</PromptSection>
      ) : null}
    </div>
  )
}

function PromptSection({ label, children }: { label: string, children: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase text-muted-foreground">{label}</div>
      <pre className="mt-0.5 whitespace-pre-wrap rounded bg-background/80 p-2 text-[11px] leading-relaxed text-foreground">
        {children}
      </pre>
    </div>
  )
}

/** What a tool was asked to do, while it is still doing it. */
function ToolArguments({ event }: { event: CallbackEvent }) {
  return (
    <div className="mt-2 rounded-md border border-border bg-muted/30 p-2 text-xs">
      <div className="text-[10px] font-semibold uppercase text-muted-foreground">Input</div>
      <pre className="mt-0.5 whitespace-pre-wrap rounded bg-background/80 p-2 text-[11px] text-foreground">
        {jsonText(event.args)}
      </pre>
    </div>
  )
}

/**
 * The answer arriving, inside the step that is producing it.
 *
 * Not a separate panel: the same text would then have two homes — a live one
 * and the finished summary on the row — and the two would disagree the moment
 * a piece is dropped (decision 2026-08-09 D6). It renders only while the step
 * runs; when the answer lands, the row settles into its own summary and this
 * goes away, so nothing is ever shown from two sources at once.
 *
 * Thinking is kept visually apart from the answer for the same reason it
 * travels on its own channel: it is the model working, not what it replied.
 */
function LiveOutput({ output }: { output: StepOutput }) {
  if (!output.text && !output.thinking) {
    return null
  }
  return (
    <div data-trace-live-output className="mt-2 space-y-1.5">
      {output.thinking ? (
        <p className="whitespace-pre-wrap rounded border border-border bg-muted/30 px-2 py-1 text-xs italic text-muted-foreground">
          {output.thinking}
        </p>
      ) : null}
      {output.text ? (
        <p className="whitespace-pre-wrap text-xs leading-snug text-foreground/90">
          {output.text}
          <span aria-hidden className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-foreground/60 align-middle" />
        </p>
      ) : null}
    </div>
  )
}

// trace-observability F7: which route the gateway used and what it decided
// about it — the endpoint and model behind the route, the provider's own status
// code, where a fall-back went, and the failure reason. Tone follows severity
// rather than the event kind, because the same event reports the route that
// answered and the run that ran out of routes.
const DECISION_TITLE: Record<RouteDecisionDetails['decision'], string> = {
  answered: 'Route used',
  skipped_circuit_open: 'Route skipped — circuit open',
  probe_failed: 'Probe failed',
  retried_same_route: 'Retried same route',
  retried_without_rejected_settings: 'Runtime settings refused — retried without them',
  escalated_budget: 'Token budget raised',
  fell_back: 'Provider fallback',
  failed_terminal: 'Route failed — no fallback',
  exhausted: 'All routes exhausted',
}

const DECISION_TONE: Record<TraceSeverity, { box: string; title: string; arrow: string }> = {
  error: {
    box: 'border-destructive-border/60 bg-destructive/10',
    title: 'text-destructive',
    arrow: 'text-destructive',
  },
  warning: {
    box: 'border-warning-border/60 bg-warning/10',
    title: 'text-warning',
    arrow: 'text-warning',
  },
  normal: {
    box: 'border-border bg-muted/40',
    title: 'text-muted-foreground',
    arrow: 'text-muted-foreground',
  },
}

function RouteDecisionBlock({
  details,
  severity,
}: {
  details: RouteDecisionDetails
  severity: TraceSeverity
}) {
  const tone = DECISION_TONE[severity]
  return (
    <div className={`mt-2 rounded border p-2 ${tone.box}`}>
      <div className={`flex flex-wrap items-center gap-1.5 text-xs font-semibold ${tone.title}`}>
        {severity === 'normal' ? <Cpu className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
        {DECISION_TITLE[details.decision]}
        {details.endpointId ? (
          <span className="font-normal text-muted-foreground">endpoint: {details.endpointId}</span>
        ) : null}
        {details.protocol ? (
          <span className="font-normal text-muted-foreground">{details.protocol}</span>
        ) : null}
        {details.statusCode !== null ? (
          <span className="font-normal text-muted-foreground">HTTP {details.statusCode}</span>
        ) : null}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-xs text-foreground">
        <span className="rounded border border-border bg-background px-1.5 py-0.5">
          {details.providerModelId ?? details.routeId ?? 'unknown route'}
        </span>
        {details.decision === 'fell_back' ? (
          <>
            <ArrowRight className={`h-3 w-3 shrink-0 ${tone.arrow}`} />
            <span className="rounded border border-border bg-background px-1.5 py-0.5">
              {details.nextRouteId ?? 'unknown route'}
            </span>
          </>
        ) : null}
        {details.decision === 'exhausted' ? (
          <>
            <ArrowRight className={`h-3 w-3 shrink-0 ${tone.arrow}`} />
            <span className="rounded border border-destructive-border/60 bg-destructive/10 px-1.5 py-0.5 text-destructive">
              no remaining route
            </span>
          </>
        ) : null}
      </div>
      {/* The panel is showing text this decision just threw away; leaving that
          unsaid lets the reader keep reading an answer that no longer counts. */}
      {details.voidedStreamedAnswer ? (
        <p className="mt-1.5 text-xs font-medium text-warning">
          Discarded the partial answer already shown above.
        </p>
      ) : null}
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

// n4-trace #16/#24: the verb-classified call with its args (input) and result
// (output), so the agent is not a black box and nobody has to read raw JSON.
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
          {/* No height cap and no inner scrollbar: the panel already scrolls, and
              a scroller inside a scroller is a worse way to read a long value
              than a fold the reader controls (decision 2026-08-09 D6). */}
          <pre className="mt-0.5 whitespace-pre-wrap rounded bg-background/80 p-2 text-[11px] text-foreground">
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

function GenericPayload({ event }: { event: CallbackEvent }) {
  // §4: long payloads default to a collapsed ~2KB head; only the user opts in to
  // the full dump so a multi-megabyte trace event never floods (or OOMs) the panel.
  const [showFull, setShowFull] = useState(false)
  const preview = payloadPreview(event)
  const body = showFull ? JSON.stringify(event, null, 2) : preview.text
  return (
    <div className="mt-2">
      <pre className="rounded-md border border-border bg-muted/30 p-3 text-xs leading-relaxed whitespace-pre-wrap text-foreground shadow-sm">
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
