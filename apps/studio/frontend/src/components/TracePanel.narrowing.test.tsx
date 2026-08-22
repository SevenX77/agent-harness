// @vitest-environment jsdom

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { EventEnvelope, RunMetadata } from '../api/types'
import { TracePanel } from './TracePanel'

/**
 * 取景 at the panel level: what the reader narrows with, and what stops being
 * shown while they are narrowing.
 *
 * These need a real client render because both behaviours are about STATE the
 * reader puts the panel into — typing, then pressing the route-issues chip —
 * and a static render can only see the state it starts in. That is exactly how
 * the defects survived: every existing case rendered the panel once, so nothing
 * ever asked what pressing the chip did to the box next to it.
 */

let sequence = 0
function envelope(payload: Record<string, unknown>): EventEnvelope {
  sequence += 1
  return {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq: sequence,
    cursor: `run:run-1:${sequence}`,
    run_id: 'run-1',
    event_type: payload.event_type as string,
    timestamp: '2026-08-21T00:00:00Z',
    payload: { schema_version: '1.0', timestamp: '2026-08-21T00:00:00Z', ...payload },
  } as EventEnvelope
}

/** One clean LLM step in `draft`, one that fell back in `review`, then the end. */
function runLogs(): EventEnvelope[] {
  sequence = 0
  return [
    envelope({ event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' }),
    envelope({
      event_type: 'llm_call',
      phase_name: 'draft',
      step_id: 's1',
      response_data: { model_name: 'deepseek-v4-flash' },
    }),
    envelope({ event_type: 'prompt_captured', phase_name: 'review', step_id: 's2' }),
    envelope({
      event_type: 'llm_route_decision',
      phase_name: 'review',
      step_id: 's2',
      decision: 'fell_back',
      route_id: 'ark-official:glm-5',
      next_route_id: 'qiniu:glm-5',
      reason: 'endpoint timed out',
    }),
    envelope({ event_type: 'llm_call', phase_name: 'review', step_id: 's2' }),
    envelope({ event_type: 'run_ended', phase_name: 'review', wall_time_seconds: 12 }),
  ]
}

const metadata: RunMetadata = {
  run_id: 'run-1',
  status: 'success',
  started_at: '2026-08-21T00:00:00Z',
  kind: 'run',
  metrics: { wall_time_sec: 12, total_tokens: 2076 },
  input_summary: null,
} as RunMetadata

describe('TracePanel 取景 (ledger T8)', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    // React only lets `act` drive updates when the environment says so.
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  function render() {
    act(() => {
      root.render(<TracePanel traceLogs={runLogs()} runId="run-1" metadata={metadata} />)
    })
  }

  const searchBox = () => container.querySelector<HTMLInputElement>('input[type="search"], input')
  const routeChip = () => Array.from(container.querySelectorAll('button'))
    .find((button) => /route issue/i.test(button.textContent ?? ''))
  const stepCount = () => Number(
    container.querySelector('[data-trace-step-count]')?.getAttribute('data-trace-step-count'),
  )
  const outcomeShown = () => container.querySelector('[data-trace-outcome]') !== null
  const matchCountLabel = () =>
    container.querySelector('[data-trace-match-count]')?.getAttribute('data-trace-match-count') ?? null

  function type(value: string) {
    const input = searchBox()
    if (!input) throw new Error('no search box')
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
    act(() => {
      setter?.call(input, value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
  }

  it('pressing the route-issues chip leaves what the reader typed alone', () => {
    // It used to narrow by WRITING `llm_route_decision` into this box, so the
    // reader's own words were destroyed by a button that never mentioned them —
    // and pressing it again cleared a box they had not asked to clear.
    render()
    type('deepseek')
    expect(searchBox()?.value).toBe('deepseek')

    const chip = routeChip()
    expect(chip).toBeDefined()
    act(() => { chip?.click() })

    expect(searchBox()?.value).toBe('deepseek')
    expect(chip?.getAttribute('aria-pressed')).toBe('true')
  })

  it('the chip reveals exactly the steps it counted', () => {
    // The count is degradations (`decision !== "answered"`). It used to reveal
    // every route decision, which is a different set — a count that does not
    // match what clicking shows is a promise the list cannot keep (F3).
    render()
    // Two LLM steps plus the run's own end event.
    expect(stepCount()).toBe(3)

    act(() => { routeChip()?.click() })

    expect(stepCount()).toBe(1)
  })

  it('a narrowed list does not carry the run’s verdict', () => {
    // The outcome row says how the RUN ended. Under a narrowing the list is not
    // the run, so the verdict would read as a judgement about the few steps
    // above it (PM 08-19 Q5, and 搜索与筛选是用户主动的取景).
    render()
    expect(outcomeShown()).toBe(true)

    type('deepseek')
    expect(outcomeShown()).toBe(false)

    type('')
    expect(outcomeShown()).toBe(true)
  })

  // Ledger T8's remaining item: 取景 has to be readable, not just correct.
  // A narrowed list answers "these rows are left" but not "why this row" or
  // "how much did I just hide" — and both answers are already in hand at the
  // moment the narrowing runs.
  it('marks the term inside the rows it kept', () => {
    render()
    type('deepseek')

    const marks = Array.from(container.querySelectorAll('mark'))
    expect(marks.length).toBeGreaterThan(0)
    for (const mark of marks) {
      expect(mark.textContent?.toLowerCase()).toBe('deepseek')
    }
  })

  it('leaves no mark behind once the search is cleared', () => {
    render()
    type('deepseek')
    expect(container.querySelector('mark')).not.toBeNull()

    type('')

    expect(container.querySelector('mark')).toBeNull()
  })

  it('says how many steps are left, and that is the number of steps it is showing', () => {
    // The count describes THIS list, so it is read off the same array the list
    // renders — not computed a second time. F3's 2026-08-20 rule: a count that
    // cannot be found by looking is worse than no count.
    render()
    expect(matchCountLabel()).toBeNull()

    type('deepseek')

    expect(matchCountLabel()).toBe(String(stepCount()))
  })

  it('reports zero rather than going silent when nothing matched', () => {
    render()
    type('nothing matches this')

    expect(stepCount()).toBe(0)
    expect(matchCountLabel()).toBe('0')
  })

  it('a hit in the closing half brings its opening half with it', () => {
    // Event-level filtering left the answer without the prompt that asked for
    // it. The model name lives only on the closing `llm_call`.
    render()
    type('deepseek-v4-flash')

    expect(stepCount()).toBe(1)
    // Whole step: the row is the prompt's row, and it is the one that carries
    // the answer — not a lone completion.
    expect(container.querySelector('[data-trace-step-count="1"]')).not.toBeNull()
  })
})
