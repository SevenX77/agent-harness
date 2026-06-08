import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { SubgraphInline } from './SubgraphInline'

// MVP1 (Studio D7 + graph-authoring F4): a subgraph node references a child graph by local path.
// When the path resolves, the inline view must show the REAL child graph, not placeholder rows.
// When the path is missing, it must surface a workspace/assets recovery entry.
type SubgraphInlineProps = Parameters<typeof SubgraphInline>[0] & {
  childGraph?: unknown
}

describe('SubgraphInline (MVP1 subgraph by path)', () => {
  it('does not render hardcoded mock entry/execute/return rows in place of the child graph', () => {
    const html = renderToStaticMarkup(
      <SubgraphInline path="./subskills/review" parentLabel="review" />,
    )

    expect(html).not.toContain('>entry<')
    expect(html).not.toContain('>execute<')
    expect(html).not.toContain('>return<')
  })

  it('shows a workspace/assets recovery affordance when the child path does not resolve', () => {
    const props = {
      path: './missing/child',
      parentLabel: 'review',
      childGraph: null,
    } as unknown as SubgraphInlineProps
    const html = renderToStaticMarkup(<SubgraphInline {...props} />)

    expect(html).toMatch(/not found|recover|add to workspace|assets/i)
  })
})
