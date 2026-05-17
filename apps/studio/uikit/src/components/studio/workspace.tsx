import { useState } from "react"
import { Header } from "./header"
import { Toolbar } from "./toolbar"
import { Canvas } from "./canvas"
import { SplitEditor } from "./split-editor"
import { Copilot } from "./copilot"
import { CenterActionBar } from "./center-action-bar"
import { SettingsPage } from "./settings-page"
import {
  AssetsPanel,
  InputPanel,
  TimelinePanel,
  PropertiesPanel,
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
  const [settingsOpen, setSettingsOpen] = useState(false)

  const handleFileOpen = (file: FileMeta) => {
    setOpenFile(file)
    setSettingsOpen(false)
  }
  const handleCloseFile = () => setOpenFile(null)

  const renderPanel = () => {
    switch (activePanel) {
      case "assets":
        return <AssetsPanel onFileOpen={handleFileOpen} />
      case "input":
        return <InputPanel onFileOpen={handleFileOpen} />
      case "timeline":
        return <TimelinePanel />
      case "properties":
        return <PropertiesPanel />
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

      <div className="flex-1 flex min-h-0 relative">
        <Toolbar
          activePanel={activePanel}
          onPanelChange={setActivePanel}
          onSettingsOpen={() => setSettingsOpen(true)}
        />

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
            <div className="relative size-full">
              {settingsOpen ? (
                <SettingsPage onClose={() => setSettingsOpen(false)} />
              ) : (
                <>
                  {openFile ? (
                    <SplitEditor file={openFile} onCloseFile={handleCloseFile} />
                  ) : (
                    <Canvas />
                  )}
                  <CenterActionBar />
                </>
              )}
            </div>
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
                <Copilot />
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>

      </div>
    </div>
  )
}
