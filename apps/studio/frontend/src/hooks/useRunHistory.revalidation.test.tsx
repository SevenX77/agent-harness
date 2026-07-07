// @vitest-environment jsdom
import { act, createElement, useEffect } from "react"
import { createRoot, type Root } from "react-dom/client"
import useSWR, { SWRConfig } from "swr"
import type { Cache } from "swr"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { SkillDetail } from "../api/types"
import { STUDIO_TRUTH_SWR_CONFIG } from "./studio-swr-policy"
import { useLocalHistory } from "./useRunHistory"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const mocks = vi.hoisted(() => ({
  api: {
    delete: vi.fn(),
    get: vi.fn(),
  },
  fetcher: vi.fn(),
  getLocalHistory: vi.fn(),
  revertSkill: vi.fn(),
}))

vi.mock("../api/client", () => ({
  api: mocks.api,
  fetcher: mocks.fetcher,
  getLocalHistory: mocks.getLocalHistory,
  revertSkill: mocks.revertSkill,
}))

type LocalHistoryHook = ReturnType<typeof useLocalHistory>

function skillDetail(name: string): SkillDetail {
  return {
    manifest: {
      schema_version: "v0.3.0",
      name,
      description: "",
      phases: [],
      io: {
        inputs: { type: "object", properties: {} },
        outputs: { type: "object", properties: {} },
      },
    },
    files: {},
    graph_topology: [],
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}

function SkillDetailSubscriber({ skillId }: { skillId: string }) {
  useSWR(`/skills/${skillId}`, mocks.fetcher, STUDIO_TRUTH_SWR_CONFIG)
  return null
}

function LocalHistoryHost({
  skillId,
  onHook,
}: {
  skillId: string
  onHook: (hook: LocalHistoryHook) => void
}) {
  const hook = useLocalHistory(skillId)
  useEffect(() => {
    onHook(hook)
  }, [hook, onHook])
  return null
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

describe("useLocalHistory skill detail revalidation policy", () => {
  let container: HTMLDivElement
  let root: Root
  let cache: Cache
  let localHistory: LocalHistoryHook | null

  beforeEach(() => {
    cache = new Map()
    localHistory = null
    mocks.fetcher.mockReset()
    mocks.fetcher.mockResolvedValue(skillDetail("cold-load"))
    mocks.getLocalHistory.mockReset()
    mocks.getLocalHistory.mockResolvedValue([])
    mocks.revertSkill.mockReset()
    mocks.revertSkill.mockResolvedValue(skillDetail("reverted"))
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

  it("projects revert's returned SkillDetail without refetching the same skill detail", async () => {
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
          createElement(SkillDetailSubscriber, { skillId: "demo" }),
          createElement(LocalHistoryHost, {
            skillId: "demo",
            onHook: (hook) => {
              localHistory = hook
            },
          }),
        ),
      )
      await settle()
    })

    expect(mocks.fetcher).toHaveBeenCalledWith("/skills/demo")
    mocks.fetcher.mockClear()

    await act(async () => {
      const reverted = await localHistory?.revert("abc123")
      expect(reverted).toMatchObject({ manifest: { name: "reverted" } })
      await settle()
    })

    expect(mocks.revertSkill).toHaveBeenCalledWith("demo", "abc123")
    expect(mocks.fetcher).not.toHaveBeenCalled()
  })
})
