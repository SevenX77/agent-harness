import { useRef, useState, type WheelEvent } from "react"
import { toast } from "sonner"
import { Brain, CheckCircle2, Copy, Eye, EyeOff, Loader2, Trash2, TriangleAlert, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { requestDeleteConfirmationToast } from "@/components/ui/delete-confirm-toast"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tag } from "@/components/ui/tag"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { translateErrorCode, translateTestStatus } from "@/lib/llm-error-messages"
import { cn } from "@/lib/utils"
import type { CredentialsState, ModelInfo, ModelProbeStatus, ProviderTestResult, ProviderType, RouteStatus } from "../../../api/llm"
import { providerCachedTestResult, providerTestParamsMatch } from "../settings/provider-utils"
import type { ProviderDraft } from "../settings/types"
import { ManualModelTestPanel } from "./ManualModelTestPanel"

type TestMessageStatus = "not_configured" | "testing" | NonNullable<CredentialsState["providers"][number]["last_test_status"]>
type RouteDisplayStatus = RouteStatus | "unknown" | "testing"
const availableModelsPreviewLimit = 12
const fieldRowClassName = "grid grid-cols-[minmax(0,1fr)_11.5rem] items-center gap-2"
const fieldActionClassName = "flex min-w-0 items-center justify-end gap-2"
const scrollableInputClassName = "overflow-x-auto whitespace-nowrap text-clip"
const providerProtocolOptions: Array<{ value: ProviderType; label: string }> = [
  { value: "openai_compatible", label: "OpenAI compatible" },
  { value: "anthropic_compatible", label: "Anthropic compatible" },
  { value: "google_genai", label: "Google GenAI" },
  { value: "ark_runtime", label: "Ark Runtime" },
]
const endpointModelExamplesByProvider: Record<string, string> = {
  anthropic: "claude-opus-4-7",
  openai: "gpt-5",
  gemini: "gemini-3.1-pro-preview",
  deepseek: "deepseek-v4-pro",
  ark: "doubao-seed-2-0-pro-260215",
  openrouter: "openai/gpt-5",
  qiniu: "deepseek-r1",
}
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

export function apiKeyInputType(visible: boolean): "text" | "password" {
  return visible ? "text" : "password"
}

export function apiKeyInputClassName(visible: boolean): string {
  return cn(scrollableInputClassName, visible ? "text-foreground" : "text-muted-foreground")
}

export function providerProtocolLabel(value: ProviderType): string {
  return providerProtocolOptions.find((option) => option.value === value)?.label ?? "OpenAI compatible"
}

export async function copyCredentialValue(value: string, label: string): Promise<void> {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    toast.success(`${label} copied`)
  } catch {
    toast.error(`Failed to copy ${label.toLowerCase()}`)
  }
}

export function copyAvailableModelId(modelId: string): Promise<void> {
  return copyCredentialValue(modelId, "Model name")
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
  const variant = routeStatusTagVariant(status, model)
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
  if (status === "testing") {
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="size-3 animate-spin" />
        Testing...
      </Badge>
    )
  }

  if (status === "ok") {
    return (
      <Badge variant="success">
        <CheckCircle2 className="size-3" />
        {latencyMs != null ? `Connected (${latencyMs}ms)` : "Connected"}
      </Badge>
    )
  }

  if (status === "not_configured") {
    return <Badge variant="secondary">Not configured</Badge>
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

  return <Badge variant="secondary">Not configured</Badge>
}

function directPersistedTestResult(
  persisted: CredentialsState["providers"][number] | null,
  draft: ProviderDraft,
): ProviderTestResult | null {
  if (!persisted || !providerTestParamsMatch(draft, persisted)) return null
  const status = persisted.last_test_status ?? (
    (persisted.available_models?.length || persisted.available_sdks?.length) ? "ok" : undefined
  )
  if (!status) return null
  const canShowDiscoveredModels = status === "ok" || status === "untested" || Boolean(persisted.available_models?.length || persisted.available_sdks?.length)
  return {
    params_fingerprint: "",
    base_url: persisted.base_url ?? "",
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
  const displayName = draftName.trim() || "this provider"

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label="Delete provider"
      data-delete-toast-trigger={true}
      className="text-muted-foreground/70 hover:text-muted-foreground"
      onClick={() => {
        requestDeleteConfirmationToast({
          id: `delete-provider-${displayName}`,
          title: `Delete ${displayName}?`,
          description: "This provider configuration will be removed from the credentials document.",
          onConfirm: onDelete,
        })
      }}
    >
      <Trash2 className="size-4" />
    </Button>
  )
}

