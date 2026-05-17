import { describe, expect, it } from 'vitest'
import { decideGraphReload } from './canvasReload'

describe('decideGraphReload', () => {
  it('reloads clean active GRAPH.md changes', () => {
    expect(decideGraphReload({
      type: 'skill_changed',
      skill_id: 'demo',
      file: 'GRAPH.md',
    }, 'demo', false)).toBe('reload')
  })

  it('prompts when the active canvas has local dirty changes', () => {
    expect(decideGraphReload({
      type: 'skill_changed',
      skill_id: 'demo',
      file: 'GRAPH.md',
    }, 'demo', true)).toBe('prompt')
  })

  it('ignores non-GRAPH.md and unrelated skill changes', () => {
    expect(decideGraphReload({
      type: 'skill_changed',
      skill_id: 'demo',
      file: 'SKILL.md',
    }, 'demo', false)).toBe('ignore')
    expect(decideGraphReload({
      type: 'skill_changed',
      skill_id: 'other',
      file: 'GRAPH.md',
    }, 'demo', false)).toBe('ignore')
  })
})
