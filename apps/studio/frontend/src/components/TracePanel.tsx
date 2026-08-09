import type { CallbackEvent, EventEnvelope, RunMetadata } from '../api/types'
import type { GoldenNodeState } from './studio/node-golden'
import type { CompareTab } from './studio/run-compare'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { countLlmFallbacks, isPredictTrace, runOutcomeFromEvents, type TraceRunOutcome } from '../utils/trace'
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
  ShieldCheck,
} from 'lucide-react'
import { useMemo, useState } from 'react'
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
import { TraceEventList } from './trace/TraceEventList'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'

// Re-exported so existing importers (`@/components/TracePanel`) keep working;
// the canonical definition now lives in studio/hitl-prompt to give the
// node-anchored box and this panel one shared source of truth.
export type { TraceHitlResumeRequest }

// The fallback shortcut narrows through the filter's own search, rather than
// owning a fifth kind of filter state that only one badge can set.
const FALLBACK_SEARCH_TERM = 'llm_fallback'

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
     * The focused node also carries its golden tri-state (atom #30) and phase
     * mode so the trace can offer a per-node golden-create affordance (atom #32
     * entry①) for the focused node without re-deriving golden coverage here.
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
   * The run's sealed record: the header status badge reads it, and so does the
   * trace's terminal entry (token total + report path, decision 2026-08-09 D8).
   * Null until the backend has finalized the run — a live stream shows the
   * verdict and wall time it already has and gains the rest when this arrives.
   */
  metadata?: RunMetadata | null
  /** True while this panel renders the live stream (streaming indicator). */
  live?: boolean
  canCompare?: boolean
  compareLoading?: boolean
  onCompareToGolden?: () => void
  onPromoteToGolden?: () => void
  /**
   * Per-node golden create (atom #32 entry①): promote ONLY the focused agent node
   * to golden from the active run. Surfaced beside the trace's focus chip when a
   * golden-less agent node is focused, mirroring the Properties-panel affordance
   * but anchored to the node the user is reading in the trace. Same callback the
   * Properties panel uses (Workspace.handlePromoteNode), so both entry points write
   * one node's golden via the node_id-aware saveGoldenBaseline.
   */
  onPromoteNode?: (nodeId: string) => Promise<void> | void
  canResume?: boolean
  resumeLoading?: boolean
  onResume?: () => void
  hitlSubmitting?: boolean
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
  /**
   * n4-trace#23 (P8 model-compare): when a compare run is active, the per-candidate
   * tabs (one per candidate_id) the user switches between. Each tab carries the
   * candidate's spawned run id + a `failed` flag (read from the run's
   * metadata.status) so a failed candidate's tab is marked. Absent on ordinary
   * (non-compare) runs, where the panel renders without the tab strip.
   */
  compareTabs?: CompareTab[]
  activeCandidateId?: string | null
  onSelectCandidate?: (candidateId: string) => void
}

function envelopePayload(event: EventEnvelope): CallbackEvent {
  return event.payload as CallbackEvent
}

/**
 * atom #32 entry①: which focused node may get a per-node golden created from the
 * trace. Pure projection of the data the trace already holds — no golden coverage
 * is re-derived here. A node qualifies only when it is an AGENT node (skill/llm/
 * agent; logic & subgraph never get golden, design g-c) and does NOT already have
 * golden ('has-golden' → already captured, nothing to create).
 */
export function isGoldenlessAgentNode(
  node: { data: { mode?: string; goldenState?: GoldenNodeState } } | null | undefined,
): boolean {
  if (!node) {
    return false
  }
  const mode = node.data.mode
  const isAgent = mode === 'agent' || mode === 'llm' || mode === 'skill'
  if (!isAgent) {
    return false
  }
  return node.data.goldenState !== 'has-golden'
}

