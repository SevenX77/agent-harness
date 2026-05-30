import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  ProviderCard,
  ProviderDeleteButton,
  apiKeyInputClassName,
  apiKeyInputType,
  copyAvailableModelId,
  sortOfficialRouteInfos,
  sortModelInfos,
} from "./ProviderCard"
import type { CredentialsState, TestStatus } from "../../../api/llm"
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
    expect(html).toContain('aria-label="Copy API key"')
    expect(html).toContain("transition-none")
    expect(html).toContain("text-muted-foreground")
    expect(html).toContain("Get Models")
    expect(html).toContain("Endpoint test")
    expect(html).toContain(">Test</button>")
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

  it("uses muted text only while the API key is hidden", () => {
    expect(apiKeyInputClassName(false)).toContain("text-muted-foreground")
    expect(apiKeyInputClassName(false)).not.toContain("text-foreground")
    expect(apiKeyInputClassName(true)).toContain("text-foreground")
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
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
        onDelete={vi.fn()}
        providerKind="official"
      />,
    )

    expect(html).toContain("OpenAI Official")
    expect(html).not.toContain('data-variant="outline">Official</span>')
    expect(html).not.toContain("Not configured")
    expect(html).not.toContain('aria-label="Provider Name"')
    expect(html).not.toContain('aria-label="Delete provider"')
    expect(html).not.toContain("Base URL")
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

    expect(html).toContain("Anthropic Official")
    expect(html).not.toContain(">anthropic-official<")
    expect(html).not.toContain("Connected")
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
    expect(html).not.toContain("Untested")
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
    expect(testButton).not.toContain('data-variant="secondary"')
    expect(html).not.toContain("Get Models")
    expect(html).not.toContain("Endpoint test")
    expect(html).not.toContain("Please choose one model from Available Models for endpoint testing.")
    expect(html).not.toContain('placeholder="e.g. doubao-seed-2-0-pro-260215"')
    expect(html).toContain(">Test</button>")
  })

  it("renders third-party API key before protocol and keeps endpoint test below base URL", () => {
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
    const protocolIndex = html.indexOf(">Protocol</label>")
    const baseUrlIndex = html.indexOf(">Base URL</label>")
    const endpointTestIndex = html.indexOf(">Endpoint test</label>")
    expect(apiKeyIndex).toBeGreaterThan(-1)
    expect(protocolIndex).toBeGreaterThan(apiKeyIndex)
    expect(baseUrlIndex).toBeGreaterThan(protocolIndex)
    expect(baseUrlIndex).toBeGreaterThan(apiKeyIndex)
    expect(endpointTestIndex).toBeGreaterThan(baseUrlIndex)
    expect(html).toContain("Get Models")
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
    expect(idleTag).not.toContain("api-route-tag-border-flow")
  })

  it("renders generated multimodal route candidates with a multimodal border and shadcn-only tooltip", () => {
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
    expect(tag).toContain('data-variant="multimodal"')
    expect(tag).toContain('data-model-type="image_generation"')
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

  it("keeps generated multimodal official entries multimodal-colored even if stale data marked them verified", () => {
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
    expect(tag).toContain('data-variant="multimodal"')
    expect(tag).not.toContain('data-variant="success"')
    expect(tag).toContain('data-model-type="image_generation"')
    expect(tag).toContain("Image generation model")
    expect(tag).not.toContain("Verified route")
    expect(tag).not.toContain("Verified text chat")
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
    expect(html).toContain('aria-label="Copy model deepseek/deepseek-v3.1-terminus"')
    expect(html).toContain("cursor-pointer")
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
    expect(html).toContain("Base URL accepted by the model-list endpoint")
    expect(html).toContain("Available Models:")
    expect(html).toContain("No models returned")
    expect(html).toContain('data-variant="warning"')
    expect(html).not.toContain("Connected")
  })
})

describe("ProviderCard protocol controls", () => {
  it("renders protocol selection for third-party providers", () => {
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
        onGetModels={vi.fn()}
        onEndpointTest={vi.fn()}
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
  it("delete trigger uses a shadcn sonner confirmation toast", () => {
    const onDelete = vi.fn()
    const element = ProviderDeleteButton({ draftName: "OpenAI", onDelete })
    const html = renderToStaticMarkup(<ProviderDeleteButton draftName="OpenAI" onDelete={onDelete} />)

    expect(html).toContain('aria-label="Delete provider"')
    expect(html).toContain('data-delete-toast-trigger="true"')
    element.props.onClick()

    expect(toastMock).toHaveBeenCalledWith(
      "Delete OpenAI?",
      expect.objectContaining({
        description: "This provider configuration will be removed from the credentials document.",
        duration: Infinity,
        action: expect.objectContaining({ label: "Delete" }),
        cancel: expect.objectContaining({ label: "Cancel" }),
        classNames: expect.objectContaining({
          actionButton: expect.stringContaining("!bg-destructive"),
        }),
      }),
    )
    expect(onDelete).not.toHaveBeenCalled()
  })

  it("sonner delete action remains wired to provider deletion", () => {
    const onDelete = vi.fn()
    const element = ProviderDeleteButton({ draftName: "OpenAI", onDelete })
    element.props.onClick()
    const options = toastMock.mock.calls.at(-1)?.[1] as {
      action?: { onClick?: () => void }
    }

    options.action?.onClick?.()

    expect(onDelete).toHaveBeenCalledTimes(1)
  })
})
