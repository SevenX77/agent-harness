import type { CredentialsState, ModelGroup, ModelInfo, ProviderType, RoleIntent, RolesData } from "../../../api/llm"
import { endpointIdFromRouteId } from "./route-credentials"

type RoleProviderEntry = RolesData["providers"][string]

export const AVAILABLE_MODEL_DRAG_TYPE = "application/x-studio-available-model"

export function visibleRoleNames(data: RolesData): string[] {
  return Object.keys(data.roles).filter((roleName) => !roleName.startsWith("deerflow_"))
}

export function roleModelProviderCodes(
  data: RolesData,
  modelCode: string,
  providers: ReadonlyArray<string>,
  credentialsByCode?: Record<string, CredentialsState["providers"][number]>,
): string[] {
  const ownedProviderCodes = new Set(ownedProviderCodesForModel(data, modelCode, credentialsByCode))
  return providers.filter((providerCode) => ownedProviderCodes.has(providerCode))
}

export function ownedProviderCodesForModel(
  data: RolesData,
  modelCode: string,
  credentialsByCode?: Record<string, CredentialsState["providers"][number]>,
): string[] {
  const configProviderCodes = Object.keys(data.models[modelCode]?.providers ?? {})
    .filter((providerCode) => Boolean(data.providers[providerCode]))
  if (!credentialsByCode) return configProviderCodes
  const hasLegacyProviderCode = configProviderCodes.some((providerCode) => (
    !isRouteBackedProviderCode(data, providerCode)
  ))
  if (!hasLegacyProviderCode) return configProviderCodes

  const availableModelId = inferAvailableModelIdForModel(data, modelCode, credentialsByCode)
  if (!availableModelId) return configProviderCodes

  return configProviderCodes.filter((providerCode) => {
    if (isRouteBackedProviderCode(data, providerCode)) return true
    const credential = credentialsByCode[providerCode]
    if (!credential) return providerCode.includes(":")
    return credentialProviderOwnsModel(credential, availableModelId)
  })
}

export function pruneInvalidRoleProviders(
  data: RolesData,
  credentialsByCode?: Record<string, CredentialsState["providers"][number]>,
): RolesData {
  let changed = false
  const next = cloneRolesData(data)

  for (const [roleName, role] of Object.entries(next.roles)) {
    for (const [modelCode, roleModel] of Object.entries(role.models)) {
      if (credentialsByCode) {
        changed = ensureRoleProviderEntries(next, modelCode, roleModel.providers, credentialsByCode) || changed
      }
      const providers = roleModelProviderCodes(next, modelCode, roleModel.providers, credentialsByCode)
      if (providers.length !== roleModel.providers.length) {
        changed = true
        next.roles[roleName].models[modelCode] = { ...roleModel, providers }
      }
    }
  }

  return changed ? next : data
}

export function normalizeRolesDraft(data: RolesData): RolesData {
  let changed = false
  const next = cloneRolesData(data)

  for (const [roleName, role] of Object.entries(next.roles)) {
    const modelEntries = Object.entries(role.models).filter(([modelCode]) => Boolean(next.models[modelCode]))
    if (modelEntries.length !== Object.keys(role.models).length) {
      changed = true
      role.models = Object.fromEntries(modelEntries)
    }
    const modelCodes = Object.keys(role.models)
    const activeModel = role.active_model
    if (modelCodes.length === 0) {
      if (activeModel) {
        changed = true
        next.roles[roleName].active_model = ""
      }
    } else if (!activeModel || !role.models[activeModel] || !next.models[activeModel]) {
      changed = true
      next.roles[roleName].active_model = modelCodes[0]
    }
  }

  return changed ? next : data
}

export function appendRole(data: RolesData, roleName?: string): RolesData {
  const next = cloneRolesData(data)
  const requestedName = roleName?.trim() || "custom_role"
  const nextRoleName = nextAvailableName(Object.keys(next.roles), requestedName)

  next.roles[nextRoleName] = {
    model_fallback: true,
    active_model: "",
    models: {},
  }
  return next
}

