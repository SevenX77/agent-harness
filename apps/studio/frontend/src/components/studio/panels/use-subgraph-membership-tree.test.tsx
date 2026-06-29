// @vitest-environment jsdom
import { createElement } from "react"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { useSubgraphMembershipTree } from "./use-subgraph-membership-tree"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

describe("useSubgraphMembershipTree", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    ;(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {}
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
  })

  it("keeps an empty Tauri membership tree stable across parent re-renders", async () => {
    let renderCount = 0
    const snapshots: Array<ReturnType<typeof useSubgraphMembershipTree>> = []

    function Harness({ tick }: { tick: number }) {
      renderCount += 1
      const tree = useSubgraphMembershipTree({
        topLevel: [],
        enabled: tick >= 0,
      })
      snapshots.push(tree)
      return null
    }

    await act(async () => {
      root.render(createElement(Harness, { tick: 0 }))
      await Promise.resolve()
    })

    await act(async () => {
      root.render(createElement(Harness, { tick: 1 }))
      await Promise.resolve()
    })

    expect(renderCount).toBeLessThan(6)
    expect(snapshots.at(-1)).toMatchObject({
      key: "",
      topLevel: [],
      items: [],
      loading: false,
    })
  })
})
