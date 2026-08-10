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

/**
 * The bucket for events that belong to the run itself rather than to any node
 * (`run_started`, `run_ended`). They used to fall back to the run id, which put
 * a 40-character identifier where a node name goes — a filter chip, a document
 * heading, and a prefix on every such row.
 */
export const RUN_SCOPE = 'run'

/**
 * Which node an event belongs to.
 *
 * Most events name their node in `phase_name`. Edge events (`input_dispatch`,
 * `blackboard_reduce`) instead describe what arrives at `to_phase`, so that is
 * the node they belong to. Anything left over is the run itself.
 */
export function eventPhase(event: CallbackEvent): string {
  const phase = event.phase_name ?? event.current_phase ?? event.to_phase
  return typeof phase === 'string' && phase !== '' ? phase : RUN_SCOPE
}

export function isRunScopedEvent(event: CallbackEvent): boolean {
  return eventPhase(event) === RUN_SCOPE
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
      // A role resolves through a fallback chain, so which model answered is a
      // per-call fact — name it on the line that reports the call.
      return typeof event.resolved_model === 'string' && event.resolved_model !== ''
        ? `LLM call completed · ${event.resolved_model}`
        : 'LLM call completed'
    case 'finish_task':
      return typeof event.reasoning === 'string' ? event.reasoning : 'Task finished'
    case 'run_ended':
      return `Run ended: ${event.status ?? 'completed'}`
    case 'internal_error':
      return typeof event.error_message === 'string' ? event.error_message : 'Internal error'
    case 'llm_route_decision': {
      const details = routeDecisionDetails(event)
      return details ? routeDecisionMessage(details) : event.event_type
    }
    case 'llm_call_settings': {
      const details = callSettingsDetails(event)
      return details ? callSettingsMessage(details) : event.event_type
    }
    case 'model_resolved':
      return typeof event.resolved_model === 'string' && event.resolved_model !== ''
        ? `Model resolved: ${event.resolved_model}`
        : 'Model resolved'
    default:
      return event.event_type
  }
}

/**
 * True when the row's message would only repeat the event type back.
 *
 * `eventMessage` falls through to `event.event_type` for every kind it has no
 * sentence for (`input_dispatch`, `agent_loop_iteration`, `run_started`, …), so
 * the row would print the same token twice — once as the kind, once as the
 * message. Rows drop the second line in that case.
 */
export function eventMessageIsRedundant(event: CallbackEvent): boolean {
  return eventMessage(event) === event.event_type
}

export type TraceSeverity = 'error' | 'warning' | 'normal'

/**
 * How much of the reader's attention an event has earned.
 *
 * This used to be a function of the event TYPE, which worked while every type
 * meant exactly one thing. `llm_route_decision` broke that: the same type
 * reports the route that answered (nothing to see) and the route that ran out
 * of candidates (the run's cause of death). Severity therefore reads the
 * event, and both surfaces that colour by severity — the rail dot and the kind
 * pill — ask this one function rather than each keeping a list of types.
 */
export function eventSeverity(event: CallbackEvent): TraceSeverity {
  if (event.event_type === 'internal_error' || event.event_type === 'validation_fail') {
    return 'error'
  }
  const settings = callSettingsDetails(event)
  if (settings !== null) {
    return settingsCarryWarning(settings.settings) ? 'warning' : 'normal'
  }
  const decision = routeDecisionDetails(event)?.decision
  if (decision === undefined || decision === 'answered') {
    return 'normal'
  }
  return decision === 'failed_terminal' || decision === 'exhausted' ? 'error' : 'warning'
}

/**
 * Colour on the timeline rail encodes SEVERITY, never the kind of event
 * (FRONTEND_UI_SPEC §2.2). A run that went fine has a monochrome rail, so the
 * one dot that is coloured is the one worth looking at.
 */
