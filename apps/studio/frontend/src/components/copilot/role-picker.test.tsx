import { renderToStaticMarkup } from 'react-dom/server'
import type { ComponentProps, ReactElement, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { CredentialsState, ModelGroup, RoleEntry, RolesData } from '../../api/llm'
import { DEFAULT_COPILOT_ROLE, RolePicker, copilotRoleOptions } from './role-picker'

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

const rolesData: RolesData = {
  models: {},
  providers: {},
  roles: {
    copilot_chat: role('copilot'),
    copilot_judge: role('copilot'),
    graph_planner: role('graph_agent'),
  },
}

describe('copilotRoleOptions', () => {
  it('keeps only copilot-kind roles and label-cases their names', () => {
    const options = copilotRoleOptions(rolesData)

    expect(options).toEqual([
      { role: 'copilot_chat', label: 'Copilot Chat' },
      { role: 'copilot_judge', label: 'Copilot Judge' },
    ])
  })

  it('drops graph_agent roles', () => {
    const options = copilotRoleOptions(rolesData)

    expect(options.some((option) => option.role === 'graph_planner')).toBe(false)
  })

  it('returns an empty list for null data', () => {
    expect(copilotRoleOptions(null)).toEqual([])
  })

  it('mirrors Copilot settings labels and skips broken legacy copilot roles', () => {
    const settingsRoles: RolesData = {
      ...rolesData,
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
        copilot_custom_1: role('copilot', {
          fallback_chain: [{ route_id: 'stale-provider:stale-model', runtime_settings: {} }],
        }),
        copilot_custom_2: role('copilot'),
        graph_planner: role('graph_agent'),
      },
    }

    expect(copilotRoleOptions(settingsRoles, [
      routeGroup('claude-opus-4.8', 'Claude Opus 4.8'),
      routeGroup('claude-opus-4.7', 'Claude Opus 4.7'),
    ], credentials)).toEqual([
      { role: 'copilot_claude_opus_4_8', label: 'Claude Opus 4.8' },
      { role: 'copilot_claude_opus_4_7', label: 'Claude Opus 4.7' },
      { role: 'copilot_custom_2', label: 'Copilot Custom 2' },
    ])
  })

  it('defaults to copilot_chat', () => {
    expect(DEFAULT_COPILOT_ROLE).toBe('copilot_chat')
  })
})

type MenuItemElement = ReactElement<{
  onSelect?: () => void
  children?: ReactNode
}>

describe('RolePicker', () => {
  it('lists every copilot-kind role option', () => {
    const html = renderToStaticMarkup(
      <RolePicker
        options={copilotRoleOptions(rolesData)}
        selectedRole={DEFAULT_COPILOT_ROLE}
        onSelect={() => undefined}
      />,
    )

    expect(html).toContain('Copilot Chat')
    expect(html).toContain('Copilot Judge')
    expect(html).toContain('Copilot role')
  })

  it('hides the picker when only one copilot role is available', () => {
    const html = renderToStaticMarkup(
      <RolePicker
        options={[{ role: 'copilot_chat', label: 'Copilot Chat' }]}
        selectedRole="copilot_chat"
        onSelect={() => undefined}
      />,
    )

    expect(html).toBe('')
  })

  it('calls onSelect with the chosen role when a menu item is selected', () => {
    const onSelect = vi.fn()
    const element = RolePicker({
      options: copilotRoleOptions(rolesData),
      selectedRole: DEFAULT_COPILOT_ROLE,
      onSelect,
    }) as ReactElement<{ children: ReactNode[] }>

    // DropdownMenu > [trigger, content]; content children = [label, ...items]
    const content = element.props.children[1] as ReactElement<{ children: ReactNode[] }>
    const items = content.props.children.flat() as MenuItemElement[]
    const judgeItem = items.find((item) => item.key === 'copilot_judge')

    judgeItem?.props.onSelect?.()

    expect(onSelect).toHaveBeenCalledWith('copilot_judge')
  })
})
