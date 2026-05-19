import React from 'react'
import type { CopilotToolUseResultEvent } from '../../types/copilot'

interface DiffBubbleProps {
  event: CopilotToolUseResultEvent
}

function extractDiff(summary: string) {
  const marker = summary.indexOf('diff --git ')
  if (marker >= 0) {
    return summary.slice(marker)
  }

  const lines = summary.split('\n')
  const start = lines.findIndex((line) => line.startsWith('--- ') || line.startsWith('+++ ') || line.startsWith('@@ '))
  return start >= 0 ? lines.slice(start).join('\n') : ''
}

function DiffBubbleBase({ event }: DiffBubbleProps) {
  const diff = extractDiff(event.result_summary)
  if (!diff) {
    return null
  }

  return (
    <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-border bg-muted/50 p-3 text-xs leading-relaxed text-foreground">
      <code>{diff}</code>
    </pre>
  )
}

export const DiffBubble = React.memo(
  DiffBubbleBase,
  (prev, next) =>
    prev.event.id === next.event.id &&
    prev.event.status === next.event.status &&
    prev.event.result_summary === next.event.result_summary,
)