export function eventColor(event: CallbackEvent): string {
  switch (eventSeverity(event)) {
    case 'error':
      return 'bg-destructive'
    case 'warning':
      return 'bg-warning'
    default:
      return 'bg-muted-foreground/50'
  }
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
  return 'border-primary/50 bg-primary/10 text-foreground'
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

// ── Gateway routing visibility (trace-observability F7) ─────────────────────
// The gateway emits `llm_route_decision` (graph_agent_gateway/events.py, code
// [F-v3-gateway-llm-route-decision]) for every candidate it skips because the
// circuit is open, probes, retries, escalates the budget on, falls back from,
// answers on, or runs out of. Only the fall-back used to reach anyone; the rest
// happened in silence, so a call that took two minutes and answered from the
// second-choice endpoint just looked slow.
//
// They are one fact with different outcomes, so `decision` is a closed set on
// one event rather than a family of event types. Surfacing it also keeps a
// model comparison honest: without it a run can silently return "model A"
// results that model B actually produced.

export const ROUTE_DECISIONS = [
  'skipped_circuit_open',
  'probe_failed',
  'retried_same_route',
  'dropped_rejected_settings',
  'escalated_budget',
  'fell_back',
  'failed_terminal',
  'answered',
  'exhausted',
] as const

export type RouteDecision = (typeof ROUTE_DECISIONS)[number]

export interface RouteDecisionDetails {
  /** What the gateway did. */
  decision: RouteDecision
  /** The route the decision is about, e.g. "openai:gpt-4o". */
  routeId: string | null
  /** Endpoint behind that route, i.e. WHERE the call went. */
  endpointId: string | null
  /** Model id the provider was asked for. */
  providerModelId: string | null
  /** Wire protocol the endpoint speaks, e.g. "anthropic_compatible". */
  protocol: string | null
  /** Route taking over; set only when falling back. */
  nextRouteId: string | null
  /** Failure reason, e.g. "RateLimitError: 429 too many requests". */
  reason: string
  /** Provider HTTP status when the failure was classified, e.g. 429. */
  statusCode: number | null
  /**
   * True when this decision discarded text the panel had ALREADY shown.
   * Retrying is only possible after a truncated answer streamed, so without
   * this the reader is left looking at a paragraph that no longer counts.
   */
  voidedStreamedAnswer: boolean
}

function optionalString(value: JsonValue | undefined): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

export function routeDecisionDetails(event: CallbackEvent): RouteDecisionDetails | null {
  if (event.event_type !== 'llm_route_decision') {
    return null
  }
  // An outcome this build has never heard of is not rendered as one it has:
  // the row falls back to printing the raw event rather than guessing.
  const decision = ROUTE_DECISIONS.find((known) => known === event.decision)
  if (decision === undefined) {
    return null
  }
  return {
    decision,
    routeId: optionalString(event.route_id),
    endpointId: optionalString(event.endpoint_id),
    providerModelId: optionalString(event.provider_model_id),
    protocol: optionalString(event.protocol),
    nextRouteId: optionalString(event.next_route_id),
    reason: typeof event.reason === 'string' ? event.reason : '',
    statusCode: typeof event.provider_status_code === 'number' ? event.provider_status_code : null,
    voidedStreamedAnswer: event.voided_streamed_answer === true,
  }
}

function routeLabel(details: RouteDecisionDetails): string {
  return details.routeId ?? details.endpointId ?? 'unknown route'
}

/** One sentence per outcome — the row's headline, not the full block. */
export function routeDecisionMessage(details: RouteDecisionDetails): string {
  switch (details.decision) {
    case 'answered':
      return `Answered by ${routeLabel(details)}`
    case 'skipped_circuit_open':
      return `Skipped ${routeLabel(details)} — circuit open`
    case 'probe_failed':
      return `Probe failed on ${routeLabel(details)}`
    case 'retried_same_route':
      return `Retrying ${routeLabel(details)}`
    case 'dropped_rejected_settings':
      return `${routeLabel(details)} refused the runtime settings — running without them`
    case 'escalated_budget':
      return `Answer was cut off — retrying ${routeLabel(details)} with a bigger budget`
    case 'fell_back':
      return `${routeLabel(details)} failed → ${details.nextRouteId ?? 'unknown route'}`
    case 'failed_terminal':
      return `${routeLabel(details)} failed — no fallback allowed`
    case 'exhausted':
      return 'No route left — every candidate failed'
  }
}

/**
 * How many routing decisions went the wrong way.
 *
 * `answered` is the outcome every healthy call ends on, so counting it would
 * put a permanent warning badge on every run.
 */
export function countRouteDegradations(events: CallbackEvent[]): number {
  return events.reduce((count, event) => {
    const decision = routeDecisionDetails(event)?.decision
    return decision !== undefined && decision !== 'answered' ? count + 1 : count
  }, 0)
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

/**
 * What the events themselves say about how the run ended.
 *
 * A live trace panel knows which run it follows but not whether that run is
 * still going: the stream simply stops. The run's own `run_ended` event carries
 * the verdict, so the panel reads it there instead of claiming "Live" forever
 * (decision 2026-08-08 D5).
 */
export type TraceRunOutcome = 'running' | 'success' | 'failed' | 'interrupted'

export function runOutcomeFromEvents(events: CallbackEvent[]): TraceRunOutcome {
  const ended = [...events].reverse().find((event) => event.event_type === 'run_ended')
  if (!ended) {
    return 'running'
  }
  if (ended.status === 'crashed') {
    return 'failed'
  }
  if (ended.status === 'interrupted') {
    return 'interrupted'
  }
  return 'success'
}

// The gateway emits `llm_call_settings` (graph_agent_gateway/events.py, code
// [F-v3-gateway-llm-call-settings]) once per answered call, carrying one
// verdict per setting the user actually chose. It answers a different question
// from the route decision beside it: not which route produced the answer, but
// what parameters the answer was produced under.
//
// Two verdicts exist so this cannot flatter itself. `sent` is the honest
// answer for settings whose effect nothing in the response can confirm, and
// `ignored` is reserved for when the answer contradicts the request.

export const SETTING_VERDICTS = [
  'applied',
  'sent',
  'adjusted',
  'unsupported',
  'rejected',
  'ignored',
] as const

export type SettingVerdict = (typeof SETTING_VERDICTS)[number]

/** The verdicts that mean the caller did not get what they asked for. */
const WARNING_VERDICTS: ReadonlySet<SettingVerdict> = new Set<SettingVerdict>([
  'adjusted',
  'unsupported',
  'rejected',
  'ignored',
])

export interface SettingOutcome {
  /** Registry name of the setting, e.g. "reasoning.effort". */
  setting: string
  /** The value the user asked for — not the one that was sent, once it moved. */
  requested: JsonValue
  verdict: SettingVerdict
  /** Why, when the verdict alone does not say it. */
  reason: string | null
}

export interface CallSettingsDetails {
  routeId: string | null
  providerModelId: string | null
  protocol: string | null
  settings: SettingOutcome[]
}

export function callSettingsDetails(event: CallbackEvent): CallSettingsDetails | null {
  if (event.event_type !== 'llm_call_settings') {
    return null
  }
  const raw = Array.isArray(event.settings) ? event.settings : []
  return {
    routeId: optionalString(event.route_id),
    providerModelId: optionalString(event.provider_model_id),
    protocol: optionalString(event.protocol),
    settings: raw.map(settingOutcome).filter((outcome): outcome is SettingOutcome => outcome !== null),
  }
}

function settingOutcome(raw: JsonValue): SettingOutcome | null {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return null
  }
  const record = raw as Record<string, JsonValue>
  const setting = optionalString(record.setting)
  // A verdict this build has never heard of is not rendered as one it has.
  const verdict = SETTING_VERDICTS.find((known) => known === record.verdict)
  if (setting === null || verdict === undefined) {
    return null
  }
  return {
    setting,
    requested: record.requested ?? null,
    verdict,
    reason: optionalString(record.reason),
  }
}

export function settingsCarryWarning(settings: readonly SettingOutcome[]): boolean {
  return settings.some((outcome) => WARNING_VERDICTS.has(outcome.verdict))
}

/** One line per setting: what was asked for, and what became of it. */
export function settingOutcomeMessage(outcome: SettingOutcome): string {
  const requested = outcome.requested === null ? '' : ` ${String(outcome.requested)}`
  const because = outcome.reason === null ? '' : `: ${outcome.reason}`
  return `${outcome.setting}${requested} — ${outcome.verdict}${because}`
}

/** The row's headline: how many settings were judged, and whether any moved. */
export function callSettingsMessage(details: CallSettingsDetails): string {
  const count = details.settings.length
  const noun = count === 1 ? 'setting' : 'settings'
  if (!settingsCarryWarning(details.settings)) {
    return `${count} ${noun} sent as asked`
  }
  const moved = details.settings.filter((outcome) => WARNING_VERDICTS.has(outcome.verdict)).length
  return `${moved} of ${count} ${noun} did not run as asked`
}
