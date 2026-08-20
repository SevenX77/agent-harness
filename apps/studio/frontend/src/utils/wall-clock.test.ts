import { describe, expect, it } from 'vitest'
import { dateAndTime, fileStamp, momentInFull, relativeTime, timeOfDay } from './wall-clock'

/**
 * The invariant every reading here has to hold: two spellings of ONE instant
 * render the same text.
 *
 * `2026-08-19T13:58:15Z` and `2026-08-19T06:58:15-07:00` are the same moment
 * written two ways. Any renderer that reaches into the digits of the string —
 * stripping the offset, slicing at the `T` — makes them render differently, and
 * whichever one it gets wrong names a moment that never happened.
 */
const SAME_INSTANT = ['2026-08-19T13:58:15Z', '2026-08-19T06:58:15-07:00', '2026-08-19T15:58:15+02:00']

const pad = (value: number) => String(value).padStart(2, '0')

describe('one instant, one reading', () => {
  it.each([
    ['timeOfDay', timeOfDay],
    ['dateAndTime', dateAndTime],
    ['momentInFull', momentInFull],
  ])('%s reads every spelling of one instant the same', (_name, render) => {
    const [first, ...rest] = SAME_INSTANT.map((iso) => render(iso))
    for (const other of rest) {
      expect(other).toBe(first)
    }
  })

  it.each([
    ['timeOfDay', timeOfDay],
    ['dateAndTime', dateAndTime],
    ['momentInFull', momentInFull],
  ])('%s reads epoch milliseconds and a Date as the same instant too', (_name, render) => {
    const at = new Date('2026-08-19T13:58:15Z')
    expect(render(at.getTime())).toBe(render(at))
    expect(render(at.toISOString())).toBe(render(at))
  })
})

describe('timeOfDay', () => {
  it('is the local clock, not the stored one', () => {
    const instant = '2026-08-19T13:58:15Z'
    const local = new Date(instant)
    expect(timeOfDay(instant)).toBe(
      `${pad(local.getHours())}:${pad(local.getMinutes())}:${pad(local.getSeconds())}`,
    )
  })

  it('answers null for anything it cannot read', () => {
    expect(timeOfDay('not a time')).toBeNull()
    expect(timeOfDay('')).toBeNull()
  })
})

describe('dateAndTime', () => {
  it('carries the local hour of the instant', () => {
    const instant = '2026-08-19T13:58:15Z'
    const local = new Date(instant)
    expect(dateAndTime(instant)).toContain(pad(local.getHours()))
  })

  it('hands back what it was given when it cannot read it', () => {
    expect(dateAndTime('whenever')).toBe('whenever')
  })
})

describe('relativeTime', () => {
  const now = Date.now()
  const ago = (ms: number) => new Date(now - ms).toISOString()

  it('steps down through the units a reader thinks in', () => {
    expect(relativeTime(ago(5_000))).toBe('5s ago')
    expect(relativeTime(ago(90_000))).toBe('1m ago')
    expect(relativeTime(ago(3 * 3_600_000))).toBe('3h ago')
    expect(relativeTime(ago(2 * 86_400_000))).toBe('2d ago')
  })

  it('never counts backwards from a clock that is slightly ahead', () => {
    expect(relativeTime(new Date(now + 4_000).toISOString())).toBe('0s ago')
  })
})

describe('fileStamp', () => {
  it('is the same wall clock the run id is stamped with', () => {
    const at = new Date('2026-08-19T13:58:15Z')
    expect(fileStamp(at)).toBe(
      `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}` +
        `T${pad(at.getHours())}-${pad(at.getMinutes())}-${pad(at.getSeconds())}`,
    )
  })

  it('carries no colons, because a filename cannot', () => {
    expect(fileStamp(new Date('2026-08-19T13:58:15Z'))).not.toContain(':')
  })
})
