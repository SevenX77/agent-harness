import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Cpu, FileText, Hash, ListTree, Loader2, TerminalSquare, Wrench } from 'lucide-react'
import type { CallbackEvent } from '../../api/types'
import type {
  CallSettingsDetails,
  EventFact,
  RouteDecisionDetails,
  TraceSeverity,
} from '../../utils/trace'
import {
  answerContent,
  answerReasoning,
  answerToolCallsText,
  eventColor,
  eventSeverity,
  eventHeadline,
  eventMockedSource,
  eventModelName,
  eventPhase,
  eventTimeLabel,
  jsonText,
  callSettingsDetails,
  eventFacts,
  machineryNarration,
  promptMessages,
  maxSeverity,
  routeDecisionDetails,
  mockedSourceClass,
  tokenText,
  toolCallSummary,
} from '../../utils/trace'
import type { StepOutput } from '../../hooks/useRunDeltas'
import type { TraceStep } from '../../utils/trace-steps'
import { EventTypeBadge } from './EventTypeBadge'
import { TraceText } from './TraceText'
import { TraceMark } from './trace-mark-term'
import {
  factLabelText,
  factValueText,
  toolCallHeadline,
  toolDurationText,
  traceHeadlineText,
  useTraceCopy,
  type TraceCopy,
} from './trace-copy'
import { useOptionalWorkspaceContext } from '../studio/WorkspaceContext'

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
  const t = useTraceCopy()
  const running = step.status === 'running'
  const severed = step.status === 'severed'
  // Chips describe the outcome, so they read from the half that HAS one.
  const settled = step.end?.event ?? step.start.event
  const tokens = tokenText(settled)
  const mockedSource = eventMockedSource(settled)
  // Whether the row itself reads as a failure is decided by the ONE authority
  // that decides it everywhere (eventSeverity), not by a second list of type
  // names kept here — the rail dot beside this row reads the same answer
  // through eventColor, so the two can never disagree about one event.
  const ownSeverity = eventSeverity(settled)
  // A warning buried in an attached verdict must still tint the collapsed row.
  const severity = maxSeverity([
    ownSeverity,
    ...step.verdicts.map(({ event }) => eventSeverity(event)),
  ])
  const modelName = eventModelName(settled)
  const timeLabel = eventTimeLabel(step.start.event)
  // A STANDALONE gateway verdict row (one that could not be attributed to an
  // open LLM step) is its own block — the verdict is the row's whole content.
  const ownRouteDecision = routeDecisionDetails(settled)
  const ownCallSettings = callSettingsDetails(settled)
  const headline = traceHeadlineText(eventHeadline(settled), t)

  return (
    <div className="relative pl-5">
      <div className={`absolute -left-[7px] top-2 size-3 rounded-full border-2 border-background ${eventColor(settled)}`} />
      <button
        type="button"
        data-trace-event-id={eventId}
        data-trace-step-status={step.status}
        aria-label={t('step.aria', { eventType: settled.event_type, phase: eventPhase(settled) })}
        aria-expanded={expanded}
        onClick={() => {
          onToggleExpanded()
          onSelectEvent?.(step.start.index, step.start.event)
        }}
        className={`block w-full rounded-md border-0 px-2.5 py-1.5 text-left transition-colors ${
          selected
            ? 'bg-accent'
            : ownSeverity === 'error'
              ? 'bg-destructive/10 hover:bg-destructive/15'
              : 'hover:bg-accent/50'
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2">
            {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
            <EventTypeBadge eventType={settled.event_type} severity={severity} />
            {running ? (
              <Loader2 aria-label={t('step.inProgress')} className="h-3 w-3 animate-spin text-muted-foreground" />
            ) : null}
            {severed ? (
              <span
                aria-label={t('step.severedAria')}
                className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
              >
                {t('step.severed')}
              </span>
            ) : null}
            {timeLabel ? (
              <span data-trace-time className="font-mono text-[10px] text-muted-foreground/80">{timeLabel}</span>
            ) : null}
          </span>
          {tokens ? (
            <span className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
              <Hash className="h-3 w-3" />
              <TraceMark text={tokens} />
            </span>
          ) : null}
          {modelName ? (
            <span
              data-trace-model-chip
              title={t('step.model', { model: modelName })}
              className="flex max-w-[180px] items-center gap-1 rounded-full border border-border bg-muted/40 px-2 py-0.5 font-mono text-xs text-muted-foreground"
            >
              <Cpu className="h-3 w-3 shrink-0" />
              <span className="truncate"><TraceMark text={modelName} /></span>
            </span>
          ) : null}
          {mockedSource ? (
            <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${mockedSourceClass(mockedSource)}`}>
              {t(`mocked.${mockedSource}`)}
            </span>
          ) : null}
        </div>
        {headline === '' ? null : (
          <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-foreground/80">
            <TraceMark text={headline} />
          </p>
        )}
        {ownRouteDecision ? <RouteDecisionBlock details={ownRouteDecision} severity={severity} /> : null}
        {ownCallSettings ? <CallSettingsBlock details={ownCallSettings} severity={severity} /> : null}
        {/* Collapsed rows keep only verdicts that went WRONG in sight; the
            healthy ones read in flow order inside the expanded body (D1). */}
        {expanded ? null : <VerdictBlocks verdicts={step.verdicts} onlyProblems />}
        <ToolHeadline step={step} />
      </button>
      {/* Outside the row button: these carry their own interactive fold
          controls, and a button inside a button is not a thing.

          The arriving answer belongs INSIDE the step's flow when the step is
          open (design D1: 装载 prompt → 渲染后 prompt → 思考 → 回答), so the
          expanded body owns it and this standalone copy is what a COLLAPSED
          row shows — one slot each, never both. */}
      {expanded
        ? <StepBody step={step} liveOutput={running ? liveOutput : undefined} />
        : running && liveOutput ? <LiveOutput output={liveOutput} /> : null}
    </div>
  )
}

