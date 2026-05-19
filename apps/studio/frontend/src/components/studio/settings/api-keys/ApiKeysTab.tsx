import { useMemo } from "react"
import { Check, Loader2, Plus, Trash2, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import type { CredentialsState, ProviderType } from "../../../../api/llm"
import { SectionTitle } from "../shared"
import type { ProviderDraft, SettingsPageContentProps } from "../types"

function SaveStatusBadge({ status }: { status: SaveStatus }) {
  if (status === "idle") return null
  if (status === "pending") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Pending
      </Badge>
    )
  }
  if (status === "saving") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Saving
      </Badge>
    )
  }
  if (status === "saved") {
    return (
      <Badge variant="outline" className="gap-1 text-[10px] font-normal">
        <Check className="size-3" />
        Saved
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1 text-[10px] font-normal">
      <TriangleAlert className="size-3" />
      Save failed
    </Badge>
  )
}

export function ApiKeysTab({
  credentials,
  drafts,
  saveStatus,
  onProviderFieldChange,
  onTestProvider,
  onDeleteProvider,
  onAddProvider,
}: Pick<
  SettingsPageContentProps,
  "credentials" | "drafts" | "saveStatus" | "onProviderFieldChange" | "onTestProvider" | "onDeleteProvider" | "onAddProvider"
>) {
  const persistedById = useMemo(
    () => Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider])),
    [credentials.providers],
  )

  return (
    <div>
      <SectionTitle
        title="API Keys"
        description="Local LLM provider credentials used by Studio runtime. Changes auto-save."
        trailing={<SaveStatusBadge status={saveStatus} />}
      />
      <div className="space-y-4" data-testid="api-keys-list">
        {drafts.map((draft) => {
          const persisted = persistedById[draft.id] ?? null
          return (
            <ProviderCard
              key={draft.id}
              draft={draft}
              persisted={persisted}
              onFieldChange={(patch) => onProviderFieldChange(draft.id, patch)}
              onTest={() => onTestProvider(draft.id)}
              onDelete={() => onDeleteProvider(draft.id)}
            />
          )
        })}
        {drafts.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border/60 bg-muted/10 px-4 py-10 text-center">
            <Button type="button" variant="default" onClick={onAddProvider} className="gap-1">
              <Plus className="size-3.5" />
              Add Provider
            </Button>
          </div>
        ) : null}
      </div>
      {drafts.length === 0 ? null : (
        <div className="mt-4 flex justify-start">
          <Button type="button" variant="outline" onClick={onAddProvider} className="gap-1">
            <Plus className="size-3.5" />
            Add Provider
          </Button>
        </div>
      )}
    </div>
  )
}

function ProviderCard({
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
            onValueChange={(next) => onFieldChange({ provider_type: next as ProviderType })}
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
