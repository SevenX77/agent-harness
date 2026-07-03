import type {
  CredentialsState,
  ModelGroup,
  ProviderModelOption,
  RoleEntry,
  RoleRouteEntry,
  RolesData,
} from '@/api/llm'

/**
 * R-F8: an eligible copilot route is one whose backend `call_method_id` is in
 * the Anthropic-messages family — i.e. the route can actually be driven by
 * ClaudeSDKClient. The old heuristic (`endpoint.provider_type ===
 * 'anthropic_compatible'`) missed ark-official + deepseek-official + openrouter
 * routes whose endpoints expose multiple call methods including
 * anthropic-messages but live behind a non-`anthropic_compatible` provider type.
 *
 * The whitelist mirrors the backend method_id set used by the gateway resolver
 * + copilot test orchestrator.
 */
export const COPILOT_ANTHROPIC_MESSAGES_METHODS = [
  'anthropic_messages',
  'ark_anthropic_messages',
  'deepseek_anthropic_messages',
  'openrouter_anthropic_messages',
] as const

export function routeSupportsAnthropicMessages(pm: ProviderModelOption): boolean {
  const m = (pm as { call_method_id?: string | null }).call_method_id
  if (typeof m !== 'string') return false
  return (COPILOT_ANTHROPIC_MESSAGES_METHODS as readonly string[]).includes(m)
}