function FieldCopyButton({ value, label }: { value: string; label: string }) {
  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      className="text-muted-foreground/70 transition-none hover:text-muted-foreground"
      onClick={() => void copyCredentialValue(value, label)}
      disabled={!value}
      aria-label={`Copy ${label}`}
    >
      <Copy className="size-4" />
    </Button>
  )
}

function FieldReachabilityCheck({ label }: { label: string }) {
  return (
    <span
      className="inline-flex size-4 shrink-0 items-center justify-center text-success"
      title={`${label} accepted by the model-list endpoint`}
      aria-label={`${label} accepted by the model-list endpoint`}
    >
      <CheckCircle2 className="size-3.5" />
    </span>
  )
}

function endpointModelPlaceholder(providerKey: string, providerType: ProviderType): string {
  const normalized = providerKey.toLowerCase()
  const matched = Object.entries(endpointModelExamplesByProvider).find(([key]) => normalized.includes(key))
  const fallback = providerType === "ark_runtime"
    ? endpointModelExamplesByProvider.ark
    : providerType === "anthropic_compatible"
      ? endpointModelExamplesByProvider.anthropic
      : providerType === "google_genai"
        ? endpointModelExamplesByProvider.gemini
        : endpointModelExamplesByProvider.openai
  return `e.g. ${matched?.[1] ?? fallback}`
}

function providerDisplayName(
  draft: ProviderDraft,
  isOfficial: boolean,
  notableProviderKey?: string,
): string {
  const raw = draft.name.trim() || draft.id.trim()
  if (!isOfficial) return raw || "Unnamed Provider"
  const providerKey = officialProviderKey(draft, notableProviderKey)
  if (providerKey) return officialProviderNamesByKey[providerKey]
  const normalizedName = humanizeOfficialProviderName(raw)
  return normalizedName ? `${normalizedName} Official` : "Official Provider"
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

function routeDisplayStatus(model: ModelInfo, isTesting: boolean): RouteDisplayStatus {
  const status = modelRouteStatus(model)
  if (status === "testing" && isTesting) return "testing"
  if (status === "testing") return "unverified_manual"
  return status
}

function routeStatusTagVariant(status: RouteDisplayStatus, model: ModelInfo): "success" | "destructive" | "muted" | "default" | "info" | "warning" | "multimodal" {
  if (status === "failed") return "destructive"
  if (status === "disabled") return "muted"
  if (isCapabilityLibraryModel(model)) return "multimodal"
  if (status === "verified") return "success"
  return "default"
}

function routeStatusLabel(status: RouteDisplayStatus): string {
  if (status === "verified") return "Verified route"
  if (status === "failed") return "Route test failed"
  if (status === "disabled") return "Disabled route"
  if (status === "testing") return "Testing route"
  if (status === "unverified_manual") return "Untested route"
  return "Route status unknown"
}

function modelCapabilityValue(model: ModelInfo, key: string): unknown {
  const value = model.capabilities?.[key]
  if (value && typeof value === "object" && !Array.isArray(value) && "value" in value) {
    return (value as { value?: unknown }).value
  }
  return value
}

function officialModelType(model: ModelInfo): string | null {
  const value = modelCapabilityValue(model, "model_type")
  return typeof value === "string" && value ? value : null
}

function officialModelTypeLabel(model: ModelInfo): string | null {
  const label = modelCapabilityValue(model, "model_type_label")
  if (typeof label === "string" && label) return label
  const modelType = officialModelType(model)
  if (modelType === "language_reasoning") return "Language/reasoning model"
  if (modelType === "image_generation") return "Image generation model"
  if (modelType === "video_generation") return "Video generation model"
  if (modelType === "audio") return "Audio/realtime model"
  if (modelType === "embedding") return "Embedding model"
  if (modelType === "translation") return "Translation model"
  if (modelType === "3d_generation") return "3D generation model"
  return null
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
    : "language"
  const methodLabels = uniqueStrings(
    profiles
      .map((profile) => profile.method_id)
      .filter((method): method is string => Boolean(method)),
  )
  return [
    `Verified ${capabilityText} route`,
    methodLabels.length > 0 ? `Methods: ${methodLabels.join(", ")}` : null,
  ].filter((line): line is string => Boolean(line)).join("\n")
}

function routeFailureTooltipText(model: ModelInfo, status: RouteDisplayStatus): string | null {
  if (status !== "failed") return null
  const message = modelProbeMessage(model)
  return message ? `Route test failed: ${message}` : null
}

function modelProbeMessage(model: ModelInfo): string | null {
  if (typeof model.last_probe_message === "string" && model.last_probe_message.trim()) {
    return model.last_probe_message.trim()
  }
  const value = modelCapabilityValue(model, "last_probe_message")
  return typeof value === "string" && value.trim() ? value.trim() : null
}

function modelVerifiedProfiles(model: ModelInfo): Array<{
  capability?: string
  method_id?: string
  status?: string
}> {
  if (Array.isArray(model.verified_profiles)) return model.verified_profiles
  const profiles = model.capabilities?.verified_profiles
  if (!Array.isArray(profiles)) return []
  return profiles.filter((profile): profile is { capability?: string; method_id?: string; status?: string } => (
    Boolean(profile) && typeof profile === "object" && !Array.isArray(profile)
  ))
}

function profileCapabilityLabel(capability: string | undefined): string | null {
  if (capability === "text_chat") return "text chat"
  if (capability === "reasoning" || capability === "thinking") return "reasoning"
  if (capability === "image_input") return "image input"
  if (capability === "audio_input") return "audio input"
  if (capability === "tool_calling") return "tool calling"
  if (capability === "structured_output") return "structured output"
  if (capability === "translation") return "translation"
  if (!capability) return null
  return capability.replaceAll("_", " ")
}

function modelHasVerifiedReasoningProfile(model: ModelInfo): boolean {
  return modelVerifiedProfiles(model).some((profile) => (
    profile.status !== "failed" &&
    (profile.capability === "reasoning" || profile.capability === "thinking")
  ))
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values)]
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