export function renameRole(data: RolesData, roleName: string, nextRoleName: string): RolesData {
  const trimmedNextRoleName = nextRoleName.trim()
  if (!trimmedNextRoleName || roleName === trimmedNextRoleName) return data
  if (!data.roles[roleName] || data.roles[trimmedNextRoleName]) return data

  const next = cloneRolesData(data)
  next.roles = Object.fromEntries(
    Object.entries(next.roles).map(([currentRoleName, role]) => (
      currentRoleName === roleName ? [trimmedNextRoleName, role] : [currentRoleName, role]
    )),
  )
  if (next.single_model_roles) {
    next.single_model_roles = next.single_model_roles.map((singleRoleName) => (
      singleRoleName === roleName ? trimmedNextRoleName : singleRoleName
    ))
  }
  return next
}

export function removeRole(data: RolesData, roleName: string): RolesData {
  if (!data.roles[roleName]) return data

  const next = cloneRolesData(data)
  delete next.roles[roleName]

  if (next.single_model_roles) {
    next.single_model_roles = next.single_model_roles.filter((singleRoleName) => singleRoleName !== roleName)
  }

  if (next.peer_model_groups) {
    next.peer_model_groups = Object.fromEntries(
      Object.entries(next.peer_model_groups).map(([groupName, roleNames]) => [
        groupName,
        roleNames.filter((peerRoleName) => peerRoleName !== roleName),
      ]),
    )
  }

  return next
}

export function updateActiveModel(data: RolesData, roleName: string, activeModel: string): RolesData {
  const next = cloneRolesData(data)
  next.roles[roleName] = { ...next.roles[roleName], active_model: activeModel }
  return next
}

export function toggleModelFallback(data: RolesData, roleName: string, enabled: boolean): RolesData {
  const next = cloneRolesData(data)
  next.roles[roleName] = { ...next.roles[roleName], model_fallback: enabled }
  return next
}

export function updateRoleIntent(data: RolesData, roleName: string, intent: RoleIntent): RolesData {
  if (!data.roles[roleName]) return data
  const next = cloneRolesData(data)
  next.roles[roleName] = { ...next.roles[roleName], intent }
  return next
}

export function moveProviderInRole(
  data: RolesData,
  roleName: string,
  modelCode: string,
  providerIndex: number,
  direction: -1 | 1,
): RolesData {
  const next = cloneRolesData(data)
  const providers = [...next.roles[roleName].models[modelCode].providers]
  const targetIndex = providerIndex + direction
  if (targetIndex < 0 || targetIndex >= providers.length) return data
  ;[providers[providerIndex], providers[targetIndex]] = [providers[targetIndex], providers[providerIndex]]
  next.roles[roleName].models[modelCode] = {
    ...next.roles[roleName].models[modelCode],
    providers,
  }
  return next
}

export function reorderProviderInRole(
  data: RolesData,
  roleName: string,
  modelCode: string,
  fromIndex: number,
  toIndex: number,
): RolesData {
  const next = cloneRolesData(data)
  const providers = [...next.roles[roleName].models[modelCode].providers]
  if (fromIndex < 0 || toIndex < 0 || fromIndex >= providers.length || toIndex >= providers.length) return data
  const [moved] = providers.splice(fromIndex, 1)
  providers.splice(toIndex, 0, moved)
  next.roles[roleName].models[modelCode] = {
    ...next.roles[roleName].models[modelCode],
    providers,
  }
  return next
}

export function removeProviderFromRole(
  data: RolesData,
  roleName: string,
  modelCode: string,
  providerIndex: number,
): RolesData {
  const next = cloneRolesData(data)
  const providers = next.roles[roleName].models[modelCode].providers.filter((_, index) => index !== providerIndex)
  next.roles[roleName].models[modelCode] = {
    ...next.roles[roleName].models[modelCode],
    providers,
  }
  return next
}

