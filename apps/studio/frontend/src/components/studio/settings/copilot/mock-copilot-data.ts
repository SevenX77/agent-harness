export type CopilotSdkId = "claude-agent-sdk" | "codex-sdk"

export type CopilotProviderApiStatus = "ready" | "failed"

export type CopilotAgentStatus = "ready" | "not_tested" | "unsupported"

export interface CopilotRoutePreview {
  id: string
  provider: string
  modelId: string
  endpoint: string
  methodId: string
  adapter: string
  providerApiStatus: CopilotProviderApiStatus
  agentStatus: CopilotAgentStatus
  capabilities: string[]
  note?: string
}

export interface CopilotRolePreview {
  id: string
  title: string
  modelLabel: string
  description: string
  sdkId: CopilotSdkId
  source: "built_in" | "third_party"
  fallbackEnabled: boolean
  activeRouteIds: string[]
  availableRoutes: CopilotRoutePreview[]
}

export const copilotSdkLabels: Record<CopilotSdkId, string> = {
  "claude-agent-sdk": "Claude Agent SDK",
  "codex-sdk": "Codex SDK",
}

export const claudeAgentSdkCompatibleMethodIds = [
  "anthropic_messages",
  "deepseek_anthropic_messages",
  "ark_anthropic_messages",
] as const

export function isClaudeAgentSdkCompatibleRoute(route: CopilotRoutePreview): boolean {
  return claudeAgentSdkCompatibleMethodIds.includes(
    route.methodId as (typeof claudeAgentSdkCompatibleMethodIds)[number],
  )
}

export const initialClaudeCopilotRoleIds = ["copilot_opus_4_7", "copilot_deepseek_v4"] as const

