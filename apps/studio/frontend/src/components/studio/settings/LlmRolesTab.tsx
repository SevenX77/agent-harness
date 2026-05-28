import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode, type RefObject } from "react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import { useRoleTestChainRunner } from "@/hooks/useRoleTestChainRunner"
import type { CredentialsState, ModelGroup, RolesData } from "../../../api/llm"
import { AvailableModelsSidebar } from "./llm-roles/AvailableModelsSidebar"
import { RoleSaveStatusBadge } from "./llm-roles/RoleBadges"
import { RoleCardList } from "./llm-roles/RoleCardList"
import { appendModelGroupToRole, ownedProviderCodesForModel, pruneInvalidRoleProviders } from "./role-utils"
import { credentialsByProviderCode } from "./route-credentials"
import { SectionTitle } from "./shared"

export { ModelSettingsDialog, ModelSettingsFields } from "./llm-roles/ModelSettingsDialog"

interface AvailableModelPointerDrag {
  dragging: boolean
  previewVisible: boolean
  modelId: string
  startX: number
  startY: number
}

export interface AvailableModelDragPreviewState {
  dragging: true
  modelId: string
  label: string
  x: number
  y: number
}

export function LlmRolesTab({
  data,
  credentials,
  modelGroups,
  saveStatus,
  error,
  onChange,
}: {
  data: RolesData | null
  credentials: CredentialsState
  modelGroups: ModelGroup[]
  saveStatus: SaveStatus
  error: string | null
  onChange: (next: RolesData) => void
}) {
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
  const modelDisplayNamesByCode = useMemo<ReadonlyMap<string, string>>(() => {
    if (!normalizedData) return new Map()
    const displayNameByCanonicalId = new Map<string, string>()
    const displayNameByRouteId = new Map<string, string>()

    for (const modelGroup of modelGroups) {
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
  }, [modelGroups, normalizedData])
  const { isRunning: testChainRunning, run: runTestChain, statuses: testStatuses } = useRoleTestChainRunner()
  const activeAvailableModelDragRef = useRef<string | null>(null)
  const availableModelPointerDragRef = useRef<AvailableModelPointerDrag | null>(null)
  const availableModelDragPreviewNodeRef = useRef<HTMLDivElement | null>(null)
  const availableModelDragPreviewFrameRef = useRef<number | null>(null)
  const availableModelDragPreviewPointRef = useRef<{ x: number; y: number } | null>(null)
  const suppressAvailableModelDragClickRef = useRef(false)
  const availableModelDragReleaseTimerRef = useRef<number | null>(null)
  const [availableModelDragPreview, setAvailableModelDragPreview] = useState<AvailableModelDragPreviewState | null>(null)
  const modelGroupsByIdRef = useRef<Map<string, ModelGroup>>(new Map())
  const normalizedDataRef = useRef<RolesData | null>(normalizedData)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const modelGroupsById = useMemo(
    () => new Map(modelGroups.map((group) => [group.canonical_id, group])),
    [modelGroups],
  )

  useEffect(() => {
    modelGroupsByIdRef.current = modelGroupsById
  }, [modelGroupsById])

  useEffect(() => {
    normalizedDataRef.current = normalizedData
  }, [normalizedData])

  useEffect(() => {
    if (data && normalizedData && normalizedData !== data) {
      onChange(normalizedData)
    }
  }, [data, normalizedData, onChange])

  const handleAvailableModelPointerDown = useCallback((
    modelId: string,
    event: ReactPointerEvent<HTMLButtonElement>,
  ) => {
    if (event.button !== 0) return
    activeAvailableModelDragRef.current = modelId
    availableModelPointerDragRef.current = {
      dragging: false,
      previewVisible: false,
      modelId,
      startX: event.clientX,
      startY: event.clientY,
    }
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch {
      // Pointer capture is a progressive enhancement; window listeners still handle the fallback.
    }
  }, [])

  const updateAvailableModelDragPreviewPosition = useCallback((x: number, y: number) => {
    availableModelDragPreviewPointRef.current = { x, y }
    if (availableModelDragPreviewFrameRef.current !== null) return

    availableModelDragPreviewFrameRef.current = window.requestAnimationFrame(() => {
      availableModelDragPreviewFrameRef.current = null
      const point = availableModelDragPreviewPointRef.current
      availableModelDragPreviewPointRef.current = null
      const node = availableModelDragPreviewNodeRef.current
      if (!point || !node) return
      node.style.transform = availableModelDragPreviewTransform(point.x, point.y)
    })
  }, [])

  useEffect(() => {
    const movementThreshold = 6

    function clearDragClickSuppression() {
      suppressAvailableModelDragClickRef.current = false
      if (availableModelDragReleaseTimerRef.current !== null) {
        window.clearTimeout(availableModelDragReleaseTimerRef.current)
        availableModelDragReleaseTimerRef.current = null
      }
    }

    function releaseDragUi() {
      document.documentElement.removeAttribute("data-available-model-dragging")
    }

    function releaseDragPreview({ clearState = true }: { clearState?: boolean } = {}) {
      if (clearState) {
        setAvailableModelDragPreview(null)
      }
      availableModelDragPreviewPointRef.current = null
      if (availableModelDragPreviewFrameRef.current !== null) {
        window.cancelAnimationFrame(availableModelDragPreviewFrameRef.current)
        availableModelDragPreviewFrameRef.current = null
      }
    }

    function scheduleDragSuppressionRelease() {
      suppressAvailableModelDragClickRef.current = true
      if (availableModelDragReleaseTimerRef.current !== null) {
        window.clearTimeout(availableModelDragReleaseTimerRef.current)
      }
      availableModelDragReleaseTimerRef.current = window.setTimeout(() => {
        clearDragClickSuppression()
      }, 1000)
    }

    function clearPointerDrag({ suppressClick = false }: { suppressClick?: boolean } = {}) {
      activeAvailableModelDragRef.current = null
      availableModelPointerDragRef.current = null
      releaseDragPreview()
      releaseDragUi()
      if (suppressClick) {
        scheduleDragSuppressionRelease()
      } else {
        clearDragClickSuppression()
      }
    }

    function previewLabel(modelId: string): string {
      const modelGroup = modelGroupsByIdRef.current.get(modelId)
      return modelGroup?.display_name || modelGroup?.canonical_id || modelId
    }

    function handlePointerMove(event: PointerEvent) {
      const drag = availableModelPointerDragRef.current
      if (!drag) return
      const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY)
      if (distance >= movementThreshold) {
        drag.dragging = true
        document.documentElement.dataset.availableModelDragging = "true"
      }
      if (drag.dragging) {
        if (!drag.previewVisible) {
          drag.previewVisible = true
          setAvailableModelDragPreview({
            dragging: true,
            modelId: drag.modelId,
            label: previewLabel(drag.modelId),
            x: event.clientX,
            y: event.clientY,
          })
        } else {
          updateAvailableModelDragPreviewPosition(event.clientX, event.clientY)
        }
        event.preventDefault()
      }
    }

    function handlePointerUp(event: PointerEvent) {
      const drag = availableModelPointerDragRef.current
      if (!drag?.dragging) {
        clearPointerDrag()
        return
      }

      const target = document.elementFromPoint(event.clientX, event.clientY)
      const dropZone = target instanceof Element ? target.closest("[data-model-drop-zone]") : null
      const roleElement = dropZone?.closest<HTMLElement>("[data-role-name]")
      const roleName = roleElement?.dataset.roleName
      const latestData = normalizedDataRef.current
      event.preventDefault()
      event.stopPropagation()
      clearPointerDrag({ suppressClick: true })
      if (!roleName || !latestData) return
      const modelGroup = modelGroupsByIdRef.current.get(drag.modelId)
      if (!modelGroup) return

      onChangeRef.current(appendModelGroupToRole(
        latestData,
        roleName,
        modelGroup,
      ))
    }

    function handleClickCapture(event: MouseEvent) {
      if (!suppressAvailableModelDragClickRef.current) return
      event.preventDefault()
      event.stopPropagation()
      event.stopImmediatePropagation()
      clearDragClickSuppression()
    }

    function handlePointerCancel() {
      clearPointerDrag()
    }

    window.addEventListener("pointermove", handlePointerMove, { passive: false })
    window.addEventListener("pointerup", handlePointerUp)
    window.addEventListener("pointercancel", handlePointerCancel)
    window.addEventListener("click", handleClickCapture, true)
    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      window.removeEventListener("pointercancel", handlePointerCancel)
      window.removeEventListener("click", handleClickCapture, true)
      releaseDragUi()
      releaseDragPreview({ clearState: false })
      clearDragClickSuppression()
    }
  }, [updateAvailableModelDragPreviewPosition])

  const getActiveAvailableModelDragId = useCallback(
    () => activeAvailableModelDragRef.current,
    [],
  )
  const getAvailableModelGroup = useCallback(
    (modelGroupId: string) => modelGroupsById.get(modelGroupId) ?? null,
    [modelGroupsById],
  )
  const handleRunTestChain = useCallback(
    (roleName: string) => {
      const latestData = normalizedDataRef.current
      if (!latestData) return
      void runTestChain({ data: latestData, roleName, credentials })
    },
    [credentials, runTestChain],
  )

  if (!normalizedData) {
    return (
      <LlmRolesLayout sidebar={<LlmRolesModelsSkeleton />}>
        <SectionTitle title="LLM Roles" description="Edit model and provider fallback order." />
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
            onModelPointerDown={handleAvailableModelPointerDown}
          />
        )}
      >
        <SectionTitle
          title="LLM Roles"
          description="Edit model and provider fallback order. Changes auto-save."
          trailing={<RoleSaveStatusBadge status={saveStatus} />}
        />

        {error ? <div className="mb-3 text-xs text-destructive">Validation failed: {error}</div> : null}

        <RoleCardList
          data={normalizedData}
          credentialsByCode={credentialsByCode}
          modelDisplayNamesByCode={modelDisplayNamesByCode}
          ownedProviderCodesByModel={ownedProviderCodesByModel}
          testStatuses={testStatuses}
          testChainRunning={testChainRunning}
          onRunTestChain={handleRunTestChain}
          getActiveAvailableModelDragId={getActiveAvailableModelDragId}
          getAvailableModelGroup={getAvailableModelGroup}
          onChange={onChange}
        />
      </LlmRolesLayout>
      <AvailableModelDragPreview drag={availableModelDragPreview} nodeRef={availableModelDragPreviewNodeRef} />
    </>
  )
}

export function AvailableModelDragPreview({
  drag,
  nodeRef,
}: {
  drag: AvailableModelDragPreviewState | null
  nodeRef: RefObject<HTMLDivElement | null>
}) {
  if (!drag?.dragging) return null

  return (
    <div
      ref={nodeRef}
      data-available-model-drag-preview="true"
      data-preview-update-mode="imperative-transform"
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-50 max-w-72 select-none rounded-md border border-border bg-popover px-3 py-2 text-left shadow-lg ring-2 ring-primary/40"
      style={{
        transform: availableModelDragPreviewTransform(drag.x, drag.y),
      }}
    >
      <div className="truncate text-xs font-medium text-foreground">{drag.label}</div>
    </div>
  )
}

export function availableModelDragPreviewTransform(x: number, y: number): string {
  return `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`
}

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
