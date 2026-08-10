import { useEffect, useRef, useState } from "react"
import { CircleHelp } from "lucide-react"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { RoleIntent, RoleProviderPreference } from "@/api/llm"
import {
  DEFAULT_ROLE_TEMPERATURE,
  formatTemperaturePercent,
  TEMPERATURE_SCALE_HELP,
} from "@/components/studio/llm-temperature"
import { formatEffortLabel, PROVIDER_DEFAULT_EFFORT } from "@/components/studio/llm-effort"

export interface TokenLimitSummary {
  knownCount: number
  totalCount: number
  min: number | null
  max: number | null
}

export interface RoleTokenLimitSummary {
  context: TokenLimitSummary
  output: TokenLimitSummary
}

export interface RoleSettingsDraft {
  providerPreference: RoleProviderPreference
  thinking: boolean
  maxOutputTokens: string
  temperature: string
  /** A level name, or PROVIDER_DEFAULT_EFFORT for "leave the provider's default". */
  reasoningEffort: string
}

export function RoleSettingsPanel({
  roleName,
  modelFallbackEnabled,
  intent,
  effortLevels,
  tokenLimitSummary,
  onModelFallbackChange,
  onSubmit,
}: {
  roleName: string
  modelFallbackEnabled: boolean
  intent?: RoleIntent
  effortLevels: string[]
  tokenLimitSummary: RoleTokenLimitSummary
  onModelFallbackChange: (enabled: boolean) => void
  onSubmit: (intent: RoleIntent) => void
}) {
  const [draft, setDraft] = useState(() => draftFromIntent(intent))

  useEffect(() => {
    setDraft(draftFromIntent(intent))
  }, [intent])

  function updateDraft(nextDraft: RoleSettingsDraft) {
    setDraft(nextDraft)
    onSubmit(roleIntentFromSettingsDraft(nextDraft))
  }

  function previewDraft(nextDraft: RoleSettingsDraft) {
    setDraft(nextDraft)
  }

  return (
    <RoleSettingsFields
      roleName={roleName}
      modelFallbackEnabled={modelFallbackEnabled}
      draft={draft}
      effortLevels={effortLevels}
      tokenLimitSummary={tokenLimitSummary}
      onModelFallbackChange={onModelFallbackChange}
      onDraftChange={updateDraft}
      onDraftPreview={previewDraft}
    />
  )
}

