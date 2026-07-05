import type { CredentialProviderState, CredentialsState, ProviderTestResult, ProviderType } from "../../../api/llm"
import type { AddProviderFormSubmission } from "../api-keys"
import type { ProviderDraft } from "./types"

type OfficialEndpointDefinition = {
  id: string
  provider_type: ProviderType
  baseUrl: string
}

type OfficialProviderDefinition = {
  code: string
  label: string
  baseUrl: string
  endpoints: OfficialEndpointDefinition[]
}

const officialProviders = [
  {
    code: "anthropic",
    label: "Anthropic",
    baseUrl: "https://api.anthropic.com",
    endpoints: [{ id: "anthropic-official", provider_type: "anthropic_compatible", baseUrl: "https://api.anthropic.com" }],
  },
  {
    code: "openai",
    label: "OpenAI",
    baseUrl: "https://api.openai.com",
    endpoints: [{ id: "openai-official", provider_type: "openai_compatible", baseUrl: "https://api.openai.com" }],
  },
  {
    code: "gemini",
    label: "Gemini",
    baseUrl: "https://generativelanguage.googleapis.com",
    endpoints: [{ id: "gemini-official", provider_type: "google_genai", baseUrl: "https://generativelanguage.googleapis.com" }],
  },
  {
    code: "deepseek",
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com",
    endpoints: [{ id: "deepseek-official", provider_type: "openai_compatible", baseUrl: "https://api.deepseek.com" }],
  },
  {
    code: "ark",
    label: "Ark",
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    endpoints: [
      { id: "ark-official", provider_type: "ark_runtime", baseUrl: "https://ark.cn-beijing.volces.com/api/v3" },
      { id: "ark-openai-official", provider_type: "openai_compatible", baseUrl: "https://ark.cn-beijing.volces.com/api/v3" },
    ],
  },
] satisfies OfficialProviderDefinition[]
const officialProviderCodes = officialProviders.map((vendor) => vendor.code)
export const thirdPartyProtocolCandidates: ProviderType[] = [
  "openai_compatible",
  "anthropic_compatible",
  "google_genai",
]
const notableProviderKeys = [
  "openrouter",
  "wavespeed",
  "qiniu",
  "onechats",
  "jiekou",
  ...officialProviderCodes,
]

type ProviderTestParams = {
  api_key?: string | null
  base_url?: string | null
  provider_type?: ProviderType | null
}

type BaseUrlDraftRow = NonNullable<ProviderDraft["base_urls"]>[number]

/** Build a draft list from the server `CredentialsState` snapshot. */
export function draftsFromCredentials(credentials: CredentialsState): ProviderDraft[] {
  const drafts: ProviderDraft[] = []
  const thirdPartyGroups = new Map<string, CredentialProviderState[]>()

  for (const provider of credentials.providers) {
    const draft = providerDraftFromCredential(provider)
    if (inferProviderKind(draft) === "official") {
      drafts.push(draft)
      continue
    }
    const groupKey = thirdPartyGroupKey(provider)
    thirdPartyGroups.set(groupKey, [...(thirdPartyGroups.get(groupKey) ?? []), provider])
  }

  for (const providers of thirdPartyGroups.values()) {
    const [primary] = providers
    if (!primary) continue
    const baseUrls = baseUrlRowsFromCredentialProviders(providers)
    drafts.push({
      ...providerDraftFromCredential(primary),
      base_url: baseUrls[0]?.value ?? "",
      base_urls: baseUrls,
    })
  }

  return drafts
}

let providerIdFallbackCounter = 0

function newProviderId(): string {
  const uuid = globalThis.crypto?.randomUUID?.()
  if (uuid) return uuid
  providerIdFallbackCounter += 1
  return `${Date.now()}-${providerIdFallbackCounter}`
}

export function inferProviderType(providerCode: string, baseUrl = "", name = ""): ProviderType {
  const normalizedProviderCode = providerCode.toLowerCase()
  const normalizedName = name.toLowerCase()
  const normalizedBaseUrl = baseUrl.toLowerCase()
  const isOfficialArk = (
    normalizedProviderCode === "ark" ||
    normalizedProviderCode === "ark-official" ||
    normalizedProviderCode === "ark_official" ||
    (normalizedName.includes("ark official") && normalizedBaseUrl.includes("volces"))
  )
  if (isOfficialArk) return "ark_runtime"
  const haystack = `${normalizedProviderCode} ${normalizedName} ${normalizedBaseUrl}`
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
  const submittedBaseUrls = (data.baseUrls?.length ? data.baseUrls : [data.baseUrl]).map((value) => value.trim())
  const baseUrls = submittedBaseUrls.some(Boolean) ? submittedBaseUrls.filter(Boolean) : [""]
  const baseUrl = baseUrls[0] ?? ""
  const providerType = inferProviderType(data.providerCode, baseUrl, data.name)
  const baseUrlRows: NonNullable<ProviderDraft["base_urls"]> = baseUrls.map((value, index) => {
    const rowId = index === 0 ? id : `${id}-url-${index + 1}`
    return {
      id: rowId,
      value,
      provider_type: providerType,
      endpoint_ids: { [providerType]: rowId },
    }
  })
  return {
    id,
    name: data.name,
    provider_type: providerType,
    base_url: baseUrl,
    base_urls: baseUrlRows,
    api_key: data.apiKey,
    isTesting: false,
    testingAction: null,
  }
}