/** The tool call named on the collapsed row, so a folded step still says what it did. */
function ToolHeadline({ step }: { step: TraceStep }) {
  const t = useTraceCopy()
  const summary = toolCallSummary(step.end?.event ?? step.start.event)
  const startedName = typeof step.start.event.tool_name === 'string' ? step.start.event.tool_name : null
  const toolName = summary?.toolName ?? startedName
  if (!toolName) {
    return null
  }
  // A folded row that has only the OPENING event has no classified summary yet;
  // the tool's own name is all there is to say, and saying it is better than
  // saying nothing until the call closes.
  const headline = summary ? toolCallHeadline(summary, t) : toolName
  const duration = summary ? toolDurationText(summary, t) : null
  return (
    <span className="mt-2 flex items-center gap-2 text-xs">
      {toolName.includes('Bash') ? (
        <TerminalSquare className="h-3.5 w-3.5 text-muted-foreground" />
      ) : (
        <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
      )}
      <span className="font-medium text-foreground"><TraceMark text={headline} /></span>
      {duration ? (
        <span className="text-muted-foreground">{duration}</span>
      ) : null}
    </span>
  )
}

function StepBody({ step, liveOutput }: { step: TraceStep; liveOutput?: StepOutput }) {
  const opener = step.start.event
  if (opener.event_type === 'prompt_captured' || opener.event_type === 'llm_call') {
    return <LlmFlowBody step={step} liveOutput={liveOutput} />
  }
  const summary = toolCallSummary(step.end?.event ?? opener)
  if (summary) {
    return <ToolCallSubtree summary={summary} />
  }
  if (opener.event_type === 'tool_call_started') {
    return <ToolArguments event={opener} />
  }
  // Everything else is machinery, and machinery says what it decided (D4) and
  // shows what it turned on. A type with NO reading is a gap in this build, not
  // a quiet step — it says so out loud rather than printing itself as JSON and
  // letting that pass for a rendering.
  const settled = step.end?.event ?? opener
  const narration = machineryNarration(settled)
  const facts = eventFacts(settled)
  if (facts === null) {
    return <UnreadEventBody event={settled} />
  }
  return <MachineryBody narration={narration} facts={facts} />
}

