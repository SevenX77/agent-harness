import { renderToStaticMarkup } from 'react-dom/server'
import type { ComponentProps, ReactElement, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { RoleEntry, RolesData } from '../../api/llm'
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

function role(roleKind: RoleEntry['role_kind']): RoleEntry {
  return {
    role_kind: roleKind,
    model_fallback_enabled: true,
    active_model: '',
    models: {},
    system_prompt_prefix: '',
    fallback_chain: [],
    lint_requirements: {},
  }
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
