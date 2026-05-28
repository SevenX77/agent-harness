import { Brain, Check, Loader2, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import type { RoleChainStatus } from "@/hooks/useRoleTestChainRunner"
import type { ModelAvailability } from "../availability"

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

export function AvailabilityBadge({ availability }: { availability: ModelAvailability }) {
  if (availability === "ok") {
    return (
      <Badge variant="success" aria-label="Provider status Connected">
        Connected
      </Badge>
    )
  }
  if (availability === "key_only") {
    return (
      <Badge variant="outline" className="text-muted-foreground" aria-label="Provider status Untested">
        Untested
      </Badge>
    )
  }
  if (availability === "failed") {
    return (
      <Badge variant="destructive" className="gap-1" aria-label="Provider status Failed">
        <TriangleAlert className="size-3" />
        Failed
      </Badge>
    )
  }
  return (
    <Badge variant="destructive" className="gap-1" aria-label="Provider status Unavailable">
      <TriangleAlert className="size-3" />
      Unavailable
    </Badge>
  )
}

export function ProviderTestStatusBadge({ status, message }: { status: RoleChainStatus; message?: string }) {
  const label = statusLabel(status)
  const variant = status === "ok"
    ? "success"
    : status === "testing"
      ? "outline"
      : status === "idle"
        ? "secondary"
        : "destructive"

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge variant={variant} className="gap-1" aria-label={`Provider test status ${label}`}>
            {status === "testing" ? <Loader2 className="size-3 animate-spin" /> : null}
            <StatusDot status={status} />
            {label}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{message || `Provider test status: ${label}`}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export function ProviderTestStatusLight({ status, message }: { status: RoleChainStatus; message?: string }) {
  const label = statusLabel(status)

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            role="status"
            aria-label={`Provider test status ${label}`}
            data-provider-status-light="true"
            data-provider-status={status}
            className={cn(
              "inline-flex size-1.5 shrink-0 rounded-full ring-1 ring-offset-0",
              providerStatusLightClass(status),
            )}
          />
        </TooltipTrigger>
        <TooltipContent>{message || `Provider test status: ${label}`}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
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

function providerStatusLightClass(status: RoleChainStatus): string {
  if (status === "ok") return "bg-success ring-success-border"
  if (status === "testing") return "animate-pulse bg-primary ring-primary/30"
  if (status === "idle") return "bg-muted-foreground/70 ring-border"
  return "bg-destructive ring-destructive-border"
}

function StatusDot({ status }: { status: RoleChainStatus }) {
  const className = status === "ok"
    ? "bg-success"
    : status === "testing"
      ? "bg-primary"
      : status === "idle"
        ? "bg-muted-foreground"
        : "bg-destructive"
  return <span aria-hidden="true" className={`size-1.5 rounded-full ${className}`} />
}

function statusLabel(status: RoleChainStatus): string {
  if (status === "ok") return "Connected"
  if (status === "testing") return "Testing"
  if (status === "missing_api_key") return "Not configured"
  if (status === "invalid_key") return "Invalid key"
  if (status === "rate_limited") return "Rate limited"
  if (status === "quota_exceeded") return "Quota exceeded"
  if (status === "network_error") return "Network error"
  if (status === "timeout") return "Timeout"
  if (status === "idle") return "Untested"
  return "Failed"
}
