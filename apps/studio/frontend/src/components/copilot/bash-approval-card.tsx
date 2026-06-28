import { useState } from 'react'
import { Check, TerminalSquare, X } from 'lucide-react'
import { toast } from 'sonner'

import { resolveCopilotBashApproval, type CopilotBashApprovalResponse } from '../../api/client'
import type { CopilotBashApprovalRequiredEvent } from '../../types/copilot'
import { Button } from '../ui/button'

interface ResolveBashApprovalDecisionInput {
  skillId: string
  event: CopilotBashApprovalRequiredEvent
  approve: boolean
}

interface ResolveBashApprovalDecisionResult {
  label: string
  response: CopilotBashApprovalResponse
}

function formatBashApprovalFailure(response: CopilotBashApprovalResponse): string {
  const reason =
    response.message ??
    (response.returncode !== null ? `return code ${response.returncode}` : 'unknown error')
  return `Command approval failed: ${reason}`
}

export async function resolveBashApprovalDecision({
  skillId,
  event,
  approve,
}: ResolveBashApprovalDecisionInput): Promise<ResolveBashApprovalDecisionResult> {
  const response = await resolveCopilotBashApproval(skillId, {
    toolUseId: event.toolUseId,
    approve,
  })

  if (!response.success || (response.returncode !== null && response.returncode !== 0)) {
    throw new Error(formatBashApprovalFailure(response))
  }

  if (!approve) {
    return { label: 'Command rejected.', response }
  }
  if (response.executed) {
    return { label: 'Command approved and executed.', response }
  }
  return { label: 'Command approved.', response }
}

interface BashApprovalCardProps {
  event: CopilotBashApprovalRequiredEvent
  skillId: string | null
}

export function BashApprovalCard({ event, skillId }: BashApprovalCardProps) {
  const [decisionLabel, setDecisionLabel] = useState<string | null>(null)
  const [errorLabel, setErrorLabel] = useState<string | null>(null)
  const [isResolving, setIsResolving] = useState(false)

  async function decide(approve: boolean) {
    if (!skillId || isResolving || decisionLabel) {
      return
    }

    setIsResolving(true)
    try {
      const result = await resolveBashApprovalDecision({ skillId, event, approve })
      setErrorLabel(null)
      setDecisionLabel(result.label)
      toast.success(result.label)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to resolve Bash approval.'
      setErrorLabel(message)
      toast.error(message)
    } finally {
      setIsResolving(false)
    }
  }

  const disabled = !skillId || isResolving || Boolean(decisionLabel)

  return (
    <div className="mt-2 rounded-md border border-border bg-card p-2 text-xs ring-1 ring-foreground/10 ring-inset">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5 font-medium text-foreground">
          <TerminalSquare className="size-3.5 text-primary" />
          <span>Bash held for approval</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            size="sm"
            onClick={() => void decide(true)}
            disabled={disabled}
            aria-label="Approve Bash command"
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
            aria-label="Reject Bash command"
          >
            <X data-icon="inline-start" />
            Reject
          </Button>
        </div>
      </div>
      <pre className="mt-1.5 max-h-40 overflow-auto rounded-md bg-background p-2 font-mono text-foreground">
        {event.command}
      </pre>
      <p className={`mt-1 ${errorLabel ? 'text-destructive' : 'text-muted-foreground'}`}>
        {errorLabel ?? decisionLabel ?? (event.blocked ? 'Waiting for approval.' : 'Approved.')}
      </p>
    </div>
  )
}