export const mockCopilotRoles: CopilotRolePreview[] = [
  {
    id: "copilot_opus_4_7",
    title: "Opus 4.7 Copilot",
    modelLabel: "claude-opus-4-7",
    description: "Default high-quality coding copilot role.",
    sdkId: "claude-agent-sdk",
    source: "built_in",
    fallbackEnabled: false,
    activeRouteIds: ["anthropic-official:claude-opus-4-7", "qiniu-anthropic:claude-opus-4-7"],
    availableRoutes: [
      {
        id: "anthropic-official:claude-opus-4-7",
        provider: "Anthropic Official",
        modelId: "claude-opus-4-7",
        endpoint: "https://api.anthropic.com",
        methodId: "anthropic_messages",
        adapter: "Standard Anthropic",
        providerApiStatus: "ready",
        agentStatus: "ready",
        capabilities: ["text", "read", "edit"],
      },
      {
        id: "qiniu-anthropic:claude-opus-4-7",
        provider: "Qiniu Anthropic",
        modelId: "claude-opus-4-7",
        endpoint: "https://ai.qiniuapi.com/v1",
        methodId: "anthropic_messages",
        adapter: "Standard Anthropic",
        providerApiStatus: "ready",
        agentStatus: "not_tested",
        capabilities: ["text", "read"],
      },
      {
        id: "openrouter:anthropic.claude-opus-4-7",
        provider: "OpenRouter",
        modelId: "anthropic/claude-opus-4-7",
        endpoint: "https://openrouter.ai/api/v1",
        methodId: "openai_chat_completions",
        adapter: "Not available",
        providerApiStatus: "ready",
        agentStatus: "unsupported",
        capabilities: ["provider api"],
        note: "OpenAI-compatible routes are not selectable for Claude Agent SDK.",
      },
    ],
  },
  {
    id: "copilot_deepseek_v4",
    title: "DeepSeek V4 Copilot",
    modelLabel: "deepseek-v4-pro",
    description: "DeepSeek Pro route prepared for Claude Agent SDK compatibility.",
    sdkId: "claude-agent-sdk",
    source: "built_in",
    fallbackEnabled: false,
    activeRouteIds: ["deepseek-official:deepseek-v4-pro", "ark-official:deepseek-v4-pro-260425", "qiniu-anthropic:deepseek-v4-pro"],
    availableRoutes: [
      {
        id: "deepseek-official:deepseek-v4-pro",
        provider: "DeepSeek Official",
        modelId: "deepseek-v4-pro",
        endpoint: "https://api.deepseek.com/anthropic",
        methodId: "deepseek_anthropic_messages",
        adapter: "DeepSeek Anthropic",
        providerApiStatus: "ready",
        agentStatus: "ready",
        capabilities: ["text", "read", "edit"],
      },
      {
        id: "ark-official:deepseek-v4-pro-260425",
        provider: "Ark Official",
        modelId: "deepseek-v4-pro-260425",
        endpoint: "https://ark.cn-beijing.volces.com/api/compatible",
        methodId: "ark_anthropic_messages",
        adapter: "Ark Anthropic",
        providerApiStatus: "ready",
        agentStatus: "ready",
        capabilities: ["text", "read", "edit"],
      },
      {
        id: "qiniu-anthropic:deepseek-v4-pro",
        provider: "Qiniu Anthropic",
        modelId: "deepseek/deepseek-v4-pro",
        endpoint: "https://ai.qiniuapi.com/v1",
        methodId: "anthropic_messages",
        adapter: "Standard Anthropic",
        providerApiStatus: "ready",
        agentStatus: "not_tested",
        capabilities: ["text", "read"],
      },
      {
        id: "qiniu-openai:deepseek-v4-pro",
        provider: "Qiniu OpenAI",
        modelId: "deepseek/deepseek-v4-pro",
        endpoint: "https://openai.qnaigc.com/v1",
        methodId: "openai_chat_completions",
        adapter: "Not available",
        providerApiStatus: "ready",
        agentStatus: "unsupported",
        capabilities: ["provider api"],
        note: "Provider API is ready, but this route does not satisfy Claude Agent SDK runtime requirements.",
      },
    ],
  },
  {
    id: "sonnet-4-7-third-party",
    title: "Claude Sonnet 4.7 Copilot",
    modelLabel: "claude-sonnet-4-7",
    description: "Third-party Anthropic-compatible Sonnet route group.",
    sdkId: "claude-agent-sdk",
    source: "third_party",
    fallbackEnabled: false,
    activeRouteIds: [
      "qiniu-anthropic-sonnet-4-7",
      "onechats-anthropic-sonnet-4-7",
      "openrouter-sonnet-4-7",
    ],
    availableRoutes: [
      {
        id: "qiniu-anthropic-sonnet-4-7",
        provider: "Qiniu Anthropic",
        modelId: "claude-sonnet-4-7",
        endpoint: "https://ai.qiniuapi.com/v1",
        methodId: "anthropic_messages",
        adapter: "Standard Anthropic",
        providerApiStatus: "ready",
        agentStatus: "not_tested",
        capabilities: ["text", "read"],
      },
      {
        id: "onechats-anthropic-sonnet-4-7",
        provider: "OneChats Anthropic",
        modelId: "anthropic/claude-sonnet-4-7",
        endpoint: "https://chatapi.onechats.ai/anthropic",
        methodId: "anthropic_messages",
        adapter: "Standard Anthropic",
        providerApiStatus: "ready",
        agentStatus: "not_tested",
        capabilities: ["text", "read"],
      },
      {
        id: "openrouter-sonnet-4-7",
        provider: "OpenRouter",
        modelId: "anthropic/claude-sonnet-4-7",
        endpoint: "https://openrouter.ai/api/v1",
        methodId: "openai_chat_completions",
        adapter: "Not available",
        providerApiStatus: "ready",
        agentStatus: "unsupported",
        capabilities: ["provider api"],
        note: "Filtered out because this route does not expose an Anthropic-compatible method.",
      },
    ],
  },
  {
    id: "openrouter-only-claude",
    title: "OpenRouter Claude Copilot",
    modelLabel: "anthropic/claude-opus-4-7",
    description: "Provider API route without a Claude Agent SDK-compatible method.",
    sdkId: "claude-agent-sdk",
    source: "third_party",
    fallbackEnabled: false,
    activeRouteIds: ["openrouter-only-claude-opus"],
    availableRoutes: [
      {
        id: "openrouter-only-claude-opus",
        provider: "OpenRouter",
        modelId: "anthropic/claude-opus-4-7",
        endpoint: "https://openrouter.ai/api/v1",
        methodId: "openai_chat_completions",
        adapter: "Not available",
        providerApiStatus: "ready",
        agentStatus: "unsupported",
        capabilities: ["provider api"],
        note: "Hidden from Claude Agent SDK model selection until an Anthropic-compatible method is verified.",
      },
    ],
  },
]

import type { ModelGroup, CredentialsState, ProviderModelOption } from "@/api/llm"

