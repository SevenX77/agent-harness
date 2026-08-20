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

/**
 * How a transition reads: the phases it joins, in the direction it ran.
 * A transition with no upstream phases starts at the graph's input
 * boundary, which the reader knows as Input.
 */
function transitionLabel(event: CallbackEvent): string {
  const from = Array.isArray(event.from_phases) ? (event.from_phases as string[]) : []
  const to = typeof event.to_phase === 'string' ? event.to_phase : RUN_SCOPE
  return `${from.length > 0 ? from.join(' + ') : 'Input'} → ${to}`
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
    case 'edge_start':
      return `Transition started: ${transitionLabel(event)}`
    case 'edge_end':
      return `Transition finished: ${transitionLabel(event)}`
    case 'prompt_captured':
      return `Prompt captured${typeof event.template_source === 'string' ? ` from ${event.template_source}` : ''}`
    case 'llm_call':
      // A role resolves through a fallback chain, so which model answered is a
      // per-call fact — name it on the line that reports the call.
      return typeof event.resolved_model === 'string' && event.resolved_model !== ''
        ? `LLM call completed · ${event.resolved_model}`
        : 'LLM call completed'
    case 'run_ended':
      return `Run ended: ${event.status ?? 'completed'}`
    case 'llm_route_decision': {
      const details = routeDecisionDetails(event)
      return details ? routeDecisionMessage(details) : event.event_type
    }
    case 'llm_call_settings': {
      const details = callSettingsDetails(event)
      return details ? callSettingsMessage(details) : event.event_type
    }
    default:
      // The machinery-speaks contract (decision 2026-08-13 D4): every internal
      // decision event carries a full-sentence `message`. Rendering it here
      // means a NEW machinery event never degrades to its raw type name.
      return typeof event.message === 'string' && event.message !== ''
        ? event.message
        : event.event_type
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
  if (event.event_type === 'protocol_violation') {
    return 'error'
  }
  if (event.event_type === 'loop_detected') {
    return 'warning'
  }
  if (event.event_type === 'finish_task_verdict') {
    return event.verdict === 'rejected' ? 'warning' : 'normal'
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

// The ~2KB byte-threshold payload preview that used to live here was replaced
// outright by the fixed-height well primitive `ui/text-well` (decision
// 2026-08-14): long text scrolls inside one capped box, not a byte budget.

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

/**
 * The usable strings out of an engine list field. Blank and non-string entries
 * are dropped rather than rendered, so a list that carried padding does not
 * become empty bullets on screen.
 */
function stringList(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
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
 * prompt_captured is the resolution-time answer, while
 * `response_data.model_name` on llm_call is the provider-reported post-call
 * answer — the one that survives a mid-call fallback.
 */
export function eventModelName(event: CallbackEvent): string | null {
  if (event.event_type === 'prompt_captured') {
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

// ── 决议 2026-08-13 D1/D4:LLM 步骤的语义分解 + 机器自述 ─────────────────────

/**
 * The model's recorded thinking for a settled LLM step: `response_data.reasoning`
 * (decision 2026-08-13 D2 put it on disk; here it becomes a flow sub-entry).
 * Null when the model did not think, or the step has not settled.
 */
export function answerReasoning(event: CallbackEvent | undefined): string | null {
  if (!event || !isJsonObject(event.response_data)) {
    return null
  }
  const reasoning = event.response_data.reasoning
  return typeof reasoning === 'string' && reasoning !== '' ? reasoning : null
}

/** The settled answer's text content; null when empty (e.g. straight to tools). */
export function answerContent(event: CallbackEvent | undefined): string | null {
  if (!event || !isJsonObject(event.response_data)) {
    return null
  }
  const content = event.response_data.content
  return typeof content === 'string' && content !== '' ? content : null
}

/** The tool calls the answer reached for, pretty-printed; null when none. */
export function answerToolCallsText(event: CallbackEvent | undefined): string | null {
  if (!event || !isJsonObject(event.response_data)) {
    return null
  }
  const toolCalls = event.response_data.tool_calls
  return Array.isArray(toolCalls) && toolCalls.length > 0
    ? JSON.stringify(toolCalls, null, 2)
    : null
}

export interface MachineryNarration {
  /** The pipeline narration, one full sentence per stage that actually ran. */
  details: string[]
  /** Why the decision went against the submission (errors / violations). */
  problems: string[]
}

/**
 * A machinery event's structured account of itself (decision 2026-08-13 D4):
 * `details` narrates the pipeline, `errors` / `violations` carry the reasons a
 * decision went against the run. Null when the event carries neither — the
 * caller falls back to the raw payload.
 */
export function machineryNarration(event: CallbackEvent): MachineryNarration | null {
  // Two channels, and BOTH are the engine speaking. The list ones carry
  // enumerated findings (a pipeline's stages, a rejection's reasons) and only
  // two of the engine's event classes have them; the single-sentence ones are
  // what the D4 machinery contract actually asks every decision to carry.
  // Reading only the lists sent every other decision — a broken loop, a
  // swallowed tool error, a repaired history — to the raw payload fallback,
  // which is the black box D4 exists to open.
  const details = [
    ...sentenceList(event.message, event.warning, event.reason),
    ...stringList(event.details),
  ]
  const problems = [
    ...stringList(event.errors),
    ...stringList(event.violations),
    ...sentenceList(event.error),
  ]
  if (details.length === 0 && problems.length === 0) {
    return null
  }
  return { details, problems }
}

function sentenceList(...values: unknown[]): string[] {
  return values.filter((value): value is string => typeof value === 'string' && value.trim() !== '')
}

/** One message of a prompt, as the reader reads it: who spoke, and what they said. */
export interface PromptMessage {
  role: string
  text: string
}

/**
 * LangChain's message types, in the words the reader already uses. Anything
 * else keeps its own name rather than being folded into "other" — an
 * unrecognised role is still a message that was sent.
 */
const PROMPT_ROLE_LABELS: Readonly<Record<string, string>> = {
  system: 'System',
  human: 'User',
  ai: 'Assistant',
}

/**
 * The messages a call actually sent, split by who spoke.
 *
 * `resolved_prompt` is a list of `{role, content}` and the panel used to
 * `JSON.stringify` the whole list into one blob — so "what was the system
 * prompt" and "what did we actually ask" were a reading exercise over escaped
 * JSON (ledger T2). `content` is passed through raw by the engine and can be a
 * string OR a list of content blocks, so a block list is rendered as its text
 * rather than stringifying to `[object Object]`.
 */
export function promptMessages(event: CallbackEvent): PromptMessage[] {
  const entries = Array.isArray(event.resolved_prompt) ? event.resolved_prompt : []
  return entries.flatMap((entry) => {
    if (entry === null || typeof entry !== 'object') return []
    const raw = entry as Record<string, unknown>
    const role = typeof raw.role === 'string' && raw.role !== '' ? raw.role : 'unknown'
    return [{ role: PROMPT_ROLE_LABELS[role] ?? role, text: promptContentText(raw.content) }]
  })
}

function promptContentText(content: unknown): string {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map((block) => {
        if (typeof block === 'string') return block
        if (block !== null && typeof block === 'object') {
          const text = (block as Record<string, unknown>).text
          if (typeof text === 'string') return text
        }
        return jsonText(block as never)
      })
      .join('\n')
  }
  if (content === null || content === undefined) return ''
  return jsonText(content as never)
}

/** One labelled fact about a step — the numbers and names its type turns on. */
export interface EventFact {
  label: string
  value: string
}

function fact(label: string, value: unknown): EventFact | null {
  if (value === null || value === undefined) return null
  if (Array.isArray(value)) {
    const items = value.filter((item) => typeof item === 'string' || typeof item === 'number')
    return items.length === 0 ? null : { label, value: items.join(', ') }
  }
  if (typeof value === 'boolean') return { label, value: value ? 'yes' : 'no' }
  if (typeof value === 'number') return { label, value: String(value) }
  if (typeof value === 'string') return value === '' ? null : { label, value }
  return null
}

/**
 * What a step turned on, as labelled facts.
 *
 * The sentence says what happened; these say with what — the keys a transition
 * dispatched, how many messages a compaction dropped, which tool looped.
 * Before this, everything but an LLM or tool call fell through to
 * `JSON.stringify` of the whole event: the data was always there, printed in a
 * shape nobody reads.
 *
 * Long values (blackboard snapshots, contexts, payloads) are deliberately NOT
 * here — they belong in a text well, not a fact row.
 *
 * Returns NULL when this build has no reading for the type at all, which is a
 * different thing from an instance that happens to carry no values: the first
 * is a gap the reader must be told about, the second is just a quiet step.
 */
export function eventFacts(event: CallbackEvent): EventFact[] | null {
  const facts = (...candidates: (EventFact | null)[]): EventFact[] =>
    candidates.filter((candidate): candidate is EventFact => candidate !== null)
  const transition = (): EventFact | null => fact('transition', transitionLabel(event))

  switch (event.event_type) {
    case 'phase_start':
    case 'phase_end':
      return facts(fact('execution', event.phase_execution_id))
    case 'edge_start':
      return facts(transition(), fact('branch', event.branch_index))
    case 'edge_end':
      return facts(
        transition(),
        fact('changed', event.changed_keys),
        fact('operations', event.operation_count),
      )
    case 'blackboard_reduce':
      return facts(transition(), fact('reducer', event.reducer), fact('changed', event.changed_keys))
    case 'input_dispatch':
      return facts(
        transition(),
        fact('dispatched', event.dispatched_keys),
        fact('changed', event.changed_keys),
        fact('branch', event.branch_index),
      )
    case 'input_file_injected':
      return facts(transition(), fact('file', event.file_ref), fact('into', event.target_field))
    case 'run_started':
      return facts(fact('run', event.run_id), fact('resumed', event.is_resume), fact('checkpoint', event.checkpoint_id))
    case 'run_ended':
      return facts(fact('status', event.status), fact('wall time', event.wall_time_seconds))
    case 'predict_chain_start':
      return facts(fact('run', event.run_id))
    case 'agent_loop_iteration':
      return facts(fact('turn', event.iteration))
    case 'nudge':
      return facts(fact('nudge', event.nudge_count), fact('kind', event.nudge_type))
    case 'loop_detected':
      return facts(fact('tool', event.tool_name), fact('repeats', event.count))
    case 'protocol_violation':
      return facts(fact('boundary', event.boundary))
    case 'tool_error_handled':
      return facts(fact('tool', event.tool_name))
    case 'tool_history_repaired':
      return facts(fact('synthesized', event.synthesized_count), fact('dropped', event.dropped_count))
    case 'runtime_input_injected':
      return facts(fact('keys', event.keys))
    case 'working_memory_update':
      return facts(fact('length', event.content_length))
    case 'compaction':
      return facts(fact('removed', event.removed_message_count), fact('sidecar', event.content_ref))
    case 'dead_end_pruned':
      return facts(fact('pruned', event.summary))
    case 'ambiguity_logged':
      return facts(
        fact('kind', event.ambiguity_type),
        fact('question', event.question),
        fact('decision', event.decision),
        fact('refs', event.related_refs),
        fact('protocols', event.related_protocols),
      )
    case 'builtin_subagent_enter':
    case 'builtin_subagent_exit':
      return facts(fact('subagent', event.builtin_name))
    case 'builtin_subagent_fallback':
      return facts(
        fact('subagent', event.builtin_name),
        fact('because', event.fallback_reason),
        fact('instead', event.fallback_strategy),
      )
    case 'artifact_saved':
      return facts(fact('artifact', event.name), fact('path', event.path), fact('bytes', event.size_bytes))
    case 'parallel_map_group_started':
      return facts(
        fact('skill', event.skill_path),
        fact('items', event.item_count),
        fact('concurrency', event.max_concurrent),
        fact('as', event.item_as),
      )
    case 'parallel_map_group_ended':
      return facts(
        fact('succeeded', event.succeeded),
        fact('failed', event.failed),
        fact('wall time', event.wall_time_seconds),
      )
    case 'interrupted':
      return facts(
        fact('question', event.question),
        fact('options', event.options),
        fact('checkpoint', event.checkpoint_id),
      )
    case 'resumed':
      return facts(fact('from', event.resumed_from_phase), fact('answer', event.human_input))
    case 'finish_task_verdict':
      return facts(fact('verdict', event.verdict), fact('items', event.item_count))
    case 'llm_delta':
      return facts(fact('channel', event.channel))
    // These three ARE read, in full, by their own bodies (the LLM flow and the
    // tool-call subtree) — naming them here keeps "no reading" honest.
    case 'prompt_captured':
    case 'llm_call':
    case 'tool_call':
    case 'tool_call_started':
    case 'llm_route_decision':
    case 'llm_call_settings':
      return []
    default:
      return null
  }
}

const SEVERITY_RANK: Record<TraceSeverity, number> = { normal: 0, warning: 1, error: 2 }

/** The loudest of several severities — a step is as red as its worst part. */
export function maxSeverity(severities: readonly TraceSeverity[]): TraceSeverity {
  return severities.reduce<TraceSeverity>(
    (worst, current) => (SEVERITY_RANK[current] > SEVERITY_RANK[worst] ? current : worst),
    'normal',
  )
}
