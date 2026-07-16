import type { CallbackEvent, EventEnvelope } from '../api/types'
import type { GoldenNodeState } from './studio/node-golden'
import type { CompareTab } from './studio/run-compare'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { AlertTriangle, BadgeCheck, GitCompareArrows, Play, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { HitlPromptForm } from './studio/HitlPromptForm'
import { latestHitlPrompt, type TraceHitlResumeRequest } from './studio/hitl-prompt'
import { TraceFilter } from './trace/TraceFilter'
import { TraceSearchBar } from './trace/TraceSearchBar'
import { VirtualTraceList } from './trace/VirtualTraceList'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'

// Re-exported so existing importers (`@/components/TracePanel`) keep working;
// the canonical definition now lives in studio/hitl-prompt to give the
// node-anchored box and this panel one shared source of truth.
export type { TraceHitlResumeRequest }

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

export function TracePanel({
  traceLogs,
  activePhase = null,
  selectedNode = null,
  selectedEventId = null,
  linkEnabled = true,
  onToggleLink,
  onSelectPrompt,
  onSelectEvent,
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
                ? 'border-primary bg-primary/10 text-primary'
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

  if (traceEvents.length === 0) {
    return (
      <div role="log" aria-live="polite" aria-label="Event Trace" className="flex h-full min-h-0 flex-col">
        {compareTabStrip}
        <div className="flex flex-1 items-center justify-center text-sm font-medium text-muted-foreground">
          Waiting for run events
        </div>
      </div>
    )
  }

  return (
    <div role="log" aria-live="polite" aria-label="Event Trace" className="flex h-full min-h-0 flex-col">
      {compareTabStrip}
      <div className="shrink-0 space-y-3 border-b border-border bg-card p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-semibold text-foreground">Event Trace</h3>
          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Resume run from last checkpoint"
                  disabled={!canResume || resumeLoading}
                  onClick={onResume}
                  className="flex items-center gap-1 rounded-md border border-success-border px-2 py-1 text-xs font-semibold text-success hover:bg-success/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Play className="h-3.5 w-3.5" />
                  {resumeLoading ? 'Resuming' : 'Resume'}
                </button>
              </TooltipTrigger>
              <TooltipContent>Continue this run from its last checkpoint</TooltipContent>
            </Tooltip>
            <button
              type="button"
              aria-label="Compare trace to golden baseline"
              disabled={!canCompare || compareLoading}
              onClick={onCompareToGolden}
              className="flex items-center gap-1 rounded-md border border-primary/40 px-2 py-1 text-xs font-semibold text-primary hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <GitCompareArrows className="h-3.5 w-3.5" />
              {compareLoading ? 'Comparing' : 'Compare'}
            </button>
            <button
              type="button"
              aria-label="Promote run to golden baseline"
              disabled={!canCompare}
              onClick={onPromoteToGolden}
              className="flex items-center gap-1 rounded-md border border-warning-border px-2 py-1 text-xs font-semibold text-warning hover:bg-warning/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <BadgeCheck className="h-3.5 w-3.5" />
              Golden
            </button>
            <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <input
                type="checkbox"
                checked={linkEnabled}
                onChange={(event) => onToggleLink?.(event.target.checked)}
                className="h-3.5 w-3.5 rounded border-border accent-primary"
              />
              Link views
            </label>
          </div>
        </div>
        <TraceSearchBar value={filter.searchTerm} onChange={filter.setSearchTerm} />
        <TraceFilter
          eventTypes={filter.eventTypes}
          phases={filter.phases}
          selectedTypes={filter.selectedTypes}
          selectedPhases={filter.selectedPhases}
          activePhase={linkEnabled ? focusPhase : null}
          onToggleType={filter.toggleType}
          onTogglePhase={filter.togglePhase}
          onClear={filter.clearFilters}
        />
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground">
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5">
                {linkEnabled && focusPhase ? `Focus: ${focusLabel}` : 'Focus: whole run'}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {linkEnabled && focusPhase
                ? `Focused on node "${focusLabel}" — showing this node's executions`
                : 'Whole-run trace — focus a node to narrow to its executions'}
            </TooltipContent>
          </Tooltip>
          <span>
            Showing {filter.filteredEvents.length} of {traceEvents.length} events
          </span>
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
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {nodePromoting ? 'Promoting node' : 'Promote node to golden'}
                </button>
              </TooltipTrigger>
              <TooltipContent>Create a golden baseline for just this focused node from the current run</TooltipContent>
            </Tooltip>
          ) : null}
        </div>
        {hitlPrompt ? (
          <HitlPromptForm
            prompt={hitlPrompt}
            submitting={hitlSubmitting}
            onSubmitHitlResponse={onSubmitHitlResponse}
          />
        ) : null}
      </div>
      <div className="min-h-0 flex-1 p-4">
        <VirtualTraceList
          events={filter.filteredEvents}
          activePhase={focusPhase}
          selectedEventId={selectedEventId}
          linkEnabled={linkEnabled}
          onSelectPrompt={onSelectPrompt}
          onSelectEvent={onSelectEvent}
        />
      </div>
    </div>
  )
}
