import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { RunMetadata } from "@/api/types"
import { WorkspaceProvider, type WorkspaceContextValue } from "../WorkspaceContext"
import { Panels } from "./Panels"

// Timeline F1 (PM: predict 历史行仅用 icon 与真实 run 行区分,其余样式一致):
// the list shows predict attempts next to real runs; a predict row leads with
// the flask icon, a run row with its status icon — everything else identical.
const predictRun: RunMetadata = {
  run_id: "predict-abc123",
  status: "success",
  started_at: "2026-08-07T00:00:00Z",
  kind: "predict",
  metrics: null,
  input_summary: null,
}

const realRun: RunMetadata = {
  run_id: "run-def456",
  status: "success",
  started_at: "2026-08-07T00:01:00Z",
  kind: "run",
  metrics: null,
  input_summary: null,
}

vi.mock("@/hooks/useRunHistory", () => ({
  useRunHistory: () => ({
    runs: [predictRun, realRun],
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
      <Panels activePanel="trace" skillId="demo.skill" selectedNode={null} runId={null} traceEvents={[]} />
    </WorkspaceProvider>,
  )
}

describe("TimelinePanel predict rows (kind discriminator)", () => {
  it("lists predict attempts beside runs, told apart by the flask icon alone", () => {
    const html = renderTimeline()

    expect(html).toContain("predict-abc123".slice(0, 12))
    expect(html).toContain("run-def456".slice(0, 12))
    // Exactly one predict row → exactly one flask icon.
    expect(html.match(/aria-label="Predict attempt"/g)?.length).toBe(1)
  })
})
