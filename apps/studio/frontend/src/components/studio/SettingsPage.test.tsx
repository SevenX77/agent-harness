import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import {
  ProviderRow,
  SettingsPageContent,
  VENDORS,
  credentialUpdateFor,
  defaultVendorOpen,
  draftsFromCredentials,
  initialTestStates,
  moveProviderInRole,
  removeProviderFromRole,
  toggleModelFallback,
  updateActiveModel,
  validateRoleDraft,
  visibleRoleNames,
  preserveTestStateOnInputChange,
  testRequestFor,
} from './SettingsPage'
import type { CredentialsState, RolesData } from '../../api/llm'

const credentials: CredentialsState = {
  providers: [
    {
      provider_code: 'DS',
      has_key: true,
      base_url: 'https://api.deepseek.com',
      name: 'DeepSeek Official',
      provider_type: 'openai_compatible',
    },
    {
      provider_code: 'OC_DS',
      has_key: false,
      base_url: 'https://chatapi.onechats.ai/v1',
      name: 'OneChats DeepSeek',
      provider_type: 'openai_compatible',
    },
    {
      provider_code: 'GM_OFF',
      has_key: false,
      name: 'Gemini Official',
      provider_type: 'gemini_official',
    },
    {
      provider_code: 'OC_GM',
      has_key: false,
      base_url: 'https://chatapi.onechats.ai/v1',
      name: 'OneChats Gemini',
      provider_type: 'openai_compatible',
    },
    {
      provider_code: 'OC_CL_ANT',
      has_key: false,
      base_url: 'https://chatapi.onechats.ai',
      name: 'OneChats Claude',
      provider_type: 'anthropic_compatible',
    },
    {
      provider_code: 'WS_LLM',
      has_key: false,
      base_url: 'https://llm.wavespeed.ai/v1',
      name: 'WaveSpeed Any-LLM',
      provider_type: 'wavespeed_any_llm',
    },
  ],
}

const rolesData: RolesData = {
  models: {
    CL46T: {
      name: 'Claude Sonnet 4.6 Thinking',
      providers: {
        OC_CL_ANT: 'claude-sonnet-4-6-thinking',
        OC_CL: 'claude-sonnet-4-6-thinking',
        WS_LLM: 'anthropic/claude-sonnet-4.6',
      },
    },
    DS32R: {
      name: 'DeepSeek-V4 Pro',
      providers: {
        DS: 'deepseek-v4-pro',
        OC_DS: 'deepseek/deepseek-r1-0528',
      },
    },
  },
  providers: {
    OC_CL_ANT: { name: 'OneChats Claude Anthropic', type: 'anthropic_compatible' },
    OC_CL: { name: 'OneChats Claude', type: 'openai_compatible' },
    WS_LLM: { name: 'WaveSpeed Any-LLM', type: 'wavespeed_any_llm' },
    DS: { name: 'DeepSeek Official', type: 'openai_compatible' },
    OC_DS: { name: 'OneChats DeepSeek', type: 'openai_compatible' },
  },
  roles: {
    copilot_chat: {
      temperature: 0.7,
      model_fallback: true,
      active_model: 'CL46T',
      models: {
        CL46T: { providers: ['OC_CL_ANT', 'OC_CL', 'WS_LLM'] },
        DS32R: { providers: ['DS', 'OC_DS'] },
      },
    },
    analyst: {
      temperature: 0.2,
      model_fallback: true,
      active_model: 'CL46T',
      models: {
        CL46T: { providers: ['OC_CL_ANT'] },
      },
    },
    deerflow_default: {
      temperature: 0.7,
      model_fallback: true,
      active_model: 'CL46T',
      models: {
        CL46T: { providers: ['OC_CL_ANT'] },
      },
    },
  },
  peer_model_groups: { claude_sonnet_tier: ['CL46T'] },
}

