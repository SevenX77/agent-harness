import type { CallbackEvent, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { TracePanel } from "@/components/TracePanel"
import type { PanelKind } from "../Toolbar"
import { useWorkspaceContext } from "../WorkspaceContext"
import { AssetsPanel } from "./AssetsPanel"
import { HistoryPanel } from "./HistoryPanel"
import { InputPanel } from "./InputPanel"
import { PanelHeader } from "./_shared/PanelHeader"
import { PropertiesPanel } from "./PropertiesPanel"
import { TimelinePanel } from "./TimelinePanel"

interface PanelsProps {
  activePanel: PanelKind
  skillId: string | null
  skillDetail?: SkillDetail
  selectedNode: { id: string; data: SkillGraphNodeData } | null
  onPhaseFileSave?: (payload: { path: string; content: string; expectedHash: string }) => Promise<void> | void
  // trace-observability F1: while a run is active the timeline region streams
  // live trace events (TracePanel); with no active run it shows run history (F2).
  runId?: string | null
  traceEvents?: CallbackEvent[]
  activeTracePhase?: string | null
  onSelectTracePrompt?: (index: number) => void
  traceCanCompare?: boolean
  traceCompareLoading?: boolean
  onCompareToGolden?: () => void
  onPromoteToGolden?: () => void
}

export function Panels({
  activePanel,
  skillId,
  skillDetail,
  selectedNode,
  onPhaseFileSave,
  runId,
  traceEvents,
  activeTracePhase,
  onSelectTracePrompt,
  traceCanCompare,
  traceCompareLoading,
  onCompareToGolden,
  onPromoteToGolden,
}: PanelsProps) {
  const { onFileOpen } = useWorkspaceContext()
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
    return <InputPanel skillDetail={skillDetail} onFileOpen={onFileOpen} />
  }
  if (activePanel === "timeline") {
    // Active run → live trace stream; otherwise the run-history list.
    if (runId) {
      return (
        <TracePanel
          traceLogs={traceEvents ?? []}
          activePhase={activeTracePhase ?? null}
          onSelectPrompt={onSelectTracePrompt ?? (() => undefined)}
          canCompare={traceCanCompare}
          compareLoading={traceCompareLoading}
          onCompareToGolden={onCompareToGolden}
          onPromoteToGolden={onPromoteToGolden}
        />
      )
    }
    return <TimelinePanel />
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
        onFileOpen={onFileOpen}
        onPhaseFileSave={onPhaseFileSave}
      />
    )
  }
  return <AssetsPanel skillDetail={skillDetail} selectedNode={selectedNode} />
}
