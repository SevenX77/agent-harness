import { describe, expect, it } from 'vitest'
import {
  applyPhaseName,
  applyPhaseFrontmatterForm,
  applyPhaseValidator,
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

  it('round-trips allow_sequential_overwrite as an editable phase frontmatter field', () => {
    const source = [
      '---',
      'name: review',
      'llm_role: analyst',
      'allow_sequential_overwrite:',
      '  - events_raw',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.allowSequentialOverwrite).toBe('events_raw')

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      allowSequentialOverwrite: 'events_raw\nparsed_events',
    }, 'agent')

    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).toContain('allow_sequential_overwrite:')
    expect(next.markdown).toContain('  - events_raw')
    expect(next.markdown).toContain('  - parsed_events')
  })

  it('migrates legacy batch into unified iterate when saving phase properties', () => {
    const source = [
      '---',
      'name: worker',
      'actions:',
      '  - worker',
      'batch:',
      '  iterator: data.items',
      '  item_var: item',
      '  concurrency: 2',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.iterate).toMatchObject({
      mode: 'batch',
      over: 'data.items',
      itemVar: 'item',
      concurrency: '2',
    })

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      iterate: {
        ...form.iterate,
        over: 'data.inputs.items',
        rangeStart: '2',
        rangeEnd: '3',
      },
    }, 'logic')

    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).not.toContain('batch:')
    expect(next.markdown).toContain('iterate:')
    expect(next.markdown).toContain('mode: batch')
    expect(next.markdown).toContain('over: data.inputs.items')
    expect(next.markdown).toContain('item_var: item')
    expect(next.markdown).toContain('range:')
    expect(next.markdown).toContain('  - 2')
    expect(next.markdown).toContain('  - 3')
    expect(next.markdown).toContain('concurrency: 2')
  })

  it('round-trips loop iterate accumulator settings', () => {
    const source = [
      '---',
      'name: collect',
      'actions:',
      '  - collect',
      'iterate:',
      '  mode: loop',
      '  over: data.inputs.items',
      '  item_var: item',
      '  accumulate:',
      '    var: collected',
      '    init: []',
      '    from: piece',
      '    merge: append',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.iterate).toMatchObject({
      mode: 'loop',
      over: 'data.inputs.items',
      itemVar: 'item',
      accumulateVar: 'collected',
      accumulateInit: '[]',
      accumulateFrom: 'piece',
      accumulateMerge: 'append',
    })

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      iterate: {
        ...form.iterate,
        accumulateInit: '0',
        accumulateMerge: 'replace',
      },
    }, 'logic')

    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).toContain('mode: loop')
    expect(next.markdown).toContain('over: data.inputs.items')
    expect(next.markdown).toContain('item_var: item')
    expect(next.markdown).toContain('accumulate:')
    expect(next.markdown).toContain('var: collected')
    expect(next.markdown).toContain('init: 0')
    expect(next.markdown).toContain('from: piece')
    expect(next.markdown).toContain('merge: replace')
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

  it('migrates legacy subgraph target_skill to path on save and never writes target_skill back', () => {
    const source = [
      '---',
      'name: child',
      'target_skill: legacy.registry.child',
      'io:',
      '  inputs: {type: object}',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.path).toBe('')

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      path: '/abs/skills/child',
    }, 'subgraph')

    expect(next.ok).toBe(true)
    if (!next.ok) return

    expect(next.markdown).toContain('path: /abs/skills/child')
    expect(next.markdown).not.toContain('target_skill:')
  })

  it('renames the phase name field without touching path, io, or body', () => {
    const source = [
      '---',
      'name: extract',
      'path: subgraph/event_extraction',
      'io:',
      '  inputs: {type: object}',
      '---',
      '<subgraph />',
    ].join('\n')

    const next = applyPhaseName(source, 'event_extraction')
    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).toContain('name: event_extraction')
    expect(next.markdown).toContain('path: subgraph/event_extraction')
    expect(next.markdown).toContain('io:')
    expect(next.markdown).toContain('<subgraph />')
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

  it('reads and round-trips agent validator + max_iterations', () => {
    const source = [
      '---',
      'name: review_chapter',
      'llm_role: analyst',
      'validator: true',
      'max_iterations: 20',
      'x_internal: keep-me',
      '---',
      '<role>Reviewer</role>',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.validator).toBe(true)
    expect(form.maxIterations).toBe('20')

    // Toggle validator off (default → drop) and lower max_iterations.
    const next = applyPhaseFrontmatterForm(source, { ...form, validator: false, maxIterations: '5' }, 'agent')
    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).not.toContain('validator:')
    expect(next.markdown).toContain('max_iterations: 5')
    // Non-form keys + body preserved.
    expect(next.markdown).toContain('llm_role: analyst')
    expect(next.markdown).toContain('x_internal: keep-me')
    expect(next.markdown).toContain('<role>Reviewer</role>')
  })

  it('drops max_iterations when cleared and ignores non-integer input', () => {
    const source = [
      '---',
      'name: review',
      'max_iterations: 12',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.maxIterations).toBe('12')

    const cleared = applyPhaseFrontmatterForm(source, { ...form, maxIterations: '' }, 'agent')
    expect(cleared.ok).toBe(true)
    if (!cleared.ok) return
    expect(cleared.markdown).not.toContain('max_iterations:')

    const garbage = applyPhaseFrontmatterForm(source, { ...form, maxIterations: '10abc' }, 'agent')
    expect(garbage.ok).toBe(true)
    if (!garbage.ok) return
    expect(garbage.markdown).not.toContain('max_iterations:')
  })

  it('parses and round-trips agent subgraphs (name/path/description)', () => {
    const source = [
      '---',
      'name: review',
      'subgraphs:',
      '  - name: evidence_pipeline',
      '    path: /abs/subgraph/evidence',
      '    description: Extract supporting evidence',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.subgraphs).toEqual([
      { name: 'evidence_pipeline', path: '/abs/subgraph/evidence', description: 'Extract supporting evidence' },
    ])

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      subgraphs: [...form.subgraphs, { name: 'extra_graph', path: '/abs/subgraph/extra', description: 'More work' }],
    }, 'agent')

    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).toContain('name: evidence_pipeline')
    expect(next.markdown).toContain('path: /abs/subgraph/evidence')
    expect(next.markdown).toContain('name: extra_graph')
    expect(next.markdown).toContain('path: /abs/subgraph/extra')
  })

  it('parses and round-trips agent references and examples (id/path/summary)', () => {
    const source = [
      '---',
      'name: review',
      'references:',
      '  - id: R1',
      '    path: references/style.md',
      '    summary: Style and scoring rules',
      'examples:',
      '  - id: E2',
      '    path: examples/boundary_case.md',
      '    summary: Boundary case example',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = phaseFrontmatterToForm(parsed.frontmatter)
    expect(form.references).toEqual([{ id: 'R1', path: 'references/style.md', summary: 'Style and scoring rules' }])
    expect(form.examples).toEqual([{ id: 'E2', path: 'examples/boundary_case.md', summary: 'Boundary case example' }])

    const next = applyPhaseFrontmatterForm(source, {
      ...form,
      references: [...form.references, { id: 'R2', path: 'references/scoring.md', summary: 'Scoring detail' }],
    }, 'agent')

    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).toContain('id: R1')
    expect(next.markdown).toContain('id: R2')
    expect(next.markdown).toContain('path: references/scoring.md')
    // examples untouched by a references-only edit.
    expect(next.markdown).toContain('id: E2')
  })

  it('keeps agent-only fields out of logic/subgraph saves even if the form carries them', () => {
    const source = [
      '---',
      'name: normalize',
      'actions:',
      '  - strip_noise',
      '---',
      'Body',
    ].join('\n')

    const parsed = parsePhaseFrontmatter(source)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return

    const form = {
      ...phaseFrontmatterToForm(parsed.frontmatter),
      subgraphs: [{ name: 'x', path: '/abs/x', description: 'd' }],
      references: [{ id: 'R1', path: 'references/s.md', summary: 's' }],
      examples: [{ id: 'E1', path: 'examples/e.md', summary: 's' }],
      maxIterations: '9',
    }

    const next = applyPhaseFrontmatterForm(source, form, 'logic')
    expect(next.ok).toBe(true)
    if (!next.ok) return
    expect(next.markdown).not.toContain('subgraphs:')
    expect(next.markdown).not.toContain('references:')
    expect(next.markdown).not.toContain('examples:')
    expect(next.markdown).not.toContain('max_iterations:')
  })

  it('toggles the validator flag in place, preserving other keys and body', () => {
    const source = [
      '---',
      'name: segment',
      'actions:',
      '  - strip',
      'x_internal: keep-me',
      '---',
      '<action>strip</action>',
    ].join('\n')

    const on = applyPhaseValidator(source, true)
    expect(on.ok).toBe(true)
    if (!on.ok) return
    expect(on.markdown).toContain('validator: true')
    expect(on.markdown).toContain('name: segment')
    expect(on.markdown).toContain('x_internal: keep-me')
    expect(on.markdown).toContain('<action>strip</action>')

    // Turning it off drops the key (default false), leaving everything else intact.
    const off = applyPhaseValidator(on.markdown, false)
    expect(off.ok).toBe(true)
    if (!off.ok) return
    expect(off.markdown).not.toContain('validator:')
    expect(off.markdown).toContain('x_internal: keep-me')
  })
})
