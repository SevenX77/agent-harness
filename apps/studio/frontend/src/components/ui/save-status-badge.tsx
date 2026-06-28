import { Check, Loader2, TriangleAlert, type LucideIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import "@/i18n"

const saveStatusIcons: Record<Exclude<SaveStatus, "idle">, LucideIcon> = {
  pending: Loader2,
  saving: Loader2,
  saved: Check,
  error: TriangleAlert,
}

const saveStatusLabelKeys = {
  pending: "saveStatus.pending",
  saving: "saveStatus.saving",
  saved: "saveStatus.saved",
  error: "saveStatus.error",
} as const satisfies Record<Exclude<SaveStatus, "idle">, string>

export function SaveStatusBadge({ status }: { status: SaveStatus }) {
  const { t } = useTranslation("settings")
  if (status === "idle") return null

  const Icon = saveStatusIcons[status]
  const label = t(saveStatusLabelKeys[status])
  const isBusy = status === "pending" || status === "saving"

  return (
    <Badge
      variant={status === "error" ? "warning" : "outline"}
      className={isBusy ? "gap-1 text-[10px] font-normal text-muted-foreground" : "gap-1 text-[10px] font-normal"}
      data-save-status-badge="true"
      data-save-status={status}
      aria-label={label}
      aria-live={status === "error" ? "assertive" : "polite"}
    >
      <Icon
        className={isBusy ? "size-3 animate-spin" : "size-3"}
        data-save-status-icon="true"
        aria-hidden="true"
      />
      {label}
    </Badge>
  )
}
