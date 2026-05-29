import { Layers3, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Item, ItemContent, ItemTitle } from "@/components/ui/item"
import { Tag } from "@/components/ui/tag"
import type { ModelGroup, ProviderModelOption, RolesData } from "@/api/llm"
import { visibleRoleNames } from "../role-utils"

interface BundleRecord {
  display_name?: string
  fallback_chain?: Array<{ route_id?: string }>
}

export function AdvancedModelBundlesSection({
  data,
  modelGroups,
  providerModelsByRouteId,
  onChange,
}: {
  data: RolesData
  modelGroups: ModelGroup[]
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>
  onChange: (next: RolesData) => void
}) {
  const bundles = modelBundleGroupsFromData(data, providerModelsByRouteId)
  const firstSourceRole = visibleRoleNames(data).find((roleName) => (
    Object.values(data.roles[roleName]?.models ?? {}).some((model) => model.providers.length > 0)
  ))

  return (
    <section data-advanced-model-bundles="true" className="pt-2">
      <Card size="sm" className="rounded-md">
        <CardHeader className="!grid-cols-1 items-center gap-2 sm:!grid-cols-[minmax(0,1fr)_auto] sm:gap-3">
          <div className="col-start-1 row-start-1 flex h-8 min-w-0 items-center gap-2">
            <Layers3 aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
            <CardTitle className="min-w-0">Advanced Model Bundles</CardTitle>
          </div>
          <CardAction className="col-start-1 row-start-2 flex h-8 items-center justify-start sm:col-start-2 sm:row-start-1 sm:justify-end">
            <Button
              type="button"
              size="default"
              variant="outline"
              data-model-bundle-create="true"
              className="gap-1"
              disabled={!firstSourceRole}
              onClick={() => {
                if (!firstSourceRole) return
                onChange(createBundleFromRole(data, firstSourceRole, modelGroups))
              }}
            >
              <Plus data-role-icon="true" className="size-3.5" />
              Create Bundle
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-3">
          {bundles.length > 0 ? (
            <div className="grid gap-2">
              {bundles.map((bundle) => (
                <Item
                  key={bundle.canonical_id}
                  variant="outline"
                  size="sm"
                  data-model-bundle-row="true"
                  className="items-center gap-3 bg-background/60 p-3 ring-inset ring-1 ring-foreground/10"
                >
                  <ItemContent className="min-w-0 gap-1 overflow-hidden">
                    <ItemTitle className="line-clamp-none w-full min-w-0 text-sm/relaxed text-card-foreground">
                      <span className="min-w-0 truncate whitespace-nowrap">{bundle.display_name}</span>
                    </ItemTitle>
                    <div className="flex min-w-0 flex-wrap gap-1">
                      {bundle.provider_models.map((providerModel) => (
                        <Tag
                          key={providerModel.route_id}
                          size="xs"
                          variant={providerModel.ui_state === "ready" ? "success" : "muted"}
                          className="font-sans"
                        >
                          {providerModel.provider_label}
                        </Tag>
                      ))}
                    </div>
                  </ItemContent>
                </Item>
              ))}
            </div>
          ) : (
            <Empty className="min-h-16 flex-none gap-1 rounded-md border border-dashed border-border bg-muted/10 p-3 text-muted-foreground">
              <EmptyHeader className="max-w-none gap-0">
                <EmptyTitle className="text-xs font-medium text-muted-foreground">No model bundles configured.</EmptyTitle>
              </EmptyHeader>
            </Empty>
          )}
        </CardContent>
      </Card>
    </section>
  )
}

export function modelBundleGroupsFromData(
  data: RolesData,
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>,
): ModelGroup[] {
  const groups: ModelGroup[] = []
  for (const [bundleId, rawBundle] of Object.entries(data.model_bundles ?? {})) {
    const bundle = asBundleRecord(rawBundle)
    const routeIds = (bundle.fallback_chain ?? [])
      .map((entry) => entry.route_id)
      .filter((routeId): routeId is string => Boolean(routeId))
    const providerModels = routeIds
      .map((routeId) => providerModelsByRouteId.get(routeId) ?? providerModelFallback(data, routeId))
      .filter((providerModel): providerModel is ProviderModelOption => Boolean(providerModel))
    if (providerModels.length === 0) continue
    groups.push({
      canonical_id: `bundle:${bundleId}`,
      display_name: bundle.display_name || bundleId,
      section_label: "Advanced Model Bundles",
      provider_models: providerModels,
      status_summary: summarizeProviderStates(providerModels),
      capability_summary: {
        capability_known_count: providerModels.filter((providerModel) => providerModel.capability_state !== "unknown").length,
        thinking: "unknown",
        tools: "unknown",
        structured_output: "unknown",
        max_context_tokens: null,
        max_output_tokens: null,
      },
    })
  }
  return groups
}

function createBundleFromRole(data: RolesData, roleName: string, modelGroups: ModelGroup[]): RolesData {
  const role = data.roles[roleName]
  if (!role) return data
  const routeIds = Object.values(role.models).flatMap((model) => model.providers)
  if (routeIds.length === 0) return data

  const existingBundleIds = Object.keys(data.model_bundles ?? {})
  const bundleId = nextBundleId(existingBundleIds, `${roleName}_bundle`)
  const modelGroupByRouteId = new Map(modelGroups.flatMap((group) => (
    group.provider_models.map((providerModel) => [providerModel.route_id, group] as const)
  )))
  const displayName = `${roleName.replace(/[_-]+/g, " ")} Bundle`
  const firstModelGroup = routeIds.map((routeId) => modelGroupByRouteId.get(routeId)).find(Boolean)
  return {
    ...data,
    model_bundles: {
      ...(data.model_bundles ?? {}),
      [bundleId]: {
        model_profile_id: bundleId,
        display_name: firstModelGroup ? `${displayName}: ${firstModelGroup.display_name}` : displayName,
        canonical_id: firstModelGroup?.canonical_id ?? routeIds[0],
        fallback_chain: routeIds.map((routeId) => ({ route_id: routeId })),
      },
    },
  }
}

function providerModelFallback(data: RolesData, routeId: string): ProviderModelOption | null {
  const provider = data.providers[routeId]
  if (!provider) return null
  return {
    route_id: routeId,
    endpoint_id: provider.endpoint_id ?? null,
    provider_label: provider.name,
    provider_kind: "custom",
    provider_model_id: routeId,
    ui_state: "untested",
    ui_detail: null,
    retry_at: null,
    reason_code: null,
    capability_state: "unknown",
    capabilities: {},
  }
}

function summarizeProviderStates(providerModels: ProviderModelOption[]): ModelGroup["status_summary"] {
  return providerModels.reduce<ModelGroup["status_summary"]>((summary, providerModel) => {
    summary[providerModel.ui_state] += 1
    return summary
  }, {
    ready: 0,
    untested: 0,
    cooling_down: 0,
    needs_setup: 0,
    off: 0,
  })
}

function asBundleRecord(value: unknown): BundleRecord {
  if (!value || typeof value !== "object") return {}
  return value as BundleRecord
}

function nextBundleId(existingIds: string[], baseId: string): string {
  const normalizedBase = baseId.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "model_bundle"
  if (!existingIds.includes(normalizedBase)) return normalizedBase
  let index = 2
  while (existingIds.includes(`${normalizedBase}_${index}`)) index += 1
  return `${normalizedBase}_${index}`
}
