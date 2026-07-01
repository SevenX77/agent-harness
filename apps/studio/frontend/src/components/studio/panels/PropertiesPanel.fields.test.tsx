import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { ModelGroup, RolesData } from '@/api/llm'
import type { SkillDetail } from '@/api/types'
import type { SkillGraphNodeData } from '@/components/GraphCanvas'
import {
  compareModelGroupsForPicker,
  graphAgentRoleNamesForProperties,
  LlmCompareCandidateRow,
  LlmCompareTestResultPanel,
  llmCompareModelGroupFilter,
  llmCompareModelGroupSearchValue,
  llmRoleSelectOptionState,
  modelGroupRouteOptions,
  PropertiesPanel,
  RoleTestControl,
  roleEndpointRouteOptions,
} from './PropertiesPanel'

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

function providerModel(overrides: Partial<ModelGroup['provider_models'][number]> = {}): ModelGroup['provider_models'][number] {
  return {
    route_id: 'qiniu-main:llama3',
    endpoint_id: 'qiniu-main',
    provider_label: 'Qiniu',
    provider_kind: 'custom',
    provider_model_id: 'llama3',
    ui_state: 'ready',
    capability_state: 'known',
    capabilities: {},
    ...overrides,
  } as ModelGroup['provider_models'][number]
}

