import { useEffect, useState } from "react"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group"
import { Switch } from "@/components/ui/switch"
import type {
  RoleIntent,
  RoleProviderPreference,
  RoleThinkingPreference,
} from "@/api/llm"

export interface OutputLimitSummary {
  knownCount: number
  totalCount: number
  min: number | null
  max: number | null
}

export interface RoleSettingsDraft {
  providerPreference: RoleProviderPreference
  thinking: RoleThinkingPreference
  outputTokens: string
  useMaximumTokens: boolean
}

export function RoleSettingsPanel({
  roleName,
  modelFallbackEnabled,
  intent,
  outputLimitSummary,
  onModelFallbackChange,
  onSubmit,
}: {
  roleName: string
  modelFallbackEnabled: boolean
  intent?: RoleIntent
  outputLimitSummary: OutputLimitSummary
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
      outputLimitSummary={outputLimitSummary}
      onModelFallbackChange={onModelFallbackChange}
      onDraftChange={updateDraft}
    />
  )
}

export function RoleSettingsFields({
  roleName,
  modelFallbackEnabled,
  draft,
  outputLimitSummary,
  onModelFallbackChange,
  onDraftChange,
}: {
  roleName: string
  modelFallbackEnabled: boolean
  draft: RoleSettingsDraft
  outputLimitSummary: OutputLimitSummary
  onModelFallbackChange: (enabled: boolean) => void
  onDraftChange: (draft: RoleSettingsDraft) => void
}) {
  const thinkingPreferred = draft.thinking !== "off"

  return (
    <FieldSet data-role-settings-fields="true" className="gap-3">
      <FieldGroup className="gap-3">
        <div
          data-role-settings-toggles="true"
          className="grid gap-x-4 gap-y-3 md:grid-cols-[minmax(8rem,0.9fr)_minmax(8rem,0.9fr)_minmax(18rem,1.8fr)]"
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

          <Field
            orientation="horizontal"
            className="items-center justify-between gap-3 py-1"
          >
            <FieldLabel htmlFor={`thinking-preferred-${roleName}`} className="min-w-0 truncate">
              Thinking Preferred
            </FieldLabel>
            <Switch
              id={`thinking-preferred-${roleName}`}
              size="sm"
              checked={thinkingPreferred}
              onCheckedChange={(checked) => onDraftChange({
                ...draft,
                thinking: checked ? "preferred" : "off",
              })}
              aria-label={`Thinking Preferred for ${roleName}`}
            />
          </Field>

          <Field data-role-output-settings="true" className="min-w-0 gap-1.5">
            <FieldLabel htmlFor={`output-token-target-${roleName}`}>Output Token Target</FieldLabel>
            <InputGroup data-role-output-token-input-group="true">
              <InputGroupInput
                id={`output-token-target-${roleName}`}
                aria-label={`Output token target for ${roleName}`}
                value={draft.outputTokens}
                disabled={draft.useMaximumTokens}
                onChange={(event) => onDraftChange({
                  ...draft,
                  outputTokens: event.target.value.replace(/[^\d]/g, ""),
                })}
                inputMode="numeric"
                placeholder={outputLimitSummary.max ? `Max ${formatNumber(outputLimitSummary.max)}` : "Optional target"}
              />
              <InputGroupAddon align="inline-end" className="cursor-default gap-2 pr-1.5">
                <span className="whitespace-nowrap text-[11px]">Use max</span>
                <Switch
                  size="sm"
                  checked={draft.useMaximumTokens}
                  onCheckedChange={(checked) => onDraftChange({
                    ...draft,
                    useMaximumTokens: checked,
                  })}
                  aria-label={`Use maximum output tokens for ${roleName}`}
                />
              </InputGroupAddon>
            </InputGroup>
            <FieldDescription>
              {outputLimitSummaryText(outputLimitSummary)}
            </FieldDescription>
          </Field>
        </div>
      </FieldGroup>
    </FieldSet>
  )
}

function draftFromIntent(intent?: RoleIntent): RoleSettingsDraft {
  const outputIntent = intent?.target_output_tokens
  return {
    providerPreference: intent?.provider_preference ?? "manual_order",
    thinking: intent?.thinking ?? "off",
    outputTokens: outputIntent?.mode === "target" && outputIntent.value ? String(outputIntent.value) : "",
    useMaximumTokens: outputIntent?.mode === "maximum_available",
  }
}

function outputLimitSummaryText(summary: OutputLimitSummary): string {
  if (summary.totalCount === 0) {
    return "No provider routes selected yet."
  }
  if (summary.knownCount === 0 || summary.min === null || summary.max === null) {
    return "Selected route max token caps are unavailable."
  }
  const prefix = summary.min === summary.max
    ? `Route max token: ${formatNumber(summary.max)}.`
    : `Route max token range: min ${formatNumber(summary.min)} / max ${formatNumber(summary.max)}.`
  const unknownCount = summary.totalCount - summary.knownCount
  if (unknownCount <= 0) return prefix
  const routeLabel = unknownCount === 1 ? "1 route cap" : `${unknownCount} route caps`
  return `${prefix} ${routeLabel} unavailable.`
}

export function roleIntentFromSettingsDraft(draft: RoleSettingsDraft): RoleIntent {
  if (draft.useMaximumTokens) {
    return {
      provider_preference: draft.providerPreference,
      thinking: draft.thinking,
      target_output_tokens: {
        mode: "maximum_available",
      },
    }
  }
  const outputValue = parseOptionalInteger(draft.outputTokens)
  return {
    provider_preference: draft.providerPreference,
    thinking: draft.thinking,
    target_output_tokens: outputValue !== null
      ? {
          mode: "target",
          value: outputValue,
          downgrade: "allow",
        }
      : null,
  }
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