export function appendProviderToModel(
  data: RolesData,
  roleName: string,
  modelCode: string,
  providerCode: string,
): RolesData {
  if (!data.models[modelCode]?.providers[providerCode] || !data.providers[providerCode]) return data
  const next = cloneRolesData(data)
  const roleModel = next.roles[roleName].models[modelCode]
  if (roleModel.providers.includes(providerCode)) return data
  roleModel.providers = [...roleModel.providers, providerCode]
  return next
}

export function updateRoleModelSettings(
  data: RolesData,
  roleName: string,
  modelCode: string,
  settings: { temperature: number | null; max_tokens: number | null },
): RolesData {
  const next = cloneRolesData(data)
  next.roles[roleName].models[modelCode] = {
    ...next.roles[roleName].models[modelCode],
    temperature: settings.temperature,
    max_tokens: settings.max_tokens,
  }
  return next
}

export function moveModelInRole(
  data: RolesData,
  roleName: string,
  modelCode: string,
  direction: -1 | 1,
): RolesData {
  const next = cloneRolesData(data)
  const entries = Object.entries(next.roles[roleName].models)
  const index = entries.findIndex(([code]) => code === modelCode)
  const targetIndex = index + direction
  if (index < 0 || targetIndex < 0 || targetIndex >= entries.length) return data
  ;[entries[index], entries[targetIndex]] = [entries[targetIndex], entries[index]]
  next.roles[roleName].models = Object.fromEntries(entries)
  syncActiveModelToFirst(next, roleName)
  return next
}

export function reorderModelInRole(
  data: RolesData,
  roleName: string,
  fromModelCode: string,
  toModelCode: string,
): RolesData {
  const next = cloneRolesData(data)
  const entries = Object.entries(next.roles[roleName].models)
  const fromIndex = entries.findIndex(([code]) => code === fromModelCode)
  const toIndex = entries.findIndex(([code]) => code === toModelCode)
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return data
  const [moved] = entries.splice(fromIndex, 1)
  entries.splice(toIndex, 0, moved)
  next.roles[roleName].models = Object.fromEntries(entries)
  syncActiveModelToFirst(next, roleName)
  return next
}

export function removeModelFromRole(data: RolesData, roleName: string, modelCode: string): RolesData {
  const next = cloneRolesData(data)
  const models = { ...next.roles[roleName].models }
  delete models[modelCode]
  next.roles[roleName] = { ...next.roles[roleName], models }
  syncActiveModelToFirst(next, roleName)
  return next
}

export function appendModelToRole(data: RolesData, roleName: string, modelCode: string): RolesData {
  const next = cloneRolesData(data)
  if (next.roles[roleName].models[modelCode]) return data
  const providerCodes = Object.keys(next.models[modelCode]?.providers ?? {})
    .filter((providerCode) => Boolean(next.providers[providerCode]))
  next.roles[roleName].models[modelCode] = { providers: providerCodes }
  if (!next.roles[roleName].active_model) {
    next.roles[roleName].active_model = modelCode
  }
  return next
}

export function appendAvailableModelToRole(
  data: RolesData,
  roleName: string,
  availableModelId: string,
  credentialsByCode: Record<string, CredentialsState["providers"][number]>,
): RolesData {
  const modelId = availableModelId.trim()
  if (!modelId) return data

  const availableModel = availableModelFromCredentials(modelId, credentialsByCode, data.providers)
  const providerCodes = Object.keys(availableModel.providers)
  if (providerCodes.length === 0) return data

  const next = cloneRolesData(data)
  for (const [providerCode, providerEntry] of Object.entries(availableModel.providerEntries)) {
    next.providers[providerCode] = next.providers[providerCode] ?? providerEntry
  }

  const modelCode = findModelCodeForAvailableModel(next, modelId, credentialsByCode) ??
    nextAvailableName(Object.keys(next.models), modelId)

  next.models[modelCode] = {
    ...next.models[modelCode],
    name: modelId,
    reasoning: availableModel.thinking || next.models[modelCode]?.reasoning || undefined,
    providers: availableModel.providers,
  }

  if (!next.roles[roleName].models[modelCode]) {
    next.roles[roleName].models[modelCode] = { providers: providerCodes }
  } else {
    next.roles[roleName].models[modelCode] = {
      ...next.roles[roleName].models[modelCode],
      providers: roleModelProviderCodes(
        next,
        modelCode,
        next.roles[roleName].models[modelCode].providers,
        credentialsByCode,
      ),
    }
  }

  syncActiveModelToFirst(next, roleName)
  return next
}

