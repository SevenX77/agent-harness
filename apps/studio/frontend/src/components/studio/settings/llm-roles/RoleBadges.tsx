import { Brain } from "lucide-react"
import { Badge } from "@/components/ui/badge"

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
