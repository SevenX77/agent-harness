import type { ReactNode } from "react"
import { X } from "lucide-react"

const LEFT_PANEL_WIDTH = "24rem"

interface WorkspaceLeftPanelOverlayProps {
  children: ReactNode
  onClose: () => void
}

export function WorkspaceLeftPanelOverlay({ children, onClose }: WorkspaceLeftPanelOverlayProps) {
  return (
    <section
      aria-label="Workspace panel"
      data-studio-left-overlay="true"
      className="studio-left-panel-overlay pointer-events-auto absolute left-3 top-3 z-30 flex h-fit min-h-0 max-h-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-lg border text-card-foreground"
      style={{ width: LEFT_PANEL_WIDTH, maxWidth: "calc(100% - 1.5rem)" }}
    >
      <button
        type="button"
        aria-label="Close panel"
        onClick={onClose}
        className="absolute right-3 top-3 z-10 inline-flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <X className="size-3.5" aria-hidden />
      </button>
      <div data-studio-left-panel-content="true" className="flex min-h-0 max-h-[inherit]">
        {children}
      </div>
    </section>
  )
}
