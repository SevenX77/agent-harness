import type { CallbackEvent, RunMetadata } from '../api/types'
import { runOutcomeFromEvents, type TraceRunOutcome } from './trace'

export interface TraceOutcomeEntry {
  status: Exclude<TraceRunOutcome, 'running'>
  /** Wall time in seconds, or null when neither source reported one. */
  wallTimeSec: number | null
  totalTokens: number | null
  reportPath: string | null
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * The run's conclusion, as the last thing in its own trace.
 *
 * A report is this run's product, and a product belongs at the end of the
 * process that made it (decision 2026-08-09 D8) — so the trace grows one final
 * entry carrying the verdict, what it cost, and the way to the report, instead
 * of hiding the report behind a menu the reader has to know about.
 *
 * Returns null while the run is still going: there is no conclusion to state.
 *
 * The two sources are not interchangeable. `run_ended` arrives the moment the
 * engine stops and carries the verdict and wall time; the sealed metadata
 * arrives later and carries the token total and the report path. Metadata wins
 * where they overlap, so this entry and the run list quote the same numbers.
 */
export function traceOutcomeEntry(
  events: CallbackEvent[],
  metadata: RunMetadata | null | undefined,
): TraceOutcomeEntry | null {
  const streamed = runOutcomeFromEvents(events)
  const status = streamed === 'running' ? statusFromMetadata(metadata) : streamed
  if (!status) {
    return null
  }
  const endedEvent = [...events].reverse().find((event) => event.event_type === 'run_ended')
  return {
    status,
    wallTimeSec:
      finiteNumber(metadata?.metrics?.wall_time_sec)
      ?? finiteNumber(endedEvent?.wall_time_seconds),
    totalTokens: finiteNumber(metadata?.metrics?.total_tokens),
    reportPath: metadata?.report_path ?? null,
  }
}

/**
 * A replayed run has no `run_ended` in view when the reader filtered it away,
 * and a run sealed by the backend after a crash may never have emitted one at
 * all — its record still states how it ended.
 */
function statusFromMetadata(
  metadata: RunMetadata | null | undefined,
): TraceOutcomeEntry['status'] | null {
  switch (metadata?.status) {
    case 'success':
      return 'success'
    case 'failed':
      return 'failed'
    case 'cancelled':
      return 'interrupted'
    default:
      return null
  }
}
