import { CircleAlert, CircleCheck, Gauge, SlidersHorizontal } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { RoleFitState } from "@/api/llm"
import { cn } from "@/lib/utils"

interface RoleFitBadgeProps {
  fit: RoleFitState
  warnings?: Array<Record<string, unknown>>
  detail?: string | null
  className?: string
}

const roleFitMeta: Record<RoleFitState, {
  label: string
  variant: "outline" | "destructive"
  description: string
  Icon: typeof CircleCheck
}> = {
  using: {
    label: "Using",
    variant: "outline",
    description: "Included in this Role fallback order.",
    Icon: CircleCheck,
  },
  downgraded: {
    label: "Downgraded",
    variant: "outline",
    description: "Included, but settings were adjusted.",
    Icon: Gauge,
  },
  needs_test: {
    label: "Needs Test",
    variant: "outline",
    description: "Required capability is unknown.",
    Icon: CircleAlert,
  },
  not_fit: {
    label: "Not Fit",
    variant: "destructive",
    description: "Not included because required settings cannot be satisfied.",
    Icon: SlidersHorizontal,
  },
}

export function RoleFitBadge({ fit, warnings = [], detail, className }: RoleFitBadgeProps) {
  const meta = roleFitMeta[fit]
  const Icon = meta.Icon
  const warningDetail = detail ?? warningMessage(warnings)
  const tooltip = [meta.description, warningDetail].filter(Boolean).join(" ")

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant={meta.variant}
            data-role-fit-label={fit}
            aria-label={`Role fit ${meta.label}`}
            className={cn("gap-1", className)}
          >
            <Icon className="size-3" />
            {meta.label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm break-words">{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function warningMessage(warnings: Array<Record<string, unknown>>): string | null {
  const firstMessage = warnings
    .map((warning) => warning.message)
    .find((message): message is string => typeof message === "string" && message.trim().length > 0)
  return firstMessage ?? null
}
