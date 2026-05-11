import { Code2, Rows2, Workflow } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { Canvas } from "./canvas"
import { CodeEditor } from "./code-editor"
import type { FileMeta } from "./panels"

export type ViewMode = "editor" | "split" | "canvas"

interface SplitEditorProps {
  file: FileMeta
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
}

export function SplitEditor({ file, viewMode, onViewModeChange }: SplitEditorProps) {
  if (viewMode === "editor") {
    return (
      <div className="relative size-full">
        <CodeEditor file={file} />
        <ViewModeToolbar viewMode={viewMode} onChange={onViewModeChange} />
      </div>
    )
  }

  if (viewMode === "canvas") {
    return (
      <div className="relative size-full">
        <Canvas />
        <ViewModeToolbar viewMode={viewMode} onChange={onViewModeChange} />
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
        <CodeEditor file={file} />
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel id="bottom-mini" defaultSize="30%" minSize="15%" maxSize="60%">
        <div className="relative size-full border-t border-border">
          <Canvas compact />
          <ViewModeToolbar viewMode={viewMode} onChange={onViewModeChange} />
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}

function ViewModeToolbar({
  viewMode,
  onChange,
}: {
  viewMode: ViewMode
  onChange: (mode: ViewMode) => void
}) {
  return (
    <div className="absolute top-3 right-3 z-20 inline-flex items-center gap-0.5 bg-card border border-border rounded-md p-0.5 shadow-sm">
      <Button
        variant={viewMode === "editor" ? "secondary" : "ghost"}
        size="icon-xs"
        onClick={() => onChange("editor")}
        title="Editor only"
        aria-pressed={viewMode === "editor"}
      >
        <Code2 />
      </Button>
      <Button
        variant={viewMode === "split" ? "secondary" : "ghost"}
        size="icon-xs"
        onClick={() => onChange("split")}
        title="Split view"
        aria-pressed={viewMode === "split"}
      >
        <Rows2 />
      </Button>
      <Button
        variant={viewMode === "canvas" ? "secondary" : "ghost"}
        size="icon-xs"
        onClick={() => onChange("canvas")}
        title="Canvas only"
        aria-pressed={viewMode === "canvas"}
      >
        <Workflow />
      </Button>
    </div>
  )
}
