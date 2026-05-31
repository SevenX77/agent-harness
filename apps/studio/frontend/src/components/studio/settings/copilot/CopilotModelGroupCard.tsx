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
  rectSortingStrategy,
  SortableContext,
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { ThinkingBadge } from "../llm-roles/RoleBadges"
import type { CopilotAgentStatus, CopilotRoutePreview } from "./mock-copilot-data"
import type { CopilotRouteJobStatus } from "./copilot-role-test"

export const CopilotModelGroupCard = memo(function CopilotModelGroupCard({
  modelName,
  modelIndex,
  routes,
  appendableRoutes,
  routeStatusOverrides,
  onAddRoute,
  onRemoveRoute,
  onReorderRoutes,
}: {
  modelName: string
  modelIndex: number
  routes: CopilotRoutePreview[]
  appendableRoutes: CopilotRoutePreview[]
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>
  onAddRoute: (routeId: string) => void
  onRemoveRoute: (routeId: string) => void
  onReorderRoutes: (activeRouteId: string, overRouteId: string) => void
}) {
  const routeIds = useMemo(() => routes.map((route) => route.id), [routes])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function handleDragEnd(event: DragEndEvent) {
    const activeRouteId = String(event.active.id)
    const overRouteId = event.over?.id ? String(event.over.id) : ""
    if (overRouteId && activeRouteId !== overRouteId) {
      onReorderRoutes(activeRouteId, overRouteId)
    }
  }

  return (
    <Item
      variant="outline"
      size="sm"
      data-copilot-model-group="true"
      className="items-center gap-3 bg-background/60 p-3 ring-inset ring-1 ring-foreground/10"
      role="listitem"
    >
      <ItemMedia className="size-6 rounded-sm bg-muted text-[10px] font-mono text-muted-foreground ring-1 ring-foreground/10">
        {modelIndex + 1}
      </ItemMedia>
      <ItemContent className="min-w-0 overflow-hidden gap-1">
        <ItemTitle
          data-copilot-model-title-row="true"
          className="line-clamp-none !grid w-full min-w-0 grid-cols-[minmax(0,max-content)_auto] justify-start gap-x-4 overflow-hidden text-sm/relaxed text-card-foreground"
        >
          <span data-copilot-model-name="true" className="min-w-0 truncate whitespace-nowrap">
            {modelName}
          </span>
          <span data-copilot-model-badge-group="true" className="flex shrink-0 items-center gap-2.5">
            <ThinkingBadge />
          </span>
        </ItemTitle>
      </ItemContent>
      <ItemActions className="ml-auto shrink-0 gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          aria-label={`Remove ${modelName}`}
          className="text-muted-foreground hover:text-foreground"
          disabled
        >
          <Trash2 data-role-icon="true" className="size-3 text-muted-foreground" />
        </Button>
      </ItemActions>
      <div className="basis-full pt-2">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={routeIds} strategy={rectSortingStrategy}>
            <div
              data-copilot-provider-grid="true"
              className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,max(12rem,calc((100%_-_0.75rem)/3))),1fr))] justify-start gap-1.5"
              role="list"
              aria-label={`${modelName} copilot route fallback order`}
            >
              {routes.map((route, index) => (
                <CopilotProviderTag
                  key={route.id}
                  route={route}
                  index={index}
                  status={agentStatusForRoute(route.agentStatus, route.id, routeStatusOverrides)}
                  onRemove={() => onRemoveRoute(route.id)}
                />
              ))}
              <AddRouteMenu routes={appendableRoutes} onAddRoute={onAddRoute} />
            </div>
          </SortableContext>
        </DndContext>
      </div>
    </Item>
  )
})

