import type { ResumeRunOptions } from "@/api/client"
import type { CallbackEvent, EventEnvelope, LintError, ResumeValidityResponse, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData, SkillNodeStatus } from "@/components/GraphCanvas"
import { TraceDocumentPanel } from "@/components/MonacoPanel"
import { TracePanel, type TraceHitlResumeRequest } from "@/components/TracePanel"
import type { CompareTab } from "../run-compare"
import { useThemeValue } from "@/store/themeStore"
import type { PanelKind } from "../Toolbar"
import { useWorkspaceContext } from "../WorkspaceContext"
import { AssetsPanel } from "./AssetsPanel"
import { HistoryPanel } from "./HistoryPanel"
import { InputPanel } from "./InputPanel"
import { PanelHeader } from "./_shared/PanelHeader"
import { EdgeContextView } from "./EdgeContextView"
import { PropertiesPanel } from "./PropertiesPanel"
import { TimelinePanel } from "./TimelinePanel"

interface PanelsProps {
  activePanel: PanelKind
  skillId: string | null
  workspaceRoot?: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  // F4: i/o-panel test-input selection that feeds Predict/Run.
  selectedTestInputId?: string | null
  onSelectTestInput?: (id: string | null) => void
  onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
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
}

export function Panels({
  activePanel,
  skillId,
  workspaceRoot = null,
  skillDetail,
  selectedNode,
  selectedTestInputId,
  onSelectTestInput,
  onPhaseFileSave,
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
}: PanelsProps) {
  const { onFileOpen, selectedEdge, setSelectedEdge } = useWorkspaceContext()
  const isDarkMode = useThemeValue() === "dark"
  if (!skillId) {
    return (
      <div className="flex h-full w-full flex-col bg-sidebar">
        <PanelHeader title="Workspace" />
        <div className="p-4 text-xs text-muted-foreground">Open a skill to populate this panel.</div>
      </div>
    )
  }

  if (activePanel === "assets") {
    return <AssetsPanel skillDetail={skillDetail} selectedNode={selectedNode} />
  }
  if (activePanel === "input") {
    return (
      <InputPanel
        skillId={skillId}
        workspaceRoot={workspaceRoot}
        skillDetail={skillDetail}
        selectedNode={selectedNode}
        selectedTestInputId={selectedTestInputId ?? null}
        onSelectTestInput={onSelectTestInput}
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
        skillId={skillId}
        skillDetail={skillDetail}
        selectedNode={selectedNode}
        runId={runId}
        selectedNodeStatus={selectedNodeStatus}
        resumeValidity={resumeValidity}
        resumeValidityLoading={resumeValidityLoading}
        resumeValidityError={resumeValidityError}
        resumeLoading={traceResumeLoading}
        lintErrors={lintErrors}
        onFileOpen={onFileOpen}
        onPhaseFileSave={onPhaseFileSave}
        onResumeNode={onResumeNode}
        onPromoteNode={onPromoteNode}
      />
    )
  }
  return <AssetsPanel skillDetail={skillDetail} selectedNode={selectedNode} />
}
