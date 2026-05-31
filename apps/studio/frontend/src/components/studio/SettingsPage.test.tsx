import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import {
  CopilotTab,
  SettingsPageContent,
  draftFromAddProviderSubmission,
  draftsFromCredentials,
  inferProviderKind,
  inferProviderType,
  moveProviderInRole,
  modelGroupsReferenceMissingCredentialProviders,
  notableProviderKeyForDraft,
  officialProviderProgressToastMessage,
  officialProviderTestSummary,
  officialProviderDrafts,
  providerDraftForAction,
  isStaleRouteReferenceError,
  refreshLoadedLlmRolesProjection,
  providerTestParamsFingerprint,
  providerTestParamsMatch,
  removeProviderFromRole,
  reorderModelInRole,
  reorderProviderInRole,
  shouldShowManualModelPanel,
  thirdPartyProviderDrafts,
  toggleModelFallback,
  updateActiveModel,
  upsertProviderModels,
  upsertProviderModelsListResponse,
  upsertProviderTestResponse,
  validateRoleDraft,
  visibleRoleNames,
} from './SettingsPage'
import type { CredentialsState, ModelGroup, RolesData } from '../../api/llm'

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
      provider_type: 'openai_compatible',
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
    WS_LLM: { name: 'WaveSpeed Any-LLM', type: 'openai_compatible' },
    DS: { name: 'DeepSeek Official', type: 'openai_compatible' },
    OC_DS: { name: 'OneChats DeepSeek', type: 'openai_compatible' },
  },
  roles: {
    copilot_chat: {
      model_fallback_enabled: true,
      active_model: 'CL46T',
      models: {
        CL46T: { providers: ['OC_CL_ANT', 'WS_LLM'], temperature: 0.7 },
        DS32R: { providers: ['DS', 'OC_DS'], temperature: 0.7 },
      },
    },
    deerflow_default: {
      model_fallback_enabled: true,
      active_model: 'CL46T',
      models: {
        CL46T: { providers: ['OC_CL_ANT'], temperature: 0.7 },
      },
    },
  },
}

const modelGroups: ModelGroup[] = []

