// @vitest-environment jsdom
import { act, type InputHTMLAttributes } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { mutate } from "swr"
import type { RolesData } from "@/api/llm"
import { api, resetClientReadCachesForTests } from "@/api/client"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import {
  createBackendRequestRecorder,
  expectNoBackendRequestsDuring,
} from "@/testing/network-side-effect-guard"
import { PropertiesPanel } from "./PropertiesPanel"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const llmMocks = vi.hoisted(() => ({
  getModelGroups: vi.fn(),
  getRoles: vi.fn(),
  startCompareCandidateTestJob: vi.fn(),
}))

const toastMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
}))

const eventStreamMocks = vi.hoisted(() => ({
  callbacks: null as null | {
    onRegistryChanged: () => void
    onRolesChanged: () => void
  },
}))

vi.mock("@/api/llm", () => ({
  getModelGroups: llmMocks.getModelGroups,
  getRoles: llmMocks.getRoles,
  startCompareCandidateTestJob: llmMocks.startCompareCandidateTestJob,
}))

vi.mock("sonner", () => ({
  toast: toastMocks,
}))

vi.mock("@/hooks/useStudioEventStream", () => ({
  useStudioEventStream: (
    callbacks: {
      onRegistryChanged: () => void
      onRolesChanged: () => void
    },
  ) => {
    eventStreamMocks.callbacks = callbacks
    return { connectionLost: false }
  },
}))

vi.mock("@/components/ui/slider", () => ({
  Slider: ({
    value,
    onValueChange,
    onValueCommit,
    ...props
  }: {
    value: number[]
    onValueChange?: (value: number[]) => void
    onValueCommit?: (value: number[]) => void
  } & InputHTMLAttributes<HTMLInputElement>) => (
    <input
      {...props}
      type="range"
      value={value[0]}
      onChange={(event) => onValueChange?.([Number(event.currentTarget.value)])}
      onBlur={(event) => onValueCommit?.([Number(event.currentTarget.value)])}
    />
  ),
}))

function emptyRoles(): RolesData {
  return { schema_version: 3, models: {}, providers: {}, roles: {} }
}

function selectedAgentNode(id: string): { id: string; data: SkillGraphNodeData } {
  return {
    id,
    data: {
      skillId: "demo",
      label: id,
      mode: "llm",
      status: "idle",
      dependsOn: [],
      filePath: `phases/${id}/SKILL.md`,
    },
  }
}

function multiNodeSkillDetail(): SkillDetail {
  const phaseMarkdown = (name: string) => [
    "---",
    `name: ${name}`,
    "llm_role: analyst",
    "---",
    `<role>${name}</role>`,
  ].join("\n")

  return {
    files: {
      "GRAPH.md": [
        "---",
        'schema_version: "v0.3.0"',
        "name: demo",
        "phases:",
        "  - setup",
        "  - review",
        "---",
        '<phase id="setup" />',
        '<phase id="review" />',
      ].join("\n"),
      "phases/setup/SKILL.md": phaseMarkdown("setup"),
      "phases/review/SKILL.md": phaseMarkdown("review"),
    },
    graph_topology: [
      { id: "setup", src: "phases/setup/SKILL.md", depends_on: [], mode: "skill" },
      { id: "review", src: "phases/review/SKILL.md", depends_on: ["setup"], mode: "skill" },
    ],
  } as unknown as SkillDetail
}

function renderPanel(root: Root, selectedId: string, detail: SkillDetail): void {
  act(() => {
    root.render(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={detail}
        selectedNode={selectedAgentNode(selectedId)}
      />,
    )
  })
}

async function settleEffects(): Promise<void> {
  await act(async () => {
    vi.runOnlyPendingTimers()
    for (let i = 0; i < 8; i += 1) {
      await Promise.resolve()
    }
  })
}

describe("PropertiesPanel network side-effect guard", () => {
  beforeEach(async () => {
    vi.useFakeTimers()
    resetClientReadCachesForTests()
    await mutate(() => true, undefined, { revalidate: false })
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )
    llmMocks.getRoles.mockResolvedValue(emptyRoles())
    llmMocks.getModelGroups.mockResolvedValue([])
    llmMocks.startCompareCandidateTestJob.mockResolvedValue({ status: "ready", summary: "ok", details: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    api.defaults.adapter = undefined
    resetClientReadCachesForTests()
    document.body.innerHTML = ""
    vi.clearAllMocks()
  })

  it("keeps node selection backend-silent after skill-scoped node config is loaded", async () => {
    const detail = multiNodeSkillDetail()
    const recorder = createBackendRequestRecorder({
      "GET /skills/demo/node-llm-params": {
        nodes: {
          setup: { enabled: true, thinking: null, max_output_tokens: null, temperature: 0.4 },
          review: { enabled: true, thinking: true, max_output_tokens: 2048, temperature: 0.7 },
        },
      },
      "GET /skills/demo/compare-candidates": {
        nodes: {
          setup: [],
          review: [],
        },
      },
    })
    api.defaults.adapter = recorder.adapter

    const container = document.createElement("div")
    document.body.appendChild(container)
    const root = createRoot(container)
    renderPanel(root, "review", detail)
    await settleEffects()

    expect(recorder.requests.map((request) => `${request.method} ${request.url}`).sort()).toEqual([
      "GET /skills/demo/node-llm-params",
      "GET /skills/demo/compare-candidates",
    ].sort())

    await expectNoBackendRequestsDuring(recorder, async () => {
      renderPanel(root, "setup", detail)
      await settleEffects()
    })

    act(() => root.unmount())
  })
})
