import type { ReactNode } from "react"

export function PanelBody({ children }: { children: ReactNode }) {
  return (
    <div data-studio-panel-body="true" className="text-xs">
      {children}
    </div>
  )
}

export function PanelSection({
  children,
  className = "",
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section data-studio-panel-section="true" className={className}>
      {children}
    </section>
  )
}

export function PanelFieldRow({ children }: { children: ReactNode }) {
  return (
    <div data-studio-panel-field-row="true">
      {children}
    </div>
  )
}

export function PanelActions({ children }: { children: ReactNode }) {
  return (
    <div data-studio-panel-actions="true">
      {children}
    </div>
  )
}
