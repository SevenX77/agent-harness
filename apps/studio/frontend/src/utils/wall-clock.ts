/**
 * How this product turns a stored instant into something a person reads.
 *
 * Everything the backend and engine store is an aware UTC instant, because that
 * is what code computes with and what survives a machine changing zones. But a
 * person never wants UTC: decision D13
 * (`docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md` F1b)
 * settled that for the run id — "UTC 戳对着文件树的人读起来就是错的时间" — and
 * the reason is about the reader, not about run ids, so it governs every
 * surface a reader looks at.
 *
 * This module is where that conversion happens, once. Before it existed the
 * product had seven separate renderings of "an instant, for a person": two
 * byte-identical `relativeTime` copies, three date-and-time formatters (two of
 * them character-for-character the same), one full-moment formatter, and one
 * that stripped the offset off the string and showed UTC digits as though they
 * were local (Settings → truth sources). That last one is the cost the
 * duplication was always going to charge — with one owner it is a single
 * function to get right.
 *
 * The readings are separate functions because they answer different questions,
 * not because they format differently: `timeOfDay` where the date is implied by
 * the surrounding rows, `dateAndTime` where it is not, `momentInFull` where the
 * moment must stand alone with no context at all, `relativeTime` where the
 * distance from now matters more than the moment, `fileStamp` where the reading
 * has to survive as a filename.
 *
 * Every one of them parses with `new Date(...)`, which reads the offset the
 * string carries; nothing here touches the digits of the string itself. Two
 * spellings of one instant therefore render identically, which is the invariant
 * `wall-clock.test.ts` pins.
 */

const pad = (value: number) => String(value).padStart(2, '0')

/**
 * An instant, however the caller happens to be holding it: an ISO string off
 * the wire, epoch milliseconds out of a local draft, or an already-parsed Date.
 * Which spelling a caller has is an accident of where the value came from, and
 * making each spelling its own renderer is how the copies started.
 */
export type Instant = string | number | Date

function parsed(value: Instant): Date | null {
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * `06:58:15` — the local clock, for rows whose date the surrounding view
 * already establishes (a trace timeline, a log tail).
 *
 * Null when the value is not a readable instant, so the caller decides whether
 * a row with no time renders without one or not at all.
 */
export function timeOfDay(value: Instant): string | null {
  const date = parsed(value)
  if (date === null) return null
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/**
 * `Aug 19, 06:58` — the local clock plus enough date to place it, for rows that
 * stand on their own (a run in the history list, a truth source's last write).
 *
 * Locale-aware via `Intl` with no explicit locale, so the month name and field
 * order follow the reader's system rather than this file's assumptions. Returns
 * the input unchanged when it is not a readable instant: a surface that already
 * has a string in hand is better off showing it than showing nothing.
 */
export function dateAndTime(value: Instant): string {
  const date = parsed(value)
  if (date === null) return String(value)
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

/**
 * `Aug 19, 2026, 6:58 AM` — a moment that has to stand on its own anywhere,
 * with no surrounding view to imply the year: a draft the reader is deciding
 * whether to restore, a line in a report that will be read months later.
 *
 * Both fields come from `Intl`'s named styles rather than a hand-picked field
 * list, so the reading follows the reader's locale conventions end to end.
 */
export function momentInFull(value: Instant): string {
  const date = parsed(value)
  if (date === null) return String(value)
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

/**
 * `3m ago` — distance from now, stepping down in precision as it grows because
 * that is how the reader's interest decays: seconds matter for something that
 * just happened, days for something that did not.
 *
 * Clamped at zero. A machine whose clock runs a few seconds behind the one that
 * stamped the value would otherwise produce a negative age, and "-3s ago" reads
 * as a bug in the product rather than a skew between two clocks.
 */
export function relativeTime(value: Instant): string {
  const date = parsed(value)
  if (date === null) return String(value)
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

/**
 * `2026-08-19T06-58-15` — a local wall clock that can be a filename.
 *
 * Deliberately the same shape the backend stamps run directories with
 * (`app/services/run_ids.py`), so an exported report and the run it came from
 * sort together and read as the same moment. Colons are out because Windows
 * refuses them in filenames; that is the whole reason for the dashes.
 */
export function fileStamp(at: Date = new Date()): string {
  return (
    `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}` +
    `T${pad(at.getHours())}-${pad(at.getMinutes())}-${pad(at.getSeconds())}`
  )
}
