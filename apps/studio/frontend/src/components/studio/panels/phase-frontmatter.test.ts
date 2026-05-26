import { describe, expect, it } from 'vitest'
import {
  applyPhaseFrontmatterForm,
  parsePhaseFrontmatter,
  phaseFrontmatterToForm,
} from './phase-frontmatter'

describe('phase frontmatter helpers', () => {
  it('updates supported logic fields while preserving unsupported fields and body', () => {
    const source = [
      '---',
      'name: draft',
      'mode: logic',
      'x_internal: keep-me',
      '---',
      '<python_callable>',
      'old_callable',
      '</python_callable>',
      '',
      '# Draft',
      '',
      'Keep this markdown body.',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter, parsed.body)
    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      name: 'outline',
      pythonCallable: 'new_callable',
    })

    expect(next.ok).toBe(true)
    if (!next.ok) return

    expect(next.markdown).toContain('name: outline')
    expect(next.markdown).toContain('mode: logic')
    expect(next.markdown).toContain('x_internal: keep-me')
    expect(next.markdown).toContain('<python_callable>\nnew_callable\n</python_callable>')
    expect(next.markdown).not.toContain('old_callable')
    expect(next.markdown.endsWith('# Draft\n\nKeep this markdown body.')).toBe(true)
  })

  it('updates supported skill fields and converts textarea lines to tools', () => {
    const source = [
      '---',
      'name: review',
      'mode: skill',
      'tools:',
      '  - read_file',
      'unsafe_extra: true',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter, parsed.body)
    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      systemPrompt: 'Review the draft.',
      exitContract: 'Call finish_task.',
      tools: 'read_file\nwrite_file',
    })

    expect(next.ok).toBe(true)
    if (!next.ok) return

    expect(next.markdown).toContain('<system_prompt>\nReview the draft.\n</system_prompt>')
    expect(next.markdown).toContain('<exit_contract>\nCall finish_task.\n</exit_contract>')
    expect(next.markdown).not.toContain('llm_role')
    expect(next.markdown).not.toContain('agent_tools')
    expect(next.markdown).toContain('  - read_file')
    expect(next.markdown).toContain('  - write_file')
    expect(next.markdown).toContain('unsafe_extra: true')
  })

  it('updates subgraph refs without adding agent-only fields', () => {
    const source = [
      '---',
      'name: child',
      'mode: subgraph',
      'target_skill: old.child',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter, parsed.body)
    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      targetSkill: 'new.child',
      systemPrompt: 'ignored',
      tools: 'ignored_tool',
    })

    expect(next.ok).toBe(true)
    if (!next.ok) return

    expect(next.markdown).toContain('target_skill: new.child')
    expect(next.markdown).not.toContain('sub_skill_ref')
    expect(next.markdown).not.toContain('tools:')
    expect(next.markdown).not.toContain('<system_prompt>')
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
