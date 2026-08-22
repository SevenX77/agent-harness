import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { MarkedText, MarkedValue, splitOnTerm, splitOnTermWithin } from './marked-text'

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

describe('splitOnTermWithin', () => {
  it('marks the term inside the value and leaves the sentence around it alone', () => {
    // The sentence is ours; only the id came off the event. A reader searching
    // `end` matched some OTHER row — marking the word "endpoint" here would
    // claim this row matched for a reason it did not.
    expect(splitOnTermWithin('endpoint: sendgrid-official', 'sendgrid-official', 'end')).toEqual([
      { text: 'endpoint: ', marked: false },
      { text: 's', marked: false },
      { text: 'end', marked: true },
      { text: 'grid-official', marked: false },
    ])
  })

  it('marks a value that is the whole sentence', () => {
    expect(splitOnTermWithin('ark-official', 'ark-official', 'ark')).toEqual([
      { text: 'ark', marked: true },
      { text: '-official', marked: false },
    ])
  })

  it('leaves everything unmarked when the value is absent or empty', () => {
    // i18n decides the wording; if a translation drops the interpolation, the
    // honest answer is an unmarked sentence, not a mark placed by guesswork.
    expect(splitOnTermWithin('no id here', 'ark-official', 'ark')).toEqual([
      { text: 'no id here', marked: false },
    ])
    expect(splitOnTermWithin('endpoint: ', '', 'ark')).toEqual([
      { text: 'endpoint: ', marked: false },
    ])
  })
})

describe('MarkedValue', () => {
  it('marks inside the value only', () => {
    const html = renderToStaticMarkup(
      <MarkedValue text="endpoint: ark-official" value="ark-official" term="ark" />,
    )

    expect(html).toContain('>ark</mark>')
    expect(html).toContain('endpoint: ')
    expect(html).not.toContain('<mark class="rounded-[2px] bg-warning/40 text-foreground">endpoint')
  })

  it('renders the sentence plainly when the term misses the value', () => {
    const html = renderToStaticMarkup(
      <MarkedValue text="endpoint: ark-official" value="ark-official" term="point" />,
    )

    expect(html).not.toContain('<mark')
    expect(html).toContain('endpoint: ark-official')
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
