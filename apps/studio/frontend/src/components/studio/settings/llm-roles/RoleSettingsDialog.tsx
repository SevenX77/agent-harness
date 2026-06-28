import { useEffect, useState } from "react"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { InputGroup, InputGroupInput } from "@/components/ui/input-group"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import type {
  RoleIntent,
  RoleProviderPreference,
  RoleThinkingPreference,
  RoleTokenIntent,
  RoleTokenIntentMode,
} from "@/api/llm"

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
  thinking: RoleThinkingPreference
  contextTokenMode: RoleTokenIntentMode
  contextTokens: string
  outputTokenMode: RoleTokenIntentMode
  outputTokens: string
}

export function RoleSettingsPanel({
  roleName,
  modelFallbackEnabled,
  intent,
  tokenLimitSummary,
  onModelFallbackChange,
  onSubmit,
}: {
  roleName: string
  modelFallbackEnabled: boolean
  intent?: RoleIntent
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

  return (
    <RoleSettingsFields
      roleName={roleName}
      modelFallbackEnabled={modelFallbackEnabled}
      draft={draft}
      tokenLimitSummary={tokenLimitSummary}
      onModelFallbackChange={onModelFallbackChange}
      onDraftChange={updateDraft}
    />
  )
}

export function RoleSettingsFields({
  roleName,
  modelFallbackEnabled,
  draft,
  tokenLimitSummary,
  onModelFallbackChange,
  onDraftChange,
}: {
  roleName: string
  modelFallbackEnabled: boolean
  draft: RoleSettingsDraft
  tokenLimitSummary: RoleTokenLimitSummary
  onModelFallbackChange: (enabled: boolean) => void
  onDraftChange: (draft: RoleSettingsDraft) => void
}) {
  return (
    <FieldSet data-role-settings-fields="true" className="gap-0">
      <FieldGroup className="gap-3">
        <div
          data-role-settings-toggles="true"
          className="rounded-md border border-border bg-muted/10 p-3"
        >
          <div className="grid gap-3 lg:grid-cols-[minmax(12rem,0.8fr)_minmax(18rem,1.2fr)]">
            <Field
              orientation="horizontal"
              data-role-model-fallback-setting="true"
              data-role-setting-key="model_fallback_enabled"
              className="min-h-10 items-center justify-between gap-3 rounded-md border border-border/70 bg-background/70 px-3"
            >
              <FieldLabel htmlFor={`model-fallback-${roleName}`} className="min-w-0 text-xs font-medium">
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

            <Field data-role-thinking-setting="true" className="min-w-0 gap-1.5 rounded-md border border-border/70 bg-background/70 p-3">
              <FieldLabel id={`thinking-${roleName}`} className="min-w-0 text-xs font-medium">
                Thinking
              </FieldLabel>
              <RadioGroup
                aria-labelledby={`thinking-${roleName}`}
                value={draft.thinking}
                onValueChange={(value) => onDraftChange({
                  ...draft,
                  thinking: value as RoleThinkingPreference,
                })}
                className="grid grid-cols-3 gap-1"
              >
                {(["off", "preferred", "required"] as const).map((value) => (
                  <FieldLabel
                    key={value}
                    htmlFor={`thinking-${value}-${roleName}`}
                    className="flex min-w-0 items-center justify-center gap-1.5 rounded-md border border-border/70 bg-muted/20 px-2 py-1.5 text-xs font-medium transition-colors has-[[data-state=checked]]:border-primary/60 has-[[data-state=checked]]:bg-primary/10"
                  >
                    <RadioGroupItem id={`thinking-${value}-${roleName}`} value={value} />
                    <span className="truncate">{thinkingLabel(value)}</span>
                  </FieldLabel>
                ))}
              </RadioGroup>
            </Field>
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <TokenIntentField
              roleName={roleName}
              kind="context"
              mode={draft.contextTokenMode}
              label="Context Tokens"
              tokens={draft.contextTokens}
              summary={tokenLimitSummary.context}
              onModeChange={(contextTokenMode) => onDraftChange({ ...draft, contextTokenMode })}
              onTokensChange={(contextTokens) => onDraftChange({ ...draft, contextTokens })}
            />
            <TokenIntentField
              roleName={roleName}
              kind="output"
              mode={draft.outputTokenMode}
              label="Output Tokens"
              tokens={draft.outputTokens}
              summary={tokenLimitSummary.output}
              onModeChange={(outputTokenMode) => onDraftChange({ ...draft, outputTokenMode })}
              onTokensChange={(outputTokens) => onDraftChange({ ...draft, outputTokens })}
            />
          </div>
        </div>
      </FieldGroup>
    </FieldSet>
  )
}

function TokenIntentField({
  roleName,
  kind,
  mode,
  label,
  tokens,
  summary,
  onModeChange,
  onTokensChange,
}: {
  roleName: string
  kind: "context" | "output"
  mode: RoleTokenIntentMode
  label: string
  tokens: string
  summary: TokenLimitSummary
  onModeChange: (mode: RoleTokenIntentMode) => void
  onTokensChange: (tokens: string) => void
}) {
  const inputId = `${kind}-token-target-${roleName}`
  const fieldDataAttribute = kind === "context"
    ? { "data-role-context-settings": true }
    : { "data-role-output-settings": true }
  const inputGroupDataAttribute = kind === "context"
    ? { "data-role-context-token-input-group": true }
    : { "data-role-output-token-input-group": true }
  return (
    <Field
      {...fieldDataAttribute}
      className="min-w-0 gap-1.5 rounded-md border border-border/70 bg-background/70 p-3"
    >
      <FieldLabel htmlFor={inputId} className="text-xs font-medium">{label}</FieldLabel>
      <div className="grid min-w-0 gap-2">
        <Select value={mode} onValueChange={(value) => onModeChange(value as RoleTokenIntentMode)}>
          <SelectTrigger size="sm" className="w-full">
            <SelectValue>{tokenModeLabel(mode)}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="default">Default</SelectItem>
            <SelectItem value="maximum_available">Use Max</SelectItem>
            <SelectItem value="required_minimum">Required Min</SelectItem>
            <SelectItem value="target">Target</SelectItem>
          </SelectContent>
        </Select>
        <InputGroup
          {...inputGroupDataAttribute}
        >
          <InputGroupInput
            id={inputId}
            aria-label={`${label} target for ${roleName}`}
            value={tokens}
            onChange={(event) => onTokensChange(event.target.value.replace(/[^\d]/g, ""))}
            inputMode="numeric"
            placeholder={summary.max ? `Blank uses max ${formatNumber(summary.max)}` : "Blank uses route max"}
          />
        </InputGroup>
      </div>
      <FieldDescription>
        {tokenSummaryText(label.replace(/ Tokens$/, ""), summary)}
      </FieldDescription>
    </Field>
  )
}

function draftFromIntent(intent?: RoleIntent): RoleSettingsDraft {
  const contextDraft = tokenDraftFromIntent(intent?.target_context_tokens)
  const outputDraft = tokenDraftFromIntent(intent?.target_output_tokens)
  return {
    providerPreference: intent?.provider_preference ?? "manual_order",
    thinking: intent?.thinking ?? "off",
    contextTokenMode: contextDraft.mode,
    contextTokens: contextDraft.tokens,
    outputTokenMode: outputDraft.mode,
    outputTokens: outputDraft.tokens,
  }
}

function tokenDraftFromIntent(intent?: RoleTokenIntent | null): {
  mode: RoleTokenIntentMode
  tokens: string
} {
  if (!intent) return { mode: "maximum_available", tokens: "" }
  return {
    mode: intent.mode,
    tokens: (intent.mode === "target" || intent.mode === "required_minimum") && intent.value ? String(intent.value) : "",
  }
}

function tokenSummaryText(label: string, summary: TokenLimitSummary): string {
  if (summary.totalCount === 0) return `${label} route max token caps are unavailable.`
  if (summary.knownCount === 0 || summary.min === null || summary.max === null) {
    return `${label} route max token caps are unavailable.`
  }
  const prefix = summary.min === summary.max
    ? `${label} route max token cap: ${formatNumber(summary.max)}.`
    : `${label} route max token range: min ${formatNumber(summary.min)} / max ${formatNumber(summary.max)}.`
  const unknownCount = summary.totalCount - summary.knownCount
  if (unknownCount <= 0) return prefix
  const routeLabel = unknownCount === 1 ? "1 route cap" : `${unknownCount} route caps`
  return `${prefix} ${routeLabel} unavailable.`
}

export function roleIntentFromSettingsDraft(draft: RoleSettingsDraft): RoleIntent {
  return {
    provider_preference: draft.providerPreference,
    thinking: draft.thinking,
    target_context_tokens: tokenIntentFromDraft(draft.contextTokenMode, draft.contextTokens),
    target_output_tokens: tokenIntentFromDraft(draft.outputTokenMode, draft.outputTokens),
  }
}

function tokenIntentFromDraft(mode: RoleTokenIntentMode, tokens: string): RoleTokenIntent | null {
  if (mode === "default") return null
  if (mode === "maximum_available") return { mode: "maximum_available" }
  const value = parseOptionalInteger(tokens)
  if (mode === "required_minimum") {
    return value === null ? { mode: "required_minimum" } : { mode, value, downgrade: "allow" }
  }
  if (value === null) return { mode: "target" }
  return { mode, value, downgrade: "allow_with_warning" }
}

function tokenModeLabel(mode: RoleTokenIntentMode): string {
  if (mode === "maximum_available") return "Use Max"
  if (mode === "required_minimum") return "Required Min"
  if (mode === "target") return "Target"
  return "Default"
}

function thinkingLabel(value: RoleThinkingPreference): string {
  if (value === "preferred") return "Preferred"
  if (value === "required") return "Required"
  return "Off"
}

function parseOptionalInteger(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? Math.max(1, Math.trunc(parsed)) : null
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value)
}
