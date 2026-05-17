import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { GraphCanvas, type SkillGraphNodeData } from "@/components/GraphCanvas"
import type { SkillDetail } from "@/api/types"
import { LazyMonacoPanel } from "./LazyMonacoPanel"
import { useWorkspaceContext, type EditorSide, type OpenFile } from "./WorkspaceContext"

interface SplitEditorProps {
  skillId: string
  skillDetail?: SkillDetail
  isLoading?: boolean
  error?: unknown
  selectedNodeId?: string | null
  onNodeSelect?: (node: { id: string; data: SkillGraphNodeData }) => void
}

export function SplitEditor({
  skillId,
  skillDetail,
  isLoading,
  error,
  selectedNodeId,
  onNodeSelect,
}: SplitEditorProps) {
  const {
    activeFileDetails,
    closeFile,
    updateFileContent,
    markFileSaved,
    setFileInFlight,
    onSaveConflict,
  } = useWorkspaceContext()

  const renderEditor = (side: EditorSide, file: OpenFile | undefined) => {
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
      />
    )
  }

  return (
    <ResizablePanelGroup
      id="studio-canvas-v"
      orientation="vertical"
      className="size-full"
    >
      <ResizablePanel id="top-editor" defaultSize="70%" minSize="30%">
        <ResizablePanelGroup id="studio-split-editor-h" orientation="horizontal" className="size-full">
          <ResizablePanel id="editor-left" defaultSize="50%" minSize="25%">
            {renderEditor("left", activeFileDetails.left)}
          </ResizablePanel>
          <ResizableHandle />
          <ResizablePanel id="editor-right" defaultSize="50%" minSize="25%">
            {renderEditor("right", activeFileDetails.right)}
          </ResizablePanel>
        </ResizablePanelGroup>
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel id="bottom-mini" defaultSize="30%" minSize="15%" maxSize="60%">
        <div className="size-full border-t border-border">
          {/* TODO: switch to compact mode when GraphCanvas exposes a compact prop. */}
          <GraphCanvas
            skillId={skillId}
            skillDetail={skillDetail}
            isLoading={isLoading}
            error={error}
            selectedNodeId={selectedNodeId}
            onNodeSelect={onNodeSelect}
          />
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
