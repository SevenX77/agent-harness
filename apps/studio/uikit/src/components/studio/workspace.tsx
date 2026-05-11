import { useState } from "react"
import { Header } from "./header"
import { Toolbar } from "./toolbar"
import { Canvas } from "./canvas"
import { SplitEditor, type ViewMode } from "./split-editor"
import { Copilot, CopilotButton } from "./copilot"
import {
  AssetsPanel,
  TimelinePanel,
  PropertiesPanel,
  EditorPanel,
  type FileMeta,
} from "./panels"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"

export function Workspace() {
  const [activePanel, setActivePanel] = useState<string | null>("assets")
  const [copilotOpen, setCopilotOpen] = useState(true)
  const [openFile, setOpenFile] = useState<FileMeta | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>("split")

  const handleFileOpen = (file: FileMeta) => {
    setOpenFile(file)
    setViewMode("split")
  }

  const renderPanel = () => {
    switch (activePanel) {
      case "assets":
        return <AssetsPanel onClose={() => setActivePanel(null)} onFileOpen={handleFileOpen} />
      case "timeline":
        return <TimelinePanel onClose={() => setActivePanel(null)} />
      case "properties":
        return <PropertiesPanel onClose={() => setActivePanel(null)} />
      case "editor":
        return <EditorPanel onClose={() => setActivePanel(null)} />
      default:
        return null
    }
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-background overflow-hidden">
      <Header
        projectName="Text Generator Skill"
        status="compiled"
        copilotOpen={copilotOpen}
        onCopilotToggle={() => setCopilotOpen((v) => !v)}
      />

      <div className="flex-1 flex min-h-0">
        <Toolbar activePanel={activePanel} onPanelChange={setActivePanel} />

        <ResizablePanelGroup
          id="studio-workspace-h"
          orientation="horizontal"
          className="flex-1"
        >
          {activePanel && (
            <>
              <ResizablePanel
                id="left-panel"
                defaultSize="20%"
                minSize="14%"
                maxSize="35%"
              >
                {renderPanel()}
              </ResizablePanel>
              <ResizableHandle />
            </>
          )}

          <ResizablePanel id="canvas" defaultSize="60%" minSize="30%">
            {openFile ? (
              <SplitEditor
                file={openFile}
                viewMode={viewMode}
                onViewModeChange={setViewMode}
              />
            ) : (
              <Canvas />
            )}
          </ResizablePanel>

          {copilotOpen && (
            <>
              <ResizableHandle />
              <ResizablePanel
                id="copilot"
                defaultSize="20%"
                minSize="18%"
                maxSize="35%"
              >
                <Copilot onClose={() => setCopilotOpen(false)} />
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      </div>

      {!copilotOpen && (
        <CopilotButton onClick={() => setCopilotOpen(true)} />
      )}
    </div>
  )
}
