import { useEffect, useState } from "react"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { InputGroup, InputGroupInput } from "@/components/ui/input-group"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select"
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

const TOKEN_MODE_OPTIONS: Array<{ value: RoleTokenIntentMode; label: string }> = [
  { value: "default", label: "Default" },
  { value: "maximum_available", label: "Use Max" },
  { value: "target", label: "Target" },
  { value: "required_minimum", label: "Required Min" },
]

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
    <FieldSet data-role-settings-fields="true" className="gap-3">
      <FieldGroup className="gap-3">
        <div
          data-role-settings-toggles="true"
          className="grid gap-x-4 gap-y-3 md:grid-cols-[minmax(8rem,0.9fr)_minmax(8rem,0.9fr)_minmax(18rem,1.8fr)] xl:grid-cols-[minmax(16rem,1fr)_minmax(16rem,1fr)]"
        >
          <Field
            orientation="horizontal"
            data-role-model-fallback-setting="true"
            data-role-setting-key="model_fallback_enabled"
            className="items-center justify-between gap-3 py-1"
          >
            <FieldLabel htmlFor={`model-fallback-${roleName}`} className="min-w-0 truncate">
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

          <Field data-role-thinking-setting="true" className="min-w-0 gap-1.5">
            <FieldLabel id={`thinking-${roleName}`} className="min-w-0 truncate">
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
                  className="flex min-w-0 items-center gap-1.5 rounded-md border border-border/70 px-2 py-1 text-xs font-medium"
                >
                  <RadioGroupItem id={`thinking-${value}-${roleName}`} value={value} />
                  <span className="truncate">{thinkingLabel(value)}</span>
                </FieldLabel>
              ))}
            </RadioGroup>
          </Field>

          <TokenIntentField
            roleName={roleName}
            label="Context Tokens"
            fieldKind="context"
            mode={draft.contextTokenMode}
            tokens={draft.contextTokens}
            summary={tokenLimitSummary.context}
            onModeChange={(contextTokenMode) => onDraftChange({
              ...draft,
              contextTokenMode,
              contextTokens: tokenModeAcceptsValue(contextTokenMode) ? draft.contextTokens : "",
            })}
            onTokensChange={(contextTokens) => onDraftChange({ ...draft, contextTokens })}
          />

          <TokenIntentField
            roleName={roleName}
            label="Output Tokens"
            fieldKind="output"
            mode={draft.outputTokenMode}
            tokens={draft.outputTokens}
            summary={tokenLimitSummary.output}
            onModeChange={(outputTokenMode) => onDraftChange({
              ...draft,
              outputTokenMode,
              outputTokens: tokenModeAcceptsValue(outputTokenMode) ? draft.outputTokens : "",
            })}
            onTokensChange={(outputTokens) => onDraftChange({ ...draft, outputTokens })}
          />
        </div>
      </FieldGroup>
    </FieldSet>
  )
}

function TokenIntentField({
  roleName,
  label,
  fieldKind,
  mode,
  tokens,
  summary,
  onModeChange,
  onTokensChange,
}: {
  roleName: string
  label: string
  fieldKind: "context" | "output"
  mode: RoleTokenIntentMode
  tokens: string
  summary: TokenLimitSummary
  onModeChange: (mode: RoleTokenIntentMode) => void
  onTokensChange: (tokens: string) => void
}) {
  const inputDisabled = !tokenModeAcceptsValue(mode)
  const inputId = `${fieldKind}-token-target-${roleName}`
  return (
    <Field
      data-role-context-settings={fieldKind === "context" ? "true" : undefined}
      data-role-output-settings={fieldKind === "output" ? "true" : undefined}
      className="min-w-0 gap-1.5"
    >
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      <div className="grid min-w-0 grid-cols-[minmax(7.25rem,auto)_minmax(0,1fr)] gap-2">
        <Select value={mode} onValueChange={(value) => onModeChange(value as RoleTokenIntentMode)}>
          <SelectTrigger size="sm" aria-label={`${label} mode for ${roleName}`} className="w-full">
            <span>{tokenModeLabel(mode)}</span>
          </SelectTrigger>
          <SelectContent>
            {TOKEN_MODE_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <InputGroup
          data-role-context-token-input-group={fieldKind === "context" ? "true" : undefined}
          data-role-output-token-input-group={fieldKind === "output" ? "true" : undefined}
        >
          <InputGroupInput
            id={inputId}
            aria-label={`${label} target for ${roleName}`}
            value={tokens}
            disabled={inputDisabled}
            onChange={(event) => onTokensChange(event.target.value.replace(/[^\d]/g, ""))}
            inputMode="numeric"
            placeholder={summary.max ? `Max ${formatNumber(summary.max)}` : "Optional value"}
          />
        </InputGroup>
      </div>
      <FieldDescription>
        {tokenLimitSummaryText(summary, fieldKind === "context" ? "Context" : "Output")}
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
  if (!intent) return { mode: "default", tokens: "" }
  return {
    mode: intent.mode,
    tokens: tokenModeAcceptsValue(intent.mode) && intent.value ? String(intent.value) : "",
  }
}

function tokenLimitSummaryText(summary: TokenLimitSummary, label: "Context" | "Output"): string {
  if (summary.totalCount === 0) return "No provider routes selected yet."
  if (summary.knownCount === 0 || summary.min === null || summary.max === null) {
    return `${label} route max token caps are unavailable.`
  }
  const prefix = summary.min === summary.max
    ? `${label} route max token: ${formatNumber(summary.max)}.`
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
  if (mode === "maximum_available") return { mode }
  const value = parseOptionalInteger(tokens)
  if (value === null) return null
  return { mode, value, downgrade: "allow" }
}

function tokenModeAcceptsValue(mode: RoleTokenIntentMode): boolean {
  return mode === "target" || mode === "required_minimum"
}

function tokenModeLabel(mode: RoleTokenIntentMode): string {
  return TOKEN_MODE_OPTIONS.find((option) => option.value === mode)?.label ?? "Default"
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
