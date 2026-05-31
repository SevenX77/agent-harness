import { describe, expect, it } from "vitest"
import type { CredentialsState, RolesData } from "@/api/llm"
import {
  buildRoleTestTargets,
  roleChainStatusKey,
  runRoleTestTargets,
  runWithConcurrency,
} from "./useRoleTestChainRunner"

const rolesData: RolesData = {
  models: {
    CL46T: {
      name: "Claude",
      providers: { anthropic: "claude-sonnet-test", openai_proxy: "anthropic/claude" },
    },
    DS32R: {
      name: "DeepSeek",
      providers: { deepseek: "deepseek-chat" },
    },
  },
  providers: {
    anthropic: { name: "Anthropic", type: "anthropic_compatible" },
    openai_proxy: { name: "Proxy", type: "openai_compatible" },
    deepseek: { name: "DeepSeek", type: "openai_compatible" },
  },
  roles: {
    copilot_chat: {
      model_fallback_enabled: true,
      active_model: "CL46T",
      models: {
        CL46T: { providers: ["anthropic", "openai_proxy"] },
        DS32R: { providers: ["deepseek"] },
      },
    },
  },
}

const credentials: CredentialsState = {
  providers: [
    { id: "anthropic", name: "Anthropic", api_key: "sk-a", provider_type: "anthropic_compatible" },
    { id: "openai_proxy", name: "Proxy", api_key: "sk-p", provider_type: "openai_compatible" },
  ],
}

describe("useRoleTestChainRunner helpers", () => {
  it("builds model-parallel provider chains with provider model ids", () => {
    const chains = buildRoleTestTargets(rolesData, "copilot_chat", credentials)

    expect(chains.map((chain) => chain.map((target) => target.providerCode))).toEqual([
      ["anthropic", "openai_proxy"],
      ["deepseek"],
    ])
    expect(chains[0][0].modelId).toBe("claude-sonnet-test")
    expect(chains[1][0].credential).toBeNull()
  })

  it("resolves route-id provider entries through their endpoint credential", () => {
    const routeId = "deepseek-official:deepseek-v4-pro"
    const chains = buildRoleTestTargets({
      models: {
        "deepseek-v4-pro": {
          name: "DeepSeek V4 Pro",
          providers: { [routeId]: "deepseek-chat" },
        },
      },
      providers: {
        [routeId]: {
          name: "DeepSeek Official",
          type: "openai_compatible",
          endpoint_id: "deepseek-official",
        },
      },
      roles: {
        analyst: {
          model_fallback_enabled: true,
          active_model: "deepseek-v4-pro",
          models: {
            "deepseek-v4-pro": { providers: [routeId] },
          },
        },
      },
    }, "analyst", {
      providers: [
        {
          id: "deepseek-official",
          name: "DeepSeek Official",
          api_key: "sk-deepseek",
          provider_type: "openai_compatible",
        },
      ],
    })

    expect(chains[0][0]).toMatchObject({
      modelCode: "deepseek-v4-pro",
      providerCode: routeId,
      modelId: "deepseek-chat",
    })
    expect(chains[0][0].credential?.id).toBe("deepseek-official")
  })

  it("uses a stable status key per model-provider pair", () => {
    expect(roleChainStatusKey("CL46T", "anthropic")).toBe("CL46T:anthropic")
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

  it("runs different providers in the same model chain concurrently", async () => {
    let active = 0
    let maxActive = 0
    const chains = buildRoleTestTargets(rolesData, "copilot_chat", credentials)

    await runRoleTestTargets(chains.slice(0, 1), 2, async () => {
      active += 1
      maxActive = Math.max(maxActive, active)
      await Promise.resolve()
      active -= 1
    })

    expect(maxActive).toBe(2)
  })
})
