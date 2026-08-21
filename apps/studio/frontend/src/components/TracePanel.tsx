import type { CallbackEvent, EventEnvelope, RunMetadata } from '../api/types'
import type { GoldenNodeState } from './studio/node-golden'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { countRouteDegradations, isPredictTrace } from '../utils/trace'
import { runVerdict, type RunVerdict } from '../utils/run-status-projection'
import { eventInScope, scopeLabel, type TraceScope } from '../utils/trace-scope'
import { EdgeTamperSection } from './trace/EdgeTamperSection'
import type { SelectedEdge } from './studio/WorkspaceContext'
import type { ResumeRunOptions } from '../api/client'
import { traceOutcomeEntry } from '../utils/trace-outcome'
import { runStatusMark, type RunStatusMark } from '../utils/run-status-mark'
import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  FlaskConical,
  GitCompareArrows,
  MoreVertical,
  Play,
  X,
} from 'lucide-react'
import { useMemo } from 'react'
import { Alert, AlertDescription, AlertTitle } from './ui/alert'
import { Button } from './ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu'
import { HitlPromptForm } from './studio/HitlPromptForm'
import { latestHitlPrompt, type TraceHitlResumeRequest } from './studio/hitl-prompt'
import { TraceFilterRow } from './trace/TraceFilterRow'
import { TraceSearchBar } from './trace/TraceSearchBar'
import { useRunDeltas } from '../hooks/useRunDeltas'
import { TraceEventList } from './trace/TraceEventList'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import { useTraceCopy } from './trace/trace-copy'

// Re-exported so existing importers (`@/components/TracePanel`) keep working;
// the canonical definition now lives in studio/hitl-prompt to give the
// node-anchored box and this panel one shared source of truth.
export type { TraceHitlResumeRequest }

// The fallback shortcut narrows through the filter's own search, rather than
// owning a fifth kind of filter state that only one badge can set.
const ROUTE_DECISION_SEARCH_TERM = 'llm_route_decision'

interface TracePanelProps {
  traceLogs: EventEnvelope[]
  activePhase?: string | null
  /**
   * The node the user has focused on the canvas. The trace SCROLLS to that
   * node's group and shows every event regardless (decision 2026-08-09 D2 —
   * focus locates, it does not hide). A node's phase key equals its id,
   * matching how events carry `phase_name` and how `activeTracePhase` is keyed.
   */
  selectedNode?: {
    id: string
    /**
     * Carried for the focus label and for the trace region's node actions
     * (`FocusedNodeActions`), which read the golden tri-state (atom #30) and
     * phase mode rather than re-deriving golden coverage.
     */
    data: { label?: string; mode?: string; goldenState?: GoldenNodeState }
  } | null
  selectedEventId?: string | null
  onSelectEvent?: (index: number, event: CallbackEvent) => void
  /**
   * viewed-run model (decision 2026-08-07): the trace is one view of the
   * timeline region, so it can always hand the user back to the run list —
   * during a live stream and after the run ends alike.
   */
  onBack?: () => void
  /** The viewed run's id, shown in the header identity strip. */
  runId?: string | null
  /**
   * The run's owning skill. Needed to address the live-output socket, which is
   * keyed (skill, run) like its sibling.
   */
  skillId?: string | null
  /**
   * The run's sealed record: the header status badge reads it, and so does the
   * trace's terminal entry (token total + report path, decision 2026-08-09 D8).
   * Null until the backend has finalized the run — a live stream shows the
   * verdict and wall time it already has and gains the rest when this arrives.
   */
  metadata?: RunMetadata | null
  /** How the terminal gate said this run ended — `runVerdict`'s second channel. */
  gateVerdict?: RunVerdict | null
  /** True while this panel renders the live stream (streaming indicator). */
  live?: boolean
  canCompare?: boolean
  compareLoading?: boolean
  onCompareToGolden?: () => void
  onPromoteToGolden?: () => void
  canResume?: boolean
  resumeLoading?: boolean
  onResume?: () => void
  hitlSubmitting?: boolean
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
  /**
   * 选中即范围 (decision 2026-08-13 D6): the canvas selection this trace is
   * narrowed to. Null = the whole run. The chip in the header announces it and
   * clears it via `onClearScope` (same effect as clicking blank canvas).
   */
  scope?: TraceScope | null
  onClearScope?: () => void
  /**
   * The selected edge behind an edge scope (D5): the tamper editor — an
   * operation, not a display — renders under the scope chip, wired to the
   * same resume-downstream flow the retired EdgeContextView owned.
   */
  selectedEdge?: SelectedEdge | null
  onResumeEdgeDownstream?: (options: ResumeRunOptions) => Promise<void> | void
  edgeResumeLoading?: boolean
}

