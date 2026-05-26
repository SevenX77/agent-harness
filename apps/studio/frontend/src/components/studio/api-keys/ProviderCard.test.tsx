import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { ReactElement } from "react"
import { ProviderCard, ProviderDeleteButton, apiKeyInputClassName, apiKeyInputType, sortModelInfos } from "./ProviderCard"
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog"
import type { CredentialsState, TestStatus } from "../../../api/llm"
import { providerTestParamsFingerprint } from "../settings/provider-utils"
import type { ProviderDraft } from "../settings/types"

const draft: ProviderDraft = {
  id: "p1",
  name: "OpenAI",
  api_key: "sk-secret-123",
  base_url: "",
  provider_type: "openai_compatible",
  isTesting: false,
}

function makeDraft(overrides: Partial<ProviderDraft> = {}): ProviderDraft {
  return { ...draft, ...overrides }
}

function makePersisted(
  overrides: Partial<CredentialsState["providers"][number]> = {},
): CredentialsState["providers"][number] {
  return {
    id: "p1",
    name: "OpenAI",
    api_key: "sk-secret-123",
    base_url: "",
    provider_type: "openai_compatible",
    ...overrides,
  }
}

function renderCardHtml({
  nextDraft = draft,
  persisted = null,
  showManualModelPanel = false,
}: {
  nextDraft?: ProviderDraft
  persisted?: CredentialsState["providers"][number] | null
  showManualModelPanel?: boolean
} = {}): string {
  return renderToStaticMarkup(
    <ProviderCard
      draft={nextDraft}
      persisted={persisted}
      onFieldChange={vi.fn()}
      onTest={vi.fn()}
      onDelete={vi.fn()}
      showManualModelPanel={showManualModelPanel}
    />,
  )
}

describe("ProviderCard API key masking", () => {
  it("renders API key as editable masked text by default", () => {
    const html = renderCardHtml()

    expect(html).toContain('type="text"')
    expect(html).toContain('value="sk-secret-123"')
    expect(html).toContain("mask-input")
    expect(html).toContain('name="provider-secret-p1"')
    expect(html).toContain('data-1p-ignore=""')
    expect(html).toContain('data-lpignore="true"')
    expect(html).toContain('data-form-type="other"')
    expect(html).toContain('autoCorrect="off"')
    expect(html).toContain('autoCapitalize="none"')
    expect(html).toContain('aria-label="Show API key"')
    expect(html).toContain('aria-label="Copy API key"')
    expect(html).toContain("transition-none")
    expect(html).toContain("text-muted-foreground")
    expect(html).toContain("px-6")
  })

  it("uses the shadcn InputGroup wrapper for API key inline actions", () => {
    const html = renderCardHtml()

    expect(html).toContain('data-slot="input-group"')
    expect(html).toContain('data-slot="input-group-control"')
    expect(html).toContain('data-slot="input-group-addon"')
    expect(html).toContain('data-size="icon-xs"')
  })

  it("visibility toggle changes only mask class and does not mutate draft api key", () => {
    const onFieldChange = vi.fn()
    const hiddenInputType = apiKeyInputType(false)
    const visibleInputType = apiKeyInputType(true)

    expect(hiddenInputType).toBe("text")
    expect(visibleInputType).toBe("text")
    expect(onFieldChange).not.toHaveBeenCalled()
    expect(draft.api_key).toBe("sk-secret-123")
  })

  it("uses CSS masking only while the API key is hidden", () => {
    expect(apiKeyInputClassName(false)).toContain("text-muted-foreground")
    expect(apiKeyInputClassName(false)).toContain("mask-input")
    expect(apiKeyInputClassName(false)).not.toContain("text-foreground")
    expect(apiKeyInputClassName(true)).toContain("text-foreground")
    expect(apiKeyInputClassName(true)).not.toContain("mask-input")
    expect(apiKeyInputClassName(true)).not.toContain("text-muted-foreground")
  })
})

