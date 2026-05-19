import { useState } from "react"
import { Eye, EyeOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"

export type AddProviderType = "third-party"

export interface AddProviderFormSubmission {
  providerCode: string
  name: string
  baseUrl: string
  apiKey: string
  type: AddProviderType
}

interface Props {
  onSubmit: (data: AddProviderFormSubmission) => Promise<void> | void
  onCancel: () => void
}

export function providerCodeFromCustomName(customName: string): string {
  return customName.toLowerCase().replace(/[^a-z0-9]/g, "-")
}

export function deriveAddProviderFormSubmission({
  customName,
  customBaseUrl,
  apiKey,
}: {
  type?: AddProviderType
  customName: string
  customBaseUrl: string
  apiKey: string
}): AddProviderFormSubmission {
  return {
    providerCode: providerCodeFromCustomName(customName),
    name: customName,
    baseUrl: customBaseUrl,
    apiKey,
    type: "third-party",
  }
}

export function canSubmitAddProviderForm({
  customName,
  customBaseUrl,
  apiKey,
}: {
  type?: AddProviderType
  customName: string
  customBaseUrl: string
  apiKey: string
}): boolean {
  if (apiKey.trim().length === 0) return false
  return customName.trim().length > 0 && customBaseUrl.trim().length > 0
}

export function AddProviderForm({ onSubmit, onCancel }: Props) {
  const [customName, setCustomName] = useState("")
  const [customBaseUrl, setCustomBaseUrl] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [visible, setVisible] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const submission = deriveAddProviderFormSubmission({
    customName,
    customBaseUrl,
    apiKey,
  })
  const canSubmit = canSubmitAddProviderForm({
    customName,
    customBaseUrl,
    apiKey,
  })

  return (
    <div className="rounded-md border p-4 space-y-4" data-testid="add-provider-form">
      <div className="space-y-1">
        <Label>Provider Name</Label>
        <Input
          value={customName}
          onChange={(event) => setCustomName(event.target.value)}
          placeholder="My OpenRouter"
          aria-label="Provider Name"
        />
      </div>
      <div className="space-y-1">
        <Label>Base URL</Label>
        <Input
          value={customBaseUrl}
          onChange={(event) => setCustomBaseUrl(event.target.value)}
          placeholder="https://openrouter.ai/api/v1"
          aria-label="Base URL"
        />
      </div>

      <div className="space-y-1">
        <Label>API Key</Label>
        <div className="flex items-center gap-2">
          <Input
            type="text"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="sk-..."
            aria-label="API Key"
            autoComplete="off"
            data-1p-ignore=""
            data-lpignore="true"
            data-form-type="other"
            spellCheck={false}
            className={cn("flex-1", !visible && "mask-input")}
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="transition-none"
            onClick={() => setVisible((value) => !value)}
            aria-label={visible ? "Hide API key" : "Show API key"}
          >
            {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </Button>
        </div>
      </div>

      <div className="flex gap-2 justify-end">
        <Button variant="ghost" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button
          disabled={!canSubmit || submitting}
          onClick={async () => {
            setSubmitting(true)
            try {
              await onSubmit(submission)
              setCustomName("")
              setCustomBaseUrl("")
              setApiKey("")
              setVisible(false)
            } finally {
              setSubmitting(false)
            }
          }}
        >
          Add
        </Button>
      </div>
    </div>
  )
}
