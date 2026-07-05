import {
  getRoleTestJob,
  startRoleTestJob,
  type RoleTestJobResponse,
  type RoleTestProviderProgressStatus,
  type RoleTestResponse,
} from "@/api/llm"
import { invalidateRoleTestResultsCache } from "@/api/client"
import i18n from "@/i18n"
// R-F11: align with the 6-state ProviderUiState (`apps/studio/backend/app/core/
// adapters/gateway.py` ProviderUiState) plus a transient "testing" projection so
// the route lights match LlmRolesTab's RoleRouteStatusLight (green/blue/gray/
// red/gray-pulse). "unsupported"/"not_tested" are retained as aliases so the
// persisted/seeded route projections still round-trip across upgrades.
export type CopilotRouteJobStatus =
  | "ready"
  | "historical_ready"
  | "untested"
  | "failed"
  | "cooling_down"
  | "off"
  | "testing"
  | "not_tested" // legacy alias for "untested"
  | "unsupported" // legacy alias for "failed"

type StartRoleTestJob = (roleName: string) => Promise<RoleTestJobResponse>
type GetRoleTestJob = (jobId: string) => Promise<RoleTestJobResponse>

interface RunCopilotRoleTestJobOptions {
  startJob?: StartRoleTestJob
  getJob?: GetRoleTestJob
  sleep?: (ms: number) => Promise<void>
  onProgress?: (job: RoleTestJobResponse) => void
}

const ROLE_TEST_POLL_MS = 500

export async function runCopilotRoleTestJob(
  roleName: string,
  {
    startJob = startRoleTestJob,
    getJob = getRoleTestJob,
    sleep = defaultSleep,
    onProgress,
  }: RunCopilotRoleTestJobOptions = {},
): Promise<RoleTestResponse> {
  let job = await startJob(roleName)
  onProgress?.(job)

  while (job.status === "queued" || job.status === "running") {
    await sleep(ROLE_TEST_POLL_MS)
    job = await getJob(job.job_id)
    onProgress?.(job)
  }

  if (job.status === "failed" || !job.result) {
    invalidateRoleTestResultsCache()
    // R-F9: keep the BE-rendered message AND the error_code on the thrown
    // error so `copilotRoleTestErrorMessage` can prefer the human message
    // mapped from error_code even when caller catches the Error instance.
    const err = new Error(job.message ?? "Copilot role test failed") as Error & {
      error_code?: string | null
      error_payload?: Record<string, unknown> | null
      job?: RoleTestJobResponse
    }
    err.error_code = job.error_code ?? null
    err.error_payload = (job.error_payload ?? null) as Record<string, unknown> | null
    err.job = job
    throw err
  }
  invalidateRoleTestResultsCache()
  return job.result
}

export function copilotRouteStatusesFromJob(
  job: RoleTestJobResponse,
): Record<string, CopilotRouteJobStatus> {
  return Object.fromEntries(
    job.provider_statuses.map((provider) => [
      provider.route_id,
      copilotRouteStatusFromProviderStatus(provider.status),
    ]),
  )
}

// 每条 route 的 SDK 测试真实信息(失败时是具体原因,如 "SDK returned an error: HTTP 404")—— 供
// tooltip 展示,让"为什么失败"看得见,而不是只有一盏红灯。
export function copilotRouteMessagesFromJob(job: RoleTestJobResponse): Record<string, string> {
  const messages: Record<string, string> = {}
  for (const provider of job.provider_statuses) {
    const message = (provider as { message?: string | null }).message
    if (typeof message === "string" && message.trim()) messages[provider.route_id] = message.trim()
  }
  return messages
}

export function copilotRouteMessagesFromPersistedResult(result: unknown): Record<string, string> {
  const routes = persistedSdkEvidenceRoutes(result)
  if (!routes) return {}
  const messages: Record<string, string> = {}
  for (const [routeId, routeResult] of Object.entries(routes)) {
    if (!isRecord(routeResult)) continue
    const message = routeResult.message
    if (typeof message === "string" && message.trim()) messages[routeId] = message.trim()
  }
  return messages
}

/**
 * R-F21: surface ``retry_after_seconds`` per route so the FE Test Button can
 * render a countdown and stay disabled while the upstream cooldown is in
 * effect. Returns an empty map when the job has no cooling_down routes (the
 * common case) so callers can spread it without affecting their state.
 */
export function copilotRouteCooldownsFromJob(
  job: RoleTestJobResponse,
): Record<string, number> {
  const result: Record<string, number> = {}
  for (const provider of job.provider_statuses) {
    if (provider.status === "cooling_down" && typeof provider.retry_after_seconds === "number") {
      result[provider.route_id] = provider.retry_after_seconds
    }
  }
  return result
}

/**
 * R20: project the persisted copilot SDK test results into the route status
 * override map (route_id -> ready/unsupported/...) that CopilotTab seeds on
 * mount, so route lights show the last-known status after a remount/restart.
 *
 * The persisted `result` is the backend copilot SDK result; its per-route
 * verdicts live under `sdk_evidence.routes` (route_id -> {status}). Each route
 * `status` is "ok"/"failed"/etc., mapped through the same provider-status logic
 * as the live job poller so seeded and live lights stay consistent.
 */
export function copilotRouteStatusesFromPersistedResult(
  result: unknown,
): Record<string, CopilotRouteJobStatus> {
  const routes = persistedSdkEvidenceRoutes(result)
  if (!routes) return {}
  const statuses: Record<string, CopilotRouteJobStatus> = {}
  for (const [routeId, routeResult] of Object.entries(routes)) {
    if (!isRecord(routeResult)) continue
    const rawStatus = routeResult.status
    if (typeof rawStatus !== "string") continue
    statuses[routeId] = copilotRouteStatusFromProviderStatus(
      rawStatus as RoleTestProviderProgressStatus,
    )
  }
  return statuses
}

