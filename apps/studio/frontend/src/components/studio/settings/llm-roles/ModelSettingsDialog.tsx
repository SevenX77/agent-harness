import { useState } from "react"
import { Settings } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

export function ModelSettingsDialog({
  modelCode,
  modelName,
  temperature,
  maxTokens,
  open,
  onSubmit,
}: {
  modelCode: string
  modelName: string
  temperature: number | null
  maxTokens: number | null
  open?: boolean
  onSubmit: (settings: { temperature: number | null; max_tokens: number | null }) => void
}) {
  const [temperatureDraft, setTemperatureDraft] = useState(formatOptionalNumber(temperature))
  const [maxTokensDraft, setMaxTokensDraft] = useState(formatOptionalNumber(maxTokens))

  function submit() {
    onSubmit({
      temperature: parseOptionalNumber(temperatureDraft),
      max_tokens: parseOptionalInteger(maxTokensDraft),
    })
  }

  return (
    <Dialog open={open}>
      <TooltipProvider>
        <Tooltip>
          <DialogTrigger asChild>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label={`Model settings for ${modelName}`}
                className="text-muted-foreground hover:text-foreground"
              >
                <Settings data-role-icon="true" className="size-3 text-muted-foreground" />
              </Button>
            </TooltipTrigger>
          </DialogTrigger>
          <TooltipContent>Model settings</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <DialogContent forceMount className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Model settings</DialogTitle>
          <DialogDescription>{modelName}</DialogDescription>
        </DialogHeader>
        <ModelSettingsFields
          modelCode={modelCode}
          temperatureDraft={temperatureDraft}
          maxTokensDraft={maxTokensDraft}
          onTemperatureChange={setTemperatureDraft}
          onMaxTokensChange={setMaxTokensDraft}
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <DialogClose asChild>
            <Button type="button" onClick={submit}>
              Apply
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ModelSettingsFields({
  modelCode,
  temperatureDraft,
  maxTokensDraft,
  onTemperatureChange,
  onMaxTokensChange,
}: {
  modelCode: string
  temperatureDraft: string
  maxTokensDraft: string
  onTemperatureChange: (value: string) => void
  onMaxTokensChange: (value: string) => void
}) {
  return (
    <FieldSet>
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor={`temperature-${modelCode}`}>Temperature</FieldLabel>
          <Input
            id={`temperature-${modelCode}`}
            value={temperatureDraft}
            onChange={(event) => onTemperatureChange(event.target.value)}
            inputMode="decimal"
            placeholder="Inherit default"
          />
          <FieldDescription>Blank uses system default 0.7.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor={`max-tokens-${modelCode}`}>Max Tokens</FieldLabel>
          <Input
            id={`max-tokens-${modelCode}`}
            value={maxTokensDraft}
            onChange={(event) => onMaxTokensChange(event.target.value)}
            inputMode="numeric"
            placeholder="Inherit default"
          />
          <FieldDescription>Blank lets the runtime choose the provider default.</FieldDescription>
        </Field>
      </FieldGroup>
    </FieldSet>
  )
}

function formatOptionalNumber(value: number | null): string {
  return value === null || value === undefined ? "" : String(value)
}

function parseOptionalNumber(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

function parseOptionalInteger(value: string): number | null {
  const parsed = parseOptionalNumber(value)
  return parsed === null ? null : Math.trunc(parsed)
}
