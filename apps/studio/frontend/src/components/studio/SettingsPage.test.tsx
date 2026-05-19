import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import {
  SettingsPageContent,
  draftsFromCredentials,
  moveProviderInRole,
  removeProviderFromRole,
  toggleModelFallback,
  updateActiveModel,
  validateRoleDraft,
  visibleRoleNames,
} from './settings'
import type { CredentialsState, RolesData } from '../../api/llm'

const credentials: CredentialsState = {
  providers: [
    {
      id: 'DS',
      name: 'DeepSeek Official',
      api_key: 'sk-deepseek',
      base_url: 'https://api.deepseek.com',
      provider_type: 'openai_compatible',
      last_test_status: 'ok',
      last_test_at: '2026-05-18T01:23:45Z',
    },
    {
      id: 'OC_DS',
      name: 'OneChats DeepSeek',
      api_key: '',
      base_url: 'https://chatapi.onechats.ai/v1',
      provider_type: 'openai_compatible',
    },
    {
      id: 'WS_LLM',
      name: 'WaveSpeed Any-LLM',
      api_key: '',
      base_url: 'https://llm.wavespeed.ai/v1',
      provider_type: 'wavespeed_any_llm',
    },
    {
      id: 'CUSTOM_AB12CD34',
      name: 'My Custom OpenAI',
      api_key: 'sk-custom',
      base_url: 'https://api.example.com/v1',
      provider_type: 'openai_compatible',
    },
  ],
}

const rolesData: RolesData = {
  models: {
    CL46T: {
      name: 'Claude Sonnet 4.6 Thinking',
      providers: {
        OC_CL_ANT: 'claude-sonnet-4-6-thinking',
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
        CL46T: { providers: ['OC_CL_ANT', 'WS_LLM'] },
        DS32R: { providers: ['DS', 'OC_DS'] },
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
}

function baseViewProps(
  overrides: Partial<Parameters<typeof SettingsPageContent>[0]> = {},
): Parameters<typeof SettingsPageContent>[0] {
  return {
    activeTab: 'api_keys',
    credentials,
    drafts: draftsFromCredentials(credentials),
    saveStatus: 'idle',
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
    onProviderFieldChange: vi.fn(),
    onTestProvider: vi.fn(),
    onDeleteProvider: vi.fn(),
    onAddProvider: vi.fn(),
    onSelectedRoleChange: vi.fn(),
    onRolesDataChange: vi.fn(),
    onSaveRoles: vi.fn(),
    ...overrides,
  }
}

describe('draftsFromCredentials', () => {
  it('produces one draft per provider with the persisted plaintext api_key', () => {
    const drafts = draftsFromCredentials(credentials)
    expect(drafts).toHaveLength(4)
    expect(drafts.map((draft) => draft.id)).toEqual(['DS', 'OC_DS', 'WS_LLM', 'CUSTOM_AB12CD34'])

    const ds = drafts.find((draft) => draft.id === 'DS')!
    expect(ds.api_key).toBe('sk-deepseek')
    expect(ds.provider_type).toBe('openai_compatible')

    const custom = drafts.find((draft) => draft.id === 'CUSTOM_AB12CD34')!
    expect(custom.name).toBe('My Custom OpenAI')
  })

  it('defaults provider_type to openai_compatible when missing', () => {
    const drafts = draftsFromCredentials({
      providers: [{ id: 'TEST', name: 'Test', api_key: '' }],
    })
    expect(drafts[0].provider_type).toBe('openai_compatible')
  })
})

describe('SettingsPageContent (api_keys)', () => {
  it('renders the provider cards with name inputs and primary test actions', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    expect(html).toContain('API Keys')
    expect(html).toContain('DS')
    expect(html).toContain('OC_DS')
    expect(html).toContain('WS_LLM')
    expect(html).toContain('My Custom OpenAI')
    expect(html).toContain('Add Provider')
    expect(html).toContain('Test')
  })

  it('renders API key inputs as plaintext values with password-manager ignore attributes', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)

    expect(html).toContain('type="text"')
    expect(html).toContain('value="sk-deepseek"')
    expect(html).toContain('name="provider-secret-DS"')
    expect(html).toContain('autoComplete="off"')
    expect(html).toContain('data-1p-ignore=""')
    expect(html).toContain('data-lpignore="true"')
    expect(html).toContain('data-form-type="other"')
    expect(html).not.toContain('Saved key retained')
    expect(html).not.toContain('Show API key')
  })

  it('renders persistent Test outcome badge from credentials', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    // DS has last_test_status='ok' set above.
    expect(html).toContain('Connected')
  })

  it('renders a Delete button for each user-owned provider', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    const matches = html.match(/aria-label="Delete provider"/g) ?? []
    expect(matches).toHaveLength(4)
  })
})

describe('LLM Roles helpers', () => {
  it('toggleModelFallback flips the flag', () => {
    const next = toggleModelFallback(rolesData, 'copilot_chat', false)
    expect(next.roles.copilot_chat.model_fallback).toBe(false)
    expect(rolesData.roles.copilot_chat.model_fallback).toBe(true)
  })

  it('updateActiveModel swaps the active model', () => {
    const next = updateActiveModel(rolesData, 'copilot_chat', 'DS32R')
    expect(next.roles.copilot_chat.active_model).toBe('DS32R')
  })

  it('moveProviderInRole shifts a provider up the chain', () => {
    const next = moveProviderInRole(rolesData, 'copilot_chat', 'CL46T', 1, -1)
    expect(next.roles.copilot_chat.models.CL46T.providers).toEqual(['WS_LLM', 'OC_CL_ANT'])
  })

  it('removeProviderFromRole drops the provider at index', () => {
    const next = removeProviderFromRole(rolesData, 'copilot_chat', 'CL46T', 0)
    expect(next.roles.copilot_chat.models.CL46T.providers).toEqual(['WS_LLM'])
  })

  it('validateRoleDraft returns null for a healthy role', () => {
    expect(validateRoleDraft(rolesData, 'copilot_chat')).toBeNull()
  })

  it('visibleRoleNames filters out deerflow_ prefixes', () => {
    expect(visibleRoleNames(rolesData)).toEqual(['copilot_chat'])
  })
})
