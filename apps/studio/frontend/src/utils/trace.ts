import type { CallbackEvent, JsonObject, JsonValue, MockedSource } from '../api/types'

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
    case 'predict_chain_start':
      return 'Predict trace started'
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
  if (eventType === 'predict_chain_start') {
    return 'bg-amber-500'
  }
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

export function isPredictRootEvent(event: CallbackEvent): boolean {
  if (event.event_type !== 'predict_chain_start') {
    return false
  }
  const metadata = event.metadata
  return isJsonObject(metadata) && metadata.is_predict === true
}

export function isPredictTrace(events: CallbackEvent[]): boolean {
  return events.some((event) => isPredictRootEvent(event))
}

export function eventMockedSource(event: CallbackEvent): MockedSource | null {
  if (isMockedSource(event.mocked_source)) {
    return event.mocked_source
  }
  const metrics = event.metrics
  if (isJsonObject(metrics) && isMockedSource(metrics.mocked_source)) {
    return metrics.mocked_source
  }
  const responseData = event.response_data
  if (isJsonObject(responseData) && isMockedSource(responseData.mocked_source)) {
    return responseData.mocked_source
  }
  return null
}

export function mockedSourceLabel(source: MockedSource): string {
  return source.replace('_', ' ')
}

export function mockedSourceClass(source: MockedSource): string {
  if (source === 'golden_case') {
    return 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300'
  }
  if (source === 'copilot') {
    return 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-900/20 dark:text-sky-300'
  }
  if (source === 'manual') {
    return 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300'
  }
  return 'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-900/20 dark:text-violet-300'
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

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isMockedSource(value: JsonValue | undefined): value is MockedSource {
  return (
    value === 'golden_case'
    || value === 'copilot'
    || value === 'heuristic_stub'
    || value === 'manual'
  )
}
