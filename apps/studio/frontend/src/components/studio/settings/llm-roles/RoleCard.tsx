import { useMemo } from "react"
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
import { Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import type { CredentialsState, RolesData } from "@/api/llm"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import { getModelAvailability } from "../availability"
import {
  appendModelToRole,
  reorderModelInRole,
  toggleModelFallback,
  updateActiveModel,
} from "../role-utils"
import { AddModelSelect } from "./AddModelSelect"
import { ModelItem } from "./ModelItem"

export function RoleCard({
  data,
  credentialsByCode,
  roleName,
  testStatuses,
  testChainRunning,
  onRunTestChain,
  onChange,
}: {
  data: RolesData
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  roleName: string
  testStatuses: RoleChainStatusMap
  testChainRunning: boolean
  onRunTestChain: () => void
  onChange: (next: RolesData) => void
}) {
  const role = data.roles[roleName]
  const modelCodes = Object.keys(role.models)
  const appendableModelCodes = useMemo(
    () => Object.keys(data.models).filter((modelCode) => !role.models[modelCode]),
    [data.models, role.models],
  )
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function modelAvailability(modelCode: string) {
    const providers = role.models[modelCode]?.providers ?? []
    return getModelAvailability(providers, credentialsByCode)
  }

  return (
    <Card size="sm" className="rounded-md" data-role-name={roleName}>
      <CardHeader className="flex flex-col gap-3">
        <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="break-all font-mono">{roleName}</CardTitle>
              <Badge variant="outline" className="font-mono">
                {role.active_model || "No active model"}
              </Badge>
            </div>
            <CardDescription>Model fallback chain with provider fallback per model.</CardDescription>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
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
              variant="outline"
              size="sm"
              disabled={testChainRunning}
              onClick={onRunTestChain}
            >
              {testChainRunning ? <Loader2 className="size-3 animate-spin" /> : null}
              {testChainRunning ? "Testing" : "Test Chain"}
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="max-w-sm">
          <Field>
            <FieldLabel htmlFor={`active-model-${roleName}`}>Active model</FieldLabel>
            <Select
              value={role.active_model}
              onValueChange={(value) => onChange(updateActiveModel(data, roleName, value))}
            >
              <SelectTrigger id={`active-model-${roleName}`} aria-label={`Active model for ${roleName}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {modelCodes.map((modelCode) => (
                  <SelectItem
                    key={modelCode}
                    value={modelCode}
                    disabled={modelAvailability(modelCode) === "unavailable"}
                    data-availability={modelAvailability(modelCode)}
                  >
                    {modelCode}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription>First model attempted before fallback.</FieldDescription>
          </Field>
        </div>

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
            <div className="space-y-3">
              {modelCodes.map((modelCode, modelIndex) => (
                <ModelItem
                  key={modelCode}
                  data={data}
                  roleName={roleName}
                  modelCode={modelCode}
                  modelIndex={modelIndex}
                  modelCount={modelCodes.length}
                  active={role.active_model === modelCode}
                  availability={modelAvailability(modelCode)}
                  testStatuses={testStatuses}
                  onChange={onChange}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      </CardContent>

      <CardFooter>
        <AddModelSelect
          modelCodes={appendableModelCodes}
          onAppend={(modelCode) => onChange(appendModelToRole(data, roleName, modelCode))}
        />
      </CardFooter>
    </Card>
  )
}
