import { describe, expect, it } from 'vitest'
import { nodeToFocus } from './canvas-focus'

describe('nodeToFocus (N4 atom #9 run-focus-follow target)', () => {
  it('returns the running phase id when a matching node exists', () => {
    // Run advances A -> B: each running phase that is on the canvas is the focus target.
    expect(nodeToFocus('A', ['INPUT', 'A', 'B', 'OUTPUT'])).toBe('A')
    expect(nodeToFocus('B', ['INPUT', 'A', 'B', 'OUTPUT'])).toBe('B')
  })

  it('returns null when no node is running', () => {
    expect(nodeToFocus(null, ['A', 'B'])).toBeNull()
    expect(nodeToFocus(undefined, ['A', 'B'])).toBeNull()
    expect(nodeToFocus('', ['A', 'B'])).toBeNull()
  })

  it('returns null when the running phase has no matching canvas node', () => {
    // Drilled child / stale phase id: never fitView onto a node that is not there.
    expect(nodeToFocus('ghost', ['A', 'B'])).toBeNull()
    expect(nodeToFocus('A', [])).toBeNull()
  })
})
