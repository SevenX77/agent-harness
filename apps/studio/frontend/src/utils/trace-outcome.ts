import type { CallbackEvent, RunMetadata } from '../api/types'
import { runVerdict, type RunVerdict } from './run-status-projection'

export interface TraceOutcomeEntry {
  /**
   * A conclusion only exists once the run can no longer continue: `running`
   * has nothing to conclude and `paused` will resume — both yield no entry.
   */
  status: Exclude<RunVerdict, 'running' | 'paused'>
  /** Wall time in seconds, or null when neither source reported one. */
  wallTimeSec: number | null
  totalTokens: number | null
  reportPath: string | null
  /** Which run this concluded, so the report can be re-rendered before it opens. */
  runId: string | null
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
 * Returns null while the run is still going or merely paused: there is no
 * conclusion to state. The verdict itself comes from run-status-projection
 * (decision 2026-08-13 D7) — the same fold of stream + sealed record every
 * other status surface quotes, so this entry cannot disagree with the badge.
 *
 * The two number sources are not interchangeable. `run_ended` arrives the
 * moment the engine stops and carries the wall time; the sealed metadata
 * arrives later and carries the token total and the report path. Metadata wins
 * where they overlap, so this entry and the run list quote the same numbers.
 */
export function traceOutcomeEntry(
  events: CallbackEvent[],
  metadata: RunMetadata | null | undefined,
): TraceOutcomeEntry | null {
  const verdict = runVerdict(events, metadata)
  if (verdict === 'running' || verdict === 'paused') {
    return null
  }
  const endedEvent = [...events].reverse().find((event) => event.event_type === 'run_ended')
  return {
    status: verdict,
    wallTimeSec:
      finiteNumber(metadata?.metrics?.wall_time_sec)
      ?? finiteNumber(endedEvent?.wall_time_seconds),
    totalTokens: finiteNumber(metadata?.metrics?.total_tokens),
    reportPath: metadata?.report_path ?? null,
    runId: metadata?.run_id ?? null,
  }
}