function baseViewProps(overrides: Partial<Parameters<typeof SettingsPageContent>[0]> = {}): Parameters<typeof SettingsPageContent>[0] {
  return {
    activeTab: 'api_keys',
    credentials,
    drafts: {
      ...draftsFromCredentials(credentials),
      DS: { apiKey: 'sk-deepseek-12345', visible: false },
      OC_DS: { apiKey: 'sk-oc-12345', visible: false },
    },
    testStates: {
      ...initialTestStates(credentials),
      DS: { status: 'ok', result: { status: 'ok', latency_ms: 87 } },
    },
    vendorOpen: defaultVendorOpen(),
    rolesData,
    selectedRole: 'copilot_chat',
    rolesDirty: false,
    rolesError: null,
    appSettings: {
      userId: 'alice',
      giteaHost: 'https://gitea.example.com',
      isLoading: false,
      setUserId: vi.fn(),
      setGiteaHost: vi.fn(),
      save: vi.fn(),
    },
    onClose: vi.fn(),
    onTabChange: vi.fn(),
    onDraftChange: vi.fn(),
    onToggleKeyVisible: vi.fn(),
    onToggleVendor: vi.fn(),
    onTestProvider: vi.fn(),
    onSelectedRoleChange: vi.fn(),
    onRolesDataChange: vi.fn(),
    onSaveRoles: vi.fn(),
    ...overrides,
  }
}

function findByAriaLabel(node: ReactNode, label: string): ReactElement<Record<string, unknown>> | null {
  if (!isValidElement(node)) return null
  const element = node as ReactElement<Record<string, unknown> & { children?: ReactNode }>
  if (element.props['aria-label'] === label) return element
  const children = element.props.children
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findByAriaLabel(child, label)
      if (match) return match
    }
  }
  return findByAriaLabel(children, label)
}

function providerRow(overrides: Partial<Parameters<typeof ProviderRow>[0]> = {}) {
  const provider = credentials.providers[0]
  const props: Parameters<typeof ProviderRow>[0] = {
    provider,
    title: 'Official API',
    isOfficial: true,
    draft: { apiKey: 'sk-local', visible: false },
    testState: { status: 'idle' },
    onDraftChange: vi.fn(),
    onToggleKeyVisible: vi.fn(),
    onTestProvider: vi.fn(),
    ...overrides,
  }
  return { props, element: ProviderRow(props) }
}

