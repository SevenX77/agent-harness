import { describe, expect, it } from 'vitest'

import { computeLineDiff, lineDiffStats } from './line-diff'

describe('computeLineDiff', () => {
  it('marks a single changed line as del + add, keeping context', () => {
    const rows = computeLineDiff('alpha\noriginal\nomega', 'alpha\nEDITED\nomega')
    expect(rows).toEqual([
      { kind: 'same', text: 'alpha' },
      { kind: 'del', text: 'original' },
      { kind: 'add', text: 'EDITED' },
      { kind: 'same', text: 'omega' },
    ])
    expect(lineDiffStats(rows)).toEqual({ added: 1, removed: 1 })
  })

  it('treats a brand-new file as all additions', () => {
    const rows = computeLineDiff('', 'line1\nline2')
    expect(rows).toEqual([
      { kind: 'add', text: 'line1' },
      { kind: 'add', text: 'line2' },
    ])
    expect(lineDiffStats(rows)).toEqual({ added: 2, removed: 0 })
  })

  it('treats a full deletion as all removals', () => {
    const rows = computeLineDiff('gone1\ngone2', '')
    expect(rows.every((r) => r.kind === 'del')).toBe(true)
    expect(lineDiffStats(rows)).toEqual({ added: 0, removed: 2 })
  })

  it('reports no changes for identical content', () => {
    const rows = computeLineDiff('x\ny', 'x\ny')
    expect(lineDiffStats(rows)).toEqual({ added: 0, removed: 0 })
    expect(rows.every((r) => r.kind === 'same')).toBe(true)
  })
})
