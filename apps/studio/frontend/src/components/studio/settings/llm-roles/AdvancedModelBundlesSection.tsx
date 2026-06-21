import { Layers3, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import type { CredentialsState, ModelGroup, ProviderModelOption, RolesData } from "@/api/llm"
import type { RoleChainStatusMap } from "@/hooks/useRoleTestChainRunner"
import {
  appendModelBundle,
  routeIdsFromBundle,
  visibleModelBundleEntries,
} from "../model-bundle-utils"
import { RoleNameDialog } from "./RoleNameDialog"
import { ModelBundleCard } from "./ModelBundleCard"

export function AdvancedModelBundlesSection({
  data,
  credentialsByCode,
  modelDisplayNamesByCode,
  modelGroups,
  providerModelsByRouteId,
  testStatusesByBundle = {},
  testRunningByBundle = {},
  bundleTestErrors = {},
  onTestBundle,
  getActiveAvailableModelDragId,
  onChange,
  onDeleteBundle,
}: {
  data: RolesData
  credentialsByCode: Record<string, CredentialsState["providers"][number]>
  modelDisplayNamesByCode: ReadonlyMap<string, string>
  modelGroups: ModelGroup[]
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>
  testStatusesByBundle?: Record<string, RoleChainStatusMap>
  testRunningByBundle?: Record<string, boolean>
  bundleTestErrors?: Record<string, string | undefined>
  onTestBundle?: (bundleId: string) => void
  getActiveAvailableModelDragId: () => string | null
  onChange: (next: RolesData) => void
  onDeleteBundle: (bundleId: string) => void
}) {
  const bundles = visibleModelBundleEntries(data)
  const modelGroupsById = new Map(modelGroups.map((group) => [group.canonical_id, group]))

  return (
    <section data-advanced-model-bundles="true" className="space-y-4 pt-2">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Layers3 aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
          <h3 className="min-w-0 text-sm font-semibold text-foreground">Model Bundles</h3>
        </div>
        <RoleNameDialog
          title="New model bundle"
          fieldLabel="Bundle name"
          initialName=""
          existingNames={bundles.map(([, bundle]) => bundle.display_name)}
          submitLabel="Add"
          trigger={(
            <Button
              type="button"
              size="default"
              variant="default"
              data-model-bundle-create="true"
              className="gap-1"
            >
              <Plus data-role-icon="true" className="size-3.5 text-primary-foreground/80" />
              Add Model Bundle
            </Button>
          )}
          onSubmit={(bundleName) => onChange(appendModelBundle(data, bundleName))}
        />
      </div>

      {bundles.length > 0 ? (
        <div className="space-y-4">
          {bundles.map(([bundleId, bundle]) => (
            <ModelBundleCard
              key={bundleId}
              data={data}
              bundle={bundle}
              bundleId={bundleId}
              credentialsByCode={credentialsByCode}
              modelDisplayNamesByCode={modelDisplayNamesByCode}
              providerModelsByRouteId={providerModelsByRouteId}
              testStatuses={testStatusesByBundle[bundleId] ?? {}}
              testRunning={testRunningByBundle[bundleId] ?? false}
              bundleTestError={bundleTestErrors[bundleId]}
              onRunTest={onTestBundle}
              getActiveAvailableModelDragId={getActiveAvailableModelDragId}
              getAvailableModelGroup={(modelGroupId) => modelGroupsById.get(modelGroupId) ?? null}
              onChange={onChange}
              onDeleteBundle={onDeleteBundle}
            />
          ))}
        </div>
      ) : (
        <Empty className="min-h-24 flex-none gap-1 rounded-md border border-dashed border-border bg-muted/10 p-4 text-muted-foreground">
          <EmptyHeader className="max-w-none gap-0">
            <EmptyTitle className="text-xs font-medium text-muted-foreground">No model bundles configured.</EmptyTitle>
          </EmptyHeader>
        </Empty>
      )}
    </section>
  )
}

export function modelBundleGroupsFromData(
  data: RolesData,
  providerModelsByRouteId: ReadonlyMap<string, ProviderModelOption>,
): ModelGroup[] {
  const groups: ModelGroup[] = []
  for (const [bundleId, bundle] of visibleModelBundleEntries(data)) {
    const routeIds = routeIdsFromBundle(bundle)
    const providerModels = routeIds
      .map((routeId) => providerModelsByRouteId.get(routeId) ?? providerModelFallback(data, routeId))
      .filter((providerModel): providerModel is ProviderModelOption => Boolean(providerModel))
    if (providerModels.length === 0) continue
    groups.push({
      canonical_id: `bundle:${bundleId}`,
      display_name: bundle.display_name || bundleId,
      section_label: "Model Bundles",
      provider_models: providerModels,
      status_summary: summarizeProviderStates(providerModels),
      capability_summary: summarizeProviderCapabilities(providerModels),
    })
  }
  return groups
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
    historical_ready: 0,
    untested: 0,
    failed: 0,
    cooling_down: 0,
    off: 0,
  })
}

function summarizeProviderCapabilities(providerModels: ProviderModelOption[]): ModelGroup["capability_summary"] {
  const maxOutputTokens = providerModels
    .map((providerModel) => providerMaxOutputTokens(providerModel))
    .filter((value): value is number => value !== null)
  return {
    capability_known_count: providerModels.filter((providerModel) => providerModel.capability_state !== "unknown").length,
    thinking: providerModels.some((providerModel) => Boolean(
      providerModel.capabilities.thinking?.value ||
      providerModel.capabilities.reasoning?.value ||
      providerModel.capabilities.supports_thinking?.value ||
      providerModel.capabilities.thinking_protocol?.value,
    )) ? "mixed" : "unknown",
    tools: "unknown",
    structured_output: "unknown",
    max_context_tokens: null,
    max_output_tokens: maxOutputTokens.length ? Math.max(...maxOutputTokens) : null,
  }
}

function providerMaxOutputTokens(providerModel: ProviderModelOption): number | null {
  const value = providerModel.capabilities.max_output_tokens?.value
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const max = (value as { max?: unknown }).max
  return typeof max === "number" && Number.isFinite(max) ? max : null
}
