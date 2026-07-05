import { memo, useMemo, useState } from "react"
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import {
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { Image as ImageIcon, Loader2, Plus, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { probeRouteMultimodal, routeAcceptsImageVerified } from "@/api/llm"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { ThinkingBadge } from "../llm-roles/RoleBadges"
import type { CopilotRoutePreview } from "./copilot-role-derivation"
type CopilotAgentStatus = string
import type { CopilotRouteJobStatus } from "./copilot-role-test"

type CopilotSettingsT = (
  key: string,
  options?: Record<string, unknown>,
) => string

function fallbackCopilotT(key: string, options?: Record<string, unknown>): string {
  const defaults: Record<string, string> = {
    "copilot.routeStatus.ready": "Ready",
    "copilot.routeStatus.historicalReady": "Previously Connected",
    "copilot.routeStatus.testing": "Testing",
    "copilot.routeStatus.untested": "Untested",
    "copilot.routeStatus.coolingDown": "Cooling Down",
    "copilot.routeStatus.off": "Off",
    "copilot.routeStatus.failed": "Failed",
    "copilot.routeTooltip.endpointWithHost": "Endpoint: {{provider}} · {{host}}{{protocol}}",
    "copilot.routeTooltip.endpoint": "Endpoint: {{provider}}",
    "copilot.routeTooltip.id": "ID: {{id}}",
    "copilot.routeTooltip.sdkStatus": "Claude Agent SDK: {{status}}",
    "copilot.routeTooltip.detailPrefix": "↳",
    "copilot.routeTooltip.transport": "Transport: {{transport}}",
    "copilot.routeTooltip.toolUse": "Tool use: {{value}}",
    "copilot.routeTooltip.yes": "yes",
    "copilot.routeTooltip.multimodal": "Multimodal: {{value}}",
    "copilot.routeTooltip.textOnly": "text only",
    "copilot.routeTooltip.output": "Output: {{output}}",
    "copilot.routeTooltip.thinking": "Thinking: yes",
  }
  const template = options?.defaultValue ? String(options.defaultValue) : (defaults[key] ?? key)
  return template.replace(/\{\{(\w+)}}/g, (_, name: string) => String(options?.[name] ?? ""))
}

function asCopilotSettingsT(t: unknown): CopilotSettingsT {
  return t as CopilotSettingsT
}

export const CopilotModelGroupCard = memo(function CopilotModelGroupCard({
  modelName,
  modelIndex,
  routes,
  appendableRoutes,
  routeStatusOverrides,
  routeMessages = {},
  onAddRoute,
  onRemoveRoute,
  onReorderRoutes,
  onRemoveModelGroup,
}: {
  modelName: string
  modelIndex: number
  routes: CopilotRoutePreview[]
  appendableRoutes: CopilotRoutePreview[]
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>
  routeMessages?: Record<string, string>
  onAddRoute: (routeId: string) => void
  onRemoveRoute: (routeId: string) => void
  onReorderRoutes: (activeRouteId: string, overRouteId: string) => void
  onRemoveModelGroup?: () => void
}) {
  const { t } = useTranslation("settings")
  const routeIds = useMemo(() => routes.map((route) => route.id), [routes])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function handleDragEnd(event: DragEndEvent) {
    const activeRouteId = String(event.active.id)
    const overRouteId = event.over?.id ? String(event.over.id) : ""
    if (overRouteId && activeRouteId !== overRouteId) {
      onReorderRoutes(activeRouteId, overRouteId)
    }
  }

  return (
    <Item
      variant="outline"
      size="sm"
      data-copilot-model-group="true"
      className="items-center gap-3 bg-background/60 p-3 ring-inset ring-1 ring-foreground/10"
      role="listitem"
    >
      <ItemMedia className="size-6 rounded-sm bg-muted text-[10px] font-mono text-muted-foreground ring-1 ring-foreground/10">
        {modelIndex + 1}
      </ItemMedia>
      <ItemContent className="min-w-0 overflow-hidden gap-1">
        <ItemTitle
          data-copilot-model-title-row="true"
          className="line-clamp-none !grid w-full min-w-0 grid-cols-[minmax(0,max-content)_auto] justify-start gap-x-4 overflow-hidden text-sm/relaxed text-card-foreground"
        >
          <span data-copilot-model-name="true" className="min-w-0 truncate whitespace-nowrap">
            {modelName}
          </span>
          <span data-copilot-model-badge-group="true" className="flex shrink-0 items-center gap-2.5">
            <ThinkingBadge />
          </span>
        </ItemTitle>
      </ItemContent>
      <ItemActions className="ml-auto shrink-0 gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          aria-label={t("copilot.routeCard.removeModelGroup", { model: modelName })}
          data-copilot-model-group-remove="true"
          className="text-muted-foreground hover:text-destructive"
          onClick={onRemoveModelGroup}
          disabled={!onRemoveModelGroup}
        >
          <Trash2 data-role-icon="true" className="size-3 text-muted-foreground" />
        </Button>
      </ItemActions>
      <div className="basis-full pt-2">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={routeIds} strategy={rectSortingStrategy}>
            <div
              data-copilot-provider-grid="true"
              className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,max(12rem,calc((100%_-_0.75rem)/3))),1fr))] justify-start gap-1.5"
              role="list"
              aria-label={t("copilot.routeCard.routeOrderAria", { model: modelName })}
              // R-F17: announce route light/order changes politely (e.g. when a
              // probe updates a chip from "untested" → "ready", or the user
              // reorders the fallback chain) without stealing focus.
              aria-live="polite"
            >
              {routes.map((route, index) => (
                <CopilotProviderTag
                  key={route.id}
                  route={route}
                  index={index}
                  status={agentStatusForRoute(route.agentStatus, route.id, routeStatusOverrides)}
                  message={routeMessages[route.id] ?? null}
                  onRemove={() => onRemoveRoute(route.id)}
                />
              ))}
              <AddRouteMenu routes={appendableRoutes} onAddRoute={onAddRoute} />
            </div>
          </SortableContext>
        </DndContext>
      </div>
    </Item>
  )
})

