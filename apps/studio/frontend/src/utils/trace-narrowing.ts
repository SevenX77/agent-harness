import type { CallbackEvent } from '../api/types'
import { traceEventCategory, type TraceCategory } from '../components/trace/trace-category'
import { routeDecisionDetails } from './trace'
import type { TraceStep } from './trace-steps'

/**
 * 取景 — what the reader has asked the trace to show less of.
 *
 * Search, the type/node tags and the route-issues chip are one act, not four:
 * `01_workflows`-level wording for it is trace-observability's own
 * (`mvp1-alignment.md:41`) — 「搜索与筛选是用户主动的取景」. They therefore share
 * one shape, one predicate, and one answer to "is anything narrowed right now",
 * which is what the outcome row and the count both read.
 */
export interface TraceNarrowing {
  searchTerm: string
  selectedCategories: TraceCategory[]
  selectedPhases: string[]
  /**
   * The route-degradation chip. Its own criterion rather than a canned search
   * term: the chip used to narrow by WRITING `llm_route_decision` into the
   * search box, which destroyed whatever the reader had typed and, on the way
   * out, cleared the box they had never asked to clear.
   */
  routeIssuesOnly: boolean
}

export const NO_NARROWING: TraceNarrowing = {
  searchTerm: '',
  selectedCategories: [],
  selectedPhases: [],
  routeIssuesOnly: false,
}

export function isNarrowingActive(narrowing: TraceNarrowing): boolean {
  return narrowing.searchTerm.trim().length > 0
    || narrowing.selectedCategories.length > 0
    || narrowing.selectedPhases.length > 0
    || narrowing.routeIssuesOnly
}

/**
 * The text of one event that a search term is matched against.
 *
 * Values, never structure. Serializing the whole event made its field NAMES
 * searchable, so `phase_name` matched every event in the run and `true` matched
 * every boolean — hits with nothing on the row to explain them. A value is
 * something the row shows or reveals when opened; a key is an implementation
 * detail of the record.
 *
 * The rendered headline arrives from the caller rather than being built here,
 * so this stays pure and language-blind while still matching the sentence the
 * reader is actually looking at (ledger K4b: search matches the translation,
 * not the English source).
 */
function eventSearchText(event: CallbackEvent, headline: string): string {
  return [event.event_type, headline, ...payloadValues(event)].join(' ').toLowerCase()
}

/** Every string and number reachable in the event, with the keys left behind. */
function payloadValues(value: unknown, depth = 0): string[] {
  // Trace payloads nest a handful of levels (response_data.usage, details.*).
  // The bound is a guard against a cyclic or pathological record, not a
  // statement about the schema.
  if (depth > 6) return []
  if (typeof value === 'string') return [value]
  if (typeof value === 'number') return [String(value)]
  if (Array.isArray(value)) return value.flatMap((item) => payloadValues(item, depth + 1))
  if (value !== null && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>)
      .flatMap((item) => payloadValues(item, depth + 1))
  }
  return []
}

/** Every event that is part of a step: its two halves and the verdicts under it. */
function stepEvents(step: TraceStep): CallbackEvent[] {
  return [
    step.start.event,
    ...(step.end ? [step.end.event] : []),
    ...step.verdicts.map((verdict) => verdict.event),
  ]
}

function stepDegradedItsRoute(step: TraceStep): boolean {
  return stepEvents(step).some((event) => {
    const decision = routeDecisionDetails(event)?.decision
    return decision !== undefined && decision !== 'answered'
  })
}

/**
 * Apply a narrowing to the step list.
 *
 * **Steps, not events** — 呈现单位 = 步骤 (trace-observability F9). Narrowing the
 * events and rebuilding afterwards splits a step in half whenever only one of
 * its halves matches, and the reader is left with an answer whose question is
 * gone. A step is kept when ANY event of it matches, so a hit always arrives
 * whole.
 *
 * Every criterion is combined with AND: each one is the reader asking for less.
 */
export function narrowTraceSteps(
  steps: TraceStep[],
  narrowing: TraceNarrowing,
  headlineOf: (event: CallbackEvent) => string,
): TraceStep[] {
  const term = narrowing.searchTerm.trim().toLowerCase()
  return steps.filter((step) => {
    const events = stepEvents(step)
    const matchesSearch = term.length === 0
      || events.some((event) => eventSearchText(event, headlineOf(event)).includes(term))
    const matchesCategory = narrowing.selectedCategories.length === 0
      || events.some((event) => narrowing.selectedCategories.includes(traceEventCategory(event.event_type)))
    const matchesPhase = narrowing.selectedPhases.length === 0
      || narrowing.selectedPhases.includes(step.phase)
    const matchesRouteIssues = !narrowing.routeIssuesOnly || stepDegradedItsRoute(step)
    return matchesSearch && matchesCategory && matchesPhase && matchesRouteIssues
  })
}
