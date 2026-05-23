import type { ReactNode } from "react"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

export function NavButton({
  active,
  icon,
  children,
  onClick,
}: {
  active: boolean
  icon: ReactNode
  children: ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-xs transition-colors [&_svg]:size-3.5",
        active ? "bg-sidebar-accent text-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
      )}
    >
      {icon}
      {children}
    </button>
  )
}

export function SectionTitle({ title, description, trailing }: { title: string; description?: string; trailing?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
      </div>
      {trailing ? <div className="shrink-0">{trailing}</div> : null}
    </div>
  )
}

export function SettingRow({
  label,
  description,
  control,
}: {
  label: string
  description?: string
  control: ReactNode
}) {
  return (
    <div className="grid grid-cols-[minmax(13rem,18rem)_minmax(0,1fr)] items-start gap-6 py-3 max-lg:grid-cols-1 max-lg:gap-2">
      <div className="min-w-0">
        <Label className="text-xs font-medium text-foreground">{label}</Label>
        {description ? <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      <div className="min-w-0">{control}</div>
    </div>
  )
}
