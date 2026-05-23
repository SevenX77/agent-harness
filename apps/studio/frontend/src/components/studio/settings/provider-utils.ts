import type { CredentialProviderState, CredentialsState, ProviderTestResult, ProviderType } from "../../../api/llm"
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
const notableProviderKeys = [
  ...officialProviderCodes,
  "openrouter",
  "wavespeed",
  "qiniu",
  "onechats",
  "jiekou",
]

type ProviderTestParams = {
  api_key?: string | null
  base_url?: string | null
  provider_type?: ProviderType | null
}

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

export function inferProviderType(providerCode: string, baseUrl = "", name = ""): ProviderType {
  const haystack = `${providerCode} ${name} ${baseUrl}`.toLowerCase()
  if (haystack.includes("anthropic") || haystack.includes("claude")) return "anthropic_compatible"
  if (haystack.includes("gemini") || haystack.includes("google")) return "google_genai"
  return "openai_compatible"
}

export function inferProviderKind(draft: ProviderDraft): "official" | "third-party" {
  if (officialProviderCodes.some((code) => isOfficialProviderDraft(draft, code))) return "official"
  return "third-party"
}

export function draftFromAddProviderSubmission(
  data: AddProviderFormSubmission,
  id: string = data.providerCode || newProviderId(),
): ProviderDraft {
  return {
    id,
    name: data.name,
    provider_type: inferProviderType(data.providerCode, data.baseUrl, data.name),
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
  const haystack = `${draft.id} ${draft.name} ${draft.base_url}`.toLowerCase()
  const matched = notableProviderKeys.find((code) => haystack.includes(code))
  if (matched) return matched
  if (draft.provider_type === "anthropic_compatible") return "anthropic"
  if (draft.provider_type === "google_genai") return "gemini"
  return "openai"
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

export function providerTestParamsMatch(
  left: ProviderTestParams,
  right: ProviderTestParams,
): boolean {
  return (
    (left.api_key ?? "") === (right.api_key ?? "") &&
    (left.base_url ?? "") === (right.base_url ?? "") &&
    (left.provider_type ?? null) === (right.provider_type ?? null)
  )
}

export function providerTestParamsFingerprint(params: ProviderTestParams): string {
  return fnv1a32(JSON.stringify({
    api_key: params.api_key ?? "",
    base_url: params.base_url ?? "",
    provider_type: params.provider_type ?? null,
  }))
}

export function providerCachedTestResult(
  persisted: CredentialProviderState | null,
  params: ProviderTestParams,
): ProviderTestResult | null {
  if (!persisted) return null
  const fingerprint = providerTestParamsFingerprint(params)
  const results = persisted.test_results ?? []
  for (let index = results.length - 1; index >= 0; index -= 1) {
    if (results[index].params_fingerprint === fingerprint) return results[index]
  }
  return null
}

function fnv1a32(value: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, "0")
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