describe("ProviderCard test status badge", () => {
  it("renders Not configured for untested provider state", () => {
    const html = renderCardHtml()

    expect(html).toContain('data-variant="secondary"')
    expect(html).toContain("Not configured")
    expect(html).not.toContain("Untested")
  })

  it("renders Testing badge with spinner", () => {
    const html = renderCardHtml({ nextDraft: makeDraft({ isTesting: true }) })

    expect(html).toContain("Testing...")
    expect(html).toContain("animate-spin")
  })

  it("renders Connected badge through semantic success tokens", () => {
    const html = renderCardHtml({ persisted: makePersisted({ last_test_status: "ok" }) })
    const connectedIndex = html.indexOf("Connected")
    const badgeStart = html.lastIndexOf("<span", connectedIndex)
    const badgeEnd = html.indexOf("</span>", connectedIndex)
    const badgeHtml = html.slice(badgeStart, badgeEnd)

    expect(html).toContain("Connected")
    expect(badgeHtml).toContain('data-variant="success"')
    expect(badgeHtml).toContain("bg-success-background")
    expect(badgeHtml).toContain("text-success-foreground")
    expect(badgeHtml).toContain("border-success-border")
    expect(badgeHtml).not.toContain("text-primary")
    expect(badgeHtml).not.toContain("border-primary")
  })

  it.each([
    ["untested", "Not configured"],
    ["ok", "Connected"],
    ["invalid_key", "Invalid API key"],
    ["rate_limited", "Rate limited"],
    ["quota_exceeded", "Quota exhausted"],
    ["network_error", "Network error"],
    ["timeout", "Request timed out"],
    ["error", "Test failed"],
  ] satisfies Array<[TestStatus, string]>)(
    "maps backend TestStatus %s to %s",
    (status, label) => {
      const html = renderCardHtml({
        persisted: makePersisted({ last_test_status: status }),
      })

      expect(html).toContain(label)
    },
  )

  it("resets persisted test state when editable provider fields diverge from stored values", () => {
    const html = renderCardHtml({
      nextDraft: makeDraft({ api_key: "sk-edited" }),
      persisted: makePersisted({
        last_test_status: "network_error",
        available_sdks: ["openai_compatible"],
        available_models: [{ id: "openai/gpt-5" }],
      }),
    })

    expect(html).toContain("Not configured")
    expect(html).not.toContain("Network error")
    expect(html).not.toContain("Available SDKs:")
    expect(html).not.toContain("Available Models:")
  })

  it("keeps persisted test state when only the provider display name changes", () => {
    const html = renderCardHtml({
      nextDraft: makeDraft({ name: "OpenAI renamed" }),
      persisted: makePersisted({
        last_test_status: "ok",
        available_sdks: ["openai_compatible"],
        available_models: [{ id: "openai/gpt-5" }],
      }),
    })

    expect(html).toContain("Connected")
    expect(html).toContain("Available SDKs:")
    expect(html).toContain("openai_compatible")
    expect(html).toContain("Available Models:")
    expect(html).toContain("openai/gpt-5")
  })

  it("restores cached test state when draft parameters match a previous result", () => {
    const cachedParams = makeDraft({ base_url: "https://api.original.test" })
    const html = renderCardHtml({
      nextDraft: cachedParams,
      persisted: makePersisted({
        base_url: "https://api.changed.test",
        last_test_status: "untested",
        available_sdks: [],
        available_models: [],
        test_results: [
          {
            params_fingerprint: providerTestParamsFingerprint(cachedParams),
            base_url: "https://api.original.test",
            provider_type: "openai_compatible",
            last_test_status: "ok",
            last_test_at: "2026-05-18T12:00:00+00:00",
            last_test_message: "",
            last_error_code: "",
            available_sdks: ["openai_compatible"],
            available_models: [{ id: "openai/gpt-5" }],
          },
        ],
      }),
    })

    expect(html).toContain("Connected")
    expect(html).toContain("Available SDKs:")
    expect(html).toContain("openai_compatible")
    expect(html).toContain("openai/gpt-5")
  })

  it("renders Error badge as destructive with error code", () => {
    const html = renderCardHtml({
      persisted: makePersisted({ last_test_status: "error", last_error_code: "auth_failed" }),
    })

    expect(html).toContain('data-variant="destructive"')
    expect(html).toContain("Test failed")
    expect(html).not.toContain(">auth_failed<")
  })

  it("renders persisted error status as a human-readable badge", () => {
    const html = renderCardHtml({
      persisted: makePersisted({ last_test_status: "invalid_key", last_error_code: "invalid_api_key" }),
    })

    expect(html).toContain("Invalid API key")
    expect(html).toContain("API key is invalid")
  })
})

