import type { ResumeRunOptions } from "@/api/client"
import type { CallbackEvent, EventEnvelope, LintError, ResumeValidityResponse, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData, SkillNodeStatus } from "@/components/GraphCanvas"
import type { ChildSaveTarget } from "@/components/GraphCanvas/drill-edit"
import { TraceDocumentPanel } from "@/components/MonacoPanel"
import { TracePanel, type TraceHitlResumeRequest } from "@/components/TracePanel"
import type { CompareTab } from "../run-compare"
import { useSkills } from "@/hooks/useSkills"
import { useThemeValue } from "@/store/themeStore"
import type { PanelKind } from "../Toolbar"
import type { SettingsTab } from "../SettingsPage"
import { useWorkspaceContext } from "../WorkspaceContext"
import { AssetsPanel } from "./AssetsPanel"
import { HistoryPanel } from "./HistoryPanel"
import { InputPanel } from "./InputPanel"
import type { IoBoundarySelection } from "./io-target"
import { PanelHeader } from "./_shared/PanelHeader"
import { EdgeContextView } from "./EdgeContextView"
import { PropertiesPanel } from "./PropertiesPanel"
import { TimelinePanel } from "./TimelinePanel"
import type { SubgraphMembershipTree } from "./use-subgraph-membership-tree"
import type { WorkspaceDirectoryTree } from "./use-workspace-directory-tree"

interface PanelsProps {
  activePanel: PanelKind
  skillId: string | null
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  assetDirectoryTree?: WorkspaceDirectoryTree
  assetSubgraphTree?: SubgraphMembershipTree
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  /** Which boundary pseudo-node is selected, so the i/o panel scopes by role. */
  ioBoundary?: IoBoundarySelection
  // F4: i/o-panel test-input selection that feeds Predict/Run.
  selectedTestInputId?: string | null
  onSelectTestInput?: (id: string | null) => void
  onPhaseFileSave?: (
    payload: { path: string; content: string; expectedHash: string },
    target?: ChildSaveTarget,
  ) => Promise<void> | void
  onPhaseRename?: (phaseId: string, nextPhaseId: string, target?: ChildSaveTarget) => Promise<void> | void
  onActionCreate?: (phaseId: string, name: string, target?: ChildSaveTarget) => Promise<void> | void
  onActionDelete?: (phaseId: string, name: string, target?: ChildSaveTarget) => Promise<void> | void
  onValidatorCreate?: (phaseId: string, target?: ChildSaveTarget) => Promise<void> | void
  // trace-observability F1: while a run is active the timeline region streams
  // live trace events (TracePanel); with no active run it shows run history (F2).
  runId?: string | null
  selectedNodeStatus?: SkillNodeStatus | null
  resumeValidity?: ResumeValidityResponse | null
  resumeValidityLoading?: boolean
  resumeValidityError?: string | null
  // Field-axis diagnostics for the Properties panel (engine field_path projection).
  lintErrors?: LintError[] | null
  traceEvents?: EventEnvelope[]
  activeTracePhase?: string | null
  onSelectTracePrompt?: (index: number) => void
  traceCanCompare?: boolean
  traceCompareLoading?: boolean
  onCompareToGolden?: () => void
  onPromoteToGolden?: () => void
  traceCanResume?: boolean
  traceResumeLoading?: boolean
  onResumeRun?: () => void
  onResumeNode?: (options: ResumeRunOptions) => Promise<void> | void
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
  onResumeEdgeDownstream?: (options: ResumeRunOptions) => Promise<void> | void
  /** Per-node golden promote (atom #32), surfaced in the node Properties panel. */
  onPromoteNode?: (nodeId: string) => Promise<void> | void
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
  assetDirectoryTree,
  assetSubgraphTree,
  selectedNode,
  ioBoundary,
  selectedTestInputId,
  onSelectTestInput,
  onPhaseFileSave,
  onPhaseRename,
  onActionCreate,
  onActionDelete,
  onValidatorCreate,
  runId,
  selectedNodeStatus,
  resumeValidity,
  resumeValidityLoading,
  resumeValidityError,
  lintErrors,
  traceEvents,
  activeTracePhase,
  onSelectTracePrompt,
  traceCanCompare,
  traceCompareLoading,
  onCompareToGolden,
  onPromoteToGolden,
  traceCanResume,
  traceResumeLoading,
  onResumeRun,
  onResumeNode,
  onSubmitHitlResponse,
  onResumeEdgeDownstream,
  onPromoteNode,
  compareTabs,
  activeCandidateId,
  onSelectCandidate,
  onStartNodeCompare,
  onOpenSettings,
  onSelectGraph,
}: PanelsProps) {
  const { onFileOpen, selectedEdge, setSelectedEdge } = useWorkspaceContext()
  const isDarkMode = useThemeValue() === "dark"
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
        <PanelHeader title="Workspace" />
        <div className="p-4 text-xs text-muted-foreground">Open a skill to populate this panel.</div>
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
        selectedNode={selectedNode}
        ioBoundary={ioBoundary ?? null}
        selectedTestInputId={selectedTestInputId ?? null}
        onSelectTestInput={onSelectTestInput}
        onFileOpen={onFileOpen}
        onPhaseFileSave={onPhaseFileSave}
      />
    )
  }
  if (activePanel === "timeline") {
    if (selectedEdge) {
      return (
        <EdgeContextView
          selectedEdge={selectedEdge}
          onClear={() => setSelectedEdge?.(null)}
          onResumeDownstream={onResumeEdgeDownstream}
          resumeLoading={traceResumeLoading}
        />
      )
    }
    // Active run → live trace stream; otherwise the run-history list.
    if (runId) {
      return (
        <TracePanel
          traceLogs={traceEvents ?? []}
          activePhase={activeTracePhase ?? null}
          selectedNode={selectedNode}
          onSelectPrompt={onSelectTracePrompt ?? (() => undefined)}
          canCompare={traceCanCompare}
          compareLoading={traceCompareLoading}
          onCompareToGolden={onCompareToGolden}
          onPromoteToGolden={onPromoteToGolden}
          onPromoteNode={onPromoteNode}
          canResume={traceCanResume}
          resumeLoading={traceResumeLoading}
          onResume={onResumeRun}
          hitlSubmitting={traceResumeLoading}
          onSubmitHitlResponse={onSubmitHitlResponse}
          compareTabs={compareTabs}
          activeCandidateId={activeCandidateId}
          onSelectCandidate={onSelectCandidate}
        />
      )
    }
    return <TimelinePanel />
  }
  if (activePanel === "trace-doc") {
    // n4-trace #18: the same run-stream events the live Event Trace panel renders,
    // projected into a read-only full-trace document. Run-stream payloads arrive as
    // EventEnvelope; unwrap to the CallbackEvent the document builder consumes (same
    // unwrap TracePanel does). Focus the document on the canvas-selected node so its
    // line-jump stays in lockstep with node focus.
    const traceDocumentEvents: CallbackEvent[] = (traceEvents ?? []).map((event) => event.payload)
    return (
      <TraceDocumentPanel
        events={traceDocumentEvents}
        isDarkMode={isDarkMode}
        focusNodeId={selectedNode?.id ?? null}
      />
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
        onPromoteNode={onPromoteNode}
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
