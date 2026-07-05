import { describe, expect, it, vi } from "vitest"
import { resolveRunInput } from "./client"
import type { TestInputDetail } from "./types"

describe("resolveRunInput", () => {
  it("rejects when no input is selected", async () => {
    const getInput = vi.fn()

    await expect(resolveRunInput("skill-1", null, getInput)).rejects.toThrow(
      "Select a compile-valid test input before Predict/Run.",
    )
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
