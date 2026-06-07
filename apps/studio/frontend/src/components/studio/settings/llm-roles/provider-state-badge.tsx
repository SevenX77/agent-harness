import { Circle, CircleX, History, PauseCircle, Timer, Check } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { ProviderUiState } from "@/api/llm"
import { cn } from "@/lib/utils"

interface ProviderStateBadgeProps {
  state: ProviderUiState
  reasonCode?: string | null
  detail?: string | null
  retryAt?: string | null
  className?: string
}

const providerStateMeta: Record<ProviderUiState, {
  label: string
  variant: "success" | "outline" | "destructive" | "secondary" | "warning"
  className?: string
  description: string
  Icon: typeof Check
}> = {
  ready: {
    label: "Ready",
    variant: "success",
    description: "Can be used now.",
    Icon: Check,
  },
  historical_ready: {
    label: "Previously Connected",
    variant: "outline",
    className: "border-multimodal-border bg-success/10 text-foreground",
    description: "Previously connected from historical probe evidence; test again before treating it as ready.",
    Icon: History,
  },
  untested: {
    label: "Untested",
    variant: "outline",
    description: "Can be tried, but capability details are not verified yet.",
    Icon: Circle,
  },
  cooling_down: {
    label: "Cooling Down",
    variant: "warning",
    description: "Temporarily paused after a runtime issue.",
    Icon: Timer,
  },
  failed: {
    label: "Failed",
    variant: "destructive",
    description: "Blocked until configuration or model failure is fixed.",
    Icon: CircleX,
  },
  off: {
    label: "Off",
    variant: "secondary",
    description: "Turned off.",
    Icon: PauseCircle,
  },
}

export function ProviderStateBadge({
  state,
  reasonCode,
  detail,
  retryAt,
  className,
}: ProviderStateBadgeProps) {
  const meta = providerStateMeta[state]
  const Icon = meta.Icon
  const tooltip = [
    meta.description,
    reasonDetail(reasonCode, detail),
    state === "cooling_down" && retryAt ? `Retry at ${retryAt}.` : null,
  ].filter(Boolean).join(" ")

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant={meta.variant}
            data-provider-state-label={state}
            aria-label={`Provider state ${meta.label}`}
            className={cn("gap-1", meta.className, className)}
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

function reasonDetail(reasonCode?: string | null, detail?: string | null): string | null {
  if (detail) return detail
  if (!reasonCode) return null
  if (reasonCode === "missing_config") return "Missing API key or required provider configuration."
  if (reasonCode === "endpoint_unreachable") return "Provider endpoint is unreachable."
  if (reasonCode === "model_failed") return "Model probe failed."
  if (reasonCode === "missing_key") return "Missing API key."
  if (reasonCode === "invalid_key") return "API key did not authenticate."
  if (reasonCode === "invalid_model") return "This model is not accepted by the provider."
  if (reasonCode === "invalid_base_url") return "Base URL is invalid or unreachable."
  if (reasonCode === "invalid_protocol") return "Selected SDK does not match this provider."
  if (reasonCode === "unsupported_parameter") return "Current settings include an unsupported parameter."
  if (reasonCode === "rate_limited") return "Provider rate limit was hit."
  return "Additional diagnostics are available."
}
