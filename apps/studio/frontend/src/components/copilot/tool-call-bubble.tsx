import React from 'react'
import { CheckCircle2, CircleAlert, Loader2, TerminalSquare, Wrench } from 'lucide-react'
import type { CopilotToolUseResultEvent, CopilotToolUseStartEvent } from '../../types/copilot'

type ToolCallEvent = CopilotToolUseStartEvent | CopilotToolUseResultEvent

interface ToolCallBubbleProps {
  event: ToolCallEvent
}

// F1: each tool call folds under a semantic verb (read=Explored / write=Worked /
// Bash=Ran), collapsed by default — visual fold only, never omitted.
const toolVerbs: Record<string, { running: string; done: string }> = {
  Read: { running: 'Exploring', done: 'Explored' },
  Write: { running: 'Working', done: 'Worked' },
  Edit: { running: 'Working', done: 'Worked' },
  Bash: { running: 'Running', done: 'Ran' },
}

function toolCallLabel(event: ToolCallEvent, failed: boolean): string {
  const verbs = toolVerbs[event.tool_name]
  if (event.type === 'tool_use_start') {
    return verbs ? verbs.running : `Running ${event.tool_name}`
  }
  if (failed) {
    return `${event.tool_name} failed`
  }
  return verbs ? verbs.done : `${event.tool_name} completed`
}

function ToolCallBubbleBase({ event }: ToolCallBubbleProps) {
  const isResult = event.type === 'tool_use_result'
  const failed = isResult && !event.success
  const label = toolCallLabel(event, failed)

  return (
    <details
      // Failures stay open so the user sees them without a click; everything
      // else folds (click the summary to expand the full input/output).
      open={failed}
      className={`border-l py-1 pl-3 text-xs ${
        failed
          ? 'border-destructive/50 text-destructive'
          : 'border-border/70 text-muted-foreground'
      }`}
    >
      <summary className="flex cursor-pointer items-center gap-2 font-medium text-foreground">
        {event.type === 'tool_use_start' ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : failed ? (
          <CircleAlert className="size-3.5" />
        ) : (
          <CheckCircle2 className="size-3.5" />
        )}
        {event.tool_name === 'Bash' ? <TerminalSquare className="size-3.5" /> : <Wrench className="size-3.5" />}
        <span>{label}</span>
      </summary>
      {event.type === 'tool_use_start' ? (
        <pre className="mt-1.5 max-h-32 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2 text-[11px] leading-snug text-muted-foreground">
          {JSON.stringify(event.tool_input, null, 2)}
        </pre>
      ) : event.result_summary ? (
        <p className="mt-1.5 whitespace-pre-wrap leading-snug">
          {event.result_summary.split('\n').slice(0, 4).join('\n')}
        </p>
      ) : null}
    </details>
  )
}

export const ToolCallBubble = React.memo(
  ToolCallBubbleBase,
  (prev, next) =>
    prev.event.id === next.event.id &&
    prev.event.status === next.event.status &&
    prev.event.type === next.event.type,
)
