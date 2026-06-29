import type { ReactNode } from "react"
import { X } from "lucide-react"
import { OverlayResizeHandle } from "./OverlayResizeHandle"

export const LEFT_PANEL_MIN_WIDTH = 280
export const LEFT_PANEL_MAX_WIDTH = 720

interface WorkspaceLeftPanelOverlayProps {
  children: ReactNode
  onClose: () => void
  width: number
  onResize: (widthPx: number) => void
}

export function WorkspaceLeftPanelOverlay({ children, onClose, width, onResize }: WorkspaceLeftPanelOverlayProps) {
  return (
    <section
      aria-label="Workspace panel"
      data-studio-left-overlay="true"
      className="studio-left-panel-overlay pointer-events-auto absolute bottom-3 left-3 top-3 z-30 flex min-h-0 flex-col overflow-hidden rounded-lg border text-card-foreground"
      style={{ width: `${width}px`, maxWidth: "calc(100% - 1.5rem)" }}
    >
      <button
        type="button"
        aria-label="Close panel"
        onClick={onClose}
        className="absolute right-3 top-3 z-10 inline-flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <X className="size-3.5" aria-hidden />
      </button>
      <div data-studio-left-panel-content="true" className="flex h-full min-h-0 flex-1">
        {children}
      </div>
      <OverlayResizeHandle
        side="right"
        min={LEFT_PANEL_MIN_WIDTH}
        max={LEFT_PANEL_MAX_WIDTH}
        onResize={onResize}
        ariaLabel="Resize panel"
      />
    </section>
  )
}
