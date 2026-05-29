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
  const providerItems = useMemo(
    () => providers.map((providerCode, index) => providerItemId(providerCode, index)),
    [providers],
  )
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const providerLabels = useMemo(
    () => Object.fromEntries(
      appendableProviderCodes.map((providerCode) => [
        providerCode,
        data.providers[providerCode]?.name ?? providerCode,
      ]),
    ),
    [appendableProviderCodes, data.providers],
  )

  function handleDragEnd(event: DragEndEvent) {
    const activeIndex = providerItems.indexOf(String(event.active.id))
    const overIndex = event.over?.id ? providerItems.indexOf(String(event.over.id)) : -1
    if (activeIndex >= 0 && overIndex >= 0 && activeIndex !== overIndex) {
      onChange(reorderProviderInRole(data, roleName, modelCode, activeIndex, overIndex))
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
          {providers.map((providerCode, index) => (
            <ProviderTag
              key={`${providerCode}-${index}`}
              id={providerItemId(providerCode, index)}
              data={data}
              roleName={roleName}
              modelCode={modelCode}
              providerCode={providerCode}
              index={index}
              providerModel={providerModels.get(providerCode)}
              roleFitEntry={roleFits.get(providerCode)}
              testStatus={testStatuses[roleChainStatusKey(modelCode, providerCode)]}
              onChange={onChange}
            />
          ))}
          <AddProviderMenu
            providerCodes={appendableProviderCodes}
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

  return (
    <div
      ref={setNodeRef}
      style={style}
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
          {roleRouteStatus ? <RoleRouteStatusLight status={roleRouteStatus} detail={statusDetail} /> : null}
          <IconTooltip label={`Remove ${providerName || providerCode}`}>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={`Remove ${providerName || providerCode}`}
              className="text-muted-foreground hover:text-foreground"
              onClick={() => onChange(removeProviderFromRole(data, roleName, modelCode, index))}
            >
              <Trash2 data-role-icon="true" className="size-3 text-muted-foreground" />
            </Button>
          </IconTooltip>
        </ItemActions>
      </Item>
    </div>
  )
})

function ProviderName({ label }: { label: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <ItemTitle
            data-provider-title-tooltip="true"
            className="line-clamp-none block w-full truncate whitespace-nowrap text-xs/relaxed text-muted-foreground"
          >
            {label}
          </ItemTitle>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm break-words">{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
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
