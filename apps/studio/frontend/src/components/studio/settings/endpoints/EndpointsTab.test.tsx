import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { ProviderImportDraft, RegistryResponse } from "@/api/llm"
import { EndpointsTab } from "./EndpointsTab"
import { ImportDraftPanel } from "./ImportDraftPanel"

const registry: RegistryResponse = {
  provider_endpoints: {
    "anthropic-official": {
      endpoint_id: "anthropic-official",
      display_name: "Anthropic Official",
      protocol: "anthropic_compatible",
      base_url: "https://api.anthropic.com",
      api_key: "**********",
      status: "verified",
      timeout_seconds: 60,
      trust_env: false,
      proxy_env: null,
      last_test_at: "2026-05-24T00:00:00Z",
      last_test_message: "Credential present.",
      metadata: { vendor: "anthropic" },
    },
  },
  provider_routes: {
    "anthropic-official:claude-opus-4-7-thinking": {
      route_id: "anthropic-official:claude-opus-4-7-thinking",
      endpoint_id: "anthropic-official",
      route_slug: "claude-opus-4-7-thinking",
      provider_model_id: "claude-opus-4-7-thinking",
      canonical_id: "claude-opus-4-7",
      display_name: "Claude Opus 4.7 Thinking",
      status: "verified",
      capabilities: {},
      metadata: {},
    },
  },
  runtime_policy: {
    provider_down_ttl_seconds: 300,
    probe_timeout_seconds: 30,
    token_escalation_rounds: 2,
  },
  model_profiles: {},
  roles: {},
  canonical_groups: [],
  lint_results: [],
}

const draft: ProviderImportDraft = {
  draft_id: "draft-openrouter",
  source: { url: "https://openrouter.ai/docs" },
  status: "needs_probe",
  created_at: "2026-05-24T00:00:00Z",
  updated_at: null,
  expires_at: null,
  endpoint_candidates: {
    openrouter: {
      endpoint_id: "openrouter",
      display_name: "OpenRouter",
      protocol: "openai_compatible",
      base_url: "https://openrouter.ai/api/v1",
      api_key: null,
      status: "unverified_manual",
      timeout_seconds: 60,
      trust_env: false,
      proxy_env: null,
      metadata: {},
      field_sources: { base_url: { source: "agent_draft" } },
    },
  },
  route_candidates: {
    "openrouter:anthropic-claude-opus-4-7-thinking": {
      endpoint_id: "openrouter",
      route_slug: "anthropic-claude-opus-4-7-thinking",
      provider_model_id: "anthropic/claude-opus-4-7-thinking",
      canonical_id: "claude-opus-4-7",
      display_name: "Claude Opus 4.7 Thinking via OpenRouter",
      capabilities: {},
      field_sources: { provider_model_id: { source: "agent_draft" } },
      metadata: {},
    },
  },
  probe_results: {},
  agent_notes: [],
  diff: { conflicts: ["endpoint_id"] },
}

describe("EndpointsTab", () => {
  it("renders Endpoints copy, endpoint fields, and route probe actions", () => {
    const html = renderToStaticMarkup(
      <EndpointsTab
        registry={registry}
        loading={false}
        error={null}
        saveStatus="saved"
        importDrafts={[]}
        onAddEndpoint={() => undefined}
        onEndpointChange={() => undefined}
        onDeleteEndpoint={() => undefined}
        onTestEndpoint={() => undefined}
        onProbeRoute={() => undefined}
        onApplyDraft={() => undefined}
      />,
    )

    expect(html).toContain("Endpoints")
    expect(html).not.toContain("API Keys")
    expect(html).toContain("Anthropic Official")
    expect(html).toContain("Claude Opus 4.7 Thinking")
    expect(html).toContain("Probe")
  })

  it("renders import draft diffs and disables apply until probed", () => {
    const html = renderToStaticMarkup(
      <ImportDraftPanel
        drafts={[draft]}
        onApplyDraft={() => undefined}
      />,
    )

    expect(html).toContain("Import Drafts")
    expect(html).toContain("OpenRouter")
    expect(html).toContain("anthropic/claude-opus-4-7-thinking")
    expect(html).toContain("Apply disabled")
  })
})