/**
 * R-F21: extract any persisted ``retry_after_seconds`` so a remount can
 * rehydrate the cooldown countdown alongside the route status seed.
 */
export function copilotRouteCooldownsFromPersistedResult(
  result: unknown,
): Record<string, number> {
  const routes = persistedSdkEvidenceRoutes(result)
  if (!routes) return {}
  const cooldowns: Record<string, number> = {}
  for (const [routeId, routeResult] of Object.entries(routes)) {
    if (!isRecord(routeResult)) continue
    const status = routeResult.status
    if (status !== "cooling_down") continue
    const retry = routeResult.retry_after_seconds
    if (typeof retry === "number" && retry > 0) cooldowns[routeId] = retry
  }
  return cooldowns
}

function persistedSdkEvidenceRoutes(result: unknown): Record<string, unknown> | null {
  if (!isRecord(result)) return null
  const evidence = result.sdk_evidence
  if (!isRecord(evidence)) return null
  const routes = evidence.routes
  return isRecord(routes) ? routes : null
}

function copilotRouteStatusFromProviderStatus(
  status: RoleTestProviderProgressStatus,
): CopilotRouteJobStatus {
  // R-F11: map the SDK probe's per-route status to the 6-state route-light
  // vocabulary so the copilot route lights agree with the LlmRolesTab status
  // conventions. R-F21 introduces "cooling_down" (anthropic 429 throttle) which
  // is its own light + countdown rather than a generic "failed".
  if (status === "ok") return "ready"
  if (status === "failed" || status === "blocked") return "failed"
  if (status === "testing") return "testing"
  if (status === "cooling_down") return "cooling_down"
  // "queued" / "untested" → not yet probed
  return "untested"
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/**
 * R-F9: FE-side mirror of backend `_human_message_for_error_code`. Used as
 * a fallback (and when the FE catches a job-failed payload before passing
 * to toast) so the user never sees raw "ResourceTerminalError: ..." text.
 *
 * Backend already emits `job.message` populated by the same table, but if
 * a transport error or job poll error short-circuits before we get the
 * BE-rendered message, we fall through to this map keyed by `error_code`.
 */
export const ERROR_CODE_MAP: Record<string, (roleName: string) => string> = {
  "resource.no_available_route": (roleName) =>
    i18n.t("copilot.testErrors.noAvailableRoute", {
      ns: "settings",
      title: roleName,
      defaultValue:
        "{{title}} has no available model route. Configure Anthropic-compatible credentials in API Keys and run a test first.",
    }),
  "resource.role_unknown": (roleName) =>
    i18n.t("copilot.testErrors.roleUnknown", {
      ns: "settings",
      title: roleName,
      defaultValue: "{{title}} does not exist or was deleted. Refresh the page and try again.",
    }),
  "resource.role_invalid_kind": (roleName) =>
    i18n.t("copilot.testErrors.invalidKind", {
      ns: "settings",
      title: roleName,
      defaultValue: "{{title}} is not a copilot role and cannot be tested with the Claude SDK.",
    }),
  "resource.credential_missing": (roleName) =>
    i18n.t("copilot.testErrors.credentialMissing", {
      ns: "settings",
      title: roleName,
      defaultValue: "{{title}} is missing a required API key. Add it in API Keys and try again.",
    }),
}

function jobErrorCode(error: unknown): string | undefined {
  if (!isRecord(error)) return undefined
  const code = (error as { error_code?: unknown }).error_code
  if (typeof code === "string") return code
  const job = (error as { job?: unknown }).job
  if (isRecord(job)) {
    const jobCode = (job as { error_code?: unknown }).error_code
    if (typeof jobCode === "string") return jobCode
  }
  return undefined
}

export function copilotRoleTestErrorMessage(error: unknown, roleDisplayName: string): string {
  // R-F9: prefer the backend job's error_code → human map over the raw
  // `error.message` so the user sees an actionable localized explanation instead of
  // "ResourceTerminalError: ...".
  const code = jobErrorCode(error)
  if (code && ERROR_CODE_MAP[code]) {
    return ERROR_CODE_MAP[code](roleDisplayName)
  }

  const response = errorResponse(error)
  const detail = errorDetail(response?.data)

  if (detail) {
    return `${roleDisplayName} test failed: ${detail}`
  }

  if (response?.status) {
    return `${roleDisplayName} test failed: ${statusReason(response.status)}${fallbackErrorMessage(error)}`
  }

  return `${roleDisplayName} test failed: ${fallbackErrorMessage(error)}`
}

function errorResponse(error: unknown): { status?: number; data?: unknown } | null {
  if (!isRecord(error)) return null
  const response = error.response
  if (!isRecord(response)) return null
  return {
    status: typeof response.status === "number" ? response.status : undefined,
    data: response.data,
  }
}

function errorDetail(data: unknown): string | null {
  if (typeof data === "string") return data
  if (!isRecord(data)) return null
  if (typeof data.detail === "string") return data.detail
  if (typeof data.message === "string") return data.message
  return null
}

function statusReason(status: number): string {
  if (status === 400) return "request parameters are incomplete or invalid. "
  if (status === 401) return "backend authentication failed. "
  if (status === 403) return "current configuration is not allowed to run this test. "
  if (status === 404) return "backend resource was not found. "
  if (status === 422) return "backend cannot run the test with the current configuration. "
  if (status === 503) return "backend test service is unavailable. "
  if (status >= 500) return "backend service failed. "
  return "request failed. "
}

function fallbackErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === "string" && error.length > 0) return error
  return "Check backend logs for more details."
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}