/**
 * The expanded LLM step, as the sequence it actually was (decision 2026-08-13
 * D1): loading the author's phase → wrapping it in the engine template →
 * filling in the variables → what was sent → the model thinking → what it
 * answered or which tools it reached for → the gateway's verdicts about the
 * call. The TEMPLATE / VARIABLES / RENDERED / Response containers this replaces
 * arranged the same data by KIND, which is an order no execution ever ran in.
 */
function LlmFlowBody({ step, liveOutput }: { step: TraceStep; liveOutput?: StepOutput }) {
  const t = useTraceCopy()
  const prompt = step.start.event
  const answered = step.end?.event
  const variables = jsonText(prompt.variables)
  const hasVariables = variables !== '' && variables !== '{}'
  // While the call is still open the same two slots carry what has arrived so
  // far. Never both: once the settled event lands it is the authority, and
  // keeping the streamed copy beside it would show one answer twice from two
  // sources that disagree after a dropped piece.
  const reasoning = answerReasoning(answered) || liveOutput?.thinking || ''
  const answer = answerContent(answered) || liveOutput?.text || ''
  const toolCalls = answerToolCallsText(answered)
  const bareResponse = answered && !reasoning && !answer && !toolCalls
  return (
    <div className="mt-2 space-y-2 text-xs">
      <PromptOrigin event={prompt} />
      {hasVariables ? (
        <FlowEntry title={t('flow.filledIn')}>
          <TraceText text={variables} label={t('text.promptVariables')} language="json" />
        </FlowEntry>
      ) : null}
      {promptMessages(prompt).map((message, position) => (
        <FlowEntry key={`sent-${position}`} title={t('flow.sent', { role: message.role })}>
          <TraceText text={message.text} label={t('text.roleMessage', { role: message.role })} />
        </FlowEntry>
      ))}
      {reasoning ? (
        <FlowEntry title={t('flow.thinking')}>
          <TraceText text={reasoning} label={t('text.thinking')} className="italic text-muted-foreground" />
        </FlowEntry>
      ) : null}
      {answer ? (
        <FlowEntry title={t('flow.answer')}>
          <TraceText text={answer} label={t('text.answer')} />
        </FlowEntry>
      ) : null}
      {toolCalls ? (
        <FlowEntry title={t('flow.toolCalls')}>
          <TraceText text={toolCalls} label={t('text.toolCalls')} language="json" />
        </FlowEntry>
      ) : null}
      {/* A response none of the semantic entries could claim still gets shown —
          decomposing the answer must never become a way of hiding it. */}
      {bareResponse ? (
        <FlowEntry title={t('flow.response')}>
          <TraceText text={jsonText(answered.response_data ?? undefined)} label={t('text.response')} language="json" />
        </FlowEntry>
      ) : null}
      <VerdictBlocks verdicts={step.verdicts} />
    </div>
  )
}

/**
 * The two acts that happen before anything is substituted: the author's phase
 * document is loaded, then the engine wraps it in the cognitive template.
 * Both are steps in the stream, in the order the engine performs them — not a
 * TEMPLATE container, which decision 2026-08-13 D1 abolished for arranging
 * data by kind instead of by time.
 *
 * The two halves travel differently on purpose. The author's document is a
 * FILE in the workspace, so it is offered as a link that opens the real thing
 * — a copy pasted into the trace would drift from what the editor shows. The
 * engine's template is not a file anywhere (`V030_COGNITIVE_TEMPLATE_ID`
 * names a constant, not a path), so it can only travel as text.
 *
 * Together they answer the question the template id alone could not: which
 * words in this prompt are the engine's, and which are the author's.
 */
