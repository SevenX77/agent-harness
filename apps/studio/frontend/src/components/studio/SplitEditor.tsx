import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import type { ReactNode } from "react"
import { LazyMonacoPanel } from "./LazyMonacoPanel"
import { useWorkspaceContext, type EditorSide, type OpenFile } from "./WorkspaceContext"

interface SplitEditorProps {
  canvas: ReactNode
}

export function SplitEditor({ canvas }: SplitEditorProps) {
  const {
    activeFileDetails,
    editorLintResult,
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
        initialLintResult={editorLintResult}
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
  const hasOpenFile = Boolean(activeFileDetails.left || activeFileDetails.right)

  return (
    <div
      className={hasOpenFile
        ? "grid size-full grid-rows-[minmax(0,70%)_1px_minmax(0,30%)]"
        : "grid size-full grid-rows-[minmax(0,1fr)]"}
    >
      {hasOpenFile
        ? [
            <div key="top-editor" className="min-h-0 overflow-hidden">
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
            </div>,
            <div key="editor-canvas-divider" className="bg-border" />,
          ]
        : null}
      <div key="canvas-panel" className={hasOpenFile ? "min-h-0 border-t border-border" : "min-h-0"}>
        {canvas}
      </div>
    </div>
  )
}
