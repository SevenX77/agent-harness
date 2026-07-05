// @vitest-environment jsdom
import { act, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { mutate } from "swr"
import type { RolesData } from "@/api/llm"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { PropertiesPanel } from "./PropertiesPanel"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

type PhaseFileSavePayload = { path: string; content: string; expectedHash: string }
type PhaseFileSaveHandler = (payload: PhaseFileSavePayload) => Promise<void>

const apiMocks = vi.hoisted(() => ({
  getChildGraphTopology: vi.fn(),
  getCompareCandidates: vi.fn(),
  getNodeLlmParams: vi.fn(),
  putNodeCompareCandidates: vi.fn(),
  putNodeLlmParams: vi.fn(),
}))

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

vi.mock("@/api/client", () => ({
  getChildGraphTopology: apiMocks.getChildGraphTopology,
  getCompareCandidates: apiMocks.getCompareCandidates,
  getNodeLlmParams: apiMocks.getNodeLlmParams,
  putNodeCompareCandidates: apiMocks.putNodeCompareCandidates,
  putNodeLlmParams: apiMocks.putNodeLlmParams,
}))

vi.mock("@/api/llm", () => ({
  getModelGroups: llmMocks.getModelGroups,
  getRoles: llmMocks.getRoles,
  startCompareCandidateTestJob: llmMocks.startCompareCandidateTestJob,
}))

vi.mock("sonner", () => ({
  toast: toastMocks,
}))

function renderJsx(node: ReactNode): { container: HTMLDivElement; root: Root } {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(node)
  })
  return { container, root }
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set
  act(() => {
    setter?.call(input, value)
    input.dispatchEvent(new Event("input", { bubbles: true }))
  })
}

async function flushAutosave() {
  await act(async () => {
    vi.advanceTimersByTime(300)
    for (let i = 0; i < 6; i += 1) {
      await Promise.resolve()
    }
  })
}

