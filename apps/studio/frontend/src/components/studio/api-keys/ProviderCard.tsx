import { Loader2, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import type { ProviderType, CredentialsState } from "../../../api/llm"
import type { ProviderDraft } from "../SettingsPage"

export function ProviderCard({
  draft,
  persisted,
  onFieldChange,
  onTest,
  onDelete,
}: {
  draft: ProviderDraft
  persisted: CredentialsState["providers"][number] | null
  onFieldChange: (patch: Partial<ProviderDraft>) => void
  onTest: () => void
  onDelete: () => void
}) {
  const status = persisted?.last_test_status ?? "untested"
  const displayStatus = status === "ok" ? "Connected" : status === "untested" ? "Untested" : "Failed"
  const statusVariant = status === "ok" ? "secondary" : status === "untested" ? "outline" : "destructive"
  return (
    <Card data-provider-id={draft.id}>
      <CardHeader className="flex flex-row items-center gap-3 pb-2">
        <Input
          value={draft.name}
          onChange={(event) => onFieldChange({ name: event.target.value })}
          placeholder="Provider Name"
          className="w-full max-w-xs font-semibold"
          aria-label="Provider Name"
        />
        <Badge variant={statusVariant}>{displayStatus}</Badge>
        <div className="flex-1" />
        <Button type="button" variant="ghost" size="icon" onClick={onDelete} aria-label="Delete provider">
          <Trash2 className="size-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>SDK Protocol</Label>
          <RadioGroup
            value={draft.provider_type}
            onValueChange={(next: string) => onFieldChange({ provider_type: next as ProviderType })}
            className="flex flex-row gap-4"
          >
            <div className="flex items-center gap-2">
              <RadioGroupItem value="openai_compatible" id={`protocol-openai-${draft.id}`} />
              <Label htmlFor={`protocol-openai-${draft.id}`}>OpenAI Compatible</Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="anthropic_compatible" id={`protocol-anthropic-${draft.id}`} />
              <Label htmlFor={`protocol-anthropic-${draft.id}`}>Anthropic</Label>
            </div>
          </RadioGroup>
        </div>
        <div className="space-y-2">
          <Label htmlFor={`api-key-${draft.id}`}>API Key</Label>
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Input
                id={`api-key-${draft.id}`}
                type="text"
                value={draft.api_key}
                onChange={(event) => onFieldChange({ api_key: event.target.value })}
                placeholder="sk-..."
                name={`provider-secret-${draft.id}`}
                autoComplete="off"
                data-1p-ignore=""
                data-lpignore="true"
                data-form-type="other"
                spellCheck={false}
              />
            </div>
            <Button type="button" variant="default" onClick={onTest} disabled={draft.isTesting}>
              {draft.isTesting ? <Loader2 className="size-3.5 animate-spin" /> : null}
              Test
            </Button>
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor={`base-url-${draft.id}`}>Base URL</Label>
          <Input
            id={`base-url-${draft.id}`}
            value={draft.base_url}
            onChange={(event) => onFieldChange({ base_url: event.target.value })}
            placeholder="https://api.openai.com/v1"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      </CardContent>
    </Card>
  )
}
