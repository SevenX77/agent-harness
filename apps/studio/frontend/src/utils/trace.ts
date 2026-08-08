import type { CallbackEvent, JsonObject, JsonValue, MockedSource } from '../api/types'

export function jsonText(value: JsonValue | undefined): string {
  if (value === undefined) {
    return ''
  }
  return JSON.stringify(value, null, 2)
}

/**
 * Wall-clock time of one trace event, local HH:MM:SS. A timeline without time
 * is only an ordering (design analogy: LangSmith 式竖向时间轴), so every row
 * carries its moment; null when the event has no parseable timestamp.
 */
export function eventTimeLabel(event: CallbackEvent): string | null {
  const raw = (event as { timestamp?: unknown }).timestamp
  if (typeof raw !== 'string') return null
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return null
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
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
    case 'llm_fallback': {
      const details = llmFallbackDetails(event)
      if (!details) {
        return event.event_type
      }
      return details.exhausted
        ? `LLM fallback: ${details.fromProvider} failed — no remaining route`
        : `LLM fallback: ${details.fromProvider} → ${details.toProvider ?? 'unknown'}`
    }
    case 'model_resolved':
      return typeof event.resolved_model === 'string' && event.resolved_model !== ''
        ? `Model resolved: ${event.resolved_model}`
        : 'Model resolved'
    default:
      return event.event_type
  }
}

export function eventColor(eventType: string): string {
  if (eventType === 'predict_chain_start') {
    return 'bg-warning'
  }
  if (eventType === 'phase_start') {
    return 'bg-multimodal-border'
  }
  if (eventType === 'phase_end' || eventType === 'run_ended') {
    return 'bg-success'
  }
  if (eventType === 'llm_call' || eventType === 'prompt_captured') {
    return 'bg-primary'
  }
  if (eventType === 'internal_error' || eventType === 'validation_fail') {
    return 'bg-destructive'
  }
  if (eventType === 'llm_fallback') {
    return 'bg-warning'
  }
  return 'bg-muted-foreground'
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
    return 'border-warning-border bg-warning/10 text-warning'
  }
  if (source === 'copilot') {
    return 'border-multimodal-border bg-multimodal-border/10 text-foreground'
  }
  if (source === 'manual') {
    return 'border-success-border bg-success/10 text-success'
  }
  return 'border-primary/50 bg-primary/10 text-primary'
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

// ── Agent tool-call folding (D1/P2, n4-trace #16) ───────────────────────────
// The engine emits a `tool_call` event (packages/graph-agent .../events.py
// ToolCallEvent: tool_name / args / result / duration_ms) for every tool an
// agent phase invokes. Instead of dumping it as raw JSON, the trace row folds
// it under a semantic verb the same way copilot/tool-call-bubble.tsx does
// (Read → Explored, Write/Edit → Worked, Bash → Ran), so the agent's actions
// read like an agent IDE rather than a JSON blob.

const TOOL_CALL_VERBS: Record<string, string> = {
  Read: 'Explored',
  Glob: 'Explored',
  Grep: 'Explored',
  LS: 'Explored',
  Write: 'Worked',
  Edit: 'Worked',
  MultiEdit: 'Worked',
  Bash: 'Ran',
}

export interface ToolCallSummary {
  /** Semantic verb for the tool (Explored / Worked / Ran) or a fallback. */
  verb: string
  /** The raw tool name, e.g. "Read". */
  toolName: string
  /** One-line headline, e.g. "Explored · Read". */
  headline: string
  /** Serialized args (tool input), empty string when there are none. */
  args: string
  /** Result / output text, trimmed to the leading lines for the summary. */
  resultSummary: string
  /** Optional duration label, e.g. "120 ms". */
  durationLabel: string | null
}

function isToolCallEvent(event: CallbackEvent): boolean {
  return event.event_type === 'tool_call' && typeof event.tool_name === 'string'
}

function summariseResult(value: JsonValue | undefined): string {
  if (typeof value !== 'string') {
    return ''
  }
  const lines = value.split('\n')
  if (lines.length <= 4) {
    return value.trim()
  }
  return `${lines.slice(0, 4).join('\n').trim()}\n…`
}

/**
 * Build a classified, foldable summary for an agent `tool_call` event.
 *
 * Returns null for any event that is not a tool_call, so callers can fall back
 * to the generic payload renderer.
 */
