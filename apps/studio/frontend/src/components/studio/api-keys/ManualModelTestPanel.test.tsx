import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
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

describe("ManualModelTestPanel", () => {
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
