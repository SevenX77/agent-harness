/**
 * 折叠属于文本自己,不属于容器(决议 2026-08-13 D3)。
 *
 * 三态契约:收起 5 行(一眼识别这段是什么)→ 展开 20 行 → 全文进 Monaco
 * 只读视图。任何 trace 表面的长文本都消费这同一个原语;按字节(~2KB)折叠的
 * 旧机制被本原语按行的三态取代。
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import {
  FOLDED_TEXT_COLLAPSED_LINES,
  FOLDED_TEXT_EXPANDED_LINES,
  FoldedText,
  foldPlan,
} from './folded-text'

const numberedLines = (count: number): string =>
  Array.from({ length: count }, (_, i) => `line-${i + 1}`).join('\n')

describe('foldPlan', () => {
  it('short text is not foldable at all', () => {
    const plan = foldPlan(numberedLines(FOLDED_TEXT_COLLAPSED_LINES))
    expect(plan.foldable).toBe(false)
    expect(plan.overflowsExpanded).toBe(false)
  })

  it('folding starts once it would hide at least two lines; past 20 lines the full view is offered', () => {
    // Hiding one line trades a click for nothing, so 6 lines still render whole.
    expect(foldPlan(numberedLines(6)).foldable).toBe(false)
    expect(foldPlan(numberedLines(7)).foldable).toBe(true)
    expect(foldPlan(numberedLines(7)).overflowsExpanded).toBe(false)
    expect(foldPlan(numberedLines(FOLDED_TEXT_EXPANDED_LINES + 1)).overflowsExpanded).toBe(true)
  })

  it('a single monster line still folds — display lines, not source lines', () => {
    const plan = foldPlan('z'.repeat(4000))
    expect(plan.foldable).toBe(true)
    expect(plan.overflowsExpanded).toBe(true)
  })
})

describe('FoldedText', () => {
  it('renders short text whole, with no fold controls', () => {
    const html = renderToStaticMarkup(<FoldedText text={'a\nb'} label="Prompt" />)
    expect(html).toContain('a\nb')
    expect(html).not.toContain('Expand')
  })

  it('collapsed state shows exactly the first 5 lines and an expand control', () => {
    const html = renderToStaticMarkup(<FoldedText text={numberedLines(30)} label="Prompt" />)
    expect(html).toContain(`line-${FOLDED_TEXT_COLLAPSED_LINES}`)
    expect(html).not.toContain(`line-${FOLDED_TEXT_COLLAPSED_LINES + 1}`)
    expect(html).toContain('Expand')
    expect(html).toContain('30 lines')
  })

  it('clampFrom end keeps the NEWEST lines visible — live output must not hide its tail', () => {
    const html = renderToStaticMarkup(
      <FoldedText text={numberedLines(30)} label="Answer" clampFrom="end" />,
    )
    expect(html).toContain('line-30')
    expect(html).not.toContain('line-1<')
  })
})
