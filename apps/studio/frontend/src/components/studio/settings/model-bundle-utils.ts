import type {
  ModelBundleEntry,
  ModelGroup,
  RoleEntry,
  RoleModelGroup,
  RoleRouteEntry,
  RolesData,
} from "../../../api/llm"
import {
  appendModelGroupToRole,
  normalizeRolesDraft,
} from "./role-utils"

export function visibleModelBundleEntries(data: RolesData): Array<[string, ModelBundleEntry]> {
  return Object.entries(data.model_bundles ?? {})
    .filter((entry): entry is [string, ModelBundleEntry] => Boolean(entry[1]))
}

export function appendModelBundle(data: RolesData, displayName?: string): RolesData {
  const next = cloneRolesData(data)
  const requestedName = displayName?.trim() || "New Model Bundle"
  const bundleId = nextAvailableBundleId(Object.keys(next.model_bundles ?? {}), requestedName)
  next.model_bundles = {
    ...(next.model_bundles ?? {}),
    [bundleId]: {
      model_profile_id: bundleId,
      display_name: requestedName,
      canonical_id: `bundle:${bundleId}`,
      model_fallback_enabled: true,
      intent: { provider_preference: "manual_order", thinking: false },
      model_groups: [],
      fallback_chain: [],
      lint_requirements: {},
    },
  }
  return next
}

export function renameModelBundle(data: RolesData, bundleId: string, displayName: string): RolesData {
  const bundle = data.model_bundles?.[bundleId]
  const trimmedName = displayName.trim()
  if (!bundle || !trimmedName || bundle.display_name === trimmedName) return data
  const next = cloneRolesData(data)
  next.model_bundles = {
    ...(next.model_bundles ?? {}),
    [bundleId]: {
      ...bundle,
      display_name: trimmedName,
    },
  }
  return next
}

export function removeModelBundle(data: RolesData, bundleId: string): RolesData {
  if (!data.model_bundles?.[bundleId]) return data
  const next = cloneRolesData(data)
  const bundles = { ...(next.model_bundles ?? {}) }
  delete bundles[bundleId]
  next.model_bundles = bundles
  return next
}

export function appendModelGroupToBundle(
  data: RolesData,
  bundleId: string,
  modelGroup: ModelGroup,
): RolesData {
  const bundle = data.model_bundles?.[bundleId]
  if (!bundle) return data
  const roleName = bundleRoleName(bundleId)
  const bundleRoleData = rolesDataWithBundleRole(data, bundleId)
  const nextRoleData = appendModelGroupToRole(bundleRoleData, roleName, modelGroup)
  return commitBundleRoleData(data, bundleId, nextRoleData)
}

export function toggleBundleModelFallback(
  data: RolesData,
  bundleId: string,
  enabled: boolean,
): RolesData {
  const bundle = data.model_bundles?.[bundleId]
  if (!bundle) return data
  const next = cloneRolesData(data)
  next.model_bundles = {
    ...(next.model_bundles ?? {}),
    [bundleId]: {
      ...bundle,
      model_fallback_enabled: enabled,
      fallback_chain: flattenBundleRouteEntries({
        ...bundle,
        model_fallback_enabled: enabled,
      }),
    },
  }
  return next
}

export function updateBundleIntent(
  data: RolesData,
  bundleId: string,
  intent: NonNullable<RoleEntry["intent"]>,
): RolesData {
  const bundle = data.model_bundles?.[bundleId]
  if (!bundle) return data
  const next = cloneRolesData(data)
  next.model_bundles = {
    ...(next.model_bundles ?? {}),
    [bundleId]: {
      ...bundle,
      intent,
      fallback_chain: flattenBundleRouteEntries({ ...bundle, intent }),
    },
  }
  return next
}

export function rolesDataWithBundleRole(data: RolesData, bundleId: string): RolesData {
  const bundle = data.model_bundles?.[bundleId]
  if (!bundle) return data
  const roleName = bundleRoleName(bundleId)
  return normalizeRolesDraft(ensureBundleRoleMaps({
    ...data,
    roles: {
      ...data.roles,
      [roleName]: roleEntryFromBundle(bundle, bundleId),
    },
  }, bundle, bundleId))
}

export function commitBundleRoleData(
  data: RolesData,
  bundleId: string,
  nextRoleData: RolesData,
): RolesData {
  const bundle = data.model_bundles?.[bundleId]
  if (!bundle) return data
  const role = nextRoleData.roles[bundleRoleName(bundleId)]
  if (!role) return data
  const nextBundle = bundleFromRoleEntry(bundleId, bundle, role, nextRoleData)
  const next = cloneRolesData(data)
  next.models = nextRoleData.models
  next.providers = nextRoleData.providers
  next.model_bundles = {
    ...(next.model_bundles ?? {}),
    [bundleId]: nextBundle,
  }
  return next
}

