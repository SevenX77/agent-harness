import {
  getRoleTestJob,
  startRoleTestJob,
  type RoleTestJobResponse,
  type RoleTestProviderProgressStatus,
  type RoleTestResponse,
} from "@/api/llm"
type CopilotAgentStatus = string

export type CopilotRouteJobStatus = CopilotAgentStatus | "testing"

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
    throw new Error(job.message ?? "Copilot role test failed")
  }
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
  if (status === "ok") return "ready"
  if (status === "failed" || status === "blocked") return "unsupported"
  if (status === "testing") return "testing"
  return "not_tested"
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function copilotRoleTestErrorMessage(error: unknown, roleDisplayName: string): string {
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
