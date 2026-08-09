import { describe, expect, it } from 'vitest'
import type { CallbackEvent, RunMetadata } from '../api/types'
import { traceOutcomeEntry } from './trace-outcome'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return { schema_version: '1.0', timestamp: '2026-08-09T00:00:00Z', ...partial } as CallbackEvent
}

function metadata(partial: Partial<RunMetadata> = {}): RunMetadata {
  return {
    run_id: '2026-08-09T10-15-00_abcd1234',
    status: 'success',
    started_at: '2026-08-09T10:15:00Z',
    metrics: {
      input_tokens: 120,
      output_tokens: 80,
      total_tokens: 200,
      cost_estimate: null,
      wall_time_sec: 12.5,
    },
    input_summary: null,
    ...partial,
  }
}

// D8 (decision 2026-08-09): "运行结束后,Trace 末尾自然长出一条终结条目
// (结论 / 耗时 / token / 报告链接)。报告是这次运行的产物,产物出现在过程末尾。"
describe('traceOutcomeEntry', () => {
  it('says nothing while the run is still going', () => {
    const events = [event({ event_type: 'phase_start', phase_name: 'draft' })]

    expect(traceOutcomeEntry(events, null)).toBeNull()
  })

  it('states the verdict as soon as the stream ends, before the run is sealed', () => {
    const events = [event({ event_type: 'run_ended', status: 'completed', wall_time_seconds: 8.25 })]

    const entry = traceOutcomeEntry(events, null)

    expect(entry?.status).toBe('success')
    expect(entry?.wallTimeSec).toBe(8.25)
    // Not sealed yet: no token total and no report, and it must not invent either.
    expect(entry?.totalTokens).toBeNull()
    expect(entry?.reportPath).toBeNull()
  })

  it('quotes the sealed numbers once metadata exists, so the trace and the list agree', () => {
    const events = [event({ event_type: 'run_ended', status: 'completed', wall_time_seconds: 8.25 })]

    const entry = traceOutcomeEntry(events, metadata({ report_path: '/skills/demo/report.md' }))

    expect(entry?.wallTimeSec).toBe(12.5)
    expect(entry?.totalTokens).toBe(200)
    expect(entry?.reportPath).toBe('/skills/demo/report.md')
  })

  it('reports a crashed run as failed and an interrupted one as interrupted', () => {
    expect(
      traceOutcomeEntry([event({ event_type: 'run_ended', status: 'crashed' })], null)?.status,
    ).toBe('failed')
    expect(
      traceOutcomeEntry([event({ event_type: 'run_ended', status: 'interrupted' })], null)?.status,
    ).toBe('interrupted')
  })

  it('falls back to the record when the run left no run_ended in view', () => {
    // A replayed run whose terminal event the reader filtered away still ended.
    const entry = traceOutcomeEntry([], metadata({ status: 'failed' }))

    expect(entry?.status).toBe('failed')
    expect(entry?.totalTokens).toBe(200)
  })

  it('stays silent for a record that has not concluded either', () => {
    expect(traceOutcomeEntry([], metadata({ status: 'running' }))).toBeNull()
    expect(traceOutcomeEntry([], metadata({ status: 'paused' }))).toBeNull()
  })

  it('reports no duration rather than a wrong one when neither source has it', () => {
    const entry = traceOutcomeEntry([event({ event_type: 'run_ended', status: 'completed' })], null)

    expect(entry?.wallTimeSec).toBeNull()
  })
})