function baseViewProps(
  overrides: Partial<Parameters<typeof SettingsPageContent>[0]> = {},
): Parameters<typeof SettingsPageContent>[0] {
  return {
    activeTab: 'api_keys',
    credentials,
    credentialsLoading: false,
    credentialsError: null,
    drafts: draftsFromCredentials(credentials),
    saveStatus: 'idle',
    rolesData,
    modelGroups,
    rolesSaveStatus: 'idle',
    rolesError: null,
    appSettings: {
      userId: 'alice',
      giteaHost: 'https://gitea.example.com',
      defaultSkillsDirectory: '/Users/alice/Skills',
      isLoading: false,
      saveStatus: 'idle',
      setUserId: vi.fn(),
      setGiteaHost: vi.fn(),
      setDefaultSkillsDirectory: vi.fn(),
    },
    onClose: vi.fn(),
    onTabChange: vi.fn(),
    onProviderFieldChange: vi.fn(),
    onGetProviderModels: vi.fn(),
    onTestProviderEndpoint: vi.fn(),
    onDeleteProvider: vi.fn(),
    onAddProvider: vi.fn(),
    onProviderModelsUpdated: vi.fn(),
    onRolesDataChange: vi.fn(),
    onDeleteRole: vi.fn(),
    onDeleteModelBundle: vi.fn(),
    onBeforeRoleTest: vi.fn().mockResolvedValue(null),
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

describe('refreshLoadedLlmRolesProjection', () => {
  it('refreshes loaded roles and model groups after credential route changes', async () => {
    const nextRoles: RolesData = {
      ...rolesData,
      providers: {},
      models: {},
    }
    const nextModelGroups: ModelGroup[] = [
      {
        canonical_id: 'gpt-5',
        display_name: 'GPT-5',
        provider_models: [],
        status_summary: { ready: 0, untested: 0, cooling_down: 0, needs_setup: 0, off: 0 },
        capability_summary: {
          capability_known_count: 0,
          thinking: 'unknown',
          tools: 'unknown',
          structured_output: 'unknown',
        },
      },
    ]
    const setRolesData = vi.fn()
    const setModelGroups = vi.fn()
    const setRolesError = vi.fn()

    await refreshLoadedLlmRolesProjection({
      rolesLoaded: true,
      loadRoles: vi.fn().mockResolvedValue(nextRoles),
      loadModelGroups: vi.fn().mockResolvedValue(nextModelGroups),
      setRolesData,
      setModelGroups,
      setRolesError,
    })

    expect(setRolesData).toHaveBeenCalledWith(nextRoles)
    expect(setModelGroups).toHaveBeenCalledWith(nextModelGroups)
    expect(setRolesError).toHaveBeenCalledWith(null)
  })

  it('does not fetch roles projection when LLM Roles has not been loaded', async () => {
    const loadRoles = vi.fn().mockResolvedValue(rolesData)
    const loadModelGroups = vi.fn().mockResolvedValue([])

    await refreshLoadedLlmRolesProjection({
      rolesLoaded: false,
      loadRoles,
      loadModelGroups,
      setRolesData: vi.fn(),
      setModelGroups: vi.fn(),
      setRolesError: vi.fn(),
    })

    expect(loadRoles).not.toHaveBeenCalled()
    expect(loadModelGroups).not.toHaveBeenCalled()
  })
})

describe('isStaleRouteReferenceError', () => {
  it('recognizes backend unknown route validation as recoverable stale state', () => {
    expect(isStaleRouteReferenceError({
      message: 'Request failed with status code 400',
      response: {
        status: 400,
        data: {
          detail: 'Validation failed: role Analyst model_groups[1].provider_models[1] references unknown route custom-qiniu:deepseek',
        },
      },
    })).toBe(true)
  })

  it('does not treat unrelated validation errors as stale route state', () => {
    expect(isStaleRouteReferenceError({
      message: 'Request failed with status code 400',
      response: {
        status: 400,
        data: { detail: 'Validation failed: role name is required' },
      },
    })).toBe(false)
  })
})

describe('modelGroupsReferenceMissingCredentialProviders', () => {
  it('detects stale available models from a deleted provider endpoint', () => {
    expect(modelGroupsReferenceMissingCredentialProviders([
      {
        canonical_id: 'aion-1',
        display_name: 'Aion 1.0',
        provider_models: [
          {
            route_id: 'openrouter:aion-1',
            endpoint_id: 'openrouter',
            provider_label: 'OpenRouter',
            provider_kind: 'third_party',
            provider_model_id: 'aion-1',
            ui_state: 'untested',
            capability_state: 'unknown',
            capabilities: {},
          },
        ],
        status_summary: { ready: 0, untested: 1, cooling_down: 0, needs_setup: 0, off: 0 },
        capability_summary: {
          capability_known_count: 0,
          thinking: 'unknown',
          tools: 'unknown',
          structured_output: 'unknown',
        },
      },
    ], {
      providers: credentials.providers.filter((provider) => provider.id !== 'openrouter'),
    })).toBe(true)
  })

  it('keeps available models when every endpoint still exists', () => {
    expect(modelGroupsReferenceMissingCredentialProviders([
      {
        canonical_id: 'deepseek-v4-flash',
        display_name: 'DeepSeek V4 Flash',
        provider_models: [
          {
            route_id: 'DS:deepseek-v4-flash',
            endpoint_id: 'DS',
            provider_label: 'DeepSeek Official',
            provider_kind: 'official',
            provider_model_id: 'deepseek-v4-flash',
            ui_state: 'ready',
            capability_state: 'known',
            capabilities: {},
          },
        ],
        status_summary: { ready: 1, untested: 0, cooling_down: 0, needs_setup: 0, off: 0 },
        capability_summary: {
          capability_known_count: 1,
          thinking: 'supported',
          tools: 'unknown',
          structured_output: 'unknown',
        },
      },
    ], credentials)).toBe(false)
  })
})

describe('Add Provider flow helpers', () => {
  it('maps official provider codes to provider_type', () => {
    expect(inferProviderType('anthropic')).toBe('anthropic_compatible')
    expect(inferProviderType('gemini')).toBe('google_genai')
    expect(inferProviderType('deepseek')).toBe('openai_compatible')
    expect(inferProviderType('ark')).toBe('ark_runtime')
  })

  it('creates a populated draft from an Add Provider submission', () => {
    const draft = draftFromAddProviderSubmission({
      providerCode: 'my-openrouter',
      name: 'My OpenRouter',
      baseUrl: 'https://openrouter.ai/api/v1',
      apiKey: 'sk-openrouter',
      type: 'third-party',
    }, 'custom-test')

    expect(draft).toEqual({
      id: 'custom-test',
      name: 'My OpenRouter',
      provider_type: 'openai_compatible',
      base_url: 'https://openrouter.ai/api/v1',
      api_key: 'sk-openrouter',
      isTesting: false,
      testingAction: null,
    })
  })

  it('infers anthropic-compatible protocol from third-party name or base URL', () => {
    expect(draftFromAddProviderSubmission({
      providerCode: 'qiniu-anthropic',
      name: 'QiNiu Anthropic',
      baseUrl: 'https://anthropic.qnaigc.com',
      apiKey: 'sk-qiniu',
      type: 'third-party',
    }, 'custom-qiniu-anthropic').provider_type).toBe('anthropic_compatible')

    expect(draftFromAddProviderSubmission({
      providerCode: 'custom-google',
      name: 'Gemini Proxy',
      baseUrl: 'https://example.test',
      apiKey: 'sk-google',
      type: 'third-party',
    }, 'custom-google').provider_type).toBe('google_genai')
  })

  it('infers provider kind from official name or official id prefix', () => {
    expect(inferProviderKind({
      id: 'custom-1',
      name: 'Anthropic-Official',
      provider_type: 'anthropic_compatible',
      base_url: 'https://api.anthropic.com',
      api_key: 'sk',
      isTesting: false,
    })).toBe('official')
    expect(inferProviderKind({
      id: 'custom-1',
      name: 'Anthropic Official',
      provider_type: 'anthropic_compatible',
      base_url: 'https://api.anthropic.com',
      api_key: 'sk',
      isTesting: false,
    })).toBe('official')
    expect(inferProviderKind({
      id: 'ark-123',
      name: 'Ark',
      provider_type: 'ark_runtime',
      base_url: 'https://ark.cn-beijing.volces.com/api/v3',
      api_key: 'sk',
      isTesting: false,
    })).toBe('official')
    expect(inferProviderKind({
      id: 'custom-1',
      name: 'OpenRouter',
      provider_type: 'openai_compatible',
      base_url: 'https://openrouter.ai/api/v1',
      api_key: 'sk',
      isTesting: false,
    })).toBe('third-party')
  })

  it('builds five official drafts and separates third-party drafts', () => {
    const drafts = draftsFromCredentials(credentials)

    expect(officialProviderDrafts(drafts).map((draft) => draft.name)).toEqual([
      'Anthropic Official',
      'OpenAI Official',
      'Gemini Official',
      'DeepSeek Official',
      'Ark Official',
    ])
    expect(thirdPartyProviderDrafts(drafts).map((draft) => draft.id)).toEqual([
      'OC_DS',
      'WS_LLM',
      'CUSTOM_AB12CD34',
    ])
  })

  it('uses canonical official provider endpoints for hidden Base URL fields and Test actions', () => {
    const staleOfficialDrafts = draftsFromCredentials({
      providers: [
        {
          id: 'anthropic-official',
          name: 'Anthropic',
          api_key: 'sk-anthropic',
          base_url: 'https://api.anthropic.example',
          provider_type: 'openai_compatible',
        },
      ],
    })

    const official = officialProviderDrafts(staleOfficialDrafts)[0]
    const actionDraft = providerDraftForAction(staleOfficialDrafts, 'anthropic-official')

    expect(official.base_url).toBe('https://api.anthropic.com')
    expect(official.provider_type).toBe('anthropic_compatible')
    expect(actionDraft?.base_url).toBe('https://api.anthropic.com')
    expect(actionDraft?.provider_type).toBe('anthropic_compatible')
  })

  it('derives notable provider key and manual panel visibility', () => {
    const official = officialProviderDrafts(draftsFromCredentials(credentials))[0]
    const wavespeed = thirdPartyProviderDrafts(draftsFromCredentials(credentials))[1]
    const custom = thirdPartyProviderDrafts(draftsFromCredentials(credentials))[2]

    expect(notableProviderKeyForDraft(official)).toBe('anthropic')
    expect(notableProviderKeyForDraft(wavespeed)).toBe('wavespeed')
    expect(notableProviderKeyForDraft({
      id: 'qiniu-openai',
      name: 'Qiniu OpenAI',
      provider_type: 'openai_compatible',
      base_url: 'https://api.qnaigc.com/v1',
      api_key: '',
      isTesting: false,
    })).toBe('qiniu')
    expect(notableProviderKeyForDraft(custom)).toBe('openai')
    expect(shouldShowManualModelPanel(official, null)).toBe(true)
    expect(shouldShowManualModelPanel(custom, null)).toBe(false)
    expect(shouldShowManualModelPanel(custom, { ...credentials.providers[3], last_test_status: 'ok' })).toBe(true)
  })

  it('matches test outcome identity by API key, base URL, and provider type only', () => {
    expect(providerTestParamsMatch(
      { api_key: 'sk', base_url: 'https://base.test', provider_type: 'openai_compatible' },
      { api_key: 'sk', base_url: 'https://base.test', provider_type: 'openai_compatible' },
    )).toBe(true)
    expect(providerTestParamsMatch(
      { api_key: 'sk', base_url: 'https://base.test', provider_type: 'openai_compatible' },
      { api_key: 'sk', base_url: 'https://changed.test', provider_type: 'openai_compatible' },
    )).toBe(false)
    expect(providerTestParamsMatch(
      { api_key: 'sk', base_url: 'https://base.test', provider_type: 'openai_compatible' },
      { api_key: 'sk', base_url: 'https://base.test', provider_type: 'anthropic_compatible' },
    )).toBe(false)
  })

  it('adds a newly tested official provider to credentials when registry-backed test returns models', () => {
    const draft = providerDraftForAction([], 'openai-official')
    expect(draft).not.toBeNull()

    const next = upsertProviderTestResponse({ providers: [] }, draft!, {
      status: 'ok',
      message: 'Connected',
      available_models: [{ id: 'gpt-5' }],
      available_sdks: ['openai_compatible'],
    })

    expect(next.providers).toMatchObject([
      {
        id: 'openai-official',
        name: 'OpenAI Official',
        last_test_status: 'ok',
        available_models: [{ id: 'gpt-5' }],
        available_sdks: ['openai_compatible'],
      },
    ])
  })

  it('caches provider test results by complete editable config for restore-on-match UX', () => {
    const draft = providerDraftForAction([], 'openai-official')
    expect(draft).not.toBeNull()

    const next = upsertProviderTestResponse({ providers: [] }, draft!, {
      status: 'ok',
      message: 'Connected',
      available_models: [{ id: 'gpt-5' }],
      available_sdks: ['openai_compatible'],
    })

    expect(next.providers[0].test_results).toMatchObject([
      {
        params_fingerprint: providerTestParamsFingerprint(draft!),
        base_url: 'https://api.openai.com',
        provider_type: 'openai_compatible',
        last_test_status: 'ok',
        last_test_message: 'Connected',
        available_models: [{ id: 'gpt-5' }],
        available_sdks: ['openai_compatible'],
      },
    ])
  })

  it('adds manual model results for a newly materialized provider instead of dropping them', () => {
    const draft = providerDraftForAction([], 'openai-official')
    expect(draft).not.toBeNull()

    const next = upsertProviderModels(
      { providers: [] },
      draft,
      'openai-official',
      [{ id: 'gpt-5' }],
    )

    expect(next.providers).toMatchObject([
      {
        id: 'openai-official',
        name: 'OpenAI Official',
        last_test_status: 'ok',
        available_models: [{ id: 'gpt-5' }],
      },
    ])
  })

  it('merges Get Models responses into the existing model list by diff', () => {
    const draft = providerDraftForAction([], 'openai-official')
    expect(draft).not.toBeNull()
    const current: CredentialsState = {
      providers: [
        {
          id: 'openai-official',
          name: 'OpenAI Official',
          api_key: 'sk-live',
          base_url: 'https://api.openai.com',
          provider_type: 'openai_compatible',
          last_test_status: 'ok',
          last_test_at: '2026-05-29T10:00:00Z',
          last_test_message: 'Connected',
          available_models: [
            { id: 'gpt-5-old', status: 'verified', route_id: 'openai-official:gpt-5-old' },
            { id: 'gpt-5', status: 'unverified_manual', route_id: 'openai-official:gpt-5' },
          ],
        },
      ],
    }

    const next = upsertProviderModelsListResponse(current, draft!, {
      status: 'ok',
      message: 'Testing 2/2 provider models.',
      available_models: [
        { id: 'gpt-5', status: 'verified', route_id: 'openai-official:gpt-5' },
        { id: 'gpt-image-1', status: 'unverified_manual' },
      ],
      available_sdks: ['openai_compatible'],
    })

    expect(next.providers[0].available_models).toEqual([
      { id: 'gpt-5-old', status: 'verified', route_id: 'openai-official:gpt-5-old' },
      { id: 'gpt-5', status: 'verified', route_id: 'openai-official:gpt-5' },
      { id: 'gpt-image-1', status: 'unverified_manual' },
    ])
  })

  it('keeps live probe evidence when an official catalog refresh returns the same model as unverified', () => {
    const draft = providerDraftForAction([], 'anthropic-official')
    expect(draft).not.toBeNull()
    const current: CredentialsState = {
      providers: [
        {
          id: 'anthropic-official',
          name: 'Anthropic Official',
          api_key: 'sk-live',
          base_url: 'https://api.anthropic.com',
          provider_type: 'anthropic_compatible',
          last_test_status: 'ok',
          last_test_at: '2026-05-30T10:00:00Z',
          last_test_message: 'Connected. Model seen: claude-opus-4-6.',
          available_models: [
            {
              id: 'claude-opus-4-6',
              route_id: 'anthropic-official:claude-opus-4.6',
              status: 'verified',
              verified_profile_count: 2,
              capabilities: { thinking: true },
            },
            {
              id: 'claude-old-failed',
              route_id: 'anthropic-official:claude-old-failed',
              status: 'failed',
              last_probe_message: 'Provider returned HTTP 404 for this model.',
            },
          ],
        },
      ],
    }

    const next = upsertProviderModelsListResponse(current, draft!, {
      status: 'ok',
      message: 'Provider catalog reachable.',
      available_models: [
        {
          id: 'claude-opus-4-6',
          route_id: 'anthropic-official:claude-opus-4.6',
          status: 'unverified_manual',
          verified_profile_count: 0,
          capabilities: { model_type: 'language_reasoning' },
        },
        {
          id: 'claude-old-failed',
          route_id: 'anthropic-official:claude-old-failed',
          status: 'unverified_manual',
        },
      ],
      available_sdks: ['anthropic_compatible'],
    })

    expect(next.providers[0].available_models).toEqual([
      {
        id: 'claude-opus-4-6',
        route_id: 'anthropic-official:claude-opus-4.6',
        status: 'verified',
        verified_profile_count: 2,
        capabilities: { model_type: 'language_reasoning', thinking: true },
      },
      {
        id: 'claude-old-failed',
        route_id: 'anthropic-official:claude-old-failed',
        status: 'failed',
        last_probe_message: 'Provider returned HTTP 404 for this model.',
      },
    ])
  })
})

describe('SettingsPageContent (api_keys)', () => {
  it('describes official provider catalog progress without generation-probe wording', () => {
    expect(officialProviderProgressToastMessage('Anthropic Official', {
      job_id: 'job-1',
      endpoint_id: 'anthropic-official',
      status: 'running',
      total_model_count: 8,
      tested_model_count: 0,
      verified_route_count: 0,
      failed_model_count: 0,
      catalog_only_count: 0,
      message: 'Reading provider catalog.',
      available_models: [],
      available_sdks: ['anthropic_compatible'],
    })).toBe('Loading Anthropic Official route candidates (8 listed)...')
  })

  it('summarizes official provider Test results as catalog hydration, not generation probing', () => {
    expect(officialProviderTestSummary([
      { id: 'claude-haiku', status: 'verified' },
      { id: 'claude-opus-4-1', status: 'unverified_manual' },
      { id: 'claude-opus-4-6' },
      { id: 'claude-opus-4-7', status: 'verified' },
      { id: 'claude-sonnet', status: 'failed' },
    ])).toEqual({
      kind: 'success',
      message: 'Catalog loaded (2 already verified, 3 not generation-probe verified)',
    })
  })

  it('renders General settings as auto-saved shadcn fields without manual save buttons', () => {
    const html = renderToStaticMarkup(
      <SettingsPageContent
        {...baseViewProps({
          activeTab: 'general',
          appSettings: {
            ...baseViewProps().appSettings,
            saveStatus: 'saving',
          },
        })}
      />,
    )

    expect(html).toContain('Changes auto-save')
    expect(html).toContain('Saving')
    expect(html).toContain('data-slot="field"')
    expect(html).toContain('value="/Users/alice/Skills"')
    expect(html).toContain('max-w-5xl')
    expect(html).not.toContain('>Save</button>')
    expect(html).not.toContain('Using /Users/alice/Skills')
  })

  it('keeps every Settings tab content constrained within the Settings surface', () => {
    for (const activeTab of ['general', 'api_keys'] as const) {
      const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab })} />)

      expect(html).toContain('max-w-3xl')
    }
    const rolesHtml = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'llm_roles' })} />)
    expect(rolesHtml).toContain('max-w-6xl')
    const copilotHtml = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'copilot' })} />)
    expect(copilotHtml).toContain('max-w-5xl')
    expect(copilotHtml).toContain('max-w-3xl')
  })

  it('renders Copilot as a standalone Settings page with SDK compatibility states', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ activeTab: 'copilot' })} />)

    expect(html).toContain('data-copilot-settings-page="true"')
    expect(html).toContain('Copilot</button>')
    expect(html).toContain('data-slot="catalog-accordion"')
    expect(html).toContain('Claude Agent SDK')
    expect(html).not.toContain('Copilot Roles')
    expect(html).toContain('Opus 4.7 Copilot')
    expect(html).toContain('DeepSeek V4 Copilot')
    expect(html).toContain('Claude Agent SDK Ready')
    expect(html).toContain('Claude Agent SDK Not tested')
    expect(html).toContain('data-copilot-model-group="true"')
    expect(html).toContain('data-copilot-provider-grid="true"')
    expect(html).toContain('data-copilot-provider-card="true"')
    expect(html).toContain('data-copilot-model-add-trigger="true"')
    expect(html).toContain('Add model')
    expect(html).toContain('DeepSeek Official')
    expect(html).toContain('Ark Official')
    expect(html).not.toContain('aria-label="Copilot roles"')
    expect(html).not.toContain('data-copilot-sdk-select="true"')
    expect(html).not.toContain('openai_chat_completions')
  })

  it('renders the Copilot tab component without depending on LLM Roles data', () => {
    const html = renderToStaticMarkup(<CopilotTab />)

    expect(html).toContain('data-copilot-role-card="true"')
    expect(html.match(/data-copilot-role-card="true"/g)).toHaveLength(2)
    expect(html.match(/data-copilot-role-source="built_in"/g)).toHaveLength(2)
    expect(html).toContain('data-copilot-model-name="true"')
    expect(html).toContain('data-variant="default"')
    expect(html).toContain('Test</button>')
    expect(html).not.toContain('data-copilot-role-delete-trigger="true"')
  })

  it('renders provider skeletons while credentials are loading', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps({ credentialsLoading: true })} />)
    const skeletons = html.match(/data-slot="skeleton"/g) ?? []
    expect(skeletons).toHaveLength(15)
    expect(html).not.toContain('Add Provider')
    expect(html).not.toContain('Provider Name')
  })

  it('renders a load failure instead of synthetic empty providers when credentials cannot load', () => {
    const html = renderToStaticMarkup(
      <SettingsPageContent
        {...baseViewProps({
          credentials: { providers: [] },
          credentialsLoading: false,
          credentialsError: 'Bad Gateway',
          drafts: [],
        })}
      />,
    )

    expect(html).toContain('API Keys load failed')
    expect(html).toContain('Bad Gateway')
    expect(html).toContain('Stored provider values are not shown')
    expect(html).not.toContain('Anthropic Official')
    expect(html).not.toContain('Add Provider')
  })

  it('renders official providers and empty third-party state after credentials finish loading', () => {
    const html = renderToStaticMarkup(
      <SettingsPageContent
        {...baseViewProps({
          credentials: { providers: [] },
          credentialsLoading: false,
          drafts: [],
        })}
      />,
    )
    expect(html).toContain('data-slot="catalog-accordion"')
    expect(html).toContain('data-slot="catalog-accordion-trigger"')
    expect(html.indexOf("catalog-accordion-state-icon")).toBeLessThan(html.indexOf("Official Providers"))
    expect(html).toContain('Official Providers')
    expect(html).toContain('Anthropic Official')
    expect(html).toContain('OpenAI Official')
    expect(html).toContain('Gemini Official')
    expect(html).toContain('DeepSeek Official')
    expect(html).toContain('Ark Official')
    expect(html).not.toContain('Not configured')
    expect(html).toContain('Third-party Providers')
    expect(html).toContain('No third-party providers configured.')
    expect(html).toContain('Add Provider')
    expect(html).toContain('data-variant="default"')
    expect(html).toContain('border-dashed')
    expect(html).not.toContain('Cancel')
    expect(html).not.toContain('data-testid="add-provider-form"')
    expect(html).not.toContain('data-slot="skeleton"')
  })

  it('renders official and third-party provider cards with primary test actions', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    expect(html).toContain('API Keys')
    expect(html).toContain('data-slot="catalog-accordion"')
    expect(html).toContain('data-slot="catalog-accordion-content"')
    expect(html).toContain('Official Providers')
    expect(html).toContain('Anthropic Official')
    expect(html).toContain('OpenAI Official')
    expect(html).toContain('Gemini Official')
    expect(html).toContain('DS')
    expect(html).toContain('Third-party Providers')
    expect(html).toContain('OC_DS')
    expect(html).toContain('WS_LLM')
    expect(html).toContain('My Custom OpenAI')
    expect(html).toContain('Add Provider')
    expect(html).toContain('Test')
  })

  it('renders API key inputs as native password values with password-manager ignore attributes', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)

    expect(html).toContain('type="password"')
    expect(html).toContain('value="sk-deepseek"')
    expect(html).toContain('name="provider-secret-DS"')
    expect(html).toContain('autoComplete="off"')
    expect(html).toContain('data-1p-ignore=""')
    expect(html).toContain('data-lpignore="true"')
    expect(html).toContain('data-form-type="other"')
    expect(html).not.toContain('Saved key retained')
    expect(html).toContain('Show API key')
  })

  it('hides official Test outcome badges but keeps third-party outcomes visible', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    expect(html).not.toContain('Connected')

    const withThirdPartyOutcome: CredentialsState = {
      providers: credentials.providers.map((provider) => (
        provider.id === 'CUSTOM_AB12CD34'
          ? { ...provider, last_test_status: 'ok' as const, last_test_message: 'Connected' }
          : provider
      )),
    }
    const htmlWithThirdPartyOutcome = renderToStaticMarkup(
      <SettingsPageContent
        {...baseViewProps({
          credentials: withThirdPartyOutcome,
          drafts: draftsFromCredentials(withThirdPartyOutcome),
        })}
      />,
    )

    expect(htmlWithThirdPartyOutcome).toContain('Connected')
  })

  it('renders a Delete button/action menu for each user-owned provider', () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...baseViewProps()} />)
    const matches = html.match(/aria-label="More actions for [^"]*"/g) ?? []
    expect(matches).toHaveLength(3)
  })
})

