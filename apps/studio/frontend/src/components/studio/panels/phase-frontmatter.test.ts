import { describe, expect, it } from 'vitest'
import {
  applyPhaseFrontmatterForm,
  parsePhaseFrontmatter,
  phaseFrontmatterToForm,
} from './phase-frontmatter'

// MVP1 Properties whitelist contract (FROZEN skill-spec + engine MVP1 + Studio D7/GE3):
// - node type comes from the file kind, never a `mode:` field; Properties must never write `mode:`.
// - legacy editable fields (<python_callable>, <system_prompt>, <exit_contract>, bare target_skill)
//   are drift and must not be the editable main path.
// - unknown frontmatter keys and the existing body must round-trip untouched.
describe('phase frontmatter helpers (MVP1 whitelist)', () => {
  it('edits a logic node without emitting a mode field or a python_callable shell', () => {
    const source = [
      '---',
      'name: draft',
      'io:',
      '  inputs:',
      '    type: object',
      '    properties:',
      '      raw_text: { type: string }',
      '  outputs:',
      '    type: object',
      '    properties:',
      '      normalized_text: { type: string }',
      'actions:',
      '  - normalize_whitespace',
      'x_internal: keep-me',
      '---',
      '<action>normalize_whitespace</action>',
      '',
      '# Draft',
      '',
      'Keep this markdown body.',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter, parsed.body)
    const next = applyPhaseFrontmatterForm(source, { ...form, name: 'outline' })

    expect(next.ok).toBe(true)
    if (!next.ok) return

    expect(next.markdown).toContain('name: outline')
    // MVP1: no synthetic `mode:` discriminator, no legacy python_callable shell.
    expect(next.markdown).not.toMatch(/^mode:/m)
    expect(next.markdown).not.toContain('<python_callable>')
    // Real logic fields and unknown keys survive the round-trip.
    expect(next.markdown).toMatch(/^actions:/m)
    expect(next.markdown).toContain('x_internal: keep-me')
    expect(next.markdown).toContain('<action>normalize_whitespace</action>')
    expect(next.markdown).toContain('Keep this markdown body.')
  })

  it('edits an agent node via role/goal body, never mode/system_prompt/exit_contract', () => {
    const source = [
      '---',
      'name: review',
      'io:',
      '  inputs:',
      '    type: object',
      '    properties:',
      '      draft: { type: string }',
      '  outputs:',
      '    type: object',
      '    properties:',
      '      verdict: { type: string }',
      'tools:',
      '  - read_reference',
      'x_internal: keep-me',
      '---',
      '<role>',
      'Senior editor.',
      '</role>',
      '',
      '<goal>',
      'Decide if the draft ships.',
      '</goal>',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter, parsed.body)
    const next = applyPhaseFrontmatterForm(source, { ...form })

    expect(next.ok).toBe(true)
    if (!next.ok) return

    expect(next.markdown).not.toMatch(/^mode:/m)
    expect(next.markdown).not.toContain('<system_prompt>')
    expect(next.markdown).not.toContain('<exit_contract>')
    // MVP1 agent business identity lives in <role>/<goal>, which must be preserved.
    expect(next.markdown).toContain('<role>')
    expect(next.markdown).toContain('<goal>')
    expect(next.markdown).toContain('x_internal: keep-me')
  })

  it('edits a subgraph node by local path, never a bare target_skill or mode', () => {
    const source = [
      '---',
      'name: child',
      'path: ./subskills/review',
      'io:',
      '  inputs:',
      '    type: object',
      '    properties:',
      '      segments: { type: array }',
      '  outputs:',
      '    type: object',
      '    properties:',
      '      review_score: { type: number }',
      '---',
      '# child',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter, parsed.body)
    const next = applyPhaseFrontmatterForm(source, { ...form })

    expect(next.ok).toBe(true)
    if (!next.ok) return

    // Studio D7 is the upper authority: subgraph is referenced by path, not a registry id.
    expect(next.markdown).toMatch(/^path:/m)
    expect(next.markdown).toContain('./subskills/review')
    expect(next.markdown).not.toMatch(/^target_skill:/m)
    expect(next.markdown).not.toMatch(/^mode:/m)
  })

  it('does not generate replacement markdown when YAML is invalid', () => {
    const source = [
      '---',
      'name: [broken',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(false)
    expect(applyPhaseFrontmatterForm(source, phaseFrontmatterToForm({})).ok).toBe(false)
  })
})