/** One entry of the run's `⋮` overflow menu. */
export interface TraceRunAction {
  key: 'resume' | 'compare' | 'promote' | 'report'
  label: string
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
      label: resumeLoading ? 'Resuming' : 'Resume from last checkpoint',
      icon: Play,
      disabled: !canResume || resumeLoading,
      run: onResume,
    })
  }
  if (onCompareToGolden) {
    actions.push({
      key: 'compare',
      label: compareLoading ? 'Comparing' : 'Compare to golden',
      icon: GitCompareArrows,
      disabled: !canCompare || compareLoading,
      run: onCompareToGolden,
    })
  }
  if (onPromoteToGolden) {
    actions.push({
      key: 'promote',
      label: 'Promote to golden',
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
 * (D9) — this only decides WHICH status the strip is describing.
 */
function stripStatusMark(
  live: boolean,
  metadata: RunMetadata | null | undefined,
  outcome: TraceRunOutcome,
): RunStatusMark | null {
  // A live stream that went quiet says which way it went, rather than pulsing
  // "in progress" at a run that already ended.
  if (live && outcome === 'running') {
    return null
  }
  return runStatusMark(live ? outcome : metadata?.status)
}

function RunStatusMark({
  live,
  metadata,
  outcome,
}: {
  live: boolean
  metadata?: RunMetadata | null
  outcome: TraceRunOutcome
}) {
  if (live && outcome === 'running') {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            aria-label="Run in progress"
            className="flex size-4 shrink-0 items-center justify-center"
          >
            <span aria-hidden className="size-2 animate-pulse rounded-full bg-primary" />
          </span>
        </TooltipTrigger>
        <TooltipContent>Running</TooltipContent>
      </Tooltip>
    )
  }
  const mark = stripStatusMark(live, metadata, outcome)
  if (!mark) {
    return null
  }
  const Icon = mark.icon
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Icon aria-label={mark.label} className={`size-4 shrink-0 ${mark.tone}`} />
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
  live = false,
  canCompare = false,
  compareLoading = false,
  onCompareToGolden,
  onPromoteToGolden,
  onPromoteNode,
  canResume = false,
  resumeLoading = false,
  onResume,
  hitlSubmitting = false,
  onSubmitHitlResponse,
  compareTabs,
  activeCandidateId = null,
  onSelectCandidate,
}: TracePanelProps) {
  const traceEvents = traceLogs.map(envelopePayload)
  // Where the reader's attention is: the node they focused on the canvas, or —
  // with nothing focused — the phase currently running. It decides where the
  // list SCROLLS, never what it contains.
  const focusPhase = selectedNode?.id ?? activePhase
  const focusLabel = selectedNode?.data.label ?? focusPhase
  const filter = useTraceFilter(traceEvents)
  const hitlPrompt = useMemo(() => latestHitlPrompt(traceLogs), [traceLogs])
  // trace-observability F7: a run that silently fell back to another provider
  // announces it up front; clicking the chip narrows the trace to the fallback
  // events via the existing type filter.
  const fallbackCount = countLlmFallbacks(traceEvents)
  const activeFilterCount = filter.selectedCategories.length + filter.selectedPhases.length
  // History views judge by the persisted metadata; a live stream judges by its
  // own events (predict root event) — no run_id prefix sniffing either way.
  const isPredict = metadata ? metadata.kind === 'predict' : isPredictTrace(traceEvents)
  const runOutcome = runOutcomeFromEvents(traceEvents)
  // D8: the run's conclusion is the last thing in its own trace. Fed the full
  // event list, not the filtered one — the ending of a run is not a search hit.
  const outcome = traceOutcomeEntry(traceEvents, metadata)

  const [nodePromoting, setNodePromoting] = useState(false)
  // atom #32 entry①: offer per-node golden creation for the focused, golden-less
  // agent node — only while a node is actually focused, a run exists to promote
  // from (canCompare === Boolean(runId)), and the wiring is present. It is the
  // trace's node-scoped counterpart to the run-level Golden action.
  const canPromoteFocusedNode =
    Boolean(onPromoteNode) &&
    canCompare &&
    isGoldenlessAgentNode(selectedNode)
  const handlePromoteFocusedNode = async () => {
    if (!onPromoteNode || !selectedNode || nodePromoting) {
      return
    }
    setNodePromoting(true)
    try {
      await onPromoteNode(selectedNode.id)
    } finally {
      setNodePromoting(false)
    }
  }

  // n4-trace#23: the per-candidate tab strip. Rendered whenever a compare run is
  // active (even before its events stream in) so the user can switch candidates
  // while a tab is still empty. Each tab shows the candidate's role and marks a
  // failed candidate (metadata.status === 'failed') so the failure is visible.
  const hasCompareTabs = Array.isArray(compareTabs) && compareTabs.length > 0
  const compareTabStrip = hasCompareTabs ? (
    <div
      role="tablist"
      aria-label="Model compare candidates"
      className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-card px-2 py-1.5"
    >
      {compareTabs!.map((tab) => {
        const isActive = tab.candidateId === activeCandidateId
        return (
          <button
            key={tab.candidateId}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-label={`Candidate ${tab.label}${tab.failed ? ' (failed)' : ''}`}
            onClick={() => onSelectCandidate?.(tab.candidateId)}
            className={[
              'flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-1 text-xs font-semibold transition-colors',
              isActive
                ? 'border-primary bg-primary/10 text-foreground'
                : 'border-border bg-card text-muted-foreground hover:bg-accent',
              tab.failed ? 'text-destructive' : '',
            ].join(' ')}
          >
            {tab.failed ? <AlertTriangle className="size-3" /> : null}
            {tab.running ? (
              <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-primary" />
            ) : null}
            <span className="max-w-[140px] truncate">{tab.label}</span>
          </button>
        )
      })}
    </div>
  ) : null

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
            <Button type="button" variant="ghost" size="icon-sm" aria-label="Run actions">
              <MoreVertical className="size-4" />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>Actions for this run</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-64">
        {runActions.map((action) => {
          const ActionIcon = action.icon
          return (
            <DropdownMenuItem key={action.key} disabled={action.disabled} onSelect={action.run}>
              <ActionIcon />
              {action.label}
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
              aria-label="Back to timeline"
            >
              <ArrowLeft className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Back to the run list</TooltipContent>
        </Tooltip>
      ) : null}
      {/* WHICH run, in full. It was truncated to a 12-char head elsewhere and
          hidden behind the ⋮ menu here; both made the one identifying fact the
          hardest thing on screen to read. */}
      {isPredict ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <FlaskConical aria-label="Predict attempt" className="size-4 shrink-0 text-muted-foreground" />
          </TooltipTrigger>
          <TooltipContent>Predict attempt — no tokens spent on a real run</TooltipContent>
        </Tooltip>
      ) : null}
      {runId ? (
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground" title={runId}>
          {runId}
        </span>
      ) : (
        <span className="min-w-0 flex-1 text-sm font-semibold text-foreground">Trace</span>
      )}
      <RunStatusMark live={live} metadata={metadata} outcome={runOutcome} />
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

  if (traceEvents.length === 0) {
    return (
      <div role="log" aria-live="polite" aria-label="Trace" className="flex h-full min-h-0 flex-col">
        {compareTabStrip}
        {identityStrip}
        {failureBanner}
        <div className="flex flex-1 items-center justify-center text-sm font-medium text-muted-foreground">
          {live ? 'Waiting for run events' : 'No events recorded for this run'}
        </div>
      </div>
    )
  }

  return (
    <div role="log" aria-live="polite" aria-label="Trace" className="flex h-full min-h-0 flex-col">
      {compareTabStrip}
      {identityStrip}
      {failureBanner}
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
        {fallbackCount > 0 || canPromoteFocusedNode ? (
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
          {fallbackCount > 0 ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={`Filter ${fallbackCount} LLM fallback event${fallbackCount === 1 ? '' : 's'}`}
                  aria-pressed={filter.searchTerm === FALLBACK_SEARCH_TERM}
                  onClick={() => filter.setSearchTerm(
                    filter.searchTerm === FALLBACK_SEARCH_TERM ? '' : FALLBACK_SEARCH_TERM,
                  )}
                  className="flex items-center gap-1 rounded-full border border-warning-border bg-warning/10 px-2 py-0.5 text-xs font-semibold text-warning hover:bg-warning/20"
                >
                  <AlertTriangle className="size-3" />
                  {fallbackCount} LLM fallback{fallbackCount === 1 ? '' : 's'}
                </button>
              </TooltipTrigger>
              <TooltipContent>
                A provider failed during this run and calls fell back to another route — the model actually
                used may differ from the configured one. Click to show only the fallback events.
              </TooltipContent>
            </Tooltip>
          ) : null}
          {canPromoteFocusedNode ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={`Promote node "${focusLabel}" to golden`}
                  disabled={nodePromoting}
                  onClick={() => {
                    void handlePromoteFocusedNode()
                  }}
                  className="flex items-center gap-1 rounded-full border border-warning-border px-2 py-0.5 text-xs font-semibold text-warning hover:bg-warning/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ShieldCheck className="size-3.5" />
                  {nodePromoting ? 'Promoting node' : 'Promote node to golden'}
                </button>
              </TooltipTrigger>
              <TooltipContent>Create a golden baseline for just this focused node from the current run</TooltipContent>
            </Tooltip>
          ) : null}
        </div>
        ) : null}
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
          onSelectEvent={onSelectEvent}
        />
      </div>
    </div>
  )
}
