import { memo, useMemo } from "react"
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import {
  SortableContext,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { roleChainStatusKey, type RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import type { MaterializationReportEntry, ProviderModelOption, RolesData } from "@/api/llm"
import { appendProviderToModel, removeProviderFromRole, reorderProviderInRole } from "../role-utils"
import { IconTooltip } from "./IconTooltip"
import {
  deriveRoleRouteStatus,
  RoleProviderRouteTooltipContent,
  roleProviderRouteTooltip,
  roleRouteStatusDetail,
  roleRouteStatusSurfaceClass,
  RoleRouteStatusLight,
} from "./role-route-status"

const EMPTY_PROVIDER_MODELS_BY_ROUTE_ID: ReadonlyMap<string, ProviderModelOption> = new Map()
const EMPTY_ROLE_FIT_BY_ROUTE_ID: ReadonlyMap<string, MaterializationReportEntry> = new Map()

export const ProviderChain = memo(function ProviderChain({
  data,
  roleName,
  modelCode,
  modelName,
  providers,
  appendableProviderCodes,
  providerModelsByRouteId,
  roleFitByRouteId,
  testStatuses,
  onChange,
}: {
  data: RolesData
  roleName: string
  modelCode: string
  modelName: string
  providers: string[]
  appendableProviderCodes: string[]
  providerModelsByRouteId?: ReadonlyMap<string, ProviderModelOption>
  roleFitByRouteId?: ReadonlyMap<string, MaterializationReportEntry>
  testStatuses: RoleChainStatusMap
  onChange: (next: RolesData) => void
}) {
  const providerModels = providerModelsByRouteId ?? EMPTY_PROVIDER_MODELS_BY_ROUTE_ID
  const roleFits = roleFitByRouteId ?? EMPTY_ROLE_FIT_BY_ROUTE_ID
  const visibleProviderEntries = useMemo(
    () => collapseProviderEntries(providers, data, providerModels),
    [data, providerModels, providers],
  )
  const providerItems = useMemo(
    () => visibleProviderEntries.map((entry) => providerItemId(entry.providerCode, entry.rawIndex)),
    [visibleProviderEntries],
  )
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const visibleProviderKeys = useMemo(() => new Set(
    visibleProviderEntries.map((entry) => providerDisplayKey(data, entry.providerCode, providerModels)),
  ), [data, providerModels, visibleProviderEntries])
  const visibleAppendableProviderCodes = useMemo(
    () => collapseAppendableProviderCodes(appendableProviderCodes, data, providerModels, visibleProviderKeys),
    [appendableProviderCodes, data, providerModels, visibleProviderKeys],
  )
  const providerLabels = useMemo(
    () => Object.fromEntries(
      visibleAppendableProviderCodes.map((providerCode) => [
        providerCode,
        data.providers[providerCode]?.name ?? providerCode,
      ]),
    ),
    [data.providers, visibleAppendableProviderCodes],
  )

  function handleDragEnd(event: DragEndEvent) {
    const activeEntry = visibleProviderEntries.find((entry) => providerItemId(entry.providerCode, entry.rawIndex) === String(event.active.id))
    const overEntry = event.over?.id
      ? visibleProviderEntries.find((entry) => providerItemId(entry.providerCode, entry.rawIndex) === String(event.over?.id))
      : undefined
    if (activeEntry && overEntry && activeEntry.rawIndex !== overEntry.rawIndex) {
      onChange(reorderProviderInRole(data, roleName, modelCode, activeEntry.rawIndex, overEntry.rawIndex))
    }
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={providerItems} strategy={rectSortingStrategy}>
        <div
          data-provider-grid="true"
          className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,max(12rem,calc((100%_-_0.75rem)/3))),1fr))] justify-start gap-1.5"
          role="list"
          aria-label={`${modelName} provider fallback order`}
        >
          {visibleProviderEntries.map((entry, index) => (
            <ProviderTag
              key={`${entry.providerCode}-${entry.rawIndex}`}
              id={providerItemId(entry.providerCode, entry.rawIndex)}
              data={data}
              roleName={roleName}
              modelCode={modelCode}
              providerCode={entry.providerCode}
              index={index}
              rawIndex={entry.rawIndex}
              providerModel={providerModels.get(entry.providerCode)}
              roleFitEntry={roleFits.get(entry.providerCode)}
              testStatus={testStatuses[roleChainStatusKey(modelCode, entry.providerCode)]}
              onChange={onChange}
            />
          ))}
          <AddProviderMenu
            providerCodes={visibleAppendableProviderCodes}
            providerLabels={providerLabels}
            onAppend={(providerCode) => onChange(appendProviderToModel(data, roleName, modelCode, providerCode))}
          />
        </div>
      </SortableContext>
    </DndContext>
  )
})

