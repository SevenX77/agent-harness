import { CheckCircle2, CircleDashed, ShieldAlert, Sparkles, Trash2, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import type { CredentialProviderState, ModelInfo, ProviderType, TestStatus } from "@/api/llm"
import { translateErrorCode, translateTestStatus } from "@/lib/llm-error-messages"
import { cn } from "@/lib/utils"
import { ApiKeyInput } from "./ApiKeyInput"

export interface ProviderRowDraft {
  provider_code: string
  title: string
  provider_type: ProviderType
  base_url: string
  vendor_hint: string
  api_key: string
  /** Reflects the persisted `has_key` flag (true while server has a non-empty stored key). */
  hasSavedKey: boolean
  isTesting: boolean
}

interface ProviderRowProps {
  draft: ProviderRowDraft
  persisted: CredentialProviderState | null
  /**
   * Whether the user can edit this provider's identifying fields. False for
   * providers that come from `llm_roles.yaml` (their metadata is owned by
   * the YAML, not the credential record) — only the api_key + base_url are
   * editable in that case.
   */
  identityEditable: boolean
  onFieldChange: (patch: Partial<ProviderRowDraft>) => void
  onTest: () => void
  onDelete: () => void
}

const PROVIDER_TYPE_LABEL: Record<ProviderType, string> = {
  anthropic_compatible: "Anthropic 兼容",
  openai_compatible: "OpenAI 兼容",
  gemini_official: "Gemini 官方",
  // Engine still routes WS_LLM via _call_wavespeed_any_llm; surfaced here
  // for compatibility with existing roles.yaml entries.
  wavespeed_any_llm: "WaveSpeed Any-LLM",
}

export function ProviderRow({
  draft,
  persisted,
  identityEditable,
  onFieldChange,
  onTest,
  onDelete,
}: ProviderRowProps) {
  const lastStatus: TestStatus = persisted?.last_test_status ?? "untested"
  const lastErrorCode = persisted?.last_error_code ?? ""
  const lastMessage = persisted?.last_test_message ?? ""
  const lastAt = persisted?.last_test_at ?? ""
  const availableModels = persisted?.available_models ?? []
  const testDisabled = draft.isTesting

  const headerTitle =
    draft.title.trim() ||
    persisted?.name ||
    persisted?.title ||
    draft.provider_code

  return (
    <div
      className="rounded-md border border-border bg-card/40 px-4 py-3 shadow-sm"
      data-provider-code={draft.provider_code}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground" title={headerTitle}>
              {headerTitle}
            </span>
            <TestOutcomeBadge
              status={lastStatus}
              errorCode={lastErrorCode}
              message={lastMessage}
              at={lastAt}
            />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{draft.provider_code}</span>
            <span>·</span>
            <span>{PROVIDER_TYPE_LABEL[draft.provider_type]}</span>
            {draft.vendor_hint ? (
              <>
                <span>·</span>
                <span title="Vendor hint">{draft.vendor_hint}</span>
              </>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onTest}
            disabled={testDisabled}
            className="gap-1"
          >
            {draft.isTesting ? <Spinner className="size-3.5" /> : <Sparkles className="size-3.5" />}
            <span>{draft.isTesting ? "测试中" : "Test"}</span>
          </Button>
          {identityEditable ? (
            <TooltipProvider delayDuration={400}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={onDelete}
                    aria-label="Delete provider"
                    className="size-7 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>删除该 Provider</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : null}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor={`title-${draft.provider_code}`}>显示名称</Label>
          <Input
            id={`title-${draft.provider_code}`}
            value={draft.title}
            onChange={(event) => onFieldChange({ title: event.target.value })}
            placeholder={persisted?.name ?? "自定义名称（可选）"}
            disabled={!identityEditable}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`provider-type-${draft.provider_code}`}>协议</Label>
          <Select
            value={draft.provider_type}
            onValueChange={(next) => onFieldChange({ provider_type: next as ProviderType })}
            disabled={!identityEditable}
          >
            <SelectTrigger id={`provider-type-${draft.provider_code}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="anthropic_compatible">{PROVIDER_TYPE_LABEL.anthropic_compatible}</SelectItem>
              <SelectItem value="openai_compatible">{PROVIDER_TYPE_LABEL.openai_compatible}</SelectItem>
              <SelectItem value="gemini_official">{PROVIDER_TYPE_LABEL.gemini_official}</SelectItem>
              {/* wavespeed_any_llm only surfaces when an existing provider
                  already has that type (YAML-managed WS_LLM). New providers
                  can't pick it from the dropdown because identityEditable=false
                  on YAML-owned rows, and other rows shouldn't route through
                  the wavespeed-specific path. */}
              {draft.provider_type === "wavespeed_any_llm" ? (
                <SelectItem value="wavespeed_any_llm" disabled>
                  {PROVIDER_TYPE_LABEL.wavespeed_any_llm}
                </SelectItem>
              ) : null}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3">
        <div className="space-y-1">
          <Label htmlFor={`api-key-${draft.provider_code}`}>
            API Key
            {draft.hasSavedKey && !draft.api_key ? (
              <Badge variant="outline" className="ml-2 text-[10px] font-normal">
                已保存（留空保留）
              </Badge>
            ) : null}
          </Label>
          <ApiKeyInput
            inputId={`api-key-${draft.provider_code}`}
            value={draft.api_key}
            onChange={(next) => onFieldChange({ api_key: next })}
            providerCode={draft.provider_code}
            placeholder={
              draft.hasSavedKey
                ? "保留已存储的 Key（输入新值则覆盖）"
                : `粘贴 ${draft.provider_code} 的 API Key`
            }
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`base-url-${draft.provider_code}`}>Base URL（含 /v1 段）</Label>
          <Input
            id={`base-url-${draft.provider_code}`}
            value={draft.base_url}
            onChange={(event) => onFieldChange({ base_url: event.target.value })}
            placeholder="例如 https://api.openai.com/v1"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      </div>

      {availableModels.length > 0 ? (
        <ModelList provider_code={draft.provider_code} models={availableModels} />
      ) : null}
    </div>
  )
}

interface TestOutcomeBadgeProps {
  status: TestStatus
  errorCode: string
  message: string
  at: string
}

function TestOutcomeBadge({ status, errorCode, message, at }: TestOutcomeBadgeProps) {
  const statusLabel = translateTestStatus(status)
  const errorLabel = translateErrorCode(errorCode)
  const isoTimestamp = at ? formatTimestamp(at) : ""
  const tooltipLines = [
    errorLabel || statusLabel,
    message ? `详细：${message}` : "",
    isoTimestamp ? `测试时间：${isoTimestamp}` : "",
  ].filter(Boolean)

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]",
              status === "ok" && "border-emerald-700/40 bg-emerald-950/40 text-emerald-300",
              status === "untested" && "border-border bg-muted/30 text-muted-foreground",
              status !== "ok" && status !== "untested" && "border-red-800/40 bg-red-950/40 text-red-300",
            )}
            data-testid="test-outcome-badge"
            data-status={status}
          >
            <BadgeIcon status={status} />
            <span>{statusLabel}</span>
            {isoTimestamp ? <span className="text-muted-foreground/80">· {isoTimestamp}</span> : null}
          </span>
        </TooltipTrigger>
        {tooltipLines.length > 0 ? (
          <TooltipContent className="max-w-xs whitespace-pre-line text-xs">
            {tooltipLines.join("\n")}
          </TooltipContent>
        ) : null}
      </Tooltip>
    </TooltipProvider>
  )
}

function BadgeIcon({ status }: { status: TestStatus }) {
  if (status === "ok") return <CheckCircle2 className="size-3" />
  if (status === "untested") return <CircleDashed className="size-3" />
  if (status === "invalid_key") return <ShieldAlert className="size-3" />
  return <XCircle className="size-3" />
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  const hour = String(date.getHours()).padStart(2, "0")
  const minute = String(date.getMinutes()).padStart(2, "0")
  return `${month}-${day} ${hour}:${minute}`
}

interface ModelListProps {
  provider_code: string
  models: ModelInfo[]
}

function ModelList({ provider_code, models }: ModelListProps) {
  return (
    <div className="mt-3 rounded-md border border-dashed border-border/60 bg-muted/20 px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">
        可用模型（{models.length}）
      </div>
      <ul className="mt-1 flex max-h-32 flex-wrap gap-1 overflow-auto" data-testid={`models-${provider_code}`}>
        {models.map((model) => (
          <li key={model.id} className="inline-flex items-center gap-1 rounded border border-border/60 bg-background/60 px-2 py-0.5 text-[11px]">
            <span className="font-mono">{model.id}</span>
            <ModelCapabilityChips capabilities={model.capabilities} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function ModelCapabilityChips({ capabilities }: { capabilities: ModelInfo["capabilities"] }) {
  const chips: string[] = []
  if (capabilities.function_calling) chips.push("FC")
  if (capabilities.vision) chips.push("Vision")
  if (capabilities.reasoning) chips.push("Reason")
  if (chips.length === 0) return null
  return (
    <span className="ml-1 inline-flex items-center gap-0.5">
      {chips.map((label) => (
        <span key={label} className="rounded bg-muted/60 px-1 py-0 text-[10px] text-muted-foreground">
          {label}
        </span>
      ))}
    </span>
  )
}
