import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import { useRoleTestChainRunner } from "@/hooks/useRoleTestChainRunner"
import type { CredentialsState, ModelGroup, RolesData } from "../../../api/llm"
import { AvailableModelsSidebar } from "./llm-roles/AvailableModelsSidebar"
import { RoleSaveStatusBadge } from "./llm-roles/RoleBadges"
import { RoleCardList } from "./llm-roles/RoleCardList"
import { appendModelGroupToRole, pruneInvalidRoleProviders } from "./role-utils"
import { SectionTitle } from "./shared"

export { ModelSettingsDialog, ModelSettingsFields } from "./llm-roles/ModelSettingsDialog"

interface AvailableModelPointerDrag {
  dragging: boolean
  modelId: string
  startX: number
  startY: number
}

export interface AvailableModelDragPreviewState {
  dragging: true
  modelId: string
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
  const credentialsByCode = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )
  const normalizedData = useMemo(() => (
    data ? pruneInvalidRoleProviders(data, credentialsByCode) : null
  ), [credentialsByCode, data])
  const { isRunning: testChainRunning, run: runTestChain, statuses: testStatuses } = useRoleTestChainRunner()
  const activeAvailableModelDragRef = useRef<string | null>(null)
  const availableModelPointerDragRef = useRef<AvailableModelPointerDrag | null>(null)
  const suppressAvailableModelDragClickRef = useRef(false)
  const availableModelDragReleaseTimerRef = useRef<number | null>(null)
  const [availableModelDragPreview, setAvailableModelDragPreview] = useState<AvailableModelDragPreviewState | null>(null)
  const modelGroupsByIdRef = useRef<Map<string, ModelGroup>>(new Map())
  const normalizedDataRef = useRef<RolesData | null>(normalizedData)
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
      setAvailableModelDragPreview(null)
      releaseDragUi()
      if (suppressClick) {
        scheduleDragSuppressionRelease()
      } else {
        clearDragClickSuppression()
      }
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
        setAvailableModelDragPreview({
          dragging: true,
          modelId: drag.modelId,
          x: event.clientX,
          y: event.clientY,
        })
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

      onChange(appendModelGroupToRole(
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
      clearDragClickSuppression()
    }
  }, [onChange])

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
            onModelDragStart={(modelId) => {
              activeAvailableModelDragRef.current = modelId
            }}
            onModelDragEnd={() => {
              activeAvailableModelDragRef.current = null
            }}
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
          testStatuses={testStatuses}
          testChainRunning={testChainRunning}
          onRunTestChain={(roleName) => void runTestChain({ data: normalizedData, roleName, credentials })}
          getActiveAvailableModelDragId={() => activeAvailableModelDragRef.current}
          getAvailableModelGroup={(modelGroupId) => modelGroupsById.get(modelGroupId) ?? null}
          onChange={onChange}
        />
      </LlmRolesLayout>
      <AvailableModelDragPreview drag={availableModelDragPreview} />
    </>
  )
}

export function AvailableModelDragPreview({
  drag,
}: {
  drag: AvailableModelDragPreviewState | null
}) {
  if (!drag?.dragging) return null

  return (
    <div
      data-available-model-drag-preview="true"
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-50 max-w-72 select-none rounded-md border border-border bg-popover px-3 py-2 text-left shadow-lg ring-2 ring-primary/40"
      style={{
        transform: `translate3d(${drag.x}px, ${drag.y}px, 0) translate(-50%, -50%)`,
      }}
    >
      <div className="truncate font-mono text-xs text-foreground">{drag.modelId}</div>
    </div>
  )
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