const ProviderTag = memo(function ProviderTag({
  id,
  data,
  roleName,
  modelCode,
  providerCode,
  index,
  rawIndex,
  providerModel,
  roleFitEntry,
  testStatus,
  onChange,
}: {
  id: string
  data: RolesData
  roleName: string
  modelCode: string
  providerCode: string
  index: number
  rawIndex: number
  providerModel?: ProviderModelOption
  roleFitEntry?: MaterializationReportEntry
  testStatus?: RoleChainStatusMap[string]
  onChange: (next: RolesData) => void
}) {
  const providerName = data.providers[providerCode]?.name ?? ""
  const roleRouteStatus = deriveRoleRouteStatus({
    providerModel,
    roleFitEntry,
    testStatus: testStatus?.status,
  })
  const statusDetail = roleRouteStatusDetail({
    providerModel,
    roleFitEntry,
    testMessage: testStatus?.message,
  })
  const statusTooltip = roleRouteStatus ? roleProviderRouteTooltip({
    status: roleRouteStatus,
    providerModel,
    fallbackProviderModelId: data.models[modelCode]?.providers[providerCode],
    detail: statusDetail,
  }) : null
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  const row = (
    <div
      ref={setNodeRef}
      style={style}
      data-provider-row-status-tooltip={statusTooltip ? "true" : undefined}
      className={cn("rounded-md", isDragging && "opacity-70")}
    >
      <Item
        variant="muted"
        size="xs"
        data-provider-card="true"
        data-provider-test-status={testStatus?.status}
        data-role-route-status={roleRouteStatus ?? undefined}
        data-dnd-drag-surface="provider"
        className={cn(
          "relative min-h-9 cursor-grab select-none flex-nowrap items-center gap-2 overflow-hidden border-border/70 bg-muted/35 text-muted-foreground active:cursor-grabbing",
          roleRouteStatusSurfaceClass(roleRouteStatus),
        )}
        {...attributes}
        {...listeners}
        role="listitem"
        aria-label={`Reorder ${providerName || providerCode}`}
      >
        <ItemMedia className="size-5 rounded-sm bg-background/80 text-[10px] font-mono text-muted-foreground ring-1 ring-foreground/10">
          {index + 1}
        </ItemMedia>
        <ItemContent className="min-w-0 overflow-hidden gap-0.5">
          <ProviderName label={providerName || providerCode} />
        </ItemContent>
        <ItemActions
          className="ml-auto shrink-0 gap-1"
          onPointerDown={(event) => event.stopPropagation()}
        >
          {roleRouteStatus ? (
            <RoleRouteStatusLight status={roleRouteStatus} detail={statusDetail} showTooltip={false} />
          ) : null}
          <IconTooltip label={`Remove ${providerName || providerCode}`}>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={`Remove ${providerName || providerCode}`}
              className="text-muted-foreground hover:text-foreground"
              onClick={() => onChange(removeProviderFromRole(data, roleName, modelCode, rawIndex))}
            >
              <Trash2 data-role-icon="true" className="size-3 text-muted-foreground" />
            </Button>
          </IconTooltip>
        </ItemActions>
      </Item>
    </div>
  )

  if (!statusTooltip) return row

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{row}</TooltipTrigger>
        <TooltipContent className="max-w-sm break-words">
          <RoleProviderRouteTooltipContent tooltip={statusTooltip} />
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
})

