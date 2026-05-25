import { describe, expect, it } from "vitest"
import type { RegistryResponse, RolesData } from "@/api/llm"
import { buildRoleProbeTargets, roleChainStatusKey, runWithConcurrency } from "./useRoleTestChainRunner"

const rolesData: RolesData = {
  schema_version: 2,
  model_profiles: {},
  roles: {
    copilot_chat: {
      system_prompt_prefix: "",
      fallback_chain: [
        { route_id: "anthropic-official:claude-sonnet-4-6" },
        { route_id: "openrouter:anthropic-claude-sonnet-4-6" },
        { route_id: "missing:route" },
      ],
      lint_requirements: { thinking: "warn" },
    },
  },
}

const registry: RegistryResponse = {
  provider_endpoints: {},
  runtime_policy: {
    provider_down_ttl_seconds: 300,
    probe_timeout_seconds: 30,
    token_escalation_rounds: 2,
  },
  provider_routes: {
    "anthropic-official:claude-sonnet-4-6": {
      route_id: "anthropic-official:claude-sonnet-4-6",
      endpoint_id: "anthropic-official",
      route_slug: "claude-sonnet-4-6",
      provider_model_id: "claude-sonnet-4-6",
      canonical_id: "claude-sonnet-4-6",
      display_name: "Claude Sonnet 4.6",
      status: "verified",
      capabilities: {},
      metadata: {},
    },
    "openrouter:anthropic-claude-sonnet-4-6": {
      route_id: "openrouter:anthropic-claude-sonnet-4-6",
      endpoint_id: "openrouter",
      route_slug: "anthropic-claude-sonnet-4-6",
      provider_model_id: "anthropic/claude-sonnet-4-6",
      canonical_id: "claude-sonnet-4-6",
      display_name: "Claude Sonnet 4.6 via OpenRouter",
      status: "unverified_manual",
      capabilities: {},
      metadata: {},
    },
  },
  model_profiles: {},
  roles: rolesData.roles,
  canonical_groups: [
    {
      canonical_id: "claude-sonnet-4-6",
      display_name: "Claude Sonnet 4.6",
      routes: [
        "anthropic-official:claude-sonnet-4-6",
        "openrouter:anthropic-claude-sonnet-4-6",
      ],
    },
  ],
  lint_results: [],
  setup_required: false,
}

describe("useRoleTestChainRunner helpers", () => {
  it("builds route probe targets without converting route IDs", () => {
    const targets = buildRoleProbeTargets(rolesData, "copilot_chat", registry)

    expect(targets.map((target) => target.routeId)).toEqual([
      "anthropic-official:claude-sonnet-4-6",
      "openrouter:anthropic-claude-sonnet-4-6",
      "missing:route",
    ])
    expect(targets[0].route?.provider_model_id).toBe("claude-sonnet-4-6")
    expect(targets[2].route).toBeNull()
    expect(targets[0].capabilities).toEqual(["thinking"])
  })

  it("uses a stable status key per role-route pair", () => {
    expect(roleChainStatusKey("copilot_chat", "anthropic-official:claude-sonnet-4-6")).toBe(
      "copilot_chat:anthropic-official:claude-sonnet-4-6",
    )
  })

  it("runs queued work without exceeding the concurrency limit", async () => {
    let active = 0
    let maxActive = 0
    await runWithConcurrency([1, 2, 3, 4, 5], 2, async () => {
      active += 1
      maxActive = Math.max(maxActive, active)
      await Promise.resolve()
      active -= 1
    })

    expect(maxActive).toBeLessThanOrEqual(2)
  })
})
