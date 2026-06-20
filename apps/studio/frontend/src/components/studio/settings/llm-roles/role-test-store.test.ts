import { afterEach, describe, expect, it, vi } from "vitest"
import { roleChainStatusKey } from "@/hooks/useRoleTestChainRunner"
import type { RoleTestJobResponse, RoleTestResponse } from "@/api/llm"
import type { RoleTestResultsResponse } from "@/api/client"
import {
  __getRoleTestStoreForTests,
  __resetRoleTestStoreForTests,
  bundleTestStoreKey,
  mergePersistedRoleTestResults,
  roleTestStatusesByRole,
  roleTestStatusesFromJob,
  roleTestStatusesFromResult,
  runBundleTest,
  runRoleTest,
  seedPersistedRoleTestResults,
  type RoleTestStore,
} from "./role-test-store"

function settledResult(): RoleTestResponse {
  return {
    role_name: "analyst",
    status: "warning",
    warnings: [],
    model_groups: [{
      canonical_id: "gpt-5",
      display_name: "GPT 5",
      provider_results: [
        {
          route_id: "ready:gpt-5",
          provider_label: "Ready",
          provider_ui_state: "ready",
          role_fit: "using",
          admission_decision: "admit",
          status: "ok",
          warnings: [],
          retry_at: null,
          message: null,
          resolved_settings: {},
        },
        {
          route_id: "downgraded:gpt-5",
          provider_label: "Downgraded",
          provider_ui_state: "ready",
          role_fit: "downgraded",
          admission_decision: "admit",
          status: "ok",
          warnings: [{ message: "Using lower max output." }],
          retry_at: null,
          message: "Using lower max output.",
          resolved_settings: {},
        },
        {
          route_id: "failed:gpt-5",
          provider_label: "Failed",
          provider_ui_state: "failed",
          role_fit: "not_fit",
          admission_decision: "block",
          status: "failed",
          warnings: [],
          retry_at: "2026-12-31T00:00:00Z",
          message: "Network error.",
          resolved_settings: {},
        },
      ],
    }],
  }
}

describe("role-test-store projectors", () => {
  afterEach(() => __resetRoleTestStoreForTests())

  it("projects a polling job's live provider statuses into chain statuses", () => {
    const job: RoleTestJobResponse = {
      job_id: "job-1",
      role_name: "analyst",
      status: "running",
      provider_statuses: [
        { canonical_id: "gpt-5", route_id: "a:gpt-5", status: "testing", message: null },
        { canonical_id: "gpt-5", route_id: "b:gpt-5", status: "ok", message: null },
        { canonical_id: "gpt-5", route_id: "c:gpt-5", status: "queued", message: null },
        { canonical_id: "gpt-5", route_id: "d:gpt-5", status: "failed", message: "boom" },
      ],
    }

    expect(roleTestStatusesFromJob(job)).toEqual({
      [roleChainStatusKey("gpt-5", "a:gpt-5")]: { status: "testing", message: undefined },
      [roleChainStatusKey("gpt-5", "b:gpt-5")]: { status: "ok", message: undefined },
      [roleChainStatusKey("gpt-5", "c:gpt-5")]: { status: "idle", message: undefined },
      [roleChainStatusKey("gpt-5", "d:gpt-5")]: { status: "error", message: "boom" },
    })
  })

  it("projects a completed result into ok / warning / error chain statuses", () => {
    const statuses = roleTestStatusesFromResult(settledResult())

    expect(statuses[roleChainStatusKey("gpt-5", "ready:gpt-5")].status).toBe("ok")
    expect(statuses[roleChainStatusKey("gpt-5", "downgraded:gpt-5")].status).toBe("warning")
    expect(statuses[roleChainStatusKey("gpt-5", "failed:gpt-5")].status).toBe("error")
    expect(statuses[roleChainStatusKey("gpt-5", "failed:gpt-5")].message).toContain("Retry after")
  })

  it("uses live activeStatuses for running roles and result projection for settled roles", () => {
    const store: RoleTestStore = {
      running_role: {
        running: true,
        activeStatuses: { [roleChainStatusKey("gpt-5", "x")]: { status: "testing" } },
        result: settledResult(),
      },
      settled_role: { running: false, result: settledResult() },
    }

    const byRole = roleTestStatusesByRole(store)

    expect(byRole.running_role).toEqual({ [roleChainStatusKey("gpt-5", "x")]: { status: "testing" } })
    expect(byRole.settled_role[roleChainStatusKey("gpt-5", "ready:gpt-5")].status).toBe("ok")
  })
})