export function toolCallSummary(event: CallbackEvent): ToolCallSummary | null {
  if (!isToolCallEvent(event)) {
    return null
  }
  const toolName = String(event.tool_name)
  const verb = TOOL_CALL_VERBS[toolName] ?? 'Called'
  const args = isJsonObject(event.args) && Object.keys(event.args).length > 0 ? JSON.stringify(event.args, null, 2) : ''
  const durationLabel = typeof event.duration_ms === 'number' && Number.isFinite(event.duration_ms)
    ? `${Math.round(event.duration_ms)} ms`
    : null
  return {
    verb,
    toolName,
    headline: `${verb} · ${toolName}`,
    args,
    resultSummary: summariseResult(event.result),
    durationLabel,
  }
}

// ── Retry-exhausted Error Stack (D10, n4-trace #25) ─────────────────────────
// When retries run out, the engine's retry_exhausted event carries
// `final_errors: list[str]` (each prior attempt's failure reason); a
// validation_fail carries `errors: list[str]` for that single attempt. The row
// surfaces these as an explicit, expandable Error Stack so the user sees *why*
// each attempt failed rather than just a red light.

function stringList(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
}

/**
 * Collect the per-attempt failure reasons carried by a retry_exhausted /
 * validation_fail event. Returns an empty array when the event is neither, or
 * carries no error list.
 */
export function errorStack(event: CallbackEvent): string[] {
  if (event.event_type === 'retry_exhausted') {
    return stringList(event.final_errors)
  }
  if (event.event_type === 'validation_fail') {
    return stringList(event.errors)
  }
  return []
}

// ── LLM fallback visibility (trace-observability F7) ────────────────────────
// The gateway emits `llm_fallback` (graph_agent_gateway/events.py, code
// [F-v3-gateway-llm-fallback]) when a provider route fails and the next
// candidate takes over; `context.from_route` / `to_route` carry the route
// diagnostics (provider_model_id / canonical_id). Surfacing it keeps a model
// comparison honest: without it a run can silently return "model A" results
// that model B actually produced.

export interface LlmFallbackDetails {
  /** Route id the call was leaving, e.g. "openai:gpt-4o". */
  fromProvider: string
  /** Route id that took over; null when the chain is exhausted. */
  toProvider: string | null
  /** True when the gateway reported no remaining candidate ("<none>"). */
  exhausted: boolean
  /** Model id behind the failing route, when the event carries diagnostics. */
  fromModel: string | null
  /** Model id behind the takeover route. */
  toModel: string | null
  /** Failure reason, e.g. "RateLimitError: 429 too many requests". */
  reason: string
  /** LLM role whose chain fell back, e.g. "graph_agent". */
  roleName: string | null
  /** Provider HTTP status when the failure was classified, e.g. 429. */
  statusCode: number | null
}

function routeModelId(route: JsonValue | undefined): string | null {
  if (!isJsonObject(route)) {
    return null
  }
  const model = route.provider_model_id ?? route.canonical_id
  return typeof model === 'string' && model !== '' ? model : null
}

export function llmFallbackDetails(event: CallbackEvent): LlmFallbackDetails | null {
  if (event.event_type !== 'llm_fallback') {
    return null
  }
  const context = isJsonObject(event.context) ? event.context : {}
  const rawTo = typeof event.to_provider === 'string' ? event.to_provider : ''
  const exhausted = rawTo === '' || rawTo === '<none>'
  return {
    fromProvider: typeof event.from_provider === 'string' ? event.from_provider : 'unknown provider',
    toProvider: exhausted ? null : rawTo,
    exhausted,
    fromModel: routeModelId(context.from_route),
    toModel: routeModelId(context.to_route),
    reason: typeof event.reason === 'string' ? event.reason : '',
    roleName: typeof context.role_name === 'string' && context.role_name !== '' ? context.role_name : null,
    statusCode: typeof context.provider_status_code === 'number' ? context.provider_status_code : null,
  }
}

export function countLlmFallbacks(events: CallbackEvent[]): number {
  return events.reduce((count, event) => (event.event_type === 'llm_fallback' ? count + 1 : count), 0)
}

/**
 * The model a trace row is known to have used: `resolved_model` on
 * prompt_captured / model_resolved is the resolution-time answer, while
 * `response_data.model_name` on llm_call is the provider-reported post-call
 * answer — the one that survives a mid-call fallback.
 */
export function eventModelName(event: CallbackEvent): string | null {
  if (event.event_type === 'prompt_captured' || event.event_type === 'model_resolved') {
    return typeof event.resolved_model === 'string' && event.resolved_model !== '' ? event.resolved_model : null
  }
  if (event.event_type === 'llm_call' && isJsonObject(event.response_data)) {
    const model = event.response_data.model_name
    return typeof model === 'string' && model !== '' ? model : null
  }
  return null
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
