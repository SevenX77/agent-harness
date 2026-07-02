import { renderToStaticMarkup } from 'react-dom/server'
import type { ComponentProps, ReactElement, ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { RegistryResponse, RoleEntry } from '../../../api/llm'
import {
  firstAvailableRoute,
  getRouteOptions,
  ModelPicker,
  ModelPickerMenu,
} from '../model-picker'

vi.mock('../../ui/button', () => ({
  Button: ({
    children,
    ...props
  }: ComponentProps<'button'> & { children: ReactNode }) => (
    <button data-slot="button" {...props}>
      {children}
    </button>
  ),
}))

vi.mock('../../ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div data-slot="dropdown-menu">{children}</div>,
  DropdownMenuContent: ({ children, className }: { children: ReactNode; className?: string }) => (
    <div className={className} data-slot="dropdown-menu-content">
      {children}
    </div>
  ),
  DropdownMenuItem: ({
    children,
    disabled,
    onSelect,
    ...props
  }: {
    children: ReactNode
    disabled?: boolean
    onSelect?: () => void
  } & ComponentProps<'div'>) => (
    <div data-disabled={disabled} data-slot="dropdown-menu-item" onClick={onSelect} {...props}>
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

const role: RoleEntry = {
  model_fallback_enabled: true,
  active_model: '',
  models: {},
  system_prompt_prefix: '',
  fallback_chain: [
    { route_id: 'anthropic-official:claude-sonnet' },
    { route_id: 'openrouter:anthropic-claude-sonnet' },
    { route_id: 'disabled:route' },
  ],
  lint_requirements: {},
}

const registry: RegistryResponse = {
  provider_endpoints: {},
  provider_routes: {
    'anthropic-official:claude-sonnet': {
      route_id: 'anthropic-official:claude-sonnet',
      endpoint_id: 'anthropic-official',
      route_slug: 'claude-sonnet',
      provider_model_id: 'claude-sonnet',
      canonical_id: 'claude-sonnet',
      display_name: 'Claude Sonnet',
      status: 'verified',
      ui_state: 'ready',
      capabilities: {},
      metadata: {},
    },
    'openrouter:anthropic-claude-sonnet': {
      route_id: 'openrouter:anthropic-claude-sonnet',
      endpoint_id: 'openrouter',
      route_slug: 'anthropic-claude-sonnet',
      provider_model_id: 'anthropic/claude-sonnet',
      canonical_id: 'claude-sonnet',
      display_name: 'Claude Sonnet via OpenRouter',
      status: 'unverified_manual',
      ui_state: 'untested',
      capabilities: {},
      metadata: {},
    },
    'disabled:route': {
      route_id: 'disabled:route',
      endpoint_id: 'disabled',
      route_slug: 'route',
      provider_model_id: 'disabled-route',
      canonical_id: 'disabled-route',
      display_name: 'Disabled Route',
      status: 'disabled',
      ui_state: 'off',
      capabilities: {},
      metadata: {},
    },
  },
  runtime_policy: {
    provider_down_ttl_seconds: 300,
    probe_timeout_seconds: 30,
    token_escalation_rounds: 2,
  },
  model_profiles: {},
  model_groups: [],
  roles: { copilot_chat: role },
  canonical_groups: [],
  lint_results: [],
  setup_required: false,
}

type MenuButtonElement = ReactElement<{
  disabled?: boolean
  onClick?: () => void
}>

function renderMenuHtml(selectedRouteId = 'anthropic-official:claude-sonnet') {
  return renderToStaticMarkup(
    <ModelPicker
      role={role}
      registry={registry}
      selectedRouteId={selectedRouteId}
      onSelect={() => undefined}
      variant="full"
    />,
  )
}

describe('ModelPicker', () => {
  it('renders exact route IDs from the role fallback chain', () => {
    const html = renderMenuHtml()

    expect(html).toContain('anthropic-official:claude-sonnet')
    expect(html).toContain('openrouter:anthropic-claude-sonnet')
  })

  it('disables routes that are missing or disabled in the active registry', () => {
    const options = getRouteOptions(role, registry)

    expect(options.find((option) => option.routeId === 'disabled:route')?.available).toBe(false)
  })

  it('calls onSelect with exact route_id when an available route is selected', () => {
    const onSelect = vi.fn()
    const options = getRouteOptions(role, registry)
    const element = ModelPickerMenu({ options, selectedRouteId: 'openrouter:anthropic-claude-sonnet', onSelect })
    // Each route renders as a keyed wrapper (span, or Tooltip for disabled
    // routes) around the Button — walk down to the first element with onClick.
    const wrappers: MenuButtonElement[] = Array.isArray(element.props.children)
      ? element.props.children
      : [element.props.children]
    const findClickable = (node: unknown): { onClick?: () => void } | null => {
      if (Array.isArray(node)) {
        for (const child of node) {
          const hit = findClickable(child)
          if (hit) return hit
        }
        return null
      }
      if (!node || typeof node !== 'object') return null
      const el = node as { props?: { onClick?: () => void; children?: unknown } }
      if (typeof el.props?.onClick === 'function') return el.props
      return findClickable(el.props?.children)
    }
    const route = wrappers.find((wrapper) => wrapper.key === 'anthropic-official:claude-sonnet')
    findClickable(route)?.onClick?.()

    expect(onSelect).toHaveBeenCalledWith('anthropic-official:claude-sonnet')
  })

  it('renders the icon variant trigger', () => {
    const html = renderToStaticMarkup(
      <ModelPicker
        role={role}
        registry={registry}
        selectedRouteId="anthropic-official:claude-sonnet"
        onSelect={() => undefined}
      />,
    )

    expect(html).toContain('Select Copilot route')
    expect(html).toContain('data-slot="dropdown-menu"')
    expect(html).toContain('data-slot="dropdown-menu-trigger"')
    expect(html).toContain('data-slot="button"')
  })

  it('renders nothing without role data (no dead placeholder controls)', () => {
    const html = renderToStaticMarkup(
      <ModelPicker
        role={null}
        registry={registry}
        selectedRouteId=""
        onSelect={() => undefined}
      />,
    )

    expect(html).toBe('')
  })

  it('hides the icon variant when the chain has a single route (F6: nothing to choose)', () => {
    const html = renderToStaticMarkup(
      <ModelPicker
        role={{ fallback_chain: [{ route_id: 'anthropic-official:claude-sonnet', runtime_settings: {} }] }}
        registry={registry}
        selectedRouteId="anthropic-official:claude-sonnet"
        onSelect={() => undefined}
      />,
    )

    expect(html).toBe('')
  })

  it('returns the first available route', () => {
    const options = getRouteOptions(role, registry)

    expect(firstAvailableRoute(options)).toBe('anthropic-official:claude-sonnet')
  })
})
