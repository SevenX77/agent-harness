import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  manualModelAccordionValue,
  manualModelCandidateErrorMessage,
  ManualModelTestPanel,
  mergeModelLists,
  modelIdPlaceholder,
} from "./ManualModelTestPanel"

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
})
