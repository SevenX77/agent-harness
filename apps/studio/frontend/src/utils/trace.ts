import type { CallbackEvent, JsonValue } from '../api/types'

export function jsonText(value: JsonValue | undefined): string {
  if (value === undefined) {
    return ''
  }
  return JSON.stringify(value, null, 2)
}

export function eventPhase(event: CallbackEvent): string {
  return event.phase_name ?? event.current_phase ?? event.run_id ?? 'system'
}

export function tokenText(event: CallbackEvent): string | null {
  if (typeof event.input_tokens === 'number' || typeof event.output_tokens === 'number') {
    return `${event.input_tokens ?? 0}/${event.output_tokens ?? 0}`
  }
  return null
}

export function eventMessage(event: CallbackEvent): string {
  switch (event.event_type) {
    case 'phase_start':
      return `Phase started: ${eventPhase(event)}`
    case 'phase_end':
      return `Phase finished: ${eventPhase(event)}`
    case 'prompt_captured':
      return `Prompt captured${typeof event.template_source === 'string' ? ` from ${event.template_source}` : ''}`
    case 'llm_call':
      return 'LLM call completed'
    case 'finish_task':
      return typeof event.reasoning === 'string' ? event.reasoning : 'Task finished'
    case 'run_ended':
      return `Run ended: ${event.status ?? 'completed'}`
    case 'internal_error':
      return typeof event.error_message === 'string' ? event.error_message : 'Internal error'
    default:
      return event.event_type
  }
}

export function eventColor(eventType: string): string {
  if (eventType === 'phase_start') {
    return 'bg-blue-500'
  }
  if (eventType === 'phase_end' || eventType === 'run_ended') {
    return 'bg-green-500'
  }
  if (eventType === 'llm_call' || eventType === 'prompt_captured') {
    return 'bg-violet-500'
  }
  if (eventType === 'internal_error' || eventType === 'validation_fail') {
    return 'bg-red-500'
  }
  return 'bg-slate-400'
}

export function findPromptEvent(events: CallbackEvent[], selectedIndex: number): CallbackEvent | null {
  const selected = events[selectedIndex]
  if (!selected) {
    return null
  }
  if (selected.event_type === 'prompt_captured') {
    return selected
  }

  for (let index = selectedIndex; index >= 0; index -= 1) {
    const candidate = events[index]
    if (candidate.event_type === 'prompt_captured' && eventPhase(candidate) === eventPhase(selected)) {
      return candidate
    }
  }
  return selected.event_type === 'llm_call' ? selected : null
}
