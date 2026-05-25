import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { RegistryResponse, RolesData } from "@/api/llm"
import { createRouteDragData, LlmRolesTab } from "./LlmRolesTab"

const rolesData: RolesData = {
  schema_version: 2,
  model_profiles: {
    clo47t: {
      model_profile_id: "clo47t",
      display_name: "Claude Opus 4.7 Thinking",
      canonical_id: "claude-opus-4-7",
      tags: ["thinking"],
      fallback_chain: [{ route_id: "anthropic-official:claude-opus-4-7-thinking" }],
      lint_requirements: { thinking: "error" },
    },
  },
  roles: {
    graph_agent: {
      system_prompt_prefix: "",
      source_profile_id: null,
      fallback_chain: [{ route_id: "anthropic-official:claude-opus-4-7-thinking" }],
      lint_requirements: { thinking: "error" },
    },
  },
}

const registry: RegistryResponse = {
  provider_endpoints: {},
  provider_routes: {
    "anthropic-official:claude-opus-4-7-thinking": {
      route_id: "anthropic-official:claude-opus-4-7-thinking",
      endpoint_id: "anthropic-official",
      route_slug: "claude-opus-4-7-thinking",
      provider_model_id: "claude-opus-4-7-thinking",
      canonical_id: "claude-opus-4-7",
      display_name: "Claude Opus 4.7 Thinking",
      status: "verified",
      capabilities: {
        thinking_protocol: {
          value: "anthropic",
          source: "probed_verified",
        },
      },
      metadata: {},
    },
    "openrouter:anthropic-claude-opus-4-7-thinking": {
      route_id: "openrouter:anthropic-claude-opus-4-7-thinking",
      endpoint_id: "openrouter",
      route_slug: "anthropic-claude-opus-4-7-thinking",
      provider_model_id: "anthropic/claude-opus-4-7-thinking",
      canonical_id: "claude-opus-4-7",
      display_name: "Claude Opus 4.7 Thinking via OpenRouter",
      status: "unverified_manual",
      capabilities: {},
      metadata: {},
    },
  },
  runtime_policy: {
    provider_down_ttl_seconds: 300,
    probe_timeout_seconds: 30,
    token_escalation_rounds: 2,
  },
  model_profiles: rolesData.model_profiles,
  roles: rolesData.roles,
  canonical_groups: [
    {
      canonical_id: "claude-opus-4-7",
      display_name: "Claude Opus 4.7",
      routes: [
        "anthropic-official:claude-opus-4-7-thinking",
        "openrouter:anthropic-claude-opus-4-7-thinking",
      ],
    },
  ],
  lint_results: [
    {
      role_name: "graph_agent",
      route_id: "openrouter:anthropic-claude-opus-4-7-thinking",
      severity: "warn",
      capability: "thinking",
      message: "thinking not verified",
      source: "lint",
      blocking: false,
      code: "requires_probe",
    },
  ],
}

describe("LlmRolesTab", () => {
  it("renders model profiles and available routes grouped by backend canonical_id", () => {
    const html = renderToStaticMarkup(
      <LlmRolesTab
        data={rolesData}
        registry={registry}
        saveStatus="saved"
        error={null}
        onChange={() => undefined}
        onProbeRole={() => undefined}
        onApplyProfile={() => undefined}
      />,
    )

    expect(html).toContain("Model Profiles")
    expect(html).toContain("Available Routes")
    expect(html).toContain("Claude Opus 4.7")
    expect(html).toContain("Claude Opus 4.7 Thinking")
    expect(html).toContain("anthropic-official:claude-opus-4-7-thinking")
  })

  it("keeps drag payloads as exact route IDs", () => {
    expect(createRouteDragData("openrouter:RAW.Model/Name-2026-05-25")).toEqual({
      type: "route",
      route_id: "openrouter:RAW.Model/Name-2026-05-25",
    })
  })
})
