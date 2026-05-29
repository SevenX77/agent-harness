import { useEffect, useState } from "react"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import type {
  RoleIntent,
  RoleProviderPreference,
  RoleThinkingPreference,
  RoleTokenDowngrade,
} from "@/api/llm"

export interface OutputLimitSummary {
  knownCount: number
  totalCount: number
  min: number | null
  max: number | null
}

interface RoleSettingsDraft {
  providerPreference: RoleProviderPreference
  thinking: RoleThinkingPreference
  outputTokens: string
  outputDowngrade: RoleTokenDowngrade
}

export function RoleSettingsPanel({
  roleName,
  intent,
  outputLimitSummary,
  onSubmit,
}: {
  roleName: string
  intent?: RoleIntent
  outputLimitSummary: OutputLimitSummary
  onSubmit: (intent: RoleIntent) => void
}) {
  const [draft, setDraft] = useState(() => draftFromIntent(intent))

  useEffect(() => {
    setDraft(draftFromIntent(intent))
  }, [intent])

  function updateDraft(nextDraft: RoleSettingsDraft) {
    setDraft(nextDraft)
    onSubmit(intentFromDraft(nextDraft))
  }

  return (
    <RoleSettingsFields
      roleName={roleName}
      draft={draft}
      outputLimitSummary={outputLimitSummary}
      onDraftChange={updateDraft}
    />
  )
}

export function RoleSettingsFields({
  roleName,
  draft,
  outputLimitSummary,
  onDraftChange,
}: {
  roleName: string
  draft: RoleSettingsDraft
  outputLimitSummary: OutputLimitSummary
  onDraftChange: (draft: RoleSettingsDraft) => void
}) {
  const thinkingRequired = draft.thinking !== "off"

  return (
    <FieldSet data-role-settings-fields="true" className="gap-3">
      <FieldGroup className="gap-3">
        <Field orientation="horizontal" className="items-center justify-between gap-3 rounded-md border border-border/70 bg-muted/10 px-3 py-2">
          <div className="min-w-0">
            <FieldLabel htmlFor={`thinking-required-${roleName}`}>Thinking Required</FieldLabel>
            <FieldDescription>Routes must prove or validate thinking support for this role.</FieldDescription>
          </div>
          <Switch
            id={`thinking-required-${roleName}`}
            size="sm"
            checked={thinkingRequired}
            onCheckedChange={(checked) => onDraftChange({
              ...draft,
              thinking: checked ? "required" : "off",
            })}
            aria-label={`Thinking Required for ${roleName}`}
          />
        </Field>

        <Field>
          <FieldLabel htmlFor={`output-token-target-${roleName}`}>Output Token Target</FieldLabel>
          <Input
            id={`output-token-target-${roleName}`}
            aria-label={`Output token target for ${roleName}`}
            value={draft.outputTokens}
            onChange={(event) => onDraftChange({
              ...draft,
              outputTokens: event.target.value.replace(/[^\d]/g, ""),
            })}
            inputMode="numeric"
            placeholder={outputLimitSummary.max ? `Max ${formatNumber(outputLimitSummary.max)}` : "Test first"}
          />
          <FieldDescription>
            {outputLimitSummaryText(outputLimitSummary)}
          </FieldDescription>
        </Field>

        <Field>
          <FieldLabel htmlFor={`output-downgrade-${roleName}`}>If Target Exceeds Route Cap</FieldLabel>
          <Select
            value={draft.outputDowngrade}
            onValueChange={(value) => onDraftChange({
              ...draft,
              outputDowngrade: value as RoleTokenDowngrade,
            })}
          >
            <SelectTrigger
              id={`output-downgrade-${roleName}`}
              className="w-full"
              aria-label={`If Target Exceeds Route Cap: ${downgradeLabel(draft.outputDowngrade)}`}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="allow_with_warning">Use route max and mark Limited</SelectItem>
              <SelectItem value="allow">Use route max</SelectItem>
              <SelectItem value="block">Block that route</SelectItem>
            </SelectContent>
          </Select>
          <FieldDescription>
            Use route max and mark Limited still lets the route run with the provider cap. Block removes that route from the role test path.
          </FieldDescription>
        </Field>
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
    outputDowngrade: outputIntent?.downgrade ?? "allow_with_warning",
  }
}

function outputLimitSummaryText(summary: OutputLimitSummary): string {
  if (summary.totalCount === 0) {
    return "No provider routes selected yet."
  }
  if (summary.knownCount === 0 || summary.min === null || summary.max === null) {
    return "Selected route output caps are not known yet. Test first."
  }
  const prefix = summary.min === summary.max
    ? `Known selected route output cap: ${formatNumber(summary.max)}.`
    : `Known selected route output caps: min ${formatNumber(summary.min)} / max ${formatNumber(summary.max)}.`
  const unknownCount = summary.totalCount - summary.knownCount
  if (unknownCount <= 0) return prefix
  const routeLabel = unknownCount === 1 ? "1 route" : `${unknownCount} routes`
  return `${prefix} ${routeLabel} still needs testing.`
}

function downgradeLabel(value: RoleTokenDowngrade): string {
  if (value === "block") return "Block that route"
  if (value === "allow") return "Use route max"
  return "Use route max and mark Limited"
}

function intentFromDraft(draft: RoleSettingsDraft): RoleIntent {
  const outputValue = parseOptionalInteger(draft.outputTokens)
  return {
    provider_preference: "manual_order",
    thinking: draft.thinking,
    target_output_tokens: outputValue !== null
      ? {
          mode: "target",
          value: outputValue,
          downgrade: draft.outputDowngrade,
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
