import type { ReactNode } from "react"
import { OverlayResizeHandle } from "./OverlayResizeHandle"

export const RIGHT_PANEL_MIN_WIDTH = 280
export const RIGHT_PANEL_MAX_WIDTH = 720

// P-6: the panel's width truth is a share of the canvas host, not a pixel
// count, so enlarging the window widens the panel proportionally. 0.275 of the
// 1280px reference host reproduces the historical 352px default, which is also
// what jsdom (no ResizeObserver → host never measured) renders in tests.
export const RIGHT_PANEL_DEFAULT_RATIO = 0.275
const REFERENCE_HOST_WIDTH = 1280

export function rightPanelWidthPx(ratio: number, hostWidth: number | null): number {
  const host = hostWidth != null && hostWidth > 0 ? hostWidth : REFERENCE_HOST_WIDTH
  return Math.min(RIGHT_PANEL_MAX_WIDTH, Math.max(RIGHT_PANEL_MIN_WIDTH, Math.round(ratio * host)))
}

export function rightPanelRatioFromPx(widthPx: number, hostWidth: number | null): number {
  const host = hostWidth != null && hostWidth > 0 ? hostWidth : REFERENCE_HOST_WIDTH
  return widthPx / host
}

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
