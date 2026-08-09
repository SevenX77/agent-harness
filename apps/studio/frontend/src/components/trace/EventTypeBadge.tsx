import type { TraceSeverity } from '../../utils/trace'

interface EventTypeBadgeProps {
  eventType: string
  severity: TraceSeverity
}

/**
 * The event's kind, as text.
 *
 * Kind is a taxonomy, and taxonomies are carried by words, not colour
 * (FRONTEND_UI_SPEC §2.2). Only events that mean something went wrong get a
 * coloured pill; everything else is mono text, so a healthy run reads
 * monochrome and a defect stands out on sight. Severity arrives decided —
 * `eventSeverity` owns that judgement, because one event type
 * (`llm_route_decision`) spans both the healthy and the fatal outcome.
 */
function severityPill(severity: TraceSeverity): string | null {
  if (severity === 'error') {
    return 'rounded-full border border-destructive-border bg-destructive/10 px-2 py-0.5 text-destructive'
  }
  if (severity === 'warning') {
    return 'rounded-full border border-warning-border bg-warning/10 px-2 py-0.5 text-warning'
  }
  return null
}

export function EventTypeBadge({ eventType, severity }: EventTypeBadgeProps) {
  const pill = severityPill(severity)
  return (
    <span className={`font-mono text-xs font-medium ${pill ?? 'text-muted-foreground'}`}>
      {eventType}
    </span>
  )
}
