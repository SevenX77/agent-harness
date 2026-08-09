import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { TraceFilterRow } from './TraceFilterRow'
import { TRACE_CATEGORIES, TRACE_CATEGORY_LABEL } from './trace-category'

function render(overrides: Partial<React.ComponentProps<typeof TraceFilterRow>> = {}): string {
  return renderToStaticMarkup(
    <TraceFilterRow
      phases={['draft', 'review']}
      selectedCategories={[]}
      selectedPhases={[]}
      onSelectCategories={() => undefined}
      onSelectPhases={() => undefined}
      {...overrides}
    />,
  )
}

describe('TraceFilterRow (decision 2026-08-09 D11)', () => {
  it('offers every event kind and every node as a tag', () => {
    const html = render()

    for (const category of TRACE_CATEGORIES) {
      expect(html).toContain(TRACE_CATEGORY_LABEL[category])
    }
    expect(html).toContain('>draft<')
    expect(html).toContain('>review<')
  })

  it('says which tags are on, so a collapsed row can be reopened onto the same state', () => {
    const html = render({ selectedCategories: ['llm'], selectedPhases: ['review'] })

    expect(html).toMatch(/aria-pressed="true"[^>]*>[^<]*review/)
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(2)
  })

  it('keeps the tags on ONE line and scrolls them sideways when they do not fit', () => {
    // The row sits between the search box and the events; letting it wrap means
    // a run with many nodes pushes the trace itself off screen.
    const html = render({ phases: Array.from({ length: 30 }, (_, index) => `node-${index}`) })

    expect(html).toContain('overflow-x-auto')
    expect(html).toContain('flex-nowrap')
    expect(html).not.toContain('flex-wrap')
  })

  it('is out of reach until it is open, so a hidden row cannot be tabbed into', () => {
    const html = render()

    expect(html).toContain('invisible')
    expect(html).toContain('group-focus-within/trace-search:visible')
  })
})