describe("ProviderCard provider kind badge", () => {
  it("does not duplicate the Official label when providerKind is official", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ api_key: "" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("OpenAI")
    expect(html).not.toContain('data-variant="outline">Official</span>')
    expect(html).toContain("Not configured")
    expect(html).not.toContain('aria-label="Provider Name"')
    expect(html).not.toContain('aria-label="Delete provider"')
    expect(html).not.toContain("Base URL")
  })

  it("renders Third-party badge when providerKind is third-party", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={draft}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).toContain("Third-party")
    expect(html).toContain('aria-label="Provider Name"')
    expect(html).toContain('id="provider-name-p1"')
    expect(html).toContain(">Provider Name</label>")
    expect(html).toContain('aria-label="Delete provider"')
    expect(html).toContain("Base URL")
    expect(html).toContain('aria-label="Copy Base URL"')
  })

  it("uses the same not-configured test state for third-party providers without an API key", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ api_key: "" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).toContain("Not configured")
    expect(html).not.toContain("Untested")
  })

  it("renders an enabled official test action after API key is configured", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ api_key: "sk-official" })}
        persisted={makePersisted({ api_key: "sk-official", last_test_status: "untested" })}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("Not configured")
    expect(html).not.toContain("Untested")
  })
})

describe("ProviderCard provider capabilities", () => {
  it("renders available_sdks chips when persisted has data", () => {
    const html = renderCardHtml({
      persisted: makePersisted({ available_sdks: ["openai_compatible", "anthropic_compatible"] }),
    })

    expect(html).toContain('data-testid="provider-capabilities"')
    expect(html).toContain("Available SDKs:")
    expect(html).toContain("openai_compatible")
    expect(html).toContain("anthropic_compatible")
    expect(html).toContain("text-muted-foreground")
    expect(html).toContain('data-variant="outline"')
    expect(html).not.toContain('data-variant="secondary">openai_compatible')
  })

  it("renders available_models chips when persisted has data", () => {
    const html = renderCardHtml({
      persisted: makePersisted({
        available_models: [
          { id: "gpt-5", capabilities: { max_context_tokens: 128000 } },
          { id: "gpt-4o", capabilities: { modalities: ["text", "image"] } },
          { id: "claude-opus-4", capabilities: { vendor: "anthropic" } },
        ],
      }),
    })

    expect(html).toContain('data-testid="provider-capabilities"')
    expect(html).toContain("Available Models:")
    expect(html).toContain("gpt-5")
    expect(html).toContain("claude-opus-4")
    expect(html).toContain("text-muted-foreground")
  })

  it("collapses long available model lists behind a show-all action", () => {
    const models = Array.from({ length: 14 }, (_, index) => ({ id: `provider/model-${index + 1}` }))
    const html = renderCardHtml({
      persisted: makePersisted({ available_models: models }),
    })

    expect(html).toContain("provider/model-1")
    expect(html).toContain("provider/model-12")
    expect(html).not.toContain("provider/model-13")
    expect(html).toContain("Show 2 more")
    expect(html).toContain('data-variant="ghost"')
    expect(html).toContain("text-muted-foreground")
    expect(html).toContain('data-testid="available-models-list"')
    expect(html).toContain("max-h-[2.75rem]")
    expect(html).toContain("space-y-2 pb-1")
    const showMoreIndex = html.indexOf("Show 2 more")
    const showMoreStart = html.lastIndexOf("<button", showMoreIndex)
    const showMoreEnd = html.indexOf("</button>", showMoreIndex)
    const showMoreButton = html.slice(showMoreStart, showMoreEnd)
    expect(showMoreButton).not.toContain("text-primary")
  })

  it("sorts available model ids alphabetically before rendering", () => {
    const sorted = sortModelInfos([
      { id: "openai/gpt-5" },
      { id: "anthropic/claude-opus-4.7" },
      { id: "~anthropic/claude-haiku-latest" },
      { id: "google/gemini-3.5-flash" },
    ]).map((model) => model.id)

    expect(sorted).toEqual([
      "~anthropic/claude-haiku-latest",
      "anthropic/claude-opus-4.7",
      "google/gemini-3.5-flash",
      "openai/gpt-5",
    ])
  })

  it("does not render chip area when persisted has no sdks/models", () => {
    const html = renderCardHtml({
      persisted: makePersisted({ available_sdks: [], available_models: [] }),
    })

    expect(html).not.toContain('data-testid="provider-capabilities"')
    expect(html).not.toContain("Available SDKs:")
    expect(html).not.toContain("Available Models:")
  })
})

