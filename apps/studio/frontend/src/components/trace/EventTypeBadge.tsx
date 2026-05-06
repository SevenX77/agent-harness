interface EventTypeBadgeProps {
  eventType: string
}

function badgeClass(eventType: string): string {
  if (eventType === 'internal_error' || eventType === 'validation_fail') {
    return 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300'
  }
  if (eventType === 'llm_call' || eventType === 'prompt_captured') {
    return 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-900/30 dark:text-violet-300'
  }
  if (eventType.includes('tool')) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'
  }
  if (eventType === 'phase_start') {
    return 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
  }
  if (eventType === 'phase_end' || eventType === 'run_ended') {
    return 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/30 dark:text-green-300'
  }
  return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
}

export function EventTypeBadge({ eventType }: EventTypeBadgeProps) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${badgeClass(eventType)}`}>
      {eventType}
    </span>
  )
}
