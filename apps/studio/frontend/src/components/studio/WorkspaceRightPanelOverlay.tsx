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
    // The open/close animation lives in the FAB↔panel container-transform morph
    // (copilot-panel-morph.tsx); the panel surface is identical to the morph's
    // final frame, so mounting here is a seamless hand-off. Only the CONTENTS
    // fade in ([&>*]) — the surface stays solid so there is no flash.
    <section
      aria-label="Copilot panel"
      data-studio-right-overlay="true"
      className="studio-right-panel-overlay pointer-events-auto absolute bottom-3 right-3 top-3 z-30 flex min-h-0 overflow-hidden rounded-lg border text-card-foreground [&>*]:motion-safe:animate-in [&>*]:motion-safe:fade-in-0 [&>*]:motion-safe:duration-300"
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
