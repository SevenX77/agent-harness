import React from 'react'
import { CheckCircle2, CircleAlert, Loader2, TerminalSquare, Wrench } from 'lucide-react'
import type { CopilotToolUseResultEvent, CopilotToolUseStartEvent } from '../../types/copilot'

type ToolCallEvent = CopilotToolUseStartEvent | CopilotToolUseResultEvent

interface ToolCallBubbleProps {
  event: ToolCallEvent
}

const toolLabels: Record<string, string> = {
  Read: '正在 Read',
  Write: '正在 Write',
  Edit: '正在 Edit',
  Bash: '正在 Bash',
}

function ToolCallBubbleBase({ event }: ToolCallBubbleProps) {
  const isResult = event.type === 'tool_use_result'
  const failed = isResult && !event.success
  const label = isResult ? `${event.tool_name} ${event.success ? '完成' : '失败'}` : (toolLabels[event.tool_name] ?? `正在 ${event.tool_name}`)

  return (
    <div
      className={`mt-2 rounded-md border p-2 text-xs ${
        failed ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-border bg-muted/45 text-muted-foreground'
      }`}
    >
      <div className="flex items-center gap-2 font-medium text-foreground">
        {event.type === 'tool_use_start' ? <Loader2 className="size-3.5 animate-spin" /> : failed ? <CircleAlert className="size-3.5" /> : <CheckCircle2 className="size-3.5" />}
        {event.tool_name === 'Bash' ? <TerminalSquare className="size-3.5" /> : <Wrench className="size-3.5" />}
        <span>{label}</span>
      </div>
      {event.type === 'tool_use_start' ? (
        <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-background/70 p-2 text-[11px] text-muted-foreground">
          {JSON.stringify(event.tool_input, null, 2)}
        </pre>
      ) : event.result_summary ? (
        <p className="mt-2 whitespace-pre-wrap leading-relaxed">{event.result_summary.split('\n').slice(0, 4).join('\n')}</p>
      ) : null}
    </div>
  )
}

export const ToolCallBubble = React.memo(
  ToolCallBubbleBase,
  (prev, next) =>
    prev.event.id === next.event.id &&
    prev.event.status === next.event.status &&
    prev.event.type === next.event.type,
)
