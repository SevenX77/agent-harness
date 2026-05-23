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
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { ArrowDown, ArrowUp, GripVertical, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { roleChainStatusKey, type RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import type { RolesData } from "@/api/llm"
import { moveProviderInRole, removeProviderFromRole, reorderProviderInRole } from "../role-utils"
import { IconTooltip } from "./IconTooltip"
import { ProviderTestStatusBadge } from "./RoleBadges"

export function ProviderChain({
  data,
  roleName,
  modelCode,
  providers,
  testStatuses,
  onChange,
}: {
  data: RolesData
  roleName: string
  modelCode: string
  providers: string[]
  testStatuses: RoleChainStatusMap
  onChange: (next: RolesData) => void
}) {
  const providerItems = providers.map((providerCode, index) => providerItemId(providerCode, index))
  const sensors = useSensors(
    useSensor(PointerSensor),
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
      <SortableContext items={providerItems} strategy={verticalListSortingStrategy}>
        <div className="space-y-1.5">
          {providers.map((providerCode, index) => (
            <ProviderTag
              key={`${providerCode}-${index}`}
              id={providerItemId(providerCode, index)}
              data={data}
              roleName={roleName}
              modelCode={modelCode}
              providerCode={providerCode}
              index={index}
              count={providers.length}
              testStatus={testStatuses[roleChainStatusKey(modelCode, providerCode)]}
              onChange={onChange}
            />
          ))}
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
  count,
  testStatus,
  onChange,
}: {
  id: string
  data: RolesData
  roleName: string
  modelCode: string
  providerCode: string
  index: number
  count: number
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
  } = useSortable({ id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex flex-col gap-2 rounded-md border border-border bg-muted/20 px-2 py-1.5 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="min-w-0 break-words text-xs">
        <span className="text-muted-foreground">{index + 1}. </span>
        <span className="font-mono">{providerCode}</span>
        <span className="block text-[11px] text-muted-foreground sm:ml-2 sm:inline">{providerName}</span>
      </div>
      <div className="flex w-full shrink-0 flex-wrap items-center justify-end gap-1 sm:w-auto">
        {testStatus ? <ProviderTestStatusBadge status={testStatus.status} message={testStatus.message} /> : null}
        <IconTooltip label={`Drag ${providerCode}`}>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Drag ${providerCode}`}
            {...attributes}
            {...listeners}
          >
            <GripVertical className="size-3" />
          </Button>
        </IconTooltip>
        <IconTooltip label={`Move ${providerCode} up`}>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Move ${providerCode} up`}
            disabled={index === 0}
            onClick={() => onChange(moveProviderInRole(data, roleName, modelCode, index, -1))}
          >
            <ArrowUp className="size-3" />
          </Button>
        </IconTooltip>
        <IconTooltip label={`Move ${providerCode} down`}>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Move ${providerCode} down`}
            disabled={index === count - 1}
            onClick={() => onChange(moveProviderInRole(data, roleName, modelCode, index, 1))}
          >
            <ArrowDown className="size-3" />
          </Button>
        </IconTooltip>
        <IconTooltip label={`Remove ${providerCode}`}>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Remove ${providerCode}`}
            onClick={() => onChange(removeProviderFromRole(data, roleName, modelCode, index))}
          >
            <Trash2 className="size-3" />
          </Button>
        </IconTooltip>
      </div>
    </div>
  )
}

function providerItemId(providerCode: string, index: number): string {
  return `${providerCode}:${index}`
}
