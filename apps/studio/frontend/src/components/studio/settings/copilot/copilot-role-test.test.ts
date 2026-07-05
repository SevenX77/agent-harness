import { describe, expect, it, vi } from "vitest"
import {
  copilotRoleTestErrorMessage,
  ERROR_CODE_MAP,
  runCopilotRoleTestJob,
  copilotRouteMessagesFromJob,
  copilotRouteMessagesFromPersistedResult,
  copilotRouteStatusesFromJob,
  copilotRouteStatusesFromPersistedResult,
} from "./copilot-role-test"
import type { RoleTestJobResponse } from "@/api/llm"

describe("copilot route SDK test messages surface the real failure reason", () => {
  it("extracts per-route messages from a live job", () => {
    const job = {
      provider_statuses: [
        { route_id: "deepseek-official:deepseek-v4-pro", status: "failed", message: "SDK returned an error: HTTP 404" },
        { route_id: "qiniu-anthropic:deepseek.deepseek-v4-pro", status: "ok", message: null },
      ],
    } as unknown as RoleTestJobResponse

    expect(copilotRouteMessagesFromJob(job)).toEqual({
      "deepseek-official:deepseek-v4-pro": "SDK returned an error: HTTP 404",
    })
  })

  it("extracts per-route messages from persisted sdk_evidence", () => {
    const result = {
      sdk_evidence: {
        routes: {
          "deepseek-official:deepseek-v4-pro": { status: "failed", message: "Request timed out. Check network or proxy settings." },
          "qiniu-anthropic:deepseek.deepseek-v4-pro": { status: "ok", message: null },
        },
      },
    }
    expect(copilotRouteMessagesFromPersistedResult(result)).toEqual({
      "deepseek-official:deepseek-v4-pro": "Request timed out. Check network or proxy settings.",
    })
  })
})

describe("copilot role test job helpers", () => {
  it("starts role test jobs and polls until completion with route status progress", async () => {
    const running: RoleTestJobResponse = {
      job_id: "job-1",
      role_name: "copilot_opus_4_7",
      status: "running",
      message: "Testing role routes.",
      provider_statuses: [
        {
          canonical_id: "claude-opus-4-7",
          route_id: "anthropic-official:claude-opus-4-7",
          status: "testing",
          message: null,
        },
      ],
      result: null,
    }
    const completed: RoleTestJobResponse = {
      ...running,
      status: "completed",
      message: "Role test completed.",
      provider_statuses: [
        {
          canonical_id: "claude-opus-4-7",
          route_id: "anthropic-official:claude-opus-4-7",
          status: "ok",
          message: null,
        },
      ],
      result: {
        role_name: "copilot_opus_4_7",
        status: "ok",
        warnings: [],
        model_groups: [],
      },
    }
    const onProgress = vi.fn()
    const startJob = vi.fn(async () => running)
    const getJob = vi.fn(async () => completed)

    const result = await runCopilotRoleTestJob("copilot_opus_4_7", {
      startJob,
      getJob,
      sleep: async () => undefined,
      onProgress,
    })

    expect(startJob).toHaveBeenCalledWith("copilot_opus_4_7")
    expect(getJob).toHaveBeenCalledWith("job-1")
    expect(onProgress).toHaveBeenCalledWith(running)
    expect(onProgress).toHaveBeenCalledWith(completed)
    expect(result.status).toBe("ok")
    expect(copilotRouteStatusesFromJob(completed)).toEqual({
      "anthropic-official:claude-opus-4-7": "ready",
    })
  })

  it("marks failed and blocked role test providers as unsupported", () => {
    const job: RoleTestJobResponse = {
      job_id: "job-2",
      role_name: "copilot_deepseek_v4",
      status: "completed",
      message: "Role test completed.",
      provider_statuses: [
        {
          canonical_id: "deepseek-v4-pro",
          route_id: "deepseek-official:deepseek-v4-pro",
          status: "failed",
          message: "provider rejected request",
        },
        {
          canonical_id: "deepseek-v4-pro",
          route_id: "qiniu-anthropic:deepseek-v4-pro",
          status: "blocked",
          message: "missing API key",
        },
      ],
      result: {
        role_name: "copilot_deepseek_v4",
        status: "failed",
        warnings: [],
        model_groups: [],
      },
    }

    // R-F11: failed/blocked now map to the 6-state "failed" light (was the
    // legacy "unsupported" alias), so route lights align with LlmRolesTab.
    expect(copilotRouteStatusesFromJob(job)).toEqual({
      "deepseek-official:deepseek-v4-pro": "failed",
      "qiniu-anthropic:deepseek-v4-pro": "failed",
    })
  })

  it("keeps backend role lookup details without showing raw Axios 404 text", () => {
    const message = copilotRoleTestErrorMessage({
      message: "Request failed with status code 404",
      response: {
        status: 404,
        data: { detail: "Unknown LLM role: copilot_opus_4_7" },
      },
    }, "Opus 4.7 Copilot")

    expect(message).toBe("Opus 4.7 Copilot test failed: Unknown LLM role: copilot_opus_4_7")
  })

  it("keeps backend failure details without rewriting the reason", () => {
    const message = copilotRoleTestErrorMessage({
      message: "Request failed with status code 500",
      response: {
        status: 500,
        data: { detail: "Role test job crashed" },
      },
    }, "DeepSeek V4 Copilot")

    expect(message).toBe("DeepSeek V4 Copilot test failed: Role test job crashed")
  })

})

