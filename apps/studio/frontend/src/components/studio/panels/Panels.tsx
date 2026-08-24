import { useTranslation } from "react-i18next"
import type { ResumeRunOptions } from "@/api/client"
import type { CallbackEvent, EventEnvelope, LintError, ResumeValidityResponse, RunMetadata, RuntimeArtifactRow, RuntimeConfig, SkillDetail } from "@/api/types"
import type { RunVerdict } from "@/utils/run-status-projection"
import type { SkillGraphNodeData, SkillNodeStatus } from "@/components/GraphCanvas"
import type { ChildSaveTarget } from "@/components/GraphCanvas/drill-edit"
import { TracePanel, type TraceHitlResumeRequest } from "@/components/TracePanel"
import { CompareCandidateTabs } from "@/components/trace/CompareCandidateTabs"
import { FocusedNodeActions } from "@/components/trace/FocusedNodeActions"
import type { CompareTab } from "../run-compare"
import { useSkills } from "@/hooks/useSkills"
import type { PanelKind } from "../Toolbar"
import type { SettingsTab } from "../SettingsPage"
import { useWorkspaceContext } from "../WorkspaceContext"
import { AssetsPanel } from "./AssetsPanel"
import { HistoryPanel } from "./HistoryPanel"
import { InputPanel } from "./InputPanel"
import type { IoBoundarySelection } from "./io-target"
import type { TraceScope } from "@/utils/trace-scope"
import { PanelHeader } from "./_shared/PanelHeader"
import { PropertiesPanel } from "./PropertiesPanel"
import { TimelinePanel } from "./TimelinePanel"
import type { TraceView } from "./trace-view"
import type { SubgraphMembershipTree } from "./use-subgraph-membership-tree"
import type { WorkspaceDirectoryTree } from "./use-workspace-directory-tree"

interface PanelsProps {
  activePanel: PanelKind
  skillId: string | null
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  runtimeConfig?: RuntimeConfig | null
  assetDirectoryTree?: WorkspaceDirectoryTree
  assetSubgraphTree?: SubgraphMembershipTree
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  /** Which boundary pseudo-node is selected, so the i/o panel scopes by role. */
  ioBoundary?: IoBoundarySelection
  // F4: i/o-panel test-input selection that feeds Predict/Run.
  selectedTestInputId?: string | null
  onSelectTestInput?: (id: string | null) => void
  onRuntimeArtifactsSave?: (artifacts: RuntimeArtifactRow[]) => Promise<string | null>
  onRuntimeConfigRefresh?: () => Promise<unknown> | unknown
  onPhaseFileSave?: (
    payload: { path: string; content: string; expectedHash: string },
    target?: ChildSaveTarget,
  ) => Promise<void> | void
  onPhaseRename?: (phaseId: string, nextPhaseId: string, target?: ChildSaveTarget) => Promise<void> | void
  onActionCreate?: (phaseId: string, name: string, target?: ChildSaveTarget) => Promise<void> | void
  onActionDelete?: (phaseId: string, name: string, target?: ChildSaveTarget) => Promise<void> | void
  onValidatorCreate?: (phaseId: string, target?: ChildSaveTarget) => Promise<void> | void
  // trace-observability F1/F2 (viewed-run model, decision 2026-08-07): the
  // timeline region renders whichever run `traceView` points at — the live
  // stream, a fetched historical run, or (null) the run-history list. `runId`
  // stays the LIVE run for Properties/resume affordances.
  traceView?: TraceView | null
  onCloseTraceView?: () => void
  onSelectRun?: (run: RunMetadata) => void
  historyLoadingRunId?: string | null
  runId?: string | null
  selectedNodeStatus?: SkillNodeStatus | null
  resumeValidity?: ResumeValidityResponse | null
  resumeValidityLoading?: boolean
  resumeValidityError?: string | null
  // Field-axis diagnostics for the Properties panel (engine field_path projection).
  lintErrors?: LintError[] | null
  traceEvents?: EventEnvelope[]
  activeTracePhase?: string | null
  traceCanCompare?: boolean
  traceCompareLoading?: boolean
  onCompareToGolden?: () => void
  onPromoteToGolden?: () => void
  traceCanResume?: boolean
  traceResumeLoading?: boolean
  /** Link views: whether canvas focus narrows the trace, and the toggle for it. */
  /** The trace row the user last opened, so it stays marked as they scroll. */
  traceSelectedEventId?: string | null
  onSelectTraceEvent?: (index: number, event: CallbackEvent) => void
  /**
   * The LIVE run's sealed record once the backend has finalized it; null before.
   * It carries the token total and the report path the streamed events cannot
   * (decision 2026-08-09 D8), and reaches the panel as the same `metadata` a
   * historical view passes, so both views build their terminal entry alike.
   */
  traceLiveMetadata?: RunMetadata | null
  /** How the terminal gate said this run ended — `runVerdict`'s second channel. */
  traceGateVerdict?: RunVerdict | null
  onResumeRun?: () => void
  onResumeNode?: (options: ResumeRunOptions) => Promise<void> | void
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
  onResumeEdgeDownstream?: (options: ResumeRunOptions) => Promise<void> | void
  /** D6: one-click scope clear — same full deselect as clicking blank canvas. */
  onClearTraceScope?: () => void
  /** Per-node golden promote (atom #32), surfaced in the node Properties panel. */
  onPromoteNode?: (nodeId: string) => Promise<void> | void
  onDesignGolden?: (node: { id: string; label?: string }) => void
  // n4-trace#23 (P8 model-compare): per-candidate Trace tabs + selection, forwarded
  // to the live TracePanel so the user can switch between candidate runs.
  compareTabs?: CompareTab[]
  activeCandidateId?: string | null
  onSelectCandidate?: (candidateId: string) => void
  /** Launch the focused node's Compare LLMs off the current base run. */
  onStartNodeCompare?: (nodeId: string) => void
  onOpenSettings?: (tab?: SettingsTab) => void
  /** Deselect the node so Properties falls back to the graph (GRAPH.md) form. */
  onSelectGraph?: () => void
}

