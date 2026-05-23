import { useState } from "react"
import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import type { RolesData } from "@/api/llm"
import type { ModelAvailability } from "../availability"
import {
  appendProviderToModel,
  moveModelInRole,
  removeModelFromRole,
  updateRoleModelSettings,
} from "../role-utils"
import { IconTooltip } from "./IconTooltip"
import { ModelSettingsDialog } from "./ModelSettingsDialog"
import { ProviderChain } from "./ProviderChain"
import { AvailabilityBadge, CapabilityBadge } from "./RoleBadges"

export function ModelItem({
  data,
  roleName,
  modelCode,
  modelIndex,
  modelCount,
  active,
  availability,
  testStatuses,
  onChange,
}: {
  data: RolesData
  roleName: string
  modelCode: string
  modelIndex: number
  modelCount: number
  active: boolean
  availability: ModelAvailability
  testStatuses: RoleChainStatusMap
  onChange: (next: RolesData) => void
}) {
  const role = data.roles[roleName]
  const roleModel = role.models[modelCode]
  const providers = roleModel.providers
  const modelName = data.models[modelCode]?.name ?? modelCode
  const appendableProviderCodes = Object.keys(data.models[modelCode]?.providers ?? {})
    .filter((providerCode) => !providers.includes(providerCode))
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ id: modelCode })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="rounded-md border border-border bg-muted/15 p-3"
      data-availability={availability}
    >
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
            <span className="font-mono">{modelCode}</span>
            {active ? <Badge variant="outline">active</Badge> : null}
            <AvailabilityBadge availability={availability} />
            {data.models[modelCode]?.reasoning ? <CapabilityBadge enabled /> : null}
          </div>
          <div className="mt-0.5 truncate text-[11px] text-muted-foreground">{modelName}</div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
          <IconTooltip label={`Drag ${modelCode}`}>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={`Drag ${modelCode}`}
              {...attributes}
              {...listeners}
            >
              <GripVertical className="size-3" />
            </Button>
          </IconTooltip>
          <ModelSettingsDialog
            modelCode={modelCode}
            modelName={modelName}
            temperature={roleModel.temperature ?? null}
            maxTokens={roleModel.max_tokens ?? null}
            onSubmit={(settings) => onChange(updateRoleModelSettings(data, roleName, modelCode, settings))}
          />
          <IconTooltip label={`Move ${modelCode} up`}>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={`Move ${modelCode} up`}
              disabled={modelIndex === 0}
              onClick={() => onChange(moveModelInRole(data, roleName, modelCode, -1))}
            >
              <ArrowUp className="size-3" />
            </Button>
          </IconTooltip>
          <IconTooltip label={`Move ${modelCode} down`}>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={`Move ${modelCode} down`}
              disabled={modelIndex === modelCount - 1}
              onClick={() => onChange(moveModelInRole(data, roleName, modelCode, 1))}
            >
              <ArrowDown className="size-3" />
            </Button>
          </IconTooltip>
          <IconTooltip label={`Remove ${modelCode}`}>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={`Remove ${modelCode}`}
              onClick={() => onChange(removeModelFromRole(data, roleName, modelCode))}
            >
              <Trash2 className="size-3" />
            </Button>
          </IconTooltip>
        </div>
      </div>
      <div className="mb-2 text-[11px] font-medium text-muted-foreground">Provider chain</div>
      <ProviderChain
        data={data}
        roleName={roleName}
        modelCode={modelCode}
        providers={providers}
        testStatuses={testStatuses}
        onChange={onChange}
      />
      <div className="mt-2">
        <AddProviderSelect
          providerCodes={appendableProviderCodes}
          onAppend={(providerCode) => onChange(appendProviderToModel(data, roleName, modelCode, providerCode))}
        />
      </div>
    </div>
  )
}

function AddProviderSelect({
  providerCodes,
  onAppend,
}: {
  providerCodes: string[]
  onAppend: (providerCode: string) => void
}) {
  const [resetKey, setResetKey] = useState(0)

  if (providerCodes.length === 0) {
    return (
      <Button type="button" variant="ghost" size="sm" disabled className="text-muted-foreground">
        All providers added
      </Button>
    )
  }

  return (
    <Select
      key={resetKey}
      onValueChange={(providerCode) => {
        onAppend(providerCode)
        setResetKey((value) => value + 1)
      }}
    >
      <SelectTrigger className="w-full sm:w-56" aria-label={`Add provider to model`}>
        <Plus className="size-3" />
        <SelectValue placeholder="Add provider" />
      </SelectTrigger>
      <SelectContent>
        {providerCodes.map((providerCode) => (
          <SelectItem key={providerCode} value={providerCode}>
            {providerCode}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