export function RoleSettingsFields({
  roleName,
  modelFallbackEnabled,
  draft,
  effortLevels,
  tokenLimitSummary,
  onModelFallbackChange,
  onDraftChange,
  onDraftPreview,
}: {
  roleName: string
  modelFallbackEnabled: boolean
  draft: RoleSettingsDraft
  effortLevels: string[]
  tokenLimitSummary: RoleTokenLimitSummary
  onModelFallbackChange: (enabled: boolean) => void
  onDraftChange: (draft: RoleSettingsDraft) => void
  onDraftPreview?: (draft: RoleSettingsDraft) => void
}) {
  const outputTokenPlaceholder = tokenLimitSummary.output.max
    ? `Blank uses model max (${formatThousands(String(tokenLimitSummary.output.max))})`
    : "Blank uses model max"
  const pendingTemperatureRef = useRef<string | null>(null)
  const lastTemperatureRoleRef = useRef(roleName)
  const lastSubmittedTemperatureRef = useRef(draft.temperature)

  if (lastTemperatureRoleRef.current !== roleName) {
    lastTemperatureRoleRef.current = roleName
    pendingTemperatureRef.current = null
    lastSubmittedTemperatureRef.current = draft.temperature
  }

  function commitTemperature(temperature: string) {
    pendingTemperatureRef.current = null
    if (lastSubmittedTemperatureRef.current === temperature) {
      return
    }
    lastSubmittedTemperatureRef.current = temperature
    onDraftChange({
      ...draft,
      temperature,
    })
  }

  function commitPendingTemperature() {
    if (pendingTemperatureRef.current == null) {
      return
    }
    commitTemperature(pendingTemperatureRef.current)
  }

  function updateTemperature(temperature: string, commit: boolean) {
    const nextDraft = {
      ...draft,
      temperature,
    }
    if (commit) {
      commitTemperature(temperature)
      return
    }
    pendingTemperatureRef.current = temperature
    ;(onDraftPreview ?? onDraftChange)(nextDraft)
  }

  return (
    <FieldSet data-role-settings-fields="true" className="gap-0">
      <FieldGroup className="gap-3">
        <div
          data-role-settings-toggles="true"
          className="grid gap-3 lg:grid-cols-2"
        >
          <Field
            orientation="horizontal"
            data-role-model-fallback-setting="true"
            data-role-setting-key="model_fallback_enabled"
            className="min-h-10 items-center justify-between gap-3 rounded-md border border-border/70 bg-background/70 px-3"
          >
            <FieldLabel
              htmlFor={`model-fallback-${roleName}`}
              className="min-w-0 text-xs font-medium"
              onClick={(event) => event.preventDefault()}
            >
              Model Fallback
            </FieldLabel>
            <Switch
              id={`model-fallback-${roleName}`}
              size="sm"
              checked={modelFallbackEnabled}
              onCheckedChange={onModelFallbackChange}
              aria-label={`Model fallback for ${roleName}`}
            />
          </Field>

          <Field
            orientation="horizontal"
            data-role-thinking-setting="true"
            className="min-h-10 items-center justify-between gap-3 rounded-md border border-border/70 bg-background/70 px-3"
          >
            <FieldLabel
              htmlFor={`thinking-${roleName}`}
              className="min-w-0 text-xs font-medium"
              onClick={(event) => event.preventDefault()}
            >
              Thinking
            </FieldLabel>
            <Switch
              id={`thinking-${roleName}`}
              size="sm"
              checked={draft.thinking}
              onCheckedChange={(thinking) => onDraftChange({ ...draft, thinking })}
              aria-label={`Thinking for ${roleName}`}
            />
          </Field>
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          <Field
            data-role-output-settings="true"
            className="min-w-0 gap-1.5 rounded-md border border-border/70 bg-background/70 p-3"
          >
            <FieldLabel htmlFor={`output-tokens-${roleName}`} className="text-xs font-medium">
              Max output tokens
            </FieldLabel>
            <Input
              id={`output-tokens-${roleName}`}
              data-role-output-token-input="true"
              aria-label={`Max output tokens for ${roleName}`}
              value={formatThousands(draft.maxOutputTokens)}
              onChange={(event) => onDraftChange({
                ...draft,
                maxOutputTokens: stripThousands(event.target.value),
              })}
              inputMode="numeric"
              placeholder={outputTokenPlaceholder}
            />
            <FieldDescription>{outputTokenSummaryText(tokenLimitSummary.output)}</FieldDescription>
          </Field>

          <Field
            data-role-temperature-settings="true"
            className="min-w-0 gap-1.5 rounded-md border border-border/70 bg-background/70 p-3"
          >
            <FieldLabel htmlFor={`temperature-${roleName}`} className="inline-flex items-center gap-1 text-xs font-medium">
              <span>Temperature</span>
              <TemperatureHelp />
            </FieldLabel>
            <div className="flex h-9 items-center gap-2">
              <Slider
                id={`temperature-${roleName}`}
                data-role-temperature-input="true"
                aria-label={`Temperature for ${roleName}`}
                min={0}
                max={2}
                step={0.1}
                value={[draft.temperature === "" ? 1 : Number(draft.temperature)]}
                onValueChange={(vals) => updateTemperature(String(vals[0]), false)}
                onValueCommit={(vals) => updateTemperature(String(vals[0]), true)}
                onPointerUpCapture={commitPendingTemperature}
                onPointerCancelCapture={commitPendingTemperature}
                onKeyUpCapture={commitPendingTemperature}
                onBlurCapture={commitPendingTemperature}
                className="flex-1"
              />
              <span className="w-9 shrink-0 text-right text-xs text-foreground">
                {formatTemperaturePercent(draft.temperature)}
              </span>
            </div>
            <FieldDescription>Drag to set the role temperature; 70% is the default.</FieldDescription>
          </Field>

          <Field
            data-role-effort-settings="true"
            className="min-w-0 gap-1.5 rounded-md border border-border/70 bg-background/70 p-3"
          >
            <FieldLabel htmlFor={`reasoning-effort-${roleName}`} className="text-xs font-medium">
              Reasoning effort
            </FieldLabel>
            <Select
              value={draft.reasoningEffort}
              disabled={effortLevels.length === 0}
              onValueChange={(reasoningEffort) => onDraftChange({ ...draft, reasoningEffort })}
            >
              <SelectTrigger
                id={`reasoning-effort-${roleName}`}
                data-role-effort-input="true"
                aria-label={`Reasoning effort for ${roleName}`}
                className="h-9 w-full text-xs"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={PROVIDER_DEFAULT_EFFORT}>Provider default</SelectItem>
                {effortLevels.map((level) => (
                  <SelectItem key={level} value={level}>{formatEffortLabel(level)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription>{effortSummaryText(effortLevels)}</FieldDescription>
          </Field>
        </div>
      </FieldGroup>
    </FieldSet>
  )
}

function TemperatureHelp() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="About temperature scale"
          className="inline-flex size-4 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-hidden"
        >
          <CircleHelp className="size-3.5" aria-hidden="true" />
        </button>
      </TooltipTrigger>
      <TooltipContent>{TEMPERATURE_SCALE_HELP}</TooltipContent>
    </Tooltip>
  )
}

function draftFromIntent(intent?: RoleIntent): RoleSettingsDraft {
  return {
    providerPreference: intent?.provider_preference ?? "manual_order",
    thinking: intent?.thinking ?? false,
    maxOutputTokens: intent?.max_output_tokens != null ? String(intent.max_output_tokens) : "",
    temperature: intent?.temperature != null ? String(intent.temperature) : String(DEFAULT_ROLE_TEMPERATURE),
    reasoningEffort: intent?.reasoning_effort ?? PROVIDER_DEFAULT_EFFORT,
  }
}

function effortSummaryText(effortLevels: string[]): string {
  if (effortLevels.length === 0) return "No model in this role reports effort levels."
  return "How hard the model works when it reasons; each model runs the nearest level it sells."
}

function outputTokenSummaryText(summary: TokenLimitSummary): string {
  if (summary.totalCount === 0 || summary.knownCount === 0 || summary.min === null || summary.max === null) {
    return "Route max output token caps are unavailable."
  }
  const prefix = summary.min === summary.max
    ? `Route max output token cap: ${formatNumber(summary.max)}.`
    : `Route max output token range: min ${formatNumber(summary.min)} / max ${formatNumber(summary.max)}.`
  const unknownCount = summary.totalCount - summary.knownCount
  if (unknownCount <= 0) return prefix
  const routeLabel = unknownCount === 1 ? "1 route cap" : `${unknownCount} route caps`
  return `${prefix} ${routeLabel} unavailable.`
}

export function roleIntentFromSettingsDraft(draft: RoleSettingsDraft): RoleIntent {
  return {
    provider_preference: draft.providerPreference,
    thinking: draft.thinking,
    max_output_tokens: parseOptionalInteger(draft.maxOutputTokens),
    temperature: parseOptionalNumber(draft.temperature) ?? DEFAULT_ROLE_TEMPERATURE,
    reasoning_effort: draft.reasoningEffort === PROVIDER_DEFAULT_EFFORT ? null : draft.reasoningEffort,
  }
}

/**
 * PR3 display helper (exported for tests): render a raw integer string with
 * thousands separators, e.g. "128000" → "128,000". Non-digit characters are
 * dropped first so it is safe to call on live keystroke input. An empty /
 * all-non-digit string returns "".
 */
export function formatThousands(value: string): string {
  const digits = value.replace(/[^\d]/g, "")
  if (!digits) return ""
  return new Intl.NumberFormat("en-US").format(Number(digits))
}

/** PR3 (exported for tests): drop thousands separators back to a raw digit string. */
export function stripThousands(value: string): string {
  return value.replace(/[^\d]/g, "")
}

function parseOptionalInteger(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : null
}

function parseOptionalNumber(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value)
}