export function Panels({
  activePanel,
  skillId,
  workspaceRoot = null,
  skillDetail,
  runtimeConfig = null,
  assetDirectoryTree,
  assetSubgraphTree,
  selectedNode,
  ioBoundary,
  selectedTestInputId,
  onSelectTestInput,
  onRuntimeArtifactsSave,
  onRuntimeConfigRefresh,
  onPhaseFileSave,
  onPhaseRename,
  onActionCreate,
  onActionDelete,
  onValidatorCreate,
  traceView,
  onCloseTraceView,
  onSelectRun,
  historyLoadingRunId = null,
  runId,
  selectedNodeStatus,
  resumeValidity,
  resumeValidityLoading,
  resumeValidityError,
  lintErrors,
  traceEvents,
  activeTracePhase,
  traceCanCompare,
  traceCompareLoading,
  onCompareToGolden,
  onPromoteToGolden,
  traceCanResume,
  traceResumeLoading,
  traceSelectedEventId = null,
  onSelectTraceEvent,
  traceLiveMetadata = null,
  traceGateVerdict = null,
  onResumeRun,
  onResumeNode,
  onSubmitHitlResponse,
  onResumeEdgeDownstream,
  onClearTraceScope,
  onPromoteNode,
  onDesignGolden,
  compareTabs,
  activeCandidateId,
  onSelectCandidate,
  onStartNodeCompare,
  onOpenSettings,
  onSelectGraph,
}: PanelsProps) {
  const { t } = useTranslation("panels")
  const { onFileOpen, selectedEdge } = useWorkspaceContext()
  const selectedNodeSkillId = selectedNode?.data.skillId ?? null
  const selectedNodeWorkspaceRoot = selectedNode?.data.workspaceRoot ?? null
  const selectedNodeUsesDifferentSkill = Boolean(
    selectedNode
    && (
      (selectedNodeSkillId && selectedNodeSkillId !== skillId)
      || (selectedNodeWorkspaceRoot && selectedNodeWorkspaceRoot !== (workspaceRoot ?? null))
    ),
  )
  const selectedNodeResolvedDetail = selectedNode?.data.resolvedSkillDetail
  const selectedNodeSkill = useSkills(selectedNodeUsesDifferentSkill && !selectedNodeResolvedDetail ? selectedNodeSkillId : null)
  const propertiesSkillId = selectedNodeUsesDifferentSkill ? selectedNodeSkillId : skillId
  const propertiesWorkspaceRoot = selectedNodeUsesDifferentSkill
    ? selectedNode?.data.workspaceRoot ?? null
    : workspaceRoot
  const propertiesSkillDetail = selectedNodeUsesDifferentSkill
    ? selectedNodeResolvedDetail ?? selectedNodeSkill.skillDetail
    : skillDetail
  const selectedNodeEditTarget = selectedNodeUsesDifferentSkill && propertiesSkillId && propertiesSkillDetail
    ? {
        skillId: propertiesSkillId,
        workspaceRoot: propertiesWorkspaceRoot,
        detail: propertiesSkillDetail,
        onSettled: async () => undefined,
      } satisfies ChildSaveTarget
    : null
  const propertiesPhaseFileSave = selectedNodeUsesDifferentSkill
    ? selectedNodeEditTarget && onPhaseFileSave
      ? (payload: { path: string; content: string; expectedHash: string }) => onPhaseFileSave(payload, selectedNodeEditTarget)
      : undefined
    : onPhaseFileSave
  const propertiesPhaseRename = selectedNodeUsesDifferentSkill
    ? selectedNodeEditTarget && onPhaseRename
      ? (phaseId: string, nextPhaseId: string) => onPhaseRename(phaseId, nextPhaseId, selectedNodeEditTarget)
      : undefined
    : onPhaseRename
  const propertiesActionCreate = selectedNodeUsesDifferentSkill
    ? selectedNodeEditTarget && onActionCreate
      ? (phaseId: string, name: string) => onActionCreate(phaseId, name, selectedNodeEditTarget)
      : undefined
    : onActionCreate
  const propertiesActionDelete = selectedNodeUsesDifferentSkill
    ? selectedNodeEditTarget && onActionDelete
      ? (phaseId: string, name: string) => onActionDelete(phaseId, name, selectedNodeEditTarget)
      : undefined
    : onActionDelete
  const propertiesValidatorCreate = selectedNodeUsesDifferentSkill
    ? selectedNodeEditTarget && onValidatorCreate
      ? (phaseId: string) => onValidatorCreate(phaseId, selectedNodeEditTarget)
      : undefined
    : onValidatorCreate
  if (!skillId) {
    return (
      <div className="flex h-full w-full flex-col bg-sidebar">
        <PanelHeader title={t("common.workspaceTitle")} />
        <div className="p-4 text-xs text-muted-foreground">{t("common.openSkillToPopulate")}</div>
      </div>
    )
  }

  if (activePanel === "assets") {
    return (
      <AssetsPanel
        skillId={skillId}
        workspaceRoot={workspaceRoot}
        skillDetail={skillDetail}
        selectedNode={selectedNode}
        directoryTree={assetDirectoryTree}
        subgraphTree={assetSubgraphTree}
      />
    )
  }
  if (activePanel === "input") {
    return (
      <InputPanel
        skillId={skillId}
        workspaceRoot={workspaceRoot}
        skillDetail={skillDetail}
        runtimeConfig={runtimeConfig}
        selectedNode={selectedNode}
        ioBoundary={ioBoundary ?? null}
        lintErrors={lintErrors}
        selectedTestInputId={selectedTestInputId ?? null}
        onSelectTestInput={onSelectTestInput}
        onRuntimeArtifactsSave={onRuntimeArtifactsSave}
        onRuntimeConfigRefresh={onRuntimeConfigRefresh}
        onFileOpen={onFileOpen}
        onPhaseFileSave={onPhaseFileSave}
      />
    )
  }
  if (activePanel === "trace") {
    // 选中即范围 (decision 2026-08-13 D6): whatever is selected on the canvas
    // is the trace's display scope — an edge outranks a node outranks a
    // boundary, matching what the user most recently anchored. The old
    // EdgeContextView swap is retired (D5): an edge now scopes the SAME trace
    // panel, whose rows are the edge-op events themselves.
    const traceScope: TraceScope | null = selectedEdge
      ? { kind: "edge", source: selectedEdge.source, target: selectedEdge.target }
      : selectedNode
      ? { kind: "node", phase: selectedNode.id }
      : ioBoundary
      ? { kind: ioBoundary }
      : null
    // viewed-run model (decision 2026-08-07): the region shows the run the user
    // is LOOKING AT, not whichever run last streamed. Live view keeps every run
    // action; a historical view is a read-only replay of the same TracePanel.
    // What you can do to the focused NODE is a fact about the selection, not
    // about whether a run exists, so it is rendered by the REGION — above the
    // run list just as much as above a trace. Putting it inside TracePanel made
    // it unreachable on a skill that had never run, which is exactly the skill
    // whose nodes still need a golden written down (ledger CP4).
    const focusedNodeActions = (
      <FocusedNodeActions
        node={selectedNode}
        canPromote={traceCanCompare}
        onPromoteNode={onPromoteNode}
        onDesignGolden={onDesignGolden}
      />
    )
    // Which candidate's side-run am I looking at — a question about the compare
    // GROUP, not about the base trace under it. It used to be answered inside
    // the live TracePanel, which made a group started off a historical run
    // unreachable (ledger L2 ③). Same reasoning as focusedNodeActions above.
    const compareCandidateTabs = (
      <CompareCandidateTabs
        tabs={compareTabs}
        activeCandidateId={activeCandidateId}
        onSelect={onSelectCandidate}
      />
    )
    if (traceView?.source === "live" && runId) {
      return (
        <div className="flex h-full min-h-0 flex-col">
          {compareCandidateTabs}
          {focusedNodeActions}
          <div className="min-h-0 flex-1">
        <TracePanel
          traceLogs={traceEvents ?? []}
          activePhase={activeTracePhase ?? null}
          selectedNode={selectedNode}
          onSelectEvent={onSelectTraceEvent}
          selectedEventId={traceSelectedEventId}
          onBack={onCloseTraceView}
          runId={runId}
          skillId={skillId}
          live
          canCompare={traceCanCompare}
          compareLoading={traceCompareLoading}
          onCompareToGolden={onCompareToGolden}
          onPromoteToGolden={onPromoteToGolden}
          canResume={traceCanResume}
          resumeLoading={traceResumeLoading}
          metadata={traceLiveMetadata}
          gateVerdict={traceGateVerdict}
          onResume={onResumeRun}
          hitlSubmitting={traceResumeLoading}
          onSubmitHitlResponse={onSubmitHitlResponse}
          scope={traceScope}
          onClearScope={onClearTraceScope}
          selectedEdge={selectedEdge}
          onResumeEdgeDownstream={onResumeEdgeDownstream}
          edgeResumeLoading={traceResumeLoading}
        />
          </div>
        </div>
      )
    }
    if (traceView?.source === "history") {
      return (
        <div className="flex h-full min-h-0 flex-col">
          {compareCandidateTabs}
          {focusedNodeActions}
          <div className="min-h-0 flex-1">
        <TracePanel
          traceLogs={traceEvents ?? []}
          activePhase={null}
          selectedNode={selectedNode}
          onSelectEvent={onSelectTraceEvent}
          selectedEventId={traceSelectedEventId}
          onBack={onCloseTraceView}
          runId={traceView.runId}
          metadata={traceView.metadata}
          scope={traceScope}
          onClearScope={onClearTraceScope}
          selectedEdge={selectedEdge}
          onResumeEdgeDownstream={onResumeEdgeDownstream}
          edgeResumeLoading={traceResumeLoading}
        />
          </div>
        </div>
      )
    }
    return (
      <div className="flex h-full min-h-0 flex-col">
        {compareCandidateTabs}
        {focusedNodeActions}
        <div className="min-h-0 flex-1">
          <TimelinePanel onSelectRun={onSelectRun} loadingRunId={historyLoadingRunId} />
        </div>
      </div>
    )
  }
  if (activePanel === "local-history") {
    return <HistoryPanel skillId={skillId} />
  }
  if (activePanel === "properties") {
    return (
      <PropertiesPanel
        skillId={propertiesSkillId}
        workspaceRoot={propertiesWorkspaceRoot}
        skillDetail={propertiesSkillDetail}
        selectedNode={selectedNode}
        runId={runId}
        selectedNodeStatus={selectedNodeStatus}
        resumeValidity={resumeValidity}
        resumeValidityLoading={resumeValidityLoading}
        resumeValidityError={resumeValidityError}
        resumeLoading={traceResumeLoading}
        lintErrors={lintErrors}
        onFileOpen={onFileOpen}
        onPhaseFileSave={propertiesPhaseFileSave}
        onPhaseRename={propertiesPhaseRename}
        onActionCreate={propertiesActionCreate}
        onActionDelete={propertiesActionDelete}
        onValidatorCreate={propertiesValidatorCreate}
        onResumeNode={onResumeNode}
        onOpenSettings={onOpenSettings}
        onSelectGraph={onSelectGraph}
        onStartNodeCompare={onStartNodeCompare}
      />
    )
  }
  return (
    <AssetsPanel
      skillId={skillId}
      workspaceRoot={workspaceRoot}
      skillDetail={skillDetail}
      selectedNode={selectedNode}
      directoryTree={assetDirectoryTree}
      subgraphTree={assetSubgraphTree}
    />
  )
}
