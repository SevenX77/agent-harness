// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import { SWRConfig } from "swr"
import type { Cache } from "swr"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { TestInputMetadata } from "@/api/types"
import { STUDIO_TRUTH_SWR_CONFIG } from "@/hooks/studio-swr-policy"
import { TestInputsSection } from "./TestInputsSection"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const mocks = vi.hoisted(() => ({
  createTestInput: vi.fn(),
  deleteTestInput: vi.fn(),
  fetcher: vi.fn(),
}))

vi.mock("@/api/client", () => ({
  createTestInput: mocks.createTestInput,
  deleteTestInput: mocks.deleteTestInput,
  fetcher: mocks.fetcher,
}))

function metadata(id: string): TestInputMetadata {
  return {
    id,
    name: id,
    created_at: "2026-07-07T00:00:00.000Z",
    size_bytes: 2,
    content_preview: "{}",
  }
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

function click(element: Element) {
  element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }))
}

describe("TestInputsSection request policy", () => {
  let container: HTMLDivElement
  let root: Root
  let cache: Cache

  beforeEach(() => {
    cache = new Map()
    mocks.createTestInput.mockReset()
    mocks.deleteTestInput.mockReset()
    mocks.fetcher.mockReset()
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
  })

  async function renderSection(props: {
    initialItems: TestInputMetadata[]
    selectedId?: string | null
    onSelect?: (id: string | null) => void
    onFileOpen?: (path: string) => void
  }) {
    mocks.fetcher.mockResolvedValue(props.initialItems)
    await act(async () => {
      root.render(
        createElement(
          SWRConfig,
          {
            value: {
              provider: () => cache,
              dedupingInterval: 0,
              focusThrottleInterval: 0,
              ...STUDIO_TRUTH_SWR_CONFIG,
            },
          },
          createElement(TestInputsSection, {
            skillId: "demo",
            workspaceRoot: "workspace-root",
            selectedId: props.selectedId ?? null,
            onSelect: props.onSelect,
            onFileOpen: props.onFileOpen,
          }),
        ),
      )
      await settle()
    })
  }

  it("projects created test input metadata without refetching the list", async () => {
    const onFileOpen = vi.fn()
    mocks.createTestInput.mockResolvedValue(metadata("input-1"))
    await renderSection({ initialItems: [], onFileOpen })

    expect(mocks.fetcher).toHaveBeenCalledWith("/skills/demo/test_inputs")
    mocks.fetcher.mockClear()

    const button = container.querySelector('[aria-label="New test input file"]')
    expect(button).not.toBeNull()
    await act(async () => {
      click(button as Element)
      await settle()
    })

    expect(mocks.createTestInput).toHaveBeenCalledWith(
      "demo",
      "input-1",
      {},
      { workspaceRoot: "workspace-root" },
    )
    expect(mocks.fetcher).not.toHaveBeenCalled()
    expect(onFileOpen).toHaveBeenCalledWith(".workspace/import_files/input-1.json")
    expect(container.textContent).toContain("input-1")
  })

  it("projects deleted test input locally without refetching the list", async () => {
    const onSelect = vi.fn()
    mocks.deleteTestInput.mockResolvedValue(undefined)
    await renderSection({
      initialItems: [metadata("input-1"), metadata("input-2")],
      selectedId: "input-1",
      onSelect,
    })

    expect(container.textContent).toContain("input-1")
    expect(container.textContent).toContain("input-2")
    mocks.fetcher.mockClear()

    const button = container.querySelector('[aria-label="Delete test input input-1"]')
    expect(button).not.toBeNull()
    await act(async () => {
      click(button as Element)
      await settle()
    })

    expect(mocks.deleteTestInput).toHaveBeenCalledWith(
      "demo",
      "input-1",
      { workspaceRoot: "workspace-root" },
    )
    expect(mocks.fetcher).not.toHaveBeenCalled()
    expect(onSelect).toHaveBeenCalledWith(null)
    expect(container.textContent).not.toContain("input-1")
    expect(container.textContent).toContain("input-2")
  })
})