function ProviderName({ label }: { label: string }) {
  return (
    <ItemTitle
      data-provider-title="true"
      className="line-clamp-none block w-full truncate whitespace-nowrap text-xs/relaxed text-muted-foreground"
    >
      {label}
    </ItemTitle>
  )
}

function AddProviderMenu({
  providerCodes,
  providerLabels,
  onAppend,
}: {
  providerCodes: string[]
  providerLabels: Record<string, string>
  onAppend: (providerCode: string) => void
}) {
  if (providerCodes.length === 0) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          data-provider-add-trigger="true"
          className="h-9 w-full justify-start gap-2 rounded-md px-2.5 text-muted-foreground hover:bg-muted/35 hover:text-foreground"
        >
          <Plus data-role-icon="true" className="size-3 text-muted-foreground" />
          Add provider
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {providerCodes.map((providerCode) => (
          <DropdownMenuItem key={providerCode} onSelect={() => onAppend(providerCode)}>
            {providerLabels[providerCode] ?? providerCode}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function providerItemId(providerCode: string, index: number): string {
  return `${providerCode}:${index}`
}

type ProviderEntry = {
  providerCode: string
  rawIndex: number
}

function collapseProviderEntries(
  providers: string[],
  data: RolesData,
  providerModels: ReadonlyMap<string, ProviderModelOption>,
): ProviderEntry[] {
  const byLabel = new Map<string, ProviderEntry>()
  providers.forEach((providerCode, rawIndex) => {
    const entry = { providerCode, rawIndex }
    const key = providerDisplayKey(data, providerCode, providerModels)
    const previous = byLabel.get(key)
    if (!previous || compareProviderEntries(entry, previous, providerModels) < 0) {
      byLabel.set(key, entry)
    }
  })
  return [...byLabel.values()].sort((left, right) => left.rawIndex - right.rawIndex)
}

function collapseAppendableProviderCodes(
  providerCodes: string[],
  data: RolesData,
  providerModels: ReadonlyMap<string, ProviderModelOption>,
  takenKeys: ReadonlySet<string>,
): string[] {
  const byLabel = new Map<string, ProviderEntry>()
  providerCodes.forEach((providerCode, rawIndex) => {
    const key = providerDisplayKey(data, providerCode, providerModels)
    if (takenKeys.has(key)) return
    const entry = { providerCode, rawIndex }
    const previous = byLabel.get(key)
    if (!previous || compareProviderEntries(entry, previous, providerModels) < 0) {
      byLabel.set(key, entry)
    }
  })
  return [...byLabel.values()]
    .sort((left, right) => left.rawIndex - right.rawIndex)
    .map((entry) => entry.providerCode)
}

function compareProviderEntries(
  left: ProviderEntry,
  right: ProviderEntry,
  providerModels: ReadonlyMap<string, ProviderModelOption>,
): number {
  return providerUiStateRank(providerModels.get(left.providerCode)?.ui_state) -
    providerUiStateRank(providerModels.get(right.providerCode)?.ui_state) ||
    left.rawIndex - right.rawIndex ||
    left.providerCode.localeCompare(right.providerCode)
}

function providerDisplayKey(
  data: RolesData,
  providerCode: string,
  providerModels: ReadonlyMap<string, ProviderModelOption>,
): string {
  const label = data.providers[providerCode]?.name ?? providerModels.get(providerCode)?.provider_label ?? providerCode
  return label.trim().toLowerCase() || providerCode
}

function providerUiStateRank(state: ProviderModelOption["ui_state"] | undefined): number {
  if (state === "ready") return 0
  if (state === "historical_ready") return 1
  if (state === "untested") return 2
  if (state === "cooling_down") return 3
  if (state === "failed") return 4
  if (state === "off") return 5
  return 2
}
