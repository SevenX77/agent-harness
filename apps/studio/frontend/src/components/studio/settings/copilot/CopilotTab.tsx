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
import { SectionTitle } from "../shared"
import { CopilotModelGroupCard } from "./CopilotModelGroupCard"
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
  copilotRouteStatusesFromJob,
  copilotRouteStatusesFromPersistedResult,
  runCopilotRoleTestJob,
  type CopilotRouteJobStatus,
} from "./copilot-role-test"
import { Skeleton } from "@/components/ui/skeleton"
import { getRoleTestResults } from "@/api/client"
import type { CredentialsState, ModelGroup, RolesData } from "@/api/llm"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"

export function copilotBackendReadyCount(
  routes: Array<Pick<CopilotRoutePreview, "agentStatus" | "id">>,
  routeStatusOverrides: Record<string, CopilotRouteJobStatus> = {},
): number {
  void routeStatusOverrides
  return routes.filter((route) => route.agentStatus === "ready").length
}

export function CopilotTab({
  data = null,
  credentials = { providers: [] },
  modelGroups = [],
  onChange = () => {},
  saveStatus = "idle",
  error = null,
}: {
  data?: RolesData | null
  credentials?: CredentialsState
  modelGroups?: ModelGroup[]
  onChange?: (next: RolesData) => void
  saveStatus?: SaveStatus
  error?: string | null
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
        for (const entry of Object.values(persisted.results ?? {})) {
          Object.assign(seeded, copilotRouteStatusesFromPersistedResult(entry.result))
        }
        if (Object.keys(seeded).length === 0) return
        setRouteStatusOverrides((current) => ({ ...seeded, ...current }))
      })
      .catch(() => {
        // Seeding is best-effort; the live test flow remains fully functional.
      })
    return () => {
      cancelled = true
    }
  }, [])

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
  function ensureRolePersisted(current: RolesData, roleId: string): RolesData {
    if (current.roles[roleId]) return current
    const group = claudeModelGroups.find((candidate) => candidate.id === roleId)
    if (!group) return current
    return { ...current, roles: { ...current.roles, [roleId]: buildCopilotRoleEntry(group) } }
  }

  function removeModelGroup(roleId: string) {
    if (!data) return
    const base = ensureRolePersisted(data, roleId)
    const role = base.roles[roleId]
    if (!role) return
    // #61: single-group constraint → "remove group" = deselect back to an empty
    // card (role + role_kind preserved), NOT deleting the role (#64).
    const nextRoles = { ...base.roles, [roleId]: { ...role, active_model: "", models: {}, fallback_chain: [] } }
    onChange({ ...base, roles: nextRoles })
  }

  function updateRouteOrder(roleId: string, nextOrder: string[]) {
    if (!data) return
    const base = ensureRolePersisted(data, roleId)
    const nextRoles = { ...base.roles }
    const role = nextRoles[roleId]
    if (!role) return

    const activeModelGroupId = Object.keys(role.models ?? {})[0] || role.active_model || roleId

    nextRoles[roleId] = {
      ...role,
      fallback_chain: nextOrder.map((routeId) => ({
        route_id: routeId,
        runtime_settings: {},
      })),
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
    const nextIndex = Object.keys(data.roles).filter(k => k.startsWith("copilot_custom_")).length + 1
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
      onConfirm: () => {
        if (!data) return
        const nextRoles = { ...data.roles }
        delete nextRoles[role.id]
        onChange({ ...data, roles: nextRoles })
      },
    })
  }

  async function testRoleRoutes(role: { id: string; title: string }) {
    // A floated built-in default enters the save chain when tested (atom-56 ①).
    if (data && !data.roles[role.id]) {
      onChange(ensureRolePersisted(data, role.id))
    }
    setTestingRoleIds((current) => {
      const next = new Set(current)
      next.add(role.id)
      return next
    })
    try {
      const result = await runCopilotRoleTestJob(role.id, {
        onProgress: (job) => {
          setRouteStatusOverrides((current) => ({
            ...current,
            ...copilotRouteStatusesFromJob(job),
          }))
        },
      })
      if (result.status === "ok") {
        toast.success(`${role.title} test passed`)
      } else {
        toast.warning(`${role.title} test needs attention`)
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

  return (
    <div data-copilot-settings-page="true" className="max-w-3xl min-w-0">
      <SectionTitle
        title={t("copilot.title")}
        description={t("copilot.description")}
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      {error ? <div className="mb-3 text-xs text-destructive">{t("llmRoles.validationFailed", { error })}</div> : null}

      <CatalogAccordion type="multiple" defaultValue={["claude-agent-sdk"]}>
        <CatalogAccordionItem value="claude-agent-sdk">
          <CatalogAccordionTrigger>
            {t("copilot.claudeAgentSdk")}
          </CatalogAccordionTrigger>
          <CatalogAccordionContent className="-mx-2 space-y-4 pb-5">
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
                  isTesting={testingRoleIds.has(role.id)}
                  onTest={() => testRoleRoutes(role)}
                  onDeleteRole={() => requestDeleteCopilotRole(role)}
                  onUpdateRouteOrder={(nextOrder) => updateRouteOrder(role.id, nextOrder)}
                  onRemoveModelGroup={() => removeModelGroup(role.id)}
                />
              )
            })}
            <Button
              type="button"
              variant="default"
              data-copilot-model-add-trigger="true"
              className="gap-1"
              onClick={addDraftCopilotRole}
            >
              <Plus data-role-icon="true" className="size-3.5 text-primary-foreground/80" />
              Add model
            </Button>
          </CatalogAccordionContent>
        </CatalogAccordionItem>
      </CatalogAccordion>
    </div>
  )
}

function CopilotRoleCard({
  role,
  modelGroup,
  routeOrder,
  chainRoutes,
  appendableRoutes,
  routeStatusOverrides,
  isTesting,
  onTest,
  onDeleteRole,
  onUpdateRouteOrder,
  onRemoveModelGroup,
}: {
  role: { id: string; title: string; source: "built_in" | "third_party" }
  modelGroup: CopilotRolePreview
  routeOrder: string[]
  chainRoutes: CopilotRoutePreview[]
  appendableRoutes: CopilotRoutePreview[]
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>
  isTesting: boolean
  onTest: () => void
  onDeleteRole: () => void
  onUpdateRouteOrder: (nextOrder: string[]) => void
  onRemoveModelGroup: () => void
}) {
  const compatibleRoutes = compatibleRoutesForRole(modelGroup)
  const readyCount = copilotBackendReadyCount(compatibleRoutes, routeStatusOverrides)

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
            onClick={onTest}
            disabled={isTesting}
          >
            {isTesting ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <FlaskConical data-icon="inline-start" />}
            {isTesting ? "Testing" : "Test"}
          </Button>
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
