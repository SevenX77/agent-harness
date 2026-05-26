import { useState } from "react"
import { toast } from "sonner"
import { CheckCircle2, Copy, Eye, EyeOff, Loader2, Trash2, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { translateErrorCode, translateTestStatus } from "@/lib/llm-error-messages"
import { cn } from "@/lib/utils"
import type { CredentialsState, ModelInfo, ProviderTestResult, ProviderType } from "../../../api/llm"
import { providerCachedTestResult, providerTestParamsMatch } from "../settings/provider-utils"
import type { ProviderDraft } from "../settings/types"
import { ManualModelTestPanel } from "./ManualModelTestPanel"

type TestMessageStatus = "not_configured" | "testing" | NonNullable<CredentialsState["providers"][number]["last_test_status"]>
const availableModelsPreviewLimit = 12
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

export function apiKeyInputType(visible: boolean): "text" | "password" {
  return visible ? "text" : "password"
}

export function apiKeyInputClassName(visible: boolean): string {
  return cn("flex-1", visible ? "text-foreground" : "text-muted-foreground")
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

export function sortModelInfos(models: ModelInfo[]): ModelInfo[] {
  return [...models].sort((left, right) => {
    const leftKey = modelSortKey(left.id)
    const rightKey = modelSortKey(right.id)
    const primary = leftKey.localeCompare(rightKey, undefined, { numeric: true, sensitivity: "base" })
    return primary !== 0 ? primary : left.id.localeCompare(right.id)
  })
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
  const canShowDiscoveredModels = status === "ok" || status === "untested"
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
    <DeleteConfirmDialog
      itemName={displayName}
      description="This provider configuration will be removed from the credentials document."
      onConfirm={onDelete}
      trigger={(
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Delete provider"
          data-delete-confirm-trigger={true}
          className="text-muted-foreground/70 hover:text-muted-foreground"
        >
          <Trash2 className="size-4" />
        </Button>
      )}
    />
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
  const isOfficial = providerKind === "official"
  const hasApiKey = draft.api_key.trim().length > 0
  const hasRequiredConfig = hasApiKey && (providerKind !== "third-party" || draft.base_url.trim().length > 0)
  const trimmedEndpointModelId = endpointModelId.trim()
  const matchedResult = providerCachedTestResult(persisted, draft) ?? directPersistedTestResult(persisted, draft)
  const hasMatchedTestResult = matchedResult !== null
  const displayName = draft.name.trim() || "Unnamed Provider"
  const apiKeyProviderName = displayName.replace(/ Official$/, "")
  const availableSdks = matchedResult?.available_sdks ?? []
  const availableModels = sortModelInfos(matchedResult?.available_models ?? [])
  const hasAvailableModels = availableModels.length > 0
  const visibleModels = showAllModels ? availableModels : availableModels.slice(0, availableModelsPreviewLimit)
  const hiddenModelCount = Math.max(0, availableModels.length - visibleModels.length)
  const matchedStatus = matchedResult?.last_test_status
  const matchedErrorCode = matchedResult?.last_error_code
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
  return (
    <Card data-provider-id={draft.id}>
      <CardHeader className="flex flex-row items-center gap-3 pb-2">
        <div className="min-w-0 max-w-xs truncate text-sm font-semibold text-foreground">{displayName}</div>
        {providerKind && !isOfficial ? (
          <Badge variant="outline" className="text-[10px] text-muted-foreground">
            Third-party
          </Badge>
        ) : null}
        <TestMessage status={testStatus} latencyMs={null} errorCode={matchedErrorCode ?? null} />
        <div className="flex-1" />
        {!isOfficial ? <ProviderDeleteButton draftName={draft.name} onDelete={onDelete} /> : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {!isOfficial ? (
          <div className="space-y-2">
            <Label htmlFor={`provider-name-${draft.id}`}>Provider Name</Label>
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
            />
          </div>
        ) : null}
        {!isOfficial ? (
          <div className="space-y-2">
            <Label htmlFor={`provider-protocol-${draft.id}`}>Protocol</Label>
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
          </div>
        ) : null}
        <div className="space-y-2">
          <Label htmlFor={`api-key-${draft.id}`}>API Key</Label>
          <div className="flex items-center gap-2">
            <Input
              id={`api-key-${draft.id}`}
              type={apiKeyInputType(visible)}
              value={draft.api_key}
              onChange={(event) => onFieldChange({ api_key: event.target.value })}
              placeholder={`Enter your ${apiKeyProviderName} API Key`}
              name={`provider-secret-${draft.id}`}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="none"
              data-1p-ignore=""
              data-lpignore="true"
              data-form-type="other"
              spellCheck={false}
              className={apiKeyInputClassName(visible)}
            />
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
            <Button type="button" variant="secondary" onClick={onGetModels} disabled={draft.isTesting || !hasRequiredConfig} className="px-4">
              {draft.isTesting ? <Loader2 className="size-3.5 animate-spin" /> : null}
              Get Models
            </Button>
          </div>
        </div>
        {!isOfficial ? (
          <div className="space-y-2">
            <Label htmlFor={`base-url-${draft.id}`}>Base URL</Label>
            <div className="flex items-center gap-2">
              <Input
                id={`base-url-${draft.id}`}
                value={draft.base_url}
                onChange={(event) => onFieldChange({ base_url: event.target.value })}
                placeholder="https://api.openai.com/v1"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                className="flex-1"
              />
              <FieldCopyButton value={draft.base_url} label="Base URL" />
            </div>
          </div>
        ) : null}
        <Field>
          <FieldLabel htmlFor={`endpoint-test-model-${draft.id}`}>Endpoint test</FieldLabel>
          <FieldDescription>
            Please choose one model from Available Models for endpoint testing.
          </FieldDescription>
          <div className="flex items-center gap-2">
            <Input
              id={`endpoint-test-model-${draft.id}`}
              value={endpointModelId}
              onChange={(event) => setEndpointModelId(event.target.value)}
              placeholder={endpointModelPlaceholder(notableProviderKey ?? draft.id, draft.provider_type)}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              className="flex-1 font-mono"
            />
            <Button
              type="button"
              variant="default"
              onClick={() => onEndpointTest(trimmedEndpointModelId)}
              disabled={draft.isTesting || !hasRequiredConfig || !trimmedEndpointModelId}
              className="px-6"
            >
              {draft.isTesting ? <Loader2 className="size-3.5 animate-spin" /> : null}
              Test
            </Button>
          </div>
        </Field>
        {availableSdks.length || availableModels.length ? (
          <div className="border-t pt-3 space-y-2 text-xs" data-testid="provider-capabilities">
            {availableSdks.length > 0 ? (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-muted-foreground">Available SDKs:</span>
                {availableSdks.map((sdk) => (
                  <Badge key={sdk} variant="outline" className="border-border/70 bg-muted/20 font-mono text-muted-foreground">
                    {sdk}
                  </Badge>
                ))}
              </div>
            ) : null}
            {hasAvailableModels ? (
              <div className="space-y-2 pb-1">
                <div className="text-muted-foreground">Available Models:</div>
                <div
                  data-testid="available-models-list"
                  className={cn("flex gap-1 flex-wrap", !showAllModels && "max-h-[2.75rem] overflow-hidden")}
                >
                  {visibleModels.map((model) => (
                    <Badge key={model.id} variant="outline" className="border-border/70 bg-muted/20 font-mono text-muted-foreground">
                      {model.id}
                    </Badge>
                  ))}
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
