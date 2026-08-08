interface EventTypeBadgeProps {
  eventType: string
}

/**
 * The event's kind, as text.
 *
 * Kind is a taxonomy, and taxonomies are carried by words, not colour
 * (FRONTEND_UI_SPEC §2.2). Only the two kinds that mean something went wrong
 * get a coloured pill; everything else is mono text, so a healthy run reads
 * monochrome and a defect stands out on sight.
 */
function severityPill(eventType: string): string | null {
  if (eventType === 'internal_error' || eventType === 'validation_fail') {
    return 'rounded-full border border-destructive-border bg-destructive/10 px-2 py-0.5 text-destructive'
  }
  if (eventType === 'llm_fallback') {
    return 'rounded-full border border-warning-border bg-warning/10 px-2 py-0.5 text-warning'
  }
  return null
}

export function EventTypeBadge({ eventType }: EventTypeBadgeProps) {
  const pill = severityPill(eventType)
  return (
    <span className={`font-mono text-xs font-medium ${pill ?? 'text-muted-foreground'}`}>
      {eventType}
    </span>
  )
}