export function buildCopilotRolesFromRealData(
  modelGroups: ModelGroup[],
  credentials: CredentialsState,
): CopilotRolePreview[] {
  const isCompatibleRoute = (pm: ProviderModelOption) => {
    const provider = credentials.providers.find((p) => p.id === pm.endpoint_id)
    if (!provider) return false
    return provider.provider_type === "anthropic" || provider.provider_type === "anthropic_compatible"
  }

  return modelGroups
    .filter((group) => {
      return group.provider_models.some(isCompatibleRoute)
    })
    .map((group): CopilotRolePreview => {
      const isOpus47 = group.canonical_id === "claude-opus-4.7" || group.canonical_id === "claude-opus-4-7"
      const isBuiltIn = isOpus47 || group.canonical_id === "deepseek-v4-pro"

      const availableRoutes: CopilotRoutePreview[] = group.provider_models
          .filter((pm) => pm.ui_state !== "off" && pm.ui_state !== "failed")
          .map((pm): CopilotRoutePreview => {
            let agentStatus: CopilotAgentStatus = "not_tested"
            if (pm.ui_state === "ready") agentStatus = "ready"

            let methodId = "anthropic_messages"
            if (pm.provider_label.toLowerCase().includes("deepseek")) {
              methodId = "deepseek_anthropic_messages"
            } else if (pm.provider_label.toLowerCase().includes("ark")) {
              methodId = "ark_anthropic_messages"
            }

            return {
              id: pm.route_id,
              provider: pm.provider_label,
              modelId: pm.provider_model_id,
              endpoint: pm.ui_detail || "",
              methodId: methodId,
              adapter: pm.provider_label.toLowerCase().includes("deepseek") ? "DeepSeek Anthropic" : "Standard Anthropic",
              providerApiStatus: "ready" as const,
              agentStatus: agentStatus,
              capabilities: Object.keys(pm.capabilities),
            }
          })

      let title = group.display_name || group.canonical_id
      if (isOpus47) title = "Opus 4.7 Copilot"
      if (group.canonical_id === "deepseek-v4-pro") title = "DeepSeek V4 Copilot"
      if (group.canonical_id === "claude-sonnet-4-7" || group.canonical_id === "claude-sonnet-4.7") title = "Claude Sonnet 4.7 Copilot"

      return {
        id: group.canonical_id,
        title: title,
        modelLabel: group.canonical_id,
        description: `Coding copilot role for ${group.display_name}.`,
        sdkId: "claude-agent-sdk" as const,
        source: isBuiltIn ? ("built_in" as const) : ("third_party" as const),
        fallbackEnabled: false,
        activeRouteIds: availableRoutes.map((r) => r.id),
        availableRoutes: availableRoutes,
      }
    })
}

export const defaultCopilotCredentials: CredentialsState = {
  providers: [
    {
      id: "anthropic-official",
      name: "Anthropic Official",
      api_key: "sk-anthropic",
      provider_type: "anthropic",
      last_test_status: "ok",
    },
    {
      id: "deepseek-official",
      name: "DeepSeek Official",
      api_key: "sk-deepseek",
      provider_type: "anthropic_compatible",
      last_test_status: "ok",
    },
    {
      id: "ark-official",
      name: "Ark Official",
      api_key: "sk-ark",
      provider_type: "anthropic_compatible",
      last_test_status: "ok",
    },
    {
      id: "qiniu-anthropic",
      name: "Qiniu Anthropic",
      api_key: "sk-qiniu",
      provider_type: "anthropic_compatible",
      last_test_status: "ok",
    },
  ],
}

export const defaultCopilotModelGroups: ModelGroup[] = [
  {
    canonical_id: "claude-opus-4-7",
    display_name: "Claude Opus 4.7",
    provider_models: [
      {
        route_id: "anthropic-official:claude-opus-4-7",
        endpoint_id: "anthropic-official",
        provider_label: "Anthropic Official",
        provider_kind: "official",
        provider_model_id: "claude-opus-4-7",
        ui_state: "ready",
        capability_state: "known",
        capabilities: { text: { value: true, source: "probed_verified" } },
      },
      {
        route_id: "qiniu-anthropic:claude-opus-4-7",
        endpoint_id: "qiniu-anthropic",
        provider_label: "Qiniu Anthropic",
        provider_kind: "third_party",
        provider_model_id: "claude-opus-4-7",
        ui_state: "untested",
        capability_state: "unknown",
        capabilities: {},
      },
    ],
    status_summary: { ready: 1, historical_ready: 0, untested: 1, failed: 0, cooling_down: 0, off: 0 },
    capability_summary: {
      capability_known_count: 1,
      thinking: "supported",
      tools: "unknown",
      structured_output: "unknown",
    },
  },
  {
    canonical_id: "deepseek-v4-pro",
    display_name: "DeepSeek V4 Pro",
    provider_models: [
      {
        route_id: "deepseek-official:deepseek-v4-pro",
        endpoint_id: "deepseek-official",
        provider_label: "DeepSeek Official",
        provider_kind: "official",
        provider_model_id: "deepseek-v4-pro",
        ui_state: "ready",
        capability_state: "known",
        capabilities: { text: { value: true, source: "probed_verified" } },
      },
      {
        route_id: "ark-official:deepseek-v4-pro-260425",
        endpoint_id: "ark-official",
        provider_label: "Ark Official",
        provider_kind: "official",
        provider_model_id: "deepseek-v4-pro-260425",
        ui_state: "ready",
        capability_state: "known",
        capabilities: { text: { value: true, source: "probed_verified" } },
      },
      {
        route_id: "qiniu-anthropic:deepseek-v4-pro",
        endpoint_id: "qiniu-anthropic",
        provider_label: "Qiniu Anthropic",
        provider_kind: "third_party",
        provider_model_id: "deepseek-v4-pro",
        ui_state: "untested",
        capability_state: "unknown",
        capabilities: {},
      },
    ],
    status_summary: { ready: 2, historical_ready: 0, untested: 1, failed: 0, cooling_down: 0, off: 0 },
    capability_summary: {
      capability_known_count: 2,
      thinking: "supported",
      tools: "unknown",
      structured_output: "unknown",
    },
  },
]
