import type { ReactNode } from "react"

export function PanelHeader({ title, extra }: { title: string; extra?: ReactNode }) {
  return (
    <div data-studio-panel-header="true" className="flex h-10 shrink-0 items-center px-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-foreground">{title}</span>
        {extra}
      </div>
    </div>
  )
}
