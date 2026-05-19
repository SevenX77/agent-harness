import type { ReactNode } from "react"
import { Label } from "@/components/ui/label"

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
    <div className="flex items-start justify-between gap-6 py-3">
      <div className="min-w-0 flex-1">
        <Label className="text-xs font-medium text-foreground">{label}</Label>
        {description ? <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  )
}
