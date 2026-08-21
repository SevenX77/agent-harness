import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { CompareCandidateTabs } from './CompareCandidateTabs'

// Migrated from TracePanel.test.tsx when the strip moved out to the trace
// region (ledger L2 ③). The cases are unchanged — what changed is that they
// now test the component that actually owns the tabs, while the REGION-level
// mounting rule is tested in Panels.trace-mount.test.tsx. Both layers matter:
// green component tests are exactly what let the strip sit in an unreachable
// branch for a whole release cycle.
describe('CompareCandidateTabs (node-compare candidate strip)', () => {
  const tabs = [
    { candidateId: 'fast', label: 'deepseek-v4', runId: 'run-f', failed: false, running: false },
    { candidateId: 'slow', label: 'claude-opus', runId: 'run-s', failed: true, running: false },
  ]

  it('renders one tab per candidate, marking the failed candidate', () => {
    const html = renderToStaticMarkup(<CompareCandidateTabs tabs={tabs} activeCandidateId="fast" />)

    expect(html).toContain('aria-label="Model compare candidates"')
    expect(html).toContain('aria-label="Candidate deepseek-v4"')
    // The failed candidate's tab carries the failure in its accessible name.
    expect(html).toContain('aria-label="Candidate claude-opus (failed)"')
    expect(html).toContain('>deepseek-v4<')
    expect(html).toContain('>claude-opus<')
  })

  it('marks the active candidate tab as selected', () => {
    const html = renderToStaticMarkup(<CompareCandidateTabs tabs={tabs} activeCandidateId="slow" />)

    const slowIdx = html.indexOf('aria-label="Candidate claude-opus (failed)"')
    // aria-selected="true" lives on the active tab's button (same element as the label).
    expect(html.slice(slowIdx - 120, slowIdx)).toContain('aria-selected="true"')
    const fastIdx = html.indexOf('aria-label="Candidate deepseek-v4"')
    expect(html.slice(fastIdx - 120, fastIdx)).toContain('aria-selected="false"')
  })

  it('renders nothing when no compare group exists', () => {
    expect(renderToStaticMarkup(<CompareCandidateTabs />)).toBe('')
    expect(renderToStaticMarkup(<CompareCandidateTabs tabs={[]} />)).toBe('')
  })
})
