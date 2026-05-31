import { Brain, Check, Loader2, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"

export function RoleSaveStatusBadge({ status }: { status: SaveStatus }) {
  if (status === "idle") return null
  if (status === "pending" || status === "saving") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        {status === "pending" ? "Pending" : "Saving"}
      </Badge>
    )
  }
  if (status === "saved") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal">
        <Check className="size-3" />
        Saved
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 text-[10px] font-normal">
      <TriangleAlert className="size-3" />
      Save failed
    </Badge>
  )
}

export function ThinkingBadge() {
  return (
    <Badge
      variant="outline"
      data-thinking-badge="true"
      className="shrink-0 gap-1 px-1.5 text-[9px]"
      aria-label="Thinking capable"
    >
      <Brain className="size-3" />
      <span className="hidden xl:inline text-[9px] leading-none">Thinking</span>
    </Badge>
  )
}
