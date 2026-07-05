// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { JsonValue } from "@/api/types"
import { resetCopilotContextPostCacheForTests, useCopilotContext } from "./useCopilotContext"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
}))

vi.mock("../api/client", () => ({
  api: {
    post: mocks.post,
  },
}))

function Host({ context }: { context: Record<string, JsonValue> }): null {
  useCopilotContext({
    skillId: "writer-smoke",
    view: "Edit",
    context,
    debounceMs: 10,
  })
  return null
}

describe("useCopilotContext", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.useFakeTimers()
    mocks.post.mockReset()
    mocks.post.mockResolvedValue({ data: {} })
    resetCopilotContextPostCacheForTests()
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    vi.useRealTimers()
    resetCopilotContextPostCacheForTests()
  })

  async function advanceContextDebounce(): Promise<void> {
    await act(async () => {
      await Promise.resolve()
    })
    await act(async () => {
      vi.advanceTimersByTime(10)
      await Promise.resolve()
    })
  }

  it("does not post identical context again across rerenders", async () => {
    await act(async () => {
      root.render(<Host context={{ selected_node_id: "draft" }} />)
    })
    await advanceContextDebounce()

    expect(mocks.post).toHaveBeenCalledTimes(1)

    await act(async () => {
      root.render(<Host context={{ selected_node_id: "draft" }} />)
    })
    await advanceContextDebounce()

    expect(mocks.post).toHaveBeenCalledTimes(1)

    await act(async () => {
      root.render(<Host context={{ selected_node_id: "review" }} />)
    })
    await advanceContextDebounce()

    expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(mocks.post).toHaveBeenLastCalledWith(
      "/skills/writer-smoke/copilot/context",
      expect.objectContaining({
        view: "Edit",
        context: { selected_node_id: "review" },
      }),
    )
  })
})
