import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  ProviderCard,
  ProviderDeleteButton,
  buildProviderDeleteRequest,
  aggregateThirdPartyModelInfos,
  apiKeyDisplayValue,
  apiKeyInputClassName,
  apiKeyInputType,
  copyAvailableModelId,
  endpointTagIsTestable,
  endpointTooltipLines,
  representativeProviderUiState,
  routeTooltipLineStatus,
  sortOfficialRouteInfos,
  sortModelInfos,
  sortThirdPartyModelInfos,
  verifiedSiblingProtocolsOnSameHost,
  type EndpointSummary,
} from "./ProviderCard"
import type { CredentialsState, ModelInfo, TestStatus } from "../../../api/llm"
import { providerTestParamsFingerprint } from "../settings/provider-utils"
import type { ProviderDraft } from "../settings/types"

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), {
  dismiss: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}))

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
  persistedEndpoints,
  showManualModelPanel = false,
}: {
  nextDraft?: ProviderDraft
  persisted?: CredentialsState["providers"][number] | null
  persistedEndpoints?: Record<string, CredentialsState["providers"][number] | null | undefined>
  showManualModelPanel?: boolean
} = {}): string {
  return renderToStaticMarkup(
    <ProviderCard
      draft={nextDraft}
      persisted={persisted}
      persistedEndpoints={persistedEndpoints}
      onFieldChange={vi.fn()}
      onGetModels={vi.fn()}
      onEndpointTest={vi.fn()}
      onDelete={vi.fn()}
      showManualModelPanel={showManualModelPanel}
    />,
  )
}

function routeTagHtml(html: string, modelId: string): string {
  const modelIndex = html.indexOf(modelId)
  return html.slice(html.lastIndexOf("<button", modelIndex), html.indexOf("</button>", modelIndex))
}

describe("ProviderCard API key masking", () => {
  it("renders a same-length mask value by default (never a native password field)", () => {
    const html = renderCardHtml()
    const maskedValue = apiKeyDisplayValue("sk-secret-123", false)

    // §1 contract: the secret field is ALWAYS type=text, so the browser /
    // extension password manager is never triggered. Hidden idle provider cards
    // render an explicit same-length mask value instead of relying on CSS
    // text-security; focusing the field enters readable edit mode.
    expect(html).toContain('type="text"')
    expect(html).not.toContain('type="password"')
    expect(maskedValue).toHaveLength("sk-secret-123".length)
    expect(maskedValue).not.toContain("sk")
    expect(html).toContain(`value="${maskedValue}"`)
    expect(html).not.toContain('value="sk-secret-123"')
    expect(html).not.toContain("mask-input")
    expect(html).toContain('name="provider-secret-p1"')
    expect(html).not.toContain('readOnly')
    expect(html).toContain('data-1p-ignore=""')
    expect(html).toContain('data-lpignore="true"')
    expect(html).toContain('data-form-type="other"')
    expect(html).toContain('autoCorrect="off"')
    expect(html).toContain('autoCapitalize="none"')
    expect(html).toContain('aria-label="Show API key"')
    expect(html).toContain('aria-label="Copy API key"')
    expect(html).toContain("transition-none")
    expect(html).toContain("text-muted-foreground")
    // apikeys#24/#25: the discover action is now a unified "Test" for both kinds.
    expect(html).not.toContain("Get Models")
    expect(html).not.toContain("Endpoint test")
    expect(html).toContain(">Test</button>")
  })

  it("returns the real API key when the field is visible or being edited", () => {
    expect(apiKeyDisplayValue("sk-secret-123", false)).toBe("\u2022".repeat("sk-secret-123".length))
    expect(apiKeyDisplayValue("sk-secret-123", true)).toBe("sk-secret-123")
    expect(apiKeyDisplayValue("sk-secret-123", false, true)).toBe("sk-secret-123")
    expect(apiKeyDisplayValue("", false)).toBe("")
  })

  it("keeps the input type=text in both hidden and visible states", () => {
    const onFieldChange = vi.fn()

    expect(apiKeyInputType()).toBe("text")
    expect(onFieldChange).not.toHaveBeenCalled()
    expect(draft.api_key).toBe("sk-secret-123")
  })

  it("masks via the mask-input class only while hidden; muted text only while hidden", () => {
    expect(apiKeyInputClassName(false, true)).toContain("mask-input")
    expect(apiKeyInputClassName(true, true)).not.toContain("mask-input")
    expect(apiKeyInputClassName(false, true)).toContain("text-muted-foreground")
    expect(apiKeyInputClassName(false, true)).not.toContain("text-foreground")
    expect(apiKeyInputClassName(true, true)).toContain("text-foreground")
    expect(apiKeyInputClassName(true, true)).not.toContain("text-muted-foreground")
  })

  it("never masks an empty field, so the placeholder stays readable (not •••)", () => {
    // -webkit-text-security masks placeholder text too; an empty official card
    // must keep "Enter your X API Key" legible instead of rendering it as dots.
    expect(apiKeyInputClassName(false, false)).not.toContain("mask-input")
    expect(apiKeyInputClassName(true, false)).not.toContain("mask-input")
  })

  it("does not mask the placeholder of an empty official provider card", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "anthropic-official", name: "Anthropic Official", api_key: "" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )
    // The only secret field on an empty official card has no value, so the
    // whole card must contain no mask-input at all (placeholder stays readable).
    expect(html).toContain('placeholder="Enter your Anthropic API Key"')
    expect(html).not.toContain("mask-input")
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
    expect(html).not.toContain("Available SDKs:")
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
    expect(html).not.toContain("Available SDKs:")
    expect(html).toContain("openai/gpt-5")
  })

  it("keeps available models visible after an endpoint test failure for the current config", () => {
    const html = renderCardHtml({
      nextDraft: makeDraft({ provider_type: "google_genai", base_url: "https://anthropic.qnaigc.com" }),
      persisted: makePersisted({
        provider_type: "google_genai",
        base_url: "https://anthropic.qnaigc.com",
        last_test_status: "error",
        last_error_code: "network_error",
        available_sdks: ["google_genai"],
        available_models: [{ id: "stale-model-from-prior-test" }],
        test_results: [],
      }),
    })

    expect(html).toContain("Test failed")
    expect(html).not.toContain("Available SDKs:")
    expect(html).toContain("Available Models:")
    expect(html).toContain("stale-model-from-prior-test")
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
    // The error-code detail moved from a native title into the badge's Radix
    // tooltip; the badge renders as the tooltip trigger.
    expect(html).toContain('data-slot="tooltip-trigger" data-variant="destructive"')
  })
})

