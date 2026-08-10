import { memo, useCallback, useMemo, useState } from "react"
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
import { ChevronDown, Layers3, Loader2, MoreVertical, Pencil, Trash2 } from "lucide-react"
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
import { useDeleteConfirm, type DeleteConfirmRequest } from "@/components/ui/delete-confirm-dialog"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import type { CredentialsState, MaterializationReportEntry, ModelBundleEntry, ModelGroup, ProviderModelOption, RolesData } from "@/api/llm"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import {
  modelDropFailureMessage,
  reorderModelInRole,
} from "../role-utils"
import { handleAvailableModelDragOver, readAvailableModelDropId } from "../available-model-pointer-drag"
import {
  appendModelGroupToBundle,
  bundleRoleName,
  commitBundleRoleData,
  renameModelBundle,
  rolesDataWithBundleRole,
  toggleBundleModelFallback,
  updateBundleIntent,
} from "../model-bundle-utils"
import { ModelItem } from "./ModelItem"
import { roleEffortLevels, roleTokenLimitSummary } from "./RoleCard"
import { RoleNameDialog } from "./RoleNameDialog"
import { RoleSettingsPanel } from "./RoleSettingsDialog"

export function buildModelBundleDeleteRequest(
  bundle: ModelBundleEntry,
  bundleId: string,
  onDeleteBundle: (bundleId: string) => void,
): DeleteConfirmRequest {
  return {
    title: `Delete ${bundle.display_name || bundleId}?`,
    description: "Remove this model bundle and its route arrangement.",
    onConfirm: () => onDeleteBundle(bundleId),
  }
}

