// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it } from 'vitest'
import { TextWell } from './text-well'

// React 19's act() warns unless the environment opts in.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

/** jsdom does no layout, so overflow is simulated through prototype getters. */
function mockScrollMetrics(scrollHeight: number, clientHeight: number) {
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
    configurable: true,
    get: () => scrollHeight,
  })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get: () => clientHeight,
  })
}

afterEach(() => {
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).scrollHeight
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientHeight
})

function mount(element: React.ReactElement) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(element)
  })
  return {
    container,
    unmount: () => {
      act(() => {
        root.unmount()
      })
      container.remove()
    },
  }
}

describe('TextWell (decision 2026-08-14: fixed-height well, no line folding)', () => {
  it('renders the FULL text — clipping is the CSS scroll cap, never slicing', () => {
    const long = Array.from({ length: 200 }, (_, i) => `line-${i}`).join('\n')
    const html = renderToStaticMarkup(<TextWell text={long} />)

    expect(html).toContain('data-slot="text-well"')
    expect(html).toContain('line-0')
    expect(html).toContain('line-199')
    expect(html).not.toContain('Expand (')
  })

  it('keeps the overflow action hidden while the text fits inside the well', () => {
    mockScrollMetrics(50, 50)
    const { container, unmount } = mount(
      <TextWell text="short" overflowAction={<button type="button">View full text</button>} />,
    )

    expect(container.textContent).not.toContain('View full text')
    unmount()
  })

  it('reveals the overflow action once the text overflows the well', () => {
    mockScrollMetrics(400, 160)
    const { container, unmount } = mount(
      <TextWell text="long" overflowAction={<button type="button">View full text</button>} />,
    )

    expect(container.textContent).toContain('View full text')
    unmount()
  })

  it('follows the newest lines while streaming (autoFollow pins scrollTop to the bottom)', () => {
    mockScrollMetrics(400, 160)
    const { container, unmount } = mount(<TextWell text="streaming" autoFollow />)

    const pre = container.querySelector('[data-slot="text-well"]') as HTMLPreElement
    expect(pre.scrollTop).toBe(400)
    unmount()
  })
})
