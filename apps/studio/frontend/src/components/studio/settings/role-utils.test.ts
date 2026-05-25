import { describe, expect, it } from "vitest"
import type { ModelProfile, RegistryResponse, RoleEntry } from "@/api/llm"
import {
  appendRouteToRole,
  applyProfileToRole,
  groupAvailableRoutes,
  moveRouteInRole,
  removeRouteFromRole,
} from "./role-utils"

const baseRole: RoleEntry = {
  system_prompt_prefix: "",
  fallback_chain: [
    { route_id: "anthropic-official:claude-opus-4-7-thinking" },
    { route_id: "openrouter:anthropic-claude-opus-4-7-thinking" },
  ],
  lint_requirements: { thinking: "error" },
}

const profile: ModelProfile = {
  model_profile_id: "clo47t",
  display_name: "Claude Opus 4.7 Thinking",
  canonical_id: "claude-opus-4-7",
  tags: ["thinking"],
  fallback_chain: [
    { route_id: "anthropic-official:claude-opus-4-7-thinking", max_output_tokens: 4096 },
  ],
  lint_requirements: { thinking: "error", tool_calling: "warn" },
}

const registry: RegistryResponse = {
  provider_endpoints: {},
  runtime_policy: {
    provider_down_ttl_seconds: 300,
    probe_timeout_seconds: 30,
    token_escalation_rounds: 2,
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
  model_profiles: { clo47t: profile },
  roles: { graph_main: baseRole },
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
  lint_results: [],
  setup_required: false,
}

describe("role-utils route-chain helpers", () => {
  it("appends exact route IDs without canonicalizing or rewriting them", () => {
    const next = appendRouteToRole(baseRole, "custom-endpoint:RAW.Model/Name-2026-05-25")

    expect(next.fallback_chain.map((entry) => entry.route_id)).toEqual([
      "anthropic-official:claude-opus-4-7-thinking",
      "openrouter:anthropic-claude-opus-4-7-thinking",
      "custom-endpoint:RAW.Model/Name-2026-05-25",
    ])
  })

  it("moves and removes route entries by exact route ID", () => {
    const moved = moveRouteInRole(baseRole, 1, 0)
    expect(moved.fallback_chain.map((entry) => entry.route_id)).toEqual([
      "openrouter:anthropic-claude-opus-4-7-thinking",
      "anthropic-official:claude-opus-4-7-thinking",
    ])

    const removed = removeRouteFromRole(moved, "openrouter:anthropic-claude-opus-4-7-thinking")
    expect(removed.fallback_chain.map((entry) => entry.route_id)).toEqual([
      "anthropic-official:claude-opus-4-7-thinking",
    ])
  })

  it("applies model profiles as explicit route-chain replacement", () => {
    const next = applyProfileToRole(baseRole, profile)

    expect(next.source_profile_id).toBe("clo47t")
    expect(next.fallback_chain).toEqual(profile.fallback_chain)
    expect(next.lint_requirements).toEqual(profile.lint_requirements)
  })

  it("groups available routes from backend canonical_groups only", () => {
    const groups = groupAvailableRoutes(registry)

    expect(groups).toHaveLength(1)
    expect(groups[0].canonical_id).toBe("claude-opus-4-7")
    expect(groups[0].routes.map((route) => route.route_id)).toEqual([
      "anthropic-official:claude-opus-4-7-thinking",
      "openrouter:anthropic-claude-opus-4-7-thinking",
    ])
  })
})
