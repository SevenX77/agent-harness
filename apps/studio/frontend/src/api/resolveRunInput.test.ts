import { describe, expect, it, vi } from "vitest"
import { resolveRunInput } from "./client"
import type { TestInputDetail } from "./types"

describe("resolveRunInput", () => {
  it("returns an empty payload when no test input is selected", async () => {
    // Design 01_workflows/04_run-and-verify.md:35 (PM verbatim): "input 和 batch
    // 都是节点配置问题, 和 predict 无关, predict 和 run 就是按照配置来跑就行了".
    // With no selected test input the graph's root inputs come from the
    // runtime_config import bindings the backend already owns — the client must
    // not invent a precondition and block the request. A genuinely unsourced
    // required field is reported by the backend preflight
    // (STUDIO_RUNTIME_INPUT_MISSING) through the one diagnostics pipeline.
    const getInput = vi.fn()

    await expect(resolveRunInput("skill-1", null, getInput)).resolves.toEqual({})
    expect(getInput).not.toHaveBeenCalled()
  })

  it("fetches and returns the selected input's content", async () => {
    const detail: TestInputDetail = {
      id: "case-a",
      name: "case-a",
      content: { input_text: "hello" },
    }
    const getInput = vi.fn().mockResolvedValue(detail)

    const result = await resolveRunInput("skill-1", "case-a", getInput)

    expect(getInput).toHaveBeenCalledWith("skill-1", "case-a")
    expect(result).toEqual({ input_text: "hello" })
  })

  it("propagates a fetch failure instead of silently running empty", async () => {
    const getInput = vi.fn().mockRejectedValue(new Error("deleted"))

    await expect(resolveRunInput("skill-1", "gone", getInput)).rejects.toThrow("deleted")
  })
})
