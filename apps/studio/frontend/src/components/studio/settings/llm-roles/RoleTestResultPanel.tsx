import { AlertCircle, CheckCircle2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type {
  ProviderUiState,
  RoleFitState,
  RoleTestAdmissionDecision,
  RoleTestProviderStatus,
  RoleTestResponse,
  RoleTestStatus,
} from "@/api/llm"

export function RoleTestResultPanel({ result }: { result: RoleTestResponse }) {
  const meta = roleTestStatusMeta(result.status)
  const StatusIcon = meta.Icon

  return (
    <div
      data-role-test-result="true"
      className="space-y-2 rounded-md border border-border bg-muted/10 p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-foreground">
          <StatusIcon className={cn("size-3.5 shrink-0", meta.iconClassName)} />
          <span>Role Test</span>
        </div>
        <Badge variant={meta.variant} className="h-5 px-1.5 text-[10px]">
          {meta.label}
        </Badge>
      </div>
      <div className="space-y-2">
        {result.model_groups.map((group) => (
          <div key={group.canonical_id} className="space-y-1.5">
            <div className="text-xs font-medium text-foreground">{group.display_name}</div>
            <div className="grid gap-1.5">
              {group.provider_results.map((providerResult, index) => (
                <div
                  key={`${providerResult.provider_label}-${index}`}
                  className="rounded-md border border-border/70 bg-background/40 px-2 py-1.5"
                >
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                    <span className="min-w-0 truncate text-xs font-medium text-foreground">
                      {providerResult.provider_label}
                    </span>
                    <Badge variant={providerStatusVariant(providerResult.status)} className="h-5 px-1.5 text-[10px]">
                      {providerStatusLabel(providerResult.status, providerResult.admission_decision)}
                    </Badge>
                    <Badge variant="outline" className="h-5 px-1.5 text-[10px] text-muted-foreground">
                      {providerUiStateLabel(providerResult.provider_ui_state)}
                    </Badge>
                    <Badge variant="outline" className="h-5 px-1.5 text-[10px] text-muted-foreground">
                      {roleFitLabel(providerResult.role_fit)}
                    </Badge>
                  </div>
                  <ProviderDiagnostics result={providerResult} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ProviderDiagnostics({ result }: { result: RoleTestResponse["model_groups"][number]["provider_results"][number] }) {
  const messages = [
    result.message,
    ...result.warnings.map(warningMessage),
    result.retry_at ? `Retry at ${result.retry_at}.` : null,
  ].filter((message): message is string => Boolean(message))
  const uniqueMessages = Array.from(new Set(messages))
  if (uniqueMessages.length === 0) return null

  return (
    <div className="mt-1.5 space-y-1 text-[11px] leading-snug text-muted-foreground">
      {uniqueMessages.map((message) => (
        <div key={message}>{message}</div>
      ))}
    </div>
  )
}

function roleTestStatusMeta(status: RoleTestStatus): {
  label: string
  variant: "success" | "warning" | "destructive"
  Icon: typeof CheckCircle2
  iconClassName: string
} {
  if (status === "ok") {
    return { label: "Passed", variant: "success", Icon: CheckCircle2, iconClassName: "text-success" }
  }
  if (status === "warning") {
    return { label: "Needs Attention", variant: "warning", Icon: AlertCircle, iconClassName: "text-warning" }
  }
  return { label: "Failed", variant: "destructive", Icon: AlertCircle, iconClassName: "text-destructive" }
}

function providerStatusVariant(status: RoleTestProviderStatus): "success" | "warning" | "destructive" | "outline" {
  if (status === "ok") return "success"
  if (status === "untested") return "outline"
  return "destructive"
}

function providerStatusLabel(status: RoleTestProviderStatus, admissionDecision: RoleTestAdmissionDecision): string {
  if (status === "ok") return "Passed"
  if (admissionDecision === "temporary_skip") return "Skipped"
  if (status === "untested") return "Untested"
  if (status === "blocked") return "Blocked"
  return "Failed"
}

function providerUiStateLabel(state: ProviderUiState): string {
  if (state === "ready") return "Ready"
  if (state === "cooling_down") return "Cooling Down"
  if (state === "needs_setup") return "Needs Setup"
  if (state === "off") return "Off"
  return "Untested"
}

function roleFitLabel(fit: RoleFitState): string {
  if (fit === "using") return "Using"
  if (fit === "downgraded") return "Downgraded"
  if (fit === "needs_test") return "Needs Test"
  return "Not Fit"
}

function warningMessage(warning: Record<string, unknown>): string | null {
  const message = stringValue(warning.message) ?? stringValue(warning.detail)
  if (message) return ensureSentence(message)
  const code = stringValue(warning.code)
  if (code === "thinking_capability_unknown") return "Thinking is required but capability is unknown."
  if (code === "thinking_unsupported") return "Thinking is required but unsupported."
  if (code === "thinking_not_enabled") return "Thinking was preferred but is not enabled for this provider model."
  if (code === "token_downgraded") return "Requested output tokens exceed this route limit."
  return null
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null
}

function ensureSentence(value: string): string {
  const trimmed = value.trim()
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`
}
