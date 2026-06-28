import { useRef, useState, type ReactElement, type WheelEvent } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  Brain,
  Box,
  CheckCircle2,
  Copy,
  Eye,
  EyeOff,
  File,
  FileText,
  FlaskConical,
  ImageIcon,
  Loader2,
  MoreVertical,
  Pencil,
  Plus,
  Trash2,
  TriangleAlert,
  Video,
  Volume2,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { requestDeleteConfirmationToast } from "@/components/ui/delete-confirm-toast"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tag } from "@/components/ui/tag"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import i18n from "@/i18n"
import { translateErrorCode, translateTestStatus } from "@/lib/llm-error-messages"
import { cn } from "@/lib/utils"
import type { CredentialsState, ModelInfo, ModelProbeStatus, ProviderTestResult, ProviderType, ProviderUiState, RouteStatus } from "../../../api/llm"
import { inferProviderType, providerCachedTestResult, providerEndpointDraftsForAction, providerTestParamsMatch } from "../settings/provider-utils"
import type { ProviderDraft } from "../settings/types"
import { ManualModelTestPanel } from "./ManualModelTestPanel"
import { RoleNameDialog } from "../settings/llm-roles/RoleNameDialog"

type TestMessageStatus = "not_configured" | "testing" | NonNullable<CredentialsState["providers"][number]["last_test_status"]>
type RouteDisplayStatus = RouteStatus | "unknown" | "testing"
type RouteFailureScope = "model" | "endpoint" | "unknown"
type AggregatedRouteSummary = {
  endpoint_id?: string
  route_id?: string
  status: RouteDisplayStatus
  ui_state?: ProviderUiState
  message?: string | null
  reason_code?: string | null
  failure_scope?: RouteFailureScope
}
type BaseUrlReachabilityState = "connected" | "failed" | "testing" | "unknown"
const availableModelsPreviewLimit = 12
const fieldRowClassName = "grid w-full grid-cols-[minmax(0,1fr)_6.5rem] items-center gap-2"
const fieldActionClassName = "flex min-w-0 items-center justify-center gap-2"
const providerTestButtonClassName = "w-24"
const scrollableInputClassName = "overflow-x-auto whitespace-nowrap text-clip"
const officialProviderNamesByKey: Record<string, string> = {
  anthropic: "Anthropic Official",
  openai: "OpenAI Official",
  gemini: "Gemini Official",
  deepseek: "DeepSeek Official",
  ark: "Ark Official",
}
const officialProviderBrandNames: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Gemini",
  deepseek: "DeepSeek",
  ark: "Ark",
}
const apiKeyMaskChar = "\u2022"

// Diagnostic classification (warning / failure) of a tooltip line is rendered by
// RouteTooltipContent with a colored icon. The classification must stay
// language-independent: instead of re-parsing the translated display text we
// prefix diagnostic lines with a stable, non-translated zero-width sentinel that
// survives any locale and is stripped before the line is shown to the user.
// routeTooltipLineStatus() reads the sentinel first, then falls back to the
// (English) literals so the exported pure function keeps classifying raw strings.
const tooltipDiagnosticSentinel = {
  warning: "\u200b\u26a0\u200b",
  failed: "\u200b\u2717\u200b",
} as const
type TooltipDiagnostic = keyof typeof tooltipDiagnosticSentinel

function markTooltipDiagnostic(kind: TooltipDiagnostic, line: string): string {
  return `${tooltipDiagnosticSentinel[kind]}${line}`
}

function stripTooltipDiagnostic(line: string): string {
  return line
    .replace(tooltipDiagnosticSentinel.warning, "")
    .replace(tooltipDiagnosticSentinel.failed, "")
}

export function apiKeyInputType(): "text" {
  // §1 / atom-22 contract: the secret field is ALWAYS a text input. Masking is
  // done purely with CSS (see apiKeyInputClassName) so the browser/extension
  // password manager is never triggered by a native type=password field.
  return "text"
}

export function apiKeyDisplayValue(value: string, visible: boolean): string {
  if (visible || !value) return value
  return apiKeyMaskChar.repeat(value.length)
}

export function apiKeyInputClassName(
  visible: boolean,
  hasValue = true,
  options: { cssMask?: boolean } = {},
): string {
  // mask-input applies `-webkit-text-security: disc` + a disc font, which also
  // masks the *placeholder* text. Only mask when there is an actual secret to
  // hide; an empty field must keep its placeholder readable (otherwise empty
  // official cards render their "Enter your X API Key" hint as •••).
  const masked = (options.cssMask ?? true) && !visible && hasValue
  return cn(
    scrollableInputClassName,
    visible ? "text-foreground" : "text-muted-foreground",
    masked && "mask-input",
  )
}

export async function copyCredentialValue(value: string, label: string): Promise<void> {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    toast.success(i18n.t("apiKeys.card.copiedToast", { label }))
  } catch {
    toast.error(i18n.t("apiKeys.card.copyFailedToast", { label: label.toLowerCase() }))
  }
}

export function copyAvailableModelId(modelId: string): Promise<void> {
  return copyCredentialValue(modelId, i18n.t("apiKeys.card.modelNameLabel"))
}

export function sortModelInfos(models: ModelInfo[]): ModelInfo[] {
  return [...models].sort((left, right) => {
    const leftKey = modelSortKey(left.id)
    const rightKey = modelSortKey(right.id)
    const primary = leftKey.localeCompare(rightKey, undefined, { numeric: true, sensitivity: "base" })
    return primary !== 0 ? primary : left.id.localeCompare(right.id)
  })
}

export function sortOfficialRouteInfos(models: ModelInfo[]): ModelInfo[] {
  return [...models].sort((left, right) => {
    const statusRank = officialRouteSortRank(left) - officialRouteSortRank(right)
    if (statusRank !== 0) return statusRank
    const leftKey = modelSortKey(left.id)
    const rightKey = modelSortKey(right.id)
    const primary = leftKey.localeCompare(rightKey, undefined, { numeric: true, sensitivity: "base" })
    return primary !== 0 ? primary : left.id.localeCompare(right.id)
  })
}

function officialRouteSortRank(model: ModelInfo): number {
  const status = modelRouteStatus(model)
  const variant = routeStatusTagVariant(status)
  if (variant === "success") return 0
  if (status === "testing") return 1
  if (variant === "destructive") return 4
  if (status === "disabled") return 3
  return 2
}

function modelSortKey(modelId: string): string {
  return modelId.replace(/^~+/, "").toLowerCase()
}

export function TestMessage({
  status,
  latencyMs,
  errorCode,
}: {
  status: TestMessageStatus
  latencyMs?: number | null
  errorCode?: string | null
}) {
  const { t } = useTranslation("settings")
  if (status === "testing") {
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="size-3 animate-spin" />
        {t("apiKeys.card.testingBadge")}
      </Badge>
    )
  }

  if (status === "ok") {
    return (
      <Badge variant="success">
        <CheckCircle2 className="size-3" />
        {latencyMs != null ? t("apiKeys.card.connectedWithLatency", { latencyMs }) : t("apiKeys.card.connectedBadge")}
      </Badge>
    )
  }

  if (status === "not_configured") {
    return <Badge variant="secondary">{t("apiKeys.card.notConfigured")}</Badge>
  }

  if (status === "error") {
    const detail = translateErrorCode(errorCode)
    return (
      <Badge variant="destructive" className="gap-1" title={detail || undefined}>
        <XCircle className="size-3" />
        {translateTestStatus(status)}
      </Badge>
    )
  }

  if (["invalid_key", "rate_limited", "quota_exceeded", "network_error", "timeout"].includes(status)) {
    const detail = translateErrorCode(errorCode)
    return (
      <Badge variant="destructive" className="gap-1" title={detail || undefined}>
        <XCircle className="size-3" />
        {translateTestStatus(status)}
      </Badge>
    )
  }

  return <Badge variant="secondary">{t("apiKeys.card.notConfigured")}</Badge>
}

function directPersistedTestResult(
  persisted: CredentialsState["providers"][number] | null,
  draft: ProviderDraft,
  options: { backendRouteTagsAreAuthoritative?: boolean } = {},
): ProviderTestResult | null {
  if (!persisted) return null
  if (!options.backendRouteTagsAreAuthoritative && !providerTestParamsMatch(draft, persisted)) {
    return null
  }
  const status = persisted.last_test_status ?? (
    (persisted.available_models?.length || persisted.available_sdks?.length) ? "ok" : undefined
  )
  if (!status) return null
  const canShowDiscoveredModels = status === "ok" || status === "untested" || Boolean(persisted.available_models?.length || persisted.available_sdks?.length)
  return {
    params_fingerprint: "",
    base_url: persisted.base_url ?? "",
    runtime_base_url: persisted.runtime_base_url,
    provider_type: persisted.provider_type ?? null,
    last_test_status: status,
    last_test_at: persisted.last_test_at ?? "",
    last_test_message: persisted.last_test_message ?? "",
    last_error_code: persisted.last_error_code ?? "",
    available_models: canShowDiscoveredModels ? persisted.available_models ?? [] : [],
    available_sdks: canShowDiscoveredModels ? persisted.available_sdks ?? [] : [],
  }
}

export function ProviderDeleteButton({
  draftName,
  onDelete,
}: {
  draftName: string
  onDelete: () => void
}) {
  // Tests invoke ProviderDeleteButton() directly as a plain function (not inside
  // a React render tree), so it must use the global i18n.t singleton rather than
  // the useTranslation() hook — the hook needs a live React dispatcher.
  const displayName = draftName.trim() || i18n.t("apiKeys.card.thisProvider")

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label={i18n.t("apiKeys.card.aria.deleteProvider")}
      data-delete-toast-trigger={true}
      className="text-muted-foreground/70 hover:text-muted-foreground"
      onClick={() => {
        requestDeleteConfirmationToast({
          id: `delete-provider-${displayName}`,
          title: i18n.t("apiKeys.card.deleteConfirm.title", { displayName }),
          description: i18n.t("apiKeys.card.deleteConfirm.description"),
          onConfirm: onDelete,
        })
      }}
    >
      <Trash2 className="size-4" />
    </Button>
  )
}

function FieldCopyButton({ value, label, className }: { value: string; label: string; className?: string }) {
  const { t } = useTranslation("settings")
  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      className={cn("text-muted-foreground/70 transition-none hover:text-muted-foreground", className)}
      onClick={() => void copyCredentialValue(value, label)}
      disabled={!value}
      aria-label={t("apiKeys.card.copyLabelButton", { label })}
    >
      <Copy className="size-4" />
    </Button>
  )
}

