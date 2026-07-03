import React from 'react'
import { CheckCircle2, CircleAlert, Loader2, TerminalSquare, Wrench } from 'lucide-react'
import type { CopilotToolUseResultEvent, CopilotToolUseStartEvent } from '../../types/copilot'

type ToolCallEvent = CopilotToolUseStartEvent | CopilotToolUseResultEvent

interface ToolCallBubbleProps {
  event: ToolCallEvent
  /** R7-A: the spinner only animates while the turn is still streaming — a
   * settled turn folds the whole process away, so a lingering spinner (the old
   * bug: 中间过程完成后 loading 圈继续转) must never survive the turn. */
  streaming?: boolean
}

// F1: each tool call folds under a semantic verb (read=Explored / write=Worked /
// Bash=Ran), collapsed by default — visual fold only, never omitted.
const toolVerbs: Record<string, { running: string; done: string }> = {
  Read: { running: 'Exploring', done: 'Explored' },
  Glob: { running: 'Exploring', done: 'Explored' },
  Grep: { running: 'Exploring', done: 'Explored' },
  Write: { running: 'Working', done: 'Worked' },
  Edit: { running: 'Working', done: 'Worked' },
  Bash: { running: 'Running', done: 'Ran' },
  Skill: { running: 'Using skill', done: 'Used skill' },
}

// studio MCP 工具（mcp__studio__<tool>）显示为 studio:<tool>。
function displayToolName(name: string): string {
  return name.startsWith('mcp__studio__') ? `studio:${name.slice('mcp__studio__'.length)}` : name
}

function toolCallLabel(event: ToolCallEvent, failed: boolean): string {
  const verbs = toolVerbs[event.tool_name]
  const name = displayToolName(event.tool_name)
  if (event.type === 'tool_use_start') {
    return verbs ? verbs.running : `Running ${name}`
  }
  if (failed) {
    return `${name} failed`
  }
  return verbs ? verbs.done : `${name} completed`
}

function ToolCallBubbleBase({ event, streaming = false }: ToolCallBubbleProps) {
  const isResult = event.type === 'tool_use_result'
  const failed = isResult && !event.success
  const label = toolCallLabel(event, failed)
  // A running tool spins only while the turn streams; a start event left behind
  // by a settled turn shows a neutral check, never a forever-spinner (R7-A).
  const pending = event.type === 'tool_use_start' && streaming

  return (
    <details
      // Failures stay open so the user sees them without a click; everything
      // else folds (click the summary to expand the full input/output).
      // R7-A: no left rule — PM「去掉对话小字前面的那根竖线」.
      open={failed}
      className={`py-0.5 text-xs ${failed ? 'text-destructive' : 'text-muted-foreground'}`}
    >
      {/* R5-D: tool activity is SECONDARY info — one shade dimmer than the
          answer text (PM: 挂载/工具调用结果都用淡一号的字); hover restores
          full contrast for affordance. Failures keep the destructive color. */}
      <summary
        className={`flex cursor-pointer items-center gap-2 font-medium transition-colors ${
          failed ? 'text-destructive' : 'text-muted-foreground hover:text-foreground'
        }`}
      >
        {pending ? (
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
    prev.event.type === next.event.type &&
    prev.streaming === next.streaming,
)