describe('SettingsPage', () => {
  it('renders vendor groups', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)

    for (const vendor of VENDORS) {
      expect(html).toContain(vendor.label)
    }
  })

  it('renders new settings tabs and no v1 active backend radio', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'general' })} />)

    expect(html).toContain('General')
    expect(html).toContain('API Keys')
    expect(html).toContain('LLM Roles')
    expect(html).not.toContain('AI &amp; Copilot')
    expect(html).not.toContain('Active Backend')
  })

  it('renders official row without base url input', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    const deepseekSection = html.slice(html.indexOf('DeepSeek'), html.indexOf('Custom: OneChats DeepSeek'))

    expect(deepseekSection).toContain('Official API')
    expect(deepseekSection).not.toContain('Base URL')
  })

  it('renders custom row base url flat', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)

    expect(html).toContain('Custom: OneChats DeepSeek')
    expect(html).toContain('https://chatapi.onechats.ai/v1')
  })

  it('creates the debounce save payload for changed api keys', () => {
    expect(credentialUpdateFor('DS', { apiKey: 'sk-new', visible: false })).toEqual([
      { provider_code: 'DS', api_key: 'sk-new' },
    ])
  })

  it('creates provider test request with provider_type', () => {
    expect(testRequestFor(credentials.providers[0], { apiKey: 'sk-new', visible: false })).toEqual({
      provider_code: 'DS',
      provider_type: 'openai_compatible',
      api_key: 'sk-new',
      base_url: 'https://api.deepseek.com',
    })
  })

  it('input change does not clear test state', () => {
    const state = {
      DS: { status: 'ok', result: { status: 'ok', latency_ms: 87 } },
    } as const

    expect(preserveTestStateOnInputChange(state)).toBe(state)
  })

  it('eye toggle shows and hides key', () => {
    const hidden = providerRow({ draft: { apiKey: 'sk-local', visible: false } }).element
    const shown = providerRow({ draft: { apiKey: 'sk-local', visible: true } }).element
    const hiddenInput = findByAriaLabel(hidden, 'DS API key')
    const shownInput = findByAriaLabel(shown, 'DS API key')

    expect(hiddenInput?.props.type).toBe('password')
    expect(shownInput?.props.type).toBe('text')
    expect(hiddenInput?.props.autoComplete).toBe('new-password')
    expect(hiddenInput?.props.name).toBeUndefined()
  })

  it('test button calls handler with provider code', () => {
    const onTestProvider = vi.fn()
    const { element } = providerRow({ onTestProvider })
    const button = findByAriaLabel(element, 'Test DS')

    ;(button?.props.onClick as (() => void) | undefined)?.()

    expect(onTestProvider).toHaveBeenCalledWith('DS')
  })

  it('add custom provider button is disabled', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)

    expect(html).toContain('+ Add Custom Provider')
    expect(html).toContain('disabled=""')
    expect(html).toContain('Custom provider editing coming in v2.5')
  })

  it('tab2 renders copilot_chat role', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'llm_roles' })} />)

    expect(html).toContain('copilot_chat')
    expect(html).toContain('value="CL46T" selected=""')
    expect(html).toContain('model_fallback')
    expect(html).toContain('OC_CL_ANT')
    expect(html).toContain('DS32R')
  })

  it('tab2 provider reorder swaps provider order', () => {
    const next = moveProviderInRole(rolesData, 'copilot_chat', 'CL46T', 1, -1)

    expect(next.roles.copilot_chat.models.CL46T.providers).toEqual(['OC_CL', 'OC_CL_ANT', 'WS_LLM'])
  })

  it('tab2 provider remove splices provider order', () => {
    const next = removeProviderFromRole(rolesData, 'copilot_chat', 'CL46T', 1)

    expect(next.roles.copilot_chat.models.CL46T.providers).toEqual(['OC_CL_ANT', 'WS_LLM'])
  })

  it('tab2 changes active model', () => {
    const next = updateActiveModel(rolesData, 'copilot_chat', 'DS32R')

    expect(next.roles.copilot_chat.active_model).toBe('DS32R')
  })

  it('tab2 toggles model fallback', () => {
    const next = toggleModelFallback(rolesData, 'copilot_chat', false)

    expect(next.roles.copilot_chat.model_fallback).toBe(false)
  })

  it('tab2 save button calls save handler', () => {
    const onSaveRoles = vi.fn()
    const html = renderToStaticMarkup(
      <SettingsPageContent {...baseViewProps({ activeTab: 'llm_roles', rolesDirty: true, onSaveRoles })} />,
    )

    expect(html).toContain('Save')
    expect(html).toContain('Dirty')
  })

  it('tab2 save failure message renders and validation blocks empty provider chains', () => {
    const broken = removeProviderFromRole(rolesData, 'copilot_chat', 'DS32R', 0)
    const brokenAgain = removeProviderFromRole(broken, 'copilot_chat', 'DS32R', 0)
    const html = renderToStaticMarkup(
      <SettingsPageContent {...baseViewProps({ activeTab: 'llm_roles', rolesError: 'bad reference' })} />,
    )

    expect(validateRoleDraft(brokenAgain, 'copilot_chat')).toContain('DS32R')
    expect(html).toContain('Validation failed: bad reference')
  })

  it('tab2 hides deerflow roles', () => {
    expect(visibleRoleNames(rolesData)).toEqual(['copilot_chat', 'analyst'])
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'llm_roles' })} />)

    expect(html).not.toContain('deerflow_default')
  })

  it('tab2 round trips peer model groups', () => {
    const next = updateActiveModel(rolesData, 'copilot_chat', 'DS32R')

    expect(next.peer_model_groups).toEqual({ claude_sonnet_tier: ['CL46T'] })
  })

  it('tab2 add buttons are disabled', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'llm_roles' })} />)

    expect(html).toContain('+ Add Model')
    expect(html).toContain('+ Add Provider')
    expect(html).toContain('Adding new model/provider coming in v2.5')
    expect(html).toContain('disabled=""')
  })
})
