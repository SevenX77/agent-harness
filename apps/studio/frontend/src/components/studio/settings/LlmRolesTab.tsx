import { useMemo } from "react"
import { ArrowDown, ArrowUp, TriangleAlert, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { CredentialsState, RolesData } from "../../../api/llm"
import { getModelAvailability, type ModelAvailability } from "./availability"
import { moveModelInRole, moveProviderInRole, removeModelFromRole, removeProviderFromRole, toggleModelFallback, updateActiveModel, visibleRoleNames } from "./role-utils"
import { SectionTitle } from "./shared"

const DISABLED_ROLE_EDITING = "Adding new model/provider coming in v2.5"

export function LlmRolesTab({
  data,
  credentials,
  selectedRole,
  dirty,
  error,
  onSelectedRoleChange,
  onChange,
  onSave,
}: {
  data: RolesData | null
  credentials: CredentialsState
  selectedRole: string
  dirty: boolean
  error: string | null
  onSelectedRoleChange: (roleName: string) => void
  onChange: (next: RolesData) => void
  onSave: () => void
}) {
  const credentialsByCode = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )

  if (!data) {
    return (
      <div>
        <SectionTitle title="LLM Roles" description="Edit active models and fallback order." />
        <div className="rounded-md border border-border p-6 text-xs text-muted-foreground">
          Loading roles...
        </div>
      </div>
    )
  }

  const roleNames = visibleRoleNames(data)
  const roleName = selectedRole && data.roles[selectedRole] ? selectedRole : roleNames[0] ?? ""
  const role = data.roles[roleName]
  const modelCodes = role ? Object.keys(role.models) : []

  function modelAvailability(modelCode: string): ModelAvailability {
    const providers = data!.roles[roleName].models[modelCode].providers
    return getModelAvailability(providers, credentialsByCode)
  }

  function availabilityPrefix(availability: ModelAvailability): string {
    if (availability === "unavailable") return "Unavailable · "
    if (availability === "key_only") return "Untested · "
    return ""
  }

  return (
    <div>
      <SectionTitle title="LLM Roles" description="Edit active model and fallback order." />
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-sm border border-border bg-card/40 p-3">
        <div>
          <Label htmlFor="llm-role-select" className="text-[11px] text-muted-foreground">Role</Label>
          <select
            id="llm-role-select"
            value={roleName}
            onChange={(event) => onSelectedRoleChange(event.target.value)}
            className="mt-1 h-8 rounded-md border border-input bg-background px-2 text-xs"
            aria-label="Role"
          >
            {roleNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
        {role ? (
          <>
            <div>
              <Label htmlFor="active-model-select" className="text-[11px] text-muted-foreground">active_model</Label>
              <select
                id="active-model-select"
                value={role.active_model}
                onChange={(event) => onChange(updateActiveModel(data, roleName, event.target.value))}
                className="mt-1 h-8 rounded-md border border-input bg-background px-2 text-xs"
                aria-label="Active model"
              >
                {modelCodes.map((modelCode) => {
                  const availability = modelAvailability(modelCode)
                  return (
                    <option
                      key={modelCode}
                      value={modelCode}
                      disabled={availability === "unavailable"}
                      data-availability={availability}
                    >
                      {`${availabilityPrefix(availability)}${modelCode}`}
                    </option>
                  )
                })}
              </select>
            </div>
            <label className="flex h-8 items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={role.model_fallback}
                onChange={(event) => onChange(toggleModelFallback(data, roleName, event.target.checked))}
                aria-label="Model fallback"
              />
              model_fallback
            </label>
          </>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          {dirty ? <Badge variant="outline">Dirty</Badge> : null}
          <Button type="button" size="sm" onClick={onSave} disabled={!role || !dirty}>
            Save
          </Button>
        </div>
      </div>
      {error ? <div className="mb-3 text-xs text-destructive">Validation failed: {error}</div> : null}
      {role ? (
        <div className="space-y-3">
          {modelCodes.map((modelCode, modelIndex) => (
            <RoleModelCard
              key={modelCode}
              data={data}
              roleName={roleName}
              modelCode={modelCode}
              modelIndex={modelIndex}
              modelCount={modelCodes.length}
              active={role.active_model === modelCode}
              availability={modelAvailability(modelCode)}
              onChange={onChange}
            />
          ))}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" variant="outline" size="sm" disabled title={DISABLED_ROLE_EDITING}>
                  + Add Model
                </Button>
              </TooltipTrigger>
              <TooltipContent>{DISABLED_ROLE_EDITING}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      ) : null}
    </div>
  )
}

function RoleModelCard({
  data,
  roleName,
  modelCode,
  modelIndex,
  modelCount,
  active,
  availability,
  onChange,
}: {
  data: RolesData
  roleName: string
  modelCode: string
  modelIndex: number
  modelCount: number
  active: boolean
  availability: ModelAvailability
  onChange: (next: RolesData) => void
}) {
  const role = data.roles[roleName]
  const providers = role.models[modelCode].providers
  const modelName = data.models[modelCode]?.name ?? modelCode
  return (
    <div className="rounded-sm border border-border bg-card/40 p-3" data-availability={availability}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold">
            {modelCode}
            {active ? <Badge variant="outline">active</Badge> : null}
            {availability === "unavailable" ? (
              <Badge variant="outline" className="border-red-800/40 bg-red-950/40 text-red-300">
                <TriangleAlert className="size-3" />
                Unavailable
              </Badge>
            ) : null}
            {availability === "key_only" ? (
              <Badge variant="outline" className="text-muted-foreground">
                Untested
              </Badge>
            ) : null}
          </div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">{modelName}</div>
        </div>
        <div className="flex items-center gap-1">
          <Button type="button" variant="ghost" size="sm" disabled={modelIndex === 0} onClick={() => onChange(moveModelInRole(data, roleName, modelCode, -1))}>
            Move Up
          </Button>
          <Button type="button" variant="ghost" size="sm" disabled={modelIndex === modelCount - 1} onClick={() => onChange(moveModelInRole(data, roleName, modelCode, 1))}>
            Move Down
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange(removeModelFromRole(data, roleName, modelCode))}>
            Remove
          </Button>
        </div>
      </div>
      <div className="mb-2 text-[11px] font-medium text-muted-foreground">
        Provider chain
      </div>
      <div className="space-y-1.5">
        {providers.map((providerCode, index) => (
          <div key={`${providerCode}-${index}`} className="flex items-center justify-between gap-2 rounded-sm bg-muted/30 px-2 py-1.5">
            <div className="text-xs">
              <span className="text-muted-foreground">{index + 1}. </span>
              {providerCode}
              <span className="ml-2 text-[11px] text-muted-foreground">{data.providers[providerCode]?.name ?? ""}</span>
            </div>
            <div className="flex items-center gap-1">
              <Button type="button" variant="ghost" size="icon-xs" aria-label={`Move ${providerCode} up`} disabled={index === 0} onClick={() => onChange(moveProviderInRole(data, roleName, modelCode, index, -1))}>
                <ArrowUp className="size-3" />
              </Button>
              <Button type="button" variant="ghost" size="icon-xs" aria-label={`Move ${providerCode} down`} disabled={index === providers.length - 1} onClick={() => onChange(moveProviderInRole(data, roleName, modelCode, index, 1))}>
                <ArrowDown className="size-3" />
              </Button>
              <Button type="button" variant="ghost" size="icon-xs" aria-label={`Remove ${providerCode}`} onClick={() => onChange(removeProviderFromRole(data, roleName, modelCode, index))}>
                <X className="size-3" />
              </Button>
            </div>
          </div>
        ))}
      </div>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button type="button" variant="ghost" size="sm" disabled title={DISABLED_ROLE_EDITING} className="mt-2">
              + Add Provider
            </Button>
          </TooltipTrigger>
          <TooltipContent>{DISABLED_ROLE_EDITING}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  )
}
