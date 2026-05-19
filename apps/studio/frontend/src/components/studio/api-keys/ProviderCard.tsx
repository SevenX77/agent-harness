import { useState } from "react"
import { CheckCircle2, Eye, EyeOff, Loader2, Trash2, XCircle } from "lucide-react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { cn } from "@/lib/utils"
import type { ProviderType, CredentialsState } from "../../../api/llm"
import type { ProviderDraft } from "../SettingsPage"

type TestMessageStatus = "untested" | "testing" | "ok" | "error"

export function apiKeyInputClassName(visible: boolean): string {
  return cn("flex-1", !visible && "mask-input")
}

export function TestMessage({
  status,
  latencyMs,
  errorCode,
}: {
  status: TestMessageStatus
  latencyMs?: number | null
  errorCode?: string | null
}) {
  if (status === "testing") {
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="size-3 animate-spin" />
        Testing...
      </Badge>
    )
  }

  if (status === "ok") {
    return (
      <Badge variant="outline" className="gap-1 text-emerald-500 border-emerald-500/50">
        <CheckCircle2 className="size-3" />
        {latencyMs != null ? `Connected (${latencyMs}ms)` : "Connected"}
      </Badge>
    )
  }

  if (status === "error") {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="size-3" />
        {errorCode ?? "Error"}
      </Badge>
    )
  }

  return <Badge variant="secondary">Untested</Badge>
}

export function ProviderDeleteConfirmation({
  draftName,
  onDelete,
}: {
  draftName: string
  onDelete: () => void
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button type="button" variant="ghost" size="icon" aria-label="Delete provider">
          <Trash2 className="size-4" />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>确认删除 {draftName || "this provider"}?</AlertDialogTitle>
          <AlertDialogDescription>此操作不可恢复, 该 provider 配置将永久删除。</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction onClick={onDelete}>删除</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

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
  const [visible, setVisible] = useState(false)
  const testStatus: TestMessageStatus = draft.isTesting
    ? "testing"
    : persisted?.last_test_status === "ok"
      ? "ok"
      : persisted?.last_test_status && persisted.last_test_status !== "untested"
        ? "error"
        : "untested"
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
        <TestMessage status={testStatus} latencyMs={null} errorCode={persisted?.last_error_code ?? null} />
        <div className="flex-1" />
        <ProviderDeleteConfirmation draftName={draft.name} onDelete={onDelete} />
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
              className={apiKeyInputClassName(visible)}
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
            <Button type="button" variant="default" onClick={onTest} disabled={draft.isTesting} className="px-6">
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