export function appendModelGroupToRole(
  data: RolesData,
  roleName: string,
  modelGroup: ModelGroup,
): RolesData {
  return appendModelGroupToRoleWithResult(data, roleName, modelGroup).data
}

export function appendModelGroupToRoleWithResult(
  data: RolesData,
  roleName: string,
  modelGroup: ModelGroup,
): { data: RolesData; error: string | null } {
  const modelLabel = modelGroup.display_name || modelGroup.canonical_id
  if (!data.roles[roleName]) {
    return {
      data,
      error: `Could not add ${modelLabel} to ${roleName}: role was not found.`,
    }
  }
  const selectedProviderModels = defaultProviderModelsForGroup(modelGroup)
  if (selectedProviderModels.length === 0) {
    return {
      data,
      error: `Could not add ${modelLabel} to ${roleName}: no provider routes are available.`,
    }
  }

  const next = cloneRolesData(data)
  const modelCode = modelGroup.canonical_id
  next.models[modelCode] = {
    ...next.models[modelCode],
    name: modelGroup.display_name || modelGroup.canonical_id,
    reasoning: modelGroupSupportsThinking(modelGroup) || next.models[modelCode]?.reasoning || undefined,
    providers: {
      ...(next.models[modelCode]?.providers ?? {}),
      ...Object.fromEntries(
        selectedProviderModels.map((providerModel) => [
          providerModel.route_id,
          providerModel.provider_model_id,
        ]),
      ),
    },
  }

  for (const providerModel of selectedProviderModels) {
    next.providers[providerModel.route_id] = next.providers[providerModel.route_id] ?? {
      name: providerModel.provider_label,
      type: "openai_compatible",
      endpoint_id: providerModel.endpoint_id ?? endpointIdFromRouteId(providerModel.route_id),
    }
  }

  const existingRoleModel = next.roles[roleName].models[modelCode]
  const providerIds = selectedProviderModels.map((providerModel) => providerModel.route_id)
  next.roles[roleName].models[modelCode] = existingRoleModel
    ? {
        ...existingRoleModel,
        providers: Array.from(new Set([...existingRoleModel.providers, ...providerIds])),
      }
    : { providers: providerIds }
  syncActiveModelToFirst(next, roleName)
  return { data: next, error: null }
}

export function modelDropFailureMessage({
  modelId,
  destination,
  reason,
}: {
  modelId: string
  destination: string
  reason: string
}): string {
  return `Could not add ${modelId} to ${destination}: ${reason}.`
}

export function canonicalAvailableModelId(
  modelId: string,
  provider: CredentialsState["providers"][number],
): string {
  const normalizedModelId = modelId.trim()
  if (providerVendor(provider) !== "openrouter") return normalizedModelId

  const withoutAliasPrefix = normalizedModelId.replace(/^~+/, "")
  const slashIndex = withoutAliasPrefix.indexOf("/")
  if (slashIndex > 0 && slashIndex < withoutAliasPrefix.length - 1) {
    return withoutAliasPrefix.slice(slashIndex + 1)
  }
  return withoutAliasPrefix
}

export function modelSupportsThinking(model: ModelInfo): boolean {
  const capabilities = model.capabilities ?? {}
  return Boolean(
    capabilities.thinking ||
    capabilities.reasoning ||
    capabilities.supports_thinking,
  )
}

function defaultProviderModelsForGroup(modelGroup: ModelGroup): ModelGroup["provider_models"] {
  return [...modelGroup.provider_models].sort((left, right) => (
    providerStateRank(left.ui_state) - providerStateRank(right.ui_state) ||
    providerKindRank(left.provider_kind) - providerKindRank(right.provider_kind) ||
    left.provider_label.localeCompare(right.provider_label, undefined, { numeric: true, sensitivity: "base" }) ||
    left.route_id.localeCompare(right.route_id)
  ))
}

