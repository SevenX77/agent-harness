import { describe, expect, it, vi } from "vitest"
import {
  copilotRoleTestErrorMessage,
  runCopilotRoleTestJob,
  copilotRouteStatusesFromJob,
} from "./copilot-role-test"
import type { RoleTestJobResponse } from "@/api/llm"

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

    expect(copilotRouteStatusesFromJob(job)).toEqual({
      "deepseek-official:deepseek-v4-pro": "unsupported",
      "qiniu-anthropic:deepseek-v4-pro": "unsupported",
    })
  })

  it("explains missing backend copilot roles without showing raw Axios 404 text", () => {
    const message = copilotRoleTestErrorMessage({
      message: "Request failed with status code 404",
      response: {
        status: 404,
        data: { detail: "Unknown LLM role: copilot_opus_4_7" },
      },
    }, "Opus 4.7 Copilot")

    expect(message).toBe(
      "Opus 4.7 Copilot 测试失败：后端还没有创建 Copilot role `copilot_opus_4_7`。请先迁移或创建该 role 后再测试。",
    )
  })

  it("keeps backend failure details but translates the request wrapper", () => {
    const message = copilotRoleTestErrorMessage({
      message: "Request failed with status code 500",
      response: {
        status: 500,
        data: { detail: "Role test job crashed" },
      },
    }, "DeepSeek V4 Copilot")

    expect(message).toBe("DeepSeek V4 Copilot 测试失败：后端服务执行失败。Role test job crashed")
  })
})
