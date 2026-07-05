// @vitest-environment jsdom

import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { renderToStaticMarkup } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ProviderModelTestResponse } from "../../../api/llm"
import {
  ManualModelResultList,
  manualModelAccordionValue,
  manualModelCandidateErrorMessage,
  manualModelResultReasonCode,
  manualModelResultUiState,
  manualModelStatusLabel,
  manualModelToastSummary,
  ManualModelTestPanel,
  modelIdPlaceholder,
} from "./ManualModelTestPanel"
import { mergeModelLists } from "./model-probe-runner"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const llmMocks = vi.hoisted(() => ({
  getNotableModels: vi.fn(async () => ({ notable_models: [] })),
  testProviderModels: vi.fn(),
}))

const toastMock = vi.hoisted(() => ({
  error: vi.fn(),
  loading: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}))

vi.mock("../../../api/llm", async () => {
  const actual = await vi.importActual<typeof import("../../../api/llm")>("../../../api/llm")
  return {
    ...actual,
    getNotableModels: llmMocks.getNotableModels,
    testProviderModels: llmMocks.testProviderModels,
  }
})

vi.mock("sonner", () => ({
  toast: toastMock,
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

describe("ManualModelTestPanel", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    llmMocks.getNotableModels.mockResolvedValue({ notable_models: [] })
    llmMocks.testProviderModels.mockReset()
    toastMock.error.mockReset()
    toastMock.loading.mockReset()
    toastMock.success.mockReset()
    toastMock.info.mockReset()
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it("renders collapsed by default using the Accordion component", () => {
    const html = renderToStaticMarkup(
      <ManualModelTestPanel
        providerKey="anthropic-official"
        notableProviderKey="anthropic"
        onModelsUpdated={vi.fn()}
      />,
    )

    expect(html).toContain('data-testid="manual-model-test-panel"')
    expect(html).toContain('data-slot="accordion"')
    expect(html).toContain('data-slot="accordion-trigger"')
    expect(html).toContain("Manual model probing")
    expect(html).not.toContain("Show manual probing")
    expect(html).not.toContain("Hide manual probing")
    expect(html).not.toContain("Add Model")
    expect(html).not.toContain("Test Models")
  })

  it("renders model rows and disabled test button when explicitly expanded", () => {
    const html = renderToStaticMarkup(
      <ManualModelTestPanel
        providerKey="anthropic-official"
        notableProviderKey="anthropic"
        onModelsUpdated={vi.fn()}
        defaultExpanded
      />,
    )

    expect(html).toContain('data-testid="manual-model-test-panel"')
    expect(html).toContain('data-slot="accordion-content"')
    expect(html).toContain("Manual model probing")
    expect(html).toContain("Add Model")
    expect(html).toContain("Test Models")
    expect(html).toContain('placeholder="e.g. claude-opus-4-7"')
    expect(html).toContain('autoCorrect="off"')
    expect(html).toContain('autoCapitalize="none"')
    expect(html).not.toContain("provider/model-id")
    expect(html).toContain("disabled")
  })

  it("keeps the Accordion controlled while collapsed so one click can close it", () => {
    expect(manualModelAccordionValue(false)).toBe("")
    expect(manualModelAccordionValue(true)).toBe("manual-model-probing")
  })

  it("only keeps vendor-prefixed placeholders for model gateway providers", () => {
    expect(modelIdPlaceholder("openai", ["openai/gpt-5"], 0)).toBe("e.g. gpt-5")
    expect(modelIdPlaceholder("openrouter", ["openai/gpt-5"], 0)).toBe("e.g. openai/gpt-5")
    expect(modelIdPlaceholder("wavespeed", ["anthropic/claude-opus-4"], 0)).toBe("e.g. anthropic/claude-opus-4")
    expect(modelIdPlaceholder("qiniu", [], 0)).toBe("e.g. deepseek-r1")
    expect(modelIdPlaceholder("openai", undefined, 0)).toBe("e.g. gpt-5")
  })

  // The fan-out/aggregation behaviour these two used to lock now lives in the
  // atomic-probe runner (model-probe-runner.test.ts: "keeps the best result per
  // model across endpoints" + "records a failure ... without aborting the rest").

  it("publishes active manual probe atoms by endpoint while each endpoint/model task is in flight", async () => {
    const modelId = "anthropic/claude-opus-4.7"
    const probeGate = deferred<ProviderModelTestResponse>()
    const onActiveAtoms = vi.fn()
    const onModelsUpdated = vi.fn()
    llmMocks.testProviderModels.mockImplementation(async (payload: { provider_id: string; model_ids: string[] }) => {
      expect(payload.model_ids).toEqual([modelId])
      return probeGate.promise
    })

    await act(async () => {
      root.render(
        <ManualModelTestPanel
          providerKey="wavespeed"
          endpointTargets={[
            { id: "wavespeed-openai", testable: true },
            { id: "wavespeed-google", testable: false },
          ]}
          notableProviderKey="wavespeed"
          onModelsUpdated={onModelsUpdated}
          onActiveProbeModelIdsByEndpointChange={onActiveAtoms}
          defaultExpanded
        />,
      )
    })

    const input = container.querySelector<HTMLInputElement>('input[aria-label="Manual model 1"]')
    expect(input).not.toBeNull()
    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set
      valueSetter?.call(input!, modelId)
      input!.dispatchEvent(new Event("input", { bubbles: true }))
      input!.dispatchEvent(new Event("change", { bubbles: true }))
    })

    const testButton = Array.from(container.querySelectorAll("button"))
      .find((button) => button.textContent?.trim() === "Test Models") as HTMLButtonElement | undefined
    expect(testButton).toBeDefined()
    expect(testButton!.disabled).toBe(false)

    await act(async () => {
      testButton!.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      await Promise.resolve()
    })

    expect(llmMocks.testProviderModels).toHaveBeenCalledTimes(1)
    expect(llmMocks.testProviderModels).toHaveBeenCalledWith({
      provider_id: "wavespeed-openai",
      model_ids: [modelId],
    })
    expect(onActiveAtoms).toHaveBeenCalledWith({ "wavespeed-openai": [modelId] })
    expect(onActiveAtoms).not.toHaveBeenCalledWith({ "wavespeed-google": [modelId] })

    await act(async () => {
      probeGate.resolve({
        results: [{ model_id: modelId, status: "ok", message: null }],
        available_models: [{ id: modelId, status: "verified", ui_state: "ready" }],
      })
      await probeGate.promise
      await Promise.resolve()
    })

    expect(onActiveAtoms).toHaveBeenLastCalledWith({})
    expect(onModelsUpdated).toHaveBeenCalledWith([{ id: modelId, status: "verified", ui_state: "ready" }])
  })

  it("can render collapsed when automatic model listing already returned models", () => {
    const html = renderToStaticMarkup(
      <ManualModelTestPanel
        providerKey="openrouter-custom"
        notableProviderKey="openrouter"
        onModelsUpdated={vi.fn()}
        defaultExpanded={false}
      />,
    )

    expect(html).toContain('data-testid="manual-model-test-panel"')
    expect(html).toContain("Manual model probing")
    expect(html).not.toContain("Show manual probing")
    expect(html).not.toContain("Add Model")
    expect(html).not.toContain("Test Models")
  })

  it("dedupes incoming model chips without overwriting existing metadata", () => {
    const merged = mergeModelLists(
      [{ id: "gpt-5", capabilities: { max_context_tokens: 128000 } }],
      [{ id: "gpt-5" }, { id: "claude-opus-4-7" }],
    )

    expect(merged).toEqual([
      { id: "gpt-5", capabilities: { max_context_tokens: 128000 } },
      { id: "claude-opus-4-7" },
    ])
  })

  it("translates notable model request failures", () => {
    expect(
      manualModelCandidateErrorMessage({
        message: "Request failed with status code 404",
        response: { status: 404, data: { detail: "Unknown provider: custom" } },
      }),
    ).toContain("resource or endpoint could not be found")
  })

  it("translates manual model test statuses into user-facing labels", () => {
    expect(manualModelStatusLabel("ok")).toBe("Available")
    expect(manualModelStatusLabel("invalid_model")).toBe("Model not found")
    expect(manualModelStatusLabel("invalid_key")).toBe("Invalid API key")
    expect(manualModelStatusLabel("rate_limited")).toBe("Rate limited")
    expect(manualModelStatusLabel("quota_exceeded")).toBe("Quota exceeded")
    expect(manualModelStatusLabel("network_error")).toBe("Network error")
    expect(manualModelStatusLabel("timeout")).toBe("Request timed out")
    expect(manualModelStatusLabel("error")).toBe("Test failed")
  })

  it("renders manual model results through the shared 6-state ProviderStateBadge (apikeys#27)", () => {
    const html = renderToStaticMarkup(
      <ManualModelResultList
        results={[
          { model_id: "gpt-5", status: "ok", latency_ms: 120 },
          { model_id: "claude-opus-4.7", status: "invalid_model", latency_ms: 354 },
        ]}
      />,
    )

    // Both rows keep their model id + human label, but the colored chip is now the
    // canonical 6-state badge (ready / failed), not the old 2-state success/destructive Badge.
    expect(html).toContain("gpt-5")
    expect(html).toContain("Available")
    expect(html).toContain('data-provider-state-label="ready"')
    expect(html).toContain("claude-opus-4.7")
    expect(html).toContain("Model not found")
    expect(html).toContain('data-provider-state-label="failed"')
    expect(html).not.toContain("invalid_model")
  })

  it("maps manual probe statuses to the 6-state ui_state and a badge reason code", () => {
    expect(manualModelResultUiState("ok")).toBe("ready")
    expect(manualModelResultUiState("invalid_model")).toBe("failed")
    expect(manualModelResultUiState("timeout")).toBe("failed")
    expect(manualModelResultReasonCode("invalid_model")).toBe("invalid_model")
    expect(manualModelResultReasonCode("invalid_key")).toBe("invalid_key")
    expect(manualModelResultReasonCode("rate_limited")).toBe("rate_limited")
    expect(manualModelResultReasonCode("quota_exceeded")).toBe("rate_limited")
    expect(manualModelResultReasonCode("timeout")).toBeNull()
  })

  it("renders an empty manual model test response as visible feedback", () => {
    const html = renderToStaticMarkup(<ManualModelResultList results={[]} />)

    expect(html).toContain("No model results were returned.")
  })

  it("summarizes manual model results for sonner toast feedback", () => {
    expect(manualModelToastSummary([])).toEqual({
      kind: "info",
      title: "No model results were returned.",
      description: undefined,
    })
    expect(
      manualModelToastSummary([
        { model_id: "gpt-5", status: "ok", latency_ms: 12 },
        { model_id: "missing-model", status: "invalid_model", latency_ms: 14 },
      ]),
    ).toEqual({
      kind: "error",
      title: "1 of 2 model tests failed.",
      description: "missing-model: Model not found",
    })
  })
})