const CopilotProviderTag = memo(function CopilotProviderTag({
  route,
  index,
  status,
  onRemove,
}: {
  route: CopilotRoutePreview
  index: number
  status: CopilotRouteJobStatus
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: route.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }
  const row = (
    <div ref={setNodeRef} style={style} className={cn("rounded-md", isDragging && "opacity-70")}>
      <Item
        variant="muted"
        size="xs"
        data-copilot-provider-card="true"
        data-agent-sdk-status={status}
        data-dnd-drag-surface="copilot-provider"
        className={cn(
          "relative min-h-9 cursor-grab select-none flex-nowrap items-center gap-2 overflow-hidden border-border/70 bg-muted/35 text-muted-foreground active:cursor-grabbing",
          routeSurfaceClass(status),
        )}
        {...attributes}
        {...listeners}
        role="listitem"
        aria-label={`Reorder ${route.provider}`}
      >
        <ItemMedia className="size-5 rounded-sm bg-background/80 text-[10px] font-mono text-muted-foreground ring-1 ring-foreground/10">
          {index + 1}
        </ItemMedia>
        <ItemContent className="min-w-0 overflow-hidden gap-0.5">
          <ItemTitle className="line-clamp-none block w-full truncate whitespace-nowrap text-xs/relaxed text-muted-foreground">
            {route.provider}
          </ItemTitle>
        </ItemContent>
        <ItemActions
          className="ml-auto shrink-0 gap-1"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <RouteStatusLight status={status} />
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={`Remove ${route.provider}`}
            className="text-muted-foreground hover:text-foreground"
            onClick={onRemove}
          >
            <Trash2 data-role-icon="true" className="size-3 text-muted-foreground" />
          </Button>
        </ItemActions>
      </Item>
    </div>
  )

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{row}</TooltipTrigger>
        <TooltipContent className="max-w-sm whitespace-pre-line break-words">
          {routeTooltip(route, status)}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
})

function AddRouteMenu({
  routes,
  onAddRoute,
}: {
  routes: CopilotRoutePreview[]
  onAddRoute: (routeId: string) => void
}) {
  if (routes.length === 0) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          data-copilot-route-add-trigger="true"
          className="h-9 w-full justify-start gap-2 rounded-md px-2.5 text-muted-foreground hover:bg-muted/35 hover:text-foreground"
        >
          <Plus data-role-icon="true" className="size-3 text-muted-foreground" />
          Add route
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {routes.map((route) => (
          <DropdownMenuItem key={route.id} onSelect={() => onAddRoute(route.id)}>
            {route.provider}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function RouteStatusLight({ status }: { status: CopilotRouteJobStatus }) {
  return (
    <span
      role="status"
      aria-label={`Claude Agent SDK ${statusLabel(status)}`}
      data-copilot-route-status-light="true"
      className={cn("inline-flex size-1.5 shrink-0 rounded-full ring-1 ring-offset-0", lightClass(status))}
    />
  )
}

function agentStatusForRoute(
  initialStatus: CopilotAgentStatus,
  routeId: string,
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>,
): CopilotRouteJobStatus {
  const override = routeStatusOverrides[routeId]
  if (override) return override
  return initialStatus
}

function routeSurfaceClass(status: CopilotRouteJobStatus): string {
  if (status === "ready") return "border-success-border ring-1 ring-success/25"
  if (status === "testing") return "border-primary ring-1 ring-primary/30"
  if (status === "not_tested") return "border-warning-border ring-1 ring-warning/25"
  return "border-destructive-border ring-1 ring-destructive/25"
}

function lightClass(status: CopilotRouteJobStatus): string {
  if (status === "ready") return "bg-success ring-success-border"
  if (status === "testing") return "bg-primary ring-primary animate-pulse"
  if (status === "not_tested") return "bg-warning ring-warning-border"
  return "bg-destructive ring-destructive-border"
}

function statusLabel(status: CopilotRouteJobStatus): string {
  if (status === "ready") return "Ready"
  if (status === "testing") return "Testing"
  if (status === "not_tested") return "Not tested"
  return "Unsupported"
}

function routeTooltip(route: CopilotRoutePreview, status: CopilotRouteJobStatus): string {
  return [
    route.modelId,
    `Claude Agent SDK: ${statusLabel(status)}`,
    `Method: ${route.methodId}`,
    route.note,
  ].filter(Boolean).join("\n")
}
