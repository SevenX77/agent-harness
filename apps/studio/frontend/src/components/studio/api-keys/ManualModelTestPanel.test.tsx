import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { ManualModelTestPanel, mergeModelLists } from "./ManualModelTestPanel"

describe("ManualModelTestPanel", () => {
  it("renders model rows and disabled test button before input", () => {
    const html = renderToStaticMarkup(
      <ManualModelTestPanel
        providerKey="anthropic-official"
        notableProviderKey="anthropic"
        onModelsUpdated={vi.fn()}
      />,
    )

    expect(html).toContain('data-testid="manual-model-test-panel"')
    expect(html).toContain("Manual model probing")
    expect(html).toContain("Add Model")
    expect(html).toContain("Test Models")
    expect(html).toContain('placeholder="model_id: claude-opus-4-7"')
    expect(html).not.toContain("provider/model-id")
    expect(html).toContain("disabled")
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
})
