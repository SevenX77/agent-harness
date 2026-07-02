import { renderToStaticMarkup } from 'react-dom/server'
import type { ComponentProps, ReactElement, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { CredentialsState, ModelGroup, RoleEntry, RolesData } from '../../api/llm'
import { RolePicker, copilotRoleOptions, type CopilotRoleOption } from './role-picker'

vi.mock('../ui/button', () => ({
  Button: ({
    children,
    ...props
  }: ComponentProps<'button'> & { children: ReactNode }) => (
    <button data-slot="button" {...props}>
      {children}
    </button>
  ),
}))

vi.mock('../ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div data-slot="dropdown-menu">{children}</div>,
  DropdownMenuContent: ({ children, className }: { children: ReactNode; className?: string }) => (
    <div className={className} data-slot="dropdown-menu-content">
      {children}
    </div>
  ),
  DropdownMenuItem: ({
    children,
    onSelect,
    ...props
  }: {
    children: ReactNode
    onSelect?: () => void
  } & ComponentProps<'div'>) => (
    <div data-slot="dropdown-menu-item" onClick={onSelect} {...props}>
      {children}
    </div>
  ),
  DropdownMenuLabel: ({ children }: { children: ReactNode }) => (
    <div data-slot="dropdown-menu-label">{children}</div>
  ),
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => (
    <div data-slot="dropdown-menu-trigger">{children}</div>
  ),
}))

function role(roleKind: RoleEntry['role_kind'], overrides: Partial<RoleEntry> = {}): RoleEntry {
  return {
    role_kind: roleKind,
    model_fallback_enabled: true,
    active_model: '',
    models: {},
    system_prompt_prefix: '',
    fallback_chain: [],
    lint_requirements: {},
    ...overrides,
  }
}

function routeGroup(canonicalId: string, displayName: string): ModelGroup {
  return {
    canonical_id: canonicalId,
    display_name: displayName,
    provider_models: [
      {
        route_id: `anthropic-official:${canonicalId}`,
        endpoint_id: 'anthropic-official',
        provider_label: 'Anthropic Official',
        provider_kind: 'official',
        provider_model_id: canonicalId,
        ui_state: 'ready',
        ui_detail: null,
        retry_at: null,
        reason_code: null,
        capability_state: 'known',
        capabilities: {},
        call_method_id: 'anthropic_messages',
      },
    ],
    status_summary: { ready: 1, historical_ready: 0, untested: 0, cooling_down: 0, failed: 0, off: 0 },
    capability_summary: {
      capability_known_count: 1,
      thinking: 'unknown',
      tools: 'unknown',
      structured_output: 'unknown',
      max_context_tokens: null,
      max_output_tokens: null,
    },
  }
}

const credentials: CredentialsState = {
  providers: [
    {
      id: 'anthropic-official',
      name: 'Anthropic Official',
      provider_type: 'anthropic_compatible',
      api_key: '**********',
    },
  ],
}

const modelGroups = [
  routeGroup('claude-opus-4.8', 'Claude Opus 4.8'),
  routeGroup('claude-opus-4.7', 'Claude Opus 4.7'),
]

