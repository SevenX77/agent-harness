import type { ReactNode } from "react"
import { OverlayResizeHandle } from "./OverlayResizeHandle"

export const RIGHT_PANEL_MIN_WIDTH = 280
export const RIGHT_PANEL_MAX_WIDTH = 720

interface WorkspaceRightPanelOverlayProps {
  children: ReactNode
  width: number
  onResize: (widthPx: number) => void
  // Drives the open/close animation. The panel grows out of / collapses into
  // the bottom-right MoirAI FAB (origin-bottom-right). Fade always plays; the
  // zoom + slide are motion-safe only, so reduced-motion degrades to a fade.
  state?: "open" | "closed"
}

export function WorkspaceRightPanelOverlay({ children, width, onResize, state = "open" }: WorkspaceRightPanelOverlayProps) {
  return (
    <section
      aria-label="Copilot panel"
      data-studio-right-overlay="true"
      data-state={state}
      className="studio-right-panel-overlay pointer-events-auto absolute bottom-3 right-3 top-3 z-30 flex min-h-0 origin-bottom-right overflow-hidden rounded-lg border text-card-foreground duration-200 ease-out data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0 motion-safe:data-[state=closed]:zoom-out-95 motion-safe:data-[state=closed]:slide-out-to-bottom-4 motion-safe:data-[state=closed]:slide-out-to-right-4 motion-safe:data-[state=open]:zoom-in-95 motion-safe:data-[state=open]:slide-in-from-bottom-4 motion-safe:data-[state=open]:slide-in-from-right-4"
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
