import { useSyncExternalStore } from "react"
import {
  roleChainStatusKey,
  type RoleChainStatus,
  type RoleChainStatusMap,
} from "@/hooks/useRoleTestChainRunner"
import {
  getRoleTestJob,
  startRoleTestJob,
  type RoleTestJobResponse,
  type RoleTestProviderProgress,
  type RoleTestProviderResult,
  type RoleTestResponse,
} from "@/api/llm"
import { getRoleTestResults, type RoleTestResultsResponse } from "@/api/client"

/**
 * #46/#47 测试态 SSOT (spec §2.4 / 实施页 #46 落地细节):
 *
 * This module is a MODULE-SCOPED *mirror* of the backend role-test SSOT — NOT a
 * second source of truth. The backend owns the truth in two layers:
 *   (a) the in-memory active-job dict (_role_test_jobs) projected via
 *       GET /role-test-jobs/{job_id} — the live progress;
 *   (b) the persisted last-known results projected via GET /roles/test-results.
 *
 * The store only mirrors whatever the backend reports. Because it lives at module
 * scope (not in a component's useState), an in-flight test SURVIVES a tab switch /
 * component remount: when LlmRolesTab remounts it reads this same mirror and
 * re-renders the live progress, then keeps projecting the polled backend job.
 */

export interface RoleTestState {
  running: boolean
  result?: RoleTestResponse
  error?: string
  activeStatuses?: RoleChainStatusMap
}

export type RoleTestStore = Record<string, RoleTestState>

let store: RoleTestStore = {}
const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): RoleTestStore {
  return store
}

function setStore(next: RoleTestStore): void {
  store = next
  emit()
}

function patchRole(roleName: string, patch: RoleTestState): void {
  setStore({ ...store, [roleName]: patch })
}

/** React hook: subscribe to the module-scoped backend mirror. */
export function useRoleTestStore(): RoleTestStore {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}

/** Project a polling job's live provider statuses into the chain-status map. */
export function roleTestStatusesFromJob(job: RoleTestJobResponse): RoleChainStatusMap {
  const statusMap: RoleChainStatusMap = {}
  for (const providerStatus of job.provider_statuses) {
    statusMap[roleChainStatusKey(providerStatus.canonical_id, providerStatus.route_id)] = {
      status: roleChainStatusForProviderProgress(providerStatus),
      message: providerStatus.message ?? undefined,
    }
  }
  return statusMap
}

function roleChainStatusForProviderProgress(providerStatus: RoleTestProviderProgress): RoleChainStatus {
  if (providerStatus.status === "testing") return "testing"
  if (providerStatus.status === "ok") return "ok"
  if (providerStatus.status === "queued" || providerStatus.status === "untested") return "idle"
  return "error"
}

/** Project a completed test result into the chain-status map. */
export function roleTestStatusesFromResult(result?: RoleTestResponse): RoleChainStatusMap {
  const statusMap: RoleChainStatusMap = {}
  for (const group of result?.model_groups ?? []) {
    for (const providerResult of group.provider_results) {
      statusMap[roleChainStatusKey(group.canonical_id, providerResult.route_id)] = {
        status: roleChainStatusForProviderResult(providerResult),
        message: roleTestProviderMessage(providerResult),
      }
    }
  }
  return statusMap
}

function roleChainStatusForProviderResult(providerResult: RoleTestProviderResult): RoleChainStatus {
  if (providerResult.status === "ok") {
    return providerResult.role_fit === "using" && providerResult.warnings.length === 0 ? "ok" : "warning"
  }
  if (providerResult.status === "untested") return "idle"
  return "error"
}

function roleTestProviderMessage(providerResult: RoleTestProviderResult): string | undefined {
  const messages = [
    providerResult.message,
    providerResult.retry_at ? `Retry after ${providerResult.retry_at}.` : null,
  ].filter((message): message is string => Boolean(message))
  return Array.from(new Set(messages)).join(" ") || undefined
}

/**
 * Project the mirror into per-role status maps for the role cards: a running role
 * shows its live activeStatuses (from the polled job); a settled role shows the
 * statuses derived from its last result.
 */
export function roleTestStatusesByRole(state: RoleTestStore): Record<string, RoleChainStatusMap> {
  return Object.fromEntries(
    Object.entries(state).map(([roleName, roleState]) => [
      roleName,
      roleState.running
        ? roleState.activeStatuses ?? {}
        : roleTestStatusesFromResult(roleState.result),
    ]),
  )
}

/**
 * Merge persisted last-known results into the current mirror WITHOUT clobbering a
 * running test: any role that already has an entry (running or freshly settled) is
 * skipped, so a late seed fetch never overwrites a live in-flight test.
 */
