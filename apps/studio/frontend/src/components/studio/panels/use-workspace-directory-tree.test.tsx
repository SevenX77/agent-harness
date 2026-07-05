// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { SkillDetail } from "@/api/types"
import { useWorkspaceDirectoryTree, type WorkspaceDirectoryTree } from "./use-workspace-directory-tree"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const mocks = vi.hoisted(() => ({
  isTauriRuntime: vi.fn(() => true),
  listWorkspaceDir: vi.fn(),
}))

vi.mock("@/config/runtime", () => ({
  isTauriRuntime: mocks.isTauriRuntime,
}))

vi.mock("@/lib/tauri", () => ({
  listWorkspaceDir: mocks.listWorkspaceDir,
}))

const detail: SkillDetail = {
  manifest: {
    schema_version: "v0.3.0",
    name: "writer-smoke",
    description: "Fixture",
    io: {
      inputs: { type: "object", properties: {} },
      outputs: { type: "object", properties: {} },
    },
    phases: [],
  },
  graph_topology: [],
  node_schema_v21: {},
  io_schema: {},
  file_paths: {},
  files: {},
  manifest_errors: null,
  has_golden: false,
  latest_run_metadata: null,
  lint_result: null,
}

describe("useWorkspaceDirectoryTree", () => {
  let container: HTMLDivElement
  let root: Root
  let tree: WorkspaceDirectoryTree | null

  beforeEach(() => {
    mocks.isTauriRuntime.mockReturnValue(true)
    mocks.listWorkspaceDir.mockReset()
    mocks.listWorkspaceDir.mockImplementation(async (_workspaceRoot: string, relativeDir: string) => {
      if (relativeDir === ".") {
        return [
          { name: "phases", kind: "dir" },
          { name: "GRAPH.md", kind: "file" },
        ]
      }
      if (relativeDir === "phases") {
        return [{ name: "draft", kind: "dir" }]
      }
      return []
    })
    tree = null
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

  function Host(): null {
    tree = useWorkspaceDirectoryTree({
      workspaceRoot: "D:/workspace/writer-smoke",
      skillId: "writer-smoke",
      skillDetail: detail,
      enabled: true,
    })
    return null
  }

  it("loads only the root directory first and does not refresh loaded folders on focus", async () => {
    await act(async () => {
      root.render(<Host />)
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mocks.listWorkspaceDir).toHaveBeenCalledTimes(1)
    expect(mocks.listWorkspaceDir).toHaveBeenCalledWith("D:/workspace/writer-smoke", ".")

    await act(async () => {
      tree?.ensureDirectory("phases")
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mocks.listWorkspaceDir).toHaveBeenCalledTimes(2)
    expect(mocks.listWorkspaceDir).toHaveBeenLastCalledWith("D:/workspace/writer-smoke", "phases")

    act(() => {
      window.dispatchEvent(new Event("focus"))
      document.dispatchEvent(new Event("visibilitychange"))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mocks.listWorkspaceDir).toHaveBeenCalledTimes(2)
  })
})
