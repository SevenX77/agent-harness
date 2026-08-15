import { AlertOctagon, AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Cpu, Hash, ListTree, Loader2, RotateCcw, TerminalSquare, Wrench } from 'lucide-react'
import type { CallbackEvent } from '../../api/types'
import type {
  CallSettingsDetails,
  RouteDecisionDetails,
  SettingVerdict,
  TraceSeverity,
} from '../../utils/trace'
import {
  answerContent,
  answerReasoning,
  answerToolCallsText,
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
  callSettingsDetails,
  machineryNarration,
  maxSeverity,
  routeDecisionDetails,
  mockedSourceClass,
  mockedSourceLabel,
  retryBadge,
  tokenText,
  toolCallSummary,
} from '../../utils/trace'
import type { StepOutput } from '../../hooks/useRunDeltas'
import type { TraceStep } from '../../utils/trace-steps'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { EventTypeBadge } from './EventTypeBadge'
import { TraceText } from './TraceText'

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
 *
 * Every long text in this file goes through the ONE well primitive
 * (`TraceText` over `ui/text-well`, decision 2026-08-14) — no section decides
 * its own fold, and no section wraps the well in a second box.
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
  const severed = step.status === 'severed'
  // Chips describe the outcome, so they read from the half that HAS one.
  const settled = step.end?.event ?? step.start.event
  const tokens = tokenText(settled)
  const mockedSource = eventMockedSource(settled)
  const retry = retryBadge(settled)
  const isError = settled.event_type === 'internal_error' || settled.event_type === 'validation_fail'
  const failures = errorStack(settled)
  // A warning buried in an attached verdict must still tint the collapsed row.
  const severity = maxSeverity([
    eventSeverity(settled),
    ...step.verdicts.map(({ event }) => eventSeverity(event)),
  ])
  const modelName = eventModelName(settled)
  const timeLabel = eventTimeLabel(step.start.event)
  // A STANDALONE gateway verdict row (one that could not be attributed to an
  // open LLM step) is its own block — the verdict is the row's whole content.
  const ownRouteDecision = routeDecisionDetails(settled)
  const ownCallSettings = callSettingsDetails(settled)

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
            {severed ? (
              <span
                aria-label="Step never completed — the run ended first"
                className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
              >
                never completed
              </span>
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
        {ownRouteDecision ? <RouteDecisionBlock details={ownRouteDecision} severity={severity} /> : null}
        {ownCallSettings ? <CallSettingsBlock details={ownCallSettings} severity={severity} /> : null}
        {/* Collapsed rows keep only verdicts that went WRONG in sight; the
            healthy ones read in flow order inside the expanded body (D1). */}
        {expanded ? null : <VerdictBlocks verdicts={step.verdicts} onlyProblems />}
        <ToolHeadline step={step} />
        {failures.length > 0 ? <ErrorStack failures={failures} /> : null}
      </button>
      {/* Outside the row button: these carry their own interactive fold
          controls, and a button inside a button is not a thing. */}
      {running && liveOutput ? <LiveOutput output={liveOutput} /> : null}
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
    return <LlmFlowBody step={step} />
  }
  const summary = toolCallSummary(step.end?.event ?? opener)
  if (summary) {
    return <ToolCallSubtree summary={summary} />
  }
  if (opener.event_type === 'tool_call_started') {
    return <ToolArguments event={opener} />
  }
  const narration = machineryNarration(step.end?.event ?? opener)
  if (narration) {
    return <MachineryBody narration={narration} />
  }
  return <GenericPayload event={step.end?.event ?? opener} />
}

/**
 * The expanded LLM step, as the sequence it actually was (decision 2026-08-13
 * D1): loading the prompt → the rendered prompt → the model thinking → what it
 * answered or which tools it reached for → the gateway's verdicts about the
 * call. The TEMPLATE / VARIABLES / RENDERED / Response containers this replaces
 * arranged the same data by KIND, which is an order no execution ever ran in.
 */