function providerKindRank(kind: ModelGroup["provider_models"][number]["provider_kind"]): number {
  if (kind === "official") return 0
  if (kind === "custom") return 1
  return 2
}

function providerStateRank(state: ModelGroup["provider_models"][number]["ui_state"]): number {
  if (state === "ready") return 0
  if (state === "untested") return 1
  if (state === "cooling_down") return 2
  return 3
}

function modelGroupSupportsThinking(modelGroup: ModelGroup): boolean {
  return modelGroup.capability_summary.thinking === "supported" ||
    modelGroup.capability_summary.thinking === "mixed" ||
    modelGroup.provider_models.some((providerModel) => Boolean(
      providerModel.capabilities.thinking?.value ||
      providerModel.capabilities.reasoning?.value ||
      providerModel.capabilities.supports_thinking?.value,
    ))
}

export function validateRoleDraft(data: RolesData, roleName: string): string | null {
  const role = data.roles[roleName]
  if (!role) return "Role not found"
  const modelCodes = Object.keys(role.models)
  if (modelCodes.length === 0) return role.active_model ? "Empty role must not set an active model" : null
  if (!role.active_model || !role.models[role.active_model]) return "Active model must exist in this role"
  for (const modelCode of modelCodes) {
    const model = data.models[modelCode]
    if (!model) return `Model ${modelCode} is missing from models`
    if (role.models[modelCode].providers.length === 0) return `Model ${modelCode} must contain at least one provider`
    for (const providerCode of role.models[modelCode].providers) {
      if (!data.providers[providerCode]) return `Model ${modelCode} references unknown provider ${providerCode}`
      if (!model.providers[providerCode]) return `Model ${modelCode} provider ${providerCode} is missing from model provider mappings`
    }
  }
  return null
}

export function validateRolesDraft(data: RolesData): string | null {
  for (const roleName of Object.keys(data.roles)) {
    const error = validateRoleDraft(data, roleName)
    if (error) return `${roleName}: ${error}`
  }
  return null
}

function nextAvailableName(existingNames: string[], baseName: string): string {
  if (!existingNames.includes(baseName)) return baseName
  let index = 2
  while (existingNames.includes(`${baseName}_${index}`)) index += 1
  return `${baseName}_${index}`
}

function cloneRolesData(data: RolesData): RolesData {
  return structuredClone(data) as RolesData
}

function syncActiveModelToFirst(data: RolesData, roleName: string) {
  data.roles[roleName].active_model = Object.keys(data.roles[roleName].models)[0] ?? ""
}

function availableModelFromCredentials(
  modelId: string,
  credentialsByCode: Record<string, CredentialsState["providers"][number]>,
  existingProviders: RolesData["providers"],
): { providers: Record<string, string>; providerEntries: Record<string, RoleProviderEntry>; thinking: boolean } {
  const providers: Record<string, string> = {}
  const providerEntries: Record<string, RoleProviderEntry> = {}
  let thinking = false

  for (const provider of Object.values(credentialsByCode)) {
    for (const model of provider.available_models ?? []) {
      if (canonicalAvailableModelId(model.id, provider) !== modelId) continue
      const providerEntry = existingProviders[provider.id] ?? providerEntryFromCredential(provider)
      if (!providerEntry) continue
      providers[provider.id] = model.id.trim()
      providerEntries[provider.id] = providerEntry
      thinking = thinking || modelSupportsThinking(model)
    }
  }

  return { providers, providerEntries, thinking }
}

function providerEntryFromCredential(provider: CredentialsState["providers"][number]): RoleProviderEntry | null {
  const providerType = providerTypeFromCredential(provider)
  if (!providerType) return null
  const baseUrl = provider.base_url?.trim()
  return {
    name: provider.name.trim() || provider.id,
    type: providerType,
    ...(baseUrl ? { base_url: baseUrl } : {}),
  }
}

