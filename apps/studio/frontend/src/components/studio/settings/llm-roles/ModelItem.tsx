import { memo, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { CircleAlert, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import { cn } from "@/lib/utils"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import type { CredentialsState, MaterializationReportEntry, ProviderModelOption, RolesData } from "@/api/llm"
import {
  ownedProviderCodesForModel,
  removeModelFromRole,
  roleModelProviderCodes,
} from "../role-utils"
import { IconTooltip } from "./IconTooltip"
import { ProviderChain } from "./ProviderChain"
import { ThinkingBadge } from "./RoleBadges"

export const ModelItem = memo(function ModelItem({
  data,
  roleName,
  modelCode,
  modelName,
  modelIndex,
  credentialsByCode,
  ownedProviderCodes,
  providerModelsByRouteId,
  roleFitByRouteId,
  testStatuses,
  onChange,
}: {
  data: RolesData
  roleName: string
  modelCode: string
  modelName: string
  modelIndex: number
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  ownedProviderCodes?: ReadonlySet<string>
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>
  roleFitByRouteId: ReadonlyMap<string, MaterializationReportEntry>
  testStatuses: RoleChainStatusMap
  onChange: (next: RolesData) => void
}) {
  const { t } = useTranslation("settings")
  const role = data.roles[roleName]
  const roleModel = role.models[modelCode]
  // Data-loss fix: an unresolved model group is a persisted routing intent the
  // CURRENT registry can no longer resolve (route deleted / credential expired /
  // model retired). It must be shown as an explicit broken state the user can act
  // on (remove, or re-add a live model) — never silently hidden or auto-dropped.
  const isUnresolved = Boolean(data.models[modelCode]?.is_unresolved)
  const providers = useMemo(() => (
    ownedProviderCodes
      ? roleModel.providers.filter((providerCode) => ownedProviderCodes.has(providerCode))
      : roleModelProviderCodes(data, modelCode, roleModel.providers, credentialsByCode)
  ), [credentialsByCode, data, modelCode, ownedProviderCodes, roleModel.providers])
  const appendableProviderCodes = useMemo(() => {
    const owned = ownedProviderCodes
      ? Array.from(ownedProviderCodes)
      : ownedProviderCodesForModel(data, modelCode, credentialsByCode)
    const taken = new Set(providers)
    return owned.filter((providerCode) => !taken.has(providerCode))
  }, [credentialsByCode, data, modelCode, ownedProviderCodes, providers])
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: modelCode })
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
        variant="outline"
        size="sm"
        data-model-row="true"
        data-dnd-drag-surface="model"
        data-model-unresolved={isUnresolved || undefined}
        className={cn(
          "cursor-grab select-none items-center gap-3 bg-background/60 p-3 ring-inset ring-1 ring-foreground/10 active:cursor-grabbing",
          isUnresolved && "border-warning-border bg-warning-background/10 ring-warning-border",
        )}
        {...attributes}
        {...listeners}
        role="listitem"
        aria-label={`Reorder ${modelName}`}
      >
        <ItemMedia className="size-6 rounded-sm bg-muted text-[10px] font-mono text-muted-foreground ring-1 ring-foreground/10">
          {modelIndex + 1}
        </ItemMedia>
        <ItemContent className="min-w-0 overflow-hidden gap-1">
          <ItemTitle
            data-model-title-row="true"
            className="line-clamp-none !grid w-full min-w-0 grid-cols-[minmax(0,max-content)_auto] justify-start gap-x-4 overflow-hidden text-sm/relaxed text-card-foreground"
          >
            <span data-model-name="true" className="min-w-0 truncate whitespace-nowrap">{modelName}</span>
            <span data-model-badge-group="true" className="flex shrink-0 items-center gap-2.5">
              {isUnresolved ? (
                <Badge variant="warning" className="gap-1" data-model-unresolved-badge="true">
                  <CircleAlert className="size-3" />
                  {t("llmRoles.unresolvedModel.badge")}
                </Badge>
              ) : null}
              {data.models[modelCode]?.reasoning ? <ThinkingBadge /> : null}
            </span>
          </ItemTitle>
          {isUnresolved ? (
            <p
              data-model-unresolved-hint="true"
              className="text-xs leading-snug text-warning-foreground"
            >
              {t("llmRoles.unresolvedModel.hint")}
            </p>
          ) : null}
        </ItemContent>
        <ItemActions
          className="ml-auto shrink-0 gap-1"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <IconTooltip label={`Remove ${modelName}`}>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={`Remove ${modelName}`}
              className="text-muted-foreground hover:text-foreground"
              onClick={() => onChange(removeModelFromRole(data, roleName, modelCode))}
            >
              <Trash2 data-role-icon="true" className="size-3 text-muted-foreground" />
            </Button>
          </IconTooltip>
        </ItemActions>
        <div className="basis-full pt-2" onPointerDown={(event) => event.stopPropagation()}>
          <ProviderChain
            data={data}
            roleName={roleName}
            modelCode={modelCode}
            modelName={modelName}
            providers={providers}
            appendableProviderCodes={appendableProviderCodes}
            providerModelsByRouteId={providerModelsByRouteId}
            roleFitByRouteId={roleFitByRouteId}
            testStatuses={testStatuses}
            onChange={onChange}
          />
        </div>
      </Item>
    </div>
  )
})
