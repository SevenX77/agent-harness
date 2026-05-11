import { ChevronDown, Code2, Maximize2, Minimize2, PanelBottomOpen, Workflow } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { Canvas } from "./canvas"
import { CodeEditor } from "./code-editor"
import type { FileMeta } from "./panels"

type LayoutMode = "split" | "editor-only" | "mini-only"
type TopViewMode = "code" | "node"

interface SplitEditorProps {
  file: FileMeta
  layoutMode: LayoutMode
  topViewMode: TopViewMode
  onLayoutModeChange: (mode: LayoutMode) => void
  onTopViewModeChange: (mode: TopViewMode) => void
}

export function SplitEditor({
  file,
  layoutMode,
  topViewMode,
  onLayoutModeChange,
  onTopViewModeChange,
}: SplitEditorProps) {
  if (layoutMode === "mini-only") {
    return (
      <div className="relative size-full">
        <Canvas compact />
        <MiniToolbar
          layoutMode={layoutMode}
          onCollapse={() => onLayoutModeChange("editor-only")}
          onToggleFullscreen={() => onLayoutModeChange("split")}
        />
      </div>
    )
  }

  if (layoutMode === "editor-only") {
    return (
      <div className="relative size-full">
        {topViewMode === "code" ? <CodeEditor file={file} /> : <Canvas />}
        <TopToolbar
          topViewMode={topViewMode}
          onChange={onTopViewModeChange}
          extra={
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={() => onLayoutModeChange("split")}
              title="Show mini canvas"
            >
              <PanelBottomOpen />
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <ResizablePanelGroup
      id="studio-canvas-v"
      orientation="vertical"
      className="size-full"
    >
      <ResizablePanel id="top-editor" defaultSize="70%" minSize="30%">
        <div className="relative size-full">
          {topViewMode === "code" ? <CodeEditor file={file} /> : <Canvas />}
          <TopToolbar topViewMode={topViewMode} onChange={onTopViewModeChange} />
        </div>
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel id="bottom-mini" defaultSize="30%" minSize="15%" maxSize="60%">
        <div className="relative size-full">
          <Canvas compact />
          <MiniToolbar
            layoutMode={layoutMode}
            onCollapse={() => onLayoutModeChange("editor-only")}
            onToggleFullscreen={() => onLayoutModeChange("mini-only")}
          />
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}

function TopToolbar({
  topViewMode,
  onChange,
  extra,
}: {
  topViewMode: TopViewMode
  onChange: (mode: TopViewMode) => void
  extra?: React.ReactNode
}) {
  return (
    <div className="absolute top-3 left-3 z-10 inline-flex items-center gap-0.5 bg-card border border-border rounded-md p-0.5 shadow-sm">
      <Button
        variant={topViewMode === "node" ? "secondary" : "ghost"}
        size="icon-xs"
        onClick={() => onChange("node")}
        title="Node view"
        aria-pressed={topViewMode === "node"}
      >
        <Workflow />
      </Button>
      <Button
        variant={topViewMode === "code" ? "secondary" : "ghost"}
        size="icon-xs"
        onClick={() => onChange("code")}
        title="Code edit"
        aria-pressed={topViewMode === "code"}
      >
        <Code2 />
      </Button>
      {extra}
    </div>
  )
}

function MiniToolbar({
  layoutMode,
  onCollapse,
  onToggleFullscreen,
}: {
  layoutMode: LayoutMode
  onCollapse: () => void
  onToggleFullscreen: () => void
}) {
  return (
    <div className="absolute top-2 right-2 z-10 inline-flex items-center gap-0.5 bg-card border border-border rounded-md p-0.5 shadow-sm">
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={onCollapse}
        title="Hide mini canvas"
      >
        <ChevronDown />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={onToggleFullscreen}
        title={layoutMode === "mini-only" ? "Exit fullscreen" : "Fullscreen mini canvas"}
      >
        {layoutMode === "mini-only" ? <Minimize2 /> : <Maximize2 />}
      </Button>
    </div>
  )
}
