import { useCallback, useEffect, useMemo, useRef, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { SaveStatusBadge } from "@/components/ui/save-status-badge"
import { Skeleton } from "@/components/ui/skeleton"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import type { CredentialsState, ModelGroup, ProviderModelOption, RolesData } from "../../../api/llm"
import { AdvancedModelBundlesSection, modelBundleGroupsFromData } from "./llm-roles/AdvancedModelBundlesSection"
import { AvailableModelsSidebar } from "./llm-roles/AvailableModelsSidebar"
import { RoleCardList } from "./llm-roles/RoleCardList"
import {
  bundleTestStoreKey,
  roleTestStatusesByRole,
  runBundleTest,
  runRoleTest,
  seedPersistedRoleTestResults,
  useRoleTestStore,
} from "./llm-roles/role-test-store"
import { appendModelGroupToBundle, removeModelBundle, visibleModelBundleEntries } from "./model-bundle-utils"
import { appendModelGroupToRoleWithResult, attachBundleReferenceToRole, BUNDLE_DRAG_PREFIX, modelDropFailureMessage, ownedProviderCodesForModel, pruneInvalidRoleProviders, removeRole } from "./role-utils"
import { credentialsByProviderCode } from "./route-credentials"
import { SectionTitle } from "./shared"
import { AvailableModelDragPreview, useAvailableModelPointerDrag } from "./available-model-pointer-drag"

export { RoleSettingsPanel, RoleSettingsFields, roleIntentFromSettingsDraft } from "./llm-roles/RoleSettingsDialog"
export { AvailableModelDragPreview, availableModelDragPreviewTransform, type AvailableModelDragPreviewState } from "./available-model-pointer-drag"

export function LlmRolesTab({
  data,
  credentials,
  modelGroups,
  saveStatus,
  error,
  onChange,
  onDeleteRole,
  onDeleteModelBundle,
  onBeforeRoleTest,
  onAfterRoleTest,
  onNavigateToApiKeys,
}: {
  data: RolesData | null
  credentials: CredentialsState
  modelGroups: ModelGroup[]
  saveStatus: SaveStatus
  error: string | null
  onChange: (next: RolesData) => void
  onDeleteRole?: (roleName: string) => void
  onDeleteModelBundle?: (bundleId: string) => void
  onBeforeRoleTest?: () => Promise<RolesData | null>
  onAfterRoleTest?: () => Promise<void> | void
  onNavigateToApiKeys?: () => void
}) {
  const { t } = useTranslation("settings")
  const credentialsByCode = useMemo(() => (
    data
      ? credentialsByProviderCode(data, { providers: credentials.providers })
      : Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider]))
  ), [credentials.providers, data])
  const normalizedData = useMemo(() => (
    data ? pruneInvalidRoleProviders(data, credentialsByCode) : null
  ), [credentialsByCode, data])
  const ownedProviderCodesByModel = useMemo<ReadonlyMap<string, ReadonlySet<string>>>(() => {
    if (!normalizedData) return new Map()
    const result = new Map<string, ReadonlySet<string>>()
    for (const modelCode of Object.keys(normalizedData.models)) {
      result.set(
        modelCode,
        new Set(ownedProviderCodesForModel(normalizedData, modelCode, credentialsByCode)),
      )
    }
    return result
  }, [normalizedData, credentialsByCode])
  const providerModelsByRouteId = useMemo<ReadonlyMap<string, ProviderModelOption>>(() => (
    new Map(modelGroups.flatMap((group) => (
      group.provider_models.map((providerModel) => [providerModel.route_id, providerModel] as const)
    )))
  ), [modelGroups])
  const bundleModelGroups = useMemo(() => (
    normalizedData ? modelBundleGroupsFromData(normalizedData, providerModelsByRouteId) : []
  ), [normalizedData, providerModelsByRouteId])
  const availableModelGroups = useMemo(() => (
    [...bundleModelGroups, ...modelGroups]
  ), [bundleModelGroups, modelGroups])
  const modelDisplayNamesByCode = useMemo<ReadonlyMap<string, string>>(() => {
    if (!normalizedData) return new Map()
    const displayNameByCanonicalId = new Map<string, string>()
    const displayNameByRouteId = new Map<string, string>()

    for (const modelGroup of availableModelGroups) {
      const displayName = modelGroup.display_name || modelGroup.canonical_id
      displayNameByCanonicalId.set(modelGroup.canonical_id, displayName)
      for (const providerModel of modelGroup.provider_models) {
        displayNameByRouteId.set(providerModel.route_id, displayName)
      }
    }

    const result = new Map<string, string>()
    for (const [modelCode, model] of Object.entries(normalizedData.models)) {
      const directDisplayName = displayNameByCanonicalId.get(modelCode)
      if (directDisplayName) {
        result.set(modelCode, directDisplayName)
        continue
      }

      const providerRouteIds = Object.keys(model.providers)
      const routeDisplayName = providerRouteIds
        .map((providerCode) => displayNameByRouteId.get(providerCode))
        .find((displayName): displayName is string => Boolean(displayName))
      if (routeDisplayName) {
        result.set(modelCode, routeDisplayName)
      }
    }
    return result
  }, [availableModelGroups, normalizedData])

  // #46/#47: read the live test state ENTIRELY from the module-scoped backend
  // mirror (role-test-store). The component holds NO copy of its own — running
  // progress, last results and error banners all project from the store, so an
  // in-flight test survives a tab switch / remount (the store is module-scoped
  // and keeps polling the backend job).
  const roleTestStore = useRoleTestStore()
  const testStatusesByRole = useMemo(() => (
    roleTestStatusesByRole(roleTestStore)
  ), [roleTestStore])

  // On mount, seed badges from the persisted last-known results so a
  // remount/restart shows prior status instead of resetting to untested. Seeding
  // is idempotent and never clobbers a running test (see mergePersistedRoleTestResults).
  useEffect(() => {
    void seedPersistedRoleTestResults()
  }, [])
  const modelGroupsByIdRef = useRef<Map<string, ModelGroup>>(new Map())
  const baseModelGroupsByIdRef = useRef<Map<string, ModelGroup>>(new Map())
  const normalizedDataRef = useRef<RolesData | null>(normalizedData)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const modelGroupsById = useMemo(
    () => new Map(availableModelGroups.map((group) => [group.canonical_id, group])),
    [availableModelGroups],
  )
  const baseModelGroupsById = useMemo(
    () => new Map(modelGroups.map((group) => [group.canonical_id, group])),
    [modelGroups],
  )

  useEffect(() => {
    modelGroupsByIdRef.current = modelGroupsById
  }, [modelGroupsById])

  useEffect(() => {
    baseModelGroupsByIdRef.current = baseModelGroupsById
  }, [baseModelGroupsById])

  useEffect(() => {
    normalizedDataRef.current = normalizedData
  }, [normalizedData])

  useEffect(() => {
    if (data && normalizedData && normalizedData !== data) {
      onChange(normalizedData)
    }
  }, [data, normalizedData, onChange])

  const {
    availableModelDragPreview,
    availableModelDragPreviewNodeRef,
    getActiveAvailableModelDragId,
    handleAvailableModelPointerDown,
  } = useAvailableModelPointerDrag({
    getPreviewLabel: useCallback((modelId: string) => {
      const modelGroup = modelGroupsByIdRef.current.get(modelId)
      return modelGroup?.display_name || modelGroup?.canonical_id || modelId
    }, []),
    onDrop: useCallback(({ modelId, target }) => {
      const dropZone = target?.closest("[data-model-drop-zone]") ?? null
      const roleElement = dropZone?.closest<HTMLElement>("[data-role-name]")
      const bundleElement = dropZone?.closest<HTMLElement>("[data-model-bundle-id]")
      const roleName = roleElement?.dataset.roleName
      const bundleId = bundleElement?.dataset.modelBundleId
      const latestData = normalizedDataRef.current
      if (!latestData) return
      if (roleName) {
        // #51: a dragged bundle attaches as a LIVE REFERENCE (bundle_id), not a
        // snapshot copy — so editing the bundle later reflects on every role that
        // links to it after re-projection.
        if (modelId.startsWith(BUNDLE_DRAG_PREFIX)) {
          onChangeRef.current(attachBundleReferenceToRole(latestData, roleName, modelId))
          return
        }
        const modelGroup = modelGroupsByIdRef.current.get(modelId)
        if (!modelGroup) {
          toast.error(modelDropFailureMessage({
            modelId,
            destination: roleName,
            reason: "source is no longer available",
          }))
          return
        }
        const result = appendModelGroupToRoleWithResult(
          latestData,
          roleName,
          modelGroup,
        )
        if (result.error) {
          toast.error(result.error)
          return
        }
        onChangeRef.current(result.data)
        return
      }
      if (bundleId) {
        if (modelId.startsWith("bundle:")) {
          toast.error(modelDropFailureMessage({
            modelId,
            destination: "model bundle",
            reason: "model bundles cannot be nested",
          }))
          return
        }
        const modelGroup = baseModelGroupsByIdRef.current.get(modelId)
        if (!modelGroup) {
          toast.error(modelDropFailureMessage({
            modelId,
            destination: "model bundle",
            reason: "source is no longer available",
          }))
          return
        }
        onChangeRef.current(appendModelGroupToBundle(
          latestData,
          bundleId,
          modelGroup,
        ))
        return
      }
      toast.error(modelDropFailureMessage({
        modelId,
        destination: "LLM Roles",
        reason: "drop target was not recognized",
      }))
    }, []),
  })
  const getAvailableModelGroup = useCallback(
    (modelGroupId: string) => modelGroupsById.get(modelGroupId) ?? null,
    [modelGroupsById],
  )
  const handleRunTestChain = useCallback(
    (roleName: string) => {
      // The store projects running/result/error into the mirror; #47 未保存先拒测
      // is handled inside runRoleTest via the validationError argument.
      void runRoleTest(roleName, {
        beforeRoleTest: onBeforeRoleTest,
        afterRoleTest: onAfterRoleTest,
        validationError: error,
      })
    },
    [error, onAfterRoleTest, onBeforeRoleTest],
  )
  // #50b: bundle test reuses the same backend mirror, keyed under __bundle__{id}.
  const handleTestBundle = useCallback(
    (bundleId: string) => {
      void runBundleTest(bundleId, {
        beforeBundleTest: onBeforeRoleTest,
        afterBundleTest: onAfterRoleTest,
      })
    },
    [onAfterRoleTest, onBeforeRoleTest],
  )
  // Project the bundle slice of the shared mirror into per-bundle props. The
  // store keys bundle entries under __bundle__{id}; testStatusesByRole already
  // projects every key (roles + bundles) into chain-status maps.
  const bundleTestState = useMemo(() => {
    const statusesByBundle: Record<string, (typeof testStatusesByRole)[string]> = {}
    const runningByBundle: Record<string, boolean> = {}
    const errorsByBundle: Record<string, string | undefined> = {}
    for (const [bundleId] of visibleModelBundleEntries(normalizedData ?? { roles: {}, models: {}, providers: {} } as RolesData)) {
      const key = bundleTestStoreKey(bundleId)
      statusesByBundle[bundleId] = testStatusesByRole[key] ?? {}
      runningByBundle[bundleId] = roleTestStore[key]?.running ?? false
      errorsByBundle[bundleId] = roleTestStore[key]?.error
    }
    return { statusesByBundle, runningByBundle, errorsByBundle }
  }, [normalizedData, roleTestStore, testStatusesByRole])
  if (!normalizedData) {
    return (
      <LlmRolesLayout sidebar={<LlmRolesModelsSkeleton />}>
        <SectionTitle title={t("llmRoles.title")} description={t("llmRoles.loadingDescription")} />
        <LlmRolesRolesSkeleton />
      </LlmRolesLayout>
    )
  }

  return (
    <>
      <LlmRolesLayout
        sidebar={(
          <AvailableModelsSidebar
            modelGroups={modelGroups}
            pinnedModelGroups={bundleModelGroups}
            onModelPointerDown={handleAvailableModelPointerDown}
            onNavigateToApiKeys={onNavigateToApiKeys}
            onReprobed={onAfterRoleTest}
          />
        )}
      >
        <SectionTitle
          title={t("llmRoles.title")}
          description={t("llmRoles.description")}
          trailing={<SaveStatusBadge status={saveStatus} />}
        />

        {error ? <div className="mb-3 text-xs text-destructive">{t("llmRoles.validationFailed", { error })}</div> : null}

        <RoleCardList
          data={normalizedData}
          credentialsByCode={credentialsByCode}
          modelDisplayNamesByCode={modelDisplayNamesByCode}
          ownedProviderCodesByModel={ownedProviderCodesByModel}
          providerModelsByRouteId={providerModelsByRouteId}
          testStatusesByRole={testStatusesByRole}
          roleTestResults={Object.fromEntries(Object.entries(roleTestStore).map(([roleName, state]) => [roleName, state.result]))}
          roleTestErrors={Object.fromEntries(Object.entries(roleTestStore).map(([roleName, state]) => [roleName, state.error]))}
          roleTestRunningByName={Object.fromEntries(Object.entries(roleTestStore).map(([roleName, state]) => [roleName, state.running]))}
          onRunTestChain={handleRunTestChain}
          getActiveAvailableModelDragId={getActiveAvailableModelDragId}
          getAvailableModelGroup={getAvailableModelGroup}
          onChange={onChange}
          onDeleteRole={onDeleteRole ?? ((roleName) => onChange(removeRole(normalizedData, roleName)))}
        />
        <AdvancedModelBundlesSection
          data={normalizedData}
          credentialsByCode={credentialsByCode}
          modelDisplayNamesByCode={modelDisplayNamesByCode}
          modelGroups={modelGroups}
          providerModelsByRouteId={providerModelsByRouteId}
          testStatusesByBundle={bundleTestState.statusesByBundle}
          testRunningByBundle={bundleTestState.runningByBundle}
          bundleTestErrors={bundleTestState.errorsByBundle}
          onTestBundle={handleTestBundle}
          getActiveAvailableModelDragId={getActiveAvailableModelDragId}
          onChange={onChange}
          onDeleteBundle={onDeleteModelBundle ?? ((bundleId) => onChange(removeModelBundle(normalizedData, bundleId)))}
        />
      </LlmRolesLayout>
      <AvailableModelDragPreview drag={availableModelDragPreview} nodeRef={availableModelDragPreviewNodeRef} />
    </>
  )
}

export { modelDropFailureMessage } from "./role-utils"

function LlmRolesLayout({ children, sidebar }: { children: ReactNode; sidebar: ReactNode }) {
  return (
    <div className="grid min-h-full min-w-0 gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden 2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]">
      <ScrollArea className="min-h-0 min-w-0 overflow-hidden lg:h-full [&_[data-slot=scroll-area-scrollbar]]:hidden [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:!min-w-0 [&_[data-slot=scroll-area-viewport]>div]:!w-full">
        <div className="pr-2">
          {children}
        </div>
      </ScrollArea>
      {sidebar}
    </div>
  )
}

function LlmRolesRolesSkeleton() {
  return (
    <div className="space-y-4">
      <Card size="sm" className="rounded-md">
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-72 max-w-full" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
      <Card size="sm" className="rounded-md">
        <CardHeader>
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-4 w-64 max-w-full" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    </div>
  )
}

function LlmRolesModelsSkeleton() {
  return (
    <aside className="min-w-0 lg:sticky lg:top-0 lg:h-full lg:min-h-0 lg:self-start">
      <div className="flex min-h-0 flex-col gap-3 lg:h-full">
        <div className="space-y-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-8 w-full" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </div>
    </aside>
  )
}
