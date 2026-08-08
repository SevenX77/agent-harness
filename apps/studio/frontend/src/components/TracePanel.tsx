import type { CallbackEvent, EventEnvelope, RunMetadata } from '../api/types'
import type { GoldenNodeState } from './studio/node-golden'
import type { CompareTab } from './studio/run-compare'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { countLlmFallbacks, isPredictTrace, runOutcomeFromEvents, type TraceRunOutcome } from '../utils/trace'
import { AlertTriangle, ArrowLeft, BadgeCheck, GitCompareArrows, Link2, Link2Off, Play, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Alert, AlertDescription, AlertTitle } from './ui/alert'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { HitlPromptForm } from './studio/HitlPromptForm'
import { latestHitlPrompt, type TraceHitlResumeRequest } from './studio/hitl-prompt'
import { TraceFilter } from './trace/TraceFilter'
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
   * The node the user has focused on the canvas (atom #17: focus decides trace
   * granularity). When set, the trace narrows to that node's phase ("focus a
   * node = its trace"); when null, the panel shows the whole-run overview
   * ("focus empty canvas = run overview"). A node's phase key equals its id,
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
  linkEnabled?: boolean
  onToggleLink?: (enabled: boolean) => void
  onSelectPrompt: (index: number) => void
  onSelectEvent?: (index: number, event: CallbackEvent) => void
  /**
   * viewed-run model (decision 2026-08-07): the trace is one view of the
   * timeline region, so it can always hand the user back to the run list —
   * during a live stream and after the run ends alike.
   */
  onBack?: () => void
  /** The viewed run's id, shown in the header identity strip. */
  runId?: string | null
  /** Historical view: the persisted metadata behind the header status badge. */
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

/** Header status: live view shows the stream state, history shows the verdict. */
function RunStatusBadge({
  live,
  metadata,
  outcome,
}: {
  live: boolean
  metadata?: RunMetadata | null
  outcome: TraceRunOutcome
}) {
  if (live && outcome !== 'running') {
    // The stream went quiet because the run finished — say which way it went
    // rather than pulsing "Live" at a run that ended.
    if (outcome === 'success') {
      return <Badge variant="outline" className="text-success">Success</Badge>
    }
    if (outcome === 'interrupted') {
      return <Badge variant="outline" className="text-warning">Interrupted</Badge>
    }
    return <Badge variant="outline" className="text-destructive">Failed</Badge>
  }
  if (live) {
    return (
      <Badge variant="outline" className="gap-1.5 text-muted-foreground">
        <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-primary" />
        Live
      </Badge>
    )
  }
  if (!metadata) {
    return null
  }
  if (metadata.status === 'success') {
    return <Badge variant="outline" className="text-success">Success</Badge>
  }
  if (metadata.status === 'paused') {
    return <Badge variant="outline" className="text-warning">Paused</Badge>
  }
  if (metadata.status === 'running') {
    return <Badge variant="outline" className="text-muted-foreground">Running</Badge>
  }
  return <Badge variant="outline" className="text-destructive">{metadata.status === 'cancelled' ? 'Cancelled' : 'Failed'}</Badge>
}