export function blankThirdPartyProviderDraft(id: string = `custom-${newProviderId()}`): ProviderDraft {
  return {
    id,
    name: "",
    provider_type: "openai_compatible",
    base_url: "",
    base_urls: [{
      id,
      value: "",
      provider_type: "openai_compatible",
      endpoint_ids: { openai_compatible: id },
    }],
    api_key: "",
    isTesting: false,
    testingAction: null,
  }
}

export function officialProviderDrafts(drafts: ProviderDraft[]): ProviderDraft[] {
  return officialProviders.map((vendor) => {
    const existing = drafts.filter((draft) => isOfficialProviderDraft(draft, vendor.code))
    const primaryEndpoint = officialEndpointDefinitions(vendor)[0]
    const primary = existing.find((draft) => draft.id === primaryEndpoint.id) ?? existing[0]
    if (primary) return withOfficialProviderDefaults(primary, vendor)
    return {
      id: primaryEndpoint.id,
      name: `${officialProviderDisplayName(vendor.label)} Official`,
      provider_type: primaryEndpoint.provider_type,
      base_url: primaryEndpoint.baseUrl,
      api_key: "",
      isTesting: false,
      testingAction: null,
    }
  })
}

export function providerDraftForAction(drafts: ProviderDraft[], providerId: string): ProviderDraft | null {
  const draft = drafts.find((item) => item.id === providerId)
    ?? officialProviderDrafts(drafts).find((item) => item.id === providerId)
  if (!draft) return null
  const vendor = officialProviderForDraft(draft)
  return vendor ? withOfficialProviderDefaults(draft, vendor) : draft
}

export function providerEndpointDraftsForAction(draft: ProviderDraft): ProviderDraft[] {
  const officialVendor = officialProviderForDraft(draft)
  if (officialVendor) {
    return officialEndpointDefinitions(officialVendor).map((endpoint) => ({
      ...draft,
      id: endpoint.id,
      provider_type: endpoint.provider_type,
      base_url: endpoint.baseUrl,
      base_urls: undefined,
    }))
  }
  const rows = draft.base_urls?.length
    ? draft.base_urls.filter((row) => row.value.trim().length > 0)
    : [{ id: draft.id, value: draft.base_url, provider_type: draft.provider_type, endpoint_ids: { [draft.provider_type]: draft.id } }]
  const effectiveRows = rows.length > 0 ? rows : [{ id: draft.id, value: draft.base_url }]
  return effectiveRows.flatMap((row) => {
    return thirdPartyProtocolCandidates.map((protocol) => ({
      ...draft,
      id: endpointIdForBaseUrlProtocol(draft.id, row, protocol),
      provider_type: protocol,
      base_url: row.value,
      base_urls: [{ ...row, provider_type: protocol }],
    }))
  })
}

export function endpointIdForBaseUrlProtocol(
  providerId: string,
  row: { id: string; endpoint_ids?: Partial<Record<ProviderType, string>> },
  protocol: ProviderType,
): string {
  const existing = row.endpoint_ids?.[protocol]
  if (existing) return existing
  const suffix = providerTypeEndpointSuffix(protocol)
  const baseId = row.id || providerId
  return `${baseId}-${suffix}`
}

export function thirdPartyProviderDrafts(drafts: ProviderDraft[]): ProviderDraft[] {
  return drafts.filter((draft) => inferProviderKind(draft) === "third-party")
}

export function notableProviderKeyForDraft(draft: ProviderDraft): string {
  const haystack = `${draft.id} ${draft.name} ${draft.base_url}`.toLowerCase()
  const matched = notableProviderKeys.find((code) => haystack.includes(code))
  if (matched) return matched
  if (draft.provider_type === "anthropic_compatible") return "anthropic"
  if (draft.provider_type === "ark_runtime") return "ark"
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
  const baseUrl = normalizeBaseUrlForProviderMatch(draft.base_url)
  const vendorBaseUrl = normalizeBaseUrlForProviderMatch(vendor?.baseUrl ?? "")
  return (
    normalizedId === providerCode ||
    normalizedId === `${providerCode}-official` ||
    normalizedId === `${providerCode}_official` ||
    (
      normalizedName.includes(label) &&
      normalizedName.includes("official") &&
      (!vendorBaseUrl || baseUrl === vendorBaseUrl)
    )
  )
}

