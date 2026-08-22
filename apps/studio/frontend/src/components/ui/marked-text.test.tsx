import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MarkedText, splitOnTerm } from './marked-text'

describe('splitOnTerm', () => {
  it('hands back one unmarked run when there is nothing to mark', () => {
    expect(splitOnTerm('hello world', '')).toEqual([{ text: 'hello world', marked: false }])
    expect(splitOnTerm('hello world', '   ')).toEqual([{ text: 'hello world', marked: false }])
    expect(splitOnTerm('hello world', 'zzz')).toEqual([{ text: 'hello world', marked: false }])
  })

  it('marks every occurrence, keeping the text the reader is looking at intact', () => {
    // Case-insensitive because the narrowing that produced this term is
    // (`trace-narrowing.ts` lowercases both sides), and a mark that disagreed
    // with the match would point at a row for a reason it cannot show.
    expect(splitOnTerm('Draft then draft again', 'DRAFT')).toEqual([
      { text: 'Draft', marked: true },
      { text: ' then ', marked: false },
      { text: 'draft', marked: true },
      { text: ' again', marked: false },
    ])
  })

  it('marks a term that starts or ends the text without emitting empty runs', () => {
    expect(splitOnTerm('draft', 'draft')).toEqual([{ text: 'draft', marked: true }])
  })

  it('treats the term as literal text, not as a pattern', () => {
    // The search box is a search box. A reader typing `a.b` means those three
    // characters; letting `.` match anything would mark spans the narrowing
    // never matched on.
    expect(splitOnTerm('a.b and axb', 'a.b')).toEqual([
      { text: 'a.b', marked: true },
      { text: ' and axb', marked: false },
    ])
  })
})

describe('MarkedText', () => {
  it('wraps only the matched runs in a mark element', () => {
    const html = renderToStaticMarkup(<MarkedText text="phase draft ended" term="draft" />)

    expect(html).toContain('<mark')
    expect(html).toContain('>draft</mark>')
    expect(html).toContain('phase ')
  })

  it('renders plain text when nothing matches, with no mark element at all', () => {
    const html = renderToStaticMarkup(<MarkedText text="phase draft ended" term="review" />)

    expect(html).not.toContain('<mark')
    expect(html).toContain('phase draft ended')
  })
})
