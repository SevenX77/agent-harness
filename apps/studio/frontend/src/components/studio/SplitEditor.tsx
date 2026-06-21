import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { GraphCanvas, type SkillGraphNodeData, type SkillNodeStatus } from "@/components/GraphCanvas"
import type { CompileError, SkillDetail } from "@/api/types"
import type { GoldenNodeState } from "@/components/studio/node-golden"
import { LazyMonacoPanel } from "./LazyMonacoPanel"
import { useWorkspaceContext, type EditorSide, type OpenFile } from "./WorkspaceContext"

interface SplitEditorProps {
  skillId: string
  skillDetail?: SkillDetail
  isLoading?: boolean
  error?: unknown
  selectedNodeId?: string | null
  // The bottom mini-canvas is a READ-ONLY projection of GRAPH.md (canvas =
  // projection, per the canvas-projection design). It renders + navigates only;
  // it deliberately receives NO graph-editing handlers (connect / reconnect /
  // disconnect / create-phase / phase-file save). All graph editing happens on
  // the main canvas, so two canvases can never race writes to GRAPH.md off
  // independent snapshots. Only node selection / panel navigation is wired.
  onNodeSelect?: (node: { id: string; data: SkillGraphNodeData }) => void
  onPanelChange?: (panel: "assets" | "input" | "timeline" | "trace-doc" | "properties" | "local-history" | null) => void
  statusByNodeId?: Record<string, SkillNodeStatus>
  compileErrorsByNodeId?: Record<string, CompileError[]>
  goldenStateByNodeId?: Record<string, GoldenNodeState>
  errorMessageByNodeId?: Record<string, string>
  // N4 atom #9 (run-focus-follow): threaded to the bottom mini-canvas so the
  // split-editor canvas also auto-centers on the running node during a run.
  activeTracePhase?: string | null
}

export function SplitEditor({
  skillId,
  skillDetail,
  isLoading,
  error,
  selectedNodeId,
  onNodeSelect,
  onPanelChange,
  statusByNodeId,
  compileErrorsByNodeId,
  goldenStateByNodeId,
  errorMessageByNodeId,
  activeTracePhase,
}: SplitEditorProps) {
  const {
    activeFileDetails,
    splitMode,
    openSplitEditor,
    closeFile,
    updateFileContent,
    markFileSaved,
    setFileInFlight,
    onSaveConflict,
  } = useWorkspaceContext()

  const renderEditor = (side: EditorSide, file: OpenFile | undefined, allowSplit: boolean) => {
    if (!file) {
      return (
        <div className="grid size-full place-items-center bg-card text-sm text-muted-foreground">
          No file selected
        </div>
      )
    }
    return (
      <LazyMonacoPanel
        title={file.title ?? file.path}
        skillId={file.skillId}
        workspaceRoot={file.workspaceRoot}
        filePath={file.path}
        initialHash={file.hash}
        saveEnabled={file.saveEnabled ?? true}
        language={file.language}
        value={file.content}
        onChange={(value) => updateFileContent(side, value)}
        onSaved={(hash) => markFileSaved(side, hash)}
        onInFlightChange={(inFlight) => setFileInFlight(side, inFlight)}
        onConflict={(conflict) => onSaveConflict({ ...conflict, side })}
        onClose={() => closeFile(side)}
        onSplit={allowSplit ? openSplitEditor : undefined}
      />
    )
  }

  const primarySide: EditorSide = activeFileDetails.left ? "left" : "right"
  const primaryFile = activeFileDetails[primarySide]

  return (
    <ResizablePanelGroup
      id="studio-canvas-v"
      orientation="vertical"
      className="size-full"
    >
      <ResizablePanel id="top-editor" defaultSize="70%" minSize="30%">
        {splitMode ? (
          <ResizablePanelGroup id="studio-split-editor-h" orientation="horizontal" className="size-full">
            <ResizablePanel id="editor-left" defaultSize="50%" minSize="25%">
              {renderEditor("left", activeFileDetails.left, false)}
            </ResizablePanel>
            <ResizableHandle />
            <ResizablePanel id="editor-right" defaultSize="50%" minSize="25%">
              {renderEditor("right", activeFileDetails.right, false)}
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          renderEditor(primarySide, primaryFile, true)
        )}
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel id="bottom-mini" defaultSize="30%" minSize="15%" maxSize="60%">
        <div className="size-full border-t border-border">
          <GraphCanvas
            skillId={skillId}
            skillDetail={skillDetail}
            isLoading={isLoading}
            error={error}
            selectedNodeId={selectedNodeId}
            onNodeSelect={onNodeSelect}
            onPanelChange={onPanelChange}
            statusByNodeId={statusByNodeId}
            errorMessageByNodeId={errorMessageByNodeId}
            compileErrorsByNodeId={compileErrorsByNodeId}
            goldenStateByNodeId={goldenStateByNodeId}
            activeTracePhase={activeTracePhase}
            compact
          />
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
