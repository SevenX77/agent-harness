import { describe, expect, it } from 'vitest'
import { CONFLICT_TITLE, CONFLICT_VERB } from './conflict-vocabulary'

// The surfaces themselves are pinned to this table by their own tests
// (`ConflictDialog.test.tsx`, `GraphCanvas.test.tsx`), which assert against
// these constants rather than against literals — so a surface that invents its
// own word for the same action fails there. What is left to pin here is the
// table's own coherence.
describe('conflict vocabulary', () => {
  it('states every conflict in one grammar', () => {
    for (const title of Object.values(CONFLICT_TITLE)) {
      expect(title.endsWith('would be overwritten')).toBe(true)
    }
  })

  it('gives each action exactly one word', () => {
    const verbs = Object.values(CONFLICT_VERB)

    expect(new Set(verbs).size).toBe(verbs.length)
  })
})
