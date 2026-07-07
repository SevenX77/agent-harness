// @vitest-environment jsdom
import { act, createElement, useEffect } from "react"
import { createRoot, type Root } from "react-dom/client"
import useSWR, { SWRConfig } from "swr"
import type { Cache } from "swr"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { RunListResponse, RunMetadata, SkillDetail } from "../api/types"
import { STUDIO_TRUTH_SWR_CONFIG } from "./studio-swr-policy"
import { useLocalHistory, useRunHistory, useRunHistoryProjection } from "./useRunHistory"

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
type RunHistoryHook = ReturnType<typeof useRunHistory>
type RunHistoryProjectionHook = ReturnType<typeof useRunHistoryProjection>

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

function runMetadata(runId: string, status: RunMetadata["status"] = "success"): RunMetadata {
  return {
    run_id: runId,
    status,
    started_at: `2026-07-07T00:00:0${runId.slice(-1)}Z`,
    metrics: null,
    input_summary: null,
  }
}

function runList(runs: RunMetadata[]): RunListResponse {
  return {
    runs,
    total: runs.length,
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

function RunHistoryHost({
  skillId,
  onHook,
}: {
  skillId: string
  onHook: (hook: RunHistoryHook) => void
}) {
  const hook = useRunHistory(skillId)
  useEffect(() => {
    onHook(hook)
  }, [hook, onHook])
  return null
}

function RunHistoryProjectionHost({
  skillId,
  onHook,
}: {
  skillId: string
  onHook: (hook: RunHistoryProjectionHook) => void
}) {
  const hook = useRunHistoryProjection(skillId)
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

describe("useRunHistory list revalidation policy", () => {
  let container: HTMLDivElement
  let root: Root
  let cache: Cache
  let runHistory: RunHistoryHook | null
  let projection: RunHistoryProjectionHook | null

  beforeEach(() => {
    cache = new Map()
    runHistory = null
    projection = null
    mocks.api.delete.mockReset()
    mocks.api.delete.mockResolvedValue({})
    mocks.fetcher.mockReset()
    mocks.fetcher.mockImplementation(async (url: string) => {
      if (url === "/skills/demo/runs") {
        return runList([runMetadata("run-1"), runMetadata("run-2")])
      }
      throw new Error(`unexpected fetch ${url}`)
    })
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

  async function renderRunHistory() {
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
          createElement(RunHistoryHost, {
            skillId: "demo",
            onHook: (hook) => {
              runHistory = hook
            },
          }),
        ),
      )
      await settle()
    })
  }

  it("projects deleted run ids locally without refetching the run list", async () => {
    await renderRunHistory()

    expect(mocks.fetcher).toHaveBeenCalledWith("/skills/demo/runs")
    expect(runHistory?.runs.map((run) => run.run_id)).toEqual(["run-1", "run-2"])
    mocks.fetcher.mockClear()

    await act(async () => {
      await runHistory?.deleteRun("run-1")
      await settle()
    })

    expect(mocks.api.delete).toHaveBeenCalledWith("/skills/demo/runs/run-1")
    expect(mocks.fetcher).not.toHaveBeenCalled()
    expect(runHistory?.runs.map((run) => run.run_id)).toEqual(["run-2"])
    expect(runHistory?.total).toBe(1)
  })

  it("projects returned run metadata locally without refetching the run list", async () => {
    await renderRunHistory()

    expect(runHistory?.runs.map((run) => run.run_id)).toEqual(["run-1", "run-2"])
    mocks.fetcher.mockClear()

    await act(async () => {
      await runHistory?.startOptimisticRun(runMetadata("run-3", "running"))
      await settle()
    })

    expect(mocks.fetcher).not.toHaveBeenCalled()
    expect(runHistory?.runs.map((run) => run.run_id)).toEqual(["run-3", "run-1", "run-2"])
    expect(runHistory?.total).toBe(3)
  })

  it("can seed the shared run-history cache without subscribing to the run list", async () => {
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
          createElement(RunHistoryProjectionHost, {
            skillId: "demo",
            onHook: (hook) => {
              projection = hook
            },
          }),
        ),
      )
      await settle()
    })

    expect(mocks.fetcher).not.toHaveBeenCalled()

    await act(async () => {
      await projection?.projectRun(runMetadata("run-1", "running"))
      await settle()
    })

    expect(mocks.fetcher).not.toHaveBeenCalled()

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
          createElement(RunHistoryProjectionHost, {
            skillId: "demo",
            onHook: (hook) => {
              projection = hook
            },
          }),
          createElement(RunHistoryHost, {
            skillId: "demo",
            onHook: (hook) => {
              runHistory = hook
            },
          }),
        ),
      )
      await settle()
    })

    expect(mocks.fetcher).not.toHaveBeenCalled()
    expect(runHistory?.runs.map((run) => run.run_id)).toEqual(["run-1"])
    expect(runHistory?.total).toBe(1)
  })
})
