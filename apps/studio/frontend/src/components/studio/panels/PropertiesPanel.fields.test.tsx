import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import type { SkillGraphNodeData } from '@/components/GraphCanvas'
import { PropertiesPanel } from './PropertiesPanel'

// Deprecated / FROZEN-violating frontmatter fields must never be EDITABLE in the
// Properties form (any node kind). Asserted via their rendered field labels.
const DEPRECATED_LABELS = [
  'System prompt',
  'Exit contract',
  'Python callable',
  'Target skill',
  'Max retries',
  'Max nudges',
]

const READ_ONLY_METADATA_LABELS = ['Phase ID', 'Node type', 'Depends On', 'Role', 'File']

function baseData(overrides: Partial<SkillGraphNodeData>): SkillGraphNodeData {
  return {
    skillId: 'demo',
    label: 'phase',
    mode: 'logic',
    status: 'idle',
    dependsOn: [],
    ...overrides,
  }
}

function renderPanel(args: {
  id: string
  data: SkillGraphNodeData
  filePath: string
  content: string
  files?: Record<string, string>
  graphTopology?: SkillDetail['graph_topology']
  workspaceRoot?: string | null
  onPhaseRename?: (phaseId: string, nextPhaseId: string) => void
}): string {
  const skillDetail = {
    files: { ...(args.files ?? {}), [args.filePath]: args.content },
    graph_topology: args.graphTopology ?? [],
  } as unknown as SkillDetail
  return renderToStaticMarkup(
    <PropertiesPanel
      skillId="demo"
      workspaceRoot={args.workspaceRoot ?? '/skills/demo'}
      skillDetail={skillDetail}
      selectedNode={{ id: args.id, data: args.data }}
      onPhaseRename={args.onPhaseRename}
    />,
  )
}

function expectNoReadOnlyMetadata(html: string) {
  for (const label of READ_ONLY_METADATA_LABELS) {
    expect(html).not.toContain(`>${label}<`)
  }
  expect(html).not.toContain('SKILL/LOGIC/SUBGRAPH.md')
  expect(html).not.toContain('not editable')
}

