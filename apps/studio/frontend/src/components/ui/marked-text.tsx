import { Fragment } from 'react'

export interface TextRun {
  text: string
  marked: boolean
}

/**
 * Split `text` into the runs a term matched and the runs it did not.
 *
 * Case-insensitive and literal, because it has to agree with the narrowing that
 * produced the term: `trace-narrowing.ts` lowercases both sides and uses
 * `includes`. A mark computed by a different rule would point at a row for a
 * reason the row cannot show, or leave a matched row with nothing marked —
 * either way the reader is told two different things about one match.
 */
export function splitOnTerm(text: string, term: string): TextRun[] {
  const needle = term.trim().toLowerCase()
  if (needle.length === 0) return [{ text, marked: false }]

  const haystack = text.toLowerCase()
  const runs: TextRun[] = []
  let cursor = 0
  for (;;) {
    const hit = haystack.indexOf(needle, cursor)
    if (hit === -1) break
    if (hit > cursor) runs.push({ text: text.slice(cursor, hit), marked: false })
    runs.push({ text: text.slice(hit, hit + needle.length), marked: true })
    cursor = hit + needle.length
  }
  if (runs.length === 0) return [{ text, marked: false }]
  if (cursor < text.length) runs.push({ text: text.slice(cursor), marked: false })
  return runs
}

/**
 * Split a sentence so that only the part of it that came off the event can be
 * marked, and the words we wrote around that part cannot.
 *
 * Trace rows print values inside sentences we authored — `endpoint: {{id}}`,
 * `Loaded — {{path}}`, `HTTP {{status}}`. Marking the whole sentence would put
 * a mark on our own vocabulary: a reader searching `end` would see "endpoint"
 * lit up on a row that matched for some entirely different reason, which is the
 * failure F14 names — the mark must always point at the thing that actually
 * matched.
 *
 * Only the FIRST occurrence of `value` is markable. These frames interpolate a
 * value once; if a translation ever repeats it, one lit occurrence is already
 * enough to show the reader why the row is here, and guessing which repeat they
 * meant would be inventing a reason.
 *
 * A `value` the sentence does not contain leaves the sentence entirely
 * unmarked. i18n owns the wording, so a translation that drops the
 * interpolation is a sentence with no verbatim part — and no mark is the honest
 * rendering of that, where a mark placed by guesswork is not.
 */
export function splitOnTermWithin(text: string, value: string, term: string): TextRun[] {
  if (value.length === 0) return [{ text, marked: false }]
  const start = text.indexOf(value)
  if (start === -1) return [{ text, marked: false }]

  const runs: TextRun[] = []
  if (start > 0) runs.push({ text: text.slice(0, start), marked: false })
  runs.push(...splitOnTerm(value, term))
  const end = start + value.length
  if (end < text.length) runs.push({ text: text.slice(end), marked: false })
  return runs
}

/**
 * Text with one term marked wherever it occurs.
 *
 * `warning` rather than `accent` or `destructive`: a mark has to stay legible
 * ON TOP of the surfaces it lands on, and those two are already the selected
 * row (`bg-accent`) and the failed row (`bg-destructive/10`) — a mark in either
 * of them would disappear into exactly the rows a reader is most likely to be
 * looking at.
 */
export function MarkedText({ text, term }: { text: string; term: string }) {
  return <Runs runs={splitOnTerm(text, term)} />
}

/**
 * A sentence we authored with the one value in it that the event supplied,
 * marked where the term hit that value — and nowhere else.
 *
 * `text` is the finished translated sentence and `value` is the substring of it
 * that came off the event, so the caller passes both: i18n owns the wording and
 * word order, and this component only needs to know which slice of the result
 * is quotable.
 */
export function MarkedValue({ text, value, term }: { text: string; value: string; term: string }) {
  return <Runs runs={splitOnTermWithin(text, value, term)} />
}

function Runs({ runs }: { runs: TextRun[] }) {
  if (!runs.some((run) => run.marked)) return <>{runs.map((run) => run.text).join('')}</>
  return (
    <>
      {runs.map((run, index) => (
        <Fragment key={index}>
          {run.marked
            ? <mark className="rounded-[2px] bg-warning/40 text-foreground">{run.text}</mark>
            : run.text}
        </Fragment>
      ))}
    </>
  )
}