describe("mergePersistedRoleTestResults", () => {
  const persisted: RoleTestResultsResponse = {
    results: {
      analyst: {
        role_name: "analyst",
        status: "warning",
        message: null,
        result: settledResult() as unknown as RoleTestResultsResponse["results"][string]["result"],
        updated_at: "2026-06-14T00:00:00Z",
      },
    },
  }

  it("seeds settled state for roles with no existing entry", () => {
    const merged = mergePersistedRoleTestResults({}, persisted)
    expect(merged.analyst).toEqual({ running: false, result: settledResult() })
  })

  it("never clobbers a running role already in the mirror", () => {
    const running: RoleTestStore = { analyst: { running: true } }
    expect(mergePersistedRoleTestResults(running, persisted)).toBe(running)
  })

  it("returns the current store unchanged when there are no persisted results", () => {
    const current: RoleTestStore = { analyst: { running: false } }
    expect(mergePersistedRoleTestResults(current, null)).toBe(current)
    expect(mergePersistedRoleTestResults(current, { results: {} })).toBe(current)
  })

  it("skips malformed persisted entries without a model_groups array", () => {
    const merged = mergePersistedRoleTestResults({}, {
      results: {
        broken: {
          role_name: "broken",
          status: "ok",
          message: null,
          result: { role_name: "broken", status: "ok" } as unknown as RoleTestResultsResponse["results"][string]["result"],
          updated_at: "2026-06-14T00:00:00Z",
        },
      },
    })
    expect(merged.broken).toBeUndefined()
  })
})

describe("seedPersistedRoleTestResults", () => {
  afterEach(() => __resetRoleTestStoreForTests())

  it("logs and swallows a fetch failure (best-effort seeding)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    await seedPersistedRoleTestResults(async () => {
      throw new Error("network down")
    })
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe("runRoleTest", () => {
  afterEach(() => __resetRoleTestStoreForTests())

  function jobResponse(overrides: Partial<RoleTestJobResponse>): RoleTestJobResponse {
    return {
      job_id: "job-1",
      role_name: "analyst",
      status: "running",
      provider_statuses: [],
      ...overrides,
    }
  }

  it("rejects an unsaved role before testing (#47) without starting a job", async () => {
    const startJob = vi.fn()
    await runRoleTest("analyst", {
      validationError: "analyst: model must contain at least one provider",
      startJob,
      getJob: vi.fn(),
      sleep: async () => {},
    })

    expect(startJob).not.toHaveBeenCalled()
    expect(__getRoleTestStoreForTests().analyst).toMatchObject({
      running: false,
      error: "Save the role before testing: analyst: model must contain at least one provider",
    })
  })

  it("starts a job, polls, and settles on the done result", async () => {
    const startJob = vi.fn().mockResolvedValue(jobResponse({ status: "queued" }))
    const getJob = vi.fn()
      .mockResolvedValueOnce(jobResponse({
        status: "running",
        provider_statuses: [{ canonical_id: "gpt-5", route_id: "a:gpt-5", status: "testing", message: null }],
      }))
      .mockResolvedValueOnce(jobResponse({ status: "completed", result: settledResult() }))

    await runRoleTest("analyst", { startJob, getJob, sleep: async () => {} })

    expect(startJob).toHaveBeenCalledWith("analyst")
    expect(getJob).toHaveBeenCalledTimes(2)
    const settled = __getRoleTestStoreForTests().analyst
    expect(settled.running).toBe(false)
    const byRole = roleTestStatusesByRole(__getRoleTestStoreForTests())
    expect(byRole.analyst[roleChainStatusKey("gpt-5", "ready:gpt-5")].status).toBe("ok")
  })

  it("settles on the failed message when the job fails", async () => {
    const startJob = vi.fn().mockResolvedValue(jobResponse({ status: "running" }))
    const getJob = vi.fn().mockResolvedValue(jobResponse({ status: "failed", message: "probe exploded" }))

    await runRoleTest("analyst", { startJob, getJob, sleep: async () => {} })

    expect(__getRoleTestStoreForTests().analyst).toMatchObject({ running: false, error: "probe exploded" })
  })
})

describe("runBundleTest (#50b)", () => {
  afterEach(() => __resetRoleTestStoreForTests())

  function jobResponse(overrides: Partial<RoleTestJobResponse>): RoleTestJobResponse {
    return {
      job_id: "bundle-job-1",
      role_name: "__bundle__primary",
      status: "running",
      provider_statuses: [],
      ...overrides,
    }
  }

  it("keys bundle test state under __bundle__{id} via startBundleTestJob", async () => {
    const startBundleJob = vi.fn().mockResolvedValue(jobResponse({ status: "queued" }))
    const getJob = vi.fn().mockResolvedValue(jobResponse({ status: "completed", result: settledResult() }))

    await runBundleTest("primary", { startBundleJob, getJob, sleep: async () => {} })

    expect(startBundleJob).toHaveBeenCalledWith("primary")
    const key = bundleTestStoreKey("primary")
    expect(key).toBe("__bundle__primary")
    const settled = __getRoleTestStoreForTests()[key]
    expect(settled.running).toBe(false)
    // The role results namespace is untouched.
    expect(__getRoleTestStoreForTests().primary).toBeUndefined()
  })
})