describe("ProviderCard provider kind badge", () => {
  it("does not duplicate the Official label when providerKind is official", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ api_key: "" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("OpenAI Official")
    expect(html).not.toContain('data-variant="outline">Official</span>')
    expect(html).toContain("Available Endpoints:")
    expect(html).not.toContain('aria-label="More actions for OpenAI Official"')
    expect(html).not.toContain(">Base URL</label>")
  })

  it("normalizes official provider card titles from persisted endpoint ids", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "anthropic-official", name: "anthropic-official", provider_type: "anthropic_compatible" })}
        persisted={makePersisted({ id: "anthropic-official", name: "anthropic-official", last_test_status: "ok" })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
        notableProviderKey="anthropic"
      />,
    )

    const headerStart = html.indexOf('data-slot="card-header"')
    const headerEnd = html.indexOf('data-slot="card-content"')
    const headerHtml = html.slice(headerStart, headerEnd)

    expect(html).toContain("Anthropic Official")
    expect(headerHtml).not.toContain("anthropic-official")
    expect(headerHtml).not.toContain("Connected")
    expect(html).toContain("Available Endpoints:")
  })

  it("renders Third-party badge when providerKind is third-party", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={draft}
        persisted={null}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).toContain("Third-party")
    expect(html).toContain('aria-label="More actions for OpenAI"')
    expect(html).toContain("Base URL")
    expect(html).toContain('aria-label="Copy Base URL"')
  })

  it("uses the same not-configured test state for third-party providers without an API key", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ api_key: "" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
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
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).not.toContain("Not configured")
    expect(html).toContain("Available Endpoints:")
    expect(html).toContain("Untested")
  })
})

describe("ProviderCard model discovery and endpoint test controls", () => {
  it("renders official providers with one primary Test action and no manual endpoint row", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "ark-official", name: "Ark Official", provider_type: "ark_runtime" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const testIndex = html.indexOf(">Test</button>")
    const testButton = html.slice(html.lastIndexOf("<button", testIndex), html.indexOf("</button>", testIndex))
    expect(testIndex).toBeGreaterThan(-1)
    expect(testButton).toContain('data-variant="default"')
    expect(testButton).toContain("w-24")
    expect(testButton).toContain("justify-center")
    expect(testButton).not.toContain("min-w-[7rem]")
    expect(testButton).not.toContain('data-variant="secondary"')
    expect(html).not.toContain("Get Models")
    expect(html).not.toContain("Endpoint test")
    expect(html).not.toContain("Please choose one model from Available Models for endpoint testing.")
    expect(html).not.toContain('placeholder="e.g. doubao-seed-2-0-pro-260215"')
    expect(html).toContain(">Test</button>")
  })

  it("collapses third-party editable fields to API Key -> Base URL, with one Test and available endpoint details", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ base_url: "https://api.qnaigc.com/v1" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    const apiKeyIndex = html.indexOf(">API Key</label>")
    const baseUrlIndex = html.indexOf(">Base URL</label>")
    const availableEndpointIndex = html.indexOf("Available Endpoints:")
    expect(apiKeyIndex).toBeGreaterThan(-1)
    expect(baseUrlIndex).toBeGreaterThan(apiKeyIndex)
    expect(availableEndpointIndex).toBeGreaterThan(baseUrlIndex)
    // apikeys#20: protocol is backend-auto-detected now — no manual Protocol dropdown.
    expect(html).not.toContain(">Protocol</label>")
    expect(html).not.toContain(`provider-protocol-${draft.id}`)
    // apikeys#24/#25: the discover action is a unified "Test"; the old one-model
    // Endpoint test escape hatch no longer appears in the provider card.
    expect(html).not.toContain("Get Models")
    expect(html).not.toContain(">Endpoint test</label>")
    expect(html).not.toContain('title="Provider:')
    const testIndex = html.indexOf(">Test</button>")
    const testButton = html.slice(html.lastIndexOf("<button", testIndex), html.indexOf("</button>", testIndex))
    expect(testIndex).toBeGreaterThan(-1)
    expect(testButton).toContain('data-variant="default"')
    expect(testButton).toContain("w-24")
    expect(testButton).toContain("justify-center")
    expect(testButton).not.toContain("min-w-[7rem]")
    expect(testButton).not.toContain('data-variant="secondary"')
    expect(html).toContain("https://api.qnaigc.com/v1")
    expect(html).toContain("Protocol: OpenAI-compatible")
    expect(html).toContain("OpenAI / api.qnaigc")
    expect(html).not.toContain("OpenAI / api.qnaigc.com")
    expect(html).not.toContain("OpenAI / api.qnaigc Connected")
    expect(html).not.toContain("OpenAI / api.qnaigc Failed")
  })

  it("shows base URL reachability on each URL row instead of the shared label", () => {
    const nextDraft = makeDraft({
      base_url: "https://good.example/v1",
      base_urls: [
        {
          id: "url-good",
          value: "https://good.example/v1",
          provider_type: "openai_compatible",
          endpoint_ids: {
            openai_compatible: "good-openai",
            anthropic_compatible: "good-anthropic",
            google_genai: "good-google",
          },
        },
        {
          id: "url-bad",
          value: "https://bad.example/v1",
          provider_type: "openai_compatible",
          endpoint_ids: {
            openai_compatible: "bad-openai",
            anthropic_compatible: "bad-anthropic",
            google_genai: "bad-google",
          },
        },
      ],
    })

    const html = renderCardHtml({
      nextDraft,
      persistedEndpoints: {
        "good-openai": makePersisted({
          id: "good-openai",
          base_url: "https://good.example/v1",
          last_test_status: "ok",
          provider_type: "openai_compatible",
          available_models: [{ id: "good-model", status: "verified", ui_state: "ready" }],
        }),
        "good-anthropic": makePersisted({
          id: "good-anthropic",
          base_url: "https://good.example/v1",
          last_test_status: "error",
          provider_type: "anthropic_compatible",
        }),
        "bad-openai": makePersisted({
          id: "bad-openai",
          base_url: "https://bad.example/v1",
          last_test_status: "error",
          provider_type: "openai_compatible",
        }),
        "bad-anthropic": makePersisted({
          id: "bad-anthropic",
          base_url: "https://bad.example/v1",
          last_test_status: "timeout",
          provider_type: "anthropic_compatible",
        }),
      },
    })

    expect(html).toContain('data-base-url-status="connected"')
    expect(html).toContain('aria-label="https://good.example/v1 connected"')
    expect(html).toContain('data-base-url-status="failed"')
    expect(html).toContain('aria-label="https://bad.example/v1 failed"')
    expect(html).not.toContain("Base URL accepted by the model-list endpoint")
  })

  it("shows protocol-normalized runtime URL separately from the input URL", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ base_url: "https://api.qnaigc.com/v1" })}
        persisted={makePersisted({
          base_url: "https://api.qnaigc.com/v1",
          runtime_base_url: "https://api.qnaigc.com",
          provider_type: "anthropic_compatible",
          last_test_status: "error",
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).toContain("Input URL: https://api.qnaigc.com/v1")
    expect(html).toContain("Runtime URL: https://api.qnaigc.com")
    expect(html).toContain("Protocol: Anthropic-compatible")
  })

  it("summarizes official endpoint methods, request mappers, and tool protocol in Available Endpoints", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({
          id: "ark-official",
          name: "Ark Official",
          provider_type: "ark_runtime",
          base_url: "https://ark.cn-beijing.volces.com",
        })}
        persisted={makePersisted({
          id: "ark-official",
          name: "Ark Official",
          provider_type: "ark_runtime",
          base_url: "https://ark.cn-beijing.volces.com",
          last_test_status: "ok",
          available_models: [
            {
              id: "doubao-seed-1-6",
              status: "verified",
              verified_profiles: [
                {
                  profile_id: "text:ark_chat",
                  capability: "text_chat",
                  method_id: "ark_chat",
                  request_mapper_id: "ark_chat_text",
                  status: "ready",
                },
                {
                  profile_id: "text:ark_responses",
                  capability: "reasoning",
                  method_id: "ark_responses",
                  request_mapper_id: "ark_responses_text",
                  status: "ready",
                },
              ],
              capabilities: { tool_protocol: true },
            },
            {
              id: "claude-opus-4-1",
              status: "verified",
              verified_profiles: [
                {
                  profile_id: "tool:ark_anthropic_messages",
                  capability: "tool_calling",
                  method_id: "ark_anthropic_messages",
                  request_mapper_id: "ark_anthropic_tools",
                  status: "ready",
                },
              ],
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
        notableProviderKey="ark"
      />,
    )

    expect(html).toContain("Available Endpoints:")
    expect(html).toContain("3m")
    expect(html).toContain("Protocol: Ark runtime")
    expect(html).toContain("Profiles: 3")
    expect(html).toContain("Methods: ark_anthropic_messages, ark_chat, ark_responses")
    expect(html).toContain("Request mappers: ark_anthropic_tools, ark_chat_text, ark_responses_text")
    expect(html).toContain("Profile capabilities: reasoning, text chat, tool calling")
    expect(html).toContain("Tool protocol: supported")
  })

  it("shows models discovered for the current params without rendering Connected", () => {
    const html = renderCardHtml({
      persisted: makePersisted({
        last_test_status: "untested",
        available_sdks: ["openai_compatible"],
        available_models: [{ id: "listed-model" }],
        test_results: [
          {
            params_fingerprint: providerTestParamsFingerprint(draft),
            base_url: "",
            provider_type: "openai_compatible",
            last_test_status: "untested",
            available_sdks: ["openai_compatible"],
            available_models: [{ id: "listed-model" }],
          },
        ],
      }),
    })

    expect(html).toContain("Not configured")
    expect(html).not.toContain("Connected")
    expect(html).toContain("Available Models:")
    expect(html).toContain("listed-model")
  })
})

