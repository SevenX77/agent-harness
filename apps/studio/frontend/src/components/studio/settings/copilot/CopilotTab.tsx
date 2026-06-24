import { useEffect, useMemo, useState } from "react"
import { ChevronsUpDown, FlaskConical, Loader2, Plus, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { requestDeleteConfirmationToast } from "@/components/ui/delete-confirm-toast"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { SectionTitle } from "../shared"
import { agentStatusForRoute, CopilotModelGroupCard } from "./CopilotModelGroupCard"
import {
  deriveCopilotCandidateGroups,
  applyCopilotModelGroupSelection,
  buildCopilotRoleEntry,
  pickDefaultCopilotGroupIds,
  type CopilotRolePreview,
  type CopilotRoutePreview,
} from "./copilot-role-derivation"
import {
  copilotRoleTestErrorMessage,
  copilotRouteCooldownsFromJob,
  copilotRouteCooldownsFromPersistedResult,
  copilotRouteStatusesFromJob,
  copilotRouteStatusesFromPersistedResult,
  runCopilotRoleTestJob,
  type CopilotRouteJobStatus,
} from "./copilot-role-test"
import { Skeleton } from "@/components/ui/skeleton"
import { getRoleTestResults } from "@/api/client"
import type { CredentialsState, ModelGroup, RolesData } from "@/api/llm"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"

/**
 * R-F5: derive a yaml-safe key for a copilot role created from a model group.
 * The yaml key must match `[a-z][a-z0-9_]*` (no hyphens, no dots, no upper).
 * `copilot_<slug>` where slug strips any non-[a-zA-Z0-9] run to `_` and lowercases.
 */
export function copilotKeyForGroupId(groupId: string): string {
  return "copilot_" + groupId.replace(/[^a-zA-Z0-9]+/g, "_").toLowerCase()
}

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

  const realCopilotRoles = useMemo(() => {
    return deriveCopilotCandidateGroups(modelGroups, credentials)
  }, [modelGroups, credentials])

  const claudeModelGroups = realCopilotRoles

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

            const mockData = realCopilotRoles.find((r) => r.id === activeModelGroupId)
            const fallbackChainRoutes = role.models?.[activeModelGroupId]?.providers ??
              role.fallback_chain?.map(e => e.route_id) ?? []

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
  }, [data, realCopilotRoles])

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
    () => (activeRoles.length > 0 ? activeRoles : floatedRoles),
    [activeRoles, floatedRoles],
  )

  const selectedModelGroupIds = useMemo(
    () =>
      new Set(
        displayRoles
          .map((role) => role.modelGroupId)
          .filter((id): id is string => typeof id === "string" && id !== null),
      ),
    [displayRoles],
  )
  const modelGroupOptions = useMemo(
    () => claudeModelGroups.filter((modelGroup) => !selectedModelGroupIds.has(modelGroup.id)),
    [claudeModelGroups, selectedModelGroupIds],
  )

  const [testingRoleIds, setTestingRoleIds] = useState<ReadonlySet<string>>(() => new Set())
  const [routeStatusOverrides, setRouteStatusOverrides] = useState<Record<string, CopilotRouteJobStatus>>({})
  // R-F21: per-route cooldown countdown (seconds remaining). Populated by the
  // SDK test job poller when a route surfaces `cooling_down`. The Test Button
  // disables while any compatible route has a positive value so users can't
  // hammer the upstream during a 429 cooldown window.
  const [routeCooldowns, setRouteCooldowns] = useState<Record<string, number>>({})

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
        for (const entry of Object.values(persisted.results ?? {})) {
          Object.assign(seeded, copilotRouteStatusesFromPersistedResult(entry.result))
          Object.assign(seededCooldowns, copilotRouteCooldownsFromPersistedResult(entry.result))
        }
        if (Object.keys(seeded).length > 0) {
          setRouteStatusOverrides((current) => ({ ...seeded, ...current }))
        }
        if (Object.keys(seededCooldowns).length > 0) {
          setRouteCooldowns((current) => ({ ...seededCooldowns, ...current }))
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

  if (!data) {
    return (
      <div data-copilot-settings-page="true" className="max-w-3xl min-w-0">
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
      </div>
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

  function selectModelGroup(roleId: string, modelGroupId: string) {
    if (!data) return
    const modelGroup = claudeModelGroups.find((candidate) => candidate.id === modelGroupId)
    if (!modelGroup) return

    const nextData = applyCopilotModelGroupSelection(data, roleId, modelGroupId, modelGroup.availableRoutes)
    onChange(nextData)
  }

  function requestDeleteCopilotRole(role: { id: string; title: string }) {
    requestDeleteConfirmationToast({
      id: `delete-copilot-role-${role.id}`,
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

  // R-F14: Add-model defrag — if the user already has an in-progress empty
  // draft card (no model_groups, no models, no fallback_chain), disable Add
  // and explain via Tooltip so we don't accumulate duplicate empties.
  const hasEmptyDraftCard = displayRoles.some((displayed) => {
    const persistedKey = resolvePersistedKey(data, displayed.id)
    const role = data?.roles?.[persistedKey]
    if (!role) return false
    const noModels = Object.keys(role.models ?? {}).length === 0
    const noModelGroups = (role.model_groups ?? []).length === 0
    const noFallbackChain = (role.fallback_chain ?? []).length === 0
    return noModels && noModelGroups && noFallbackChain
  })

  // R-F12: empty-state with API Keys CTA when there are no eligible candidates
  // (no anthropic-messages route configured anywhere) AND no copilot role is
  // bound (displayRoles only contained floated defaults, but those are also
  // gone when claudeModelGroups is empty).
  const showEmptyState = displayRoles.length === 0 && claudeModelGroups.length === 0

  return (
    <div data-copilot-settings-page="true" className="max-w-3xl min-w-0">
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
                ? claudeModelGroups.find((candidate) => candidate.id === role.modelGroupId)
                : null
              if (!modelGroup) {
                return (
                  <EmptyCopilotRoleCard
                    key={role.id}
                    role={role}
                    modelGroups={modelGroupOptions}
                    onSelectModelGroup={(modelGroupId) => selectModelGroup(role.id, modelGroupId)}
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
                  routeOrder={routeOrder}
                  chainRoutes={chainRoutes}
                  appendableRoutes={appendableRoutes}
                  routeStatusOverrides={routeStatusOverrides}
                  routeCooldowns={routeCooldowns}
                  isTesting={testingRoleIds.has(role.id)}
                  saveStatus={saveStatus}
                  onTest={() => testRoleRoutes(role)}
                  onDeleteRole={() => requestDeleteCopilotRole(role)}
                  onUpdateRouteOrder={(nextOrder) => updateRouteOrder(role.id, nextOrder)}
                  onRemoveModelGroup={() => removeModelGroup(role.id)}
                  onNavigateToApiKeys={onNavigateToApiKeys}
                />
              )
            })}
            <AddCopilotModelButton
              disabled={hasEmptyDraftCard}
              onClick={addDraftCopilotRole}
            />
          </CatalogAccordionContent>
        </CatalogAccordionItem>
      </CatalogAccordion>
    </div>
  )
}

/**
 * R-F14 Add-model button with defrag Tooltip when an empty draft card already
 * exists. Extracted so the button stays a single render (no double-mount of
 * Tooltip when toggling disabled).
 */
function AddCopilotModelButton({
  disabled,
  onClick,
}: {
  disabled: boolean
  onClick: () => void
}) {
  const { t } = useTranslation("settings")
  const button = (
    <Button
      type="button"
      variant="default"
      data-copilot-model-add-trigger="true"
      data-disabled={disabled ? "true" : "false"}
      className="gap-1"
      disabled={disabled}
      onClick={onClick}
    >
      <Plus data-role-icon="true" className="size-3.5 text-primary-foreground/80" />
      Add model
    </Button>
  )
  if (!disabled) return button
  return (
    <TooltipProvider>
      <Tooltip>
        {/* asChild needs a wrapper because disabled Buttons don't fire mouse events. */}
        <TooltipTrigger asChild>
          <span tabIndex={0}>{button}</span>
        </TooltipTrigger>
        <TooltipContent side="top">
          {t("copilot.addModelDisabledTooltip", {
            defaultValue: "Choose a model group for the empty card before adding another.",
          })}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
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
        <CardTitle>
          {t("copilot.emptyState.title", { defaultValue: "No Anthropic Messages route yet" })}
        </CardTitle>
        <CardDescription>
          {t("copilot.emptyState.description", {
            defaultValue:
              "Add credentials that support the anthropic-messages protocol in API Keys (Anthropic Official, Ark, DeepSeek, OpenRouter, and similar providers). Routes appear here after the provider or role test verifies them.",
          })}
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
          {t("copilot.emptyState.cta", { defaultValue: "Go to API Keys" })}
        </Button>
      </CardContent>
    </Card>
  )
}

function CopilotRoleCard({
  role,
  modelGroup,
  routeOrder,
  chainRoutes,
  appendableRoutes,
  routeStatusOverrides,
  routeCooldowns,
  isTesting,
  saveStatus,
  onTest,
  onDeleteRole,
  onUpdateRouteOrder,
  onRemoveModelGroup,
  onNavigateToApiKeys,
}: {
  role: { id: string; title: string; source: "built_in" | "third_party" }
  modelGroup: CopilotRolePreview
  routeOrder: string[]
  chainRoutes: CopilotRoutePreview[]
  appendableRoutes: CopilotRoutePreview[]
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>
  // R-F21: per-route cooldown countdown (seconds). When any compatible route
  // has a positive value the Test Button stays disabled until it elapses.
  routeCooldowns: Record<string, number>
  isTesting: boolean
  // R-F7: when the parent's debounced roles save is mid-flight, Test must
  // wait for it to settle before sending the SDK probe so the gateway sees
  // the latest yaml snapshot.
  saveStatus?: SaveStatus
  onTest: () => void
  onDeleteRole: () => void
  onUpdateRouteOrder: (nextOrder: string[]) => void
  onRemoveModelGroup: () => void
  onNavigateToApiKeys?: () => void
}) {
  // R-F17: per-card a11y text needs i18n so it tracks the active language.
  const { t } = useTranslation("settings")
  const compatibleRoutes = compatibleRoutesForRole(modelGroup)
  const readyCount = copilotBackendReadyCount(compatibleRoutes, routeStatusOverrides)
  // R-F7: disable Test while debounced roles-save is still pending/saving so
  // the gateway resolver sees the snapshot the user just authored.
  const saveInFlight = saveStatus === "pending" || saveStatus === "saving"
  // R-F21: longest cooldown across compatible routes drives the countdown
  // label and the Test Button's disabled state. Falls back to 0 (no cooldown).
  const maxCooldownSeconds = compatibleRoutes.reduce((max, route) => {
    const seconds = routeCooldowns[route.id]
    return typeof seconds === "number" && seconds > max ? seconds : max
  }, 0)
  const isCoolingDown = maxCooldownSeconds > 0
  // R-F12: per-card warning when there are eligible routes but none ready
  // yet — guide the user to single-test them in API Keys.
  const showUntestedWarning =
    readyCount === 0 && compatibleRoutes.length > 0

  return (
    <Card
      size="sm"
      className="min-w-0 rounded-md"
      data-copilot-role-card="true"
      data-copilot-role-source={role.source}
    >
      <CardHeader className="!grid-cols-1 items-start gap-2 sm:!grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <CardTitle className="flex min-w-0 flex-wrap items-center gap-2">
            {role.title}
            <Badge variant="secondary">{role.source === "built_in" ? "Built-in" : "Third-party"}</Badge>
          </CardTitle>
          <CardDescription>Coding copilot role synced with backend fallback chain.</CardDescription>
          {showUntestedWarning ? (
            <button
              type="button"
              data-copilot-untested-warning="true"
              className="mt-1 inline-flex items-center gap-1 text-xs text-amber-600 underline-offset-2 hover:underline disabled:cursor-default disabled:no-underline"
              onClick={onNavigateToApiKeys}
              disabled={!onNavigateToApiKeys}
            >
              {t("copilot.untestedRoutesCta", {
                count: compatibleRoutes.length,
                defaultValue:
                  compatibleRoutes.length === 1
                    ? "{{count}} route has not been tested. Test it in API Keys."
                    : "{{count}} routes have not been tested. Test them in API Keys.",
              })}
            </button>
          ) : null}
        </div>
        <CardAction className="row-start-2 flex flex-wrap items-center gap-2 justify-self-start sm:row-start-1 sm:justify-self-end">
          <Badge variant={readyCount === compatibleRoutes.length ? "success" : "outline"}>
            {readyCount}/{compatibleRoutes.length} SDK Ready
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
                  total: compatibleRoutes.length,
                })}
          </span>
          {role.source === "third_party" ? (
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
  modelGroups,
  onSelectModelGroup,
  onDeleteRole,
}: {
  role: { id: string; title: string; source: "built_in" | "third_party" }
  modelGroups: CopilotRolePreview[]
  onSelectModelGroup: (modelGroupId: string) => void
  onDeleteRole: () => void
}) {
  const [open, setOpen] = useState(false)
  const hasGroups = modelGroups.length > 0

  return (
    <Card
      size="sm"
      className="min-w-0 rounded-md border-dashed bg-card/70"
      data-copilot-empty-role-card="true"
      data-copilot-role-card="true"
      data-copilot-role-source={role.source}
    >
      <CardHeader className="!grid-cols-1 items-start gap-2 sm:!grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <CardTitle className="flex min-w-0 flex-wrap items-center gap-2">
            {role.title}
            <Badge variant="secondary">{role.source === "built_in" ? "Built-in" : "Third-party"}</Badge>
          </CardTitle>
          <CardDescription>Select one model group to configure the Copilot fallback chain.</CardDescription>
        </div>
        {role.source === "third_party" ? (
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
      <CardContent>
        <FieldGroup>
          <Field orientation="responsive" className="items-start">
            <FieldContent>
              <FieldLabel>Model group</FieldLabel>
              <FieldDescription>Only groups with Anthropic-compatible routes are listed.</FieldDescription>
            </FieldContent>
            <Popover open={open} onOpenChange={setOpen}>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  role="combobox"
                  aria-expanded={open}
                  disabled={!hasGroups}
                  data-copilot-model-group-select="true"
                  className="w-full min-w-0 justify-between font-normal sm:w-64"
                >
                  <span className="truncate text-muted-foreground">
                    {hasGroups ? "Choose model group" : "No compatible model groups"}
                  </span>
                  <ChevronsUpDown className="ml-2 size-3.5 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-[min(20rem,var(--radix-popover-trigger-width))] p-0">
                <Command filter={copilotGroupComboboxFilter}>
                  <CommandInput placeholder="Search model groups…" data-copilot-model-group-search="true" />
                  <CommandList>
                    <CommandEmpty>No model group found.</CommandEmpty>
                    <CommandGroup>
                      {modelGroups.map((modelGroup) => (
                        <CommandItem
                          key={modelGroup.id}
                          value={copilotGroupSearchValue(modelGroup)}
                          data-copilot-model-option={modelGroup.id}
                          onSelect={() => {
                            onSelectModelGroup(modelGroup.id)
                            setOpen(false)
                          }}
                        >
                          {modelGroup.modelLabel}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </Field>
        </FieldGroup>
      </CardContent>
    </Card>
  )
}

/** Compact, separator-insensitive normalization for combobox matching (§2.1 parity). */
export function normalizeForSearch(value: string): string {
  return value.toLowerCase().replace(/[\s\-_./:]+/g, "")
}

/** Searchable haystack for a copilot group: display name + canonical id + provider labels + model ids (atom-63 ②). */
export function copilotGroupSearchValue(group: CopilotRolePreview): string {
  return [
    group.modelLabel,
    group.id,
    ...group.availableRoutes.flatMap((route) => [route.providerLabel, route.providerModelId]),
  ].join(" ")
}

/** cmdk filter: every search token must appear in the haystack (multi-token AND, separator-insensitive). */
export function copilotGroupComboboxFilter(value: string, search: string): number {
  const haystack = normalizeForSearch(value)
  const tokens = search.toLowerCase().split(/\s+/).filter(Boolean)
  if (tokens.length === 0) return 1
  return tokens.every((token) => haystack.includes(normalizeForSearch(token))) ? 1 : 0
}

function compatibleRoutesForRole(role: CopilotRolePreview): CopilotRoutePreview[] {
  return role.availableRoutes
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