export function ProviderCard({
  draft,
  persisted,
  onFieldChange,
  onGetModels,
  onEndpointTest,
  onDelete,
  providerKind,
  showManualModelPanel = false,
  notableProviderKey,
  onModelsUpdated,
}: {
  draft: ProviderDraft
  persisted: CredentialsState["providers"][number] | null
  onFieldChange: (patch: Partial<ProviderDraft>) => void
  onGetModels: () => void
  onEndpointTest: (modelId: string) => void
  onDelete: () => void
  providerKind?: "official" | "third-party"
  showManualModelPanel?: boolean
  notableProviderKey?: string
  onModelsUpdated?: (models: ModelInfo[]) => void
}) {
  const [visible, setVisible] = useState(false)
  const [showAllModels, setShowAllModels] = useState(false)
  const [endpointModelId, setEndpointModelId] = useState("")
  const [apiKeyError, setApiKeyError] = useState("")
  const [baseUrlError, setBaseUrlError] = useState("")
  const apiKeyInputRef = useRef<HTMLInputElement>(null)
  const baseUrlInputRef = useRef<HTMLInputElement>(null)
  const isOfficial = providerKind === "official"
  const hasApiKey = draft.api_key.trim().length > 0
  const hasRequiredConfig = hasApiKey && (providerKind !== "third-party" || draft.base_url.trim().length > 0)
  const isGettingModels = draft.testingAction === "models"
  const isTestingEndpoint = draft.testingAction === "endpoint"
  const trimmedEndpointModelId = endpointModelId.trim()
  const matchedResult = providerCachedTestResult(persisted, draft) ?? directPersistedTestResult(persisted, draft)
  const hasMatchedTestResult = matchedResult !== null
  const displayName = providerDisplayName(draft, isOfficial, notableProviderKey)
  const apiKeyProviderName = displayName.replace(/ Official$/, "")
  const availableSdks = matchedResult?.available_sdks ?? []
  const availableModels = isOfficial
    ? sortOfficialRouteInfos(matchedResult?.available_models ?? [])
    : sortModelInfos(matchedResult?.available_models ?? [])
  const hasAvailableModels = availableModels.length > 0
  const availableModelsLabel = isOfficial ? "Available Routes:" : "Available Models:"
  const copyTargetLabel = isOfficial ? "route" : "model"
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
  const handleGetModels = () => {
    const nextApiKeyError = hasApiKey ? "" : "API key is required."
    const nextBaseUrlError = providerKind === "third-party" && !draft.base_url.trim() ? "Base URL is required." : ""
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

  return (
    <Card data-provider-id={draft.id}>
      <CardHeader className="flex flex-row items-center gap-3 pb-2">
        <div className="min-w-0 max-w-xs truncate text-sm font-semibold text-foreground">{displayName}</div>
        {providerKind && !isOfficial ? (
          <Badge variant="outline" className="text-[10px] text-muted-foreground">
            Third-party
          </Badge>
        ) : null}
        {!isOfficial ? <TestMessage status={testStatus} latencyMs={null} errorCode={matchedErrorCode ?? null} /> : null}
        <div className="flex-1" />
        {!isOfficial ? <ProviderDeleteButton draftName={draft.name} onDelete={onDelete} /> : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {!isOfficial ? (
          <div className="space-y-2">
            <Label htmlFor={`provider-name-${draft.id}`}>Provider Name</Label>
            <div className={fieldRowClassName}>
              <Input
                id={`provider-name-${draft.id}`}
                value={draft.name}
                onChange={(event) => onFieldChange({ name: event.target.value })}
                placeholder="Provider Name"
                aria-label="Provider Name"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                onWheel={scrollInputContentOnWheel}
                className={scrollableInputClassName}
              />
              <div aria-hidden="true" />
            </div>
          </div>
        ) : null}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <Label htmlFor={`api-key-${draft.id}`}>API Key</Label>
            {hasReachableModelList ? <FieldReachabilityCheck label="API key" /> : null}
          </div>
          <div className={fieldRowClassName}>
            <Input
              ref={apiKeyInputRef}
              id={`api-key-${draft.id}`}
              type={apiKeyInputType(visible)}
              value={draft.api_key}
              onChange={(event) => {
                if (apiKeyError) setApiKeyError("")
                onFieldChange({ api_key: event.target.value })
              }}
              placeholder={`Enter your ${apiKeyProviderName} API Key`}
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
              className={apiKeyInputClassName(visible)}
            />
            <div className={fieldActionClassName}>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="text-muted-foreground/70 transition-none hover:text-muted-foreground"
                onClick={() => setVisible((value) => !value)}
                aria-label={visible ? "Hide API key" : "Show API key"}
              >
                {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </Button>
              <FieldCopyButton value={draft.api_key} label="API key" />
              <Button
                type="button"
                variant={isOfficial ? "default" : "secondary"}
                onClick={handleGetModels}
                disabled={isGettingModels}
                className="px-4"
              >
                {isGettingModels ? <Loader2 className="size-3.5 animate-spin" /> : null}
                {isOfficial ? "Test" : "Get Models"}
              </Button>
            </div>
          </div>
          {apiKeyError ? <p id={`api-key-error-${draft.id}`} className="text-xs text-destructive">{apiKeyError}</p> : null}
        </div>
        {!isOfficial ? (
          <div className="space-y-2">
            <Label htmlFor={`provider-protocol-${draft.id}`}>Protocol</Label>
            <div className={fieldRowClassName}>
              <Select
                value={draft.provider_type}
                onValueChange={(value) => onFieldChange({ provider_type: value as ProviderType })}
              >
                <SelectTrigger id={`provider-protocol-${draft.id}`} className="w-full justify-between">
                  <SelectValue>{providerProtocolLabel(draft.provider_type)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {providerProtocolOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div aria-hidden="true" />
            </div>
          </div>
        ) : null}
        {!isOfficial ? (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <Label htmlFor={`base-url-${draft.id}`}>Base URL</Label>
              {hasReachableModelList ? <FieldReachabilityCheck label="Base URL" /> : null}
            </div>
            <div className={fieldRowClassName}>
              <Input
                ref={baseUrlInputRef}
                id={`base-url-${draft.id}`}
                value={draft.base_url}
                onChange={(event) => {
                  if (baseUrlError) setBaseUrlError("")
                  onFieldChange({ base_url: event.target.value })
                }}
                placeholder="https://api.openai.com/v1"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                aria-invalid={baseUrlError ? true : undefined}
                aria-describedby={baseUrlError ? `base-url-error-${draft.id}` : undefined}
                onWheel={scrollInputContentOnWheel}
                className={scrollableInputClassName}
              />
              <div className={fieldActionClassName}>
                <FieldCopyButton value={draft.base_url} label="Base URL" />
              </div>
            </div>
            {baseUrlError ? <p id={`base-url-error-${draft.id}`} className="text-xs text-destructive">{baseUrlError}</p> : null}
          </div>
        ) : null}
        {!isOfficial ? (
          <Field>
            <FieldLabel htmlFor={`endpoint-test-model-${draft.id}`}>Endpoint test</FieldLabel>
            <FieldDescription>
              Please choose one model from Available Models for endpoint testing.
            </FieldDescription>
            <div className={fieldRowClassName}>
              <Input
                id={`endpoint-test-model-${draft.id}`}
                value={endpointModelId}
                onChange={(event) => setEndpointModelId(event.target.value)}
                placeholder={endpointModelPlaceholder(notableProviderKey ?? draft.id, draft.provider_type)}
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                onWheel={scrollInputContentOnWheel}
                className={cn(scrollableInputClassName, "font-mono")}
              />
              <div className={fieldActionClassName}>
                <Button
                  type="button"
                  variant="default"
                  onClick={() => onEndpointTest(trimmedEndpointModelId)}
                  disabled={isTestingEndpoint || !hasRequiredConfig || !trimmedEndpointModelId}
                  className="px-6"
                >
                  {isTestingEndpoint ? <Loader2 className="size-3.5 animate-spin" /> : null}
                  Test
                </Button>
              </div>
            </div>
          </Field>
        ) : null}
        {availableModels.length || hasEmptyModelListWarning ? (
          <div className="border-t pt-3 space-y-2 text-xs" data-testid="provider-capabilities">
            {hasAvailableModels ? (
              <div className="space-y-2 pb-1">
                <div className="text-muted-foreground">{availableModelsLabel}</div>
                <div
                  data-testid="available-models-list"
                  className={cn("flex gap-1 flex-wrap", !showAllModels && "max-h-[2.75rem] overflow-hidden")}
                >
                  <TooltipProvider>
                    {visibleModels.map((model) => {
                    const status = isOfficial ? routeDisplayStatus(model, isGettingModels) : modelRouteStatus(model)
                    const statusLabel = routeStatusLabel(status)
                    const modelType = isOfficial ? officialModelType(model) : null
                    const modelTypeLabel = isOfficial ? officialModelTypeLabel(model) : null
                    const isCapabilityModel = isOfficial && isCapabilityLibraryModel(model)
                    const profileTooltipText = isOfficial && !isCapabilityModel ? routeProfileTooltipText(model, status) : null
                    const failureTooltipText = isOfficial ? routeFailureTooltipText(model, status) : null
                    const tooltipDetail = (
                      failureTooltipText
                      ?? (isCapabilityModel && status !== "failed"
                        ? modelTypeLabel
                        : profileTooltipText)
                    ) ?? statusLabel
                    const appendModelTypeLabel = Boolean(
                      modelTypeLabel &&
                      tooltipDetail !== modelTypeLabel &&
                      status !== "verified",
                    )
                    const tooltipText = isOfficial
                      ? `${model.id} - ${tooltipDetail}${appendModelTypeLabel ? ` - ${modelTypeLabel}` : ""}`
                      : `Copy ${model.id}`
                    const hasReasoningProfile = isOfficial && modelHasVerifiedReasoningProfile(model)
                    const ariaLabel = isOfficial
                      ? `Copy ${copyTargetLabel} ${model.id}. ${tooltipDetail.replace(/\s+/g, " ")}`
                      : `Copy ${copyTargetLabel} ${model.id}`
                    const tag = (
                      <Tag
                        key={`${model.route_id ?? model.id}:${model.status ?? "model"}`}
                        asChild
                        variant={isOfficial ? routeStatusTagVariant(status, model) : "muted"}
                        size="xs"
                        className={cn(
                          "cursor-pointer font-mono hover:bg-muted/40",
                          status === "testing" && "api-route-tag-border-flow",
                        )}
                      >
                          <button
                            type="button"
                            onClick={() => void copyAvailableModelId(model.id)}
                            aria-label={ariaLabel}
                            data-route-status={isOfficial ? status : undefined}
                            data-model-type={modelType ?? undefined}
                            data-reasoning-route={hasReasoningProfile ? true : undefined}
                          >
                            {model.id}
                            {hasReasoningProfile ? <Brain className="size-2.5 shrink-0" aria-hidden="true" /> : null}
                          </button>
                        </Tag>
                      )
                    return (
                      <Tooltip key={`${model.route_id ?? model.id}:${model.status ?? "model"}:tooltip`}>
                        <TooltipTrigger asChild>{tag}</TooltipTrigger>
                        <TooltipContent className="max-w-sm whitespace-pre-line break-words">
                          {tooltipText}
                        </TooltipContent>
                      </Tooltip>
                    )
                  })}
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
                    {showAllModels ? "Show fewer" : `Show ${hiddenModelCount} more`}
                  </Button>
                ) : null}
              </div>
            ) : null}
            {hasEmptyModelListWarning ? (
              <div className="space-y-2 pb-1">
                <div className="text-muted-foreground">{availableModelsLabel}</div>
                <Badge variant="warning" className="gap-1">
                  <TriangleAlert className="size-3" />
                  No models returned
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
    </Card>
  )
}
