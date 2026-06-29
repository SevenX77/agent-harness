import type { ReactNode } from "react"

export function PanelHeader({ title, extra, right }: { title: string; extra?: ReactNode; right?: ReactNode }) {
  return (
    <div data-studio-panel-header="true" className="flex h-10 shrink-0 items-center justify-between gap-3 px-3 pr-12">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="text-xs font-medium text-foreground">{title}</span>
        {extra}
      </div>
      {right ? <div className="flex shrink-0 items-center">{right}</div> : null}
    </div>
  )
}