// F3 sync contract (docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md):
// composer options == the Settings Copilot display roles that are actually
// configured (bound model group / non-empty fallback chain).
describe('copilotRoleOptions', () => {
  it('returns an empty list for null data', () => {
    expect(copilotRoleOptions(null)).toEqual([])
  })

  it('mirrors Settings: configured roles kept, empty drafts and broken legacy roles excluded', () => {
    const settingsRoles: RolesData = {
      models: {},
      providers: {},
      roles: {
        copilot_claude_opus_4_8: role('copilot', {
          active_model: 'claude-opus-4.8',
          models: {
            'claude-opus-4.8': { providers: ['anthropic-official:claude-opus-4.8'] },
          },
          fallback_chain: [{ route_id: 'anthropic-official:claude-opus-4.8', runtime_settings: {} }],
        }),
        copilot_claude_opus_4_7: role('copilot', {
          active_model: 'claude-opus-4.7',
          models: {
            'claude-opus-4.7': { providers: ['anthropic-official:claude-opus-4.7'] },
          },
          fallback_chain: [{ route_id: 'anthropic-official:claude-opus-4.7', runtime_settings: {} }],
        }),
        // broken legacy: fallback_chain without any model binding
        copilot_custom_1: role('copilot', {
          fallback_chain: [{ route_id: 'stale-provider:stale-model', runtime_settings: {} }],
        }),
        // empty draft: shows as a "Drop model" card in Settings, not a usable chat role
        copilot_custom_2: role('copilot'),
        graph_planner: role('graph_agent'),
      },
    }

    const options = copilotRoleOptions(settingsRoles, modelGroups, credentials)

    expect(options.map(({ role: id, label, persisted }) => ({ role: id, label, persisted }))).toEqual([
      { role: 'copilot_claude_opus_4_8', label: 'Claude Opus 4.8', persisted: true },
      { role: 'copilot_claude_opus_4_7', label: 'Claude Opus 4.7', persisted: true },
    ])
    expect(options[0].fallbackChain).toEqual([
      { route_id: 'anthropic-official:claude-opus-4.8', runtime_settings: {} },
    ])
    expect(options[0].modelGroupId).toBe('claude-opus-4.8')
  })

  it('excludes copilot roles that have no bound model group', () => {
    const bare: RolesData = {
      models: {},
      providers: {},
      roles: {
        copilot_chat: role('copilot'),
        copilot_judge: role('copilot'),
      },
    }

    expect(copilotRoleOptions(bare, modelGroups, credentials)).toEqual([])
  })

  it('labels a role bound to a non-anthropic-eligible group from the FULL group list (same as Settings)', () => {
    // Spec 2.5: the Available Models sidebar is NOT pre-filtered by SDK
    // compatibility, so a copilot role may bind any model group. The composer
    // label must still come from the group display_name, like Settings cards.
    const incompatible: ModelGroup = {
      ...routeGroup('claude-sonnet-4-5-20250929', 'Claude Sonnet 4.5'),
      provider_models: [{
        ...routeGroup('claude-sonnet-4-5-20250929', 'Claude Sonnet 4.5').provider_models[0],
        call_method_id: 'openai_chat_completions',
      }],
    }
    const settingsRoles: RolesData = {
      models: {},
      providers: {},
      roles: {
        copilot_custom_2: role('copilot', {
          active_model: 'claude-sonnet-4-5-20250929',
          models: {
            'claude-sonnet-4-5-20250929': { providers: ['anthropic-official:claude-sonnet-4-5-20250929'] },
          },
          fallback_chain: [{ route_id: 'anthropic-official:claude-sonnet-4-5-20250929', runtime_settings: {} }],
        }),
      },
    }

    const options = copilotRoleOptions(settingsRoles, [...modelGroups, incompatible], credentials)

    expect(options.map(({ role: id, label }) => ({ role: id, label }))).toEqual([
      { role: 'copilot_custom_2', label: 'Claude Sonnet 4.5' },
    ])
  })

  it('floats the built-in defaults when no copilot role is persisted (same as Settings)', () => {
    const noCopilotRoles: RolesData = {
      models: {},
      providers: {},
      roles: { graph_planner: role('graph_agent') },
    }

    const options = copilotRoleOptions(noCopilotRoles, modelGroups, credentials)

    expect(options.map(({ role: id, label, persisted, modelGroupId }) => ({ role: id, label, persisted, modelGroupId }))).toEqual([
      { role: 'claude-opus-4.8', label: 'Claude Opus 4.8', persisted: false, modelGroupId: 'claude-opus-4.8' },
    ])
    expect(options[0].fallbackChain).toEqual([
      { route_id: 'anthropic-official:claude-opus-4.8', runtime_settings: {} },
    ])
  })
})

function option(id: string, label: string, overrides: Partial<CopilotRoleOption> = {}): CopilotRoleOption {
  return {
    role: id,
    label,
    fallbackChain: [{ route_id: `anthropic-official:${id}`, runtime_settings: {} }],
    persisted: true,
    modelGroupId: id,
    ...overrides,
  }
}

type MenuItemElement = ReactElement<{
  onSelect?: () => void
  children?: ReactNode
}>

describe('RolePicker', () => {
  const options = [
    option('copilot_claude_opus_4_8', 'Claude Opus 4.8'),
    option('copilot_claude_opus_4_7', 'Claude Opus 4.7'),
  ]

  it('lists every configured copilot role option', () => {
    const html = renderToStaticMarkup(
      <RolePicker
        options={options}
        selectedRole="copilot_claude_opus_4_8"
        onSelect={() => undefined}
      />,
    )

    expect(html).toContain('Claude Opus 4.8')
    expect(html).toContain('Claude Opus 4.7')
    expect(html).toContain('Copilot role')
  })

  // R6-1 (PM 2026-07-02, overrides the old F6 "render nothing" rule): the role
  // anchor must NEVER vanish — the PM deleted roles down to one floated default
  // and the whole model selector disappeared. One option still renders visibly.
  it('still shows the single role as a visible anchor (never vanishes)', () => {
    const html = renderToStaticMarkup(
      <RolePicker
        options={[option('copilot_claude_opus_4_8', 'Claude Opus 4.8')]}
        selectedRole="copilot_claude_opus_4_8"
        onSelect={() => undefined}
      />,
    )

    expect(html).not.toBe('')
    expect(html).toContain('Claude Opus 4.8')
  })

  // R6-1: with zero configured/floated roles the anchor still renders an
  // explicit empty state (not an empty row) so the user knows where to look.
  it('renders an empty-state anchor when there are no roles at all', () => {
    const html = renderToStaticMarkup(
      <RolePicker options={[]} selectedRole="" onSelect={() => undefined} />,
    )

    expect(html).not.toBe('')
    expect(html).toContain('No copilot role')
  })

  it('calls onSelect with the chosen role when a menu item is selected', () => {
    const onSelect = vi.fn()
    const element = RolePicker({
      options,
      selectedRole: 'copilot_claude_opus_4_8',
      onSelect,
    }) as ReactElement<{ children: ReactNode[] }>

    // DropdownMenu > [trigger, content]; content children = [label, ...items]
    const content = element.props.children[1] as ReactElement<{ children: ReactNode[] }>
    const items = content.props.children.flat() as MenuItemElement[]
    const secondItem = items.find((item) => item.key === 'copilot_claude_opus_4_7')

    secondItem?.props.onSelect?.()

    expect(onSelect).toHaveBeenCalledWith('copilot_claude_opus_4_7')
  })
})