function officialProviderForDraft(draft: ProviderDraft): (typeof officialProviders)[number] | null {
  return officialProviders.find((vendor) => isOfficialProviderDraft(draft, vendor.code)) ?? null
}

function withOfficialProviderDefaults(
  draft: ProviderDraft,
  vendor: (typeof officialProviders)[number],
): ProviderDraft {
  const primaryEndpoint = officialEndpointDefinitions(vendor)[0]
  return {
    ...draft,
    provider_type: primaryEndpoint.provider_type,
    base_url: primaryEndpoint.baseUrl,
    base_urls: undefined,
  }
}

function officialEndpointDefinitions(
  vendor: (typeof officialProviders)[number],
): OfficialEndpointDefinition[] {
  return vendor.endpoints
}

function officialProviderDisplayName(label: string): string {
  return label.replace(/\s*\(.+\)\s*$/, "")
}

function normalizeBaseUrlForProviderMatch(value: string): string {
  return value.trim().replace(/\/+$/, "").toLowerCase()
}

function normalizeBaseUrlGroupKey(value: string): string {
  return normalizeBaseUrlForProviderMatch(value).replace(/\/v1$/, "")
}

function baseUrlRowsFromCredentialProviders(providers: CredentialProviderState[]): BaseUrlDraftRow[] {
  const groups = new Map<string, CredentialProviderState[]>()
  for (const provider of providers) {
    const key = normalizeBaseUrlGroupKey(provider.base_url ?? "")
    groups.set(key, [...(groups.get(key) ?? []), provider])
  }
  return [...groups.values()].map((group) => {
    const [primary] = group
    const endpointIds: Partial<Record<ProviderType, string>> = {}
    for (const provider of group) {
      const providerType = credentialProviderProtocolSlot(provider)
      if (!thirdPartyProtocolCandidates.includes(providerType)) continue
      endpointIds[providerType] ??= provider.id
    }
    const primaryType = primary ? credentialProviderProtocolSlot(primary) : "openai_compatible"
    return {
      id: primary?.id ?? "",
      value: primary?.base_url ?? "",
      provider_type: primaryType,
      endpoint_ids: endpointIds,
    }
  })
}

function providerTypeEndpointSuffix(providerType: ProviderType): string {
  if (providerType === "openai_compatible") return "openai"
  if (providerType === "anthropic_compatible") return "anthropic"
  if (providerType === "google_genai") return "google"
  return "ark"
}

function credentialProviderProtocolSlot(provider: CredentialProviderState): ProviderType {
  // Design §1.2 protocol matrix (2026-07-02): the persisted `provider_type` is
  // the single protocol truth. Endpoint ids are opaque — the old slug sniffing
  // ("-openai-" in the id => openai slot) was a second protocol writer that
  // fought the backend and rendered self-contradictory cards.
  return (provider.provider_type ?? "openai_compatible") as ProviderType
}

function providerDraftFromCredential(provider: CredentialProviderState): ProviderDraft {
  return {
    id: provider.id,
    name: provider.name,
    provider_type: credentialProviderProtocolSlot(provider),
    base_url: provider.base_url ?? "",
    api_key: provider.api_key,
    isTesting: false,
    testingAction: null,
  }
}

/**
 * Stable provider IDENTITY for a draft, independent of its (unstable) id.
 *
 * A freshly-added third-party provider draft carries a locally-minted id
 * (`custom-<uuid>`), but once saved the backend keys its per-protocol endpoints
 * by `<id>-<protocol>`, so `draftsFromCredentials` rebuilds the draft under the
 * primary endpoint's id — a DIFFERENT string. Matching drafts by id alone then
 * fails to recognise the just-saved provider, so reconcile keeps BOTH copies
 * (the duplicate-card bug). Identity mirrors `thirdPartyGroupKey` (name +
 * api_key) for third-party providers and the stable code for official ones, so
 * the two copies collapse to one.
 */
export function providerDraftIdentityKey(draft: ProviderDraft): string {
  if (inferProviderKind(draft) === "official") return `official ${draft.id}`
  return `third ${draft.name.trim().toLowerCase()} ${draft.api_key}`
}

function thirdPartyGroupKey(provider: CredentialProviderState): string {
  return [
    provider.name.trim().toLowerCase(),
    provider.api_key,
  ].join("\u0000")
}
