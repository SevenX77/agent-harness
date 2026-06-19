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

export interface RetryBadge {
  /** Human-facing label, e.g. "2/3" when a limit is known or "#2" when it is not. */
  label: string
  /** Current attempt number, 1-based. */
  attempt: number
  /** Max attempts when the engine reported a limit; null otherwise. */
  limit: number | null
  /** True once this is the final allowed attempt (attempt === limit). */
  exhausted: boolean
}

/** Auto-expand a trace payload only when it is small enough to read inline (~2KB). */
export const TRACE_PAYLOAD_AUTO_EXPAND_BYTES = 2048

export interface PayloadPreview {
  /** Serialized payload, truncated to a readable head when it exceeds the limit. */
  text: string
  /** True when the full payload is larger than the auto-expand limit. */
  truncated: boolean
  /** Byte size of the full serialized payload. */
  sizeBytes: number
  /** Human-readable size, e.g. "3.9 KB". */
  sizeLabel: string
}

function numericField(value: JsonValue | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function readAttemptFields(source: Record<string, JsonValue | undefined>): { attempt: number | null; limit: number | null } {
  // attempt/max_attempts are 1-based; retry_count is 0-based attempts already spent.
  const attemptDirect = numericField(source.attempt)
  const retryCount = numericField(source.retry_count)
  const attempt = attemptDirect ?? (retryCount !== null ? retryCount + 1 : null)
  const limit = numericField(source.max_attempts) ?? numericField(source.max_retries) ?? numericField(source.retry_limit)
  return { attempt, limit }
}

export function retryBadge(event: CallbackEvent): RetryBadge | null {
  let { attempt, limit } = readAttemptFields(event)
  if (attempt === null && isJsonObject(event.metadata)) {
    ({ attempt, limit } = readAttemptFields(event.metadata))
  }
  if (attempt === null && isJsonObject(event.metrics)) {
    ({ attempt, limit } = readAttemptFields(event.metrics))
  }
  if (attempt === null) {
    return null
  }
  const label = limit !== null ? `${attempt}/${limit}` : `#${attempt}`
  return {
    label,
    attempt,
    limit,
    exhausted: limit !== null && attempt >= limit,
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  return `${(bytes / 1024).toFixed(1)} KB`
}

export function payloadPreview(event: CallbackEvent): PayloadPreview {
  const full = JSON.stringify(event, null, 2)
  const sizeBytes = full.length
  const sizeLabel = formatBytes(sizeBytes)
  if (sizeBytes <= TRACE_PAYLOAD_AUTO_EXPAND_BYTES) {
    return { text: full, truncated: false, sizeBytes, sizeLabel }
  }
  return {
    text: `${full.slice(0, TRACE_PAYLOAD_AUTO_EXPAND_BYTES)}…`,
    truncated: true,
    sizeBytes,
    sizeLabel,
  }
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