function PromptOrigin({ event }: { event: CallbackEvent }) {
  const t = useTraceCopy()
  const onFileOpen = useOptionalWorkspaceContext()?.onFileOpen
  const sourcePath = typeof event.phase_source_path === 'string' ? event.phase_source_path : ''
  const templateText = typeof event.template_text === 'string' ? event.template_text : ''
  const templateSource = typeof event.template_source === 'string' && event.template_source !== ''
    ? event.template_source
    : 'inline'
  return (
    <>
      {sourcePath ? (
        <FlowEntry title={t('flow.loaded', { path: sourcePath })}>
          {onFileOpen ? (
            <button
              type="button"
              data-trace-prompt-source={sourcePath}
              onClick={() => { onFileOpen({ path: sourcePath, saveEnabled: true }) }}
              className="inline-flex items-center gap-1 font-mono text-xs text-link hover:text-link/80"
            >
              <FileText className="h-3 w-3" />
              {t('step.openPhase')}
            </button>
          ) : null}
        </FlowEntry>
      ) : null}
      <FlowEntry title={t('flow.wrapped', { source: templateSource })}>
        {templateText ? (
          <TraceText text={templateText} label={t('text.promptTemplate')} />
        ) : null}
      </FlowEntry>
    </>
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
      {shown.map(({ event, index, occurrence }) => {
        const route = routeDecisionDetails(event)
        if (route) {
          // The reason was already given the first time this exact degradation
          // appeared. Repeating the whole block on every subsequent call turned
          // one dead endpoint into a wall of identical warnings.
          return occurrence > 1
            ? <RouteDecisionRepeat key={`verdict-${index}`} details={route} occurrence={occurrence} severity={eventSeverity(event)} />
            : <RouteDecisionBlock key={`verdict-${index}`} details={route} severity={eventSeverity(event)} />
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
  const t = useTraceCopy()
  return (
    <div className="mt-2 text-xs">
      <div className="text-[10px] font-semibold uppercase text-muted-foreground">{t('step.input')}</div>
      <div className="mt-0.5">
        <TraceText text={jsonText(event.args)} label={t('text.toolInput')} language="json" />
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
  const t = useTraceCopy()
  if (!output.text && !output.thinking) {
    return null
  }
  return (
    <div data-trace-live-output className="mt-2 space-y-1.5 px-2.5">
      {output.thinking ? (
        <TraceText
          text={output.thinking}
          label={t('text.liveThinking')}
          autoFollow
          className="italic text-muted-foreground"
        />
      ) : null}
      {output.text ? (
        <TraceText
          text={output.text}
          label={t('text.liveAnswer')}
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

function decisionTitle(details: RouteDecisionDetails, t: TraceCopy): string {
  return t(`decision.${details.decision}`)
}

/**
 * A degradation the reader has already had explained: this call hit it too.
 *
 * One line, no reason, no route table — the full block for this exact
 * complaint is further up the trace. What the repeat still has to say is that
 * THIS call fell back as well, which is a fact about this call.
 */
function RouteDecisionRepeat({
  details,
  occurrence,
  severity,
}: {
  details: RouteDecisionDetails
  occurrence: number
  severity: TraceSeverity
}) {
  const t = useTraceCopy()
  const tone = DECISION_TONE[severity]
  return (
    <div
      data-trace-route-repeat={occurrence}
      className={`mt-2 flex flex-wrap items-center gap-1.5 rounded border px-2 py-1 text-xs ${tone.box}`}
    >
      <AlertTriangle className={`h-3.5 w-3.5 shrink-0 ${tone.title}`} />
      <span className={tone.title}>{t('route.again', { title: decisionTitle(details, t) })}</span>
      {details.endpointId ? (
        <span className="text-muted-foreground">{t('route.endpoint', { id: details.endpointId })}</span>
      ) : null}
      <span className="text-muted-foreground">{t('route.repeats', { count: occurrence })}</span>
    </div>
  )
}

function RouteDecisionBlock({
  details,
  severity,
}: {
  details: RouteDecisionDetails
  severity: TraceSeverity
}) {
  const t = useTraceCopy()
  const tone = DECISION_TONE[severity]
  return (
    <div className={`mt-2 rounded border p-2 ${tone.box}`}>
      <div className={`flex flex-wrap items-center gap-1.5 text-xs font-semibold ${tone.title}`}>
        {severity === 'normal' ? <Cpu className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
        {decisionTitle(details, t)}
        {details.endpointId ? (
          <span className="font-normal text-muted-foreground">{t('route.endpoint', { id: details.endpointId })}</span>
        ) : null}
        {details.protocol ? (
          <span className="font-normal text-muted-foreground"><TraceMark text={details.protocol} /></span>
        ) : null}
        {details.statusCode !== null ? (
          <span className="font-normal text-muted-foreground">{t('route.http', { status: details.statusCode })}</span>
        ) : null}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-xs text-foreground">
        <span className="rounded border border-border bg-background px-1.5 py-0.5">
          <TraceMark text={details.providerModelId ?? details.routeId ?? t('route.unknown')} />
        </span>
        {details.decision === 'fell_back' ? (
          <>
            <ArrowRight className={`h-3 w-3 shrink-0 ${tone.arrow}`} />
            <span className="rounded border border-border bg-background px-1.5 py-0.5">
              <TraceMark text={details.nextRouteId ?? t('route.unknown')} />
            </span>
          </>
        ) : null}
        {details.decision === 'exhausted' ? (
          <>
            <ArrowRight className={`h-3 w-3 shrink-0 ${tone.arrow}`} />
            <span className="rounded border border-destructive-border/60 bg-destructive/10 px-1.5 py-0.5 text-destructive">
              {t('route.noRemaining')}
            </span>
          </>
        ) : null}
      </div>
      {/* The panel is showing text this decision just threw away; leaving that
          unsaid lets the reader keep reading an answer that no longer counts. */}
      {details.voidedStreamedAnswer ? (
        <p className="mt-1.5 text-xs font-medium text-warning">
          {t('route.discarded')}
        </p>
      ) : null}
      {details.reason ? (
        <p className="mt-1.5 whitespace-pre-wrap text-xs text-muted-foreground"><TraceMark text={details.reason} /></p>
      ) : null}
    </div>
  )
}

// n4-trace #16/#24: the verb-classified call with its args (input) and result
// (output), so the agent is not a black box and nobody has to read raw JSON.
function ToolCallSubtree({ summary }: { summary: NonNullable<ReturnType<typeof toolCallSummary>> }) {
  const t = useTraceCopy()
  return (
    <div className="mt-2 text-xs">
      <div className="flex items-center gap-1.5 font-medium text-foreground">
        <ListTree className="h-3.5 w-3.5" />
        {toolCallHeadline(summary, t)}
      </div>
      {summary.args ? (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">{t('step.input')}</div>
          <div className="mt-0.5">
            <TraceText text={summary.args} label={t('text.toolInput')} language="json" />
          </div>
        </div>
      ) : null}
      {summary.resultSummary ? (
        <div className="mt-1.5">
          <div className="text-[10px] font-semibold uppercase text-muted-foreground">{t('step.result')}</div>
          <div className="mt-0.5">
            <TraceText text={summary.resultSummary} label={t('text.toolResult')} />
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
function MachineryBody({
  narration,
  facts,
}: {
  narration: ReturnType<typeof machineryNarration>
  facts: EventFact[]
}) {
  const t = useTraceCopy()
  if (narration === null && facts.length === 0) {
    return null
  }
  return (
    <div className="mt-2 space-y-1.5 rounded-md border border-border bg-muted/30 p-2 text-xs">
      {facts.length > 0 ? (
        <dl data-trace-facts className="flex flex-wrap gap-x-4 gap-y-1">
          {facts.map((item) => {
            const value = factValueText(item.value, t)
            return (
              <div key={item.label} className="flex min-w-0 items-baseline gap-1.5">
                <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">{factLabelText(item, t)}</dt>
                <dd className="min-w-0 truncate font-mono text-foreground" title={value}><TraceMark text={value} /></dd>
              </div>
            )
          })}
        </dl>
      ) : null}
      {narration !== null && narration.details.length > 0 ? (
        <ol className="space-y-1">
          {narration.details.map((line, position) => (
            <li key={`detail-${position}`} className="flex gap-2 text-foreground/90">
              <span className="font-mono text-muted-foreground">{position + 1}.</span>
              <span className="whitespace-pre-wrap"><TraceMark text={line} /></span>
            </li>
          ))}
        </ol>
      ) : null}
      {narration !== null && narration.problems.length > 0 ? (
        <ol className="space-y-1">
          {narration.problems.map((reason, position) => (
            <li
              key={`problem-${position}`}
              className="flex gap-2 rounded border border-destructive-border/60 bg-background px-2 py-1 text-destructive"
            >
              <span className="font-mono text-destructive/70">#{position + 1}</span>
              <span className="whitespace-pre-wrap"><TraceMark text={reason} /></span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  )
}

/**
 * An event this build cannot read.
 *
 * The old behaviour was to print the whole event as JSON, which LOOKS like a
 * rendering — so a new engine event could ship and silently turn a step back
 * into a black box, which is the state the glass-box decision set out to end.
 * Naming the gap is the point: the payload is still here so the reader is not
 * stuck, but nobody mistakes it for a reading.
 */
function UnreadEventBody({ event }: { event: CallbackEvent }) {
  const t = useTraceCopy()
  return (
    <div data-trace-unread-event={event.event_type} className="mt-2 space-y-1.5">
      <p className="flex items-center gap-1.5 rounded border border-warning-border bg-warning-background px-2 py-1 text-xs text-warning-foreground">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        {t('step.unread', { eventType: event.event_type })}
      </p>
      <TraceText text={jsonText(event as never)} label={t('text.eventPayload')} language="json" />
    </div>
  )
}

function CallSettingsBlock({
  details,
  severity,
}: {
  details: CallSettingsDetails
  severity: TraceSeverity
}) {
  const t = useTraceCopy()
  if (details.settings.length === 0) {
    return null
  }
  const tone = DECISION_TONE[severity]
  return (
    <div className={`mt-2 rounded border p-2 ${tone.box}`}>
      <div className={`flex flex-wrap items-center gap-1.5 text-xs font-semibold ${tone.title}`}>
        {severity === 'normal' ? <Cpu className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
        {t('settings.title')}
        {details.providerModelId ? (
          <span className="font-normal text-muted-foreground"><TraceMark text={details.providerModelId} /></span>
        ) : null}
      </div>
      <ul className="mt-1.5 space-y-1">
        {details.settings.map((outcome) => (
          <li
            key={outcome.setting}
            className="flex flex-wrap items-center gap-1.5 font-mono text-xs text-foreground"
          >
            <span className="text-muted-foreground"><TraceMark text={outcome.setting} /></span>
            <span className="rounded border border-border bg-background px-1.5 py-0.5">
              <TraceMark text={outcome.requested === null ? '—' : String(outcome.requested)} />
            </span>
            <ArrowRight className={`h-3 w-3 shrink-0 ${tone.arrow}`} />
            {/* A setting that did not run as asked is the whole reason this
                block exists, so it says the verdict in words rather than
                colouring the row and hoping. */}
            <span className="rounded border border-border bg-background px-1.5 py-0.5">
              {t(`settings.${outcome.verdict}`)}
            </span>
            {outcome.reason ? (
              <span className="font-sans text-muted-foreground"><TraceMark text={outcome.reason} /></span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
