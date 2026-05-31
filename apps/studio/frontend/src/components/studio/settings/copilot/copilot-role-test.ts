import {
  getRoleTestJob,
  startRoleTestJob,
  type RoleTestJobResponse,
  type RoleTestProviderProgressStatus,
  type RoleTestResponse,
} from "@/api/llm"
import type { CopilotAgentStatus } from "./mock-copilot-data"

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
  const missingRoleName = detail ? unknownLlmRoleName(detail) : null

  if (missingRoleName) {
    return `${roleDisplayName} 测试失败：后端还没有创建 Copilot role \`${missingRoleName}\`。请先迁移或创建该 role 后再测试。`
  }

  if (response?.status) {
    const detailSuffix = detail ? detail : fallbackErrorMessage(error)
    return `${roleDisplayName} 测试失败：${statusReason(response.status)}${detailSuffix}`
  }

  return `${roleDisplayName} 测试失败：${fallbackErrorMessage(error)}`
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

function unknownLlmRoleName(detail: string): string | null {
  return /Unknown LLM role:\s*([A-Za-z0-9_-]+)/.exec(detail)?.[1] ?? null
}

function statusReason(status: number): string {
  if (status === 400) return "请求参数不完整或格式不正确。"
  if (status === 401) return "后端认证失败。"
  if (status === 403) return "当前配置没有权限执行测试。"
  if (status === 404) return "后端没有找到对应资源。"
  if (status === 422) return "后端无法使用当前配置执行测试。"
  if (status === 503) return "后端测试服务暂时不可用。"
  if (status >= 500) return "后端服务执行失败。"
  return "请求失败。"
}

function fallbackErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === "string" && error.length > 0) return error
  return "请查看后端日志获取更多信息。"
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}