export function bundleRoleName(bundleId: string): string {
  return `__bundle__${bundleId}`
}

export function routeIdsFromBundle(bundle: ModelBundleEntry): string[] {
  if (bundle.fallback_chain?.length) {
    return bundle.fallback_chain
      .map((entry) => entry.route_id)
      .filter(Boolean)
  }
  return flattenBundleRouteEntries(bundle).map((entry) => entry.route_id)
}

function roleEntryFromBundle(bundle: ModelBundleEntry, bundleId: string): RoleEntry {
  const modelGroups = modelGroupsFromBundle(bundle, bundleId)
  return {
    role_kind: "graph_agent",
    model_fallback_enabled: bundle.model_fallback_enabled ?? true,
    intent: bundle.intent ?? { provider_preference: "manual_order", thinking: false },
    active_model: modelGroups[0]?.canonical_id ?? "",
    models: Object.fromEntries(
      modelGroups.map((group) => [
        group.canonical_id,
        {
          providers: group.provider_models.map((providerModel) => providerModel.route_id),
        },
      ]),
    ),
    model_groups: modelGroups,
    fallback_chain: bundle.fallback_chain ?? [],
    lint_requirements: bundle.lint_requirements ?? {},
    materialization_report: bundle.materialization_report,
  }
}

function bundleFromRoleEntry(
  bundleId: string,
  bundle: ModelBundleEntry,
  role: RoleEntry,
  data: RolesData,
): ModelBundleEntry {
  const modelGroups = modelGroupsFromRoleEntry(role, data)
  const nextBundle = {
    ...bundle,
    model_profile_id: bundle.model_profile_id || bundleId,
    canonical_id: bundle.canonical_id || `bundle:${bundleId}`,
    model_fallback_enabled: role.model_fallback_enabled,
    intent: role.intent ?? bundle.intent ?? { provider_preference: "manual_order", thinking: false },
    model_groups: modelGroups,
    lint_requirements: role.lint_requirements ?? bundle.lint_requirements ?? {},
  }
  return {
    ...nextBundle,
    fallback_chain: flattenBundleRouteEntries(nextBundle),
  }
}

function modelGroupsFromBundle(bundle: ModelBundleEntry, bundleId: string): RoleModelGroup[] {
  if (bundle.model_groups?.length) return bundle.model_groups
  const routeIds = (bundle.fallback_chain ?? [])
    .map((entry) => entry.route_id)
    .filter(Boolean)
  if (routeIds.length === 0) return []
  return [{
    canonical_id: bundle.canonical_id || `bundle:${bundleId}`,
    display_name: bundle.display_name || bundleId,
    provider_models: routeIds.map((routeId) => ({ route_id: routeId })),
  }]
}

function ensureBundleRoleMaps(
  data: RolesData,
  bundle: ModelBundleEntry,
  bundleId: string,
): RolesData {
  const next = cloneRolesData(data)
  for (const group of modelGroupsFromBundle(bundle, bundleId)) {
    const providers = Object.fromEntries(
      group.provider_models.map((providerModel) => [providerModel.route_id, providerModel.route_id]),
    )
    next.models[group.canonical_id] = {
      ...next.models[group.canonical_id],
      name: next.models[group.canonical_id]?.name ?? group.display_name,
      providers: {
        ...(next.models[group.canonical_id]?.providers ?? {}),
        ...providers,
      },
    }
    for (const routeId of Object.keys(providers)) {
      next.providers[routeId] = next.providers[routeId] ?? {
        name: routeId,
        type: "openai_compatible",
      }
    }
  }
  return next
}

function modelGroupsFromRoleEntry(role: RoleEntry, data: RolesData): RoleModelGroup[] {
  return Object.entries(role.models).map(([modelCode, roleModel]) => ({
    canonical_id: modelCode,
    display_name: data.models[modelCode]?.name ?? modelCode,
    provider_models: roleModel.providers.map((routeId) => ({ route_id: routeId })),
  }))
}

function flattenBundleRouteEntries(bundle: ModelBundleEntry): RoleRouteEntry[] {
  const groups = bundle.model_fallback_enabled === false
    ? (bundle.model_groups ?? []).slice(0, 1)
    : bundle.model_groups ?? []
  return groups.flatMap((group) => (
    group.provider_models.map((providerModel) => ({ route_id: providerModel.route_id }))
  ))
}

function nextAvailableBundleId(existingIds: string[], displayName: string): string {
  const normalizedBase = displayName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "model_bundle"
  if (!existingIds.includes(normalizedBase)) return normalizedBase
  let index = 2
  while (existingIds.includes(`${normalizedBase}_${index}`)) index += 1
  return `${normalizedBase}_${index}`
}

function cloneRolesData(data: RolesData): RolesData {
  return structuredClone(data) as RolesData
}