describe('PropertiesPanel - per-kind whitelist form (R3)', () => {
  it('agent node shows only llm_role / tools / subagents, never deprecated fields', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: ['---', 'name: review', 'llm_role: reviewer', '---', '<role>r</role>'].join('\n'),
    })

    expect(html).toContain('llm_role')
    expect(html).toContain('tools')
    expect(html).toContain('subagents')
    expect(html).toContain('allow_sequential_overwrite')
    expect(html).toContain('>iterate<')
    // No logic/subgraph-only editor controls.
    expect(html).not.toContain('Actions')
    expect(html).not.toContain('id="phase-path"')
    for (const label of DEPRECATED_LABELS) {
      expect(html).not.toContain(`>${label}<`)
    }
    expectNoReadOnlyMetadata(html)
  })

  it('agent node suggests allow_sequential_overwrite candidates from upstream outputs before compile', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: [
        '---',
        'name: review',
        'llm_role: reviewer',
        'io:',
        '  outputs:',
        '    properties:',
        '      events_raw: {type: string}',
        '---',
        '<role>r</role>',
      ].join('\n'),
      files: {
        'phases/draft/SKILL.md': [
          '---',
          'name: draft',
          'io:',
          '  outputs:',
          '    properties:',
          '      events_raw: {type: string}',
          '---',
          'Body',
        ].join('\n'),
      },
      graphTopology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
        { id: 'review', src: 'phases/review/SKILL.md', depends_on: ['draft'], mode: 'skill' },
      ],
    })

    expect(html).toContain('allow_sequential_overwrite')
    expect(html).toContain('events_raw')
    expect(html).toContain('from draft')
    expect(html).toContain('aria-label="Allow overwrite for events_raw"')
  })

  it('agent node shows the current allow_sequential_overwrite value from YAML', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: [
        '---',
        'name: review',
        'llm_role: reviewer',
        'allow_sequential_overwrite:',
        '  - events_raw',
        '---',
        '<role>r</role>',
      ].join('\n'),
    })

    expect(html).toContain('allow_sequential_overwrite')
    expect(html).toContain('events_raw')
  })

  it('logic node shows only actions / validator, never deprecated fields', () => {
    const html = renderPanel({
      id: 'normalize',
      data: baseData({ mode: 'logic', filePath: 'phases/normalize/LOGIC.md' }),
      filePath: 'phases/normalize/LOGIC.md',
      content: ['---', 'name: normalize', 'actions:', '  - strip_noise', '---', 'Body'].join('\n'),
    })

    expect(html).toContain('actions')
    expect(html).toContain('validator')
    expect(html).toContain('allow_sequential_overwrite')
    expect(html).toContain('>iterate<')
    expect(html).not.toContain('LLM role')
    expect(html).not.toContain('Subagents')
    expect(html).not.toContain('id="phase-path"')
    for (const label of DEPRECATED_LABELS) {
      expect(html).not.toContain(`>${label}<`)
    }
    expect(html).not.toContain('>tools<')
    expectNoReadOnlyMetadata(html)
  })

  // n2-properties #19 (atom #19): io.outputs field boundaries are owned by the
  // I/O panel, NOT Properties. A logic node must still carry a NON-blocking hint
  // pointing the author to the I/O panel so they don't assume "logic has no io
  // constraint". The hint is additive (a FieldDescription affordance) and must
  // not introduce any editable io field here.
  it('logic node surfaces a non-blocking io.outputs hint pointing to the I/O panel', () => {
    const html = renderPanel({
      id: 'normalize',
      data: baseData({ mode: 'logic', filePath: 'phases/normalize/LOGIC.md' }),
      filePath: 'phases/normalize/LOGIC.md',
      content: ['---', 'name: normalize', 'actions:', '  - strip_noise', '---', 'Body'].join('\n'),
    })

    // Mentions the io.outputs boundary and points to the I/O panel.
    expect(html).toContain('io.outputs')
    expect(html).toContain('I/O panel')
    // The hint is informational only - it must not add an editable output field
    // (those live in the I/O panel).
    expect(html).not.toContain('id="phase-outputs"')
  })

  it('subgraph node shows yaml-key fields for name / path / validator / iterate, never deprecated fields', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', subgraphPath: '/abs/child', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'path: /abs/child', '---', 'Body'].join('\n'),
    })

    expect(html).toContain('>name<')
    expect(html).toContain('>path<')
    expect(html).toContain('>validator<')
    expect(html).toContain('allow_sequential_overwrite')
    expect(html).toContain('>iterate<')
    expect(html).toContain('aria-label="Reconnect path"')
    expect(html).toContain('aria-label="About path"')
    expect(html).not.toContain('<input id="phase-name"')
    expect(html).not.toContain('<input id="phase-path"')
    expect(html).not.toContain('id="phase-io"')
    expect(html).not.toContain('aria-label="Open io panel"')
    expect(html).not.toContain('Reconnect child graph')
    expect(html).not.toContain('Subgraph target')
    expect(html).not.toContain('LLM role')
    expect(html).not.toContain('Actions')
    expect(html).not.toContain('Subagents')
    for (const label of DEPRECATED_LABELS) {
      expect(html).not.toContain(`>${label}<`)
    }
    expect(html).not.toContain('>tools<')
    expectNoReadOnlyMetadata(html)
  })

  it('subgraph node with a legacy child reference is treated as missing path in Properties', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'target_skill: legacy.registry.child', '---', 'Body'].join('\n'),
    })

    expect(html).toMatch(/id="phase-path"[^>]*aria-invalid="true"|aria-invalid="true"[^>]*id="phase-path"/)
    expect(html).toContain('Select a child graph folder')
    expect(html).not.toContain('legacy.registry.child')
    expect(html).not.toContain('Target skill')
  })

  // n2-properties #20: a subgraph phase whose SUBGRAPH.md declares no usable
  // `path` must render the Path value as invalid (red, via shadcn's
  // aria-invalid styling) AND surface the OS folder-picker import affordance.
  it('subgraph node with a missing path marks the target invalid and offers reconnect', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', '---', 'Body'].join('\n'),
    })

    // The Path value carries aria-invalid and uses semantic destructive text.
    expect(html).toMatch(/id="phase-path"[^>]*aria-invalid="true"|aria-invalid="true"[^>]*id="phase-path"/)
    expect(html).toContain('aria-label="Reconnect path"')
    expect(html).toContain('Select a child graph folder')
  })

  // A subgraph phase with a usable path resolves syntactically, so the
  // Path value is NOT marked invalid and the import affordance stays hidden (the
  // on-disk probe runs only client-side, never during this SSR render).
  it('subgraph node with a usable absolute path is not marked invalid', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', subgraphPath: '/abs/child', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'path: /abs/child', '---', 'Body'].join('\n'),
    })

    expect(html).not.toContain('aria-invalid="true"')
    expect(html).toContain('aria-label="Reconnect path"')
  })

  it('subgraph node with a relative path resolves against the skill root', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', subgraphPath: 'subgraph/child', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'path: subgraph/child', '---', 'Body'].join('\n'),
      workspaceRoot: '/skills/demo',
    })

    expect(html).not.toContain('aria-invalid="true"')
    expect(html).toContain('aria-label="Reconnect path"')
    expect(html).not.toContain('Reconnect selects')
  })

  it('subgraph node exposes rename through a dialog trigger, not a freeform inline input', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', subgraphPath: '/abs/child', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'path: /abs/child', '---', 'Body'].join('\n'),
      onPhaseRename: () => undefined,
    })

    expect(html).toContain('aria-label="Rename phase"')
    expect(html).not.toContain('id="phase-rename-input"')
  })

  it('batch iterate settings surface the stable iterate YAML fields', () => {
    const html = renderPanel({
      id: 'worker',
      data: baseData({ mode: 'logic', filePath: 'phases/worker/LOGIC.md' }),
      filePath: 'phases/worker/LOGIC.md',
      content: [
        '---',
        'name: worker',
        'actions:',
        '  - worker',
        'iterate:',
        '  mode: batch',
        '  over: data.inputs.items',
        '  item_var: item',
        '  range: [2, 3]',
        '  concurrency: 2',
        '---',
        'Body',
      ].join('\n'),
    })

    expect(html).toContain('>iterate<')
    expect(html).toContain('id="phase-iterate-mode"')
    expect(html).toContain('id="phase-iterate-over"')
    expect(html).toContain('value="data.inputs.items"')
    expect(html).toContain('id="phase-iterate-item-var"')
    expect(html).toContain('value="item"')
    expect(html).toContain('aria-label="iterate range start"')
    expect(html).toContain('value="2"')
    expect(html).toContain('aria-label="iterate range end"')
    expect(html).toContain('value="3"')
    expect(html).toContain('id="phase-iterate-concurrency"')
  })

  it('loop iterate settings surface accumulator fields', () => {
    const html = renderPanel({
      id: 'collect',
      data: baseData({ mode: 'logic', filePath: 'phases/collect/LOGIC.md' }),
      filePath: 'phases/collect/LOGIC.md',
      content: [
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
      ].join('\n'),
    })

    expect(html).toContain('accumulate.var')
    expect(html).toContain('id="phase-iterate-accumulate-var"')
    expect(html).toContain('value="collected"')
    expect(html).toContain('accumulate.init')
    expect(html).toContain('id="phase-iterate-accumulate-init"')
    expect(html).toContain('value="[]"')
    expect(html).toContain('accumulate.from')
    expect(html).toContain('id="phase-iterate-accumulate-from"')
    expect(html).toContain('value="piece"')
    expect(html).toContain('accumulate.merge')
  })
})