function envelopePayload(event: EventEnvelope): CallbackEvent {
  return event.payload as CallbackEvent
}

/**
 * One entry of the run's `⋮` overflow menu.
 *
 * `key` says which action it is and `pending` whether it is already under way;
 * between them they decide the word, which the menu looks up in the trace
 * namespace. The entry carries no sentence of its own — this projection is
 * pure and has no idea who is reading it.
 */
export interface TraceRunAction {
  key: 'resume' | 'compare' | 'promote' | 'report'
  pending: boolean
  icon: LucideIcon
  disabled: boolean
  run: () => void
}

/**
 * Which run-level actions this trace offers, and which of them are currently
 * available.
 *
 * An action exists only when the view wired its handler — a historical view
 * passes none and stays read-only (decision 2026-08-07). Availability is
 * separate: a wired action can still be unavailable right now (no resumable
 * run, a compare already in flight), which is what `disabled` says.
 *
 * The run report is deliberately NOT here. It moved to the trace's terminal
 * entry and to the run list row (decision 2026-08-09 D8 relocating 2026-08-08
 * D5): a product of the run belongs at the end of the run, not behind a menu
 * the reader has to think to open.
 */
export function traceRunActions({
  canResume,
  resumeLoading,
  onResume,
  canCompare,
  compareLoading,
  onCompareToGolden,
  onPromoteToGolden,
}: {
  canResume: boolean
  resumeLoading: boolean
  onResume?: () => void
  canCompare: boolean
  compareLoading: boolean
  onCompareToGolden?: () => void
  onPromoteToGolden?: () => void
}): TraceRunAction[] {
  const actions: TraceRunAction[] = []
  if (onResume) {
    actions.push({
      key: 'resume',
      pending: resumeLoading,
      icon: Play,
      disabled: !canResume || resumeLoading,
      run: onResume,
    })
  }
  if (onCompareToGolden) {
    actions.push({
      key: 'compare',
      pending: compareLoading,
      icon: GitCompareArrows,
      disabled: !canCompare || compareLoading,
      run: onCompareToGolden,
    })
  }
  if (onPromoteToGolden) {
    actions.push({
      key: 'promote',
      pending: false,
      icon: BadgeCheck,
      disabled: !canCompare,
      run: onPromoteToGolden,
    })
  }
  return actions
}

/**
 * How the run stands in the strip, as ONE icon.
 *
 * The strip has 331px of content box and one job per element (decision
 * 2026-08-09 D3); a word like "Success" spends a third of that saying what a
 * check mark says. The icon vocabulary itself is shared with the run list
 * (D9); WHICH status the strip describes comes from run-status-projection's
 * verdict (D7) — the same fold of stream + sealed record every other status
 * surface quotes, so a cancel whose stream died still lands here.
 */
function RunStatusMark({
  live,
  verdict,
}: {
  live: boolean
  verdict: RunVerdict
}) {
  const t = useTraceCopy()
  if (live && verdict === 'running') {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            data-trace-verdict="running"
            aria-label={t('panel.running')}
            className="flex size-4 shrink-0 items-center justify-center"
          >
            <span aria-hidden className="size-2 animate-pulse rounded-full bg-primary" />
          </span>
        </TooltipTrigger>
        <TooltipContent>{t('panel.runningTooltip')}</TooltipContent>
      </Tooltip>
    )
  }
  const mark = runStatusMark(verdict)
  if (!mark) {
    return null
  }
  const Icon = mark.icon
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Icon data-trace-verdict={verdict} aria-label={mark.label} className={`size-4 shrink-0 ${mark.tone}`} />
      </TooltipTrigger>
      <TooltipContent>{mark.label}</TooltipContent>
    </Tooltip>
  )
}

