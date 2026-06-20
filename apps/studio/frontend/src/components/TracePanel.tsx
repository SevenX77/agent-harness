import type { CallbackEvent, EventEnvelope } from '../api/types'
import type { GoldenNodeState } from './studio/node-golden'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { BadgeCheck, GitCompareArrows, Play, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { HitlPromptForm } from './studio/HitlPromptForm'
import { latestHitlPrompt, type TraceHitlResumeRequest } from './studio/hitl-prompt'
import { TraceFilter } from './trace/TraceFilter'
import { TraceSearchBar } from './trace/TraceSearchBar'
import { VirtualTraceList } from './trace/VirtualTraceList'

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
}

function envelopePayload(event: EventEnvelope): CallbackEvent {
  return event.payload as CallbackEvent
}

/**
 * atom #32 entry①: which focused node may get a per-node golden created from the
 * trace. Pure projection of the data the trace already holds — no golden coverage
 * is re-derived here. A node qualifies only when it is an AGENT node (the same
 * mode set the Properties panel gates NodeGoldenSection on: skill/llm/agent; logic
 * & subgraph never get golden, design g-c) and does NOT already have golden
 * ('has-golden' → already captured, nothing to create).
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

  if (traceEvents.length === 0) {
    return (
      <div
        role="log"
        aria-live="polite"
        aria-label="Event Trace"
        className="flex h-full items-center justify-center text-sm font-medium text-slate-400 dark:text-slate-500"
      >
        Waiting for run events
      </div>
    )
  }

  return (
    <div role="log" aria-live="polite" aria-label="Event Trace" className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-3 border-b border-border bg-card p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-semibold text-foreground">Event Trace</h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Resume run from last checkpoint"
              title="Continue this run from its last checkpoint"
              disabled={!canResume || resumeLoading}
              onClick={onResume}
              className="flex items-center gap-1 rounded-md border border-emerald-200 px-2 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-900 dark:text-emerald-300 dark:hover:bg-emerald-950/40"
            >
              <Play className="h-3.5 w-3.5" />
              {resumeLoading ? 'Resuming' : 'Resume'}
            </button>
            <button
              type="button"
              aria-label="Compare trace to golden baseline"
              disabled={!canCompare || compareLoading}
              onClick={onCompareToGolden}
              className="flex items-center gap-1 rounded-md border border-sky-200 px-2 py-1 text-xs font-semibold text-sky-700 hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-sky-900 dark:text-sky-300 dark:hover:bg-sky-950/40"
            >
              <GitCompareArrows className="h-3.5 w-3.5" />
              {compareLoading ? 'Comparing' : 'Compare'}
            </button>
            <button
              type="button"
              aria-label="Promote run to golden baseline"
              disabled={!canCompare}
              onClick={onPromoteToGolden}
              className="flex items-center gap-1 rounded-md border border-amber-200 px-2 py-1 text-xs font-semibold text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-900 dark:text-amber-300 dark:hover:bg-amber-950/40"
            >
              <BadgeCheck className="h-3.5 w-3.5" />
              Golden
            </button>
            <label className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
              <input
                type="checkbox"
                checked={linkEnabled}
                onChange={(event) => onToggleLink?.(event.target.checked)}
                className="h-3.5 w-3.5 rounded border-gray-300 text-sky-600 focus:ring-sky-500"
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
          <span
            className="rounded-full border border-border bg-muted/40 px-2 py-0.5"
            title={
              linkEnabled && focusPhase
                ? `Focused on node "${focusLabel}" — showing this node's executions`
                : 'Whole-run trace — focus a node to narrow to its executions'
            }
          >
            {linkEnabled && focusPhase ? `Focus: ${focusLabel}` : 'Focus: whole run'}
          </span>
          <span>
            Showing {filter.filteredEvents.length} of {traceEvents.length} events
          </span>
          {canPromoteFocusedNode ? (
            <button
              type="button"
              aria-label={`Promote node "${focusLabel}" to golden`}
              title="Create a golden baseline for just this focused node from the current run"
              disabled={nodePromoting}
              onClick={() => {
                void handlePromoteFocusedNode()
              }}
              className="flex items-center gap-1 rounded-full border border-amber-200 px-2 py-0.5 text-xs font-semibold text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-900 dark:text-amber-300 dark:hover:bg-amber-950/40"
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              {nodePromoting ? 'Promoting node' : 'Promote node to golden'}
            </button>
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
