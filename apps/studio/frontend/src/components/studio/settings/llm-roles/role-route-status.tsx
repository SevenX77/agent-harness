import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import type { RoleChainStatus } from "@/hooks/useRoleTestChainRunner"
import type { MaterializationReportEntry, ProviderModelOption } from "@/api/llm"

export type RoleRouteStatus = "runnable" | "limited" | "blocked" | "testing"

interface RoleRouteStatusInput {
  providerModel?: ProviderModelOption
  roleFitEntry?: MaterializationReportEntry
  testStatus?: RoleChainStatus
}

interface RoleProviderRouteTooltipInput {
  status: RoleRouteStatus
  providerModel?: ProviderModelOption
  fallbackProviderModelId?: string | null
  detail?: string | null
}

const statusMeta: Record<RoleRouteStatus, {
  label: string
  description: string
}> = {
  runnable: {
    label: "Can Run",
    description: "Role match: requirements satisfied.",
  },
  limited: {
    label: "Limited",
    description: "Role match: limited or unverified capabilities.",
  },
  blocked: {
    label: "Blocked",
    description: "Role match: blocked by route availability or required capabilities.",
  },
  testing: {
    label: "Testing",
    description: "Role match: testing this route.",
  },
}

export function deriveRoleRouteStatus({
  providerModel,
  roleFitEntry,
  testStatus,
}: RoleRouteStatusInput): RoleRouteStatus | null {
  if (testStatus === "testing") return "testing"
  if (testStatus === "warning") return "limited"
  if (testStatus && testStatus !== "ok" && testStatus !== "idle") return "blocked"
  if (roleFitEntry?.role_fit === "not_fit") return "blocked"
  if (providerModel?.ui_state === "needs_setup" || providerModel?.ui_state === "off") return "blocked"
  if (providerModel?.ui_state === "cooling_down" && testStatus !== "ok") return "blocked"
  if (roleFitEntry?.role_fit === "downgraded" || roleFitEntry?.role_fit === "needs_test") return "limited"
  if (providerModel?.ui_state === "untested" && testStatus !== "ok") return "limited"
  if (providerModel || roleFitEntry || testStatus === "ok") return "runnable"
  return null
}

export function roleRouteStatusSurfaceClass(status: RoleRouteStatus | null): string {
  if (status === "runnable") return "border-success-border ring-1 ring-success/25"
  if (status === "limited") return "border-warning-border ring-1 ring-warning/25"
  if (status === "blocked") return "border-destructive-border ring-1 ring-destructive/25"
  if (status === "testing") return "border-primary/70 ring-1 ring-primary/30"
  return ""
}

