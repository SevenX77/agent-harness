import type { RolesData } from "../../../api/llm"

export function visibleRoleNames(data: RolesData): string[] {
  return Object.keys(data.roles).filter((roleName) => !roleName.startsWith("deerflow_"))
}

export function appendRole(data: RolesData): RolesData {
  const next = cloneRolesData(data)
  const roleName = nextAvailableName(Object.keys(next.roles), "custom_role")
  const firstModelCode = Object.keys(next.models)[0] ?? ""
  const models = firstModelCode
    ? {
      [firstModelCode]: {
        providers: Object.keys(next.models[firstModelCode]?.providers ?? {}),
        temperature: null,
        max_tokens: null,
      },
    }
    : {}

  next.roles[roleName] = {
    model_fallback: true,
    active_model: firstModelCode,
    models,
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
  return next
}

export function removeModelFromRole(data: RolesData, roleName: string, modelCode: string): RolesData {
  const next = cloneRolesData(data)
  const models = { ...next.roles[roleName].models }
  delete models[modelCode]
  const activeModel = next.roles[roleName].active_model === modelCode ? Object.keys(models)[0] ?? "" : next.roles[roleName].active_model
  next.roles[roleName] = { ...next.roles[roleName], models, active_model: activeModel }
  return next
}

export function appendModelToRole(data: RolesData, roleName: string, modelCode: string): RolesData {
  const next = cloneRolesData(data)
  if (next.roles[roleName].models[modelCode]) return data
  const providerCodes = Object.keys(next.models[modelCode]?.providers ?? {})
  next.roles[roleName].models[modelCode] = { providers: providerCodes }
  if (!next.roles[roleName].active_model) {
    next.roles[roleName].active_model = modelCode
  }
  return next
}

export function validateRoleDraft(data: RolesData, roleName: string): string | null {
  const role = data.roles[roleName]
  if (!role) return "Role not found"
  const modelCodes = Object.keys(role.models)
  if (modelCodes.length === 0) return "Role must contain at least one model"
  if (!role.active_model || !role.models[role.active_model]) return "Active model must exist in this role"
  for (const modelCode of modelCodes) {
    if (role.models[modelCode].providers.length === 0) return `Model ${modelCode} must contain at least one provider`
  }
  return null
}

export function validateRolesDraft(data: RolesData): string | null {
  for (const roleName of visibleRoleNames(data)) {
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