describe("ProviderCard protocol controls", () => {
  it("renders protocol selection for third-party providers", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ provider_type: "anthropic_compatible" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).toContain("Protocol")
    expect(html).toContain("Anthropic compatible")
    expect(html).toContain('data-slot="select-trigger"')
  })

  it("does not render protocol selection for official providers", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ provider_type: "anthropic_compatible" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).not.toContain("Protocol")
    expect(html).not.toContain("Anthropic compatible")
  })
})

describe("ProviderCard manual model panel", () => {
  it("renders fallback panel when requested", () => {
    const html = renderCardHtml({ showManualModelPanel: true })

    expect(html).toContain('data-testid="manual-model-test-panel"')
    expect(html).toContain('data-slot="accordion"')
    expect(html).toContain("Manual model probing")
    expect(html).not.toContain("Show manual probing")
    expect(html).not.toContain("Add Model")
    expect(html).not.toContain("Test Models")
  })

  it("hides fallback panel by default", () => {
    const html = renderCardHtml()

    expect(html).not.toContain('data-testid="manual-model-test-panel"')
  })

  it("collapses fallback controls when available model chips render", () => {
    const html = renderCardHtml({
      showManualModelPanel: true,
      persisted: makePersisted({ available_models: [{ id: "gpt-5" }] }),
    })

    expect(html).toContain("Available Models:")
    expect(html).toContain("gpt-5")
    expect(html).toContain('data-testid="manual-model-test-panel"')
    expect(html).toContain("Manual model probing")
    expect(html).not.toContain("Show manual probing")
    expect(html).not.toContain("Add Model")
    expect(html).not.toContain("Test Models")
  })
})

describe("ProviderCard delete confirmation", () => {
  it("delete trigger uses the shared confirmation dialog", () => {
    const onDelete = vi.fn()
    const element = ProviderDeleteButton({ draftName: "OpenAI", onDelete })
    const html = renderToStaticMarkup(<ProviderDeleteButton draftName="OpenAI" onDelete={onDelete} />)

    expect(element.type).toBe(DeleteConfirmDialog)
    expect(element.props.itemName).toBe("OpenAI")
    expect(element.props.description).toBe("This provider configuration will be removed from the credentials document.")
    expect(html).toContain('data-delete-confirm-trigger="true"')
  })

  it("delete trigger remains wired to the provider delete button", () => {
    const onDelete = vi.fn()
    const element = ProviderDeleteButton({ draftName: "OpenAI", onDelete })
    const trigger = element.props.trigger as ReactElement<Record<string, unknown>>

    expect(element.props.onConfirm).toBe(onDelete)
    expect(trigger.props["aria-label"]).toBe("Delete provider")
    expect(trigger.props["data-delete-confirm-trigger"]).toBe(true)
  })
})