function LlmFlowBody({ step }: { step: TraceStep }) {
  const prompt = step.start.event
  const answered = step.end?.event
  const variables = jsonText(prompt.variables)
  const hasVariables = variables !== '' && variables !== '{}'
  const reasoning = answerReasoning(answered)
  const answer = answerContent(answered)
  const toolCalls = answerToolCallsText(answered)
  const bareResponse = answered && !reasoning && !answer && !toolCalls
  return (
    <div className="mt-2 space-y-2 text-xs">
      <FlowEntry title={`Prompt loaded — ${typeof prompt.template_source === 'string' && prompt.template_source !== '' ? prompt.template_source : 'inline'}`}>
        {hasVariables ? (
          <TraceText text={variables} label="Prompt variables" language="json" />
        ) : null}
      </FlowEntry>
      <FlowEntry title="Rendered prompt">
        <TraceText text={jsonText(prompt.resolved_prompt)} label="Rendered prompt" language="json" />
      </FlowEntry>
      {reasoning ? (
        <FlowEntry title="Thinking">
          <TraceText text={reasoning} label="Thinking" className="italic text-muted-foreground" />
        </FlowEntry>
      ) : null}
      {answer ? (
        <FlowEntry title="Answer">
          <TraceText text={answer} label="Answer" />
        </FlowEntry>
      ) : null}
      {toolCalls ? (
        <FlowEntry title="Tool calls">
          <TraceText text={toolCalls} label="Tool calls" language="json" />
        </FlowEntry>
      ) : null}
      {/* A response none of the semantic entries could claim still gets shown —
          decomposing the answer must never become a way of hiding it. */}
      {bareResponse ? (
        <FlowEntry title="Response">
          <TraceText text={jsonText(answered.response_data ?? undefined)} label="Response" language="json" />
        </FlowEntry>
      ) : null}
      <VerdictBlocks verdicts={step.verdicts} />
    </div>
  )
}

function FlowEntry({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div data-trace-flow-entry>
      <div className="text-[10px] font-semibold uppercase text-muted-foreground">{title}</div>
      {children ? <div className="mt-0.5">{children}</div> : null}
    </div>
  )
}

/**
 * The gateway's verdicts about a call, rendered where the reader is
 * (`onlyProblems` on the collapsed row keeps trouble visible without opening).
 */
function VerdictBlocks({ verdicts, onlyProblems = false }: { verdicts: TraceStep['verdicts']; onlyProblems?: boolean }) {
  const shown = verdicts.filter(({ event }) => !onlyProblems || eventSeverity(event) !== 'normal')
  if (shown.length === 0) {
    return null
  }
  return (
    <>
      {shown.map(({ event, index }) => {
        const route = routeDecisionDetails(event)
        if (route) {
          return <RouteDecisionBlock key={`verdict-${index}`} details={route} severity={eventSeverity(event)} />
        }
        const settings = callSettingsDetails(event)
        if (settings) {
          return <CallSettingsBlock key={`verdict-${index}`} details={settings} severity={eventSeverity(event)} />
        }
        return null
      })}
    </>
  )
}

