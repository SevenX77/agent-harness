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
      last_test_status: 'ok',
      last_test_at: '2026-05-18T01:23:45Z',
    },
    {
      provider_code: 'OC_DS',
      has_key: false,
      base_url: 'https://chatapi.onechats.ai/v1',
      name: 'OneChats DeepSeek',
      provider_type: 'openai_compatible',
    },
    {
      provider_code: 'WS_LLM',
      has_key: false,
      base_url: 'https://llm.wavespeed.ai/v1',
      name: 'WaveSpeed Any-LLM',
      provider_type: 'wavespeed_any_llm',
    },
    {
      provider_code: 'CUSTOM_AB12CD34',
      has_key: true,
      base_url: 'https://api.example.com/v1',
      title: 'My Custom OpenAI',
      provider_type: 'openai_compatible',
      vendor_hint: 'openai',
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
  it('produces one draft per provider with the persisted has_key flag', () => {
    const drafts = draftsFromCredentials(credentials)
    expect(drafts).toHaveLength(4)
    expect(drafts.map((draft) => draft.provider_code)).toEqual(['DS', 'OC_DS', 'WS_LLM', 'CUSTOM_AB12CD34'])

    const ds = drafts.find((draft) => draft.provider_code === 'DS')!
    expect(ds.hasSavedKey).toBe(true)
    expect(ds.api_key).toBe('')
    expect(ds.provider_type).toBe('openai_compatible')

    const custom = drafts.find((draft) => draft.provider_code === 'CUSTOM_AB12CD34')!
    expect(custom.title).toBe('My Custom OpenAI')
    expect(custom.vendor_hint).toBe('openai')
  })

  it('defaults provider_type to openai_compatible when missing', () => {
    const drafts = draftsFromCredentials({
      providers: [{ provider_code: 'TEST', has_key: false }],
    })
    expect(drafts[0].provider_type).toBe('openai_compatible')
  })
})

describe('SettingsPageContent (api_keys)', () => {
  it('renders the flat provider list with title + provider_code', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    expect(html).toContain('API Keys')
    expect(html).toContain('DS')
    expect(html).toContain('OC_DS')
    expect(html).toContain('WS_LLM')
    expect(html).toContain('My Custom OpenAI')
    expect(html).toContain('新增 Provider')
  })

  it('renders persistent Test outcome badge from credentials', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    // DS has last_test_status='ok' set above.
    expect(html).toContain('连接正常')
  })

  it('omits the Delete button for YAML-owned providers but renders it for custom ones', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    // The aria-label "Delete provider" only appears on Trash buttons rendered
    // when identityEditable is true (i.e., not a YAML-owned provider). With
    // 3 YAML-owned providers + 1 custom in our fixture, exactly one Delete
    // button should be in the markup.
    const matches = html.match(/aria-label="Delete provider"/g) ?? []
    expect(matches).toHaveLength(1)
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