// 从 base_url 取 host 做 route 消歧标签(同一 provider 多 endpoint 靠 host 区分)。
export function hostFromBaseUrl(baseUrl: string | null | undefined): string | null {
  const value = (baseUrl ?? '').trim()
  if (!value) return null
  try {
    return new URL(value).host || null
  } catch {
    return value.replace(/^https?:\/\//i, '').split('/')[0] || null
  }
}

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
  // 消歧标签:同一个 provider(如"七牛")下有多条不同 host/协议的 endpoint,光看
  // providerLabel 全一样分不清 → 追加 host 区分(如 "七牛 · api.qnaigc.com")。
  endpointLabel: string
  // tooltip 用:该 route 端点的协议 + host(从 credentials 查真实 base_url)。
  protocol: string | null
  baseUrlHost: string | null
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

export interface CopilotDisplayRole {
  id: string
  title: string
  description: string
  source: 'built_in' | 'third_party'
  modelGroupId: string
  fallback_chain: RoleRouteEntry[]
}

/**
 * 派生出符合 Copilot 协议的候选模型组列表
 */
export function deriveCopilotCandidateGroups(
  modelGroups: ModelGroup[],
  credentials: CredentialsState,
): CopilotRolePreview[] {
  // R-F8: only keep routes whose `call_method_id` is in the anthropic-messages
  // family (i.e. ClaudeSDKClient can drive them). The old heuristic — filter
  // by `endpoint.provider_type === 'anthropic_compatible'` — missed ark /
  // deepseek / openrouter routes that expose anthropic-messages under a
  // different provider_type.
  // credentials 用来把每条 route 的端点真实 base_url / 协议查出来做消歧标签(同 provider
  // 多 host 时光看 providerLabel 分不清)。
  const endpointById = new Map(credentials.providers.map((provider) => [provider.id, provider]))

  const candidates = (modelGroups || []).map((group) => {
    const availableRoutes: CopilotRoutePreview[] = (group.provider_models || [])
      .filter((pm) => routeSupportsAnthropicMessages(pm))
      .map((pm) => {
        const endpointId = pm.endpoint_id || ''
        const endpoint = endpointById.get(endpointId)
        const host = hostFromBaseUrl(endpoint?.base_url ?? endpoint?.runtime_base_url ?? null)
        const protocol = endpoint?.provider_type ?? null
        return {
          id: pm.route_id,
          route_id: pm.route_id,
          endpointId,
          providerLabel: pm.provider_label,
          providerKind: pm.provider_kind || 'official',
          providerModelId: pm.provider_model_id,
          uiState: pm.ui_state,
          agentStatus: pm.ui_state,
          capabilities: pm.capabilities || {},
          provider: pm.provider_label,
          modelId: pm.provider_model_id,
          methodId: pm.call_method_id ?? null,
          note: (pm as unknown as Record<string, unknown>).note as string | null || null,
          endpointLabel: host ? `${pm.provider_label} · ${host}` : pm.provider_label,
          protocol,
          baseUrlHost: host,
        }
      })

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

export function copilotRoleTitleFromName(roleName: string): string {
  return roleName.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}

export function isBrokenLegacyCopilotRole(role: RoleEntry): boolean {
  // MVP1 §3.1: a copilot role must bind to one model group. A record with no
  // model binding but a populated fallback_chain is a stale pre-translator role;
  // Settings hides it, so other consumers must not offer it as selectable.
  const hasModelsProjection = Object.keys(role.models ?? {}).length > 0
  const hasModelGroups = (role.model_groups ?? []).length > 0
  const hasFallbackChain = (role.fallback_chain ?? []).length > 0
  return !hasModelsProjection && !hasModelGroups && hasFallbackChain
}

export function deriveActiveCopilotRoles(
  data: RolesData | null,
  realCopilotRoles: CopilotRolePreview[],
  allModelGroups: ModelGroup[] = [],
): CopilotDisplayRole[] {
  // Titles come from the FULL group list: a copilot role may bind any model
  // group (the sidebar is not pre-filtered by SDK compatibility, spec 2.5),
  // so a non-anthropic-eligible group still labels by its display_name —
  // exactly what the Settings cards show.
  const groupTitles = new Map(allModelGroups.map((group) => [group.canonical_id, group.display_name]))
  return data
    ? Object.entries(data.roles)
        .filter(([, role]) => role.role_kind === 'copilot')
        .filter(([, role]) => !isBrokenLegacyCopilotRole(role))
        .map(([name, role]) => {
          const activeModelGroupId = Object.keys(role.models ?? {})[0] || role.active_model || name
          const modelGroup = realCopilotRoles.find((candidate) => candidate.id === activeModelGroupId)
          const fallbackChainRoutes =
            role.models?.[activeModelGroupId]?.providers ??
            role.fallback_chain?.map((entry) => entry.route_id) ??
            []

          return {
            id: name,
            title: modelGroup?.title ?? groupTitles.get(activeModelGroupId) ?? copilotRoleTitleFromName(name),
            description: modelGroup?.description ?? 'Coding copilot role.',
            source: modelGroup?.source ?? ('third_party' as const),
            modelGroupId: activeModelGroupId,
            fallback_chain: fallbackChainRoutes.map((routeId) => ({ route_id: routeId, runtime_settings: {} })),
          }
        })
    : []
}

export function deriveFloatedCopilotRoles(
  realCopilotRoles: CopilotRolePreview[],
): CopilotDisplayRole[] {
  return pickDefaultCopilotGroupIds(realCopilotRoles)
    .map((id) => realCopilotRoles.find((candidate) => candidate.id === id))
    .filter((group): group is CopilotRolePreview => Boolean(group))
    .map((group) => ({
      id: group.id,
      title: group.title,
      description: group.description,
      source: group.source,
      modelGroupId: group.id,
      fallback_chain: buildCopilotRoleEntry(group).fallback_chain ?? [],
    }))
}

export function deriveCopilotDisplayRolesFromCandidates(
  data: RolesData | null,
  realCopilotRoles: CopilotRolePreview[],
  allModelGroups: ModelGroup[] = [],
): CopilotDisplayRole[] {
  const activeRoles = deriveActiveCopilotRoles(data, realCopilotRoles, allModelGroups)
  return activeRoles.length > 0 ? activeRoles : deriveFloatedCopilotRoles(realCopilotRoles)
}

export function deriveCopilotDisplayRoles(
  data: RolesData | null,
  modelGroups: ModelGroup[],
  credentials: CredentialsState,
): CopilotDisplayRole[] {
  return deriveCopilotDisplayRolesFromCandidates(
    data,
    deriveCopilotCandidateGroups(modelGroups, credentials),
    modelGroups,
  )
}

/**
 * Materialize a candidate/floated group into a persistable copilot RoleEntry.
 *
 * Used both when a floated built-in default is first acted on (it enters the
 * save chain only on user action, per atom-56 ①) and as the base shape for a
 * selected group. The default fallback chain is the group's ready routes.
 */
export function buildCopilotRoleEntry(group: CopilotRolePreview): RoleEntry {
  // R-F4 / spec §3.2 #3: include ALL eligible routes (already filtered by
  // anthropic-messages capability upstream), not just `ui_state === 'ready'`.
  // Untested/failed routes must still be in the chain so Test can drive them.
  const allRouteIds = group.availableRoutes.map((route) => route.id)
  return {
    role_kind: 'copilot',
    system_prompt_prefix: '',
    model_fallback_enabled: true,
    intent: { provider_preference: 'manual_order' },
    model_groups: [],
    active_model: group.id,
    models: {
      [group.id]: { providers: allRouteIds },
    },
    fallback_chain: allRouteIds.map((routeId) => ({ route_id: routeId, runtime_settings: {} })),
  }
}

/**
 * R-F5: derive a yaml-safe key for a copilot role created from a model group.
 * The yaml key must match `[a-z][a-z0-9_]*` (no hyphens, no dots, no upper).
 * `copilot_<slug>` where slug strips any non-[a-zA-Z0-9] run to `_` and lowercases.
 */
export function copilotKeyForGroupId(groupId: string): string {
  return "copilot_" + groupId.replace(/[^a-zA-Z0-9]+/g, "_").toLowerCase()
}

export interface CopilotSendRoleResolution {
  /** Role key to send over the chat websocket (always a persisted yaml key when resolvable). */
  roleKey: string
  /** Roles snapshot to persist BEFORE sending, or null when nothing needs materializing. */
  nextRoles: RolesData | null
}

/**
 * F3 (docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md): resolve the role
 * key for a chat send. A floated built-in option (rendered, not persisted —
 * atom-56) materializes into `copilot_<slug>` through the same
 * buildCopilotRoleEntry path Settings uses: first use IS the act-on-it moment.
 */
export function resolveCopilotSendRole(
  data: RolesData,
  option: { role: string; persisted: boolean; modelGroupId: string },
  modelGroups: ModelGroup[],
  credentials: CredentialsState = { providers: [] },
): CopilotSendRoleResolution {
  if (option.persisted || data.roles[option.role]) {
    return { roleKey: option.role, nextRoles: null }
  }
  const persistedKey = copilotKeyForGroupId(option.role)
  if (data.roles[persistedKey]) {
    return { roleKey: persistedKey, nextRoles: null }
  }
  const group = deriveCopilotCandidateGroups(modelGroups, credentials)
    .find((candidate) => candidate.id === option.modelGroupId)
  if (!group) {
    return { roleKey: option.role, nextRoles: null }
  }
  return {
    roleKey: persistedKey,
    nextRoles: { ...data, roles: { ...data.roles, [persistedKey]: buildCopilotRoleEntry(group) } },
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

  // R-F4: include ALL eligible routes (anthropic-messages capable), not just
  // ready ones. Untested/failed routes must enter the chain so Test can run
  // them. Spec §3.2 #3 (`00_settings-ux-spec.md:201-202`): never pre-filter
  // by `uiState === 'ready'` on the derivation side.
  const defaultRouteIds = availableRoutes.map((r) => r.id)

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