/** What a tool was asked to do, while it is still doing it. */
function ToolArguments({ event }: { event: CallbackEvent }) {
  return (
    <div className="mt-2 text-xs">
      <div className="text-[10px] font-semibold uppercase text-muted-foreground">Input</div>
      <div className="mt-0.5">
        <TraceText text={jsonText(event.args)} label="Tool input" language="json" />
      </div>
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
 * Both wells auto-follow: live text keeps the line arriving in view.
 */
function LiveOutput({ output }: { output: StepOutput }) {
  if (!output.text && !output.thinking) {
    return null
  }
  return (
    <div data-trace-live-output className="mt-2 space-y-1.5 px-2.5">
      {output.thinking ? (
        <TraceText
          text={output.thinking}
          label="Live thinking"
          autoFollow
          className="italic text-muted-foreground"
        />
      ) : null}
      {output.text ? (
        <TraceText
          text={output.text}
          label="Live answer"
          autoFollow
          className="text-foreground/90"
        />
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
  dropped_rejected_settings: 'Runtime settings refused — running without them',
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
    <div className="mt-2 text-xs">
      <div className="flex items-center gap-1.5 font-medium text-foreground">
        <ListTree className="h-3.5 w-3.5" />
        {summary.headline}
      </div>
      {summary.args ? (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">Input</div>
          <div className="mt-0.5">
            <TraceText text={summary.args} label="Tool input" language="json" />
          </div>
        </div>
      ) : null}
      {summary.resultSummary ? (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">Result</div>
          <div className="mt-0.5">
            <TraceText text={summary.resultSummary} label="Tool result" />
          </div>
        </div>
      ) : null}
    </div>
  )
}

/**
 * A machinery event's own account of itself (decision 2026-08-13 D4): the
 * pipeline narration it carried in `details`, and the reasons in
 * `errors` / `violations` when the decision went against the submission.
 */
function MachineryBody({ narration }: { narration: NonNullable<ReturnType<typeof machineryNarration>> }) {
  return (
    <div className="mt-2 space-y-1.5 rounded-md border border-border bg-muted/30 p-2 text-xs">
      {narration.details.length > 0 ? (
        <ol className="space-y-1">
          {narration.details.map((line, position) => (
            <li key={`detail-${position}`} className="flex gap-2 text-foreground/90">
              <span className="font-mono text-muted-foreground">{position + 1}.</span>
              <span className="whitespace-pre-wrap">{line}</span>
            </li>
          ))}
        </ol>
      ) : null}
      {narration.problems.length > 0 ? (
        <ol className="space-y-1">
          {narration.problems.map((reason, position) => (
            <li
              key={`problem-${position}`}
              className="flex gap-2 rounded border border-destructive-border/60 bg-background px-2 py-1 text-destructive"
            >
              <span className="font-mono text-destructive/70">#{position + 1}</span>
              <span className="whitespace-pre-wrap">{reason}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  )
}

function GenericPayload({ event }: { event: CallbackEvent }) {
  return (
    <div className="mt-2">
      <TraceText text={jsonText(event as never)} label="Event payload" language="json" />
    </div>
  )
}

// A setting that did not run as asked is the whole reason this block exists, so
// it says the verdict in words rather than colouring the row and hoping.
const VERDICT_LABEL: Record<SettingVerdict, string> = {
  applied: 'applied',
  sent: 'sent',
  adjusted: 'adjusted to fit',
  unsupported: 'not supported here',
  rejected: 'refused',
  ignored: 'ignored',
}

function CallSettingsBlock({
  details,
  severity,
}: {
  details: CallSettingsDetails
  severity: TraceSeverity
}) {
  if (details.settings.length === 0) {
    return null
  }
  const tone = DECISION_TONE[severity]
  return (
    <div className={`mt-2 rounded border p-2 ${tone.box}`}>
      <div className={`flex flex-wrap items-center gap-1.5 text-xs font-semibold ${tone.title}`}>
        {severity === 'normal' ? <Cpu className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
        Runtime settings
        {details.providerModelId ? (
          <span className="font-normal text-muted-foreground">{details.providerModelId}</span>
        ) : null}
      </div>
      <ul className="mt-1.5 space-y-1">
        {details.settings.map((outcome) => (
          <li
            key={outcome.setting}
            className="flex flex-wrap items-center gap-1.5 font-mono text-xs text-foreground"
          >
            <span className="text-muted-foreground">{outcome.setting}</span>
            <span className="rounded border border-border bg-background px-1.5 py-0.5">
              {outcome.requested === null ? '—' : String(outcome.requested)}
            </span>
            <ArrowRight className={`h-3 w-3 shrink-0 ${tone.arrow}`} />
            <span className="rounded border border-border bg-background px-1.5 py-0.5">
              {VERDICT_LABEL[outcome.verdict]}
            </span>
            {outcome.reason ? (
              <span className="font-sans text-muted-foreground">{outcome.reason}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