describe("ProviderCard provider capabilities", () => {
  it("does not render available_sdks chips when persisted has data", () => {
    const html = renderCardHtml({
      persisted: makePersisted({ available_sdks: ["openai_compatible", "anthropic_compatible"] }),
    })

    expect(html).toContain('data-testid="provider-capabilities"')
    expect(html).not.toContain("Available SDKs:")
    expect(html).not.toContain("openai_compatible")
    expect(html).not.toContain("anthropic_compatible")
    expect(html).toContain("No models returned")
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

  it("renders official provider route chips with probe status variants", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "openai-official", name: "OpenAI Official" })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          available_models: [
            {
              id: "gpt-5",
              route_id: "openai-official:gpt-5",
              status: "verified",
            },
            {
              id: "gpt-image-1",
              route_id: "openai-official:gpt-image-1",
              status: "failed",
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("Available Routes:")
    expect(html).not.toContain("Available Models:")

    const verifiedTag = routeTagHtml(html, "gpt-5")
    expect(verifiedTag).toContain('data-slot="tooltip-trigger"')
    expect(verifiedTag).toContain('data-variant="success"')
    expect(verifiedTag).toContain('data-route-status="verified"')

    const failedTag = routeTagHtml(html, "gpt-image-1")
    expect(failedTag).toContain('data-slot="tooltip-trigger"')
    expect(failedTag).toContain('data-variant="destructive"')
    expect(failedTag).toContain('data-route-status="failed"')
  })

  it("classifies inline failed and warning tooltip lines for diagnostic icons", () => {
    expect(routeTooltipLineStatus("gpt-broken - Route test failed: 401 Unauthorized.")).toBe("failed")
    expect(routeTooltipLineStatus("gpt-5 - Warning: Thinking was preferred.")).toBe("warning")
    expect(routeTooltipLineStatus("Input: text")).toBeNull()
  })

  it("keeps official backend route tags visible when the editable draft secret differs", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "openai-official", name: "OpenAI Official", api_key: "sk-edited" })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          api_key: "**********",
          available_models: [
            {
              id: "gpt-5",
              route_id: "openai-official:gpt-5",
              status: "verified",
              capabilities: { model_type: "language_reasoning" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("Available Routes:")
    expect(routeTagHtml(html, "gpt-5")).toContain('data-variant="success"')
  })

  it("animates only official route chips reported as actively testing", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({
          id: "openai-official",
          name: "OpenAI Official",
          isTesting: true,
          testingAction: "models",
        })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          available_models: [
            {
              id: "gpt-5.2",
              status: "testing",
              last_probe_message: null,
              capabilities: { model_type: "language_reasoning", model_type_label: "Language/reasoning model" },
            },
            {
              id: "gpt-5.3",
              status: "unverified_manual",
              last_probe_message: null,
              capabilities: { model_type: "language_reasoning", model_type_label: "Language/reasoning model" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const tag = routeTagHtml(html, "gpt-5.2")
    expect(tag).toContain('data-route-status="testing"')
    expect(tag).toContain("api-route-tag-border-flow")

    const idleTag = routeTagHtml(html, "gpt-5.3")
    expect(idleTag).toContain('data-route-status="unverified_manual"')
    expect(idleTag).toContain('data-variant="default"')
    expect(idleTag).not.toContain("api-route-tag-border-flow")
  })

  it("animates third-party model chips while the endpoint test runs (R-G2)", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({
          id: "qiniu",
          name: "Qiniu",
          base_url: "https://api.qnaigc.com/v1",
          isTesting: true,
          testingAction: "models",
        })}
        persisted={makePersisted({
          id: "qiniu",
          name: "Qiniu",
          base_url: "https://api.qnaigc.com/v1",
          available_models: [
            {
              id: "deepseek-v3",
              status: "unverified_manual",
              last_probe_message: null,
              capabilities: { model_type: "language_reasoning", model_type_label: "Language/reasoning model" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    // R-G2: while the endpoint test runs, a third-party model chip pulses even though
    // its own status is still "unverified_manual" — the whole endpoint is being verified.
    const tag = routeTagHtml(html, "deepseek-v3")
    expect(tag).toContain("api-route-tag-border-flow")
  })

  it("renders generated multimodal route candidates with a default border and shadcn-only tooltip", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "openai-official", name: "OpenAI Official" })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          available_models: [
            {
              id: "gpt-image-1",
              status: "unverified_manual",
              capabilities: { model_type: "image_generation", model_type_label: "Image generation model" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const tag = routeTagHtml(html, "gpt-image-1")
    expect(tag).toContain('data-variant="default"')
    expect(tag).toContain('data-model-type="image_generation"')
    expect(html).toContain('data-route-type-group="Multimodal"')
    expect(tag).toContain('data-input-modalities="text,image"')
    expect(tag).toContain('data-output-modalities="image"')
    expect(tag).toContain("lucide-file-text")
    expect(tag).toContain("lucide-image")
    expect(tag).not.toContain("title=")
    expect(tag).toContain("Image generation model")
    expect(html).toContain("Input: text, image")
    expect(html).toContain("Output: image")
    expect(html).toContain("Max input: not listed")
    expect(html).toContain("Max output: not listed")
    expect(html).not.toContain("Modalities are inferred from model type, not capability-probed.")
  })

  it("renders input and output modality icons on official route tags", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "openai-official", name: "OpenAI Official" })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          available_models: [
            {
              id: "gpt-image-1",
              status: "unverified_manual",
              capabilities: {
                model_type: "image_generation",
                model_type_label: "Image generation model",
                input_modalities: ["text", "image"],
                output_modalities: ["image"],
                input_modalities_source: "provider_doc",
                output_modalities_source: "provider_doc",
                input_modalities_source_urls: ["https://developers.openai.com/api/docs/guides/image-generation"],
                output_modalities_source_urls: ["https://developers.openai.com/api/docs/guides/image-generation"],
                max_input_tokens: 8192,
                max_input_tokens_source: "api_list",
                max_input_tokens_source_urls: ["https://api.openai.com/v1/models"],
                max_output_tokens: 128000,
                max_output_tokens_source: "provider_doc",
              },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const tag = routeTagHtml(html, "gpt-image-1")
    expect(tag).toContain('data-input-modalities="text,image"')
    expect(tag).toContain('data-output-modalities="image"')
    expect(tag).toContain("lucide-file-text")
    expect(tag).toContain("lucide-image")
    expect(html).toContain("Input: text, image")
    expect(html).toContain("Output: image")
    expect(html).toContain("Max input: 8k tokens")
    expect(html).toContain("Max output: 128k tokens")
    expect(html).not.toContain("provider model catalog")
    expect(html).not.toContain("Modalities are from provider documentation.")
    expect(html).not.toContain("Source URLs:")
    expect(html).not.toContain("https://developers.openai.com/api/docs/guides/image-generation")
    expect(html).not.toContain("https://api.openai.com/v1/models")
  })

  it("renders active verified routes as green even if they are multimodal/image models", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "gemini-official", name: "Gemini Official" })}
        persisted={makePersisted({
          id: "gemini-official",
          name: "Gemini Official",
          available_models: [
            {
              id: "gemini-3-pro-image",
              route_id: "gemini-official:gemini-3-pro-image",
              status: "verified",
              verified_profiles: [
                {
                  profile_id: "text:gemini_generate_content",
                  capability: "text_chat",
                  method_id: "gemini_generate_content",
                  request_mapper_id: "gemini_generate_content_text",
                  status: "ready",
                },
              ],
              capabilities: { model_type: "image_generation", model_type_label: "Image generation model" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const tag = routeTagHtml(html, "gemini-3-pro-image")
    expect(tag).toContain('data-variant="success"')
    expect(tag).not.toContain('data-variant="probe-verified"')
    expect(tag).toContain('data-model-type="image_generation"')
    expect(tag).toContain("Image generation model")
    expect(tag).not.toContain("Verified route")
  })

  it("renders historically probe-verified routes as blue (probe-verified variant) if not active in credentials", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "openai-official", name: "OpenAI Official" })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          available_models: [
            {
              id: "gpt-5-probe-verified",
              route_id: "openai-official:gpt-5-probe-verified",
              status: "probe-verified",
              capabilities: { model_type: "language_reasoning", model_type_label: "Language/reasoning model" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const tag = routeTagHtml(html, "gpt-5-probe-verified")
    expect(tag).toContain('data-variant="probe-verified"')
    expect(tag).toContain('data-route-status="probe-verified"')
  })

  it("renders a historical_ready route (backend 6-state ui_state) as the blue Previously Connected tag, not at the card title", () => {
    // Real backend data for a historically probe-verified route this session:
    // RouteStatus "unverified_manual" + ui_state "historical_ready". The blue
    // must come from ui_state on the ROUTE tag (UI-spec §143), and must NOT be
    // rolled up to a card-title badge (UI-spec §140).
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "openai-official", name: "OpenAI Official" })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          available_models: [
            {
              id: "gpt-5",
              route_id: "openai-official:gpt-5",
              status: "unverified_manual",
              ui_state: "historical_ready",
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const tag = routeTagHtml(html, "gpt-5")
    expect(tag).toContain('data-variant="probe-verified"')
    expect(tag).toContain('data-route-ui-state="historical_ready"')
    // §140: no connection-status badge in the official card title.
    expect(html).not.toContain('data-provider-state-label="historical_ready"')
  })

  it("describes verified route profile capability types instead of profile counts", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "openai-official", name: "OpenAI Official" })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          available_models: [
            {
              id: "gpt-5.2",
              route_id: "openai-official:gpt-5.2",
              status: "verified",
              verified_profile_count: 2,
              verified_profiles: [
                {
                  profile_id: "text:openai_responses",
                  capability: "text_chat",
                  method_id: "openai_responses",
                  request_mapper_id: "openai_responses_text",
                  status: "ready",
                },
                {
                  profile_id: "reasoning:openai_responses",
                  capability: "reasoning",
                  method_id: "openai_responses",
                  request_mapper_id: "openai_responses_reasoning",
                  status: "ready",
                },
              ],
              capabilities: { model_type: "language_reasoning", model_type_label: "Language/reasoning model" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const tag = routeTagHtml(html, "gpt-5.2")
    expect(tag).toContain("Verified text chat + reasoning route")
    expect(html).toContain("Methods: openai_responses")
    expect(html).not.toContain("profiles")
  })

  it("does not append generic model type text to verified route tooltips", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "gemini-official", name: "Gemini Official" })}
        persisted={makePersisted({
          id: "gemini-official",
          name: "Gemini Official",
          available_models: [
            {
              id: "gemini-3.1-flash-lite-preview",
              route_id: "gemini-official:gemini-3.1-flash-lite-preview",
              status: "verified",
              verified_profile_count: 2,
              verified_profiles: [
                {
                  profile_id: "text:gemini_generate_content",
                  capability: "text_chat",
                  method_id: "gemini_generate_content",
                  request_mapper_id: "gemini_generate_content_text",
                  status: "ready",
                },
                {
                  profile_id: "thinking:gemini_generate_content:low",
                  capability: "thinking",
                  method_id: "gemini_generate_content",
                  request_mapper_id: "gemini_generate_content_thinking_level_low",
                  status: "ready",
                },
              ],
              capabilities: { model_type: "language_reasoning", model_type_label: "Language/reasoning model" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("Verified text chat + reasoning route")
    expect(html).toContain("Methods: gemini_generate_content")
    expect(html).not.toContain("Language/reasoning model")
  })

  it("surfaces failed official route probe messages in the route tooltip", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "gemini-official", name: "Gemini Official" })}
        persisted={makePersisted({
          id: "gemini-official",
          name: "Gemini Official",
          available_models: [
            {
              id: "gemini-3-pro-preview",
              status: "failed",
              last_probe_message: "Provider returned HTTP 404 (NOT_FOUND). This model models/gemini-3-pro-preview is no longer available.",
              capabilities: { model_type: "language_reasoning", model_type_label: "Language/reasoning model" },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("Route test failed: Provider returned HTTP 404 (NOT_FOUND). This model models/gemini-3-pro-preview is no longer available.")
    const tag = routeTagHtml(html, "gemini-3-pro-preview")
    expect(tag).toContain('data-model-type="language_reasoning"')
    expect(tag).not.toContain("title=")
  })

  it("surfaces per-method official probe attempts in failed route tooltips", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "openai-official", name: "OpenAI Official" })}
        persisted={makePersisted({
          id: "openai-official",
          name: "OpenAI Official",
          available_models: [
            {
              id: "gpt-5.2-pro",
              status: "failed",
              last_probe_message: "No official language call method passed for this model.",
              capabilities: {
                model_type: "language_reasoning",
                model_type_label: "Language/reasoning model",
                probe_attempts: [
                  {
                    method_id: "openai_responses",
                    profile_id: "reasoning:openai_responses",
                    status: "invalid_model",
                    message: "Provider returned HTTP 400 (unsupported_value). Unsupported value: low.",
                  },
                ],
              },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("Attempts:")
    expect(html).toContain("openai_responses/reasoning:openai_responses")
    expect(html).toContain("Unsupported value: low.")
  })

  it("marks verified thinking routes with a compact brain icon", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ id: "gemini-official", name: "Gemini Official" })}
        persisted={makePersisted({
          id: "gemini-official",
          name: "Gemini Official",
          available_models: [
            {
              id: "gemini-3.1-pro-preview",
              route_id: "gemini-official:gemini-3.1-pro-preview",
              status: "verified",
              verified_profile_count: 2,
              capabilities: {
                model_type: "language_reasoning",
                model_type_label: "Language/reasoning model",
                verified_profiles: [
                  {
                    profile_id: "text:gemini_generate_content",
                    capability: "text_chat",
                    method_id: "gemini_generate_content",
                    request_mapper_id: "gemini_generate_content_text",
                    status: "ready",
                  },
                  {
                    profile_id: "thinking:gemini_generate_content:low",
                    capability: "thinking",
                    method_id: "gemini_generate_content",
                    request_mapper_id: "gemini_generate_content_thinking_level_low",
                    status: "ready",
                  },
                ],
              },
            },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    const tag = routeTagHtml(html, "gemini-3.1-pro-preview")
    expect(tag).toContain('data-reasoning-route="true"')
    expect(tag).toContain("lucide-brain")
    expect(tag).toContain("Verified text chat + reasoning route")
  })

  it("renders available models as clickable copy targets", () => {
    const html = renderCardHtml({
      persisted: makePersisted({
        available_models: [{ id: "deepseek/deepseek-v3.1-terminus" }],
      }),
    })

    expect(html).toContain('type="button"')
    expect(html).toContain('aria-label="Copy model deepseek/deepseek-v3.1-terminus. Route status unknown"')
    expect(html).toContain("cursor-pointer")
  })

  it("keeps endpoint-scoped third-party failures from marking the model failed", () => {
    const html = renderCardHtml({
      persisted: makePersisted({
        available_models: [{
          id: "deepseek/deepseek-v3.1-terminus-thinking",
          endpoint_id: "api-qnaigc-com-v1-openai-cd4c26a12b",
          route_id: "api-qnaigc-com-v1-openai-cd4c26a12b:deepseek.deepseek-v3.1-terminus-thinking",
          status: "failed",
          ui_state: "failed",
          last_probe_message: "Provider returned HTTP 502 (upstream_error). service temporarily unavailable.",
          capabilities: {
            reason_code: "error",
            probe_attempts: [{ status: "error", message: "Provider returned HTTP 502." }],
          },
        }],
      }),
    })

    expect(html).toContain('data-route-status="unverified_manual"')
    expect(html).toContain('data-route-ui-state="untested"')
    expect(html).toContain('aria-label="Copy model deepseek/deepseek-v3.1-terminus-thinking. Model not verified; endpoint failed"')
    expect(html).not.toContain("border-tag-destructive-border")
  })

  it("marks a third-party model failed only when the probe reports an invalid model", () => {
    const html = renderCardHtml({
      persisted: makePersisted({
        available_models: [{
          id: "gemini-2.0-flash-thinking-exp",
          endpoint_id: "api-qnaigc-com-v1-google-1d9e40f3e4",
          route_id: "api-qnaigc-com-v1-google-1d9e40f3e4:gemini-2.0-flash-thinking-exp",
          status: "failed",
          ui_state: "failed",
          last_probe_message: "Endpoint model probe failed (invalid_model). Provider returned HTTP 404.",
          capabilities: {
            reason_code: "invalid_model",
            probe_attempts: [{ status: "invalid_model", message: "Provider returned HTTP 404." }],
          },
        }],
      }),
    })

    expect(html).toContain('data-route-status="failed"')
    expect(html).toContain('data-route-ui-state="failed"')
    expect(html).toContain('aria-label="Copy model gemini-2.0-flash-thinking-exp. Route test failed"')
    expect(html).toContain("border-tag-destructive-border")
  })

  it("does not mark the endpoint or base URL failed when the only failure is invalid_model", () => {
    const html = renderCardHtml({
      nextDraft: makeDraft({
        base_url: "https://api.qnaigc.com/v1",
      }),
      persisted: makePersisted({
        base_url: "https://api.qnaigc.com/v1",
        provider_type: "openai_compatible",
        last_test_status: "error",
        last_error_code: "invalid_model",
        last_test_message: "Endpoint model probe failed (invalid_model). Provider returned HTTP 404.",
        available_models: [{
          id: "gemini-2.0-flash-thinking-exp",
          endpoint_id: "api-qnaigc-com-v1-google-1d9e40f3e4",
          route_id: "api-qnaigc-com-v1-google-1d9e40f3e4:gemini-2.0-flash-thinking-exp",
          status: "failed",
          ui_state: "failed",
          last_probe_message: "Endpoint model probe failed (invalid_model). Provider returned HTTP 404.",
          capabilities: {
            reason_code: "invalid_model",
            probe_attempts: [{ status: "invalid_model", message: "Provider returned HTTP 404." }],
          },
        }],
      }),
    })

    expect(html).toContain('data-endpoint-status="untested"')
    expect(html).not.toContain('data-endpoint-status="error"')
    expect(html).not.toContain('data-base-url-status="failed"')
    expect(html).toContain('data-route-status="failed"')
  })

  it("collapses duplicate third-party routes into one model tag and prefers a verified endpoint", () => {
    const duplicateModels: ModelInfo[] = [
      {
        id: "deepseek/deepseek-v3",
        endpoint_id: "qiniu-anthropic",
        route_id: "qiniu-anthropic:deepseek.deepseek-v3",
        status: "failed",
        ui_state: "failed",
        last_probe_message: "Use /v1/messages instead.",
      },
      {
        id: "deepseek/deepseek-v3",
        endpoint_id: "qiniu-openai",
        route_id: "qiniu-openai:deepseek.deepseek-v3",
        status: "verified",
        ui_state: "ready",
      },
      {
        id: "deepseek/deepseek-v3",
        endpoint_id: "qiniu-google",
        route_id: "qiniu-google:deepseek.deepseek-v3",
        status: "unverified_manual",
        ui_state: "untested",
      },
    ]

    const aggregated = aggregateThirdPartyModelInfos(duplicateModels)
    expect(aggregated).toHaveLength(1)
    expect(aggregated[0].status).toBe("verified")
    expect(aggregated[0].ui_state).toBe("ready")

    const html = renderCardHtml({
      persisted: makePersisted({ available_models: duplicateModels }),
    })
    const tags = html.match(/data-route-count="3"/g) ?? []
    expect(tags).toHaveLength(1)
    expect(html).toContain('data-route-status="verified"')
    expect(html).toContain('data-route-ui-state="ready"')
    expect(html).toContain('aria-label="Copy model deepseek/deepseek-v3. Verified route"')
  })

  it("collapses duplicate third-party routes and keeps historical-ready blue when no endpoint is currently verified", () => {
    const aggregated = aggregateThirdPartyModelInfos([
      {
        id: "anthropic/claude-fable-5",
        endpoint_id: "qiniu-anthropic",
        route_id: "qiniu-anthropic:anthropic.claude-fable-5",
        status: "unverified_manual",
        ui_state: "historical_ready",
      },
      {
        id: "anthropic/claude-fable-5",
        endpoint_id: "qiniu-openai",
        route_id: "qiniu-openai:anthropic.claude-fable-5",
        status: "failed",
        ui_state: "failed",
      },
    ])

    expect(aggregated).toHaveLength(1)
    expect(aggregated[0].status).toBe("probe-verified")
    expect(aggregated[0].ui_state).toBe("historical_ready")

    const html = renderCardHtml({
      persisted: makePersisted({ available_models: aggregated }),
    })
    expect(html).toContain('data-route-status="probe-verified"')
    expect(html).toContain('data-route-ui-state="historical_ready"')
    expect(html).toContain('aria-label="Copy model anthropic/claude-fable-5. Previously Connected"')
    expect(html).toContain("border-multimodal-border")
  })

  it("does not show an aggregate failed status when every route summary is still untested", () => {
    const aggregated = aggregateThirdPartyModelInfos([
      {
        id: "qwen3-30b-a3b-thinking-2507",
        endpoint_id: "qiniu-anthropic",
        route_id: "qiniu-anthropic:qwen3-30b-a3b-thinking-2507",
        status: "unverified_manual",
        ui_state: "failed",
      },
      {
        id: "qwen3-30b-a3b-thinking-2507",
        endpoint_id: "qiniu-openai",
        route_id: "qiniu-openai:qwen3-30b-a3b-thinking-2507",
        status: "unverified_manual",
        ui_state: "untested",
      },
    ])

    expect(aggregated).toHaveLength(1)
    expect(aggregated[0].status).toBe("unverified_manual")
    expect(aggregated[0].ui_state).toBe("untested")

    const html = renderCardHtml({
      persisted: makePersisted({ available_models: aggregated }),
    })
    expect(html).toContain('data-route-status="unverified_manual"')
    expect(html).toContain('data-route-ui-state="untested"')
    expect(html).toContain('aria-label="Copy model qwen3-30b-a3b-thinking-2507. Untested route"')
    expect(html).not.toContain("Route test failed")
  })

  it("copies the available model real id", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { clipboard: { writeText } })

    await copyAvailableModelId("deepseek/deepseek-v3.1-terminus")

    expect(writeText).toHaveBeenCalledWith("deepseek/deepseek-v3.1-terminus")
    vi.unstubAllGlobals()
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

  it("sorts official route chips with verified routes first and failed routes last", () => {
    const sorted = sortOfficialRouteInfos([
      { id: "a-failed", status: "failed" },
      { id: "z-verified", status: "verified" },
      { id: "m-image", status: "unverified_manual", capabilities: { model_type: "image_generation" } },
      { id: "a-neutral", status: "unverified_manual" },
    ]).map((model) => model.id)

    expect(sorted).toEqual([
      "z-verified",
      "a-neutral",
      "m-image",
      "a-failed",
    ])
  })

  it("sorts third-party models green(verified) > blue(historical) > neutral > failed > off to the top (item 4)", () => {
    // The third-party Available Models list must lift usable models to the top,
    // mirroring the tag colours: green (ready) first, then blue (historical),
    // then neutral (untested), with failed/off sinking. Previously the list was
    // sorted purely alphabetically, burying verified models below dead ones.
    const sorted = sortThirdPartyModelInfos([
      { id: "m-off", ui_state: "off" },
      { id: "m-failed", ui_state: "failed" },
      { id: "m-untested", ui_state: "untested" },
      { id: "m-historical", ui_state: "historical_ready" },
      { id: "m-ready", ui_state: "ready" },
    ]).map((model) => model.id)

    expect(sorted).toEqual([
      "m-ready", // green
      "m-historical", // blue
      "m-untested", // neutral
      "m-failed", // red
      "m-off", // muted / off
    ])
  })

  it("breaks third-party sort ties alphabetically within the same status (item 4)", () => {
    const sorted = sortThirdPartyModelInfos([
      { id: "zeta", ui_state: "ready" },
      { id: "alpha", ui_state: "ready" },
      { id: "mid", ui_state: "ready" },
    ]).map((model) => model.id)

    expect(sorted).toEqual(["alpha", "mid", "zeta"])
  })

  it("does not render chip area when persisted has no sdks/models", () => {
    const html = renderCardHtml({
      persisted: makePersisted({ available_sdks: [], available_models: [] }),
    })

    expect(html).not.toContain('data-testid="provider-capabilities"')
    expect(html).not.toContain("Available SDKs:")
    expect(html).not.toContain("Available Models:")
  })

  it("shows reachable field checks and an empty model-list warning after Get Models returns no models", () => {
    const nextDraft = makeDraft({
      id: "wavespeed",
      name: "WaveSpeed",
      base_url: "https://llm.wavespeed.ai/v1",
      provider_type: "openai_compatible",
    })
    const persisted = makePersisted({
      id: "wavespeed",
      name: "WaveSpeed",
      base_url: "https://llm.wavespeed.ai/v1",
      provider_type: "openai_compatible",
      last_test_status: "untested",
      last_test_at: "2026-05-27T12:00:00Z",
      last_test_message: "Endpoint reachable but returned no models.",
      available_sdks: [],
      available_models: [],
      test_results: [
        {
          params_fingerprint: providerTestParamsFingerprint(nextDraft),
          base_url: "https://llm.wavespeed.ai/v1",
          provider_type: "openai_compatible",
          last_test_status: "untested",
          last_test_at: "2026-05-27T12:00:00Z",
          last_test_message: "Endpoint reachable but returned no models.",
          last_error_code: "",
          available_sdks: [],
          available_models: [],
        },
      ],
    })
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={nextDraft}
        persisted={persisted}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).toContain("API key accepted by the model-list endpoint")
    expect(html).toContain('data-base-url-status="connected"')
    expect(html).toContain('aria-label="https://llm.wavespeed.ai/v1 connected"')
    expect(html).toContain("Available Models:")
    expect(html).toContain("No models returned")
    expect(html).toContain('data-variant="warning"')
    expect(html).not.toContain("Connected")
  })
})

describe("ProviderCard protocol controls", () => {
  it("does not render a manual protocol selector for third-party providers (apikeys#20)", () => {
    // apikeys#20: the backend test entry auto-detects the protocol, so the manual
    // dropdown is removed and third-party editable fields are name/base_url/api_key.
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ provider_type: "anthropic_compatible" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).not.toContain(">Protocol</label>")
    expect(html).not.toContain('data-slot="select-trigger"')
    expect(html).not.toContain(`provider-protocol-${draft.id}`)
    expect(html).toContain(">API Key</label>")
    expect(html).toContain(">Base URL</label>")
  })

  it("does not render protocol selection for official providers", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ provider_type: "anthropic_compatible" })}
        persisted={null}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).not.toContain(">Protocol</label>")
    expect(html).not.toContain('data-slot="select-trigger"')
    expect(html).not.toContain(`provider-protocol-${draft.id}`)
    expect(html).not.toContain("Anthropic compatible")
  })
})

describe("endpointTagIsTestable — single-endpoint probe affordance (item 2)", () => {
  // Clicking an endpoint tag re-probes THAT one (URL, protocol) cell. A tag is a
  // click target only when there is something to probe and no reason it cannot:
  //   - not_configured → no api key / base url yet, nothing to test
  //   - testing        → a probe is already in flight
  //   - protocol_unsupported → a dormant architectural fact (§4.2: gray = not
  //     user-fixable); its only affordance is the explicit half-life-bypassing
  //     Re-probe button (§1.2 matrix point 4), not a plain re-test.
  it("treats configured, idle endpoints (verified / untested / failed) as testable", () => {
    for (const status of [
      "ok",
      "untested",
      "invalid_key",
      "rate_limited",
      "quota_exceeded",
      "network_error",
      "timeout",
      "error",
    ] as const) {
      expect(endpointTagIsTestable(status)).toBe(true)
    }
  })

  it("does not treat testing / not_configured / protocol_unsupported cells as testable", () => {
    expect(endpointTagIsTestable("testing")).toBe(false)
    expect(endpointTagIsTestable("not_configured")).toBe(false)
    expect(endpointTagIsTestable("protocol_unsupported")).toBe(false)
  })
})

describe("ProviderCard 6-state ui_state projection (apikeys#30)", () => {
  it("does not duplicate route connectivity as a third-party header badge", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({ base_url: "https://api.example.com/v1" })}
        persisted={makePersisted({
          base_url: "https://api.example.com/v1",
          last_test_status: "error",
          last_error_code: "endpoint_test_failed",
          available_models: [
            { id: "openai/gpt-5", route_id: "p1:gpt-5", status: "verified", ui_state: "ready" },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).not.toContain('data-provider-state-label="ready"')
    expect(html).not.toContain(">Ready</")
    expect(html).toContain(">Test failed</")
  })

  it("does not show historical route state as the provider test state", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={draft}
        persisted={makePersisted({
          last_test_status: "untested",
          available_models: [
            { id: "openai/gpt-5", route_id: "p1:gpt-5", status: "unverified_manual", ui_state: "historical_ready" },
          ],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).not.toContain('data-provider-state-label="historical_ready"')
    expect(html).toContain(">Not configured</")
    expect(html).toContain('aria-label="Copy model openai/gpt-5. Previously Connected"')
  })

  it("does not render a state badge when no route carries a backend ui_state", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={draft}
        persisted={makePersisted({
          available_models: [{ id: "openai/gpt-5", route_id: "p1:gpt-5", status: "unverified_manual" }],
        })}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
      />,
    )

    expect(html).not.toContain("data-provider-state-label=")
  })

  it("picks the most-usable representative state across the endpoint's routes", () => {
    expect(representativeProviderUiState([
      { id: "a", ui_state: "failed" },
      { id: "b", ui_state: "ready" },
      { id: "c", ui_state: "untested" },
    ])).toBe("ready")
    expect(representativeProviderUiState([
      { id: "a", ui_state: "failed" },
      { id: "b", ui_state: "historical_ready" },
    ])).toBe("historical_ready")
    expect(representativeProviderUiState([{ id: "a", status: "verified" }])).toBeNull()
    expect(representativeProviderUiState([])).toBeNull()
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
  // R6-2: the delete button no longer fires a body-level sonner toast (which
  // closed the Settings modal on click). It signals intent via onRequestDelete;
  // the parent turns that into an in-tree AlertDialog request.
  it("delete trigger signals intent via onRequestDelete without deleting", () => {
    const onRequestDelete = vi.fn()
    const element = ProviderDeleteButton({ onRequestDelete })
    const html = renderToStaticMarkup(<ProviderDeleteButton onRequestDelete={onRequestDelete} />)

    expect(html).toContain('aria-label="Delete provider"')
    expect(html).toContain('data-delete-toast-trigger="true"')
    element.props.onClick()

    expect(onRequestDelete).toHaveBeenCalledTimes(1)
  })

  it("builds an AlertDialog delete request wired to provider deletion", () => {
    const onDelete = vi.fn()

    const request = buildProviderDeleteRequest("OpenAI", onDelete)

    expect(request).toMatchObject({
      title: "Delete OpenAI?",
      description: "This provider and its routes will be removed from API Keys, LLM Roles, and model bundles.",
    })
    expect(onDelete).not.toHaveBeenCalled()

    void request.onConfirm()
    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it("shows a protocol-unsupported cell honestly and offers a force re-probe", () => {
    // Design §1.2 protocol matrix point 4: within the 30-day half-life the bulk
    // Test skips the cell, so the card must (a) label the cell "Protocol not
    // supported" (not "Untested"/"Invalid API key" lies) and (b) offer an
    // explicit per-cell re-probe that bypasses the gate.
    const unsupported = makePersisted({
      id: "qiniu-google",
      name: "Qiniu",
      base_url: "https://api.qiniu.example/v1",
      provider_type: "google_genai",
      last_test_status: "protocol_unsupported" as TestStatus,
      last_error_code: "protocol_unsupported",
      last_test_at: "2026-07-02T09:00:00Z",
      last_test_message: "Endpoint model probe failed (protocol_unsupported).",
    })
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={makeDraft({
          id: "qiniu-google",
          name: "Qiniu",
          base_url: "https://api.qiniu.example/v1",
          provider_type: "google_genai",
        })}
        persisted={unsupported}
        onFieldChange={vi.fn()}
        onGetModels={vi.fn()}
        onDelete={vi.fn()}
        providerKind="third-party"
        onForceEndpointTest={vi.fn()}
      />,
    )

    expect(html).toContain("Protocol not supported")
    expect(html).toContain("Re-probe protocol")
  })
})

function makeEndpointSummary(overrides: Partial<EndpointSummary>): EndpointSummary {
  return {
    id: "endpoint",
    label: "Qiniu",
    baseUrl: "https://api.qnaigc.com/v1",
    protocol: "openai_compatible",
    status: "ok",
    routeCount: 0,
    sdkCount: 0,
    profileCount: 0,
    methodIds: [],
    requestMapperIds: [],
    profileCapabilities: [],
    toolProtocol: "not_listed",
    ...overrides,
  }
}

describe("verifiedSiblingProtocolsOnSameHost", () => {
  // Design §1.2 protocol matrix point 9: a protocol_unsupported cell is not a
  // dead end — the capability lives in a verified sibling protocol on the SAME
  // host (anthropic.qnaigc.com × OpenAI → same host × Anthropic). The tooltip
  // must point there so the muted cell doesn't read as "this key/host is dead".
  it("points an unsupported cell to the verified sibling protocol on the same host", () => {
    const unsupported = makeEndpointSummary({
      id: "an-openai",
      baseUrl: "https://anthropic.qnaigc.com",
      protocol: "openai_compatible",
      status: "protocol_unsupported",
    })
    const endpoints = [
      unsupported,
      makeEndpointSummary({
        id: "an-anthropic",
        baseUrl: "https://anthropic.qnaigc.com",
        protocol: "anthropic_compatible",
        status: "ok",
      }),
    ]
    expect(verifiedSiblingProtocolsOnSameHost(unsupported, endpoints)).toEqual([
      "anthropic_compatible",
    ])
  })

  it("lists every verified sibling protocol on the same host, de-duplicated and path-agnostic", () => {
    const unsupported = makeEndpointSummary({
      id: "api-gemini",
      baseUrl: "https://api.qnaigc.com/v1",
      protocol: "google_genai",
      status: "protocol_unsupported",
    })
    const endpoints = [
      unsupported,
      makeEndpointSummary({
        id: "api-openai",
        baseUrl: "https://api.qnaigc.com/v1",
        protocol: "openai_compatible",
        status: "ok",
      }),
      // Same host, different path — still the same host.
      makeEndpointSummary({
        id: "api-anthropic",
        baseUrl: "https://api.qnaigc.com",
        protocol: "anthropic_compatible",
        status: "ok",
      }),
    ]
    expect(verifiedSiblingProtocolsOnSameHost(unsupported, endpoints)).toEqual([
      "openai_compatible",
      "anthropic_compatible",
    ])
  })

  it("excludes a different host and any non-verified sibling", () => {
    const unsupported = makeEndpointSummary({
      id: "an-openai",
      baseUrl: "https://anthropic.qnaigc.com",
      protocol: "openai_compatible",
      status: "protocol_unsupported",
    })
    const endpoints = [
      unsupported,
      // Different host — the redirect must stay on the SAME host.
      makeEndpointSummary({
        id: "other-host",
        baseUrl: "https://api.qnaigc.com/v1",
        protocol: "anthropic_compatible",
        status: "ok",
      }),
      // Same host but itself unsupported — not a live route to redirect to.
      makeEndpointSummary({
        id: "an-gemini",
        baseUrl: "https://anthropic.qnaigc.com",
        protocol: "google_genai",
        status: "protocol_unsupported",
      }),
    ]
    expect(verifiedSiblingProtocolsOnSameHost(unsupported, endpoints)).toEqual([])
  })
})

describe("endpointTooltipLines protocol_unsupported guidance", () => {
  it("appends a redirect line naming the verified sibling protocol", () => {
    const unsupported = makeEndpointSummary({
      id: "an-openai",
      baseUrl: "https://anthropic.qnaigc.com",
      protocol: "openai_compatible",
      status: "protocol_unsupported",
    })
    const joined = endpointTooltipLines(unsupported, ["anthropic_compatible"]).join(" ")
    expect(joined).toContain("does not serve")
    expect(joined).toContain("Anthropic-compatible")
    expect(joined).toContain("use its")
  })

  it("falls back to a no-route line when the host serves no other protocol", () => {
    const unsupported = makeEndpointSummary({
      id: "solo",
      baseUrl: "https://solo.example",
      protocol: "google_genai",
      status: "protocol_unsupported",
    })
    const joined = endpointTooltipLines(unsupported, []).join(" ")
    expect(joined).toContain("does not serve")
    expect(joined).not.toContain("use its")
  })

  it("adds no guidance line for a verified cell", () => {
    const verified = makeEndpointSummary({ status: "ok" })
    const joined = endpointTooltipLines(verified, []).join(" ")
    expect(joined).not.toContain("does not serve")
  })
})
