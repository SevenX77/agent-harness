import type { ReactNode } from "react"

interface WorkspaceRightPanelOverlayProps {
  children: ReactNode
}

export function WorkspaceRightPanelOverlay({ children }: WorkspaceRightPanelOverlayProps) {
  return (
    <section
      aria-label="Copilot panel"
      data-studio-right-overlay="true"
      className="studio-right-panel-overlay pointer-events-auto absolute bottom-3 right-3 top-3 z-30 flex min-h-0 w-[22rem] overflow-hidden rounded-lg border text-card-foreground"
    >
      {children}
    </section>
  )
}
