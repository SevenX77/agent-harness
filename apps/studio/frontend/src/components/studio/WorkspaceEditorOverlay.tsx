import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import type { ReactNode } from "react"
import { LazyMonacoPanel } from "./LazyMonacoPanel"
import { useWorkspaceContext, type EditorSide, type OpenFile } from "./WorkspaceContext"

interface WorkspaceEditorOverlayProps {
  children?: ReactNode
}

export function WorkspaceEditorOverlay({ children }: WorkspaceEditorOverlayProps) {
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
        <div className="grid size-full place-items-center bg-transparent text-sm text-muted-foreground">
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
  const hasOpenFile = Boolean(activeFileDetails.left || activeFileDetails.right)

  if (!hasOpenFile) {
    return <>{children}</>
  }

  return (
    <>
      {children}
      <section
        aria-label="File editor"
        data-studio-editor-overlay="true"
        className="studio-editor-overlay absolute top-3 z-30 flex min-h-0 overflow-hidden rounded-lg border text-card-foreground"
      >
        {splitMode ? (
          <ResizablePanelGroup id="studio-overlay-editor-h" orientation="horizontal" className="size-full">
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
      </section>
    </>
  )
}
