import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react"
import { AlertTriangle, Boxes, GripVertical, ListRestart, Plus, Route, WandSparkles, X } from "lucide-react"
import type { ModelProfile, RegistryResponse, RolesData } from "@/api/llm"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  CatalogAccordion,
  CatalogAccordionContent,
  CatalogAccordionItem,
  CatalogAccordionTrigger,
} from "@/components/ui/catalog-accordion"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import {
  appendRouteToRole,
  createEmptyRole,
  groupAvailableRoutes,
  moveRouteInRole,
  removeRouteFromRole,
  routeDisplayName,
} from "./role-utils"
import { SectionTitle } from "./shared"

export interface RouteDragData {
  type: "route"
  route_id: string
}

export interface AvailableRouteDragPreviewState {
  dragging: true
  routeId: string
  x: number
  y: number
}

export function createRouteDragData(routeId: string): RouteDragData {
  return { type: "route", route_id: routeId }
}

export function LlmRolesTab({
  data,
  registry,
  saveStatus,
  error,
  onChange,
  onProbeRole,
  onApplyProfile,
}: {
  data: RolesData | null
  registry: RegistryResponse | null
  saveStatus: SaveStatus
  error: string | null
  onChange: (next: RolesData) => void
  onProbeRole: (roleName: string) => void
  onApplyProfile: (roleName: string, profileId: string) => void
}) {
  const activeRouteDragRef = useRef<RouteDragData | null>(null)
  const pointerDragRef = useRef<{ routeId: string; startX: number; startY: number; dragging: boolean } | null>(null)
  const latestDataRef = useRef<RolesData | null>(data)
  const suppressClickRef = useRef(false)
  const releaseTimerRef = useRef<number | null>(null)
  const [dragPreview, setDragPreview] = useState<AvailableRouteDragPreviewState | null>(null)
  const [selectedRoleName, setSelectedRoleName] = useState<string | null>(null)

  const roles = data?.roles ?? {}
  const roleNames = Object.keys(roles)
  const effectiveSelectedRole = selectedRoleName && roles[selectedRoleName] ? selectedRoleName : roleNames[0] ?? null
  const routeGroups = useMemo(() => registry ? groupAvailableRoutes(registry) : [], [registry])
  const profiles = Object.values(data?.model_profiles ?? {})

  useEffect(() => {
    latestDataRef.current = data
  }, [data])

  useEffect(() => {
    if (!effectiveSelectedRole && roleNames.length > 0) {
      setSelectedRoleName(roleNames[0])
    }
  }, [effectiveSelectedRole, roleNames])

  useEffect(() => {
    const movementThreshold = 6

    function releaseDragUi() {
      document.documentElement.removeAttribute("data-available-route-dragging")
    }

    function clearClickSuppression() {
      suppressClickRef.current = false
      if (releaseTimerRef.current !== null) {
        window.clearTimeout(releaseTimerRef.current)
        releaseTimerRef.current = null
      }
    }

    function clearPointerDrag({ suppressClick = false }: { suppressClick?: boolean } = {}) {
      pointerDragRef.current = null
      activeRouteDragRef.current = null
      setDragPreview(null)
      releaseDragUi()
      if (suppressClick) {
        suppressClickRef.current = true
        releaseTimerRef.current = window.setTimeout(clearClickSuppression, 1000)
      } else {
        clearClickSuppression()
      }
    }

    function handlePointerMove(event: PointerEvent) {
      const drag = pointerDragRef.current
      if (!drag) return
      const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY)
      if (distance >= movementThreshold) {
        drag.dragging = true
        document.documentElement.dataset.availableRouteDragging = "true"
      }
      if (drag.dragging) {
        setDragPreview({ dragging: true, routeId: drag.routeId, x: event.clientX, y: event.clientY })
        event.preventDefault()
      }
    }

    function handlePointerUp(event: PointerEvent) {
      const drag = pointerDragRef.current
      if (!drag?.dragging) {
        clearPointerDrag()
        return
      }
      const target = document.elementFromPoint(event.clientX, event.clientY)
      const dropZone = target instanceof Element ? target.closest("[data-route-drop-zone]") : null
      const roleElement = dropZone?.closest<HTMLElement>("[data-role-name]")
      const roleName = roleElement?.dataset.roleName
      const latestData = latestDataRef.current
      event.preventDefault()
      event.stopPropagation()
      clearPointerDrag({ suppressClick: true })
      if (!roleName || !latestData) return
      onChange(updateRole(latestData, roleName, (role) => appendRouteToRole(role, drag.routeId)))
    }

    function handleClickCapture(event: MouseEvent) {
      if (!suppressClickRef.current) return
      event.preventDefault()
      event.stopPropagation()
      event.stopImmediatePropagation()
      clearClickSuppression()
    }

    window.addEventListener("pointermove", handlePointerMove, { passive: false })
    window.addEventListener("pointerup", handlePointerUp)
    window.addEventListener("pointercancel", () => clearPointerDrag())
    window.addEventListener("click", handleClickCapture, true)
    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      window.removeEventListener("click", handleClickCapture, true)
      releaseDragUi()
      clearClickSuppression()
    }
  }, [onChange])

  function handleRoutePointerDown(routeId: string, event: ReactPointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return
    activeRouteDragRef.current = createRouteDragData(routeId)
    pointerDragRef.current = { routeId, startX: event.clientX, startY: event.clientY, dragging: false }
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch {
      // Pointer capture is best-effort in browser/Tauri shells.
    }
  }

  if (!data || !registry) {
    return (
      <LlmRolesLayout sidebar={<LlmRolesRoutesSkeleton />}>
        <SectionTitle title="LLM Roles" description="Edit explicit route fallback chains." />
        <LlmRolesRolesSkeleton />
      </LlmRolesLayout>
    )
  }

  return (
    <>
      <LlmRolesLayout
        sidebar={(
          <AvailableRoutesSidebar
            routeGroups={routeGroups}
            selectedRoleName={effectiveSelectedRole}
            onRoutePointerDown={handleRoutePointerDown}
            onAddRoute={(routeId) => {
              if (!effectiveSelectedRole) return
              onChange(updateRole(data, effectiveSelectedRole, (role) => appendRouteToRole(role, routeId)))
            }}
          />
        )}
      >
        <SectionTitle
          title="LLM Roles"
          description="Build deterministic route fallback chains. Capabilities lint the chain; they never reroute it."
          trailing={<SaveStatusBadge status={saveStatus} />}
        />

        {error ? <div className="mb-3 text-xs text-destructive">Validation failed: {error}</div> : null}

        <ModelProfilesPanel
          profiles={profiles}
          selectedRoleName={effectiveSelectedRole}
          onApplyProfile={(profileId) => {
            if (!effectiveSelectedRole) return
            onApplyProfile(effectiveSelectedRole, profileId)
          }}
        />

        <CatalogAccordion type="multiple" defaultValue={["graph", "copilot"]}>
          <CatalogAccordionItem value="graph">
            <CatalogAccordionTrigger>
              Graph Agent Roles <Boxes className="size-4 text-primary" />
            </CatalogAccordionTrigger>
            <CatalogAccordionContent className="space-y-3">
              {roleNames.length === 0 ? (
                <EmptyRoles data={data} onChange={onChange} />
              ) : null}
              {roleNames.map((roleName) => (
                <RoleCard
                  key={roleName}
                  roleName={roleName}
                  role={data.roles[roleName]}
                  registry={registry}
                  selected={roleName === effectiveSelectedRole}
                  lintMessages={registry.lint_results.filter((lint) => lint.role_name === roleName)}
                  onSelect={() => setSelectedRoleName(roleName)}
                  onProbe={() => onProbeRole(roleName)}
                  onMoveRoute={(fromIndex, toIndex) => {
                    onChange(updateRole(data, roleName, (role) => moveRouteInRole(role, fromIndex, toIndex)))
                  }}
                  onRemoveRoute={(routeId) => {
                    onChange(updateRole(data, roleName, (role) => removeRouteFromRole(role, routeId)))
                  }}
                />
              ))}
            </CatalogAccordionContent>
          </CatalogAccordionItem>
        </CatalogAccordion>
      </LlmRolesLayout>
      <AvailableRouteDragPreview drag={dragPreview} />
    </>
  )
}