describe('LLM Roles helpers', () => {
  it('toggleModelFallback flips the flag', () => {
    const next = toggleModelFallback(rolesData, 'copilot_chat', false)
    expect(next.roles.copilot_chat.model_fallback_enabled).toBe(false)
    expect(rolesData.roles.copilot_chat.model_fallback_enabled).toBe(true)
  })

  it('updateActiveModel swaps the active model', () => {
    const next = updateActiveModel(rolesData, 'copilot_chat', 'DS32R')
    expect(next.roles.copilot_chat.active_model).toBe('DS32R')
  })

  it('moveProviderInRole shifts a provider up the chain', () => {
    const next = moveProviderInRole(rolesData, 'copilot_chat', 'CL46T', 1, -1)
    expect(next.roles.copilot_chat.models.CL46T.providers).toEqual(['WS_LLM', 'OC_CL_ANT'])
  })

  it('reorderProviderInRole moves a provider to a target index while preserving settings', () => {
    const next = reorderProviderInRole(rolesData, 'copilot_chat', 'CL46T', 0, 1)
    expect(next.roles.copilot_chat.models.CL46T.providers).toEqual(['WS_LLM', 'OC_CL_ANT'])
    expect(next.roles.copilot_chat.models.CL46T.temperature).toBe(0.7)
  })

  it('reorderModelInRole moves a model to a target position', () => {
    const next = reorderModelInRole(rolesData, 'copilot_chat', 'DS32R', 'CL46T')
    expect(Object.keys(next.roles.copilot_chat.models)).toEqual(['DS32R', 'CL46T'])
    expect(next.roles.copilot_chat.active_model).toBe('DS32R')
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
