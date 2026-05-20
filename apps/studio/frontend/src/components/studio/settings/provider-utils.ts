import type { CredentialsState, ProviderType } from "../../../api/llm"
import type { AddProviderFormSubmission } from "../api-keys"
import type { ProviderDraft } from "./types"

const officialProviders = [
  { code: "anthropic", label: "Anthropic", baseUrl: "https://api.anthropic.com" },
  { code: "openai", label: "OpenAI", baseUrl: "https://api.openai.com" },
  { code: "gemini", label: "Gemini", baseUrl: "https://generativelanguage.googleapis.com" },
  { code: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com" },
  { code: "ark", label: "Ark", baseUrl: "https://ark.cn-beijing.volces.com/api/v3" },
]
const officialProviderCodes = officialProviders.map((vendor) => vendor.code)

/** Build a draft list from the server `CredentialsState` snapshot. */
export function draftsFromCredentials(credentials: CredentialsState): ProviderDraft[] {
  return credentials.providers.map((provider) => ({
    id: provider.id,
    name: provider.name,
    provider_type: (provider.provider_type ?? "openai_compatible") as ProviderType,
    base_url: provider.base_url ?? "",
    api_key: provider.api_key,
    isTesting: false,
  }))
}

function newProviderId(): string {
  return (globalThis.crypto?.randomUUID?.() ?? Date.now() + "-" + Math.random().toString(36).slice(2)).toString()
}

export function inferProviderType(providerCode: string): ProviderType {
  if (providerCode === "anthropic") return "anthropic_compatible"
  if (providerCode === "gemini") return "google_genai"
  return "openai_compatible"
}

export function inferProviderKind(draft: ProviderDraft): "official" | "third-party" {
  if (officialProviderCodes.some((code) => isOfficialProviderDraft(draft, code))) return "official"
  return "third-party"
}

export function draftFromAddProviderSubmission(
  data: AddProviderFormSubmission,
  id: string = newProviderId(),
): ProviderDraft {
  return {
    id,
    name: data.name,
    provider_type: "openai_compatible",
    base_url: data.baseUrl,
    api_key: data.apiKey,
    isTesting: false,
  }
}

export function officialProviderDrafts(drafts: ProviderDraft[]): ProviderDraft[] {
  return officialProviders.map((vendor) => {
    const existing = drafts.find((draft) => isOfficialProviderDraft(draft, vendor.code))
    if (existing) return existing
    return {
      id: `${vendor.code}-official`,
      name: `${officialProviderDisplayName(vendor.label)} Official`,
      provider_type: inferProviderType(vendor.code),
      base_url: vendor.baseUrl,
      api_key: "",
      isTesting: false,
    }
  })
}

export function thirdPartyProviderDrafts(drafts: ProviderDraft[]): ProviderDraft[] {
  return drafts.filter((draft) => inferProviderKind(draft) === "third-party")
}

export function notableProviderKeyForDraft(draft: ProviderDraft): string {
  const officialCode = officialProviderCodes.find((code) => isOfficialProviderDraft(draft, code))
  if (officialCode) return officialCode
  return draft.id.split(/[-_]/, 1)[0].toLowerCase()
}

export function shouldShowManualModelPanel(
  draft: ProviderDraft,
  persisted: CredentialsState["providers"][number] | null,
): boolean {
  return (
    inferProviderKind(draft) === "official" ||
    persisted?.last_test_status === "ok" ||
    (persisted?.available_models?.length ?? 0) > 0
  )
}

function isOfficialProviderDraft(draft: ProviderDraft, providerCode: string): boolean {
  const normalizedId = draft.id.toLowerCase()
  const normalizedName = draft.name.toLowerCase()
  const vendor = officialProviders.find((item) => item.code === providerCode)
  const label = vendor ? officialProviderDisplayName(vendor.label).toLowerCase() : providerCode
  return (
    normalizedId === providerCode ||
    normalizedId.startsWith(`${providerCode}-`) ||
    normalizedId.startsWith(`${providerCode}_`) ||
    (normalizedName.includes(label) && normalizedName.includes("official"))
  )
}

function officialProviderDisplayName(label: string): string {
  return label.replace(/\s*\(.+\)\s*$/, "")
}
