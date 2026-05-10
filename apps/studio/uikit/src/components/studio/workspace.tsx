
import { useState } from "react"
import { Header } from "./header"
import { Toolbar } from "./toolbar"
import { Canvas } from "./canvas"
import { Copilot, CopilotButton } from "./copilot"
import { AssetsPanel, TimelinePanel, PropertiesPanel, EditorPanel } from "./panels"
import { cn } from "@/lib/utils"

export function Workspace() {
  const [activePanel, setActivePanel] = useState<string | null>("assets")
  const [panelWidth, setPanelWidth] = useState(280)
  const [copilotOpen, setCopilotOpen] = useState(false)
  const [isResizing, setIsResizing] = useState(false)

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
    
    const startX = e.clientX
    const startWidth = panelWidth
    
    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - startX
      const newWidth = Math.min(Math.max(startWidth + delta, 200), 500)
      setPanelWidth(newWidth)
    }
    
    const handleMouseUp = () => {
      setIsResizing(false)
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
    }
    
    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)
  }

  const renderPanel = () => {
    switch (activePanel) {
      case "assets":
        return <AssetsPanel onClose={() => setActivePanel(null)} />
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
    <div className={cn(
      "h-screen w-screen flex flex-col bg-background overflow-hidden",
      isResizing && "cursor-col-resize select-none"
    )}>
      <Header projectName="Text Generator Skill" status="compiled" />

      <div className="flex-1 flex min-h-0">
        <Toolbar activePanel={activePanel} onPanelChange={setActivePanel} />

        {/* Left Panel with manual resize */}
        {activePanel && (
          <div 
            className="h-full border-r border-border flex"
            style={{ width: panelWidth }}
          >
            <div className="flex-1 overflow-hidden">
              {renderPanel()}
            </div>
            {/* Resize Handle */}
            <div
              className="w-1 hover:bg-primary/50 cursor-col-resize transition-colors flex-shrink-0"
              onMouseDown={handleMouseDown}
            />
          </div>
        )}

        {/* Canvas */}
        <div className="flex-1 min-w-0">
          <Canvas />
        </div>
      </div>

      <CopilotButton onClick={() => setCopilotOpen(true)} />
      <Copilot isOpen={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  )
}
