import type { RoleTestProviderResult, RoleTestResponse, RoleTestStatus } from "@/api/llm"

// Maps the node Properties role-test runner state (running / last result / error)
// to a single status badge. Reuses the same overall RoleTestStatus vocabulary the
// settings role test projection uses, projected to the badge variants the shadcn
// Badge component exposes. Pure + framework-free so it can be unit tested
// without a DOM (renderToStaticMarkup / element-walk convention).

export type RoleTestBadgeVariant = "secondary" | "success" | "warning" | "destructive"

export interface RoleTestStatusBadge {
  label: string
  variant: RoleTestBadgeVariant
  // "running" suppresses click + drives the spinner; informational for the UI.
  running: boolean
}

export interface RoleTestStatusInput {
  running: boolean
  status?: RoleTestStatus | null
  error?: string | null
  details?: string[]
}

export function roleTestStatusBadge(input: RoleTestStatusInput): RoleTestStatusBadge {
  if (input.running) {
    return { label: "Testing", variant: "secondary", running: true }
  }
  if (input.error) {
    return { label: "Failed", variant: "destructive", running: false }
  }
  return { ...roleTestResultBadge(input.status ?? null), running: false }
}

function roleTestResultBadge(status: RoleTestStatus | null): Omit<RoleTestStatusBadge, "running"> {
  if (status === "ok") {
    return { label: "Passed", variant: "success" }
  }
  if (status === "warning") {
    return { label: "Needs Attention", variant: "warning" }
  }
  if (status === "blocked" || status === "failed") {
    return { label: "Failed", variant: "destructive" }
  }
  return { label: "Untested", variant: "secondary" }
}

export function roleTestDetailsFromResult(result: RoleTestResponse): string[] {
  return uniqueDetails([
    ...result.warnings.map((warning) => warningDetail(warning)),
    ...result.model_groups.flatMap((group) => (
      group.provider_results.flatMap((providerResult) => providerResultDetails(providerResult))
    )),
  ].filter((detail): detail is string => Boolean(detail)))
}

function providerResultDetails(providerResult: RoleTestProviderResult): string[] {
  const prefix = providerResult.provider_label || providerResult.route_id
  const details = [
    providerResult.message,
    providerResult.retry_at ? `Retry after ${providerResult.retry_at}.` : null,
    ...providerResult.warnings.map((warning) => warningDetail(warning)),
  ].filter((detail): detail is string => Boolean(detail))
  return details.map((detail) => `${prefix}: ${ensureSentence(detail)}`)
}

function warningDetail(warning: Record<string, unknown>): string | null {
  const message = stringValue(warning.message) ?? stringValue(warning.detail)
  if (message) return ensureSentence(message)

  const code = stringValue(warning.code) ?? stringValue(warning.reason_code)
  if (code === "thinking_not_enabled") {
    return "Thinking was preferred but is not enabled for this provider model."
  }
  if (code === "thinking_capability_unknown") {
    return "Thinking capability is unknown for this provider model."
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

function uniqueDetails(details: string[]): string[] {
  const seen = new Set<string>()
  return details.filter((detail) => {
    const normalized = detail.trim()
    if (!normalized || seen.has(normalized)) return false
    seen.add(normalized)
    return true
  })
}