function FieldReachabilityCheck({ label }: { label: string }) {
  const { t } = useTranslation("settings")
  const text = t("apiKeys.card.fieldReachable", { label })
  return (
    <span
      className="inline-flex size-4 shrink-0 items-center justify-center text-success"
      title={text}
      aria-label={text}
    >
      <CheckCircle2 className="size-3.5" />
    </span>
  )
}

function BaseUrlReachabilityIcon({ state, url }: { state: BaseUrlReachabilityState; url: string }) {
  const { t } = useTranslation("settings")
  if (state === "unknown") return null
  if (state === "testing") {
    const text = t("apiKeys.card.baseUrlTesting", { url: url || t("apiKeys.card.baseUrlFallback") })
    return (
      <span
        className="inline-flex size-4 shrink-0 items-center justify-center text-muted-foreground"
        title={text}
        aria-label={text}
        data-base-url-status="testing"
      >
        <Loader2 className="size-3.5 animate-spin" />
      </span>
    )
  }
  if (state === "connected") {
    const text = t("apiKeys.card.baseUrlConnected", { url })
    return (
      <span
        className="inline-flex size-4 shrink-0 items-center justify-center text-success"
        title={text}
        aria-label={text}
        data-base-url-status="connected"
      >
        <CheckCircle2 className="size-3.5" />
      </span>
    )
  }
  const failedText = t("apiKeys.card.baseUrlFailed", { url })
  return (
    <span
      className="inline-flex size-4 shrink-0 items-center justify-center text-destructive"
      title={failedText}
      aria-label={failedText}
      data-base-url-status="failed"
    >
      <XCircle className="size-3.5" />
    </span>
  )
}

type EndpointSummary = {
  id: string
  label: string
  baseUrl: string
  runtimeBaseUrl?: string
  protocol: ProviderType | null
  status: TestMessageStatus
  lastTestAt?: string | null
  message?: string | null
  errorCode?: string | null
  routeCount: number
  sdkCount: number
  profileCount: number
  methodIds: string[]
  requestMapperIds: string[]
  profileCapabilities: string[]
  toolProtocol: "supported" | "not_listed"
}

function AvailableEndpointSummary({ endpoints }: { endpoints: EndpointSummary[] }) {
  const { t } = useTranslation("settings")
  if (endpoints.length === 0) return null
  return (
    <div className="border-t pt-3 space-y-2 text-xs" data-testid="available-endpoints">
      <div className="text-muted-foreground">{t("apiKeys.card.availableEndpointsLabel")}</div>
      <div className="flex flex-wrap gap-1">
        <TooltipProvider>
          {endpoints.map((endpoint) => {
            const endpointLabel = `${endpointProtocolShortLabel(endpoint.protocol)} / ${endpointHostLabel(endpoint.baseUrl || endpoint.id)}`
            const ariaLabel = endpointTooltipText(endpoint)
            return (
              <Tooltip key={endpoint.id}>
                <TooltipTrigger asChild>
                  <span
                    tabIndex={0}
                    className={cn(
                      "inline-flex h-6 max-w-full cursor-help items-center gap-1.5 rounded-md border border-l-2 px-2 text-[0.625rem] font-medium leading-none",
                      "bg-card font-mono shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      endpointStatusSurfaceClass(endpoint.status),
                      endpoint.status === "testing" && "api-route-tag-border-flow",
                    )}
                    aria-label={ariaLabel}
                    data-endpoint-status={endpoint.status}
                  >
                    {endpoint.status === "testing" ? <Loader2 className="size-2.5 animate-spin" aria-hidden="true" /> : null}
                    <span className="min-w-0 truncate">{endpointLabel}</span>
                    {endpoint.methodIds.length > 0 ? (
                      <span className="shrink-0 font-sans text-muted-foreground">
                        {endpoint.methodIds.length}m
                      </span>
                    ) : null}
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-sm break-words">
                  <EndpointTooltipContent endpoint={endpoint} />
                </TooltipContent>
              </Tooltip>
            )
          })}
        </TooltipProvider>
      </div>
    </div>
  )
}

function EndpointTooltipContent({ endpoint }: { endpoint: EndpointSummary }) {
  const lines = endpointTooltipLines(endpoint)
  return (
    <span className="flex flex-col gap-0.5 text-left">
      {lines.map((line) => (
        <span key={line}>{line}</span>
      ))}
    </span>
  )
}

function endpointTooltipText(endpoint: EndpointSummary): string {
  return endpointTooltipLines(endpoint).join(". ")
}

function endpointTooltipLines(endpoint: EndpointSummary): string[] {
  const inputBaseUrl = endpoint.baseUrl || i18n.t("apiKeys.card.tooltip.notSet")
  const runtimeBaseUrl = endpoint.runtimeBaseUrl || endpoint.baseUrl || ""
  const toolProtocolStatus = endpoint.toolProtocol === "supported"
    ? i18n.t("apiKeys.card.tooltip.toolProtocolSupported")
    : i18n.t("apiKeys.card.tooltip.toolProtocolNotListed")
  const lines = [
    i18n.t("apiKeys.card.tooltip.provider", { label: endpoint.label }),
    i18n.t("apiKeys.card.tooltip.endpoint", { id: endpoint.id }),
    i18n.t("apiKeys.card.tooltip.inputUrl", { url: inputBaseUrl }),
    ...(runtimeBaseUrl && runtimeBaseUrl !== endpoint.baseUrl ? [i18n.t("apiKeys.card.tooltip.runtimeUrl", { url: runtimeBaseUrl })] : []),
    i18n.t("apiKeys.card.tooltip.protocol", { protocol: endpointProtocolLabel(endpoint.protocol) }),
    i18n.t("apiKeys.card.tooltip.status", { status: endpointStatusLabel(endpoint.status) }),
    i18n.t("apiKeys.card.tooltip.routes", { n: endpoint.routeCount }),
    i18n.t("apiKeys.card.tooltip.profiles", { n: endpoint.profileCount }),
    endpoint.methodIds.length > 0
      ? i18n.t("apiKeys.card.tooltip.methods", { methods: endpoint.methodIds.join(", ") })
      : i18n.t("apiKeys.card.tooltip.methodsNotVerified"),
    endpoint.requestMapperIds.length > 0
      ? i18n.t("apiKeys.card.tooltip.requestMappers", { mappers: endpoint.requestMapperIds.join(", ") })
      : i18n.t("apiKeys.card.tooltip.requestMappersNotVerified"),
    endpoint.profileCapabilities.length > 0
      ? i18n.t("apiKeys.card.tooltip.profileCapabilities", { capabilities: endpoint.profileCapabilities.map(profileCapabilityLabel).join(", ") })
      : i18n.t("apiKeys.card.tooltip.profileCapabilitiesNotVerified"),
    i18n.t("apiKeys.card.tooltip.toolProtocol", { status: toolProtocolStatus }),
  ]
  if (endpoint.sdkCount > 0) lines.push(i18n.t("apiKeys.card.tooltip.sdks", { n: endpoint.sdkCount }))
  if (endpoint.lastTestAt) lines.push(i18n.t("apiKeys.card.tooltip.lastTest", { timestamp: endpoint.lastTestAt }))
  if (endpoint.message) lines.push(i18n.t("apiKeys.card.tooltip.message", { message: endpoint.message }))
  if (endpoint.errorCode) lines.push(i18n.t("apiKeys.card.tooltip.errorCode", { code: endpoint.errorCode }))
  return lines
}

function endpointProtocolLabel(providerType: ProviderType | null): string {
  if (providerType === "anthropic_compatible") return i18n.t("apiKeys.card.protocol.anthropic")
  if (providerType === "ark_runtime") return i18n.t("apiKeys.card.protocol.ark")
  if (providerType === "google_genai") return i18n.t("apiKeys.card.protocol.google")
  if (providerType === "openai_compatible") return i18n.t("apiKeys.card.protocol.openai")
  return i18n.t("apiKeys.card.protocol.unknown")
}

function endpointProtocolShortLabel(providerType: ProviderType | null): string {
  if (providerType === "anthropic_compatible") return i18n.t("apiKeys.card.protocolShort.anthropic")
  if (providerType === "google_genai") return i18n.t("apiKeys.card.protocolShort.gemini")
  if (providerType === "openai_compatible") return i18n.t("apiKeys.card.protocolShort.openai")
  if (providerType === "ark_runtime") return i18n.t("apiKeys.card.protocolShort.ark")
  return i18n.t("apiKeys.card.protocolShort.unknown")
}

