interface EventTypeBadgeProps {
  eventType: string
}

function badgeClass(eventType: string): string {
  if (eventType === 'internal_error' || eventType === 'validation_fail') {
    return 'border-destructive-border bg-destructive/10 text-destructive'
  }
  if (eventType === 'llm_fallback') {
    return 'border-warning-border bg-warning/10 text-warning'
  }
  if (eventType === 'llm_call' || eventType === 'prompt_captured') {
    return 'border-primary/50 bg-primary/10 text-foreground'
  }
  if (eventType.includes('tool')) {
    return 'border-success-border bg-success/10 text-success'
  }
  if (eventType === 'phase_start') {
    return 'border-multimodal-border bg-multimodal-border/10 text-foreground'
  }
  if (eventType === 'phase_end' || eventType === 'run_ended') {
    return 'border-success-border bg-success/10 text-success-foreground'
  }
  return 'border-border bg-muted/30 text-muted-foreground'
}

export function EventTypeBadge({ eventType }: EventTypeBadgeProps) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${badgeClass(eventType)}`}>
      {eventType}
    </span>
  )
}