function ensureRoleProviderEntries(
  data: RolesData,
  modelCode: string,
  providerCodes: ReadonlyArray<string>,
  credentialsByCode: Record<string, CredentialsState["providers"][number]>,
): boolean {
  let changed = false
  const modelProviders = data.models[modelCode]?.providers ?? {}
  for (const providerCode of providerCodes) {
    if (data.providers[providerCode] || !modelProviders[providerCode]) continue
    const credential = credentialsByCode[providerCode]
    const providerEntry = credential ? providerEntryFromCredential(credential) : null
    if (!providerEntry) continue
    data.providers[providerCode] = providerEntry
    changed = true
  }
  return changed
}

function providerTypeFromCredential(provider: CredentialsState["providers"][number]): ProviderType | null {
  return normalizeProviderType(provider.provider_type) ??
    normalizeProviderType(provider.available_sdks?.[0]) ??
    normalizeProviderType(provider.test_results?.find((result) => result.provider_type)?.provider_type) ??
    null
}

function normalizeProviderType(value: unknown): ProviderType | null {
  if (
    value === "anthropic_compatible" ||
    value === "ark_runtime" ||
    value === "openai_compatible" ||
    value === "google_genai"
  ) {
    return value
  }
  return null
}

function findModelCodeForAvailableModel(
  data: RolesData,
  availableModelId: string,
  credentialsByCode: Record<string, CredentialsState["providers"][number]>,
): string | null {
  for (const [modelCode, model] of Object.entries(data.models)) {
    if (model.name.trim() === availableModelId) return modelCode
    const hasMatchingProviderModel = Object.entries(model.providers).some(([providerCode, providerModelId]) => {
      const provider = credentialsByCode[providerCode]
      if (!provider) return providerModelId.trim() === availableModelId
      return canonicalAvailableModelId(providerModelId, provider) === availableModelId
    })
    if (hasMatchingProviderModel) return modelCode
  }

  return null
}

function inferAvailableModelIdForModel(
  data: RolesData,
  modelCode: string,
  credentialsByCode: Record<string, CredentialsState["providers"][number]>,
): string | null {
  const model = data.models[modelCode]
  if (!model) return null

  const modelName = model.name.trim()
  if (modelName && Object.values(credentialsByCode).some((provider) => credentialProviderOwnsModel(provider, modelName))) {
    return modelName
  }

  const candidateCounts = new Map<string, number>()
  for (const [providerCode, providerModelId] of Object.entries(model.providers)) {
    const provider = credentialsByCode[providerCode]
    if (!provider) continue
    const candidateModelId = canonicalAvailableModelId(providerModelId, provider)
    if (!credentialProviderOwnsModel(provider, candidateModelId)) continue
    candidateCounts.set(candidateModelId, (candidateCounts.get(candidateModelId) ?? 0) + 1)
  }

  const sortedCandidates = [...candidateCounts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))

  return sortedCandidates[0]?.[0] ?? null
}

function credentialProviderOwnsModel(
  provider: CredentialsState["providers"][number] | undefined,
  availableModelId: string,
): boolean {
  if (!provider) return false
  return (provider.available_models ?? []).some((model) => (
    canonicalAvailableModelId(model.id, provider) === availableModelId
  ))
}

function isRouteBackedProviderCode(data: RolesData, providerCode: string): boolean {
  return providerCode.includes(":") || Boolean(data.providers[providerCode]?.endpoint_id)
}

function providerVendor(provider: CredentialsState["providers"][number]): string {
  const haystack = `${provider.id} ${provider.name} ${provider.base_url ?? ""}`.toLowerCase()
  const knownVendors = [
    "openai",
    "gemini",
    "deepseek",
    "anthropic",
    "ark",
    "openrouter",
    "wavespeed",
    "qiniu",
    "onechats",
    "jiekou",
  ]
  return knownVendors.find((vendor) => haystack.includes(vendor)) ?? normalizeVendor(provider.name || provider.id)
}

function normalizeVendor(vendor: string): string {
  return vendor.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "unknown"
}
