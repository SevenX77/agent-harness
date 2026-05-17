import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"
import { Canvas } from "./canvas"
import { CodeEditor } from "./code-editor"
import type { FileMeta } from "./panels"

interface SplitEditorProps {
  file: FileMeta
  onCloseFile: () => void
}

export function SplitEditor({ file, onCloseFile }: SplitEditorProps) {
  return (
    <ResizablePanelGroup
      id="studio-canvas-v"
      orientation="vertical"
      className="size-full"
    >
      <ResizablePanel id="top-editor" defaultSize="70%" minSize="30%">
        <CodeEditor file={file} onClose={onCloseFile} />
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel id="bottom-mini" defaultSize="30%" minSize="15%" maxSize="60%">
        <div className="size-full border-t border-border">
          <Canvas compact />
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
