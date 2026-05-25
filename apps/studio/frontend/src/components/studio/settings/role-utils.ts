import type { ModelProfile, ProviderRoute, RegistryResponse, RoleEntry } from "@/api/llm"

export interface AvailableRouteGroup {
  canonical_id: string
  display_name: string
  routes: ProviderRoute[]
}

export function createEmptyRole(): RoleEntry {
  return {
    system_prompt_prefix: "",
    fallback_chain: [],
    lint_requirements: {},
  }
}

export function appendRouteToRole(role: RoleEntry, routeId: string): RoleEntry {
  if (role.fallback_chain.some((entry) => entry.route_id === routeId)) {
    return role
  }
  return {
    ...role,
    fallback_chain: [...role.fallback_chain, { route_id: routeId }],
  }
}

export function removeRouteFromRole(role: RoleEntry, routeId: string): RoleEntry {
  return {
    ...role,
    fallback_chain: role.fallback_chain.filter((entry) => entry.route_id !== routeId),
  }
}

export function moveRouteInRole(role: RoleEntry, fromIndex: number, toIndex: number): RoleEntry {
  if (
    fromIndex === toIndex ||
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= role.fallback_chain.length ||
    toIndex >= role.fallback_chain.length
  ) {
    return role
  }

  const next = [...role.fallback_chain]
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  return { ...role, fallback_chain: next }
}

export function updateRolePrefix(role: RoleEntry, systemPromptPrefix: string): RoleEntry {
  return { ...role, system_prompt_prefix: systemPromptPrefix }
}

export function updateRoleLintRequirement(
  role: RoleEntry,
  capability: string,
  severity: RoleEntry["lint_requirements"][string],
): RoleEntry {
  return {
    ...role,
    lint_requirements: {
      ...role.lint_requirements,
      [capability]: severity,
    },
  }
}

export function applyProfileToRole(role: RoleEntry, profile: ModelProfile): RoleEntry {
  return {
    ...role,
    source_profile_id: profile.model_profile_id,
    source_profile_snapshot: {
      model_profile_id: profile.model_profile_id,
      display_name: profile.display_name,
      canonical_id: profile.canonical_id ?? null,
      tags: [...profile.tags],
      fallback_chain: profile.fallback_chain.map((entry) => ({ ...entry })),
      lint_requirements: { ...profile.lint_requirements },
    },
    fallback_chain: profile.fallback_chain.map((entry) => ({ ...entry })),
    lint_requirements: { ...profile.lint_requirements },
  }
}

export function groupAvailableRoutes(registry: RegistryResponse): AvailableRouteGroup[] {
  return registry.canonical_groups.map((group) => ({
    ...group,
    routes: group.routes
      .map((routeId) => registry.provider_routes[routeId])
      .filter((route): route is ProviderRoute => Boolean(route)),
  }))
}

export function routeDisplayName(route: ProviderRoute | undefined, routeId: string): string {
  return route?.display_name || route?.provider_model_id || routeId
}
