import { describe, expect, it } from 'vitest'
import {
  applyPhaseFrontmatterForm,
  EMPTY_FORM,
  parsePhaseFrontmatter,
  phaseFrontmatterToForm,
} from './phase-frontmatter'

const DEPRECATED_TOKENS = [
  'mode:',
  'system_prompt',
  'user_prompt_builder',
  'exit_contract',
  'python_callable',
  'target_skill',
  'max_retries',
  'max_nudges',
]

describe('phase frontmatter helpers', () => {
  it('parses whitelisted agent fields and round-trips, preserving unknown keys and body', () => {
    const source = [
      '---',
      'name: producer_review',
      'llm_role: reviewer',
      'io:',
      '  inputs:',
      '    type: object',
      '    properties:',
      '      segments: {type: array}',
      'tools:',
      '  - read_reference',
      'x_internal: keep-me',
      '---',
      '<role>Reviewer</role>',
      '',
      '<goal>Review the draft.</goal>',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.llmRole).toBe('reviewer')
    expect(form.tools).toBe('read_reference')

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      tools: 'read_reference\nread_example',
    }, 'agent')

    expect(next.ok).toBe(true)
    if (!next.ok) return

    // Whitelisted edits applied.
    expect(next.markdown).toContain('  - read_reference')
    expect(next.markdown).toContain('  - read_example')
    // Editable whitelist field preserved when not changed.
    expect(next.markdown).toContain('llm_role: reviewer')
    // Non-form keys preserved (name, io, unknown) — never destroyed on save.
    expect(next.markdown).toContain('name: producer_review')
    expect(next.markdown).toContain('io:')
    expect(next.markdown).toContain('x_internal: keep-me')
    // Body preserved.
    expect(next.markdown).toContain('<role>Reviewer</role>')
    expect(next.markdown).toContain('<goal>Review the draft.</goal>')
  })

  it('parses and round-trips whitelisted subagents on agent nodes', () => {
    const source = [
      '---',
      'name: review',
      'subagents:',
      '  - name: producer_reviewer',
      '    target_skill: producer_reviewer',
      '    description: Review story production quality',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.subagents).toEqual([
      { name: 'producer_reviewer', target_skill: 'producer_reviewer', description: 'Review story production quality' },
    ])

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      subagents: [
        ...form.subagents,
        { name: 'fact_checker', target_skill: 'fact_checker', description: 'Verify claims' },
      ],
    }, 'agent')

    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).toContain('name: producer_reviewer')
    expect(next.markdown).toContain('name: fact_checker')
    expect(next.markdown).toContain('target_skill: fact_checker')
  })

  it('updates whitelisted logic fields and preserves unknown keys, llm_role, and body', () => {
    const source = [
      '---',
      'name: normalize_text',
      'llm_role: analyst',
      'actions:',
      '  - strip_noise',
      'x_internal: keep-me',
      '---',
      '<action>strip_noise</action>',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.actions).toBe('strip_noise')
    expect(form.validator).toBe(false)

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      actions: 'strip_noise\nnormalize_whitespace',
      validator: true,
    }, 'logic')

    expect(next.ok).toBe(true)
    if (!next.ok) return

    expect(next.markdown).toContain('  - strip_noise')
    expect(next.markdown).toContain('  - normalize_whitespace')
    expect(next.markdown).toContain('validator: true')
    // Non-form keys preserved — including llm_role the logic form never shows.
    expect(next.markdown).toContain('name: normalize_text')
    expect(next.markdown).toContain('llm_role: analyst')
    expect(next.markdown).toContain('x_internal: keep-me')
    // Body preserved.
    expect(next.markdown).toContain('<action>strip_noise</action>')
  })

  it('updates whitelisted subgraph path/validator and preserves unknown keys and body', () => {
    const source = [
      '---',
      'name: producer_review',
      'path: /old/path/to/child',
      'io:',
      '  inputs: {type: object}',
      'x_internal: keep-me',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.path).toBe('/old/path/to/child')

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      path: '/abs/path/to/child',
      validator: true,
    }, 'subgraph')

    expect(next.ok).toBe(true)
    if (!next.ok) return

    expect(next.markdown).toContain('path: /abs/path/to/child')
    expect(next.markdown).toContain('validator: true')
    expect(next.markdown).toContain('name: producer_review')
    expect(next.markdown).toContain('io:')
    expect(next.markdown).toContain('x_internal: keep-me')
  })

  it('drops validator when toggled off without touching other keys', () => {
    const source = [
      '---',
      'name: normalize_text',
      'actions:',
      '  - strip_noise',
      'validator: true',
      'x_internal: keep-me',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.validator).toBe(true)

    const next = applyPhaseFrontmatterForm(source, { ...form, validator: false }, 'logic')
    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).not.toContain('validator:')
    expect(next.markdown).toContain('x_internal: keep-me')
  })

  it('never writes any deprecated / FROZEN-violating field for any kind', () => {
    const source = [
      '---',
      'name: phase',
      'llm_role: reviewer',
      'tools:',
      '  - read_reference',
      'actions:',
      '  - strip_noise',
      'path: /abs/child',
      '---',
      'Body',
    ].join('\n')

    for (const kind of ['agent', 'logic', 'subgraph'] as const) {
      const parsed = parsePhaseFrontmatter(source)
      expect(parsed.ok).toBe(true)
      if (!parsed.ok) continue
      const form = phaseFrontmatterToForm(parsed.frontmatter)
      const next = applyPhaseFrontmatterForm(source, form, kind)
      expect(next.ok).toBe(true)
      if (!next.ok) continue
      for (const token of DEPRECATED_TOKENS) {
        expect(next.markdown).not.toContain(token)
      }
    }
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
    expect(applyPhaseFrontmatterForm(source, EMPTY_FORM, 'logic').ok).toBe(false)
  })
})
