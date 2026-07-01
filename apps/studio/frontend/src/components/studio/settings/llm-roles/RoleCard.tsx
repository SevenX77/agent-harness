import { memo, useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type MouseEvent, type PointerEvent } from "react"
import { toast } from "sonner"
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core"
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { Bot, ChevronDown, Cog, FlaskConical, Layers3, Loader2, MoreVertical, Pencil, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { requestDeleteConfirmationToast } from "@/components/ui/delete-confirm-toast"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import type { CredentialsState, MaterializationReportEntry, ModelGroup, ProviderModelOption, RoleTestResponse, RolesData } from "@/api/llm"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import {
  AVAILABLE_MODEL_DRAG_TYPE,
  appendModelGroupToRoleWithResult,
  modelDropFailureMessage,
  renameRole,
  reorderModelInRole,
  toggleModelFallback,
  updateRoleIntent,
} from "../role-utils"
import { ModelItem } from "./ModelItem"
import { RoleNameDialog } from "./RoleNameDialog"
import { RoleSettingsPanel, type RoleTokenLimitSummary } from "./RoleSettingsDialog"

export type RoleCategory = "graph-agent" | "copilot"

const EMPTY_PROVIDER_MODELS_BY_ROUTE_ID: ReadonlyMap<string, ProviderModelOption> = new Map()

export function requestRoleDeleteConfirmation(
  roleName: string,
  onDeleteRole: (roleName: string) => void,
) {
  requestDeleteConfirmationToast({
    id: `delete-role-${roleName}`,
    title: `Delete ${roleName}?`,
    description: `Remove ${roleName} and its model fallback chain.`,
    onConfirm: () => onDeleteRole(roleName),
  })
}

export const RoleCard = memo(function RoleCard({
  data,
  category,
  credentialsByCode,
  modelDisplayNamesByCode,
  ownedProviderCodesByModel,
  providerModelsByRouteId = EMPTY_PROVIDER_MODELS_BY_ROUTE_ID,
  roleName,
  testStatuses = {},
  testChainRunning = false,
  roleTestError,
  onRunTestChain,
  getActiveAvailableModelDragId,
  getAvailableModelGroup,
  onChange,
  onDeleteRole,
}: {
  data: RolesData
  category: RoleCategory
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  modelDisplayNamesByCode: ReadonlyMap<string, string>
  ownedProviderCodesByModel: ReadonlyMap<string, ReadonlySet<string>>
  providerModelsByRouteId?: ReadonlyMap<string, ProviderModelOption>
  roleName: string
  testStatuses?: RoleChainStatusMap
  testChainRunning?: boolean
  roleTestResult?: RoleTestResponse
  roleTestError?: string
  onRunTestChain: (roleName: string) => void
  getActiveAvailableModelDragId: () => string | null
  getAvailableModelGroup: (modelGroupId: string) => ModelGroup | null
  onChange: (next: RolesData) => void
  onDeleteRole: (roleName: string) => void
}) {
  const role = data.roles[roleName]
  const modelCodes = useMemo(() => Object.keys(role.models), [role.models])
  // #51: a role linked to a bundle by reference shows a "Linked to bundle X"
  // badge. The chain is materialized from the live bundle (not a snapshot), so an
  // edit to the bundle reflects here after re-projection.
  const linkedBundle = useMemo(() => (
    role.bundle_id ? data.model_bundles?.[role.bundle_id] ?? null : null
  ), [data.model_bundles, role.bundle_id])
  const linkedBundleLabel = role.bundle_id
    ? linkedBundle?.display_name || role.bundle_id
    : null
  const [editOpen, setEditOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [actionsOpen, setActionsOpen] = useState(false)
  const actionsOpenTimerRef = useRef<number | null>(null)
  const RoleIcon = category === "copilot" ? Bot : Cog
  const roleFitByRouteId = useMemo<ReadonlyMap<string, MaterializationReportEntry>>(() => (
    new Map((role.materialization_report?.entries ?? []).map((entry) => [entry.route_id, entry]))
  ), [role.materialization_report?.entries])
  const tokenLimitSummary = useMemo(
    () => roleTokenLimitSummary(role, providerModelsByRouteId),
    [providerModelsByRouteId, role],
  )
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleRunTestChain = useCallback(() => {
    onRunTestChain(roleName)
  }, [onRunTestChain, roleName])

  function handleAvailableModelDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    event.dataTransfer.dropEffect = "copy"
  }

  function handleAvailableModelDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    const modelId = event.dataTransfer.getData(AVAILABLE_MODEL_DRAG_TYPE) ||
      event.dataTransfer.getData("text/plain") ||
      getActiveAvailableModelDragId()
    const modelGroup = modelId ? getAvailableModelGroup(modelId) : null
    if (!modelGroup) {
      toast.error(modelDropFailureMessage({
        modelId: modelId || "unknown model",
        destination: roleName,
        reason: "source is no longer available",
      }))
      return
    }
    const result = appendModelGroupToRoleWithResult(data, roleName, modelGroup)
    if (result.error) {
      toast.error(result.error)
      return
    }
    onChange(result.data)
  }

  function clearActionsOpenTimer() {
    if (actionsOpenTimerRef.current !== null) {
      window.clearTimeout(actionsOpenTimerRef.current)
      actionsOpenTimerRef.current = null
    }
  }

  function handleActionsPointerDown(event: PointerEvent<HTMLButtonElement>) {
    event.preventDefault()
    event.stopPropagation()
  }

  function handleActionsClick(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault()
    event.stopPropagation()
    clearActionsOpenTimer()
    if (event.detail > 1) {
      setActionsOpen(false)
      event.currentTarget.blur()
      return
    }
    actionsOpenTimerRef.current = window.setTimeout(() => {
      setActionsOpen((current) => !current)
      actionsOpenTimerRef.current = null
    }, 180)
  }

  function handleActionsDoubleClick(event: MouseEvent<HTMLButtonElement>) {
    event.preventDefault()
    event.stopPropagation()
    clearActionsOpenTimer()
    setActionsOpen(false)
    event.currentTarget.blur()
  }

  useEffect(() => () => {
    if (actionsOpenTimerRef.current !== null) {
      window.clearTimeout(actionsOpenTimerRef.current)
      actionsOpenTimerRef.current = null
    }
  }, [])

  return (
    <Collapsible open={settingsOpen} onOpenChange={setSettingsOpen}>
      <Card
        size="sm"
        className="relative rounded-md"
        data-role-name={roleName}
        data-model-drop-zone="true"
        data-model-drop-fallback="active-drag-ref"
        onDragOver={handleAvailableModelDragOver}
        onDrop={handleAvailableModelDrop}
      >
        <div
          aria-hidden="true"
          data-role-drop-shield="true"
          data-model-drop-zone="true"
          data-model-drop-fallback="active-drag-ref"
          className="pointer-events-none absolute inset-0 z-10 hidden rounded-md"
        />
        <CardHeader className="!grid-cols-1 items-center gap-2 sm:!grid-cols-[minmax(0,1fr)_auto] sm:gap-3">
          <CollapsibleTrigger
            data-role-settings-toggle="true"
            data-role-card-title-row="true"
            className="group col-start-1 row-start-1 flex h-8 min-w-0 items-center gap-2 rounded-md px-1 text-left outline-none transition-colors hover:bg-muted/25 focus-visible:ring-2 focus-visible:ring-ring/50"
            aria-label={`Toggle settings for ${roleName}`}
          >
            <RoleIcon
              aria-hidden="true"
              data-role-title-icon="true"
              className="size-3.5 shrink-0 text-muted-foreground"
            />
            <CardTitle className="min-w-0 break-all">{roleName}</CardTitle>
            <ChevronDown
              aria-hidden="true"
              className="ml-auto size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
            />
          </CollapsibleTrigger>
          <CardAction
            data-role-header-actions="true"
            className="col-start-1 row-start-2 row-span-1 flex h-8 flex-nowrap items-center justify-start gap-2 self-center sm:col-start-2 sm:row-start-1 sm:justify-end"
          >
            <Button
              type="button"
              variant="default"
              size="default"
              data-role-test-trigger="true"
              className="min-w-20 shrink-0"
              disabled={testChainRunning}
              onClick={handleRunTestChain}
            >
              {testChainRunning
                ? <Loader2 data-role-test-icon="true" className="size-3 animate-spin" />
                : <FlaskConical data-role-test-icon="true" className="size-3.5" />}
              {testChainRunning ? "Testing" : "Test"}
            </Button>
            <DropdownMenu open={actionsOpen} onOpenChange={setActionsOpen}>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  data-role-actions-trigger="true"
                  aria-label={`More actions for ${roleName}`}
                  className="shrink-0 text-muted-foreground"
                  onClick={handleActionsClick}
                  onDoubleClick={handleActionsDoubleClick}
                  onPointerDown={handleActionsPointerDown}
                  onKeyDown={(event) => event.stopPropagation()}
                >
                  <MoreVertical data-role-icon="true" className="text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="w-36"
                onClick={(event) => event.stopPropagation()}
              >
                <DropdownMenuItem data-role-edit-trigger="true" onSelect={() => setEditOpen(true)}>
                  <Pencil data-role-icon="true" />
                  Rename
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  data-role-delete-trigger="true"
                  variant="destructive"
                  onSelect={() => {
                    setActionsOpen(false)
                    requestRoleDeleteConfirmation(roleName, onDeleteRole)
                  }}
                >
                  <Trash2 />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </CardAction>
        </CardHeader>
        <CollapsibleContent
          forceMount
          data-role-settings-panel="true"
          className="border-t border-border/60 px-3 py-3 data-[state=closed]:hidden"
        >
          <RoleSettingsPanel
            roleName={roleName}
            modelFallbackEnabled={role.model_fallback_enabled}
            intent={role.intent}
            tokenLimitSummary={tokenLimitSummary}
            onModelFallbackChange={(checked) => onChange(toggleModelFallback(data, roleName, checked))}
            onSubmit={(intent) => onChange(updateRoleIntent(data, roleName, intent))}
          />
        </CollapsibleContent>

      <CardContent
        data-model-drop-zone="true"
        data-model-drop-fallback="active-drag-ref"
        onDragOver={handleAvailableModelDragOver}
        onDrop={handleAvailableModelDrop}
        className="space-y-4"
      >
        {roleTestError ? (
          <div
            data-role-test-error="true"
            className="rounded-md border border-destructive-border bg-destructive-background/10 px-3 py-2 text-xs text-destructive"
          >
            Role Test failed: {roleTestError}
          </div>
        ) : null}
        {linkedBundleLabel ? (
          <div
            data-role-linked-bundle="true"
            data-linked-bundle-id={role.bundle_id ?? undefined}
            className="flex items-center gap-1.5 rounded-md border border-border/60 bg-muted/20 px-3 py-1.5 text-xs text-muted-foreground"
          >
            <Layers3 aria-hidden="true" className="size-3.5 shrink-0" />
            <span className="min-w-0 break-all">Linked to bundle: {linkedBundleLabel}</span>
          </div>
        ) : null}
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={(event) => {
            const activeId = String(event.active.id)
            const overId = event.over?.id ? String(event.over.id) : ""
            if (overId && activeId !== overId) {
              onChange(reorderModelInRole(data, roleName, activeId, overId))
            }
          }}
        >
          <SortableContext items={modelCodes} strategy={verticalListSortingStrategy}>
            <div className="space-y-3" role="list" aria-label={`${roleName} model fallback order`}>
              {modelCodes.map((modelCode, modelIndex) => {
                const modelName = modelDisplayNamesByCode.get(modelCode) ?? data.models[modelCode]?.name ?? modelCode
                return (
                  <ModelItem
                    key={modelCode}
                    data={data}
                    roleName={roleName}
                    modelCode={modelCode}
                    modelName={modelName}
                    modelIndex={modelIndex}
                    credentialsByCode={credentialsByCode}
                    ownedProviderCodes={ownedProviderCodesByModel.get(modelCode)}
                    providerModelsByRouteId={providerModelsByRouteId}
                    roleFitByRouteId={roleFitByRouteId}
                    testStatuses={testStatuses}
                    onChange={onChange}
                  />
                )
              })}
            </div>
          </SortableContext>
        </DndContext>
        <Empty
          aria-label={`Drop model into ${roleName}`}
          data-model-drop-target="true"
          onDragOver={handleAvailableModelDragOver}
          onDrop={handleAvailableModelDrop}
          className="min-h-16 flex-none select-none gap-1 rounded-md border border-dashed border-border bg-muted/10 p-3 text-muted-foreground transition-colors hover:bg-muted/20"
        >
          <EmptyHeader className="max-w-none gap-0">
            <EmptyTitle className="text-xs font-medium text-muted-foreground">Drop model</EmptyTitle>
          </EmptyHeader>
        </Empty>
      </CardContent>
      <RoleNameDialog
        title="Rename role"
        initialName={roleName}
        existingNames={Object.keys(data.roles)}
        open={editOpen}
        onOpenChange={setEditOpen}
        onSubmit={(nextRoleName) => onChange(renameRole(data, roleName, nextRoleName))}
      />
      </Card>
    </Collapsible>
  )
})

