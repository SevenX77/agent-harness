import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { CircleAlert, CircleHelp, FlaskConical, Loader2, Plus, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { useDeleteConfirm } from "@/components/ui/delete-confirm-dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import { SectionTitle } from "../shared"
import { AvailableModelsSidebar } from "../llm-roles/AvailableModelsSidebar"
import { missingRecommendedModels, modelDropFailureMessage, normalizeModelGroupKey } from "../role-utils"
import {
  AvailableModelDragPreview,
  handleAvailableModelDragOver,
  readAvailableModelDropId,
  useAvailableModelPointerDrag,
} from "../available-model-pointer-drag"
import { agentStatusForRoute, CopilotModelGroupCard } from "./CopilotModelGroupCard"
import {
  deriveCopilotCandidateGroups,
  hostFromBaseUrl,
  applyCopilotModelGroupSelection,
  buildCopilotRoleEntry,
  configuredCopilotRouteIds,
  copilotKeyForGroupId,
  orderCopilotDisplayRoles,
  pickDefaultCopilotGroupIds,
  routeSupportsCopilotSdk,
  type CopilotRolePreview,
  type CopilotRoutePreview,
} from "./copilot-role-derivation"
import {
  copilotRoleTestErrorMessage,
  copilotRouteCooldownsFromJob,
  copilotRouteCooldownsFromPersistedResult,
  copilotRouteMessagesFromJob,
  copilotRouteMessagesFromPersistedResult,
  copilotRouteStatusesFromJob,
  copilotRouteStatusesFromPersistedResult,
  runCopilotRoleTestJob,
  type CopilotRouteJobStatus,
} from "./copilot-role-test"
import { Skeleton } from "@/components/ui/skeleton"
import { getRoleTestResults } from "@/api/client"
import { getFixedRoleNames, getFixedRoleStatus } from "@/api/llm"
import type { CredentialsState, FixedRoleRecommendedModel, ModelGroup, ProviderModelOption, RolesData } from "@/api/llm"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"

/**
 * R-F5: resolve the persisted yaml key for a UI role id. Floated built-in
 * defaults are rendered with the model-group id as their UI id, but persist
 * under `copilot_<slug>`. All write paths (remove/reorder/delete/test) MUST
 * go through this helper so UI and yaml stay consistent.
 */
export function resolvePersistedKey(data: RolesData | null, roleId: string): string {
  if (data?.roles?.[roleId]) return roleId
  return copilotKeyForGroupId(roleId)
}

/**
 * R-F5: derive the next `copilot_custom_N` id by taking `max(existing N) + 1`
 * rather than `count + 1`. Prevents collision when a middle id was deleted
 * (e.g. _1, _3 present → next is _4, not _3 which would overwrite).
 */
/**
 * R-F6: pure helper that rebuilds a role's fallback_chain in the new order
 * while keeping per-route `runtime_settings` (e.g. `max_tokens`, `model_id`
 * written back by the materializer). Routes new to the chain default to `{}`.
 * Extracted so it can be unit-tested independently of the React component.
 */
export function rebuildFallbackChainPreservingRuntime(
  existingChain: ReadonlyArray<{ route_id: string; runtime_settings?: Record<string, unknown> }>,
  nextOrder: readonly string[],
): Array<{ route_id: string; runtime_settings: Record<string, unknown> }> {
  const prevByRouteId = new Map(
    existingChain.map((entry) => [entry.route_id, entry.runtime_settings ?? {}]),
  )
  return nextOrder.map((routeId) => ({
    route_id: routeId,
    runtime_settings: prevByRouteId.get(routeId) ?? {},
  }))
}

export function nextCopilotCustomIndex(roleIds: readonly string[]): number {
  const prefix = "copilot_custom_"
  const existing = roleIds
    .filter((k) => k.startsWith(prefix))
    .map((k) => Number.parseInt(k.slice(prefix.length), 10))
    .filter((n) => Number.isFinite(n))
  if (existing.length === 0) return 1
  return Math.max(...existing) + 1
}

export function copilotBackendReadyCount(
  routes: Array<Pick<CopilotRoutePreview, "agentStatus" | "id">>,
  routeStatusOverrides: Record<string, CopilotRouteJobStatus> = {},
): number {
  // atom-57: the N/M ready badge must agree with the route lights, so it counts
  // the *effective* per-route status (real SDK verdict — live or persisted-seeded —
  // over the backend ui_state) via the same projection as the light, not the raw
  // ui_state. A persisted/live 'ready' lights and counts a route; an 'unsupported'
  // verdict knocks a ui_state='ready' route back out.
  return routes.filter(
    (route) => agentStatusForRoute(route.agentStatus, route.id, routeStatusOverrides) === "ready",
  ).length
}

type CopilotEndpointMeta = { base_url?: string; runtime_base_url?: string; provider_type?: string | null }

function copilotRoutePreviewFromProviderModel(
  pm: ProviderModelOption,
  endpointById: ReadonlyMap<string, CopilotEndpointMeta>,
): CopilotRoutePreview {
  const endpoint = endpointById.get(pm.endpoint_id || "")
  const host = hostFromBaseUrl(endpoint?.base_url ?? endpoint?.runtime_base_url ?? null)
  return {
    id: pm.route_id,
    route_id: pm.route_id,
    endpointId: pm.endpoint_id || "",
    providerLabel: pm.provider_label,
    providerKind: pm.provider_kind || "official",
    providerModelId: pm.provider_model_id,
    uiState: pm.ui_state,
    agentStatus: pm.ui_state,
    capabilities: pm.capabilities || {},
    provider: pm.provider_label,
    modelId: pm.provider_model_id,
    methodId: pm.call_method_id ?? null,
    candidateMethodIds: pm.candidate_call_method_ids ?? [],
    copilotSdkCompatible: pm.copilot_sdk_compatible,
    note: (pm as unknown as Record<string, unknown>).note as string | null || null,
    // 同 provider 多 endpoint 靠 host 消歧(如"七牛 · api.qnaigc.com"),host 拿不到才退回 provider_label。
    endpointLabel: host ? `${pm.provider_label} · ${host}` : pm.provider_label,
    protocol: endpoint?.provider_type ?? null,
    baseUrlHost: host,
  }
}

function copilotPreviewFromModelGroup(
  group: ModelGroup,
  source: "built_in" | "third_party",
  endpointById: ReadonlyMap<string, CopilotEndpointMeta>,
): CopilotRolePreview {
  const availableRoutes = (group.provider_models || []).map((pm) =>
    copilotRoutePreviewFromProviderModel(pm, endpointById),
  )
  return {
    id: group.canonical_id,
    title: group.display_name,
    description: group.display_name,
    source,
    modelLabel: group.display_name,
    sdkId: "claude-agent-sdk",
    activeRouteIds: availableRoutes.filter((route) => route.uiState === "ready").map((route) => route.id),
    availableRoutes,
    routes: availableRoutes,
  }
}

export function CopilotTab({
  data = null,
  credentials = { providers: [] },
  modelGroups = [],
  onChange = () => {},
  saveStatus = "idle",
  error = null,
  onDeleteRole,
  onBeforeRoleTest,
  onNavigateToApiKeys,
}: {
  data?: RolesData | null
  credentials?: CredentialsState
  modelGroups?: ModelGroup[]
  onChange?: (next: RolesData) => void
  saveStatus?: SaveStatus
  error?: string | null
  /**
   * R-F3: real DELETE /api/llm/roles/{id} endpoint. Replaces the old
   * `onChange(...delete key...)` + PUT (which the backend treated as additive
   * merge and could never actually remove a key from yaml).
   */
  onDeleteRole?: (roleId: string) => Promise<void> | void
  /**
   * R-F7: awaited before any Test run so a debounced roles-save flushes to the
   * gateway snapshot first. Without this, Test fires against a stale yaml and
   * may report `no_available_route` on a route the user just added.
   */
  onBeforeRoleTest?: () => Promise<unknown> | unknown
  /**
   * R-F12: callback to jump to the API Keys tab from the empty-state CTA
   * ("Go configure Anthropic-compatible credentials") and the per-card
   * "N routes untested" warning chip.
   */
  onNavigateToApiKeys?: () => void
} = {}) {
  const { t } = useTranslation("settings")
  const { confirm: confirmDelete, dialog: deleteDialog } = useDeleteConfirm()

  const realCopilotRoles = useMemo(() => {
    return deriveCopilotCandidateGroups(modelGroups, credentials)
  }, [modelGroups, credentials])

  const claudeModelGroups = realCopilotRoles
  const realCopilotRolesById = useMemo(
    () => new Map(realCopilotRoles.map((candidate) => [candidate.id, candidate])),
    [realCopilotRoles],
  )
  // 端点 → base_url/协议,给每条 route 的消歧标签("七牛 · <host>")用。
  const endpointById = useMemo<ReadonlyMap<string, CopilotEndpointMeta>>(
    () => new Map(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )
  const allModelGroupPreviews = useMemo<CopilotRolePreview[]>(() => (
    modelGroups.map((group) => copilotPreviewFromModelGroup(
      group,
      realCopilotRolesById.get(group.canonical_id)?.source ?? "third_party",
      endpointById,
    ))
  ), [modelGroups, realCopilotRolesById, endpointById])
  const allModelGroupPreviewsById = useMemo(
    () => new Map(allModelGroupPreviews.map((group) => [group.id, group])),
    [allModelGroupPreviews],
  )

  const activeRoles = useMemo(() => {
    return data
      ? Object.entries(data.roles)
          .filter(([, role]) => role.role_kind === "copilot")
          .filter(([, role]) => {
            // MVP1 §3.1: a copilot role MUST bind to one model group. The wire
            // shape is `model_groups: list` (backend v3); the FE projection adds
            // `models{}` (api/llm.ts `roleEntryFromBackend`). A copilot record
            // with NO group binding (both `models{}` and `model_groups[]` empty)
            // AND a populated `fallback_chain` is a legacy/broken pre-translator
            // entry — skip it so `activeRoles` stays empty and #56 float defaults
            // take over (no EmptyCard fallback for stale data, no manual select).
            // An "Add model" draft (also empty groups, BUT empty fallback_chain)
            // is the user's in-progress empty card — keep it so EmptyCard renders.
            const hasModelsProjection = Object.keys(role.models ?? {}).length > 0
            const hasModelGroups = (role.model_groups ?? []).length > 0
            const hasFallbackChain = (role.fallback_chain ?? []).length > 0
            const isBrokenLegacy = !hasModelsProjection && !hasModelGroups && hasFallbackChain
            return !isBrokenLegacy
          })
          .map(([name, role]) => {
            const activeModelGroupId = Object.keys(role.models ?? {})[0] || role.active_model || name

            const mockData = allModelGroupPreviewsById.get(activeModelGroupId)
            const fallbackChainRoutes = configuredCopilotRouteIds(role, activeModelGroupId)

            return {
              id: name,
              title: mockData?.title ?? name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
              description: mockData?.description ?? "Coding copilot role.",
              source: mockData?.source ?? ("third_party" as const),
              modelGroupId: activeModelGroupId,
              fallback_chain: fallbackChainRoutes.map((routeId) => ({ route_id: routeId, runtime_settings: {} })),
            }
          })
      : []
  }, [data, allModelGroupPreviewsById])

  // #56 dynamic float: when the user has never created a copilot role, surface
  // the family-ladder defaults (Claude opus-4.8→4.7, DeepSeek v4-pro→v3.2-pro)
  // as built-in cards. These are RENDERED from candidates, not written to disk —
  // they only enter the save chain when the user acts on one (atom-56 ①).
  const floatedRoles = useMemo(() => {
    return pickDefaultCopilotGroupIds(realCopilotRoles)
      .map((id) => realCopilotRoles.find((candidate) => candidate.id === id))
      .filter((group): group is CopilotRolePreview => Boolean(group))
      .map((group) => ({
        id: group.id,
        title: group.title,
        description: group.description,
        source: group.source, // floated set == built_in set; single source = deriveCopilotCandidateGroups
        modelGroupId: group.id,
        fallback_chain: buildCopilotRoleEntry(group).fallback_chain ?? [],
      }))
  }, [realCopilotRoles])

  const displayRoles = useMemo(
    () => (activeRoles.length > 0 ? orderCopilotDisplayRoles(activeRoles, realCopilotRoles) : floatedRoles),
    [activeRoles, realCopilotRoles, floatedRoles],
  )

  // 固定角色(不可删除/不可改名)—— 内置 copilot 角色(opus / deepseek)在其列。前端据此
  // 隐藏删除入口、渲染问号说明,并在缺推荐模型时给警告。推荐清单是静态的,拉一次即可。
  const [fixedRoleNames, setFixedRoleNames] = useState<ReadonlySet<string>>(() => new Set())
  const [fixedRoleRecommended, setFixedRoleRecommended] = useState<Record<string, FixedRoleRecommendedModel[]>>({})
  const fixedRoleNamesRef = useRef(fixedRoleNames)
  const fixedRoleRecommendedRef = useRef(fixedRoleRecommended)
  useEffect(() => {
    fixedRoleNamesRef.current = fixedRoleNames
  }, [fixedRoleNames])
  useEffect(() => {
    fixedRoleRecommendedRef.current = fixedRoleRecommended
  }, [fixedRoleRecommended])
  useEffect(() => {
    let alive = true
    getFixedRoleNames()
      .then((names) => {
        if (!alive) return
        setFixedRoleNames(new Set(names))
        names.forEach((name) => {
          getFixedRoleStatus(name)
            .then((status) => {
              if (alive) setFixedRoleRecommended((prev) => ({ ...prev, [name]: status.recommendedModels }))
            })
            .catch(() => {
              /* 拿不到推荐清单就不显示提示,不影响角色本身 */
            })
        })
      })
      .catch(() => {
        /* 取不到固定角色名就当没有,后端仍会拒删 */
      })
    return () => {
      alive = false
    }
  }, [])

  const [testingRoleIds, setTestingRoleIds] = useState<ReadonlySet<string>>(() => new Set())
  const [routeStatusOverrides, setRouteStatusOverrides] = useState<Record<string, CopilotRouteJobStatus>>({})
  // 每条 route 的 SDK 测试真实信息(失败原因),供 tooltip 展示"为什么失败"。
  const [routeMessages, setRouteMessages] = useState<Record<string, string>>({})
  // R-F21: per-route cooldown countdown (seconds remaining). Populated by the
  // SDK test job poller when a route surfaces `cooling_down`. The Test Button
  // disables while any compatible route has a positive value so users can't
  // hammer the upstream during a 429 cooldown window.
  const [routeCooldowns, setRouteCooldowns] = useState<Record<string, number>>({})
  const dataRef = useRef<RolesData | null>(data)
  const claudeModelGroupsRef = useRef<CopilotRolePreview[]>(claudeModelGroups)
  const allModelGroupPreviewsRef = useRef<CopilotRolePreview[]>(allModelGroupPreviews)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    dataRef.current = data
  }, [data])

  useEffect(() => {
    claudeModelGroupsRef.current = claudeModelGroups
  }, [claudeModelGroups])

  useEffect(() => {
    allModelGroupPreviewsRef.current = allModelGroupPreviews
  }, [allModelGroupPreviews])

  // R20: on mount, seed copilot route lights from the persisted last-known test
  // results so they show prior status after a remount/restart instead of
  // resetting. Live tests still update + re-persist via the backend; the seed
  // only fills route ids not already overridden in this session.
  useEffect(() => {
    let cancelled = false
    getRoleTestResults()
      .then((persisted) => {
        if (cancelled) return
        const seeded: Record<string, CopilotRouteJobStatus> = {}
        // R-F21: rehydrate any persisted cooldown so the Test Button stays
        // disabled if a 429 was recorded just before the user closed the tab.
        const seededCooldowns: Record<string, number> = {}
        const seededMessages: Record<string, string> = {}
        for (const entry of Object.values(persisted.results ?? {})) {
          Object.assign(seeded, copilotRouteStatusesFromPersistedResult(entry.result))
          Object.assign(seededCooldowns, copilotRouteCooldownsFromPersistedResult(entry.result))
          Object.assign(seededMessages, copilotRouteMessagesFromPersistedResult(entry.result))
        }
        if (Object.keys(seeded).length > 0) {
          setRouteStatusOverrides((current) => ({ ...seeded, ...current }))
        }
        if (Object.keys(seededCooldowns).length > 0) {
          setRouteCooldowns((current) => ({ ...seededCooldowns, ...current }))
        }
        if (Object.keys(seededMessages).length > 0) {
          setRouteMessages((current) => ({ ...seededMessages, ...current }))
        }
      })
      .catch(() => {
        // Seeding is best-effort; the live test flow remains fully functional.
      })
    return () => {
      cancelled = true
    }
  }, [])

  // R-F21: tick the per-route cooldown countdown once a second; drop entries
  // when they reach 0 so the Test Button re-enables itself without a remount.
  useEffect(() => {
    if (Object.keys(routeCooldowns).length === 0) return
    const interval = window.setInterval(() => {
      setRouteCooldowns((current) => {
        const next: Record<string, number> = {}
        let changed = false
        for (const [routeId, seconds] of Object.entries(current)) {
          const remaining = seconds - 1
          if (remaining > 0) {
            next[routeId] = remaining
          } else {
            changed = true
            continue
          }
          if (next[routeId] !== seconds) changed = true
        }
        return changed ? next : current
      })
    }, 1000)
    return () => window.clearInterval(interval)
  }, [routeCooldowns])

  const dropCopilotModelOnRole = useCallback((roleId: string, modelGroupId: string): boolean => {
    const current = dataRef.current
    if (!current) return false
    // 固定 copilot 角色 = 固定模型:只接受它自己的推荐模型组(空卡修复),换组一律拒绝。
    const fixedRecommended = fixedRoleRecommendedRef.current[roleId]
    if (fixedRoleNamesRef.current.has(roleId) && fixedRecommended) {
      const allowed = fixedRecommended.map((model) => model.canonicalId)
      if (!allowed.includes(modelGroupId)) {
        toast.error(modelDropFailureMessage({
          modelId: modelGroupId || "unknown model",
          destination: roleId,
          reason: "fixed copilot role's model is fixed",
        }))
        return false
      }
    }
    const modelGroup = allModelGroupPreviewsRef.current.find((candidate) => candidate.id === modelGroupId)
    if (!modelGroup) {
      toast.error(modelDropFailureMessage({
        modelId: modelGroupId || "unknown model",
        destination: roleId,
        reason: "source is no longer available",
      }))
      return false
    }

    let nextData = current
    let targetRoleId = roleId
    if (!nextData.roles[targetRoleId]) {
      const floatedGroup = claudeModelGroupsRef.current.find((candidate) => candidate.id === roleId)
      if (!floatedGroup) {
        toast.error(modelDropFailureMessage({
          modelId: modelGroupId,
          destination: roleId,
          reason: "role was not found",
        }))
        return false
      }
      targetRoleId = copilotKeyForGroupId(roleId)
      nextData = {
        ...nextData,
        roles: {
          ...nextData.roles,
          [targetRoleId]: buildCopilotRoleEntry(floatedGroup),
        },
      }
    }

    onChangeRef.current(
      applyCopilotModelGroupSelection(
        nextData,
        targetRoleId,
        modelGroup.id,
        compatibleRoutesForRole(modelGroup),
      ),
    )
    return true
  }, [])

  const {
    availableModelDragPreview,
    availableModelDragPreviewNodeRef,
    getActiveAvailableModelDragId,
    handleAvailableModelPointerDown,
  } = useAvailableModelPointerDrag({
    getPreviewLabel: useCallback((modelId: string) => {
      const modelGroup = allModelGroupPreviewsRef.current.find((candidate) => candidate.id === modelId)
      return modelGroup?.modelLabel || modelGroup?.id || modelId
    }, []),
    onDrop: useCallback(({ modelId, target }) => {
      const roleId = copilotRoleIdFromModelDropTarget(target)

      if (roleId) {
        dropCopilotModelOnRole(roleId, modelId)
        return
      }
      toast.error(modelDropFailureMessage({
        modelId,
        destination: "Copilot",
        reason: "drop target was not recognized",
      }))
    }, [dropCopilotModelOnRole]),
  })

  if (!data) {
    return (
      <CopilotRolesLayout sidebar={<CopilotAvailableModelsSidebarSkeleton />}>
        <SectionTitle
          title={t("copilot.title")}
          description={t("copilot.description")}
          trailing={<SaveStatusBadge status={saveStatus} />}
        />
        {error ? <div className="mb-3 text-xs text-destructive">{t("llmRoles.validationFailed", { error })}</div> : null}

        <div className="space-y-4 pt-4">
          {[1, 2].map((i) => (
            <Card key={i} size="sm" className="min-w-0 rounded-md">
              <CardHeader className="!grid-cols-1 items-start gap-2 sm:!grid-cols-[minmax(0,1fr)_auto]">
                <div className="min-w-0 space-y-2">
                  <div className="flex items-center gap-2">
                    <Skeleton className="h-5 w-36" />
                    <Skeleton className="h-5 w-16" />
                  </div>
                  <Skeleton className="h-4 w-64" />
                </div>
                <CardAction className="row-start-2 flex items-center gap-2 justify-self-start sm:row-start-1 sm:justify-self-end">
                  <Skeleton className="h-5 w-24" />
                  <Skeleton className="h-8 w-16" />
                </CardAction>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-3 rounded-md border border-foreground/10 bg-background/60 p-3">
                  <Skeleton className="h-6 w-6 rounded-sm" />
                  <div className="min-w-0 flex-1 space-y-1">
                    <Skeleton className="h-4 w-32" />
                  </div>
                  <div className="ml-auto">
                    <Skeleton className="h-5 w-5 rounded" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </CopilotRolesLayout>
    )
  }

  // A floated built-in default is not persisted until acted on. Any edit (reorder,
  // remove group, test) first materializes it into data.roles via buildCopilotRoleEntry.
  // R-F5: persist under `copilot_<slug>` (yaml-key-safe), not the raw model-group id
  // which may contain hyphens/dots (e.g. `claude-opus-4.8`).
  function ensureRolePersisted(current: RolesData, roleId: string): RolesData {
    const persistedKey = copilotKeyForGroupId(roleId)
    if (current.roles[persistedKey]) return current
    if (current.roles[roleId]) return current
    const group = claudeModelGroups.find((candidate) => candidate.id === roleId)
    if (!group) return current
    return { ...current, roles: { ...current.roles, [persistedKey]: buildCopilotRoleEntry(group) } }
  }

  function removeModelGroup(roleId: string) {
    if (!data) return
    const base = ensureRolePersisted(data, roleId)
    // R-F5: read/write under the yaml-safe key, never the raw model-group id.
    const persistedKey = resolvePersistedKey(base, roleId)
    const role = base.roles[persistedKey]
    if (!role) return
    // #61: single-group constraint → "remove group" = deselect back to an empty
    // card (role + role_kind preserved), NOT deleting the role (#64).
    const nextRoles = { ...base.roles, [persistedKey]: { ...role, active_model: "", models: {}, fallback_chain: [] } }
    onChange({ ...base, roles: nextRoles })
  }

  function updateRouteOrder(roleId: string, nextOrder: string[]) {
    if (!data) return
    const base = ensureRolePersisted(data, roleId)
    // R-F5: read/write under the yaml-safe key, never the raw model-group id.
    const persistedKey = resolvePersistedKey(base, roleId)
    const nextRoles = { ...base.roles }
    const role = nextRoles[persistedKey]
    if (!role) return

    const activeModelGroupId = Object.keys(role.models ?? {})[0] || role.active_model || roleId

    // R-F6: preserve runtime_settings per route_id across reorder. The
    // materializer writes max_tokens/model_id into runtime_settings on the
    // first save; dropping them on every drag wipes the live params.
    nextRoles[persistedKey] = {
      ...role,
      fallback_chain: rebuildFallbackChainPreservingRuntime(role.fallback_chain ?? [], nextOrder),
      models: {
        [activeModelGroupId]: {
          providers: nextOrder,
        }
      }
    }
    onChange({ ...base, roles: nextRoles })
  }

  function addDraftCopilotRole() {
    if (!data) return
    // R-F5: pick `max(existing) + 1` not `count + 1` to avoid collision when a
    // middle id was deleted (e.g. _1 + _3 present → next must be _4, never _3).
    const nextIndex = nextCopilotCustomIndex(Object.keys(data.roles))
    const newRoleId = `copilot_custom_${nextIndex}`
    const nextRoles = {
      ...data.roles,
      [newRoleId]: {
        role_kind: "copilot" as const,
        system_prompt_prefix: "",
        model_fallback_enabled: true,
        fallback_chain: [],
        intent: { provider_preference: "manual_order" as const },
        model_groups: [],
        active_model: "",
        models: {},
      }
    }
    onChange({ ...data, roles: nextRoles })
  }

  function requestDeleteCopilotRole(role: { id: string; title: string }) {
    confirmDelete({
      title: `Delete ${role.title}?`,
      description: "Remove this Copilot role permanently.",
      onConfirm: async () => {
        // R-F3: route through the real DELETE /api/llm/roles/{roleId} endpoint
        // (SettingsPage.deleteRoleByName). The old local `onChange(...delete
        // key...)` + PUT path could never actually drop a key from yaml because
        // the backend treats PUT roles as additive merge.
        const persistedKey = resolvePersistedKey(data, role.id)
        try {
          await onDeleteRole?.(persistedKey)
        } catch (err) {
          // R-F3 acceptance #4 + rules/logging.md: never silently swallow.
          console.error(
            "phase=copilot-tab action=delete-role role_id=%s persisted_key=%s error=%o",
            role.id,
            persistedKey,
            err,
          )
          toast.error(
            `Delete ${role.title} failed: ${err instanceof Error ? err.message : String(err)}`,
          )
        }
      },
    })
  }

  async function testRoleRoutes(role: { id: string; title: string }) {
    // A floated built-in default enters the save chain when tested (atom-56 ①).
    // R-F5: yaml key may differ from the UI role id (e.g. `claude-opus-4.8` → `copilot_claude_opus_4_8`).
    const persistedKey = resolvePersistedKey(data, role.id)
    if (data && !data.roles[persistedKey]) {
      onChange(ensureRolePersisted(data, role.id))
    }
    // R-F7: flush any debounced roles-save BEFORE startJob so the gateway sees
    // the snapshot the user just authored. Without this, Test can race the
    // save and report `no_available_route` on the route the user just added.
    try {
      await onBeforeRoleTest?.()
    } catch (err) {
      // rules/logging.md: degradation must be observable. The Test still
      // proceeds — flush failure is non-blocking, but we record why.
      console.warn(
        "phase=copilot-tab action=before-role-test-flush-failed role_id=%s error=%o",
        role.id,
        err,
      )
    }
    setTestingRoleIds((current) => {
      const next = new Set(current)
      next.add(role.id)
      return next
    })
    try {
      const result = await runCopilotRoleTestJob(persistedKey, {
        onProgress: (job) => {
          setRouteStatusOverrides((current) => ({
            ...current,
            ...copilotRouteStatusesFromJob(job),
          }))
          setRouteMessages((current) => ({
            ...current,
            ...copilotRouteMessagesFromJob(job),
          }))
          // R-F21: capture any new cooldown windows the backend reports as a
          // route flips into cooling_down. We additively merge so an existing
          // countdown isn't bumped back up by a stale poll response.
          const cooldowns = copilotRouteCooldownsFromJob(job)
          if (Object.keys(cooldowns).length > 0) {
            setRouteCooldowns((current) => ({ ...current, ...cooldowns }))
          }
        },
      })
      if (result.status === "ok") {
        // R-F16: route toast text through i18n so the copy follows the active
        // language (en/zh-CN), aligned with LlmRolesTab's i18n conventions.
        toast.success(t("copilot.testToast.passed", { title: role.title }))
      } else {
        toast.warning(t("copilot.testToast.needsAttention", { title: role.title }))
      }
    } catch (err) {
      toast.error(copilotRoleTestErrorMessage(err, role.title))
    } finally {
      setTestingRoleIds((current) => {
        const next = new Set(current)
        next.delete(role.id)
        return next
      })
    }
  }

  // R-F12: empty-state with API Keys CTA when there are no eligible candidates
  // (no anthropic-messages route configured anywhere) AND no copilot role is
  // bound (displayRoles only contained floated defaults, but those are also
  // gone when claudeModelGroups is empty).
  const showEmptyState = displayRoles.length === 0 && allModelGroupPreviews.length === 0

  return (
    <>
      {deleteDialog}
      <CopilotRolesLayout
        sidebar={(
          <div data-copilot-available-models-sidebar="true" className="min-w-0 lg:h-full">
            <AvailableModelsSidebar
              modelGroups={modelGroups}
              onModelPointerDown={handleAvailableModelPointerDown}
              onNavigateToApiKeys={onNavigateToApiKeys}
            />
          </div>
        )}
      >
        <SectionTitle
          title={t("copilot.title")}
          description={t("copilot.description")}
          // R-F15: shared SaveStatusBadge already wired here (idle hides; pending/
          // saving spins; saved checks; error triangle). Kept consistent with the
          // LlmRolesTab badge so users see one status convention across both tabs.
          trailing={<SaveStatusBadge status={saveStatus} />}
        />
        {error ? <div className="mb-3 text-xs text-destructive">{t("llmRoles.validationFailed", { error })}</div> : null}

        {showEmptyState ? (
          <EmptyCopilotState onNavigateToApiKeys={onNavigateToApiKeys} />
        ) : null}

        <CatalogAccordion type="multiple" defaultValue={["claude-agent-sdk"]}>
          <CatalogAccordionItem value="claude-agent-sdk">
            <CatalogAccordionTrigger>
              {t("copilot.claudeAgentSdk")}
            </CatalogAccordionTrigger>
            <CatalogAccordionContent className="space-y-4 pb-5">
              {displayRoles.map((role) => {
                const modelGroup = role.modelGroupId
                  ? allModelGroupPreviewsById.get(role.modelGroupId)
                  : null
                const isFixed = fixedRoleNames.has(role.id)
                const recommendedModels = fixedRoleRecommended[role.id] ?? []
                const fixedDescription = isFixed
                  ? t(`llmRoles.fixedRole.${role.id}.description`, { defaultValue: "" })
                  : ""
                // 缺哪个推荐模型:拿当前内存里的模型组(canonical + 展示名)实时算,拖进来立刻消警告。
                const presentGroupKeys = new Set<string>()
                if (modelGroup) {
                  presentGroupKeys.add(normalizeModelGroupKey(role.modelGroupId ?? ""))
                  presentGroupKeys.add(normalizeModelGroupKey(modelGroup.modelLabel ?? ""))
                }
                const missingRecommended = isFixed
                  ? missingRecommendedModels(recommendedModels, presentGroupKeys)
                  : []
                if (!modelGroup) {
                  return (
                    <EmptyCopilotRoleCard
                      key={role.id}
                      role={role}
                      isFixed={isFixed}
                      fixedDescription={fixedDescription}
                      recommendedModels={recommendedModels}
                      missingRecommended={missingRecommended}
                      getActiveAvailableModelDragId={getActiveAvailableModelDragId}
                      onDropModel={(modelGroupId) => dropCopilotModelOnRole(role.id, modelGroupId)}
                      onDeleteRole={() => requestDeleteCopilotRole(role)}
                    />
                  )
                }
                const visibleRoutes = compatibleRoutesForRole(modelGroup)
                const routeOrder = role.fallback_chain.map((entry) => entry.route_id)
                const chainRoutes = routeOrder
                  .map((routeId) => visibleRoutes.find((route) => route.id === routeId))
                  .filter(isCopilotRoute)
                const appendableRoutes = visibleRoutes.filter((route) => !routeOrder.includes(route.id))

                return (
                  <CopilotRoleCard
                    key={role.id}
                    role={role}
                    modelGroup={modelGroup}
                    isFixed={isFixed}
                    fixedDescription={fixedDescription}
                    recommendedModels={recommendedModels}
                    routeOrder={routeOrder}
                    chainRoutes={chainRoutes}
                    appendableRoutes={appendableRoutes}
                    routeStatusOverrides={routeStatusOverrides}
                    routeMessages={routeMessages}
                    routeCooldowns={routeCooldowns}
                    isTesting={testingRoleIds.has(role.id)}
                    saveStatus={saveStatus}
                    getActiveAvailableModelDragId={getActiveAvailableModelDragId}
                    onDropModel={(modelGroupId) => dropCopilotModelOnRole(role.id, modelGroupId)}
                    onTest={() => testRoleRoutes(role)}
                    onDeleteRole={() => requestDeleteCopilotRole(role)}
                    onUpdateRouteOrder={(nextOrder) => updateRouteOrder(role.id, nextOrder)}
                    onRemoveModelGroup={
                      role.source === "third_party" && !isFixed ? () => removeModelGroup(role.id) : undefined
                    }
                    onNavigateToApiKeys={onNavigateToApiKeys}
                  />
                )
              })}
              <AddCopilotModelButton onClick={addDraftCopilotRole} />
            </CatalogAccordionContent>
          </CatalogAccordionItem>
        </CatalogAccordion>
      </CopilotRolesLayout>
      <AvailableModelDragPreview drag={availableModelDragPreview} nodeRef={availableModelDragPreviewNodeRef} />
    </>
  )
}

function CopilotRolesLayout({ children, sidebar }: { children: ReactNode; sidebar: ReactNode }) {
  return (
    <div
      data-copilot-settings-page="true"
      className="grid min-h-full min-w-0 gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden 2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]"
    >
      <ScrollArea className="min-h-0 min-w-0 overflow-hidden lg:h-full [&_[data-slot=scroll-area-scrollbar]]:hidden [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:!min-w-0 [&_[data-slot=scroll-area-viewport]>div]:!w-full">
        <div className="pr-2">
          {children}
        </div>
      </ScrollArea>
      {sidebar}
    </div>
  )
}

function CopilotAvailableModelsSidebarSkeleton() {
  return (
    <aside className="min-w-0 lg:sticky lg:top-0 lg:h-full lg:min-h-0 lg:self-start">
      <div className="flex min-h-0 flex-col gap-3 lg:h-full">
        <div className="space-y-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-8 w-full" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </div>
    </aside>
  )
}

function AddCopilotModelButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      type="button"
      variant="default"
      data-copilot-model-add-trigger="true"
      data-disabled="false"
      className="gap-1"
      onClick={onClick}
    >
      <Plus data-role-icon="true" className="size-3.5 text-primary-foreground/80" />
      Add model
    </Button>
  )
}

/**
 * R-F12: empty-state shown when no Anthropic-messages eligible route exists
 * (claudeModelGroups is empty). CTA jumps to API Keys so the user knows where
 * to fix it instead of staring at an empty tab.
 */
function EmptyCopilotState({
  onNavigateToApiKeys,
}: {
  onNavigateToApiKeys?: () => void
}) {
  const { t } = useTranslation("settings")
  return (
    <Card
      size="sm"
      className="mb-4 min-w-0 rounded-md border-dashed bg-card/70"
      data-copilot-empty-state="true"
    >
      <CardHeader className="!grid-cols-1">
        <CardTitle>{t("copilot.emptyState.title")}</CardTitle>
        <CardDescription>
          {t("copilot.emptyState.description")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button
          type="button"
          variant="default"
          data-copilot-empty-cta="true"
          onClick={onNavigateToApiKeys}
          disabled={!onNavigateToApiKeys}
        >
          {t("copilot.emptyState.cta")}
        </Button>
      </CardContent>
    </Card>
  )
}

// 固定角色名旁的问号说明:这个角色是干嘛的 + 建议模型(与 LLM Roles 页 RoleCard 一致)。
function FixedCopilotRoleInfo({
  roleId,
  description,
  recommendedModels,
}: {
  roleId: string
  description: string
  recommendedModels: FixedRoleRecommendedModel[]
}) {
  const { t } = useTranslation("settings")
  const content = [
    description,
    recommendedModels.length
      ? `${t("llmRoles.fixedRole.recommendedLabel")}: ${recommendedModels.map((model) => model.displayName).join(", ")}`
      : null,
  ]
    .filter(Boolean)
    .join("\n")
  if (!content) return null
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span data-role-fixed-info="true" className="inline-flex shrink-0 text-muted-foreground">
            <CircleHelp aria-hidden="true" className="size-3.5" />
            <span className="sr-only">{t("llmRoles.fixedRole.infoAria", { role: roleId })}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm whitespace-pre-line break-words">{content}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function CopilotRoleCard({
  role,
  modelGroup,
  isFixed,
  fixedDescription,
  recommendedModels,
  routeOrder,
  chainRoutes,
  appendableRoutes,
  routeStatusOverrides,
  routeMessages,
  routeCooldowns,
  isTesting,
  saveStatus,
  getActiveAvailableModelDragId,
  onDropModel,
  onTest,
  onDeleteRole,
  onUpdateRouteOrder,
  onRemoveModelGroup,
  onNavigateToApiKeys,
}: {
  role: { id: string; title: string; source: "built_in" | "third_party" }
  modelGroup: CopilotRolePreview
  isFixed: boolean
  fixedDescription: string
  recommendedModels: FixedRoleRecommendedModel[]
  routeOrder: string[]
  chainRoutes: CopilotRoutePreview[]
  appendableRoutes: CopilotRoutePreview[]
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>
  routeMessages: Record<string, string>
  // R-F21: per-route cooldown countdown (seconds). When any compatible route
  // has a positive value the Test Button stays disabled until it elapses.
  routeCooldowns: Record<string, number>
  isTesting: boolean
  // R-F7: when the parent's debounced roles save is mid-flight, Test must
  // wait for it to settle before sending the SDK probe so the gateway sees
  // the latest yaml snapshot.
  saveStatus?: SaveStatus
  getActiveAvailableModelDragId: () => string | null
  onDropModel: (modelGroupId: string) => void
  onTest: () => void
  onDeleteRole: () => void
  onUpdateRouteOrder: (nextOrder: string[]) => void
  onRemoveModelGroup?: () => void
  onNavigateToApiKeys?: () => void
}) {
  // R-F17: per-card a11y text needs i18n so it tracks the active language.
  const { t } = useTranslation("settings")
  const configuredRoutes = chainRoutes
  const readyCount = copilotBackendReadyCount(configuredRoutes, routeStatusOverrides)
  // R-F7: disable Test while debounced roles-save is still pending/saving so
  // the gateway resolver sees the snapshot the user just authored.
  const saveInFlight = saveStatus === "pending" || saveStatus === "saving"
  // R-F21: longest cooldown across configured routes drives the countdown
  // label and the Test Button's disabled state. Falls back to 0 (no cooldown).
  const maxCooldownSeconds = configuredRoutes.reduce((max, route) => {
    const seconds = routeCooldowns[route.id]
    return typeof seconds === "number" && seconds > max ? seconds : max
  }, 0)
  const isCoolingDown = maxCooldownSeconds > 0
  // R-F12: per-card warning when there are eligible routes but none ready
  // yet — guide the user to single-test them in API Keys.
  const showUntestedWarning =
    readyCount === 0 && configuredRoutes.length > 0

  function handleAvailableModelDrop(event: Parameters<typeof readAvailableModelDropId>[0]) {
    const modelId = readAvailableModelDropId(event, getActiveAvailableModelDragId)
    if (!modelId) {
      toast.error(modelDropFailureMessage({
        modelId: "unknown model",
        destination: role.id,
        reason: "source is no longer available",
      }))
      return
    }
    onDropModel(modelId)
  }

  return (
    <Card
      size="sm"
      className="min-w-0 rounded-md"
      data-copilot-role-card="true"
      data-copilot-role-source={role.source}
      data-role-name={role.id}
      data-copilot-role-id={role.id}
      data-model-drop-zone="true"
      data-model-drop-fallback="active-drag-ref"
      onDragOver={handleAvailableModelDragOver}
      onDrop={handleAvailableModelDrop}
    >
      <CardHeader className="!grid-cols-1 items-start gap-2 sm:!grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <CardTitle className="flex min-w-0 flex-wrap items-center gap-2">
            {role.title}
            {isFixed ? (
              <FixedCopilotRoleInfo roleId={role.id} description={fixedDescription} recommendedModels={recommendedModels} />
            ) : null}
            <Badge variant="secondary">{role.source === "built_in" ? "Built-in" : "Third-party"}</Badge>
          </CardTitle>
          <CardDescription>{t("copilot.roleCard.description")}</CardDescription>
          {showUntestedWarning ? (
            <button
              type="button"
              data-copilot-untested-warning="true"
              className="mt-1 inline-flex items-center gap-1 text-xs text-warning underline-offset-2 hover:underline disabled:cursor-default disabled:no-underline"
              onClick={onNavigateToApiKeys}
              disabled={!onNavigateToApiKeys}
            >
              {t("copilot.roleCard.untestedWarning", { n: configuredRoutes.length })}
            </button>
          ) : null}
        </div>
        <CardAction className="row-start-2 flex flex-wrap items-center gap-2 justify-self-start sm:row-start-1 sm:justify-self-end">
          <Badge variant={readyCount === configuredRoutes.length ? "success" : "outline"}>
            {readyCount}/{configuredRoutes.length} SDK Ready
          </Badge>
          <Button
            type="button"
            variant="default"
            size="sm"
            data-copilot-test-chain="true"
            data-copilot-test-save-pending={saveInFlight ? "true" : "false"}
            // R-F21: surface cooldown state for tests + reader UIs.
            data-copilot-test-cooling-down={isCoolingDown ? "true" : "false"}
            data-copilot-test-cooldown-seconds={isCoolingDown ? String(maxCooldownSeconds) : "0"}
            // R-F17: aria-busy lets screen readers know the Test action is
            // mid-flight so users hear status instead of "button". The sr-only
            // sibling below provides polite live updates as readyCount/total
            // change during/after a probe.
            aria-busy={isTesting}
            onClick={onTest}
            disabled={isTesting || saveInFlight || isCoolingDown}
          >
            {isTesting ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <FlaskConical data-icon="inline-start" />}
            {isTesting
              ? "Testing"
              : isCoolingDown
              ? `Cooling down ${maxCooldownSeconds}s`
              : "Test"}
          </Button>
          <span
            // R-F17: polite live region announces Test progress without
            // stealing focus. Two phrases: "Testing {title}..." mid-flight,
            // "{title} ready: N/M routes" at rest. Title + ready/total flow
            // through i18n so the announcement follows the active language.
            aria-live="polite"
            data-copilot-test-live-status="true"
            className="sr-only"
          >
            {isTesting
              ? t("copilot.aria.testing", { title: role.title })
              : t("copilot.aria.ready", {
                  title: role.title,
                  ready: readyCount,
                  total: configuredRoutes.length,
                })}
          </span>
          {role.source === "third_party" && !isFixed ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Delete ${role.title}`}
              data-copilot-role-delete-trigger="true"
              className="text-muted-foreground hover:text-destructive"
              onClick={onDeleteRole}
            >
              <Trash2 data-role-icon="true" className="size-4" />
            </Button>
          ) : null}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <CopilotModelGroupCard
          modelName={modelGroup.modelLabel}
          modelIndex={0}
          routes={chainRoutes}
          appendableRoutes={appendableRoutes}
          routeStatusOverrides={routeStatusOverrides}
          routeMessages={routeMessages}
          onRemoveModelGroup={onRemoveModelGroup}
          onAddRoute={(routeId) => onUpdateRouteOrder([...routeOrder, routeId])}
          onRemoveRoute={(routeId) => onUpdateRouteOrder(routeOrder.filter((candidate) => candidate !== routeId))}
          onReorderRoutes={(activeRouteId, overRouteId) => {
            const activeIndex = routeOrder.indexOf(activeRouteId)
            const overIndex = routeOrder.indexOf(overRouteId)
            if (activeIndex < 0 || overIndex < 0) return
            onUpdateRouteOrder(moveItem(routeOrder, activeIndex, overIndex))
          }}
        />
      </CardContent>
    </Card>
  )
}

function EmptyCopilotRoleCard({
  role,
  isFixed,
  fixedDescription,
  recommendedModels,
  missingRecommended,
  getActiveAvailableModelDragId,
  onDropModel,
  onDeleteRole,
}: {
  role: { id: string; title: string; source: "built_in" | "third_party" }
  isFixed: boolean
  fixedDescription: string
  recommendedModels: FixedRoleRecommendedModel[]
  missingRecommended: FixedRoleRecommendedModel[]
  getActiveAvailableModelDragId: () => string | null
  onDropModel: (modelGroupId: string) => void
  onDeleteRole: () => void
}) {
  const { t } = useTranslation("settings")
  function handleAvailableModelDrop(event: Parameters<typeof readAvailableModelDropId>[0]) {
    const modelId = readAvailableModelDropId(event, getActiveAvailableModelDragId)
    if (!modelId) {
      toast.error(modelDropFailureMessage({
        modelId: "unknown model",
        destination: role.id,
        reason: "source is no longer available",
      }))
      return
    }
    onDropModel(modelId)
  }

  return (
    <Card
      size="sm"
      className="min-w-0 rounded-md"
      data-copilot-empty-role-card="true"
      data-copilot-role-card="true"
      data-copilot-role-source={role.source}
      data-role-name={role.id}
      data-copilot-role-id={role.id}
      data-model-drop-zone="true"
      data-model-drop-fallback="active-drag-ref"
      onDragOver={handleAvailableModelDragOver}
      onDrop={handleAvailableModelDrop}
    >
      <CardHeader className="!grid-cols-1 items-start gap-2 sm:!grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <CardTitle className="flex min-w-0 flex-wrap items-center gap-2">
            {role.title}
            {isFixed ? (
              <FixedCopilotRoleInfo roleId={role.id} description={fixedDescription} recommendedModels={recommendedModels} />
            ) : null}
            <Badge variant="secondary">{role.source === "built_in" ? "Built-in" : "Third-party"}</Badge>
          </CardTitle>
        </div>
        {role.source === "third_party" && !isFixed ? (
          <CardAction className="row-start-2 justify-self-start sm:row-start-1 sm:justify-self-end">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Delete ${role.title}`}
              data-copilot-role-delete-trigger="true"
              className="text-muted-foreground hover:text-destructive"
              onClick={onDeleteRole}
            >
              <Trash2 data-role-icon="true" className="size-4" />
            </Button>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {isFixed && missingRecommended.length > 0 ? (
          <Empty
            aria-label={`Drop model into ${role.title}`}
            data-model-drop-target="true"
            data-model-drop-zone="true"
            data-model-drop-fallback="active-drag-ref"
            data-copilot-missing-recommended-model="true"
            onDragOver={handleAvailableModelDragOver}
            onDrop={handleAvailableModelDrop}
            className="min-h-16 flex-none select-none gap-1 rounded-md border border-dashed border-warning-border bg-warning-background/20 p-3 text-warning-foreground transition-colors hover:bg-warning-background/30"
          >
            <EmptyHeader className="max-w-none gap-1.5">
              <Badge variant="warning" className="gap-1">
                <CircleAlert className="size-3" />
                {t("llmRoles.fixedRole.missingWarning")}
              </Badge>
              <EmptyTitle className="text-xs font-medium text-warning-foreground">
                {t("llmRoles.fixedRole.dragInHint", {
                  models: missingRecommended.map((model) => model.displayName).join(", "),
                })}
              </EmptyTitle>
            </EmptyHeader>
          </Empty>
        ) : (
          <Empty
            aria-label={`Drop model into ${role.title}`}
            data-model-drop-target="true"
            data-model-drop-zone="true"
            data-model-drop-fallback="active-drag-ref"
            onDragOver={handleAvailableModelDragOver}
            onDrop={handleAvailableModelDrop}
            className="min-h-16 flex-none select-none gap-1 rounded-md border border-dashed border-border bg-muted/10 p-3 text-muted-foreground transition-colors hover:bg-muted/20"
          >
            <EmptyHeader className="max-w-none gap-0">
              <EmptyTitle className="text-xs font-medium text-muted-foreground">Drop model</EmptyTitle>
            </EmptyHeader>
          </Empty>
        )}
      </CardContent>
    </Card>
  )
}

export function copilotRoleIdFromModelDropTarget(target: Element | null): string | null {
  const dropZone = target?.closest<HTMLElement>("[data-model-drop-zone]") ?? null
  const roleElement = dropZone?.closest<HTMLElement>("[data-role-name]") ?? null
  return roleElement?.dataset.roleName ?? null
}

export function compatibleRoutesForRole(role: CopilotRolePreview): CopilotRoutePreview[] {
  return role.availableRoutes.filter((route) => routeSupportsCopilotSdk(route, role.sdkId))
}

function isCopilotRoute(route: CopilotRoutePreview | undefined): route is CopilotRoutePreview {
  return Boolean(route)
}

function moveItem<T>(items: readonly T[], fromIndex: number, toIndex: number): T[] {
  const next = [...items]
  const [item] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, item)
  return next
}
