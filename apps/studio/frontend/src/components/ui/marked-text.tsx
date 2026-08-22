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
 * Text with one term marked wherever it occurs.
 *
 * `warning` rather than `accent` or `destructive`: a mark has to stay legible
 * ON TOP of the surfaces it lands on, and those two are already the selected
 * row (`bg-accent`) and the failed row (`bg-destructive/10`) — a mark in either
 * of them would disappear into exactly the rows a reader is most likely to be
 * looking at.
 */
export function MarkedText({ text, term }: { text: string; term: string }) {
  const runs = splitOnTerm(text, term)
  if (runs.length === 1 && !runs[0].marked) return <>{text}</>
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
