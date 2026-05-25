import { useEffect, useRef, useState, type DragEvent, type MouseEvent, type PointerEvent } from "react"
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
import { Bot, Cog, Loader2, MoreVertical, Pencil, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Switch } from "@/components/ui/switch"
import type { CredentialsState, RolesData } from "@/api/llm"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import { getModelAvailability } from "../availability"
import {
  AVAILABLE_MODEL_DRAG_TYPE,
  appendAvailableModelToRole,
  removeRole,
  renameRole,
  reorderModelInRole,
  roleModelProviderCodes,
  toggleModelFallback,
} from "../role-utils"
import { ModelItem } from "./ModelItem"
import { RoleNameDialog } from "./RoleNameDialog"

export type RoleCategory = "graph-agent" | "copilot"

export function RoleCard({
  data,
  category,
  credentialsByCode,
  roleName,
  testStatuses,
  testChainRunning,
  onRunTestChain,
  getActiveAvailableModelDragId,
  onChange,
}: {
  data: RolesData
  category: RoleCategory
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  roleName: string
  testStatuses: RoleChainStatusMap
  testChainRunning: boolean
  onRunTestChain: () => void
  getActiveAvailableModelDragId: () => string | null
  onChange: (next: RolesData) => void
}) {
  const role = data.roles[roleName]
  const modelCodes = Object.keys(role.models)
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [actionsOpen, setActionsOpen] = useState(false)
  const actionsOpenTimerRef = useRef<number | null>(null)
  const RoleIcon = category === "copilot" ? Bot : Cog
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function modelAvailability(modelCode: string) {
    const providers = roleModelProviderCodes(
      data,
      modelCode,
      role.models[modelCode]?.providers ?? [],
      credentialsByCode,
    )
    return getModelAvailability(providers, credentialsByCode)
  }

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
    if (!modelId) return
    onChange(appendAvailableModelToRole(data, roleName, modelId, credentialsByCode))
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
      <CardHeader className="grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
        <div
          data-role-card-title-row="true"
          className="col-start-1 row-start-1 flex h-8 min-w-0 items-center gap-2"
        >
          <RoleIcon
            aria-hidden="true"
            data-role-title-icon="true"
            className="size-3.5 shrink-0 text-muted-foreground"
          />
          <CardTitle className="min-w-0 break-all">{roleName}</CardTitle>
        </div>
        <CardAction
          data-role-header-actions="true"
          className="col-start-2 row-start-1 row-span-1 flex h-8 flex-nowrap items-center justify-end gap-3 self-center"
        >
          <label className="flex h-8 items-center gap-2 whitespace-nowrap text-xs text-muted-foreground">
            <Switch
              size="sm"
              checked={role.model_fallback}
              onCheckedChange={(checked) => onChange(toggleModelFallback(data, roleName, checked))}
              aria-label={`Model fallback for ${roleName}`}
            />
            model_fallback
          </label>
          <Button
            type="button"
            variant="default"
            size="default"
            data-role-test-trigger="true"
            className="min-w-20 shrink-0"
            disabled={testChainRunning}
            onClick={onRunTestChain}
          >
            {testChainRunning ? <Loader2 className="size-3 animate-spin" /> : null}
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
                Edit
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                data-role-delete-trigger="true"
                variant="destructive"
                onSelect={() => setDeleteOpen(true)}
              >
                <Trash2 />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </CardAction>
      </CardHeader>

      <CardContent
        data-model-drop-zone="true"
        data-model-drop-fallback="active-drag-ref"
        onDragOver={handleAvailableModelDragOver}
        onDrop={handleAvailableModelDrop}
        className="space-y-4"
      >
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
              {modelCodes.map((modelCode, modelIndex) => (
                <ModelItem
                  key={modelCode}
                  data={data}
                  roleName={roleName}
                  modelCode={modelCode}
                  modelIndex={modelIndex}
                  credentialsByCode={credentialsByCode}
                  availability={modelAvailability(modelCode)}
                  testStatuses={testStatuses}
                  onChange={onChange}
                />
              ))}
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
        title="Edit role"
        initialName={roleName}
        existingNames={Object.keys(data.roles)}
        open={editOpen}
        onOpenChange={setEditOpen}
        onSubmit={(nextRoleName) => onChange(renameRole(data, roleName, nextRoleName))}
      />
      <DeleteConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        itemName={roleName}
        description={`Remove ${roleName} and its model fallback chain.`}
        onConfirm={() => onChange(removeRole(data, roleName))}
      />
    </Card>
  )
}