export function mergePersistedRoleTestResults(
  current: RoleTestStore,
  persisted: RoleTestResultsResponse | null | undefined,
): RoleTestStore {
  if (!persisted?.results) return current
  const merged: RoleTestStore = { ...current }
  let changed = false
  for (const [roleName, entry] of Object.entries(persisted.results)) {
    if (merged[roleName]) continue
    const result = entry.result as unknown as RoleTestResponse | undefined
    if (!result || !Array.isArray(result.model_groups)) continue
    merged[roleName] = { running: false, result }
    changed = true
  }
  return changed ? merged : current
}

/**
 * On mount: fetch the persisted last-known results and seed them into the mirror.
 * Idempotent (merge skips roles that already have an entry) and best-effort —
 * a fetch failure is logged, never thrown, so the live test flow still works.
 */
export async function seedPersistedRoleTestResults(
  load: () => Promise<RoleTestResultsResponse> = getRoleTestResults,
): Promise<void> {
  try {
    const persisted = await load()
    setStore(mergePersistedRoleTestResults(store, persisted))
  } catch (error) {
    console.warn(
      "phase=role-test-seed action=persisted-fetch-failed reason=%s",
      error instanceof Error ? error.message : String(error),
    )
  }
}

/**
 * Run a role test, projecting progress straight into the module mirror.
 *
 * - If `validationError` is set the role has unsaved validation errors (#47 未保存
 *   先拒测): patch an error state and return without starting a job.
 * - Otherwise patch running, start POST /roles/{name}/test-jobs, poll
 *   GET /role-test-jobs/{job_id} every 500ms projecting live progress into the
 *   mirror, then settle on the failed message (error) or done result.
 *
 * A failed test keeps the previous result (last-known) so the card does not blank.
 */
export async function runRoleTest(
  roleName: string,
  {
    beforeRoleTest,
    afterRoleTest,
    startJob = startRoleTestJob,
    getJob = getRoleTestJob,
    sleep = defaultSleep,
    validationError,
  }: {
    beforeRoleTest?: () => Promise<unknown> | unknown
    afterRoleTest?: () => Promise<unknown> | unknown
    startJob?: (roleName: string) => Promise<RoleTestJobResponse>
    getJob?: (jobId: string) => Promise<RoleTestJobResponse>
    sleep?: (ms: number) => Promise<void>
    validationError?: string | null
  } = {},
): Promise<void> {
  if (validationError) {
    patchRole(roleName, {
      running: false,
      result: store[roleName]?.result,
      error: `Save the role before testing: ${validationError}`,
    })
    return
  }

  patchRole(roleName, {
    ...store[roleName],
    running: true,
    error: undefined,
    activeStatuses: {},
  })

  try {
    await beforeRoleTest?.()
    let job = await startJob(roleName)
    patchRole(roleName, { ...store[roleName], running: true, activeStatuses: roleTestStatusesFromJob(job) })
    while (job.status === "queued" || job.status === "running") {
      await sleep(500)
      job = await getJob(job.job_id)
      patchRole(roleName, { ...store[roleName], running: true, activeStatuses: roleTestStatusesFromJob(job) })
    }
    if (job.status === "failed" || !job.result) {
      throw new Error(job.message ?? "Role test failed")
    }
    await afterRoleTest?.()
    patchRole(roleName, { running: false, result: job.result, error: undefined, activeStatuses: undefined })
  } catch (error) {
    patchRole(roleName, {
      running: false,
      result: store[roleName]?.result,
      error: error instanceof Error ? error.message : "Role test failed",
      activeStatuses: undefined,
    })
  }
}

/**
 * Run a role test job to its terminal state and return the result, WITHOUT
 * touching the module mirror. Used by the node Properties quick-Test (which keeps
 * its own local status), so it reuses the exact same backend job + poll loop the
 * settings page uses (settings-ux-spec §2.7) without coupling to the store.
 */
export async function runRoleTestJobToResult(
  roleName: string,
  {
    startJob = startRoleTestJob,
    getJob = getRoleTestJob,
    sleep = defaultSleep,
  }: {
    startJob?: (roleName: string) => Promise<RoleTestJobResponse>
    getJob?: (jobId: string) => Promise<RoleTestJobResponse>
    sleep?: (ms: number) => Promise<void>
  } = {},
): Promise<RoleTestResponse> {
  let job = await startJob(roleName)
  while (job.status === "queued" || job.status === "running") {
    await sleep(500)
    job = await getJob(job.job_id)
  }
  if (job.status === "failed" || !job.result) {
    throw new Error(job.message ?? "Role test failed")
  }
  return job.result
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/** Test-only: replace the entire mirror (used to arrange unit/e2e scenarios). */
export function __setRoleTestStoreForTests(next: RoleTestStore): void {
  setStore(next)
}

/** Test-only: read the current mirror snapshot synchronously. */
export function __getRoleTestStoreForTests(): RoleTestStore {
  return store
}

/** Test-only: clear the mirror back to empty between tests. */
export function __resetRoleTestStoreForTests(): void {
  setStore({})
}