function modelGroup(overrides: Partial<ModelGroup> = {}): ModelGroup {
  return {
    canonical_id: 'llama3',
    display_name: 'Llama 3',
    provider_models: [providerModel()],
    status_summary: {
      ready: 1,
      historical_ready: 0,
      untested: 0,
      cooling_down: 0,
      failed: 0,
      off: 0,
    },
    capability_summary: {
      capability_known_count: 0,
      thinking: 'unknown',
      tools: 'unknown',
      structured_output: 'unknown',
    },
    ...overrides,
  } as ModelGroup
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

describe('PropertiesPanel - node compare model group picker', () => {
  it('filters invalid model groups so the picker never renders a blank option', () => {
    const groups = compareModelGroupsForPicker([
      modelGroup({ canonical_id: '', display_name: '', provider_models: [providerModel()] }),
      modelGroup({ canonical_id: 'empty-routes', display_name: 'Empty routes', provider_models: [] }),
      modelGroup({ canonical_id: 'blank-route', display_name: 'Blank route', provider_models: [providerModel({ route_id: ' ' })] }),
      modelGroup({ canonical_id: 'claude-sonnet', display_name: 'Claude Sonnet' }),
    ])

    expect(groups.map((group) => group.canonical_id)).toEqual(['claude-sonnet'])
  })

  it('searches model groups by name, id, provider, endpoint, and route', () => {
    const group = modelGroup({
      canonical_id: 'claude-sonnet-4-5',
      display_name: 'Claude Sonnet 4.5',
      provider_models: [
        providerModel({
          route_id: 'qiniu-main:claude-sonnet-4-5',
          endpoint_id: 'qiniu-main',
          provider_model_id: 'claude-sonnet-4-5',
        }),
      ],
    })
    const value = llmCompareModelGroupSearchValue(group)

    expect(llmCompareModelGroupFilter(value, 'sonnet qiniu')).toBe(1)
    expect(llmCompareModelGroupFilter(value, 'claude-sonnet-4-5')).toBe(1)
    expect(llmCompareModelGroupFilter(value, 'qiniu-main')).toBe(1)
    expect(llmCompareModelGroupFilter(value, 'openai qiniu')).toBe(0)
  })

  it('sorts model groups by the same family section used by LLM Roles available models', () => {
    const groups = compareModelGroupsForPicker([
      modelGroup({
        canonical_id: 'deepseek-v4',
        display_name: 'A DeepSeek via proxy',
        provider_models: [
          providerModel({
            route_id: 'anthropic-proxy:deepseek-v4',
            endpoint_id: 'anthropic-proxy',
            provider_label: 'Qiniu',
            provider_model_id: 'deepseek-v4',
          }),
        ],
      }),
      modelGroup({
        canonical_id: 'claude-opus-4-8',
        display_name: 'Z Claude Opus 4.8',
        provider_models: [
          providerModel({
            route_id: 'anthropic:claude-opus-4-8',
            endpoint_id: 'anthropic',
            provider_label: 'Anthropic Official',
            provider_model_id: 'claude-opus-4.8',
          }),
        ],
      }),
    ])

    expect(groups.map((group) => group.canonical_id)).toEqual([
      'claude-opus-4-8',
      'deepseek-v4',
    ])
  })

  it('deduplicates endpoint options, shows readable names, and keeps endpoint details for tooltip', () => {
    const group = modelGroup({
      provider_models: [
        providerModel({ route_id: 'qiniu-main:llama3', endpoint_id: 'qiniu-main' }),
        providerModel({ route_id: 'qiniu-main:llama3', endpoint_id: 'qiniu-main' }),
        providerModel({ route_id: 'qiniu-backup:llama3', endpoint_id: 'qiniu-backup' }),
        providerModel({ route_id: ' ', endpoint_id: 'empty' }),
      ],
    })

    expect(modelGroupRouteOptions(group)).toEqual([
      {
        value: 'route:qiniu-main:llama3',
        label: 'Qiniu',
        detail: 'Endpoint: qiniu-main\nModel: llama3\nRoute: qiniu-main:llama3',
      },
      {
        value: 'route:qiniu-backup:llama3',
        label: 'Qiniu',
        detail: 'Endpoint: qiniu-backup\nModel: llama3\nRoute: qiniu-backup:llama3',
      },
    ])
  })

  it('derives endpoint options for a configured role from its fallback chain', () => {
    const group = modelGroup({
      provider_models: [
        providerModel({ route_id: 'wavespeed:claude-opus-4-8', endpoint_id: 'wavespeed', provider_label: 'WaveSpeed', provider_model_id: 'anthropic/claude-opus-4.8' }),
        providerModel({ route_id: 'anthropic:claude-opus-4-8', endpoint_id: 'anthropic', provider_label: 'Anthropic Official', provider_model_id: 'claude-opus-4.8' }),
      ],
    })

    expect(roleEndpointRouteOptions({
      model_fallback_enabled: true,
      active_model: 'claude-opus-4-8',
      models: {},
      fallback_chain: [
        { route_id: 'wavespeed:claude-opus-4-8' },
        { route_id: 'anthropic:claude-opus-4-8' },
      ],
    }, [group])).toEqual([
      {
        value: 'route:wavespeed:claude-opus-4-8',
        label: 'WaveSpeed',
        detail: 'Endpoint: wavespeed\nModel: anthropic/claude-opus-4.8\nRoute: wavespeed:claude-opus-4-8',
      },
      {
        value: 'route:anthropic:claude-opus-4-8',
        label: 'Anthropic Official',
        detail: 'Endpoint: anthropic\nModel: claude-opus-4.8\nRoute: anthropic:claude-opus-4-8',
      },
    ])
  })

  it('renders compare candidates as provider-style blocks with Test and no Model label', () => {
    const html = renderToStaticMarkup(
      <LlmCompareCandidateRow
        candidate={{ id: 'compare-1', modelGroupId: 'llama3', route: 'route:qiniu-main:llama3' }}
        modelGroups={[modelGroup()]}
        testState={{
          running: false,
          result: {
            status: 'ok',
            summary: 'Qiniu route passed.',
            details: ['Provider Qiniu responded successfully.'],
          },
        }}
        onTest={() => undefined}
        onEdit={() => undefined}
        onRemove={() => undefined}
      />,
    )

    expect(html).toContain('data-llm-compare-model-card="true"')
    expect(html).toContain('data-llm-compare-test-trigger="true"')
    expect(html).toContain('data-llm-compare-test-icon="true"')
    expect(html).toContain('data-llm-compare-status-light="true"')
    expect(html).toContain('Qiniu route passed.')
    expect(html).not.toContain('>Model<')
  })

  it('renders compare Test results with warning details', () => {
    const html = renderToStaticMarkup(
      <LlmCompareTestResultPanel
        state={{
          running: false,
          result: {
            status: 'warning',
            summary: 'Needs Attention',
            details: ['Provider skipped this route because thinking capability is unknown.'],
          },
        }}
      />,
    )

    expect(html).toContain('data-llm-compare-test-result="true"')
    expect(html).toContain('Needs Attention')
    expect(html).toContain('Provider skipped this route because thinking capability is unknown.')
  })
})

describe('PropertiesPanel - role options', () => {
  it('hides copilot roles from llm_role while keeping graph-agent roles with copilot-like names', () => {
    const data = {
      roles: {
        'loop pm': { role_kind: 'graph_agent' },
        copilot_claude_opus_4_8: { role_kind: 'copilot' },
        copilot_named_graph_agent: { role_kind: 'graph_agent' },
      },
    } as unknown as Pick<RolesData, 'roles'>

    expect(graphAgentRoleNamesForProperties(data)).toEqual([
      'copilot_named_graph_agent',
      'loop pm',
    ])
  })

  it('marks yaml llm_role values that are not configured', () => {
    expect(llmRoleSelectOptionState('reviewer', false)).toEqual({
      label: 'reviewer (not configured)',
      title: 'reviewer is not configured in LLM Roles',
      unconfigured: true,
    })
    expect(llmRoleSelectOptionState('loop pm', true)).toEqual({
      label: 'loop pm',
      unconfigured: false,
    })
  })
})

describe('PropertiesPanel - node role Test control (R23)', () => {
  it('agent node renders a compact primary Test icon next to the llm_role field', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: ['---', 'name: review', 'llm_role: reviewer', '---', '<role>r</role>'].join('\n'),
    })

    expect(html).toContain('llm_role')
    expect(html).toContain('id="phase-llm-role"')
    expect(html).toContain('role="combobox"')
    expect(html).toContain('>Run role<')
    expect(html).toContain('>Compare LLMs<')
    expect(html).not.toContain('id="phase-llm-endpoint"')
    expect(html).toContain('data-llm-role-settings-trigger="true"')
    expect(html).toContain('aria-label="Open LLM Roles settings"')
    expect(html).toContain('data-llm-role-test-trigger="true"')
    expect(html).toContain('data-variant="default"')
    expect(html).toContain('data-llm-role-test-icon="true"')
  })

  it('role Test status badge exposes detailed diagnostics in a tooltip', () => {
    const html = renderToStaticMarkup(
      <RoleTestControl
        roleName="reviewer"
        roleTest={{
          running: false,
          status: 'warning',
          details: ['Thinking capability is unknown for Qiniu.'],
        }}
        onRoleTest={() => undefined}
      />,
    )

    expect(html).toContain('data-role-test-status-tooltip="true"')
    expect(html).toContain('Needs Attention')
    expect(html).toContain('Thinking capability is unknown for Qiniu.')
  })

  it('agent node renders the MVP1 node-scoped multi-LLM compare trigger next to llm_role', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: ['---', 'name: review', 'llm_role: reviewer', '---', '<role>r</role>'].join('\n'),
    })

    expect(html).toContain('llm_role')
    expect(html).toContain('data-llm-role-compare-trigger="true"')
    expect(html).toContain('aria-label="Add LLM compare candidate"')
    expect(html).toContain('No compare LLMs yet.')
    expect(html).toContain('Add compare LLM</button>')
    expect(html).not.toContain('Add temporary candidates for this node only')
    expect(html).not.toContain('>Model bundle<')
    expect(html).not.toContain('Node LLM compare')
    expect(html).not.toContain('Node-scoped runner')
  })

  it('logic node has no role Test control', () => {
    const html = renderPanel({
      id: 'normalize',
      data: baseData({ mode: 'logic', filePath: 'phases/normalize/LOGIC.md' }),
      filePath: 'phases/normalize/LOGIC.md',
      content: ['---', 'name: normalize', 'actions:', '  - strip_noise', '---', 'Body'].join('\n'),
    })

    expect(html).not.toContain('>Test<')
    expect(html).not.toContain('data-llm-role-compare-trigger="true"')
  })

  it('subgraph node has no role Test control', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', subgraphPath: '/abs/child', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'path: /abs/child', '---', 'Body'].join('\n'),
    })

    expect(html).not.toContain('>Test<')
    expect(html).not.toContain('data-llm-role-compare-trigger="true"')
  })
})