export function RoleRouteStatusLight({
  status,
  detail,
  showTooltip = true,
}: {
  status: RoleRouteStatus
  detail?: string | null
  showTooltip?: boolean
}) {
  const ariaLabel = roleRouteStatusAriaLabel(status, detail)
  const light = (
    <span
      role="status"
      aria-label={ariaLabel}
      data-role-route-status-light="true"
      data-role-route-status={status}
      className={cn(
        "inline-flex size-1.5 shrink-0 rounded-full ring-1 ring-offset-0",
        roleRouteStatusLightClass(status),
      )}
    />
  )

  if (!showTooltip) return light

  const tooltip = roleRouteStatusTooltip(status, detail)
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {light}
        </TooltipTrigger>
        <TooltipContent className="max-w-sm break-words">{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export function roleRouteStatusTooltip(status: RoleRouteStatus, detail?: string | null): string {
  const meta = statusMeta[status]
  return detail ? `${meta.label}: ${detail}` : meta.description
}

export function roleProviderRouteTooltip({
  status,
  providerModel,
  fallbackProviderModelId,
  detail,
}: RoleProviderRouteTooltipInput): string {
  const modelName = stringValue(providerModel?.provider_model_id)
    ?? stringValue(fallbackProviderModelId)
    ?? "Unknown model"
  const headline = providerRouteHeadline(providerModel)
  const lines = [
    headline ? `${modelName} - ${headline}` : modelName,
    `Role match: ${roleMatchDetail(status, detail)}`,
  ]
  const methods = stringListCapability(providerModel, "verified_methods")
  const inputModalities = stringListCapability(providerModel, "input_modalities")
  const outputModalities = stringListCapability(providerModel, "output_modalities")
  const maxInputTokens = numericLimitCapability(providerModel, "max_input_tokens")
  const maxOutputTokens = numericLimitCapability(providerModel, "max_output_tokens")

  if (methods.length > 0) lines.push(`Methods: ${methods.join(", ")}`)
  if (inputModalities.length > 0) lines.push(`Input: ${formatModalityList(inputModalities)}`)
  if (outputModalities.length > 0) lines.push(`Output: ${formatModalityList(outputModalities)}`)
  if (maxInputTokens !== null) lines.push(`Max input: ${formatNumber(maxInputTokens)} tokens`)
  if (maxOutputTokens !== null) lines.push(`Max output: ${formatNumber(maxOutputTokens)} tokens`)
  if (!providerModel || providerModel.capability_state === "unknown") lines.push("Capabilities: not listed")

  return lines.join("\n")
}

export function roleRouteStatusAriaLabel(status: RoleRouteStatus, detail?: string | null): string {
  const meta = statusMeta[status]
  return detail ? `Role route status ${meta.label}: ${detail}` : `Role route status ${meta.label}`
}

export function roleRouteStatusDetail({
  providerModel,
  roleFitEntry,
  testMessage,
}: {
  providerModel?: ProviderModelOption
  roleFitEntry?: MaterializationReportEntry
  testMessage?: string
}): string | null {
  const details = [
    testMessage,
    ...roleFitDetails(roleFitEntry),
    providerUiStateDetail(providerModel),
  ].filter((detail): detail is string => Boolean(detail))
  return uniqueDetails(details).join(" ") || null
}

function roleRouteStatusLightClass(status: RoleRouteStatus): string {
  if (status === "runnable") return "bg-success ring-success-border"
  if (status === "limited") return "bg-warning ring-warning-border"
  if (status === "testing") return "animate-pulse bg-primary ring-primary/30"
  return "bg-destructive ring-destructive-border"
}

function roleFitDetails(roleFitEntry?: MaterializationReportEntry): string[] {
  if (!roleFitEntry) return []
  const warningDetails = roleFitEntry.warnings
    ?.map((warning) => warningDetail(warning))
    .filter((detail): detail is string => Boolean(detail)) ?? []
  if (warningDetails.length > 0) return warningDetails
  if (roleFitEntry.role_fit === "downgraded") {
    return ["A requested role capability is downgraded for this route."]
  }
  if (roleFitEntry.role_fit === "needs_test") {
    return ["A requested role capability needs validation for this route."]
  }
  if (roleFitEntry.role_fit === "not_fit") {
    return ["A required role capability is unsupported by this route."]
  }
  return []
}

function warningDetail(warning: Record<string, unknown>): string | null {
  const message = stringValue(warning.message) ?? stringValue(warning.detail)
  if (message) return ensureSentence(message)

  const code = stringValue(warning.code) ?? stringValue(warning.reason_code)
  if (code === "thinking_not_enabled") {
    return "Thinking was preferred but is not enabled for this provider model."
  }
  if (code === "thinking_capability_unknown") {
    return "Thinking is required but capability is unknown."
  }
  if (code === "thinking_unsupported") {
    return "Thinking is required but unsupported."
  }
  if (code === "token_downgraded") {
    return "Requested output tokens exceed this route limit."
  }

  const capability = stringValue(warning.capability)
    ?? stringValue(warning.capability_id)
    ?? stringValue(warning.feature)
  if (capability) {
    return `${humanizeToken(capability)} needs validation for this route.`
  }
  return code ? `${humanizeToken(code)}.` : null
}

function providerUiStateDetail(providerModel?: ProviderModelOption): string | null {
  if (!providerModel) return null
  const detail = stringValue(providerModel.ui_detail)
  if (providerModel.ui_state === "cooling_down") {
    const base = detail ? `Cooling Down: ${detail}` : "Cooling Down."
    const retry = stringValue(providerModel.retry_at)
    return detail || !retry ? ensureSentence(base) : `${ensureSentence(base)} Retry after ${retry}.`
  }
  if (providerModel.ui_state === "untested") {
    return detail ? `Untested: ${ensureSentence(detail)}` : "Global route test is still untested."
  }
  if (providerModel.ui_state === "needs_setup") {
    return detail ? `Needs setup: ${ensureSentence(detail)}` : "Needs setup before this route can run."
  }
  if (providerModel.ui_state === "off") {
    return detail ? `Off: ${ensureSentence(detail)}` : "This route is disabled."
  }
  return detail ? ensureSentence(detail) : null
}

function uniqueDetails(details: string[]): string[] {
  const seen = new Set<string>()
  return details.filter((detail) => {
    const normalized = detail.trim()
    if (!normalized || seen.has(normalized)) return false
    seen.add(normalized)
    return true
  })
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null
}

function ensureSentence(value: string): string {
  const trimmed = value.trim()
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`
}

function humanizeToken(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (letter) => letter.toUpperCase())
}

function roleMatchDetail(status: RoleRouteStatus, detail?: string | null): string {
  if (detail) return ensureSentence(detail)
  if (status === "runnable") return "requirements satisfied."
  if (status === "limited") return "limited or unverified capabilities."
  if (status === "testing") return "testing this route."
  return "blocked by route availability or required capabilities."
}

function providerRouteHeadline(providerModel?: ProviderModelOption): string | null {
  if (!providerModel) return null
  const state = providerModel.ui_state === "ready" ? "Verified" : humanizeToken(providerModel.ui_state)
  const modes = providerRouteModes(providerModel)
  return [state, modes.length > 0 ? `${modes.join(" + ")} route` : "route"].join(" ")
}

function providerRouteModes(providerModel: ProviderModelOption): string[] {
  const inputModalities = stringListCapability(providerModel, "input_modalities")
  const outputModalities = stringListCapability(providerModel, "output_modalities")
  const modes: string[] = []
  if (hasModality(inputModalities, "text") && hasModality(outputModalities, "text")) {
    modes.push("text chat")
  } else if (outputModalities.length > 0) {
    modes.push(`${formatModalityList(outputModalities)} output`)
  }
  if (hasModality(inputModalities, "image")) modes.push("image input")
  if (hasModality(inputModalities, "pdf")) modes.push("PDF input")
  if (booleanCapability(providerModel, "thinking_protocol")
    || booleanCapability(providerModel, "thinking")
    || booleanCapability(providerModel, "reasoning")
    || booleanCapability(providerModel, "supports_thinking")) {
    modes.push("reasoning")
  }
  if (booleanCapability(providerModel, "tools") || booleanCapability(providerModel, "tool")) {
    modes.push("tools")
  }
  return uniqueDetails(modes)
}

function stringListCapability(providerModel: ProviderModelOption | undefined, key: string): string[] {
  const value = capabilityValue(providerModel, key)
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
  }
  return typeof value === "string" && value.trim().length > 0 ? [value.trim()] : []
}

function booleanCapability(providerModel: ProviderModelOption, key: string): boolean {
  const value = capabilityValue(providerModel, key)
  return value === true || value === "true"
}

function numericLimitCapability(providerModel: ProviderModelOption | undefined, key: string): number | null {
  const value = capabilityValue(providerModel, key)
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const max = (value as { max?: unknown }).max
  return typeof max === "number" && Number.isFinite(max) ? max : null
}

function capabilityValue(providerModel: ProviderModelOption | undefined, key: string): unknown {
  return providerModel?.capabilities[key]?.value
}

function hasModality(modalities: string[], expected: string): boolean {
  return modalities.some((modality) => modality.toLowerCase() === expected)
}

function formatModalityList(modalities: string[]): string {
  return modalities.map(formatModality).join(", ")
}

function formatModality(modality: string): string {
  return modality.toLowerCase() === "pdf" ? "PDF" : modality
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value)
}