describe("R20 persisted copilot route status seeding", () => {
  it("maps persisted sdk_evidence route verdicts into route status overrides", () => {
    const result = {
      role_name: "copilot_opus_4_7",
      status: "ok",
      model_groups: [],
      sdk_evidence: {
        tested: true,
        passed: 1,
        total: 2,
        routes: {
          "anthropic-official:claude-opus-4-7": { status: "ok", message: null },
          "qiniu-anthropic:claude-opus-4-7": { status: "failed", message: "boom" },
        },
      },
    }

    expect(copilotRouteStatusesFromPersistedResult(result)).toEqual({
      "anthropic-official:claude-opus-4-7": "ready",
      "qiniu-anthropic:claude-opus-4-7": "failed",
    })
  })

  it("returns an empty map when persisted result has no sdk_evidence routes", () => {
    expect(copilotRouteStatusesFromPersistedResult(null)).toEqual({})
    expect(copilotRouteStatusesFromPersistedResult({ status: "ok" })).toEqual({})
    expect(
      copilotRouteStatusesFromPersistedResult({ sdk_evidence: { routes: {} } }),
    ).toEqual({})
  })

  it("skips route entries with a non-string status", () => {
    const result = {
      sdk_evidence: {
        routes: {
          "good:route": { status: "ok" },
          "bad:route": { status: 42 },
          "missing:route": {},
        },
      },
    }

    expect(copilotRouteStatusesFromPersistedResult(result)).toEqual({
      "good:route": "ready",
    })
  })
})

describe("R-F9 copilotRoleTestErrorMessage prefers error_code → human text", () => {
  it("uses ERROR_CODE_MAP for resource.no_available_route", () => {
    const message = copilotRoleTestErrorMessage(
      { error_code: "resource.no_available_route", message: "raw backend tail" },
      "Claude Opus 4.7",
    )
    expect(message).toContain("Claude Opus 4.7")
    expect(message).toContain("has no available model route")
    // No raw exception class names leak.
    expect(message).not.toContain("ResourceTerminalError")
    expect(message).not.toContain("raw backend tail")
  })

  it("falls through to the existing axios-detail path when no error_code is present", () => {
    const message = copilotRoleTestErrorMessage(
      {
        message: "Request failed with status code 404",
        response: { status: 404, data: { detail: "Unknown LLM role" } },
      },
      "DeepSeek V4",
    )
    expect(message).toBe("DeepSeek V4 test failed: Unknown LLM role")
  })

  it("ERROR_CODE_MAP covers each backend code the helper emits", () => {
    expect(ERROR_CODE_MAP["resource.no_available_route"]("X")).toContain("has no available model route")
    expect(ERROR_CODE_MAP["resource.role_unknown"]("X")).toContain("does not exist or was deleted")
    expect(ERROR_CODE_MAP["resource.role_invalid_kind"]("X")).toContain("is not a copilot role")
    expect(ERROR_CODE_MAP["resource.credential_missing"]("X")).toContain("is missing a required API key")
  })

  it("R-F11 cooling_down provider status surfaces as the cooling_down route light", () => {
    const job: RoleTestJobResponse = {
      job_id: "job-cd",
      role_name: "copilot_opus_4_7",
      status: "running",
      message: "Testing role routes.",
      provider_statuses: [
        {
          canonical_id: "claude-opus-4-7",
          route_id: "anthropic-official:claude-opus-4-7",
          status: "cooling_down",
          message: "rate-limited",
          retry_after_seconds: 42,
        },
      ],
      result: null,
    }
    expect(copilotRouteStatusesFromJob(job)).toEqual({
      "anthropic-official:claude-opus-4-7": "cooling_down",
    })
  })

  it("R-F11 untested provider status maps to the untested route light (was not_tested alias)", () => {
    const job: RoleTestJobResponse = {
      job_id: "job-untested",
      role_name: "copilot_opus_4_7",
      status: "queued",
      message: null,
      provider_statuses: [
        {
          canonical_id: "claude-opus-4-7",
          route_id: "anthropic-official:claude-opus-4-7",
          status: "untested",
          message: null,
        },
      ],
      result: null,
    }
    expect(copilotRouteStatusesFromJob(job)).toEqual({
      "anthropic-official:claude-opus-4-7": "untested",
    })
  })

  it("runCopilotRoleTestJob propagates error_code so the catch handler can map it", async () => {
    const failed: RoleTestJobResponse = {
      job_id: "job-3",
      role_name: "copilot_opus_4_7",
      status: "failed",
      message: "Claude Opus 4.7 has no available model route...",
      error_code: "resource.no_available_route",
      error_payload: { role: "copilot_opus_4_7" },
      provider_statuses: [],
      result: null,
    }
    const startJob = vi.fn(async () => failed)
    const getJob = vi.fn(async () => failed)
    let caught: unknown = null
    try {
      await runCopilotRoleTestJob("copilot_opus_4_7", { startJob, getJob, sleep: async () => undefined })
    } catch (err) {
      caught = err
    }
    expect(caught).not.toBeNull()
    expect((caught as { error_code?: string }).error_code).toBe("resource.no_available_route")
    expect(copilotRoleTestErrorMessage(caught, "Claude Opus 4.7")).toContain("has no available model route")
  })
})
