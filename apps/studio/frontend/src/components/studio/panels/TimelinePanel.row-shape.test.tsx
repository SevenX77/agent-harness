import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { RunMetadata } from "@/api/types"
import { WorkspaceProvider, type WorkspaceContextValue } from "../WorkspaceContext"
import { Panels } from "./Panels"

// Decision 2026-08-09 D9: "行首固定为类型图标(run = `Play`,predict = `FlaskConical`,
// 中性色,不承载状态)→ 完整 run_id → 状态图标徽章(与 D3 同一套)。与 Trace 顶条
// 同构,两屏读法一致。" — the old row put type and status in the SAME leading
// position, so one slot sometimes said "this is a predict" and sometimes said
// "this succeeded", and truncated the run_id to 12 characters on top of it.
//
// Decision D8 entrance ②: "运行列表每一行带报告链接。"

const FULL_RUN_ID = "2026-08-09T14-32-07_9f3ac1de"
const FULL_PREDICT_ID = "predict-2026-08-09T14-30-11_1b2c3d4e"

const failedRun: RunMetadata = {
  run_id: FULL_RUN_ID,
  status: "failed",
  started_at: "2026-08-09T14:32:07Z",
  kind: "run",
  metrics: null,
  input_summary: null,
  report_path: "D:/skills/demo/.workspace/runs/run-1/report.md",
}

const succeededPredict: RunMetadata = {
  run_id: FULL_PREDICT_ID,
  status: "success",
  started_at: "2026-08-09T14:30:11Z",
  kind: "predict",
  metrics: null,
  input_summary: null,
}

vi.mock("@/hooks/useRunHistory", () => ({
  useRunHistory: () => ({
    runs: [failedRun, succeededPredict],
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

describe("TimelinePanel row shape (D9)", () => {
  it("shows the run id in full, never truncated", () => {
    const html = renderTimeline()

    expect(html).toContain(FULL_RUN_ID)
    expect(html).toContain(FULL_PREDICT_ID)
    expect(html).not.toContain(`${FULL_RUN_ID.slice(0, 12)}...`)
  })

  it("leads with the type, which never carries the status", () => {
    const html = renderTimeline()

    // One run + one predict → one of each type mark, regardless of outcome.
    expect(html.match(/data-run-type="run"/g)).toHaveLength(1)
    expect(html.match(/data-run-type="predict"/g)).toHaveLength(1)
    // A FAILED run still leads with the neutral run icon: the type mark must
    // not be tinted by the outcome (that is the status badge's one job).
    const typeMark = html.slice(html.indexOf('data-run-type="run"'))
    expect(typeMark.slice(0, 200)).not.toContain("text-destructive")
  })

  it("states the status in its own badge, the same vocabulary the trace strip uses", () => {
    const html = renderTimeline()

    expect(html).toContain('data-run-status="failed"')
    expect(html).toContain('data-run-status="success"')
    expect(html).toContain('aria-label="Run failed"')
    expect(html).toContain('aria-label="Run succeeded"')
  })

  it("offers the report on the row that has one, and only there (D8 entrance ②)", () => {
    const html = renderTimeline()

    expect(html.match(/data-run-report/g)).toHaveLength(1)
    expect(html).toContain('aria-label="Open report for run 2026-08-09T14-32-07_9f3ac1de"')
  })
})
