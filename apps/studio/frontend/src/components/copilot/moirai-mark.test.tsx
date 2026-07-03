import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MoiraiMark } from './moirai-mark'

describe('MoiraiMark', () => {
  it('is decorative (aria-hidden) when it has no title', () => {
    const html = renderToStaticMarkup(<MoiraiMark className="size-4" />)
    expect(html).toContain('<svg')
    expect(html).toContain('aria-hidden="true"')
    expect(html).not.toContain('role="img"')
  })

  it('exposes an accessible name when given a title', () => {
    const html = renderToStaticMarkup(<MoiraiMark title="MoirAI" />)
    expect(html).toContain('role="img"')
    expect(html).toContain('<title>MoirAI</title>')
    expect(html).not.toContain('aria-hidden')
  })

  it('themes through currentColor, never a hardcoded palette', () => {
    const html = renderToStaticMarkup(<MoiraiMark />)
    expect(html).toContain('currentColor')
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,6}\b/)
  })

  it('draws the five stars of the Cassiopeia constellation', () => {
    const html = renderToStaticMarkup(<MoiraiMark />)
    expect(html.match(/<circle/g) ?? []).toHaveLength(5)
  })
})
