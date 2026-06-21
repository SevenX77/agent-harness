import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { RunMetadata } from "@/api/types"
import { WorkspaceProvider, type WorkspaceContextValue } from "../WorkspaceContext"
import { Panels } from "./Panels"

// N4 atom #10: the run history's 耗时 column reads the typed
// `metrics.wall_time_sec` (projected from the engine through the Studio run DTO).
const runWithWallTime: RunMetadata = {
  run_id: "run-with-duration",
  status: "success",
  started_at: "2026-06-18T00:00:00Z",
  metrics: {
    input_tokens: 10,
    output_tokens: 20,
    total_tokens: 30,
    cost_estimate: null,
    wall_time_sec: 2.5,
  },
  input_summary: null,
}

const runWithoutWallTime: RunMetadata = {
  run_id: "run-no-duration",
  status: "success",
  started_at: "2026-06-18T00:00:00Z",
  metrics: {
    input_tokens: 10,
    output_tokens: 20,
    total_tokens: 30,
    cost_estimate: null,
    wall_time_sec: null,
  },
  input_summary: null,
}

let mockRuns: RunMetadata[] = [runWithWallTime]

vi.mock("@/hooks/useRunHistory", () => ({
  useRunHistory: () => ({
    runs: mockRuns,
    isLoading: false,
    error: null,
    refresh: () => undefined,
  }),
}))

const workspaceContextStub: WorkspaceContextValue = {
  currentSkillId: "demo.skill",
  navStack: [],
  activeFiles: {},
  activeFileDetails: {},
  splitMode: false,
  onFileOpen: () => undefined,
  openSplitEditor: () => undefined,
  closeFile: () => undefined,
  updateFileContent: () => undefined,
  markFileSaved: () => undefined,
  setFileInFlight: () => undefined,
  onSaveConflict: () => undefined,
  reloadOpenFile: async () => undefined,
  pushNavSkill: () => undefined,
  popNavTo: () => undefined,
}

function renderTimeline(): string {
  return renderToStaticMarkup(
    <WorkspaceProvider value={workspaceContextStub}>
      <Panels activePanel="timeline" skillId="demo.skill" selectedNode={null} runId={null} traceEvents={[]} />
    </WorkspaceProvider>,
  )
}

describe("TimelinePanel wall_time_sec", () => {
  it("renders the run duration from the typed metrics.wall_time_sec", () => {
    mockRuns = [runWithWallTime]
    const html = renderTimeline()
    expect(html).toContain("2.5s")
  })

  it("falls back to n/a when wall_time_sec is absent on the metrics", () => {
    mockRuns = [runWithoutWallTime]
    const html = renderTimeline()
    expect(html).toContain("n/a")
  })
})
