import type { ReactNode } from "react"
import { OverlayResizeHandle } from "./OverlayResizeHandle"

export const RIGHT_PANEL_MIN_WIDTH = 280
export const RIGHT_PANEL_MAX_WIDTH = 720

interface WorkspaceRightPanelOverlayProps {
  children: ReactNode
  width: number
  onResize: (widthPx: number) => void
}

export function WorkspaceRightPanelOverlay({ children, width, onResize }: WorkspaceRightPanelOverlayProps) {
  return (
    <section
      aria-label="Copilot panel"
      data-studio-right-overlay="true"
      className="studio-right-panel-overlay pointer-events-auto absolute bottom-3 right-3 top-3 z-30 flex min-h-0 overflow-hidden rounded-lg border text-card-foreground"
      style={{ width: `${width}px`, maxWidth: "calc(100% - 1.5rem)" }}
    >
      {children}
      <OverlayResizeHandle
        side="left"
        min={RIGHT_PANEL_MIN_WIDTH}
        max={RIGHT_PANEL_MAX_WIDTH}
        onResize={onResize}
        ariaLabel="Resize Copilot panel"
      />
    </section>
  )
}