export function roleTokenLimitSummary(
  role: RolesData["roles"][string],
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>,
): RoleTokenLimitSummary {
  const routeIds = Object.values(role.models).flatMap((model) => model.providers)

  return {
    context: routeTokenLimitSummary(routeIds, providerModelsByRouteId, "max_input_tokens"),
    output: routeTokenLimitSummary(routeIds, providerModelsByRouteId, "max_output_tokens"),
  }
}

function routeTokenLimitSummary(
  routeIds: string[],
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>,
  capabilityKey: "max_input_tokens" | "max_output_tokens",
): RoleTokenLimitSummary["context"] {
  const values = routeIds
    .map((routeId) => providerMaxTokens(providerModelsByRouteId.get(routeId), capabilityKey))
    .filter((value): value is number => value !== null)

  return {
    knownCount: values.length,
    totalCount: routeIds.length,
    min: values.length ? Math.min(...values) : null,
    max: values.length ? Math.max(...values) : null,
  }
}

function providerMaxTokens(
  providerModel: ProviderModelOption | undefined,
  capabilityKey: "max_input_tokens" | "max_output_tokens",
): number | null {
  const value = providerModel?.capabilities[capabilityKey]?.value
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const max = (value as { max?: unknown }).max
  return typeof max === "number" && Number.isFinite(max) ? max : null
}