const CopilotProviderTag = memo(function CopilotProviderTag({
  route,
  index,
  status,
  message,
  onRemove,
}: {
  route: CopilotRoutePreview
  index: number
  status: CopilotRouteJobStatus
  message?: string | null
  onRemove: () => void
}) {
  const { t } = useTranslation("settings")
  const tx = asCopilotSettingsT(t)
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: route.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }
  const row = (
    <div ref={setNodeRef} style={style} className={cn("rounded-md", isDragging && "opacity-70")}>
      <Item
        variant="muted"
        size="xs"
        data-copilot-provider-card="true"
        data-copilot-route-id={route.id}
        data-agent-sdk-status={status}
        data-dnd-drag-surface="copilot-provider"
        className={cn(
          "relative min-h-9 cursor-grab select-none flex-nowrap items-center gap-2 overflow-hidden border-border/70 bg-muted/35 text-muted-foreground active:cursor-grabbing",
          routeSurfaceClass(status),
        )}
        {...attributes}
        {...listeners}
        role="listitem"
        aria-label={t("copilot.routeCard.reorderRoute", { route: route.endpointLabel })}
      >
        <ItemMedia className="size-5 rounded-sm bg-background/80 text-[10px] font-mono text-muted-foreground ring-1 ring-foreground/10">
          {index + 1}
        </ItemMedia>
        <ItemContent className="min-w-0 overflow-hidden gap-0.5">
          <ItemTitle className="line-clamp-none block w-full truncate whitespace-nowrap text-xs/relaxed text-muted-foreground">
            {route.endpointLabel}
          </ItemTitle>
        </ItemContent>
        <ItemActions
          className="ml-auto shrink-0 gap-1"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <RouteStatusLight status={status} />
          <MultimodalTestButton route={route} />
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={t("copilot.routeCard.removeRoute", { route: route.endpointLabel })}
            className="text-muted-foreground hover:text-foreground"
            onClick={onRemove}
          >
            <Trash2 data-role-icon="true" className="size-3 text-muted-foreground" />
          </Button>
        </ItemActions>
      </Item>
    </div>
  )

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{row}</TooltipTrigger>
        <TooltipContent className="max-w-sm whitespace-pre-line break-words">
          {routeTooltip(route, status, message, tx)}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
})