function ModelProfilesPanel({
  profiles,
  selectedRoleName,
  onApplyProfile,
}: {
  profiles: ModelProfile[]
  selectedRoleName: string | null
  onApplyProfile: (profileId: string) => void
}) {
  return (
    <Card size="sm" className="mb-5 rounded-md">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <WandSparkles className="size-4 text-primary" />
          Model Profiles
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {profiles.length === 0 ? (
          <div className="rounded-md border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">
            No model profiles configured.
          </div>
        ) : null}
        {profiles.map((profile) => (
          <article key={profile.model_profile_id} className="rounded-md border border-border p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="break-words text-xs font-semibold text-foreground">{profile.display_name}</div>
                <div className="break-all font-mono text-[11px] text-muted-foreground">{profile.model_profile_id}</div>
              </div>
              <Button
                type="button"
                size="sm"
                disabled={!selectedRoleName}
                onClick={() => onApplyProfile(profile.model_profile_id)}
              >
                Apply
              </Button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {profile.tags.map((tag) => <Badge key={tag} variant="secondary">{tag}</Badge>)}
            </div>
          </article>
        ))}
      </CardContent>
    </Card>
  )
}

function RoleCard({
  roleName,
  role,
  registry,
  selected,
  lintMessages,
  onSelect,
  onProbe,
  onMoveRoute,
  onRemoveRoute,
}: {
  roleName: string
  role: RolesData["roles"][string]
  registry: RegistryResponse
  selected: boolean
  lintMessages: RegistryResponse["lint_results"]
  onSelect: () => void
  onProbe: () => void
  onMoveRoute: (fromIndex: number, toIndex: number) => void
  onRemoveRoute: (routeId: string) => void
}) {
  return (
    <Card
      size="sm"
      data-role-name={roleName}
      data-selected={selected}
      className="rounded-md data-[selected=true]:ring-2 data-[selected=true]:ring-primary/50"
      onClick={onSelect}
    >
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="break-words text-sm">{roleName}</CardTitle>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {role.fallback_chain.length} route fallback{role.fallback_chain.length === 1 ? "" : "s"}
            </p>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={(event) => {
            event.stopPropagation()
            onProbe()
          }}>
            <ListRestart className="size-3.5" />
            Probe Role
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div data-route-drop-zone="true" className="min-h-16 rounded-md border border-dashed border-border p-2">
          {role.fallback_chain.length === 0 ? (
            <div className="py-4 text-center text-xs text-muted-foreground">Drop a route here.</div>
          ) : null}
          {role.fallback_chain.map((entry, index) => {
            const route = registry.provider_routes[entry.route_id]
            return (
              <div key={`${entry.route_id}-${index}`} className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-card p-2 last:mb-0">
                <div className="flex min-w-0 items-start gap-2">
                  <GripVertical className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <div className="break-words text-xs font-medium text-foreground">
                      {routeDisplayName(route, entry.route_id)}
                    </div>
                    <div className="break-all font-mono text-[11px] text-muted-foreground">{entry.route_id}</div>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {route ? <Badge variant={route.status === "verified" ? "default" : "secondary"}>{route.status}</Badge> : <Badge variant="destructive">missing</Badge>}
                  <Button type="button" size="sm" variant="ghost" disabled={index === 0} onClick={(event) => {
                    event.stopPropagation()
                    onMoveRoute(index, index - 1)
                  }}>Up</Button>
                  <Button type="button" size="sm" variant="ghost" disabled={index === role.fallback_chain.length - 1} onClick={(event) => {
                    event.stopPropagation()
                    onMoveRoute(index, index + 1)
                  }}>Down</Button>
                  <Button type="button" size="icon" variant="ghost" aria-label={`Remove route ${entry.route_id}`} onClick={(event) => {
                    event.stopPropagation()
                    onRemoveRoute(entry.route_id)
                  }}>
                    <X className="size-3.5" />
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
        {lintMessages.length > 0 ? (
          <div className="space-y-1">
            {lintMessages.map((lint) => (
              <div key={`${lint.route_id}-${lint.capability}-${lint.message}`} className="flex items-start gap-2 rounded-md border border-border/70 p-2 text-xs">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                <span className="min-w-0 break-words text-muted-foreground">{lint.message}</span>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function AvailableRoutesSidebar({
  routeGroups,
  selectedRoleName,
  onRoutePointerDown,
  onAddRoute,
}: {
  routeGroups: ReturnType<typeof groupAvailableRoutes>
  selectedRoleName: string | null
  onRoutePointerDown: (routeId: string, event: ReactPointerEvent<HTMLButtonElement>) => void
  onAddRoute: (routeId: string) => void
}) {
  return (
    <aside className="min-w-0 lg:sticky lg:top-0 lg:h-full lg:min-h-0 lg:self-start">
      <div className="flex min-h-0 flex-col gap-3 lg:h-full">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Route className="size-4 text-primary" />
            Available Routes
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Drag a route into {selectedRoleName ?? "a role"} or add it directly.
          </p>
        </div>
        <ScrollArea className="min-h-0 flex-1 [&_[data-slot=scroll-area-scrollbar]]:hidden">
          <CatalogAccordion type="multiple" defaultValue={routeGroups.map((group) => group.canonical_id)}>
            {routeGroups.map((group) => (
              <CatalogAccordionItem key={group.canonical_id} value={group.canonical_id}>
                <CatalogAccordionTrigger>{group.display_name}</CatalogAccordionTrigger>
                <CatalogAccordionContent className="space-y-2">
                  {group.routes.map((route) => (
                    <button
                      key={route.route_id}
                      type="button"
                      draggable
                      data-route-id={route.route_id}
                      onPointerDown={(event) => onRoutePointerDown(route.route_id, event)}
                      onClick={() => onAddRoute(route.route_id)}
                      className="flex w-full select-none flex-col rounded-md border border-border bg-card p-2 text-left text-xs hover:bg-muted/60"
                    >
                      <span className="break-words font-medium text-foreground">{route.display_name}</span>
                      <span className="break-all font-mono text-[11px] text-muted-foreground">{route.route_id}</span>
                    </button>
                  ))}
                </CatalogAccordionContent>
              </CatalogAccordionItem>
            ))}
          </CatalogAccordion>
        </ScrollArea>
      </div>
    </aside>
  )
}

function EmptyRoles({ data, onChange }: { data: RolesData; onChange: (next: RolesData) => void }) {
  return (
    <Button
      type="button"
      variant="outline"
      onClick={() => onChange({
        ...data,
        roles: { graph_agent: createEmptyRole() },
      })}
    >
      <Plus className="size-3.5" />
      Add Graph Agent Role
    </Button>
  )
}

export function AvailableRouteDragPreview({ drag }: { drag: AvailableRouteDragPreviewState | null }) {
  if (!drag?.dragging) return null

  return (
    <div
      data-available-route-drag-preview="true"
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-50 max-w-72 select-none rounded-md border border-border bg-popover px-3 py-2 text-left shadow-lg ring-2 ring-primary/40"
      style={{ transform: `translate3d(${drag.x}px, ${drag.y}px, 0) translate(-50%, -50%)` }}
    >
      <div className="truncate font-mono text-xs text-foreground">{drag.routeId}</div>
    </div>
  )
}

function LlmRolesLayout({ children, sidebar }: { children: React.ReactNode; sidebar: React.ReactNode }) {
  return (
    <div className="grid min-h-full min-w-0 gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden 2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]">
      <ScrollArea className="min-h-0 min-w-0 overflow-hidden lg:h-full [&_[data-slot=scroll-area-scrollbar]]:hidden [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:!min-w-0 [&_[data-slot=scroll-area-viewport]>div]:!w-full">
        <div className="pr-2">{children}</div>
      </ScrollArea>
      {sidebar}
    </div>
  )
}

function updateRole(data: RolesData, roleName: string, updater: (role: RolesData["roles"][string]) => RolesData["roles"][string]): RolesData {
  const role = data.roles[roleName] ?? createEmptyRole()
  return {
    ...data,
    roles: {
      ...data.roles,
      [roleName]: updater(role),
    },
  }
}

function SaveStatusBadge({ status }: { status: SaveStatus }) {
  return <Badge variant={status === "error" ? "destructive" : "secondary"}>{status}</Badge>
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
        </CardContent>
      </Card>
    </div>
  )
}

function LlmRolesRoutesSkeleton() {
  return (
    <aside className="min-w-0 lg:sticky lg:top-0 lg:h-full lg:min-h-0 lg:self-start">
      <div className="flex min-h-0 flex-col gap-3 lg:h-full">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    </aside>
  )
}
