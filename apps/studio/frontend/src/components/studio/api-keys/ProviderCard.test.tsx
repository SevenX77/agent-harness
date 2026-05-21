import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { isValidElement, type ReactElement, type ReactNode } from "react"
import { toast } from "sonner"
import { ProviderCard, ProviderDeleteButton, apiKeyInputType, sortModelInfos } from "./ProviderCard"
import type { CredentialsState } from "../../../api/llm"
import type { ProviderDraft } from "../SettingsPage"

const toastMock = vi.hoisted(() => vi.fn())

vi.mock("sonner", () => ({
  toast: toastMock,
}))

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

function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") {
    return ""
  }
  if (typeof node === "string" || typeof node === "number") {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(textOf).join("")
  }
  if (isValidElement(node)) {
    return textOf((node as ReactElement<{ children?: ReactNode }>).props.children)
  }
  return ""
}

function findElement(
  node: ReactNode,
  predicate: (element: ReactElement<Record<string, unknown>>) => boolean,
): ReactElement<Record<string, unknown>> | null {
  if (!isValidElement(node)) {
    return null
  }

  const element = node as ReactElement<Record<string, unknown>>
  if (predicate(element)) {
    return element
  }

  const children = element.props.children as ReactNode
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findElement(child, predicate)
      if (match) return match
    }
    return null
  }
  return findElement(children, predicate)
}

describe("ProviderCard API key masking", () => {
  it("renders API key as a native password input by default", () => {
    const html = renderCardHtml()

    expect(html).toContain('type="password"')
    expect(html).toContain('value="sk-secret-123"')
    expect(html).not.toContain("mask-input")
    expect(html).toContain('name="provider-secret-p1"')
    expect(html).toContain('data-1p-ignore=""')
    expect(html).toContain('data-lpignore="true"')
    expect(html).toContain('data-form-type="other"')
    expect(html).toContain('autoCorrect="off"')
    expect(html).toContain('autoCapitalize="none"')
    expect(html).toContain('aria-label="Show API key"')
    expect(html).toContain("transition-none")
    expect(html).toContain("px-6")
  })

  it("visibility toggle changes only input type and does not mutate draft api key", () => {
    const onFieldChange = vi.fn()
    const hiddenInputType = apiKeyInputType(false)
    const visibleInputType = apiKeyInputType(true)

    expect(hiddenInputType).toBe("password")
    expect(visibleInputType).toBe("text")
    expect(onFieldChange).not.toHaveBeenCalled()
    expect(draft.api_key).toBe("sk-secret-123")
  })
})

describe("ProviderCard test status badge", () => {
  it("renders Untested as secondary badge", () => {
    const html = renderCardHtml()

    expect(html).toContain('data-variant="secondary"')
    expect(html).toContain("Untested")
  })

  it("renders Testing badge with spinner", () => {
    const html = renderCardHtml({ nextDraft: makeDraft({ isTesting: true }) })

    expect(html).toContain("Testing...")
    expect(html).toContain("animate-spin")
  })

  it("renders Connected badge with emerald utility color", () => {
    const html = renderCardHtml({ persisted: makePersisted({ last_test_status: "ok" }) })

    expect(html).toContain("Connected")
    expect(html).toContain("text-emerald-500")
    expect(html).toContain("border-emerald-500/50")
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
        persisted={makePersisted({ last_test_status: "untested" })}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("Untested")
    expect(html).not.toContain("Not configured")
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
  it("does not render SDK protocol selection UI", () => {
    const html = renderCardHtml()
    const protocolLabel = ["SDK", " Protocol"].join("")
    const openAiLabel = ["OpenAI", " Compatible"].join("")

    expect(html).not.toContain(protocolLabel)
    expect(html).not.toContain(openAiLabel)
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
  it("delete trigger uses a sonner toast action instead of AlertDialog", () => {
    const onDelete = vi.fn()
    const element = ProviderDeleteButton({ draftName: "OpenAI", onDelete })
    const trigger = findElement(element, (candidate) => candidate.props["aria-label"] === "Delete provider")

    expect(textOf(element)).not.toContain("Confirm")
    expect(textOf(element)).not.toContain("Delete OpenAI?")
    expect(trigger?.props.onClick).toBeTypeOf("function")
    ;(trigger!.props.onClick as () => void)()

    expect(toast).toHaveBeenCalledWith(
      "Delete OpenAI?",
      expect.objectContaining({
        description: "This provider configuration will be removed from the credentials document.",
        action: expect.objectContaining({ label: "Delete" }),
        cancel: expect.objectContaining({ label: "Cancel" }),
        classNames: expect.objectContaining({
          actionButton: "!bg-destructive !text-destructive-foreground hover:!bg-destructive/90",
        }),
      }),
    )
    expect(onDelete).not.toHaveBeenCalled()
  })

  it("toast delete action is wired to call onDelete", () => {
    const onDelete = vi.fn()
    ProviderDeleteButton({ draftName: "OpenAI", onDelete }).props.onClick?.()
    const options = vi.mocked(toast).mock.calls.at(-1)?.[1] as {
      action?: { onClick?: () => void }
    }

    options.action?.onClick?.()
    expect(onDelete).toHaveBeenCalledTimes(1)
  })
})
