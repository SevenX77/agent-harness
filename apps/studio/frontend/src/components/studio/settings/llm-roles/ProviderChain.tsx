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
import type { RolesData } from "@/api/llm"
import { appendProviderToModel, removeProviderFromRole, reorderProviderInRole } from "../role-utils"
import { IconTooltip } from "./IconTooltip"
import { ProviderTestStatusBadge } from "./RoleBadges"

export function ProviderChain({
  data,
  roleName,
  modelCode,
  providers,
  appendableProviderCodes,
  testStatuses,
  onChange,
}: {
  data: RolesData
  roleName: string
  modelCode: string
  providers: string[]
  appendableProviderCodes: string[]
  testStatuses: RoleChainStatusMap
  onChange: (next: RolesData) => void
}) {
  const providerItems = providers.map((providerCode, index) => providerItemId(providerCode, index))
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
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
          className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,12rem),20rem))] justify-start gap-1.5"
          role="list"
          aria-label={`${modelCode} provider fallback order`}
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
              testStatus={testStatuses[roleChainStatusKey(modelCode, providerCode)]}
              onChange={onChange}
            />
          ))}
          <AddProviderMenu
            providerCodes={appendableProviderCodes}
            providerLabels={Object.fromEntries(
              appendableProviderCodes.map((providerCode) => [
                providerCode,
                data.providers[providerCode]?.name ?? providerCode,
              ]),
            )}
            onAppend={(providerCode) => onChange(appendProviderToModel(data, roleName, modelCode, providerCode))}
          />
        </div>
      </SortableContext>
    </DndContext>
  )
}

function ProviderTag({
  id,
  data,
  roleName,
  modelCode,
  providerCode,
  index,
  testStatus,
  onChange,
}: {
  id: string
  data: RolesData
  roleName: string
  modelCode: string
  providerCode: string
  index: number
  testStatus?: RoleChainStatusMap[string]
  onChange: (next: RolesData) => void
}) {
  const providerName = data.providers[providerCode]?.name ?? ""
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
        data-dnd-drag-surface="provider"
        className="min-h-9 cursor-grab select-none flex-nowrap items-center gap-2 border-border/70 bg-muted/35 text-muted-foreground active:cursor-grabbing"
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
          {testStatus ? <ProviderTestStatusBadge status={testStatus.status} message={testStatus.message} /> : null}
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
}

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