// #11 slice C: per-route 多模态实测。真塞一张图探这条 route 的模型认不认图 —— vision
// 是每个模型各不相同的能力,所以按 route 各测(不是整个角色一把测)。结果只认
// probed_verified(catalog 声称只是提示,不算实测通过)。
function MultimodalTestButton({ route }: { route: CopilotRoutePreview }) {
  const { t } = useTranslation("settings")
  const [testing, setTesting] = useState(false)
  const [verified, setVerified] = useState<boolean | null>(null)

  async function handleTest() {
    if (testing) return
    setTesting(true)
    try {
      const updated = await probeRouteMultimodal(route.id)
      const accepts = routeAcceptsImageVerified(updated)
      setVerified(accepts)
      if (accepts) {
        toast.success(t("copilot.multimodal.acceptsImage", { provider: route.provider }))
      } else {
        toast.warning(t("copilot.multimodal.rejectsImage", { provider: route.provider }))
      }
    } catch (error) {
      const detail = error instanceof Error
        ? error.message
        : t("copilot.multimodal.failedFallback")
      toast.error(t("copilot.multimodal.failed", { provider: route.provider, error: detail }))
    } finally {
      setTesting(false)
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      aria-label={t("copilot.multimodal.aria", { provider: route.provider })}
      title={t("copilot.multimodal.title")}
      className={cn(
        "text-muted-foreground hover:text-foreground",
        verified === true && "text-success hover:text-success",
        verified === false && "text-destructive hover:text-destructive",
      )}
      disabled={testing}
      onClick={handleTest}
    >
      {testing ? (
        <Loader2 data-role-icon="true" className="size-3 animate-spin" />
      ) : (
        <ImageIcon data-role-icon="true" className="size-3" />
      )}
    </Button>
  )
}

function AddRouteMenu({
  routes,
  onAddRoute,
}: {
  routes: CopilotRoutePreview[]
  onAddRoute: (routeId: string) => void
}) {
  const { t } = useTranslation("settings")
  if (routes.length === 0) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          data-copilot-route-add-trigger="true"
          className="h-9 w-full justify-start gap-2 rounded-md px-2.5 text-muted-foreground hover:bg-muted/35 hover:text-foreground"
        >
          <Plus data-role-icon="true" className="size-3 text-muted-foreground" />
          {t("copilot.routeCard.addRoute")}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {routes.map((route) => (
          <DropdownMenuItem key={route.id} onSelect={() => onAddRoute(route.id)}>
            {route.endpointLabel}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function RouteStatusLight({ status }: { status: CopilotRouteJobStatus }) {
  const { t } = useTranslation("settings")
  const label = statusLabel(status, asCopilotSettingsT(t))
  return (
    <span
      role="status"
      aria-label={t("copilot.routeTooltip.sdkStatusAria", {
        status: label,
        defaultValue: `Claude Agent SDK ${label}`,
      })}
      data-copilot-route-status-light="true"
      className={cn("inline-flex size-1.5 shrink-0 rounded-full ring-1 ring-offset-0", lightClass(status))}
    />
  )
}

// The backend ui_state (initialStatus) is typed as a wide string; CopilotRouteJobStatus
// is the narrowed light vocabulary. Every real ui_state value is a member, so coerce
// the fallback to a valid member and default unknowns to "untested" rather than leak a
// raw string into the typed light. (CopilotRouteJobStatus was narrowed from string in a
// shared type; this keeps the ui_state fallback type-correct.)
const ROUTE_JOB_STATUS_VALUES = new Set<CopilotRouteJobStatus>([
  "ready", "historical_ready", "untested", "failed",
  "cooling_down", "off", "testing", "not_tested", "unsupported",
])
function coerceRouteStatus(status: string): CopilotRouteJobStatus {
  return ROUTE_JOB_STATUS_VALUES.has(status as CopilotRouteJobStatus)
    ? (status as CopilotRouteJobStatus)
    : "untested"
}

export function agentStatusForRoute(
  initialStatus: CopilotAgentStatus,
  routeId: string,
  routeStatusOverrides: Record<string, CopilotRouteJobStatus>,
): CopilotRouteJobStatus {
  // atom-57 light authority: an in-flight re-test ('testing') is strictly highest
  // so a stale persisted/seeded verdict can never mask it. Any other present
  // override is the real SDK verdict (live-completed or persisted-and-seeded on
  // mount) and beats the backend ui_state, so the light survives a tab reopen /
  // backend restart. With no override at all, fall back to the initial ui_state.
  const override = routeStatusOverrides[routeId]
  if (override === "testing") return override
  if (override !== undefined) return override
  return coerceRouteStatus(initialStatus)
}

// R-F11: 6-state route light vocabulary aligned with the shared
// `llm-roles/role-route-status.tsx` Tailwind tokens (bg-success / bg-warning /
// bg-destructive / bg-primary). We can't reuse `RoleRouteStatusLight` directly
// because the shared widget is keyed by a 4-state `RoleRouteStatus`
// ("runnable"/"limited"/"blocked"/"testing") and would collapse our 6 states
// (ready / historical_ready / untested / failed / cooling_down / off) — so we
// keep a local renderer but reuse the same color tokens for visual parity.
// "not_tested" / "unsupported" are legacy aliases so persisted/seeded route
// status maps from older sessions still light up correctly.
function routeSurfaceClass(status: CopilotRouteJobStatus): string {
  if (status === "ready") return "border-success-border ring-1 ring-success/25"
  if (status === "historical_ready") return "border-primary/40 ring-1 ring-primary/20"
  if (status === "testing") return "border-primary ring-1 ring-primary/30"
  if (status === "untested" || status === "not_tested") return "border-warning-border ring-1 ring-warning/25"
  if (status === "cooling_down") return "border-warning-border ring-1 ring-warning/30"
  if (status === "off") return "border-border ring-1 ring-foreground/10"
  // status === "failed" / "unsupported"
  return "border-destructive-border ring-1 ring-destructive/25"
}

function lightClass(status: CopilotRouteJobStatus): string {
  if (status === "ready") return "bg-success ring-success-border"
  if (status === "historical_ready") return "bg-primary ring-primary/40"
  if (status === "testing") return "bg-primary ring-primary animate-pulse"
  if (status === "untested" || status === "not_tested") return "bg-muted ring-foreground/20"
  if (status === "cooling_down") return "bg-warning ring-warning-border animate-pulse"
  if (status === "off") return "bg-muted ring-foreground/10"
  // status === "failed" / "unsupported"
  return "bg-destructive ring-destructive-border"
}

function statusLabel(status: CopilotRouteJobStatus, t?: CopilotSettingsT): string {
  const labelKey =
    status === "ready" ? "ready"
    : status === "historical_ready" ? "historicalReady"
    : status === "testing" ? "testing"
    : status === "untested" || status === "not_tested" ? "untested"
    : status === "cooling_down" ? "coolingDown"
    : status === "off" ? "off"
    : "failed"
  const fallback =
    status === "ready" ? "Ready"
    : status === "historical_ready" ? "Previously Connected"
    : status === "testing" ? "Testing"
    : status === "untested" || status === "not_tested" ? "Untested"
    : status === "cooling_down" ? "Cooling Down"
    : status === "off" ? "Off"
    : "Failed"
  return t ? t(`copilot.routeStatus.${labelKey}`, { defaultValue: fallback }) : fallback
}

function routeCapabilityList(route: CopilotRoutePreview, key: string): string[] {
  const capability = (route.capabilities as Record<string, { value?: unknown } | undefined>)[key]
  const value = capability?.value
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
  }
  return typeof value === "string" && value.trim().length > 0 ? [value.trim()] : []
}

function routeCapabilityBool(route: CopilotRoutePreview, key: string): boolean {
  const capability = (route.capabilities as Record<string, { value?: unknown } | undefined>)[key]
  const value = capability?.value
  return value === true || value === "true"
}

function routeTooltip(
  route: CopilotRoutePreview,
  status: CopilotRouteJobStatus,
  message?: string | null,
  t: CopilotSettingsT = fallbackCopilotT,
): string {
  // 与 LLM Roles 的 route 状态 tooltip 对齐:端点 + 协议/method + 多模态 + 工具 + 思考,
  // 再带上本次 SDK 测试的真实结果信息(失败时是具体原因,不再只显示状态)。
  const methods = routeCapabilityList(route, "verified_methods")
  const inputModalities = routeCapabilityList(route, "input_modalities")
  const outputModalities = routeCapabilityList(route, "output_modalities")
  const acceptsImage = inputModalities.some((modality) => modality.toLowerCase() === "image")
  const supportsTools = routeCapabilityBool(route, "tools") || routeCapabilityBool(route, "tool_use")
  const supportsThinking = routeCapabilityBool(route, "thinking")
  const transport = methods.length > 0 ? methods.join(", ") : route.methodId || "—"
  const diagnostic = message?.trim() || null
  const note = route.note?.trim() || null

  const lines = [
    route.modelId,
    route.baseUrlHost
      ? t("copilot.routeTooltip.endpointWithHost", {
          provider: route.provider,
          host: route.baseUrlHost,
          protocol: route.protocol ? ` (${route.protocol})` : "",
        })
      : t("copilot.routeTooltip.endpoint", { provider: route.provider }),
    // 同 host 的多个端点靠 endpoint id 彻底区分。
    route.endpointId ? t("copilot.routeTooltip.id", { id: route.endpointId }) : null,
    t("copilot.routeTooltip.sdkStatus", { status: statusLabel(status, t) }),
    diagnostic ? `${t("copilot.routeTooltip.detailPrefix")} ${diagnostic}` : null,
    t("copilot.routeTooltip.transport", { transport }),
    t("copilot.routeTooltip.toolUse", {
      value: supportsTools ? t("copilot.routeTooltip.yes") : "—",
    }),
    t("copilot.routeTooltip.multimodal", {
      value: acceptsImage
        ? "image"
        : inputModalities.length
        ? inputModalities.join(", ")
        : t("copilot.routeTooltip.textOnly"),
    }),
    outputModalities.length ? t("copilot.routeTooltip.output", { output: outputModalities.join(", ") }) : null,
    supportsThinking ? t("copilot.routeTooltip.thinking") : null,
    note,
  ]
  return lines.filter(Boolean).join("\n")
}
