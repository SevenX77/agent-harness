/**
 * The four questions a reader asks of a trace, as filter buckets.
 *
 * The filter used to list every raw `event_type` the run happened to emit, so a
 * 17-event run produced eight chips and a long run produced more — a control
 * whose size is decided by the data it filters. These buckets are fixed: they do
 * not grow with the run, and every event type falls in exactly one of them, so a
 * new engine event can never slip past the filter unseen.
 */
export const TRACE_CATEGORIES = ['errors', 'llm', 'tools', 'flow'] as const

export type TraceCategory = (typeof TRACE_CATEGORIES)[number]


/** Which bucket an event type belongs to. Unknown types are flow (the default skeleton). */
export function traceEventCategory(eventType: string): TraceCategory {
  if (eventType === 'protocol_violation') {
    return 'errors'
  }
  if (eventType === 'llm_call' || eventType === 'prompt_captured' || eventType === 'llm_route_decision') {
    return 'llm'
  }
  if (eventType.includes('tool')) {
    return 'tools'
  }
  return 'flow'
}