export function TracePanel({
  traceLogs,
  activePhase = null,
  selectedNode = null,
  selectedEventId = null,
  onSelectEvent,
  onBack,
  runId = null,
  metadata = null,
  gateVerdict = null,
  live = false,
  canCompare = false,
  compareLoading = false,
  onCompareToGolden,
  onPromoteToGolden,
  canResume = false,
  resumeLoading = false,
  onResume,
  hitlSubmitting = false,
  onSubmitHitlResponse,
  skillId = null,
  scope = null,
  onClearScope,
  selectedEdge = null,
  onResumeEdgeDownstream,
  edgeResumeLoading = false,
}: TracePanelProps) {
  const t = useTraceCopy()
  const traceEvents = traceLogs.map(envelopePayload)
  // Live output goes into the step rows that are producing it (decision
  // 2026-08-09 D6). Only a live view subscribes: a finished run's pieces were
  // never kept, and its answers are already on its events.
  const deltas = useRunDeltas(skillId, runId ?? null, Boolean(live))
  // Where the reader's attention is: the node they focused on the canvas, or —
  // with nothing focused — the phase currently running. It decides where the
  // list SCROLLS, never what it contains.
  const focusPhase = selectedNode?.id ?? activePhase
  const scopedEvents = scope ? traceEvents.filter((event) => eventInScope(event, scope)) : traceEvents
  const filter = useTraceFilter(scopedEvents)
  const hitlPrompt = useMemo(() => latestHitlPrompt(traceLogs), [traceLogs])
  // trace-observability F7: a run that silently fell back to another provider
  // announces it up front; clicking the chip narrows the trace to the fallback
  // events via the existing type filter.
  // Scoped, because the chip is ACTIONABLE: clicking it searches THIS list. A
  // count that does not match what clicking reveals is a promise the panel
  // cannot keep (2026-08-20 revision of F3).
  const degradedRouteCount = countRouteDegradations(scopedEvents)
  const activeFilterCount = filter.selectedCategories.length + filter.selectedPhases.length
  // History views judge by the persisted metadata; a live stream judges by its
  // own events (predict root event) — no run_id prefix sniffing either way.
  const isPredict = metadata ? metadata.kind === 'predict' : isPredictTrace(traceEvents)
  // D7: ONE verdict — stream, sealed record and terminal gate folded by
  // run-status-projection — feeds the strip badge, the outcome entry, and the
  // step list's severing.
  const verdict = runVerdict(traceEvents, metadata, undefined, gateVerdict)
  // D8: the run's conclusion is the last thing in its own trace. Fed the full
  // event list, not the filtered one — the ending of a run is not a search hit.
  // The outcome row sits at the END of the step list and says how the RUN
  // ended. Under a scope that list is one node's few events, so the verdict
  // reads as a judgement about them — a statement about the run pasted onto
  // something that is not the run (PM 08-19 Q5). The run's verdict stays
  // visible where it belongs: the top bar, which names the run itself (F8).
  const outcome = scope ? null : traceOutcomeEntry(traceEvents, metadata)

  const runActions = traceRunActions({
    canResume,
    resumeLoading,
    onResume,
    canCompare,
    compareLoading,
    onCompareToGolden,
    onPromoteToGolden,
  })
  // Run-level actions belong to the run's identity, not to the event list, so
  // they collapse into one overflow menu instead of each taking a labelled
  // button out of the search row's width (decision 2026-08-08 D4/D5).
  const runActionsMenu = runActions.length > 0 ? (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="icon-sm" aria-label={t('panel.runActions')}>
              <MoreVertical className="size-4" />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>{t('panel.runActionsTooltip')}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-64">
        {runActions.map((action) => {
          const ActionIcon = action.icon
          return (
            <DropdownMenuItem key={action.key} disabled={action.disabled} onSelect={action.run}>
              <ActionIcon />
              {action.pending ? t(`action.${action.key}Pending`) : t(`action.${action.key}`)}
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  ) : null

  // Identity strip: which run this trace belongs to, and how it stands. Shared
  // by the live and history views so the region reads as ONE surface.
  const identityStrip = (
    // pr-10 is the lane the overlay's floating close button occupies
    // (WorkspaceLeftPanelOverlay: absolute right-3 top-3) — content must not run
    // under it (FRONTEND_UI_SPEC §2.6).
    <div className="flex shrink-0 items-center gap-2 border-b border-border bg-card py-2 pl-3 pr-10">
      {onBack ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={onBack}
              aria-label={t('panel.back')}
            >
              <ArrowLeft className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('panel.backTooltip')}</TooltipContent>
        </Tooltip>
      ) : null}
      {/* WHICH run, in full. It was truncated to a 12-char head elsewhere and
          hidden behind the ⋮ menu here; both made the one identifying fact the
          hardest thing on screen to read. */}
      {isPredict ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <FlaskConical aria-label={t('panel.predict')} className="size-4 shrink-0 text-muted-foreground" />
          </TooltipTrigger>
          <TooltipContent>{t('panel.predictTooltip')}</TooltipContent>
        </Tooltip>
      ) : null}
      {runId ? (
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground" title={runId}>
          {runId}
        </span>
      ) : (
        <span className="min-w-0 flex-1 text-sm font-semibold text-foreground">{t('panel.title')}</span>
      )}
      <RunStatusMark live={live} verdict={verdict} />
      {runActionsMenu}
    </div>
  )

  // A failed run that cannot say why is undiagnosable. The reason travels on the
  // run's own metadata, so it renders whether or not the run got far enough to
  // emit events.
  const failureBanner = metadata?.error ? (
    <Alert variant="destructive" className="shrink-0 rounded-none border-x-0 border-t-0">
      <AlertTriangle className="size-4" />
      <AlertTitle className="font-mono text-xs">{metadata.error.code}</AlertTitle>
      <AlertDescription className="break-words text-xs">{metadata.error.message}</AlertDescription>
    </Alert>
  ) : null

  // D6: the scope chip is the filter's visible anchor — always shown while a
  // scope is active, including the no-events branch (a pre-run edge click has
  // its static inference to show there).
  const scopeStrip = scope ? (
    <div data-trace-scope className="shrink-0 space-y-2 border-b border-border bg-card px-3 py-2">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <span>{t('panel.scope')}</span>
        <span className="rounded-full border border-border bg-muted px-2 py-0.5 font-mono text-xs text-foreground">
          {scopeLabel(scope, (boundary) => t(`canvas:boundary.${boundary}`))}
        </span>
        <button
          type="button"
          aria-label={t('panel.clearScope')}
          onClick={() => onClearScope?.()}
          className="flex items-center rounded-full border border-border p-0.5 text-muted-foreground hover:bg-accent"
        >
          <X className="size-3" />
        </button>
      </div>
      {scope.kind === 'edge' && selectedEdge ? (
        <EdgeTamperSection
          selectedEdge={selectedEdge}
          onResumeDownstream={onResumeEdgeDownstream}
          resumeLoading={edgeResumeLoading}
        />
      ) : null}
    </div>
  ) : null

  // How this RUN was routed — a fact about the events on screen, and the chip
  // drives this panel's own search filter, so it belongs here. What you can do
  // to the focused NODE does not: that row is rendered by the trace region
  // (`FocusedNodeActions`), which is mounted whether or not a run exists.
  const routeIssuesRow = degradedRouteCount > 0 ? (
    <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
      {degradedRouteCount > 0 ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={t('routeIssues.show', { count: degradedRouteCount })}
              aria-pressed={filter.searchTerm === ROUTE_DECISION_SEARCH_TERM}
              onClick={() => filter.setSearchTerm(
                filter.searchTerm === ROUTE_DECISION_SEARCH_TERM ? '' : ROUTE_DECISION_SEARCH_TERM,
              )}
              className="flex items-center gap-1 rounded-full border border-warning-border bg-warning/10 px-2 py-0.5 text-xs font-semibold text-warning hover:bg-warning/20"
            >
              <AlertTriangle className="size-3" />
              {t('routeIssues.chip', { count: degradedRouteCount })}
            </button>
          </TooltipTrigger>
          <TooltipContent>
            {t('routeIssues.tooltip', { count: degradedRouteCount })}
          </TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  ) : null

  if (traceEvents.length === 0) {
    return (
      <div role="log" aria-live="polite" aria-label={t('panel.region')} className="flex h-full min-h-0 flex-col">
        {identityStrip}
        {failureBanner}
        {scopeStrip}
        {routeIssuesRow ? (
          <div className="shrink-0 border-b border-border bg-card px-3 py-2">{routeIssuesRow}</div>
        ) : null}
        <div className="flex flex-1 items-center justify-center text-sm font-medium text-muted-foreground">
          {live ? t('panel.waiting') : t('panel.empty')}
        </div>
      </div>
    )
  }

  return (
    <div role="log" aria-live="polite" aria-label={t('panel.region')} className="flex h-full min-h-0 flex-col">
      {identityStrip}
      {failureBanner}
      {scopeStrip}
      <div className="shrink-0 space-y-2 border-b border-border bg-card px-3 py-2">
        {/* One focus scope over the box and its tags: reaching for a tag must not
            be what closes the tags (decision 2026-08-09 D11). */}
        <div className="group/trace-search">
          <TraceSearchBar
            value={filter.searchTerm}
            onChange={filter.setSearchTerm}
            activeFilterCount={activeFilterCount}
          />
          <TraceFilterRow
            phases={filter.phases}
            selectedCategories={filter.selectedCategories}
            selectedPhases={filter.selectedPhases}
            onSelectCategories={filter.setSelectedCategories}
            onSelectPhases={filter.setSelectedPhases}
          />
        </div>
        {routeIssuesRow}
        {hitlPrompt ? (
          <HitlPromptForm
            prompt={hitlPrompt}
            submitting={hitlSubmitting}
            onSubmitHitlResponse={onSubmitHitlResponse}
          />
        ) : null}
      </div>
      <div className="min-h-0 flex-1 p-4 pb-0">
        <TraceEventList
          events={filter.filteredEvents}
          selectedEventId={selectedEventId}
          followStream={live}
          streamKey={runId}
          focusPhase={focusPhase}
          outcome={outcome}
          verdict={verdict}
          onSelectEvent={onSelectEvent}
          deltas={deltas}
        />
      </div>
    </div>
  )
}
