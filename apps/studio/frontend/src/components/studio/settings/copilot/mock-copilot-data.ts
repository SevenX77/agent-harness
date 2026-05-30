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

export const initialClaudeCopilotRoleIds = ["opus-4-7", "deepseek-v4"] as const

export const mockCopilotRoles: CopilotRolePreview[] = [
  {
    id: "opus-4-7",
    title: "Opus 4.7 Copilot",
    modelLabel: "claude-opus-4-7",
    description: "Default high-quality coding copilot role.",
    sdkId: "claude-agent-sdk",
    source: "built_in",
    fallbackEnabled: false,
    activeRouteIds: ["anthropic-opus-4-7", "qiniu-anthropic-opus-4-7"],
    availableRoutes: [
      {
        id: "anthropic-opus-4-7",
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
        id: "qiniu-anthropic-opus-4-7",
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
        id: "openrouter-opus-4-7",
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
    id: "deepseek-v4",
    title: "DeepSeek V4 Copilot",
    modelLabel: "deepseek-v4-pro",
    description: "DeepSeek Pro route prepared for Claude Agent SDK compatibility.",
    sdkId: "claude-agent-sdk",
    source: "built_in",
    fallbackEnabled: false,
    activeRouteIds: ["deepseek-official-v4-pro", "ark-v4-pro", "qiniu-anthropic-v4-pro"],
    availableRoutes: [
      {
        id: "deepseek-official-v4-pro",
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
        id: "ark-v4-pro",
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
        id: "qiniu-anthropic-v4-pro",
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
        id: "qiniu-openai-v4-pro",
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
