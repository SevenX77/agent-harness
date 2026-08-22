/** Which images a turn will carry, and what it says about the ones it won't.
 *
 * Design: `copilot-assist/mvp1-alignment.md` decision COPILOT_ASSIST-11 ②③.
 *
 * The rules these tests hold the intake to:
 *   * one budget for the whole turn, because one WebSocket frame carries the
 *     whole turn;
 *   * over budget or wrong type means REFUSED and named — never silently
 *     downscaled, re-encoded, or dropped;
 *   * a refusal never disturbs what was already attached.
 */
import { describe, expect, it } from 'vitest'

import {
  TURN_IMAGE_BUDGET_BYTES,
  admitAttachments,
  decodedByteLength,
} from './attachment-intake'

function image(name: string, mediaType: string, byteCount: number) {
  return { name, mediaType, bytes: new Uint8Array(byteCount).fill(65) }
}

describe('decodedByteLength', () => {
  it('reads the real size back out of base64', () => {
    for (const size of [1, 2, 3, 4, 5, 100, 1023]) {
      const base64 = btoa(String.fromCharCode(...new Uint8Array(size).fill(66)))
      expect(decodedByteLength(base64)).toBe(size)
    }
  })
})

describe('admitAttachments', () => {
  it('turns a picked image into the attachment the wire carries', () => {
    const { accepted, refused } = admitAttachments([], [image('shot.png', 'image/png', 12)])

    expect(refused).toEqual([])
    expect(accepted).toHaveLength(1)
    expect(accepted[0]).toMatchObject({ kind: 'image', media_type: 'image/png', name: 'shot.png' })
    expect(decodedByteLength(accepted[0].data)).toBe(12)
  })

  it('keeps what was already attached and appends', () => {
    const first = admitAttachments([], [image('a.png', 'image/png', 4)]).accepted
    const { accepted } = admitAttachments(first, [image('b.jpg', 'image/jpeg', 4)])

    expect(accepted.map((item) => item.name)).toEqual(['a.png', 'b.jpg'])
  })

  it('refuses a type the wire has no word for, and says which type it was', () => {
    // The media_type union is closed; guessing at a mapping (or renaming the
    // extension) would put a value on the wire the backend must then reject.
    const { accepted, refused } = admitAttachments([], [image('notes.pdf', 'application/pdf', 4)])

    expect(accepted).toEqual([])
    expect(refused).toEqual([
      { name: 'notes.pdf', refusal: { reason: 'unsupported_type', mediaType: 'application/pdf' } },
    ])
  })

  it('refuses what would take the turn over budget, and says by how much', () => {
    const oversized = image('huge.png', 'image/png', TURN_IMAGE_BUDGET_BYTES + 1)
    const { accepted, refused } = admitAttachments([], [oversized])

    expect(accepted).toEqual([])
    expect(refused[0].refusal).toEqual({
      reason: 'over_turn_budget',
      totalBytes: TURN_IMAGE_BUDGET_BYTES + 1,
      budgetBytes: TURN_IMAGE_BUDGET_BYTES,
    })
  })

  it('counts what is ALREADY attached against the same budget', () => {
    // One frame carries the whole turn, so the budget is per turn, not per pick.
    const half = Math.floor(TURN_IMAGE_BUDGET_BYTES / 2)
    const existing = admitAttachments([], [image('a.png', 'image/png', half)]).accepted
    const { accepted, refused } = admitAttachments(existing, [
      image('b.png', 'image/png', half + 10),
    ])

    expect(accepted).toEqual(existing)
    expect(refused[0].refusal.reason).toBe('over_turn_budget')
  })

  it('takes the ones that fit and names the ones that do not', () => {
    // A refusal must not throw away a sibling that was perfectly fine — the
    // user picked several files in one dialog and only one of them was wrong.
    const { accepted, refused } = admitAttachments([], [
      image('ok.png', 'image/png', 8),
      image('bad.svg', 'image/svg+xml', 8),
      image('also-ok.webp', 'image/webp', 8),
    ])

    expect(accepted.map((item) => item.name)).toEqual(['ok.png', 'also-ok.webp'])
    expect(refused.map((item) => item.name)).toEqual(['bad.svg'])
  })

  it('accepts every media type the wire has a word for', () => {
    const { accepted, refused } = admitAttachments([], [
      image('a.png', 'image/png', 4),
      image('b.jpg', 'image/jpeg', 4),
      image('c.gif', 'image/gif', 4),
      image('d.webp', 'image/webp', 4),
    ])

    expect(refused).toEqual([])
    expect(accepted.map((item) => item.media_type)).toEqual([
      'image/png',
      'image/jpeg',
      'image/gif',
      'image/webp',
    ])
  })

  it('never re-encodes or resizes to make something fit', () => {
    // COPILOT_ASSIST-11 ③: shrinking the picture silently swaps the evidence the
    // user is asking about. The bytes that come out are the bytes that went in.
    const bytes = new Uint8Array([1, 2, 3, 250, 251, 252])
    const { accepted } = admitAttachments([], [{ name: 'x.png', mediaType: 'image/png', bytes }])

    const roundTripped = Uint8Array.from(atob(accepted[0].data), (char) => char.charCodeAt(0))
    expect([...roundTripped]).toEqual([...bytes])
  })
})