async function settleEffects() {
  await act(async () => {
    vi.runOnlyPendingTimers()
    for (let i = 0; i < 8; i += 1) {
      await Promise.resolve()
    }
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function emptyRoles(): RolesData {
  return { schema_version: 3, models: {}, providers: {}, roles: {} }
}

function rolesWithAnalystFallback(): RolesData {
  return {
    schema_version: 3,
    providers: {},
    models: {
      "gpt-5": {
        providers: ["ready:gpt-5"],
        temperature: null,
        max_tokens: null,
      },
    },
    roles: {
      analyst: {
        role_kind: "graph",
        model_fallback_enabled: true,
        active_model: "gpt-5",
        models: {
          "gpt-5": { providers: ["ready:gpt-5"], temperature: null, max_tokens: null },
        },
        intent: {
          provider_preference: "manual_order",
          thinking: true,
          max_output_tokens: 1234,
          temperature: 0.7,
        },
        fallback_chain: [],
      },
    },
  } as unknown as RolesData
}

function graphSkillDetail(graphMarkdown: string): SkillDetail {
  return {
    files: { "GRAPH.md": graphMarkdown },
    graph_topology: [],
  } as unknown as SkillDetail
}

function phaseSkillDetail(phaseMarkdown: string): SkillDetail {
  return {
    files: {
      "GRAPH.md": [
        "---",
        'schema_version: "v0.3.0"',
        "name: demo",
        "phases:",
        "  - review",
        "---",
        '<phase id="review" />',
      ].join("\n"),
      "phases/review/SKILL.md": phaseMarkdown,
    },
    graph_topology: [{ id: "review", src: "phases/review/SKILL.md", depends_on: [], mode: "skill" }],
  } as unknown as SkillDetail
}

function selectedAgentNode(): { id: string; data: SkillGraphNodeData } {
  return {
    id: "review",
    data: {
      skillId: "demo",
      label: "review",
      mode: "llm",
      status: "idle",
      dependsOn: [],
      filePath: "phases/review/SKILL.md",
    },
  }
}

describe("PropertiesPanel autosave", () => {
  beforeEach(async () => {
    vi.useFakeTimers()
    await mutate("llm/roles", undefined, { revalidate: false })
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
    apiMocks.getCompareCandidates.mockResolvedValue({ nodes: {} })
    apiMocks.getNodeLlmParams.mockResolvedValue({ nodes: {} })
    apiMocks.putNodeCompareCandidates.mockResolvedValue({ candidates: [] })
    apiMocks.putNodeLlmParams.mockResolvedValue({ enabled: false, thinking: null, max_output_tokens: null, temperature: null })
    toastMocks.error.mockReset()
    toastMocks.success.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    document.body.innerHTML = ""
    vi.clearAllMocks()
  })

  it("writes GRAPH.md frontmatter after graph property edits without clicking Save", async () => {
    const onPhaseFileSave = vi.fn<PhaseFileSaveHandler>(async () => undefined)
    const { container, root } = renderJsx(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={graphSkillDetail([
          "---",
          'schema_version: "v0.3.0"',
          "name: demo",
          "phases: []",
          "---",
          "<phase id=\"draft\" />",
        ].join("\n"))}
        selectedNode={null}
        onPhaseFileSave={onPhaseFileSave}
      />,
    )

    await settleEffects()
    setInputValue(container.querySelector("#graph-name") as HTMLInputElement, "demo_next")
    await flushAutosave()

    expect(onPhaseFileSave).toHaveBeenCalledTimes(1)
    expect(onPhaseFileSave).toHaveBeenCalledWith(expect.objectContaining({
      path: "GRAPH.md",
      content: expect.stringContaining("name: demo_next"),
    }))
    expect(onPhaseFileSave.mock.calls[0]?.[0].content).toContain('<phase id="draft" />')
    expect(container.innerHTML).not.toContain(">Save<")
    expect(container.querySelector('[data-save-status="saved"]')).not.toBeNull()

    act(() => {
      root.render(
        <PropertiesPanel
          skillId="demo-2"
          workspaceRoot="/skills/demo-2"
          skillDetail={graphSkillDetail([
            "---",
            'schema_version: "v0.3.0"',
            "name: demo-2",
            "phases: []",
            "---",
            "<phase id=\"draft\" />",
          ].join("\n"))}
          selectedNode={null}
          onPhaseFileSave={onPhaseFileSave}
        />,
      )
    })
    await settleEffects()

    expect(container.querySelector('[data-save-status-badge="true"]')).toBeNull()

    act(() => root.unmount())
  })

  it("writes the selected phase markdown after phase property edits without clicking Save", async () => {
    const onPhaseFileSave = vi.fn<PhaseFileSaveHandler>(async () => undefined)
    const { container, root } = renderJsx(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={phaseSkillDetail([
          "---",
          "name: review",
          "llm_role: analyst",
          "---",
          "<role>Reviewer</role>",
        ].join("\n"))}
        selectedNode={selectedAgentNode()}
        onPhaseFileSave={onPhaseFileSave}
      />,
    )

    await settleEffects()
    setInputValue(container.querySelector("#phase-max-iterations") as HTMLInputElement, "7")
    await flushAutosave()

    expect(onPhaseFileSave).toHaveBeenCalledTimes(1)
    expect(onPhaseFileSave).toHaveBeenCalledWith(expect.objectContaining({
      path: "phases/review/SKILL.md",
      content: expect.stringContaining("max_iterations: 7"),
    }))
    expect(onPhaseFileSave.mock.calls[0]?.[0].content).toContain("<role>Reviewer</role>")
    expect(container.innerHTML).not.toContain(">Save<")

    act(() => root.unmount())
  })

  it("shows node temperature overrides as percentages", async () => {
    apiMocks.getNodeLlmParams.mockResolvedValue({
      nodes: {
        review: {
          enabled: true,
          thinking: null,
          max_output_tokens: null,
          temperature: 0.7,
        },
      },
    })

    const { container, root } = renderJsx(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={phaseSkillDetail([
          "---",
          "name: review",
          "llm_role: analyst",
          "---",
          "<role>Reviewer</role>",
        ].join("\n"))}
        selectedNode={selectedAgentNode()}
        onPhaseFileSave={vi.fn()}
      />,
    )

    await settleEffects()

    expect(container.querySelector("[data-llm-node-temperature]")).not.toBeNull()
    expect(container.innerHTML).toContain(">35%<")
    expect(container.innerHTML).not.toContain(">0.7<")

    act(() => root.unmount())
  })

  it("autosaves the node custom model params switch", async () => {
    const { container, root } = renderJsx(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={phaseSkillDetail([
          "---",
          "name: review",
          "llm_role: analyst",
          "---",
          "<role>Reviewer</role>",
        ].join("\n"))}
        selectedNode={selectedAgentNode()}
        onPhaseFileSave={vi.fn()}
      />,
    )

    await settleEffects()
    const toggle = container.querySelector("[data-llm-node-params-enabled]") as HTMLButtonElement
    expect(toggle).not.toBeNull()

    act(() => {
      toggle.click()
    })
    await flushAutosave()

    expect(apiMocks.putNodeLlmParams).toHaveBeenCalledWith("demo", "review", {
      enabled: true,
      thinking: null,
      max_output_tokens: null,
      temperature: null,
    })
    expect(container.querySelector('[data-llm-node-params-save-status]')).toBeNull()
    expect(container.querySelector('[data-studio-panel-header="true"] [data-save-status="saved"]')).not.toBeNull()
    expect(container.querySelectorAll('[data-save-status-badge="true"]')).toHaveLength(1)

    act(() => root.unmount())
  })

  it("keeps the newest node params save queued while an older save is still in flight", async () => {
    const first = deferred<{ enabled: true; thinking: null; max_output_tokens: null; temperature: null }>()
    const second = deferred<{ enabled: true; thinking: null; max_output_tokens: number; temperature: null }>()
    apiMocks.putNodeLlmParams
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const { container, root } = renderJsx(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={phaseSkillDetail([
          "---",
          "name: review",
          "llm_role: analyst",
          "---",
          "<role>Reviewer</role>",
        ].join("\n"))}
        selectedNode={selectedAgentNode()}
        onPhaseFileSave={vi.fn()}
      />,
    )

    await settleEffects()
    act(() => {
      ;(container.querySelector("[data-llm-node-params-enabled]") as HTMLButtonElement).click()
    })
    await flushAutosave()
    expect(apiMocks.putNodeLlmParams).toHaveBeenCalledTimes(1)

    setInputValue(container.querySelector("#node-max-output-review") as HTMLInputElement, "2048")
    await flushAutosave()
    expect(container.querySelector('[data-studio-panel-header="true"] [data-save-status="pending"]')).not.toBeNull()

    await act(async () => {
      first.resolve({ enabled: true, thinking: null, max_output_tokens: null, temperature: null })
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(apiMocks.putNodeLlmParams).toHaveBeenCalledTimes(2)
    expect(container.querySelector('[data-studio-panel-header="true"] [data-save-status="saved"]')).toBeNull()
    expect(apiMocks.putNodeLlmParams.mock.calls[1]?.[2]).toEqual({
      enabled: true,
      thinking: null,
      max_output_tokens: 2048,
      temperature: null,
    })

    await act(async () => {
      second.resolve({ enabled: true, thinking: null, max_output_tokens: 2048, temperature: null })
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(container.querySelector('[data-studio-panel-header="true"] [data-save-status="saved"]')).not.toBeNull()

    act(() => root.unmount())
  })

  it("renders custom model params as a title-row checkbox and shows inherited fallback values while disabled", async () => {
    await mutate("llm/roles", rolesWithAnalystFallback(), { revalidate: false })

    const { container, root } = renderJsx(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={phaseSkillDetail([
          "---",
          "name: review",
          "llm_role: analyst",
          "---",
          "<role>Reviewer</role>",
        ].join("\n"))}
        selectedNode={selectedAgentNode()}
        onPhaseFileSave={vi.fn()}
      />,
    )

    await settleEffects()

    const paramsHeader = container.querySelector('[data-llm-node-params-header="true"]')
    expect(paramsHeader?.textContent).toContain("Custom model params")
    const customCheckbox = paramsHeader?.querySelector("[data-llm-node-params-enabled]")
    expect(customCheckbox).not.toBeNull()
    expect(container.querySelector('[data-llm-node-params-body="true"] [data-llm-node-params-enabled]')).toBeNull()

    expect((container.querySelector("#node-max-output-review") as HTMLInputElement).value).toBe("1,234")
    expect(container.innerHTML).toContain(">35%<")
    expect(container.querySelector("[data-llm-node-thinking]")?.getAttribute("aria-checked")).toBe("true")
    expect(container.querySelector("[data-llm-node-thinking]")?.hasAttribute("disabled")).toBe(true)

    act(() => root.unmount())
  })

  it("clears local node custom params when the switch is disabled", async () => {
    apiMocks.getNodeLlmParams.mockResolvedValue({
      nodes: {
        review: {
          enabled: true,
          thinking: true,
          max_output_tokens: 2048,
          temperature: 0.7,
        },
      },
    })

    const { container, root } = renderJsx(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={phaseSkillDetail([
          "---",
          "name: review",
          "llm_role: analyst",
          "---",
          "<role>Reviewer</role>",
        ].join("\n"))}
        selectedNode={selectedAgentNode()}
        onPhaseFileSave={vi.fn()}
      />,
    )

    await settleEffects()
    expect(container.innerHTML).toContain(">35%<")
    expect((container.querySelector("#node-max-output-review") as HTMLInputElement).value).toBe("2,048")

    const toggle = container.querySelector("[data-llm-node-params-enabled]") as HTMLButtonElement
    act(() => {
      toggle.click()
    })
    await flushAutosave()

    expect(apiMocks.putNodeLlmParams).toHaveBeenCalledWith("demo", "review", {
      enabled: false,
      thinking: null,
      max_output_tokens: null,
      temperature: null,
    })
    expect((container.querySelector("#node-max-output-review") as HTMLInputElement).value).toBe("")
    expect(container.innerHTML).not.toContain(">35%<")

    act(() => root.unmount())
  })

  it("re-applies phase property edits to the current markdown after a hash conflict", async () => {
    const remoteContent = [
      "---",
      "name: review",
      "description: edited elsewhere",
      "llm_role: reviewer",
      "max_iterations: 4",
      "---",
      "<role>Remote body</role>",
    ].join("\n")
    const onPhaseFileSave = vi.fn<PhaseFileSaveHandler>()
    onPhaseFileSave
      .mockRejectedValueOnce({
        type: "HashConflict",
        data: {
          current_hash: "remote-hash",
          current_content: remoteContent,
        },
      })
      .mockResolvedValueOnce(undefined)

    const { container, root } = renderJsx(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={phaseSkillDetail([
          "---",
          "name: review",
          "llm_role: analyst",
          "max_iterations: 3",
          "---",
          "<role>Reviewer</role>",
        ].join("\n"))}
        selectedNode={selectedAgentNode()}
        onPhaseFileSave={onPhaseFileSave}
      />,
    )

    await settleEffects()
    setInputValue(container.querySelector("#phase-max-iterations") as HTMLInputElement, "7")
    await flushAutosave()

    expect(onPhaseFileSave).toHaveBeenCalledTimes(2)
    expect(onPhaseFileSave.mock.calls[1]?.[0]).toEqual(expect.objectContaining({
      path: "phases/review/SKILL.md",
      expectedHash: "remote-hash",
      content: expect.stringContaining("max_iterations: 7"),
    }))
    expect(onPhaseFileSave.mock.calls[1]?.[0].content).toContain("description: edited elsewhere")
    expect(onPhaseFileSave.mock.calls[1]?.[0].content).toContain("<role>Remote body</role>")
    expect(toastMocks.error).not.toHaveBeenCalled()
    expect(container.querySelector('[data-save-status="saved"]')).not.toBeNull()

    act(() => root.unmount())
  })
})