export const ModelBundleCard = memo(function ModelBundleCard({
  bundle,
  bundleId,
  data,
  credentialsByCode,
  modelDisplayNamesByCode,
  providerModelsByRouteId,
  testStatuses = {},
  testRunning = false,
  bundleTestError,
  onRunTest,
  getActiveAvailableModelDragId,
  getAvailableModelGroup,
  onChange,
  onDeleteBundle,
}: {
  bundle: ModelBundleEntry
  bundleId: string
  data: RolesData
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  modelDisplayNamesByCode: ReadonlyMap<string, string>
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>
  testStatuses?: RoleChainStatusMap
  testRunning?: boolean
  bundleTestError?: string
  onRunTest?: (bundleId: string) => void
  getActiveAvailableModelDragId: () => string | null
  getAvailableModelGroup: (modelGroupId: string) => ModelGroup | null
  onChange: (next: RolesData) => void
  onDeleteBundle: (bundleId: string) => void
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [actionsOpen, setActionsOpen] = useState(false)
  const { confirm: confirmDelete, dialog: deleteDialog } = useDeleteConfirm()
  const roleName = bundleRoleName(bundleId)
  const bundleRoleData = useMemo(
    () => rolesDataWithBundleRole(data, bundleId),
    [bundleId, data],
  )
  const role = bundleRoleData.roles[roleName]
  const modelCodes = useMemo(() => Object.keys(role?.models ?? {}), [role?.models])
  const roleFitByRouteId = useMemo<ReadonlyMap<string, MaterializationReportEntry>>(() => (
    new Map((bundle.materialization_report?.entries ?? []).map((entry) => [entry.route_id, entry]))
  ), [bundle.materialization_report?.entries])
  const tokenLimitSummary = useMemo(
    () => role ? roleTokenLimitSummary(role, providerModelsByRouteId) : {
      context: {
        knownCount: 0,
        totalCount: 0,
        min: null,
        max: null,
      },
      output: {
        knownCount: 0,
        totalCount: 0,
        min: null,
        max: null,
      },
    },
    [providerModelsByRouteId, role],
  )
  const effortLevels = useMemo(
    () => role ? roleEffortLevels(role, providerModelsByRouteId) : [],
    [providerModelsByRouteId, role],
  )
  const ownedProviderCodesByModel = useMemo<ReadonlyMap<string, ReadonlySet<string>>>(() => {
    const result = new Map<string, ReadonlySet<string>>()
    for (const modelCode of modelCodes) {
      result.set(
        modelCode,
        new Set(bundleRoleData.models[modelCode] ? Object.keys(bundleRoleData.models[modelCode].providers) : []),
      )
    }
    return result
  }, [bundleRoleData.models, modelCodes])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleRunTest = useCallback(() => {
    onRunTest?.(bundleId)
  }, [bundleId, onRunTest])

  function commitRoleLikeData(nextRoleData: RolesData) {
    onChange(commitBundleRoleData(data, bundleId, nextRoleData))
  }

  function handleAvailableModelDrop(event: Parameters<typeof readAvailableModelDropId>[0]) {
    const modelId = readAvailableModelDropId(event, getActiveAvailableModelDragId)
    if (modelId?.startsWith("bundle:")) {
      toast.error(modelDropFailureMessage({
        modelId,
        destination: bundle.display_name || bundleId,
        reason: "model bundles cannot be nested",
      }))
      return
    }
    const modelGroup = modelId ? getAvailableModelGroup(modelId) : null
    if (!modelGroup) {
      toast.error(modelDropFailureMessage({
        modelId: modelId || "unknown model",
        destination: bundle.display_name || bundleId,
        reason: "source is no longer available",
      }))
      return
    }
    onChange(appendModelGroupToBundle(data, bundleId, modelGroup))
  }

  if (!role) return null

  return (
    <Collapsible open={settingsOpen} onOpenChange={setSettingsOpen}>
      {deleteDialog}
      <Card
        size="sm"
        className="relative rounded-md"
        data-model-bundle-card="true"
        data-model-bundle-id={bundleId}
        data-model-drop-zone="true"
        data-model-drop-fallback="active-drag-ref"
        onDragOver={handleAvailableModelDragOver}
        onDrop={handleAvailableModelDrop}
      >
        <CardHeader className="!grid-cols-1 items-center gap-2 sm:!grid-cols-[minmax(0,1fr)_auto] sm:gap-3">
          <CollapsibleTrigger
            data-model-bundle-settings-toggle="true"
            className="group col-start-1 row-start-1 flex h-8 min-w-0 items-center gap-2 rounded-md px-1 text-left outline-none transition-colors hover:bg-muted/25 focus-visible:ring-2 focus-visible:ring-ring/50"
            aria-label={`Toggle settings for ${bundle.display_name || bundleId}`}
          >
            <Layers3 aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
            <CardTitle className="min-w-0 break-all">{bundle.display_name || bundleId}</CardTitle>
            <ChevronDown
              aria-hidden="true"
              className="ml-auto size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
            />
          </CollapsibleTrigger>
          <CardAction className="col-start-1 row-start-2 flex h-8 flex-nowrap items-center justify-start gap-2 self-center sm:col-start-2 sm:row-start-1 sm:justify-end">
            {onRunTest ? (
              <Button
                type="button"
                variant="default"
                size="default"
                data-model-bundle-test-trigger="true"
                className="min-w-20 shrink-0"
                disabled={testRunning}
                onClick={handleRunTest}
              >
                {testRunning ? <Loader2 className="size-3 animate-spin" /> : null}
                {testRunning ? "Testing" : "Test"}
              </Button>
            ) : null}
            <DropdownMenu open={actionsOpen} onOpenChange={setActionsOpen}>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  data-model-bundle-actions-trigger="true"
                  aria-label={`More actions for ${bundle.display_name || bundleId}`}
                  className="shrink-0 text-muted-foreground"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => event.stopPropagation()}
                >
                  <MoreVertical data-role-icon="true" className="text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-36" onClick={(event) => event.stopPropagation()}>
                <DropdownMenuItem data-model-bundle-edit-trigger="true" onSelect={() => setEditOpen(true)}>
                  <Pencil data-role-icon="true" />
                  Edit
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  data-model-bundle-delete-trigger="true"
                  variant="destructive"
                  onSelect={() => {
                    setActionsOpen(false)
                    confirmDelete(buildModelBundleDeleteRequest(bundle, bundleId, onDeleteBundle))
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
          data-model-bundle-settings-panel="true"
          className="border-t border-border/60 px-3 py-3 data-[state=closed]:hidden"
        >
          <RoleSettingsPanel
            roleName={`bundle-${bundleId}`}
            modelFallbackEnabled={bundle.model_fallback_enabled ?? true}
            intent={bundle.intent}
            effortLevels={effortLevels}
            tokenLimitSummary={tokenLimitSummary}
            onModelFallbackChange={(checked) => onChange(toggleBundleModelFallback(data, bundleId, checked))}
            onSubmit={(intent) => onChange(updateBundleIntent(data, bundleId, intent))}
          />
        </CollapsibleContent>

        <CardContent
          data-model-drop-zone="true"
          data-model-drop-fallback="active-drag-ref"
          onDragOver={handleAvailableModelDragOver}
          onDrop={handleAvailableModelDrop}
          className="space-y-4"
        >
          {bundleTestError ? (
            <div
              data-model-bundle-test-error="true"
              className="rounded-md border border-destructive-border bg-destructive-background/10 px-3 py-2 text-xs text-destructive"
            >
              Bundle Test failed: {bundleTestError}
            </div>
          ) : null}
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={(event) => {
              const activeId = String(event.active.id)
              const overId = event.over?.id ? String(event.over.id) : ""
              if (overId && activeId !== overId) {
                commitRoleLikeData(reorderModelInRole(bundleRoleData, roleName, activeId, overId))
              }
            }}
          >
            <SortableContext items={modelCodes} strategy={verticalListSortingStrategy}>
              <div className="space-y-3" role="list" aria-label={`${bundle.display_name || bundleId} model group order`}>
                {modelCodes.map((modelCode, modelIndex) => {
                  const modelName = modelDisplayNamesByCode.get(modelCode) ?? bundleRoleData.models[modelCode]?.name ?? modelCode
                  return (
                    <ModelItem
                      key={modelCode}
                      data={bundleRoleData}
                      roleName={roleName}
                      modelCode={modelCode}
                      modelName={modelName}
                      modelIndex={modelIndex}
                      credentialsByCode={credentialsByCode}
                      ownedProviderCodes={ownedProviderCodesByModel.get(modelCode)}
                      providerModelsByRouteId={providerModelsByRouteId}
                      roleFitByRouteId={roleFitByRouteId}
                      testStatuses={testStatuses}
                      onChange={commitRoleLikeData}
                    />
                  )
                })}
              </div>
            </SortableContext>
          </DndContext>
          <Empty
            aria-label={`Drop model group into ${bundle.display_name || bundleId}`}
            data-model-drop-target="true"
            onDragOver={handleAvailableModelDragOver}
            onDrop={handleAvailableModelDrop}
            className="min-h-16 flex-none select-none gap-1 rounded-md border border-dashed border-border bg-muted/10 p-3 text-muted-foreground transition-colors hover:bg-muted/20"
          >
            <EmptyHeader className="max-w-none gap-0">
              <EmptyTitle className="text-xs font-medium text-muted-foreground">Drop model group</EmptyTitle>
            </EmptyHeader>
          </Empty>
        </CardContent>
        <RoleNameDialog
          title="Edit model bundle"
          fieldLabel="Bundle name"
          initialName={bundle.display_name || bundleId}
          existingNames={Object.values(data.model_bundles ?? {}).map((entry) => entry.display_name)}
          open={editOpen}
          onOpenChange={setEditOpen}
          onSubmit={(nextName) => onChange(renameModelBundle(data, bundleId, nextName))}
        />
      </Card>
    </Collapsible>
  )
})
