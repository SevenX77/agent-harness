import { useState } from 'react'
import { Check, FileSearch, Settings, TerminalSquare, X } from 'lucide-react'
import { toast } from 'sonner'

import { resolveCopilotToolApproval, type CopilotToolApprovalResponse } from '../../api/client'
import type { CopilotToolApprovalRequiredEvent } from '../../types/copilot'
import { copilotStore } from '../../store/copilotStore'
import { Button } from '../ui/button'

interface ResolveToolApprovalDecisionInput {
  skillId: string
  event: CopilotToolApprovalRequiredEvent
  approve: boolean
}

interface ResolveToolApprovalDecisionResult {
  label: string
  response: CopilotToolApprovalResponse
}

export async function resolveToolApprovalDecision({
  skillId,
  event,
  approve,
}: ResolveToolApprovalDecisionInput): Promise<ResolveToolApprovalDecisionResult> {
  const response = await resolveCopilotToolApproval(skillId, {
    toolUseId: event.toolUseId,
    approve,
  })

  if (!response.resolved) {
    // The hold is gone. WHICH way it went is the backend's to say — this used to
    // prefix "Approval expired:", asserting the timeout case whichever of the
    // three had actually happened (problem ledger CP6).
    throw new Error(response.message ?? 'This call is no longer being held.')
  }

  if (!approve) {
    return { label: `${event.toolName} rejected.`, response }
  }
  // Approved -> the CLI executes the tool itself; its result streams back into
  // the conversation (no backend re-execution).
  return { label: `${event.toolName} approved.`, response }
}

interface ToolApprovalCardProps {
  event: CopilotToolApprovalRequiredEvent
  skillId: string | null
}

export function ToolApprovalCard({ event, skillId }: ToolApprovalCardProps) {
  // Only the in-flight moment is local. The DECISION is read from the event,
  // which is what gets persisted — a card that remembered its own verdict came
  // back undecided every time it remounted (problem ledger CP6).
  const [errorLabel, setErrorLabel] = useState<string | null>(null)
  const [isResolving, setIsResolving] = useState(false)
  const settled = event.decision !== 'pending'
  const decisionLabel = settled ? `${event.toolName} ${event.decision}.` : null

  async function decide(approve: boolean) {
    if (!skillId || isResolving || settled) {
      return
    }

    setIsResolving(true)
    try {
      const result = await resolveToolApprovalDecision({ skillId, event, approve })
      setErrorLabel(null)
      copilotStore.decideToolApproval(event.id, approve ? 'approved' : 'denied')
      toast.success(result.label)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to resolve tool approval.'
      setErrorLabel(message)
      toast.error(message)
    } finally {
      setIsResolving(false)
    }
  }

  const disabled = !skillId || isResolving || settled
  // Mirrors the backend's _EXECUTION_CLASS_TOOLS: command runners whose detail
  // is the raw command line.
  const isExecution = event.toolName === 'Bash' || event.toolName === 'PowerShell'
  // A copilot config-truth write (mcp__studio__<tool>) is held for consent BEFORE
  // it persists — it is a Settings-scoped change, so it gets a settings icon +
  // a clear "LLM configuration" title. Anything else here is a write-class or
  // not-yet-classified tool held by the default-approval tier.
  const isMcpConfigWrite = event.toolName.startsWith('mcp__studio__')
  const Icon = isExecution ? TerminalSquare : isMcpConfigWrite ? Settings : FileSearch
  const title = isExecution
    ? `${event.toolName} held for approval`
    : isMcpConfigWrite
      ? `LLM configuration: ${event.toolName.slice('mcp__studio__'.length)} held for approval`
      : `${event.toolName} held for approval`

  return (
    <div className="mt-2 rounded-md border border-border bg-card p-2 text-xs ring-1 ring-foreground/10 ring-inset">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5 font-medium text-foreground">
          <Icon className="size-3.5 text-link" />
          <span>{title}</span>
        </div>
        {settled ? null : (
          <div className="flex shrink-0 items-center gap-1">
            <Button
              type="button"
              size="sm"
              onClick={() => void decide(true)}
              disabled={disabled}
              aria-label={`Approve ${event.toolName}`}
            >
              <Check data-icon="inline-start" />
              Approve
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => void decide(false)}
              disabled={disabled}
              aria-label={`Reject ${event.toolName}`}
            >
              <X data-icon="inline-start" />
              Reject
            </Button>
          </div>
        )}
      </div>
      <pre className="mt-1.5 max-h-40 overflow-auto rounded-md bg-background p-2 font-mono text-foreground">
        {event.detail}
      </pre>
      <p className={`mt-1 ${errorLabel ? 'text-destructive' : 'text-muted-foreground'}`}>
        {errorLabel ?? decisionLabel ?? 'Waiting for approval.'}
      </p>
    </div>
  )
}