export function TracePanel({
  traceLogs,
  activePhase = null,
  selectedNode = null,
  selectedEventId = null,
  linkEnabled = true,
  onToggleLink,
  onSelectPrompt,
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
  // atom #17: a user-focused node decides trace granularity and wins over the
  // running-phase link highlight. With no focused node we fall back to
  // activePhase (the live link-views behavior) so existing wiring is unchanged.
  const focusPhase = selectedNode?.id ?? activePhase
  const focusLabel = selectedNode?.data.label ?? focusPhase
  const filter = useTraceFilter(traceEvents, linkEnabled ? focusPhase : null)
  const hitlPrompt = useMemo(() => latestHitlPrompt(traceLogs), [traceLogs])
  // trace-observability F7: a run that silently fell back to another provider
  // announces it up front; clicking the chip narrows the trace to the fallback
  // events via the existing type filter.
  const fallbackCount = countLlmFallbacks(traceEvents)
  // History views judge by the persisted metadata; a live stream judges by its
  // own events (predict root event) — no run_id prefix sniffing either way.
  const isPredict = metadata ? metadata.kind === 'predict' : isPredictTrace(traceEvents)
  const runOutcome = runOutcomeFromEvents(traceEvents)

  const [nodePromoting, setNodePromoting] = useState(false)
  // atom #32 entry①: offer per-node golden creation for the focused, golden-less
  // agent node — only while a node is actually focused in the trace (link on),
  // a run exists to promote from (canCompare === Boolean(runId)), and the wiring
  // is present. We narrow to the focused node, so this button is the trace's
  // node-scoped counterpart to the run-level Golden button above it.
  const canPromoteFocusedNode =
    Boolean(onPromoteNode) &&
    canCompare &&
    linkEnabled &&
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

  // Identity strip: which run this trace belongs to, and how it stands. Shared
  // by the live and history views so the region reads as ONE surface (D3 命名:
  // 区域=Timeline / 本视图=Trace / 文档=Full Trace).
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
      <h3 className="text-sm font-semibold text-foreground">Trace</h3>
      {runId ? (
        <span className="min-w-0 truncate font-mono text-xs text-muted-foreground">
          {runId.slice(0, 16)}{runId.length > 16 ? '…' : ''}
        </span>
      ) : null}
      {isPredict ? (
        <Badge variant="outline" className="text-warning">Predict</Badge>
      ) : null}
      <RunStatusBadge live={live} metadata={metadata} outcome={runOutcome} />
      <span className="ml-auto shrink-0 whitespace-nowrap text-xs text-muted-foreground">
        {filter.filteredEvents.length === traceEvents.length
          ? `${traceEvents.length} events`
          : `${filter.filteredEvents.length} / ${traceEvents.length}`}
      </span>
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
      <div className="shrink-0 space-y-2 border-b border-border bg-card p-3">
        <div className="flex items-center gap-1.5">
          <div className="min-w-0 flex-1">
            <TraceSearchBar value={filter.searchTerm} onChange={filter.setSearchTerm} />
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Link trace to the focused node"
                aria-pressed={linkEnabled}
                onClick={() => onToggleLink?.(!linkEnabled)}
                className={linkEnabled ? 'text-link' : 'text-muted-foreground'}
              >
                {linkEnabled ? <Link2 className="size-4" /> : <Link2Off className="size-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {linkEnabled
                ? 'Linked: focusing a node narrows the trace to it'
                : 'Unlinked: the trace ignores canvas focus'}
            </TooltipContent>
          </Tooltip>
          {onResume ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label="Resume run from last checkpoint"
                  disabled={!canResume || resumeLoading}
                  onClick={onResume}
                  className="text-success hover:text-success"
                >
                  <Play className="size-3.5" />
                  {resumeLoading ? 'Resuming' : 'Resume'}
                </Button>
              </TooltipTrigger>
              <TooltipContent>Continue this run from its last checkpoint</TooltipContent>
            </Tooltip>
          ) : null}
          {onCompareToGolden ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Compare trace to golden baseline"
              disabled={!canCompare || compareLoading}
              onClick={onCompareToGolden}
              className="text-link hover:text-link"
            >
              <GitCompareArrows className="size-3.5" />
              {compareLoading ? 'Comparing' : 'Compare'}
            </Button>
          ) : null}
          {onPromoteToGolden ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Promote run to golden baseline"
              disabled={!canCompare}
              onClick={onPromoteToGolden}
              className="text-warning hover:text-warning"
            >
              <BadgeCheck className="size-3.5" />
              Golden
            </Button>
          ) : null}
        </div>
        <TraceFilter
          phases={filter.phases}
          selectedCategories={filter.selectedCategories}
          selectedPhases={filter.selectedPhases}
          activePhase={linkEnabled ? focusPhase : null}
          onSelectCategories={filter.setSelectedCategories}
          onSelectPhases={filter.setSelectedPhases}
          onClear={filter.clearFilters}
        />
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
          activePhase={focusPhase}
          selectedEventId={selectedEventId}
          linkEnabled={linkEnabled}
          followStream={live}
          streamKey={runId}
          onSelectPrompt={onSelectPrompt}
          onSelectEvent={onSelectEvent}
        />
      </div>
    </div>
  )
}
