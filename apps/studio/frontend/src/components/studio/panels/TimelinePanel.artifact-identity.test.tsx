import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { RunMetadata } from "@/api/types"
import { WorkspaceProvider, type WorkspaceContextValue } from "../WorkspaceContext"
import { Panels } from "./Panels"

const runWithArtifactIdentity: RunMetadata = {
  run_id: "run-artifact-identity",
  status: "success",
  started_at: "2026-06-18T00:00:00Z",
  metrics: null,
  input_summary: null,
  artifact_ref: {
    artifact_id: "demo.skill",
    content_hash: `sha256:${"a".repeat(64)}`,
    store: "ephemeral",
    version: null,
    manifest_ref: "file:///tmp/manifest.json",
    source_map_ref: "file:///tmp/source-map.json",
    execution_fingerprint: `sha256:${"b".repeat(64)}`,
  },
  source_map_ref: "file:///tmp/source-map.json",
  execution_fingerprint: `sha256:${"b".repeat(64)}`,
}

vi.mock("@/hooks/useRunHistory", () => ({
  useRunHistory: () => ({
    runs: [runWithArtifactIdentity],
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

describe("TimelinePanel artifact identity", () => {
  it("shows artifact content hash and execution fingerprint from RunMetadata", () => {
    const html = renderTimeline()

    expect(html).toContain("art aaaaaaaa")
    expect(html).toContain("fp bbbbbbbb")
    expect(html).toContain("demo.skill")
  })
})