describe('PropertiesPanel - editable-only surface', () => {
  it('does not render immutable node metadata beside the editable agent form', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({
        mode: 'llm',
        filePath: 'phases/review/SKILL.md',
        dependsOn: ['setup'],
        role: 'readonly-role',
        tools: ['readonly-tool'],
      }),
      filePath: 'phases/review/SKILL.md',
      content: ['---', 'name: review', 'llm_role: reviewer', '---', '<role>r</role>'].join('\n'),
    })

    expect(html).toContain('llm_role')
    expect(html).toContain('tools')
    expectNoReadOnlyMetadata(html)
    expect(html).not.toContain('setup')
    expect(html).not.toContain('readonly-role')
    expect(html).not.toContain('readonly-tool')
  })

  it('does not render role/tools/file metadata for non-agent nodes', () => {
    const html = renderPanel({
      id: 'normalize',
      data: baseData({
        mode: 'logic',
        filePath: 'phases/normalize/LOGIC.md',
        dependsOn: ['input'],
        role: 'ignored-role',
        tools: ['ignored-tool'],
      }),
      filePath: 'phases/normalize/LOGIC.md',
      content: ['---', 'name: normalize', 'actions:', '  - strip_noise', '---', 'Body'].join('\n'),
    })

    expect(html).toContain('actions')
    expect(html).not.toContain('LLM role')
    expect(html).not.toContain('>tools<')
    expectNoReadOnlyMetadata(html)
    expect(html).not.toContain('ignored-role')
    expect(html).not.toContain('ignored-tool')
  })
})

describe('PropertiesPanel - node role Test control (R23)', () => {
  it('agent node renders a Test button next to the llm_role field', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: ['---', 'name: review', 'llm_role: reviewer', '---', '<role>r</role>'].join('\n'),
    })

    expect(html).toContain('llm_role')
    expect(html).toContain('>Test<')
  })

  it('logic node has no role Test control', () => {
    const html = renderPanel({
      id: 'normalize',
      data: baseData({ mode: 'logic', filePath: 'phases/normalize/LOGIC.md' }),
      filePath: 'phases/normalize/LOGIC.md',
      content: ['---', 'name: normalize', 'actions:', '  - strip_noise', '---', 'Body'].join('\n'),
    })

    expect(html).not.toContain('>Test<')
  })

  it('subgraph node has no role Test control', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', subgraphPath: '/abs/child', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'path: /abs/child', '---', 'Body'].join('\n'),
    })

    expect(html).not.toContain('>Test<')
  })
})
