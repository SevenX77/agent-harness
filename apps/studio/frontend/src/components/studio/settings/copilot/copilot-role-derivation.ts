import type { CredentialsState, ModelGroup, RoleEntry, RolesData } from '@/api/llm'

export interface CopilotRoutePreview {
  id: string
  route_id: string
  endpointId: string
  providerLabel: string
  providerKind: string
  providerModelId: string
  uiState: string
  agentStatus: string
  capabilities: Record<string, unknown>
  provider: string
  modelId: string
  methodId?: string | null
  note?: string | null
}

export interface CopilotRolePreview {
  id: string
  title: string
  description: string
  source: 'built_in' | 'third_party'
  modelLabel: string
  sdkId: 'claude-agent-sdk'
  activeRouteIds: string[]
  availableRoutes: CopilotRoutePreview[]
  routes: CopilotRoutePreview[]
}

/**
 * 派生出符合 Copilot 协议的候选模型组列表
 */
export function deriveCopilotCandidateGroups(
  modelGroups: ModelGroup[],
  credentials: CredentialsState,
): CopilotRolePreview[] {
  const anthropicProviderIds = new Set(
    (credentials?.providers || [])
      .filter((p) => p.provider_type === 'anthropic_compatible')
      .map((p) => p.id)
  )

  const candidates = (modelGroups || []).map((group) => {
    const availableRoutes: CopilotRoutePreview[] = (group.provider_models || [])
      .filter((pm) => pm.endpoint_id && anthropicProviderIds.has(pm.endpoint_id))
      .map((pm) => ({
        id: pm.route_id,
        route_id: pm.route_id,
        endpointId: pm.endpoint_id || '',
        providerLabel: pm.provider_label,
        providerKind: pm.provider_kind || 'official',
        providerModelId: pm.provider_model_id,
        uiState: pm.ui_state,
        agentStatus: pm.ui_state,
        capabilities: pm.capabilities || {},
        provider: pm.provider_label,
        modelId: pm.provider_model_id,
        methodId: (pm as unknown as Record<string, unknown>).call_method_id as string | null || null,
        note: (pm as unknown as Record<string, unknown>).note as string | null || null,
      }))

    const activeRouteIds = availableRoutes.filter((r) => r.uiState === 'ready').map((r) => r.id)

    // Title + description come from the normalized canonical display_name — no
    // family-name heuristic (spec §3.2: never branch on display_name.includes('Claude')).
    return {
      id: group.canonical_id,
      title: group.display_name,
      description: group.display_name,
      source: 'third_party' as const, // resolved below against the floated default set
      modelLabel: group.display_name,
      sdkId: 'claude-agent-sdk' as const,
      activeRouteIds,
      availableRoutes,
      routes: availableRoutes,
    }
  }).filter((r) => r.availableRoutes.length > 0)

  // Built-in detection is the SAME canonical-id truth as the dynamic float
  // (spec §3.2 / atom-55/56): a group is built_in iff it is one the system would
  // float by family ladder. pickDefaultCopilotGroupIds is the single source.
  const floatedDefaultIds = new Set(pickDefaultCopilotGroupIds(candidates))
  return candidates.map((candidate) => ({
    ...candidate,
    source: floatedDefaultIds.has(candidate.id) ? ('built_in' as const) : ('third_party' as const),
  }))
}

/**
 * 在候选组中挑选默认激活的模型组 ID
 */
export function pickDefaultCopilotGroupIds(candidates: CopilotRolePreview[]): string[] {
  const ids = candidates.map((c) => c.id)
  const defaults: string[] = []

  // Claude 优先级
  if (ids.includes('claude-opus-4.8')) {
    defaults.push('claude-opus-4.8')
  } else if (ids.includes('claude-opus-4.7')) {
    defaults.push('claude-opus-4.7')
  }

  // DeepSeek 优先级
  if (ids.includes('deepseek-v4-pro')) {
    defaults.push('deepseek-v4-pro')
  } else if (ids.includes('deepseek-v3.2-pro')) {
    defaults.push('deepseek-v3.2-pro')
  }

  return defaults
}

/**
 * Materialize a candidate/floated group into a persistable copilot RoleEntry.
 *
 * Used both when a floated built-in default is first acted on (it enters the
 * save chain only on user action, per atom-56 ①) and as the base shape for a
 * selected group. The default fallback chain is the group's ready routes.
 */
export function buildCopilotRoleEntry(group: CopilotRolePreview): RoleEntry {
  const readyRouteIds = group.availableRoutes.filter((route) => route.uiState === 'ready').map((route) => route.id)
  return {
    role_kind: 'copilot',
    system_prompt_prefix: '',
    model_fallback_enabled: true,
    intent: { provider_preference: 'manual_order' },
    model_groups: [],
    active_model: group.id,
    models: {
      [group.id]: { providers: readyRouteIds },
    },
    fallback_chain: readyRouteIds.map((routeId) => ({ route_id: routeId, runtime_settings: {} })),
  }
}

/**
 * 选组保留 copilot_ 前缀
 */
export function applyCopilotModelGroupSelection(
  roles: RolesData,
  roleId: string,
  modelGroupId: string,
  availableRoutes: CopilotRoutePreview[] = [],
): RolesData {
  if (!roles || !roles.roles) return roles
  const nextRoles = JSON.parse(JSON.stringify(roles.roles))
  const role = nextRoles[roleId]
  if (!role) return roles

  const defaultRouteIds = availableRoutes
    .filter((r) => r.uiState === 'ready')
    .map((r) => r.id)

  nextRoles[roleId] = {
    ...role,
    role_kind: 'copilot',
    active_model: modelGroupId,
    fallback_chain: defaultRouteIds.map((routeId) => ({
      route_id: routeId,
      runtime_settings: {},
    })),
    models: {
      [modelGroupId]: {
        providers: defaultRouteIds,
      },
    },
  }

  return {
    ...roles,
    roles: nextRoles,
  }
}