function endpointHostLabel(value: string): string {
  const compactHost = (host: string) => {
    if (!host || host === "localhost" || /^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$/.test(host)) return host
    const [hostname, port] = host.split(":")
    const labels = hostname.split(".").filter(Boolean)
    const compact = labels.length >= 2 ? labels.slice(0, -1).join(".") : hostname
    return port ? `${compact}:${port}` : compact
  }

  try {
    const parsed = new URL(value)
    return compactHost(parsed.host) || value
  } catch {
    return compactHost(value.replace(/^https?:\/\//, "").replace(/\/.*$/, "")) || value
  }
}

function endpointProfileSummary(models: ModelInfo[]): Pick<
  EndpointSummary,
  "profileCount" | "methodIds" | "requestMapperIds" | "profileCapabilities" | "toolProtocol"
> {
  const methods: string[] = []
  const requestMappers: string[] = []
  const capabilities: string[] = []
  let profileCount = 0
  let toolProtocolSupported = false

  for (const model of models) {
    methods.push(...modelCapabilityStringArray(model, "verified_methods"))
    if (modelCapabilityBoolean(model, "tool_protocol")) {
      toolProtocolSupported = true
    }

    for (const profile of modelVerifiedProfiles(model)) {
      if (profile.status === "failed") continue
      profileCount += 1
      if (profile.method_id) methods.push(profile.method_id)
      if (profile.request_mapper_id) requestMappers.push(profile.request_mapper_id)
      if (profile.capability) {
        capabilities.push(profile.capability)
        if (profile.capability === "tool_calling") {
          toolProtocolSupported = true
        }
      }
    }
  }

  return {
    profileCount,
    methodIds: uniqueSortedStrings(methods),
    requestMapperIds: uniqueSortedStrings(requestMappers),
    profileCapabilities: uniqueSortedStrings(capabilities),
    toolProtocol: toolProtocolSupported ? "supported" : "not_listed",
  }
}

function endpointStatusLabel(status: TestMessageStatus): string {
  if (status === "not_configured") return i18n.t("apiKeys.card.endpointStatus.notConfigured")
  if (status === "testing") return i18n.t("apiKeys.card.endpointStatus.testing")
  if (status === "ok") return i18n.t("apiKeys.card.endpointStatus.connected")
  if (status === "untested") return i18n.t("apiKeys.card.endpointStatus.untested")
  return translateTestStatus(status)
}

function endpointStatusSurfaceClass(status: TestMessageStatus): string {
  if (status === "ok") return "border-success bg-success/10 text-foreground"
  if (status === "testing") return "border-primary/70 bg-primary/10 text-foreground"
  if (status === "not_configured" || status === "untested") return "border-border/70 bg-muted/10 text-muted-foreground"
  return "border-tag-destructive-border bg-tag-destructive-border/10 text-foreground"
}

function endpointStateDisplayStatus({
  hasApiKey,
  hasBaseUrl,
  isTesting,
  result,
  models,
}: {
  hasApiKey: boolean
  hasBaseUrl: boolean
  isTesting: boolean
  result: ProviderTestResult | null | undefined
  models: ModelInfo[]
}): TestMessageStatus {
  if (!hasApiKey || !hasBaseUrl) return "not_configured"
  if (isTesting) return "testing"
  if (endpointHasUsableRoute(models)) return "ok"
  const status = result?.last_test_status
  if (!status || status === "untested") return "untested"
  if (endpointFailureIsOnlyModelScoped(result, models)) return "untested"
  return status
}

function endpointHasUsableRoute(models: ModelInfo[]): boolean {
  return models.some((model) => (
    model.status === "verified" ||
    model.status === "probe-verified" ||
    model.ui_state === "ready" ||
    model.ui_state === "historical_ready" ||
    modelVerifiedProfiles(model).some((profile) => profile.status === "ready")
  ))
}

function endpointFailureIsOnlyModelScoped(
  result: ProviderTestResult | null | undefined,
  models: ModelInfo[],
): boolean {
  const summaries = models.flatMap(routeSummariesForModel)
  const failureSummaries = summaries.filter((summary) => (
    summary.status === "failed" || summary.ui_state === "failed" || summary.failure_scope
  ))
  if (failureSummaries.some((summary) => summary.failure_scope === "endpoint")) return false
  if (failureSummaries.length > 0 && failureSummaries.every((summary) => summary.failure_scope === "model")) return true
  const errorCode = result?.last_error_code?.trim().toLowerCase()
  const message = result?.last_test_message?.toLowerCase() ?? ""
  return (
    errorCode === "invalid_model" ||
    errorCode === "model_not_found" ||
    message.includes("invalid_model") ||
    message.includes("model_not_found") ||
    message.includes("no available channels for model")
  )
}

function resultLooksReachable(result: ProviderTestResult | null | undefined): boolean {
  if (!result) return false
  if (result.last_error_code) return false
  if (result.last_test_status !== "untested" && result.last_test_status !== "ok") return false
  return Boolean(
    result.last_test_at ||
    result.last_test_message ||
    (result.available_models?.length ?? 0) > 0 ||
    (result.available_sdks?.length ?? 0) > 0
  )
}

function providerDisplayName(
  draft: ProviderDraft,
  isOfficial: boolean,
  notableProviderKey?: string,
): string {
  const raw = draft.name.trim() || draft.id.trim()
  if (!isOfficial) return raw || i18n.t("apiKeys.card.unnamedProvider")
  const providerKey = officialProviderKey(draft, notableProviderKey)
  if (providerKey) return officialProviderNamesByKey[providerKey]
  const normalizedName = humanizeOfficialProviderName(raw)
  return normalizedName ? `${normalizedName} Official` : i18n.t("apiKeys.card.officialProvider")
}

function officialProviderKey(draft: ProviderDraft, notableProviderKey?: string): string | null {
  if (notableProviderKey && officialProviderNamesByKey[notableProviderKey]) {
    return notableProviderKey
  }
  const haystack = `${draft.id} ${draft.name} ${draft.base_url}`.toLowerCase()
  return Object.keys(officialProviderNamesByKey).find((key) => haystack.includes(key)) ?? null
}

function humanizeOfficialProviderName(value: string): string {
  const normalized = value
    .replace(/[-_]+/g, " ")
    .replace(/\bofficial\b/gi, "")
    .trim()
  if (!normalized) return ""
  const knownBrand = officialProviderBrandNames[normalized.toLowerCase()]
  if (knownBrand) return knownBrand
  return normalized
    .split(/\s+/)
    .map((part) => officialProviderBrandNames[part.toLowerCase()] ?? `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ")
}

function modelRouteStatus(model: ModelInfo): ModelProbeStatus | "unknown" {
  return model.status ?? "unknown"
}

// apikeys#30: the API Keys card surfaces the backend's authoritative 6-state
// ui_state (projected per route in GET /llm/registry) as an inline connectivity
// badge. We pick the most-usable state across the endpoint's routes so the card
// reads green the moment any route is connectable, blue when only historical
// evidence exists, and so on. Priority is highest-confidence first.
const providerUiStatePriority: ProviderUiState[] = [
  "ready",
  "historical_ready",
  "untested",
  "cooling_down",
  "failed",
  "off",
]

const modelAggregateUiStatePriority: ProviderUiState[] = [
  "ready",
  "historical_ready",
  "cooling_down",
  "failed",
  "untested",
  "off",
]

export function representativeProviderUiState(models: ModelInfo[]): ProviderUiState | null {
  let best: ProviderUiState | null = null
  let bestRank = providerUiStatePriority.length
  for (const model of models) {
    const state = model.ui_state
    if (!state) continue
    const rank = providerUiStatePriority.indexOf(state)
    if (rank === -1) continue
    if (rank < bestRank) {
      bestRank = rank
      best = state
    }
  }
  return best
}

function routeDisplayStatus(model: ModelInfo, isTesting: boolean): RouteDisplayStatus {
  const status = modelRouteStatus(model)
  if (status === "testing" && isTesting) return "testing"
  if (status === "testing") return "unverified_manual"
  return status
}

function routeStatusTagVariant(status: RouteDisplayStatus): "success" | "destructive" | "muted" | "default" | "info" | "warning" | "probe-verified" {
  if (status === "testing") return "default"
  if (status === "failed") return "destructive"
  if (status === "disabled") return "muted"
  if (status === "verified") return "success"
  if (status === "probe-verified") return "probe-verified"
  if (status === "unverified_manual" || status === "unknown") return "default"
  return "default"
}

// apikeys#30 / UI-spec §143: official route tags take their colour from the
// backend 6-state ui_state. A historically probe-verified route is persisted
// with RouteStatus "unverified_manual" this session but projects ui_state
// "historical_ready" — it must read as the blue "Previously Connected" tag
// (same border-multimodal-border token ProviderStateBadge uses), not the
// neutral tag its session-level RouteStatus would otherwise produce.
function routeTagVariantFromUiState(
  uiState: ProviderUiState,
): "success" | "destructive" | "muted" | "default" | "warning" | "probe-verified" {
  switch (uiState) {
    case "ready":
      return "success"
    case "historical_ready":
      return "probe-verified"
    case "failed":
      return "destructive"
    case "cooling_down":
      return "warning"
    case "off":
      return "muted"
    case "untested":
      return "default"
  }
}

function routeStatusLabel(status: RouteDisplayStatus): string {
  if (status === "verified") return i18n.t("apiKeys.card.routeStatus.verified")
  if (status === "failed") return i18n.t("apiKeys.card.routeStatus.failed")
  if (status === "disabled") return i18n.t("apiKeys.card.routeStatus.disabled")
  if (status === "testing") return i18n.t("apiKeys.card.routeStatus.testing")
  if (status === "probe-verified") return i18n.t("apiKeys.card.routeStatus.probeVerified")
  if (status === "unverified_manual") return i18n.t("apiKeys.card.routeStatus.unverified")
  return i18n.t("apiKeys.card.routeStatus.unknown")
}

function routeFailureScopeFromSignals({
  status,
  uiState,
  reasonCode,
  attemptStatuses,
  message,
}: {
  status: RouteDisplayStatus
  uiState?: ProviderUiState
  reasonCode?: string | null
  attemptStatuses?: string[]
  message?: string | null
}): RouteFailureScope | undefined {
  if (status !== "failed" && uiState !== "failed") return undefined
  const reason = reasonCode?.trim().toLowerCase()
  const attempts = attemptStatuses?.map((item) => item.trim().toLowerCase()).filter(Boolean) ?? []
  if (reason === "invalid_model" || attempts.includes("invalid_model")) return "model"
  if (reason === "model_not_found" || attempts.includes("model_not_found")) return "model"
  if (reason === "ok" || attempts.includes("ok")) return undefined
  if (reason === "error") return "endpoint"
  const text = message?.toLowerCase() ?? ""
  if (
    text.includes("invalid api key") ||
    text.includes("authentication_error") ||
    text.includes("direct access to") ||
    text.includes("use /v1/messages") ||
    text.includes("chat/completions is not allowed") ||
    text.includes("upstream_error") ||
    text.includes("processing_error") ||
    text.includes("service temporarily unavailable") ||
    text.includes("timeout") ||
    text.includes("network")
  ) {
    return "endpoint"
  }
  if (text.includes("invalid_model") || text.includes("no available channels for model")) return "model"
  return "unknown"
}

function summaryAggregateStatus(summary: AggregatedRouteSummary): ModelProbeStatus | "unknown" {
  if (summary.ui_state === "ready" || summary.status === "verified") return "verified"
  if (summary.ui_state === "historical_ready" || summary.status === "probe-verified") return "probe-verified"
  if (summary.ui_state === "cooling_down" || summary.status === "testing") return "testing"
  if (summary.status === "failed") {
    return summary.failure_scope === "endpoint" ? "unverified_manual" : "failed"
  }
  if (summary.ui_state === "failed") return "unverified_manual"
  if (summary.ui_state === "off" || summary.status === "disabled") return "disabled"
  if (summary.ui_state === "untested" || summary.status === "unverified_manual") return "unverified_manual"
  return summary.status
}

function summaryAggregateUiState(summary: AggregatedRouteSummary): ProviderUiState | undefined {
  if (summary.ui_state === "ready" || summary.status === "verified") return "ready"
  if (summary.ui_state === "historical_ready" || summary.status === "probe-verified") return "historical_ready"
  if (summary.ui_state === "cooling_down" || summary.status === "testing") return "cooling_down"
  if (summary.status === "failed") {
    return summary.failure_scope === "endpoint" ? "untested" : "failed"
  }
  if (summary.ui_state === "failed") return "untested"
  if (summary.ui_state === "off" || summary.status === "disabled") return "off"
  if (summary.ui_state === "untested" || summary.status === "unverified_manual") return "untested"
  return summary.ui_state
}

function summaryAggregateRank(summary: AggregatedRouteSummary): number {
  const status = summaryAggregateStatus(summary)
  const uiState = summaryAggregateUiState(summary)
  if (uiState === "ready" || status === "verified") return 0
  if (uiState === "historical_ready" || status === "probe-verified") return 1
  if (uiState === "cooling_down" || status === "testing") return 2
  if (uiState === "failed" || status === "failed") return 3
  if (uiState === "untested" || status === "unverified_manual" || status === "unknown") return 4
  if (uiState === "off" || status === "disabled") return 5
  return 4
}

function modelAggregateRank(model: ModelInfo): number {
  return summaryAggregateRank(aggregateRouteSummary(model))
}

function aggregateSummaryUiState(summaries: AggregatedRouteSummary[]): ProviderUiState | undefined {
  let best: ProviderUiState | undefined
  let bestRank = modelAggregateUiStatePriority.length
  for (const summary of summaries) {
    const state = summaryAggregateUiState(summary)
    if (!state) continue
    const rank = modelAggregateUiStatePriority.indexOf(state)
    if (rank !== -1 && rank < bestRank) {
      bestRank = rank
      best = state
    }
  }
  return best
}

function aggregateSummaryStatus(summaries: AggregatedRouteSummary[]): ModelProbeStatus | undefined {
  if (summaries.some((summary) => summaryAggregateStatus(summary) === "verified")) return "verified"
  if (summaries.some((summary) => summaryAggregateStatus(summary) === "probe-verified")) return "probe-verified"
  if (summaries.some((summary) => summaryAggregateStatus(summary) === "testing")) return "testing"
  if (summaries.some((summary) => summaryAggregateStatus(summary) === "failed")) return "failed"
  if (summaries.length > 0 && summaries.every((summary) => summaryAggregateStatus(summary) === "disabled")) return "disabled"
  if (summaries.some((summary) => summaryAggregateStatus(summary) === "unverified_manual")) return "unverified_manual"
  return undefined
}

function aggregateRouteSummary(model: ModelInfo): AggregatedRouteSummary {
  const status = modelRouteStatus(model)
  const reasonCode = modelProbeReasonCode(model)
  const attemptStatuses = modelProbeAttemptStatuses(model)
  const message = modelProbeMessage(model)
  return {
    endpoint_id: model.endpoint_id,
    route_id: model.route_id,
    status,
    ui_state: model.ui_state,
    message,
    reason_code: reasonCode,
    failure_scope: routeFailureScopeFromSignals({
      status,
      uiState: model.ui_state,
      reasonCode,
      attemptStatuses,
      message,
    }),
  }
}

function normalizeAggregateRouteSummary(summary: AggregatedRouteSummary): AggregatedRouteSummary {
  const status = summary.status ?? "unknown"
  return {
    ...summary,
    status,
    failure_scope: summary.failure_scope ?? routeFailureScopeFromSignals({
      status,
      uiState: summary.ui_state,
      reasonCode: summary.reason_code,
      message: summary.message,
    }),
  }
}

function aggregateRouteSummaries(model: ModelInfo): AggregatedRouteSummary[] {
  const value = model.capabilities?.__aggregate_routes
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is AggregatedRouteSummary => (
      Boolean(item) &&
      typeof item === "object" &&
      !Array.isArray(item) &&
      "status" in item
    ))
    .map(normalizeAggregateRouteSummary)
}

function routeSummariesForModel(model: ModelInfo): AggregatedRouteSummary[] {
  const summaries = aggregateRouteSummaries(model)
  return summaries.length > 0 ? summaries : [aggregateRouteSummary(model)]
}

function aggregateRoutesTooltipText(model: ModelInfo): string | null {
  const summaries = aggregateRouteSummaries(model)
  if (summaries.length <= 1) return null
  const lines = summaries.slice(0, 6).map((summary) => {
    const target = summary.endpoint_id ?? summary.route_id ?? i18n.t("apiKeys.card.routeWord")
    const state = aggregateRouteSummaryLabel(summary)
    const line = `${state}: ${target}${summary.message ? ` - ${summary.message}` : ""}`
    const diagnostic = aggregateRouteSummaryDiagnostic(summary)
    return diagnostic ? markTooltipDiagnostic(diagnostic, line) : line
  })
  const remaining = summaries.length - lines.length
  return `${i18n.t("apiKeys.card.tooltip.routesHeader")}\n${lines.join("\n")}${remaining > 0 ? `\n${i18n.t("apiKeys.card.tooltip.plusMore", { n: remaining })}` : ""}`
}

// Classify the aggregate-route summary by its source enum/scope, NOT by the
// translated display label, so RouteTooltipContent can paint the warning/failed
// icon correctly in any language.
function aggregateRouteSummaryDiagnostic(summary: AggregatedRouteSummary): TooltipDiagnostic | null {
  if (summary.ui_state === "historical_ready") return null
  if (summary.status === "failed") {
    if (summary.failure_scope === "endpoint") return "warning"
    return "failed"
  }
  if (summary.ui_state === "failed") return "warning"
  return null
}

function aggregateRouteSummaryLabel(summary: AggregatedRouteSummary): string {
  if (summary.ui_state === "historical_ready") return i18n.t("apiKeys.card.routeStatus.previouslyConnected")
  if (summary.status === "failed") {
    if (summary.failure_scope === "endpoint") return i18n.t("apiKeys.card.routeStatus.endpointFailed")
    if (summary.failure_scope === "model") return i18n.t("apiKeys.card.routeStatus.modelFailed")
    return i18n.t("apiKeys.card.routeStatus.failed")
  }
  if (summary.ui_state === "failed") return i18n.t("apiKeys.card.routeStatus.endpointFailed")
  return routeStatusLabel(summary.status)
}

function modelCapabilityValue(model: ModelInfo, key: string): unknown {
  const value = model.capabilities?.[key]
  if (value && typeof value === "object" && !Array.isArray(value) && "value" in value) {
    return (value as { value?: unknown }).value
  }
  return value
}

function modelCapabilityStringArray(model: ModelInfo, key: string): string[] {
  const value = modelCapabilityValue(model, key)
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : []
}

function modelCapabilityBoolean(model: ModelInfo, key: string): boolean {
  return modelCapabilityValue(model, key) === true
}

function modelCapabilityNumber(model: ModelInfo, key: string): number | null {
  const value = modelCapabilityValue(model, key)
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function officialModelType(model: ModelInfo): string | null {
  const value = modelCapabilityValue(model, "model_type")
  return typeof value === "string" && value ? value : null
}

function officialModelTypeLabel(model: ModelInfo): string | null {
  const label = modelCapabilityValue(model, "model_type_label")
  if (typeof label === "string" && label) return label
  const modelType = officialModelType(model)
  if (modelType === "language_reasoning") return i18n.t("apiKeys.card.modelTypeLabel.languageReasoning")
  if (modelType === "image_generation") return i18n.t("apiKeys.card.modelTypeLabel.imageGeneration")
  if (modelType === "video_generation") return i18n.t("apiKeys.card.modelTypeLabel.videoGeneration")
  if (modelType === "audio") return i18n.t("apiKeys.card.modelTypeLabel.audio")
  if (modelType === "embedding") return i18n.t("apiKeys.card.modelTypeLabel.embedding")
  if (modelType === "translation") return i18n.t("apiKeys.card.modelTypeLabel.translation")
  if (modelType === "3d_generation") return i18n.t("apiKeys.card.modelTypeLabel.threeD")
  return null
}

function groupOfficialRouteInfos(models: ModelInfo[]): Array<{ label: string; models: ModelInfo[] }> {
  const groups = new Map<string, ModelInfo[]>()
  for (const model of models) {
    const label = officialRouteGroupLabel(model)
    groups.set(label, [...(groups.get(label) ?? []), model])
  }
  return [...groups.entries()]
    .sort(([left], [right]) => officialRouteGroupRank(left) - officialRouteGroupRank(right) || left.localeCompare(right))
    .map(([label, groupModels]) => ({ label, models: groupModels }))
}

// Stable, non-translated group key — used for grouping, ranking
// (officialRouteGroupRank), the data-route-type-group attribute and React keys.
// The user-visible text is produced by officialRouteGroupDisplayLabel().
function officialRouteGroupLabel(model: ModelInfo): string {
  const modelType = officialModelType(model)
  if (modelType === "language_reasoning") return "Language"
  if (modelType === "image_generation") return "Multimodal"
  if (modelType === "embedding") return "Embedding"
  if (modelType === "audio") return "Audio"
  if (modelType === "video_generation") return "Video"
  if (modelType === "translation") return "Translation"
  if (modelType === "3d_generation") return "3D"
  if (modelType === "moderation") return "Moderation"
  if (modelType === "interactions_agent") return "Interactions Agent"
  return "Other"
}

function officialRouteGroupDisplayLabel(groupKey: string): string {
  switch (groupKey) {
    case "Language":
      return i18n.t("apiKeys.card.routeGroup.language")
    case "Multimodal":
      return i18n.t("apiKeys.card.routeGroup.multimodal")
    case "Embedding":
      return i18n.t("apiKeys.card.routeGroup.embedding")
    case "Audio":
      return i18n.t("apiKeys.card.routeGroup.audio")
    case "Video":
      return i18n.t("apiKeys.card.routeGroup.video")
    case "Translation":
      return i18n.t("apiKeys.card.routeGroup.translation")
    case "3D":
      return i18n.t("apiKeys.card.routeGroup.threeD")
    case "Moderation":
      return i18n.t("apiKeys.card.routeGroup.moderation")
    case "Interactions Agent":
      return i18n.t("apiKeys.card.routeGroup.interactionsAgent")
    default:
      return i18n.t("apiKeys.card.routeGroup.other")
  }
}

function officialRouteGroupRank(label: string): number {
  return [
    "Language",
    "Multimodal",
    "Embedding",
    "Audio",
    "Video",
    "Translation",
    "3D",
    "Moderation",
    "Interactions Agent",
    "Other",
  ].indexOf(label)
}

function routeProfileTooltipText(model: ModelInfo, status: RouteDisplayStatus): string | null {
  if (status !== "verified") return null
  const profiles = modelVerifiedProfiles(model).filter((profile) => profile.status !== "failed")
  if (profiles.length === 0) return null
  const capabilityLabels = uniqueStrings(
    profiles
      .map((profile) => profileCapabilityLabel(profile.capability))
      .filter((label): label is string => Boolean(label)),
  )
  const capabilityText = capabilityLabels.length > 0
    ? capabilityLabels.join(" + ")
    : i18n.t("apiKeys.card.routeTooltip.languageFallback")
  const methodLabels = uniqueStrings(
    profiles
      .map((profile) => profile.method_id)
      .filter((method): method is string => Boolean(method)),
  )
  return [
    i18n.t("apiKeys.card.routeTooltip.verifiedRoute", { capability: capabilityText }),
    methodLabels.length > 0 ? i18n.t("apiKeys.card.routeTooltip.methods", { methods: methodLabels.join(", ") }) : null,
  ].filter((line): line is string => Boolean(line)).join("\n")
}

function routeCapabilityTooltipText(model: ModelInfo): string | null {
  const inputModalities = modelInputModalities(model)
  const outputModalities = modelOutputModalities(model)
  const maxInputTokens = modelCapabilityNumber(model, "max_input_tokens")
  const maxOutputTokens = modelCapabilityNumber(model, "max_output_tokens")
  const lines = [
    inputModalities.length > 0 ? i18n.t("apiKeys.card.routeTooltip.input", { modalities: inputModalities.map(modalityLabel).join(", ") }) : null,
    outputModalities.length > 0 ? i18n.t("apiKeys.card.routeTooltip.output", { modalities: outputModalities.map(modalityLabel).join(", ") }) : null,
    maxInputTokens !== null
      ? i18n.t("apiKeys.card.routeTooltip.maxInput", { value: formatTokenLimit(maxInputTokens) })
      : i18n.t("apiKeys.card.routeTooltip.maxInputNotListed"),
    maxOutputTokens !== null
      ? i18n.t("apiKeys.card.routeTooltip.maxOutput", { value: formatTokenLimit(maxOutputTokens) })
      : i18n.t("apiKeys.card.routeTooltip.maxOutputNotListed"),
  ].filter((line): line is string => Boolean(line))
  return lines.length > 0 ? lines.join("\n") : null
}

function formatTokenLimit(value: number): string {
  if (value >= 1000) return `${Math.round(value / 1000)}k`
  return new Intl.NumberFormat("en-US").format(value)
}

function routeFailureTooltipText(model: ModelInfo, status: RouteDisplayStatus): string | null {
  if (status !== "failed") return null
  const message = modelProbeMessage(model)
  const attempts = modelProbeAttemptTooltipText(model)
  const failureLine = message
    ? i18n.t("apiKeys.card.routeTooltip.routeTestFailed", { message })
    : i18n.t("apiKeys.card.routeTooltip.routeTestFailedBare")
  return [
    markTooltipDiagnostic("failed", failureLine),
    attempts,
  ].filter((line): line is string => Boolean(line)).join("\n")
}

function RouteTooltipContent({ text }: { text: string }) {
  return (
    <div className="space-y-1 whitespace-normal">
      {text.split("\n").map((line, index) => {
        const status = routeTooltipLineStatus(line)
        // The diagnostic sentinel is an internal marker only — strip it before
        // the line is shown so the user never sees it.
        const displayLine = stripTooltipDiagnostic(line)
        if (status) {
          const Icon = status === "warning" ? TriangleAlert : XCircle
          return (
            <div
              key={`${status}-${index}-${displayLine}`}
              data-tooltip-diagnostic={status}
              className={cn(
                "flex items-start gap-1.5",
                status === "warning" ? "text-warning" : "text-destructive",
              )}
            >
              <Icon
                aria-hidden="true"
                data-tooltip-diagnostic-icon={status}
                className="mt-0.5 size-3 shrink-0"
              />
              <span className="min-w-0 break-words">{displayLine}</span>
            </div>
          )
        }
        return <div key={`${index}-${displayLine}`} className="break-words">{displayLine}</div>
      })}
    </div>
  )
}

// Classify a tooltip line as a warning/failure diagnostic. Primary path: the
// language-independent sentinel the line-builders prepend (see
// tooltipDiagnosticSentinel). Fallback path: the legacy English markers, kept so
// (a) the exported pure function still classifies raw English strings (tests +
// any caller) and (b) English-literal lines coming from out-of-scope siblings
// (e.g. role-route-status' "Warning:"/"Failed:") still light up.
export function routeTooltipLineStatus(line: string): "warning" | "failed" | null {
  if (line.includes(tooltipDiagnosticSentinel.warning)) return "warning"
  if (line.includes(tooltipDiagnosticSentinel.failed)) return "failed"
  if (line.includes("Warning:")) return "warning"
  if (line.includes("Endpoint failed")) return "warning"
  if (line.includes("Failed:") || line.includes("Route test failed") || line.includes("Model failed")) return "failed"
  return null
}

function modelProbeReasonCode(model: ModelInfo): string | null {
  const value = modelCapabilityValue(model, "reason_code")
  return typeof value === "string" && value.trim() ? value.trim() : null
}

function modelProbeAttemptStatuses(model: ModelInfo): string[] {
  const attempts = modelCapabilityValue(model, "probe_attempts")
  if (!Array.isArray(attempts)) return []
  return attempts
    .filter((attempt): attempt is Record<string, unknown> => Boolean(attempt) && typeof attempt === "object" && !Array.isArray(attempt))
    .map((attempt) => (typeof attempt.status === "string" ? attempt.status.trim() : ""))
    .filter(Boolean)
}

function modelProbeMessage(model: ModelInfo): string | null {
  if (typeof model.last_probe_message === "string" && model.last_probe_message.trim()) {
    return model.last_probe_message.trim()
  }
  const value = modelCapabilityValue(model, "last_probe_message")
  return typeof value === "string" && value.trim() ? value.trim() : null
}

function modelProbeAttemptTooltipText(model: ModelInfo): string | null {
  const attempts = modelCapabilityValue(model, "probe_attempts")
  if (!Array.isArray(attempts) || attempts.length === 0) return null
  const lines = attempts
    .filter((attempt): attempt is Record<string, unknown> => Boolean(attempt) && typeof attempt === "object" && !Array.isArray(attempt))
    .slice(0, 4)
    .map((attempt) => {
      const method = typeof attempt.method_id === "string" ? attempt.method_id : "unknown_method"
      const profile = typeof attempt.profile_id === "string" ? attempt.profile_id : ""
      const status = typeof attempt.status === "string" ? attempt.status : "failed"
      const message = typeof attempt.message === "string" && attempt.message.trim()
        ? attempt.message.trim()
        : status
      return `${method}${profile ? `/${profile}` : ""}: ${message}`
    })
  if (lines.length === 0) return null
  const remaining = attempts.length - lines.length
  return `${i18n.t("apiKeys.card.tooltip.attemptsHeader")}\n${lines.join("\n")}${remaining > 0 ? `\n${i18n.t("apiKeys.card.tooltip.plusMore", { n: remaining })}` : ""}`
}

function thirdPartyModelTooltipText(model: ModelInfo, status: RouteDisplayStatus): string {
  const lines = [
    model.id,
    i18n.t("apiKeys.card.tooltip.status", { status: thirdPartyModelStatusLabel(model, status) }),
  ]
  if (model.endpoint_id) lines.push(i18n.t("apiKeys.card.tooltip.endpoint", { id: model.endpoint_id }))
  if (model.route_id) lines.push(i18n.t("apiKeys.card.routeTooltip.route", { id: model.route_id }))
  const message = modelProbeMessage(model)
  if (message) lines.push(i18n.t("apiKeys.card.tooltip.message", { message }))
  const aggregatedRoutes = aggregateRoutesTooltipText(model)
  if (aggregatedRoutes) lines.push(aggregatedRoutes)
  const attempts = modelProbeAttemptTooltipText(model)
  if (attempts) lines.push(attempts)
  return lines.join("\n")
}

function thirdPartyModelStatusLabel(model: ModelInfo, status: RouteDisplayStatus): string {
  if (model.ui_state === "historical_ready" || status === "probe-verified") return i18n.t("apiKeys.card.routeStatus.previouslyConnected")
  const summaries = routeSummariesForModel(model)
  const hasEndpointFailure = summaries.some((summary) => summary.failure_scope === "endpoint")
  const hasModelFailure = summaries.some((summary) => summary.failure_scope === "model")
  if (status === "unverified_manual" && hasEndpointFailure && !hasModelFailure) {
    return i18n.t("apiKeys.card.routeStatus.modelNotVerified")
  }
  return routeStatusLabel(status)
}

function modelVerifiedProfiles(model: ModelInfo): Array<{
  profile_id?: string
  capability?: string
  method_id?: string
  request_mapper_id?: string
  status?: string
  input_modalities?: string[]
  output_modalities?: string[]
  runtime_overrides?: Record<string, unknown>
  metadata?: Record<string, unknown>
}> {
  if (Array.isArray(model.verified_profiles)) return model.verified_profiles
  const profiles = model.capabilities?.verified_profiles
  if (!Array.isArray(profiles)) return []
  return profiles.filter((profile): profile is {
    profile_id?: string
    capability?: string
    method_id?: string
    request_mapper_id?: string
    status?: string
    input_modalities?: string[]
    output_modalities?: string[]
    runtime_overrides?: Record<string, unknown>
    metadata?: Record<string, unknown>
  } => (
    Boolean(profile) && typeof profile === "object" && !Array.isArray(profile)
  ))
}

function profileCapabilityLabel(capability: string | undefined): string | null {
  if (capability === "text_chat") return i18n.t("apiKeys.card.capability.textChat")
  if (capability === "reasoning" || capability === "thinking") return i18n.t("apiKeys.card.capability.reasoning")
  if (capability === "image_input") return i18n.t("apiKeys.card.capability.imageInput")
  if (capability === "audio_input") return i18n.t("apiKeys.card.capability.audioInput")
  if (capability === "tool_calling") return i18n.t("apiKeys.card.capability.toolCalling")
  if (capability === "structured_output") return i18n.t("apiKeys.card.capability.structuredOutput")
  if (capability === "translation") return i18n.t("apiKeys.card.capability.translation")
  if (!capability) return null
  return capability.replaceAll("_", " ")
}

function modelHasVerifiedReasoningProfile(model: ModelInfo): boolean {
  return modelVerifiedProfiles(model).some((profile) => (
    profile.status !== "failed" &&
    (profile.capability === "reasoning" || profile.capability === "thinking")
  ))
}

function modelInputModalities(model: ModelInfo): string[] {
  const capabilities = modelCapabilityStringArray(model, "input_modalities")
  if (capabilities.length > 0) return uniqueStrings(capabilities)
  const verifiedProfileModalities = modelVerifiedProfiles(model).flatMap((profile) => profile.input_modalities ?? [])
  if (verifiedProfileModalities.length > 0) return uniqueStrings(verifiedProfileModalities)
  return fallbackModelInputModalities(model)
}

function modelOutputModalities(model: ModelInfo): string[] {
  const capabilities = modelCapabilityStringArray(model, "output_modalities")
  if (capabilities.length > 0) return uniqueStrings(capabilities)
  const verifiedProfileModalities = modelVerifiedProfiles(model).flatMap((profile) => profile.output_modalities ?? [])
  if (verifiedProfileModalities.length > 0) return uniqueStrings(verifiedProfileModalities)
  return fallbackModelOutputModalities(model)
}

function fallbackModelInputModalities(model: ModelInfo): string[] {
  const modelType = officialModelType(model)
  const modelId = model.id.toLowerCase()
  if (modelType === "image_generation") {
    return modelId.includes("image") || modelId.includes("edit") || modelId.includes("gpt-image")
      ? ["text", "image"]
      : ["text"]
  }
  if (modelType === "video_generation") {
    return modelId.includes("i2v") || modelId.includes("flf2v") || modelId.includes("image")
      ? ["text", "image"]
      : ["text"]
  }
  if (modelType === "audio") {
    if (modelId.includes("whisper") || modelId.includes("transcribe")) return ["audio"]
    if (modelId.includes("tts")) return ["text"]
    return ["text", "audio"]
  }
  if (modelType === "embedding" || modelType === "translation" || modelType === "language_reasoning") {
    return ["text"]
  }
  if (modelType === "3d_generation") return ["text", "image"]
  return []
}

function fallbackModelOutputModalities(model: ModelInfo): string[] {
  const modelType = officialModelType(model)
  const modelId = model.id.toLowerCase()
  if (modelType === "image_generation") return ["image"]
  if (modelType === "video_generation") return ["video"]
  if (modelType === "audio") {
    if (modelId.includes("whisper") || modelId.includes("transcribe")) return ["text"]
    if (modelId.includes("tts")) return ["audio"]
    return ["text", "audio"]
  }
  if (modelType === "embedding") return ["embedding"]
  if (modelType === "3d_generation") return ["3d"]
  if (modelType === "translation" || modelType === "language_reasoning") return ["text"]
  return []
}

function modalityLabel(modality: string): string {
  if (modality === "text") return i18n.t("apiKeys.card.modality.text")
  if (modality === "image") return i18n.t("apiKeys.card.modality.image")
  if (modality === "video") return i18n.t("apiKeys.card.modality.video")
  if (modality === "audio") return i18n.t("apiKeys.card.modality.audio")
  if (modality === "file") return i18n.t("apiKeys.card.modality.file")
  if (modality === "pdf") return i18n.t("apiKeys.card.modality.pdf")
  if (modality === "embedding") return i18n.t("apiKeys.card.modality.embedding")
  if (modality === "moderation") return i18n.t("apiKeys.card.modality.moderation")
  if (modality === "3d") return i18n.t("apiKeys.card.modality.threeD")
  return modality
}

function modalityIcon(modality: string, position: "input" | "output") {
  const className = cn("size-2.5 shrink-0", position === "input" ? "opacity-80" : "")
  if (modality === "text") return <FileText key={`${position}-${modality}`} className={className} aria-hidden="true" />
  if (modality === "image") return <ImageIcon key={`${position}-${modality}`} className={className} aria-hidden="true" />
  if (modality === "video") return <Video key={`${position}-${modality}`} className={className} aria-hidden="true" />
  if (modality === "audio") return <Volume2 key={`${position}-${modality}`} className={className} aria-hidden="true" />
  if (modality === "file" || modality === "pdf") return <File key={`${position}-${modality}`} className={className} aria-hidden="true" />
  if (modality === "embedding" || modality === "3d") return <Box key={`${position}-${modality}`} className={className} aria-hidden="true" />
  if (modality === "moderation") return <TriangleAlert key={`${position}-${modality}`} className={className} aria-hidden="true" />
  return null
}

function modalityIcons(modalities: string[], position: "input" | "output") {
  return uniqueStrings(modalities)
    .map((modality) => modalityIcon(modality, position))
    .filter((icon): icon is ReactElement => Boolean(icon))
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values)]
}

function uniqueSortedStrings(values: string[]): string[] {
  return uniqueStrings(values.filter((value) => value.trim().length > 0)).sort((left, right) => left.localeCompare(right))
}

function isCapabilityLibraryModel(model: ModelInfo): boolean {
  const modelType = officialModelType(model)
  return Boolean(modelType && !["language_reasoning", "catalog_candidate"].includes(modelType))
}

function scrollInputContentOnWheel(event: WheelEvent<HTMLInputElement>) {
  const input = event.currentTarget
  const maxScrollLeft = input.scrollWidth - input.clientWidth
  if (maxScrollLeft <= 0) return
  const delta = event.deltaX || event.deltaY
  if (!delta) return
  input.scrollLeft = Math.max(0, Math.min(maxScrollLeft, input.scrollLeft + delta))
  event.preventDefault()
}

function newBaseUrlDraftId(providerId: string): string {
  const uuid = globalThis.crypto?.randomUUID?.()
  return `${providerId}-url-${uuid ?? Date.now()}`
}

function baseUrlRowsForDraft(draft: ProviderDraft): NonNullable<ProviderDraft["base_urls"]> {
  return draft.base_urls?.length
    ? draft.base_urls
    : [{ id: draft.id, value: draft.base_url, provider_type: draft.provider_type, endpoint_ids: { [draft.provider_type]: draft.id } }]
}

export function aggregateThirdPartyModelInfos(models: ModelInfo[]): ModelInfo[] {
  const grouped = new Map<string, ModelInfo[]>()
  for (const model of models) {
    grouped.set(model.id, [...(grouped.get(model.id) ?? []), model])
  }
  return [...grouped.values()].map((group) => {
    const sorted = [...group].sort((left, right) => (
      modelAggregateRank(left) - modelAggregateRank(right) ||
      (left.endpoint_id ?? "").localeCompare(right.endpoint_id ?? "") ||
      (left.route_id ?? "").localeCompare(right.route_id ?? "")
    ))
    const representative = sorted[0]
    const summaries = sorted.flatMap(routeSummariesForModel)
    const verifiedProfileCount = Math.max(...group.map((model) => model.verified_profile_count ?? 0))
    const aggregateStatus = aggregateSummaryStatus(summaries)
    const aggregateUiState = aggregateSummaryUiState(summaries)
    return {
      ...representative,
      id: representative.id,
      status: aggregateStatus,
      ui_state: aggregateUiState,
      verified_profile_count: verifiedProfileCount || representative.verified_profile_count,
      capabilities: {
        ...(representative.capabilities ?? {}),
        __aggregate_routes: summaries,
      },
    }
  })
}

export function ProviderCard({
  draft,
  persisted,
  persistedEndpoints,
  onFieldChange,
  onGetModels,
  onDelete,
  providerKind,
  showManualModelPanel = false,
  notableProviderKey,
  onModelsUpdated,
}: {
  draft: ProviderDraft
  persisted: CredentialsState["providers"][number] | null
  persistedEndpoints?: Record<string, CredentialsState["providers"][number] | null | undefined>
  onFieldChange: (patch: Partial<ProviderDraft>) => void
  onGetModels: () => void
  onEndpointTest?: (modelId: string) => void
  onDelete: () => void
  providerKind?: "official" | "third-party"
  showManualModelPanel?: boolean
  notableProviderKey?: string
  onModelsUpdated?: (models: ModelInfo[]) => void
}) {
  const { t } = useTranslation("settings")
  const [visible, setVisible] = useState(false)
  const [showAllModels, setShowAllModels] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [apiKeyError, setApiKeyError] = useState("")
  const [baseUrlError, setBaseUrlError] = useState("")
  const apiKeyInputRef = useRef<HTMLInputElement>(null)
  const baseUrlInputRef = useRef<HTMLInputElement>(null)
  const isOfficial = providerKind === "official"
  const baseUrlRows = baseUrlRowsForDraft(draft)
  const filledBaseUrlRows = baseUrlRows.filter((row) => row.value.trim().length > 0)
  const endpointDrafts = isOfficial ? [draft] : providerEndpointDraftsForAction(draft)
  const hasApiKey = draft.api_key.trim().length > 0
  const hasRequiredConfig = hasApiKey && (providerKind !== "third-party" || filledBaseUrlRows.length > 0)
  const isGettingModels = draft.testingAction === "models"
  const endpointStates = endpointDrafts.map((endpointDraft) => {
    const row = { id: endpointDraft.id, value: endpointDraft.base_url, provider_type: endpointDraft.provider_type }
    const rowPersisted = persistedEndpoints?.[endpointDraft.id] ?? (endpointDraft.id === draft.id ? persisted : null)
    const matchedResult = providerCachedTestResult(rowPersisted ?? null, endpointDraft)
      ?? directPersistedTestResult(rowPersisted ?? null, endpointDraft, {
        backendRouteTagsAreAuthoritative: isOfficial,
      })
    const models = isOfficial
      ? sortOfficialRouteInfos(matchedResult?.available_models ?? [])
      : sortModelInfos(matchedResult?.available_models ?? [])
    return {
      row,
      draft: endpointDraft,
      persisted: rowPersisted ?? null,
      matchedResult,
      models,
      sdks: matchedResult?.available_sdks ?? [],
    }
  })
  const endpointStatesByBaseUrlRow = new Map<string, typeof endpointStates>()
  for (const state of endpointStates) {
    const rowId = state.draft.base_urls?.[0]?.id ?? state.row.id
    endpointStatesByBaseUrlRow.set(rowId, [...(endpointStatesByBaseUrlRow.get(rowId) ?? []), state])
  }
  const primaryEndpointState = endpointStates[0] ?? null
  const matchedResult = (
    isOfficial
      ? primaryEndpointState?.matchedResult
      : endpointStates.find((state) => state.matchedResult?.last_test_status === "ok")?.matchedResult
        ?? primaryEndpointState?.matchedResult
  ) ?? null

  const hasMatchedTestResult = matchedResult !== null
  const displayName = providerDisplayName(draft, isOfficial, notableProviderKey)
  const apiKeyProviderName = displayName.replace(/ Official$/, "")
  const availableSdks = uniqueStrings(endpointStates.flatMap((state) => state.sdks))
  const availableModels = isOfficial
    ? sortOfficialRouteInfos(primaryEndpointState?.models ?? [])
    : sortModelInfos(aggregateThirdPartyModelInfos(endpointStates.flatMap((state) => state.models)))
  const hasAvailableModels = availableModels.length > 0
  const availableModelsLabel = isOfficial ? t("apiKeys.card.availableRoutesLabel") : t("apiKeys.card.availableModelsLabel")
  const copyTargetLabel = isOfficial ? t("apiKeys.card.routeWord") : t("apiKeys.card.modelWord")
  const visibleModels = showAllModels ? availableModels : availableModels.slice(0, availableModelsPreviewLimit)
  const hiddenModelCount = Math.max(0, availableModels.length - visibleModels.length)
  const matchedStatus = matchedResult?.last_test_status
  const matchedErrorCode = matchedResult?.last_error_code
  const hasReachableModelList = Boolean(
    hasRequiredConfig &&
    matchedResult &&
    !matchedErrorCode &&
    (matchedStatus === "untested" || matchedStatus === "ok") &&
    (matchedResult.last_test_at || matchedResult.last_test_message || availableModels.length > 0 || availableSdks.length > 0),
  )
  const hasEmptyModelListWarning = hasReachableModelList && !hasAvailableModels
  const testStatus: TestMessageStatus = !hasRequiredConfig
    ? "not_configured"
    : draft.isTesting
    ? "testing"
    : !hasMatchedTestResult
      ? "not_configured"
    : matchedStatus === "ok"
      ? "ok"
    : matchedStatus && matchedStatus !== "untested"
      ? matchedStatus
      : "not_configured"
  const endpointSummaries: EndpointSummary[] = endpointStates
    .filter((state) => state.row.value.trim() || isOfficial || state.persisted)
    .map((state) => {
      const stateProfiles = endpointProfileSummary(state.models)
      const stateStatus = endpointStateDisplayStatus({
        hasApiKey,
        hasBaseUrl: isOfficial || Boolean(state.row.value.trim()),
        isTesting: isGettingModels,
        result: state.matchedResult,
        models: state.models,
      })
      return {
        id: state.persisted?.id ?? state.row.id,
        label: displayName,
        baseUrl: state.matchedResult?.base_url || state.persisted?.base_url || state.row.value,
        runtimeBaseUrl: state.matchedResult?.runtime_base_url || state.persisted?.runtime_base_url,
        protocol: state.matchedResult?.provider_type ?? state.persisted?.provider_type ?? state.draft.provider_type,
        status: stateStatus,
        lastTestAt: state.matchedResult?.last_test_at ?? state.persisted?.last_test_at ?? null,
        message: state.matchedResult?.last_test_message ?? state.persisted?.last_test_message ?? null,
        errorCode: state.matchedResult?.last_error_code ?? state.persisted?.last_error_code ?? null,
        routeCount: state.models.length,
        sdkCount: state.sdks.length,
        ...stateProfiles,
      }
    })
  const showAvailableEndpoint = endpointSummaries.length > 0

  const baseUrlReachabilityState = (rowId: string): BaseUrlReachabilityState => {
    const states = endpointStatesByBaseUrlRow.get(rowId) ?? []
    if (states.length === 0) return "unknown"
    if (isGettingModels && states.some((state) => state.row.value.trim())) return "testing"
    const reachability = states.map((state): BaseUrlReachabilityState => {
      const result = state.matchedResult
      const status = endpointStateDisplayStatus({
        hasApiKey,
        hasBaseUrl: isOfficial || Boolean(state.row.value.trim()),
        isTesting: false,
        result,
        models: state.models,
      })
      if (status === "ok") return "connected"
      if (status === "untested" && resultLooksReachable(result)) return "connected"
      if (status && status !== "untested" && status !== "not_configured") return "failed"
      return "unknown"
    })
    if (reachability.includes("connected")) return "connected"
    if (reachability.includes("failed")) return "failed"
    return "unknown"
  }

  const updateBaseUrlRows = (nextRows: NonNullable<ProviderDraft["base_urls"]>) => {
    const rows = nextRows.length > 0 ? nextRows : [{ id: draft.id, value: "", provider_type: draft.provider_type }]
    onFieldChange({
      base_url: rows[0]?.value ?? "",
      provider_type: rows[0]?.provider_type ?? draft.provider_type,
      base_urls: rows,
    })
  }

  const updateBaseUrlRow = (rowId: string, value: string) => {
    updateBaseUrlRows(baseUrlRows.map((row) => (
      row.id === rowId ? { ...row, value, provider_type: inferProviderType(draft.id, value, draft.name) } : row
    )))
  }

  const addBaseUrlRow = () => {
    updateBaseUrlRows([...baseUrlRows, { id: newBaseUrlDraftId(draft.id), value: "", provider_type: draft.provider_type }])
  }

  const deleteBaseUrlRow = (rowId: string) => {
    updateBaseUrlRows(baseUrlRows.filter((row) => row.id !== rowId))
  }

  const handleGetModels = () => {
    const nextApiKeyError = hasApiKey ? "" : t("apiKeys.card.apiKeyRequired")
    const nextBaseUrlError = providerKind === "third-party" && filledBaseUrlRows.length === 0 ? t("apiKeys.card.baseUrlRequired") : ""
    setApiKeyError(nextApiKeyError)
    setBaseUrlError(nextBaseUrlError)
    if (nextApiKeyError) {
      apiKeyInputRef.current?.focus()
      return
    }
    if (nextBaseUrlError) {
      baseUrlInputRef.current?.focus()
      return
    }
    onGetModels()
  }
  const officialRouteGroups = isOfficial ? groupOfficialRouteInfos(visibleModels) : []
  const modelListClassName = cn(
    isOfficial ? "space-y-2" : "flex gap-1 flex-wrap",
    !showAllModels && (isOfficial ? "max-h-[7rem] overflow-hidden" : "max-h-[2.75rem] overflow-hidden"),
  )
  const renderAvailableModelTag = (model: ModelInfo): ReactElement => {
    const status = isOfficial ? routeDisplayStatus(model, isGettingModels) : modelRouteStatus(model)
    // Route colour comes from the backend 6-state ui_state when present
    // (UI-spec §143: historical_ready -> blue "Previously Connected"); fall back
    // to the session RouteStatus only when ui_state is absent.
    const uiState = model.ui_state
    const tagVariant = uiState ? routeTagVariantFromUiState(uiState) : routeStatusTagVariant(status)
    const statusLabel = isOfficial
      ? uiState === "historical_ready" ? t("apiKeys.card.routeStatus.previouslyConnected") : routeStatusLabel(status)
      : thirdPartyModelStatusLabel(model, status)
    const modelType = isOfficial ? officialModelType(model) : null
    const modelTypeLabel = isOfficial ? officialModelTypeLabel(model) : null
    const isCapabilityModel = isOfficial && isCapabilityLibraryModel(model)
    const profileTooltipText = isOfficial && !isCapabilityModel ? routeProfileTooltipText(model, status) : null
    const failureTooltipText = isOfficial ? routeFailureTooltipText(model, status) : null
    const capabilityTooltipText = isOfficial ? routeCapabilityTooltipText(model) : null
    const primaryTooltipDetail = (
      failureTooltipText
      ?? (isCapabilityModel && status !== "failed"
        ? modelTypeLabel
        : profileTooltipText)
    ) ?? statusLabel
    const tooltipDetail = [
      primaryTooltipDetail,
      capabilityTooltipText,
    ].filter((line): line is string => Boolean(line)).join("\n")
    const appendModelTypeLabel = Boolean(
      modelTypeLabel &&
      primaryTooltipDetail !== modelTypeLabel &&
      status !== "verified",
    )
    const tooltipText = isOfficial
      ? `${model.id} - ${tooltipDetail}${appendModelTypeLabel ? ` - ${modelTypeLabel}` : ""}`
      : thirdPartyModelTooltipText(model, status)
    const hasReasoningProfile = isOfficial && modelHasVerifiedReasoningProfile(model)
    const inputModalities = isOfficial ? modelInputModalities(model) : []
    const outputModalities = isOfficial ? modelOutputModalities(model) : []
    const inputCapabilityIcons = modalityIcons(inputModalities, "input")
    const outputCapabilityIcons = modalityIcons(outputModalities, "output")
    const ariaLabel = isOfficial
      ? t("apiKeys.card.copyTagAria", { target: copyTargetLabel, modelId: model.id, detail: tooltipDetail.replace(/\s+/g, " ") })
      : t("apiKeys.card.copyTagAria", { target: copyTargetLabel, modelId: model.id, detail: statusLabel })
    const tagKey = isOfficial ? `${model.route_id ?? model.id}:${model.status ?? "model"}` : model.id
    const isDisabled = status === "disabled"
    const aggregateRouteCount = aggregateRouteSummaries(model).length
    const tag = (
      <Tag
        key={tagKey}
        asChild
        variant={tagVariant}
        size="xs"
        className={cn(
          isDisabled ? "cursor-not-allowed opacity-40 font-mono" : "cursor-pointer font-mono hover:bg-muted/40",
          status === "testing" && "api-route-tag-border-flow",
        )}
      >
        <button
          type="button"
          disabled={isDisabled}
          onClick={isDisabled ? undefined : () => void copyAvailableModelId(model.id)}
          aria-label={ariaLabel}
          data-route-status={status}
          data-route-ui-state={uiState}
          data-route-count={aggregateRouteCount > 1 ? aggregateRouteCount : undefined}
          data-model-type={modelType ?? undefined}
          data-reasoning-route={hasReasoningProfile ? true : undefined}
          data-input-modalities={inputModalities.length > 0 ? inputModalities.join(",") : undefined}
          data-output-modalities={outputModalities.length > 0 ? outputModalities.join(",") : undefined}
          className={isDisabled ? "cursor-not-allowed pointer-events-none" : undefined}
        >
          {inputCapabilityIcons}
          {model.id}
          {hasReasoningProfile ? <Brain className="size-2.5 shrink-0" aria-hidden="true" /> : null}
          {outputCapabilityIcons}
        </button>
      </Tag>
    )
    return (
      <Tooltip key={`${tagKey}:tooltip`}>
        <TooltipTrigger asChild>{tag}</TooltipTrigger>
        <TooltipContent className="max-w-sm break-words">
          <RouteTooltipContent text={tooltipText} />
        </TooltipContent>
      </Tooltip>
    )
  }

  return (
    <Card data-provider-id={draft.id}>
      <CardHeader className="flex flex-row items-center gap-3 pb-2">
        <div className="min-w-0 max-w-xs truncate text-sm font-semibold text-foreground">{displayName}</div>
        {providerKind && !isOfficial ? (
          <Badge variant="outline" className="text-[10px] text-muted-foreground">
            {t("apiKeys.card.thirdPartyBadge")}
          </Badge>
        ) : null}
        {!isOfficial ? <TestMessage status={testStatus} latencyMs={null} errorCode={matchedErrorCode ?? null} /> : null}
        {/* UI-spec §140: official provider card titles carry NO connection-status
            badge — reachability shows on the API-key row icon + per-route tags.
            The 6-state badge (incl. blue historical_ready) belongs on the route
            tags, not rolled up to the title. Third-party keeps its inline badge. */}
        <div className="flex-1" />
        {!isOfficial ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0 text-muted-foreground"
                aria-label={t("apiKeys.card.moreActionsButton", { draftName: draft.name })}
              >
                <MoreVertical className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-36">
              <DropdownMenuItem onSelect={() => setRenameOpen(true)}>
                <Pencil className="size-3.5 mr-2" />
                {t("apiKeys.card.renameButton")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onSelect={() => {
                  requestDeleteConfirmationToast({
                    id: `delete-provider-${draft.name}`,
                    title: t("apiKeys.card.deleteConfirm.title", { displayName: draft.name }),
                    description: t("apiKeys.card.deleteConfirm.description"),
                    onConfirm: onDelete,
                  })
                }}
              >
                <Trash2 className="size-3.5 mr-2" />
                {t("apiKeys.card.deleteButton")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label htmlFor={`api-key-${draft.id}`}>{t("apiKeys.card.apiKeyLabel")}</Label>
            {hasReachableModelList ? <FieldReachabilityCheck label={t("apiKeys.card.apiKeyShort")} /> : null}
          </div>
          <div className={fieldRowClassName}>
            <div className="flex flex-1 min-w-0 items-center gap-1.5">
              <Input
                ref={apiKeyInputRef}
                id={`api-key-${draft.id}`}
                type={apiKeyInputType()}
                value={apiKeyDisplayValue(draft.api_key, visible)}
                readOnly={!visible && hasApiKey}
                onChange={(event) => {
                  if (!visible && hasApiKey) return
                  if (apiKeyError) setApiKeyError("")
                  onFieldChange({ api_key: event.target.value })
                }}
                placeholder={t("apiKeys.card.apiKeyPlaceholder", { providerName: apiKeyProviderName })}
                name={`provider-secret-${draft.id}`}
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                data-1p-ignore=""
                data-lpignore="true"
                data-form-type="other"
                spellCheck={false}
                aria-invalid={apiKeyError ? true : undefined}
                aria-describedby={apiKeyError ? `api-key-error-${draft.id}` : undefined}
                onWheel={scrollInputContentOnWheel}
                className={apiKeyInputClassName(visible, hasApiKey, { cssMask: false })}
              />
              <div className="flex shrink-0 items-center gap-0.5">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="size-7 text-muted-foreground/70 transition-none hover:text-muted-foreground [&_svg]:size-3.5"
                  onClick={() => setVisible((value) => !value)}
                  aria-label={visible ? t("apiKeys.card.hideApiKeyButton") : t("apiKeys.card.showApiKeyButton")}
                >
                  {visible ? <EyeOff /> : <Eye />}
                </Button>
                <FieldCopyButton value={draft.api_key} label={t("apiKeys.card.apiKeyShort")} className="size-7 [&_svg]:size-3.5" />
              </div>
            </div>
            <div className={fieldActionClassName}>
              <Button
                type="button"
                variant="default"
                onClick={handleGetModels}
                disabled={isGettingModels}
                className={providerTestButtonClassName}
              >
                {isGettingModels ? (
                  <Loader2 data-icon="inline-start" className="size-3.5 animate-spin shrink-0" />
                ) : (
                  <FlaskConical data-icon="inline-start" className="size-3.5 shrink-0" />
                )}
                {/* apikeys#24/#25: official and third-party share one real connectivity Test entry. */}
                {t("apiKeys.card.testButton")}
              </Button>
            </div>
          </div>
          {apiKeyError ? <p id={`api-key-error-${draft.id}`} className="text-xs text-destructive">{apiKeyError}</p> : null}
        </div>
        {/* apikeys#20: the manual Protocol dropdown is removed — the backend test
            entry (#25) auto-detects the transport protocol, so the third-party
            card's editable fields collapse to name / base_url / api_key. */}
        {!isOfficial ? (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <Label htmlFor={`base-url-${draft.id}`}>{t("apiKeys.card.baseUrlLabel")}</Label>
            </div>
            <div className="space-y-2">
              {baseUrlRows.map((row, index) => {
                const rowStatus = baseUrlReachabilityState(row.id)
                return (
                  <div key={row.id} className={fieldRowClassName}>
                    <div className="flex flex-1 min-w-0 items-center gap-1.5">
                      <Input
                        ref={index === 0 ? baseUrlInputRef : undefined}
                        id={index === 0 ? `base-url-${draft.id}` : `base-url-${draft.id}-${index}`}
                        value={row.value}
                        onChange={(event) => {
                          if (baseUrlError) setBaseUrlError("")
                          updateBaseUrlRow(row.id, event.target.value)
                        }}
                        placeholder={index === 0 ? t("apiKeys.card.baseUrlPlaceholder1") : t("apiKeys.card.baseUrlPlaceholder2")}
                        autoComplete="off"
                        autoCorrect="off"
                        autoCapitalize="none"
                        spellCheck={false}
                        aria-invalid={baseUrlError ? true : undefined}
                        aria-describedby={baseUrlError ? `base-url-error-${draft.id}` : undefined}
                        onWheel={scrollInputContentOnWheel}
                        className={scrollableInputClassName}
                      />
                      <BaseUrlReachabilityIcon state={rowStatus} url={row.value} />
                      <div className="flex shrink-0 items-center">
                        <FieldCopyButton value={row.value} label={t("apiKeys.card.baseUrlLabel")} className="size-7 [&_svg]:size-3.5" />
                        {baseUrlRows.length > 1 ? (
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            className="size-7 text-muted-foreground/70 transition-none hover:text-destructive [&_svg]:size-3.5"
                            onClick={() => deleteBaseUrlRow(row.id)}
                            aria-label={t("apiKeys.card.removeBaseUrlButton")}
                          >
                            <Trash2 />
                          </Button>
                        ) : null}
                      </div>
                    </div>
                    <div aria-hidden="true" />
                  </div>
                )
              })}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1"
                onClick={addBaseUrlRow}
              >
                <Plus className="size-3.5" />
                {t("apiKeys.card.addUrlButton")}
              </Button>
            </div>
            {baseUrlError ? <p id={`base-url-error-${draft.id}`} className="text-xs text-destructive">{baseUrlError}</p> : null}
          </div>
        ) : null}
        {showAvailableEndpoint ? <AvailableEndpointSummary endpoints={endpointSummaries} /> : null}
        {availableModels.length || hasEmptyModelListWarning ? (
          <div className="border-t pt-3 space-y-2 text-xs" data-testid="provider-capabilities">
            {hasAvailableModels ? (
              <div className="space-y-2 pb-1">
                <div className="text-muted-foreground">{availableModelsLabel}</div>
                <div
                  data-testid="available-models-list"
                  className={modelListClassName}
                >
                  <TooltipProvider>
                    {isOfficial ? (
                      officialRouteGroups.map((group) => (
                        <div key={group.label} className="space-y-1" data-route-type-group={group.label}>
                          <div className="text-[10px] font-medium uppercase text-muted-foreground">
                            {officialRouteGroupDisplayLabel(group.label)}
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {group.models.map(renderAvailableModelTag)}
                          </div>
                        </div>
                      ))
                    ) : (
                      visibleModels.map(renderAvailableModelTag)
                    )}
                  </TooltipProvider>
                </div>
                {availableModels.length > availableModelsPreviewLimit ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    className="h-5 px-1 text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => setShowAllModels((value) => !value)}
                  >
                    {showAllModels ? t("apiKeys.card.showFewerButton") : t("apiKeys.card.showMoreButton", { n: hiddenModelCount })}
                  </Button>
                ) : null}
              </div>
            ) : null}
            {hasEmptyModelListWarning ? (
              <div className="space-y-2 pb-1">
                <div className="text-muted-foreground">{availableModelsLabel}</div>
                <Badge variant="warning" className="gap-1">
                  <TriangleAlert className="size-3" />
                  {t("apiKeys.card.noModelsWarning")}
                </Badge>
              </div>
            ) : null}
          </div>
        ) : null}
        {showManualModelPanel ? (
          <ManualModelTestPanel
            providerKey={draft.id}
            notableProviderKey={notableProviderKey ?? draft.id.split(/[-_]/, 1)[0].toLowerCase()}
            onModelsUpdated={(models) => onModelsUpdated?.(models)}
            defaultExpanded={false}
          />
        ) : null}
      </CardContent>
      {!isOfficial ? (
        <RoleNameDialog
          title={t("apiKeys.card.renameDialog.title")}
          initialName={draft.name}
          existingNames={[]}
          open={renameOpen}
          onOpenChange={setRenameOpen}
          onSubmit={(nextName: string) => onFieldChange({ name: nextName })}
          fieldLabel={t("apiKeys.card.renameDialog.fieldLabel")}
        />
      ) : null}
    </Card>
  )
}
