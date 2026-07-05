import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from './client'
import {
  getCredentials,
  getRegistry,
  getProviderModels,
  getRoles,
  deleteModelBundle,
  deleteRole,
  modelGroupsFromRegistry,
  probeRoute,
  probeRouteMultimodal,
  routeAcceptsImageVerified,
  putCredentials,
  putRoles,
  resetLlmApiCachesForTests,
  getRoleTestJob,
  startRoleTestJob,
  syncVerifiedCommunityCatalog,
  testRole,
  testProviderModels,
  testProvider,
  type ProviderEndpoint,
  type ProviderRoute,
  type RegistryResponse,
} from './llm'

function adapter(assertConfig: (config: InternalAxiosRequestConfig) => AxiosResponse['data']): AxiosAdapter {
  return async (config): Promise<AxiosResponse> => ({
    data: assertConfig(config),
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  })
}

const endpoint: ProviderEndpoint = {
  endpoint_id: 'openrouter-custom',
  display_name: 'OpenRouter Custom',
  protocol: 'openai_compatible',
  base_url: 'https://openrouter.ai/api/v1',
  api_key: '**********',
  status: 'verified',
  last_test_at: '2026-05-25T12:00:00Z',
  last_test_message: 'Connected in 42ms. Model seen: openai/gpt-5.',
  timeout_seconds: 120,
  trust_env: false,
  proxy_env: null,
  metadata: {},
}

const route: ProviderRoute = {
  route_id: 'openrouter-custom:gpt-5',
  endpoint_id: 'openrouter-custom',
  route_slug: 'gpt-5',
  provider_model_id: 'openai/gpt-5',
  canonical_id: 'gpt-5',
  display_name: 'GPT-5',
  status: 'verified',
  ui_state: 'ready',
  capabilities: {
    tool_protocol: { value: 'openai-tools', source: 'probed_verified' },
  },
  metadata: {},
}

const probeCatalog = {
  local_evidence_records_count: 6,
  local_verified_records_count: 2,
  local_failed_records_count: 1,
  local_route_candidates_count: 3,
  community_catalog: {
    synced: true,
    generated_at: '2026-06-20T23:00:00+00:00',
    protocol_major: 1,
    record_count: 5,
    entries: [],
  },
  sharing: {
    mode: 'local_export_only' as const,
    auto_upload_enabled: false,
    message: 'Local probe evidence is recorded on this machine.',
  },
}

function registry(overrides: Partial<RegistryResponse> = {}): RegistryResponse {
  return {
    provider_endpoints: { [endpoint.endpoint_id]: endpoint },
    provider_routes: { [route.route_id]: route },
    runtime_policy: {
      provider_down_ttl_seconds: 60,
      probe_timeout_seconds: 5,
      token_escalation_rounds: 2,
    },
    model_profiles: {},
    model_groups: [],
    roles: {},
    canonical_groups: [],
    lint_results: [],
    setup_required: false,
    ...overrides,
  }
}

describe('API Keys v4 registry adapter', () => {
  afterEach(() => {
    api.defaults.adapter = undefined
    resetLlmApiCachesForTests()
  })

  it('loads API Keys cards from the v4 registry endpoint', async () => {
    const seen: string[] = []
    api.defaults.adapter = adapter((config) => {
      seen.push(`${config.method} ${config.url}`)
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      return registry({
        model_groups: [
          {
            canonical_id: 'gpt-5',
            display_name: 'GPT-5',
            provider_models: [
              {
                route_id: route.route_id,
                endpoint_id: endpoint.endpoint_id,
                provider_label: 'OpenRouter Custom',
                provider_kind: 'third_party',
                provider_model_id: 'openai/gpt-5',
                ui_state: 'ready',
                ui_detail: null,
                retry_at: null,
                reason_code: null,
                capability_state: 'known',
                capabilities: route.capabilities,
              },
            ],
            status_summary: {
              ready: 1,
              untested: 0,
              cooling_down: 0,
              historical_ready: 0,
              failed: 0,
              off: 0,
            },
            capability_summary: {
              capability_known_count: 1,
              thinking: 'unknown',
              tools: 'unknown',
              structured_output: 'unknown',
              max_context_tokens: null,
              max_output_tokens: null,
            },
          },
        ],
      })
    })

    const credentials = await getCredentials()

    expect(seen).toEqual([
      'get /llm/registry',
      'get /llm/registry/endpoints/openrouter-custom/secret',
    ])
    expect(credentials.providers).toHaveLength(1)
    expect(credentials.providers[0]).toMatchObject({
      id: 'openrouter-custom',
      name: 'OpenRouter Custom',
      api_key: 'sk-openrouter-real',
      base_url: 'https://openrouter.ai/api/v1',
      provider_type: 'openai_compatible',
      last_test_status: 'ok',
      last_test_at: '2026-05-25T12:00:00Z',
      last_test_message: 'Connected in 42ms. Model seen: openai/gpt-5.',
      last_error_code: '',
      available_models: [
        {
          id: 'openai/gpt-5',
          capabilities: {
            tool_protocol: { value: 'openai-tools', source: 'probed_verified' },
          },
        },
      ],
      available_sdks: ['openai_compatible'],
    })
    expect(credentials.providers[0].test_results?.[0]).toMatchObject({
      base_url: 'https://openrouter.ai/api/v1',
      provider_type: 'openai_compatible',
      last_test_status: 'ok',
      available_sdks: ['openai_compatible'],
    })
  })

  it('reuses the registry snapshot for repeated reads until callers force a refresh', async () => {
    const seen: string[] = []
    api.defaults.adapter = adapter((config) => {
      seen.push(`${config.method} ${config.url}`)
      return registry()
    })

    await getRegistry()
    await getRegistry()
    await getRegistry({ force: true })

    expect(seen).toEqual([
      'get /llm/registry',
      'get /llm/registry',
    ])
  })

  it('dedupes concurrent registry reads into one backend request', async () => {
    const seen: string[] = []
    api.defaults.adapter = async (config): Promise<AxiosResponse> => {
      seen.push(`${config.method} ${config.url}`)
      await Promise.resolve()
      return {
        data: registry(),
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }

    await Promise.all([getRegistry(), getRegistry(), getRegistry()])

    expect(seen).toEqual(['get /llm/registry'])
  })

  it('reuses roles data until callers force a refresh', async () => {
    const seen: string[] = []
    api.defaults.adapter = adapter((config) => {
      seen.push(`${config.method} ${config.url}`)
      if (config.url === '/llm/roles') {
        return { schema_version: 3, model_profiles: {}, model_bundles: {}, roles: {} }
      }
      return registry()
    })

    await getRoles()
    await getRoles()
    await getRoles({ force: true })

    expect(seen).toEqual([
      'get /llm/roles',
      'get /llm/registry',
      'get /llm/roles',
      'get /llm/registry',
    ])
  })

  it('syncs the verified community catalog through the verified read-path endpoint', async () => {
    const seen: string[] = []
    api.defaults.adapter = adapter((config) => {
      seen.push(`${config.method} ${config.url}`)
      return {
        status: 'success',
        verified_sync_enabled: true,
        sync_status: 'updated',
        record_count: 5,
        manifest_etag: 'W/"catalog-1"',
        protocol_major: 1,
      }
    })

    await expect(syncVerifiedCommunityCatalog()).resolves.toEqual({
      status: 'success',
      verified_sync_enabled: true,
      sync_status: 'updated',
      record_count: 5,
      manifest_etag: 'W/"catalog-1"',
      protocol_major: 1,
    })

    expect(seen).toEqual(['post /llm/catalog/sync-verified'])
  })

  it('projects local probe catalog evidence status from the registry snapshot', async () => {
    api.defaults.adapter = adapter(() => registry({
      probe_catalog: {
        local_evidence_records_count: 3,
        local_verified_records_count: 2,
        local_failed_records_count: 1,
        local_route_candidates_count: 0,
        community_catalog: {
          synced: true,
          generated_at: '2026-06-26T14:40:44Z',
          protocol_major: 1,
          record_count: 1,
          entries: [
            {
              public_base_url: 'https://api.deepseek.com',
              model_id: 'deepseek-v4-pro',
              capability_family: 'language_reasoning',
              method_id: 'deepseek_chat_completions',
              observed_at: '2026-06-26T09:33:40+00:00',
            },
          ],
        },
        sharing: {
          mode: 'local_export_only',
          auto_upload_enabled: false,
          message: 'Local probe evidence is recorded on this machine. MVP1 does not auto-upload community catalog evidence.',
        },
      },
    }))

    const credentials = await getCredentials({ hydrateSecrets: false })

    expect(credentials.probe_catalog).toEqual({
      local_evidence_records_count: 3,
      local_verified_records_count: 2,
      local_failed_records_count: 1,
      local_route_candidates_count: 0,
      community_catalog: {
        synced: true,
        generated_at: '2026-06-26T14:40:44Z',
        protocol_major: 1,
        record_count: 1,
        entries: [
          {
            public_base_url: 'https://api.deepseek.com',
            model_id: 'deepseek-v4-pro',
            capability_family: 'language_reasoning',
            method_id: 'deepseek_chat_completions',
            observed_at: '2026-06-26T09:33:40+00:00',
          },
        ],
      },
      sharing: {
        mode: 'local_export_only',
        auto_upload_enabled: false,
        message: 'Local probe evidence is recorded on this machine. MVP1 does not auto-upload community catalog evidence.',
      },
    })
  })

  it('can load endpoint summaries without hydrating API key secrets', async () => {
    const seen: string[] = []
    api.defaults.adapter = adapter((config) => {
      seen.push(`${config.method} ${config.url}`)
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        throw new Error('secret hydration should not run')
      }
      return registry({
        model_groups: [
          {
            canonical_id: 'gpt-5',
            display_name: 'GPT-5',
            provider_models: [
              {
                route_id: route.route_id,
                endpoint_id: endpoint.endpoint_id,
                provider_label: 'OpenRouter Custom',
                provider_kind: 'third_party',
                provider_model_id: 'openai/gpt-5',
                ui_state: 'ready',
                ui_detail: null,
                retry_at: null,
                reason_code: null,
                capability_state: 'known',
                capabilities: route.capabilities,
              },
            ],
            status_summary: {
              ready: 1,
              untested: 0,
              cooling_down: 0,
              historical_ready: 0,
              failed: 0,
              off: 0,
            },
            capability_summary: {
              capability_known_count: 1,
              thinking: 'unknown',
              tools: 'unknown',
              structured_output: 'unknown',
              max_context_tokens: null,
              max_output_tokens: null,
            },
          },
        ],
      })
    })

    const credentials = await getCredentials({ hydrateSecrets: false })

    expect(seen).toEqual(['get /llm/registry'])
    expect(credentials.providers[0]).toMatchObject({
      id: 'openrouter-custom',
      api_key: '**********',
      last_test_status: 'ok',
    })
  })

  it('saves API Keys edits through v4 endpoint upsert without calling legacy credentials API', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      if (config.method === 'get') return currentRegistry
      currentRegistry = registry({
        provider_endpoints: {
          'openrouter-custom': {
            ...endpoint,
            display_name: 'OpenRouter Renamed',
          },
        },
      })
      return currentRegistry
    })

    const loaded = await getCredentials()
    const saved = await putCredentials([
      {
        id: 'openrouter-custom',
        name: 'OpenRouter Renamed',
        api_key: loaded.providers[0].api_key,
        base_url: 'https://openrouter.ai/api/v1',
        provider_type: 'openai_compatible',
      },
    ])

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'get /llm/registry',
      'get /llm/registry/endpoints/openrouter-custom/secret',
      'put /llm/registry/endpoints',
      'get /llm/registry',
    ])
    expect(JSON.parse(String(seen[2].data))).toEqual({
      provider_endpoints: {
        'openrouter-custom': {
          endpoint_id: endpoint.endpoint_id,
          display_name: 'OpenRouter Renamed',
          protocol: endpoint.protocol,
          base_url: endpoint.base_url,
          api_key: 'sk-openrouter-real',
          timeout_seconds: endpoint.timeout_seconds,
          trust_env: endpoint.trust_env,
          proxy_env: endpoint.proxy_env,
          metadata: {
            ...endpoint.metadata,
            studio_base_url: 'https://openrouter.ai/api/v1',
          },
        },
      },
    })
    expect(saved.providers[0].name).toBe('OpenRouter Renamed')
  })

  it('sends an explicit empty secret when the user clears an API key', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      if (config.method === 'get') return currentRegistry
      currentRegistry = registry({
        provider_endpoints: {
          'openrouter-custom': {
            ...endpoint,
            api_key: null,
          },
        },
      })
      return currentRegistry
    })

    await getCredentials()
    await putCredentials([
      {
        id: 'openrouter-custom',
        name: 'OpenRouter Custom',
        api_key: '',
        base_url: 'https://openrouter.ai/api/v1',
        provider_type: 'openai_compatible',
      },
    ])

    expect(JSON.parse(String(seen[2].data)).provider_endpoints['openrouter-custom'].api_key).toBe('')
  })

  it('keeps the full registry projection after saving endpoint credentials', async () => {
    let currentRegistry = registry({ probe_catalog: probeCatalog })
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'get') return currentRegistry
      currentRegistry = registry({
        provider_endpoints: {
          'openrouter-custom': {
            ...endpoint,
            display_name: 'OpenRouter Renamed',
          },
        },
        probe_catalog: probeCatalog,
      })
      return {
        schema_version: 4,
        provider_endpoints: currentRegistry.provider_endpoints,
        provider_routes: currentRegistry.provider_routes,
        runtime_policy: currentRegistry.runtime_policy,
      }
    })

    await getCredentials({ hydrateSecrets: false })
    const saved = await putCredentials([
      {
        id: 'openrouter-custom',
        name: 'OpenRouter Renamed',
        api_key: 'sk-openrouter-real',
        base_url: 'https://openrouter.ai/api/v1',
        provider_type: 'openai_compatible',
      },
    ])

    expect(saved.probe_catalog).toEqual(probeCatalog)
    expect(saved.providers[0].name).toBe('OpenRouter Renamed')
  })

  it('tests a provider by upserting the endpoint before calling the v4 endpoint test API', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'put') return registry()
      if (config.method === 'post') return {
        ...endpoint,
        status: 'verified',
        last_test_at: '2026-05-25T12:10:00Z',
        last_test_message: 'Connected in 42ms. Model seen: openai/gpt-5.',
      }
      return registry({
        model_groups: [
          {
            canonical_id: 'gpt-5',
            display_name: 'GPT-5',
            provider_models: [
              {
                route_id: route.route_id,
                endpoint_id: endpoint.endpoint_id,
                provider_label: 'OpenRouter Custom',
                provider_kind: 'third_party',
                provider_model_id: 'openai/gpt-5',
                ui_state: 'ready',
                ui_detail: null,
                retry_at: null,
                reason_code: null,
                capability_state: 'known',
                capabilities: route.capabilities,
              },
            ],
            status_summary: {
              ready: 1,
              untested: 0,
              cooling_down: 0,
              historical_ready: 0,
              failed: 0,
              off: 0,
            },
            capability_summary: {
              capability_known_count: 1,
              thinking: 'unknown',
              tools: 'unknown',
              structured_output: 'unknown',
              max_context_tokens: null,
              max_output_tokens: null,
            },
          },
        ],
      })
    })

    const result = await testProvider({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'put /llm/registry/endpoints',
      'post /llm/endpoints/openrouter-custom/test',
    ])
    expect(result.status).toBe('ok')
    expect(result.message).toBe('Connected in 42ms. Model seen: openai/gpt-5.')
  })

  it('projects endpoint test results from the returned registry truth source', async () => {
    const discoveredRoute: ProviderRoute = {
      ...route,
      route_id: 'openrouter-custom:anthropic.claude-sonnet-4.6',
      route_slug: 'anthropic.claude-sonnet-4.6',
      provider_model_id: 'anthropic/claude-sonnet-4.6',
      canonical_id: 'claude-sonnet-4.6',
      display_name: 'Claude Sonnet 4.6 via OpenRouter',
      status: 'unverified_manual',
      capabilities: {},
    }
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'put') return registry()
      if (config.method === 'post') {
        currentRegistry = registry({
            provider_endpoints: {
              'openrouter-custom': {
                ...endpoint,
                status: 'verified',
                last_test_at: '2026-05-25T12:10:00Z',
                last_test_message: 'Connected in 42ms. Discovered 2 models.',
              },
            },
            provider_routes: {
              [route.route_id]: route,
              [discoveredRoute.route_id]: discoveredRoute,
            },
          })
        return {
          registry: currentRegistry,
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 2,
        }
      }
      return currentRegistry
    })

    const result = await testProvider({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'put /llm/registry/endpoints',
      'post /llm/endpoints/openrouter-custom/test',
    ])
    expect(result.status).toBe('ok')
    expect(result.available_models?.map((model) => model.id)).toEqual([
      'openai/gpt-5',
      'anthropic/claude-sonnet-4.6',
    ])
    expect(result.available_models).toEqual([
      expect.objectContaining({
        id: 'openai/gpt-5',
        route_id: 'openrouter-custom:gpt-5',
        status: 'verified',
      }),
      expect.objectContaining({
        id: 'anthropic/claude-sonnet-4.6',
        route_id: 'openrouter-custom:anthropic.claude-sonnet-4.6',
        status: 'unverified_manual',
      }),
    ])

    const credentials = await getCredentials()
    expect(credentials.providers[0].available_models?.map((model) => model.id)).toEqual([
      'openai/gpt-5',
      'anthropic/claude-sonnet-4.6',
    ])
  })

  it('does not judge a reachable-but-unverified endpoint as connected (apikeys#25 verified-only verdict)', async () => {
    // Under the unified test entry, only status === 'verified' counts as connected.
    // A reachable endpoint the backend leaves at 'unverified_manual' (e.g. no models
    // to probe) is no longer reported as ok by the old "not failed" heuristic.
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'put') return currentRegistry
      if (config.method === 'post') {
        currentRegistry = registry({
          provider_endpoints: {
            'openrouter-custom': {
              ...endpoint,
              status: 'unverified_manual',
              last_test_at: '2026-05-27T12:10:00Z',
              last_test_message: 'Endpoint reachable but returned no models.',
            },
          },
          provider_routes: {},
        })
        return {
          registry: currentRegistry,
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 0,
        }
      }
      return currentRegistry
    })

    const result = await getProviderModels({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'put /llm/registry/endpoints',
      'post /llm/endpoints/openrouter-custom/test',
    ])
    expect(result.status).not.toBe('ok')
    expect(result.available_models).toEqual([])

    const credentials = await getCredentials()
    expect(credentials.providers[0].last_test_status).toBe('untested')
    expect(credentials.providers[0].available_models).toEqual([])
  })

  it('routes official AND third-party Test through the single sync /endpoints/{id}/test entry (apikeys#24/#25)', async () => {
    // apikeys#24/#25: the official-only async /test-jobs fork is gone; both kinds
    // POST the one sync entry, and the FE judges connectivity off the backend's
    // authoritative endpoint status === 'verified'.
    const officialEndpoint: ProviderEndpoint = {
      ...endpoint,
      endpoint_id: 'openai-official',
      display_name: 'OpenAI Official',
      base_url: 'https://api.openai.com/v1',
      provider_kind: 'official',
    }
    const verifiedRoute: ProviderRoute = {
      ...route,
      route_id: 'openai-official:gpt-5',
      endpoint_id: 'openai-official',
      route_slug: 'gpt-5',
      provider_model_id: 'gpt-5',
      canonical_id: 'gpt-5',
      display_name: 'GPT-5',
      status: 'verified',
      ui_state: 'ready',
      capabilities: {},
    }
    const seen: Array<{ method?: string; url?: string }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url })
      if (config.method === 'put') {
        return registry({
          provider_endpoints: { 'openai-official': officialEndpoint },
          provider_routes: {},
        })
      }
      if (config.method === 'post' && config.url === '/llm/endpoints/openai-official/test') {
        return {
          registry: registry({
            provider_endpoints: {
              'openai-official': {
                ...officialEndpoint,
                status: 'verified',
                last_test_at: '2026-06-20T12:00:00Z',
                last_test_message: 'Connected in 42ms. Model seen: gpt-5.',
              },
            },
            provider_routes: { [verifiedRoute.route_id]: verifiedRoute },
          }),
          tested_endpoint_id: 'openai-official',
          discovered_model_count: 1,
        }
      }
      if (config.method === 'get' && config.url === '/llm/registry') {
        return registry({
          provider_endpoints: { 'openai-official': officialEndpoint },
          provider_routes: { [verifiedRoute.route_id]: verifiedRoute },
        })
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })

    const result = await getProviderModels({
      id: 'openai-official',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://api.openai.com/v1',
    })

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'put /llm/registry/endpoints',
      'post /llm/endpoints/openai-official/test',
    ])
    expect(result.status).toBe('ok')
    expect(result.message).toBe('Connected in 42ms. Model seen: gpt-5.')
    expect(result.available_models?.map((model) => [model.id, model.status])).toEqual([
      ['gpt-5', 'verified'],
    ])
  })

  it('judges a third-party endpoint connected only when the probe promotes it to verified (apikeys#25)', async () => {
    const probeVerifiedRoute: ProviderRoute = {
      ...route,
      status: 'verified',
      ui_state: 'ready',
    }
    const seen: Array<{ method?: string; url?: string }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url })
      if (config.method === 'put') return registry()
      if (config.method === 'post' && config.url === '/llm/endpoints/openrouter-custom/test') {
        return {
          registry: registry({
            provider_endpoints: {
              'openrouter-custom': {
                ...endpoint,
                status: 'verified',
                last_test_at: '2026-06-20T12:05:00Z',
                last_test_message: 'Generation verified via openai_compatible. Model: openai/gpt-5.',
              },
            },
            provider_routes: { [probeVerifiedRoute.route_id]: probeVerifiedRoute },
          }),
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 1,
        }
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })

    const result = await getProviderModels({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'put /llm/registry/endpoints',
      'post /llm/endpoints/openrouter-custom/test',
    ])
    expect(result.status).toBe('ok')
    expect(result.error_code).toBeNull()
    expect(result.available_models?.map((model) => model.id)).toEqual(['openai/gpt-5'])
  })

  it('keeps an endpoint usable when route evidence has a verified model even if endpoint status is stale failed', async () => {
    const verifiedRoute: ProviderRoute = {
      ...route,
      status: 'verified',
      ui_state: 'ready',
    }
    const invalidModelRoute: ProviderRoute = {
      ...route,
      route_id: 'openrouter-custom:missing-model',
      route_slug: 'missing-model',
      provider_model_id: 'missing-model',
      canonical_id: 'missing-model',
      status: 'failed',
      ui_state: 'failed',
      metadata: {
        reason_code: 'invalid_model',
        last_probe_message: 'Endpoint model probe failed (invalid_model). Provider returned HTTP 404.',
      },
    }
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'get') return currentRegistry
      if (config.method === 'put') return currentRegistry
      if (config.method === 'post' && config.url === '/llm/endpoints/openrouter-custom/test') {
        currentRegistry = registry({
          provider_endpoints: {
            'openrouter-custom': {
              ...endpoint,
              status: 'failed',
              last_test_at: '2026-06-20T12:15:00Z',
              last_test_message: 'Endpoint model probe failed (invalid_model). Provider returned HTTP 404.',
            },
          },
          provider_routes: {
            [verifiedRoute.route_id]: verifiedRoute,
            [invalidModelRoute.route_id]: invalidModelRoute,
          },
        })
        return {
          registry: currentRegistry,
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 2,
        }
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })

    const result = await getProviderModels({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(result.status).toBe('ok')
    expect(result.error_code).toBeNull()
    expect(result.model_seen).toBe('openai/gpt-5')
    expect(result.available_models?.map((model) => [model.id, model.status])).toEqual([
      ['openai/gpt-5', 'verified'],
      ['missing-model', 'failed'],
    ])

    const credentials = await getCredentials()
    expect(credentials.providers[0].last_test_status).toBe('ok')
    expect(credentials.providers[0].last_error_code).toBe('')
  })

  it('does not mark an endpoint failed when every failure is model-scoped invalid_model', async () => {
    const invalidModelRoute: ProviderRoute = {
      ...route,
      status: 'failed',
      ui_state: 'failed',
      metadata: {
        reason_code: 'invalid_model',
        last_probe_message: 'Endpoint model probe failed (invalid_model). Provider returned HTTP 404.',
      },
    }
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'get') return currentRegistry
      if (config.method === 'put') return currentRegistry
      if (config.method === 'post' && config.url === '/llm/endpoints/openrouter-custom/test') {
        currentRegistry = registry({
          provider_endpoints: {
            'openrouter-custom': {
              ...endpoint,
              status: 'failed',
              last_test_at: '2026-06-20T12:16:00Z',
              last_test_message: 'Endpoint model probe failed (invalid_model). Provider returned HTTP 404.',
            },
          },
          provider_routes: { [invalidModelRoute.route_id]: invalidModelRoute },
        })
        return {
          registry: currentRegistry,
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 1,
        }
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })

    const result = await getProviderModels({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(result.status).toBe('error')
    expect(result.error_code).toBe('invalid_model')
    expect(result.available_models?.map((model) => [model.id, model.status])).toEqual([
      ['openai/gpt-5', 'failed'],
    ])

    const credentials = await getCredentials()
    expect(credentials.providers[0].last_test_status).toBe('untested')
    expect(credentials.providers[0].last_error_code).toBe('invalid_model')
  })

  it('surfaces protocol_unsupported as its own endpoint state, never masked as untested', async () => {
    // Design §1.2 protocol matrix (2026-07-02): "this URL does not speak this
    // protocol" is a first-class endpoint fact. The old classification funnelled
    // it into invalid_model, and the model-scope masking then displayed a tested,
    // structurally dead cell as "Untested" — two lies from one conflation.
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'get') return currentRegistry
      if (config.method === 'put') return currentRegistry
      if (config.method === 'post' && config.url === '/llm/endpoints/openrouter-custom/test') {
        currentRegistry = registry({
          provider_endpoints: {
            'openrouter-custom': {
              ...endpoint,
              status: 'failed',
              last_test_at: '2026-07-02T09:00:00Z',
              last_test_message: 'Endpoint model probe failed (protocol_unsupported). Provider returned HTTP 404. not found or method not allowed',
              last_error_code: 'protocol_unsupported',
            },
          },
          provider_routes: {},
        })
        return {
          registry: currentRegistry,
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 0,
        }
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })

    const result = await getProviderModels({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(result.status).toBe('protocol_unsupported')
    expect(result.error_code).toBe('protocol_unsupported')

    const credentials = await getCredentials()
    expect(credentials.providers[0].last_test_status).toBe('protocol_unsupported')
    expect(credentials.providers[0].last_error_code).toBe('protocol_unsupported')
  })

  it('reports a third-party endpoint as failed when the probe does not reach verified (apikeys#25)', async () => {
    // The old heuristic (status !== 'failed' => ok) is gone; a reachable endpoint
    // whose batch inference probe never succeeds stays out of the connected state.
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'put') return registry()
      if (config.method === 'post' && config.url === '/llm/endpoints/openrouter-custom/test') {
        return {
          registry: registry({
            provider_endpoints: {
              'openrouter-custom': {
                ...endpoint,
                status: 'failed',
                last_test_at: '2026-06-20T12:10:00Z',
                last_test_message: 'Could not auto-detect a working protocol for this endpoint.',
              },
            },
            provider_routes: {},
          }),
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 0,
        }
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })

    const result = await getProviderModels({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(result.status).not.toBe('ok')
    expect(result.available_models).toEqual([])
  })

  it('does not echo transient test status back into the debounced credential save after a unified Test', async () => {
    const officialEndpoint: ProviderEndpoint = {
      ...endpoint,
      endpoint_id: 'openai-official',
      display_name: 'OpenAI Official',
      base_url: 'https://api.openai.com/v1',
      api_key: 'sk-live',
      provider_kind: 'official',
    }
    const verifiedRoute: ProviderRoute = {
      ...route,
      route_id: 'openai-official:gpt-5',
      endpoint_id: 'openai-official',
      route_slug: 'gpt-5',
      provider_model_id: 'gpt-5',
      canonical_id: 'gpt-5',
      display_name: 'GPT-5',
      status: 'verified',
      ui_state: 'ready',
      capabilities: {},
    }
    const putPayloads: Array<{ provider_endpoints: Record<string, ProviderEndpoint> }> = []
    let currentRegistry = registry({
      provider_endpoints: { 'openai-official': officialEndpoint },
      provider_routes: { [verifiedRoute.route_id]: verifiedRoute },
    })
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'put' && config.url === '/llm/registry/endpoints') {
        const payload = typeof config.data === 'string' ? JSON.parse(config.data) : config.data
        putPayloads.push(payload)
        const savedEndpoint = {
          ...officialEndpoint,
          ...payload.provider_endpoints['openai-official'],
          provider_kind: 'official',
        }
        currentRegistry = registry({
          provider_endpoints: { 'openai-official': savedEndpoint },
          provider_routes: {},
        })
        return currentRegistry
      }
      if (config.method === 'post' && config.url === '/llm/endpoints/openai-official/test') {
        currentRegistry = registry({
          provider_endpoints: {
            'openai-official': {
              ...officialEndpoint,
              status: 'verified',
              last_test_at: '2026-06-20T12:00:00Z',
              last_test_message: 'Connected in 42ms. Model seen: gpt-5.',
            },
          },
          provider_routes: { [verifiedRoute.route_id]: verifiedRoute },
        })
        return {
          registry: currentRegistry,
          tested_endpoint_id: 'openai-official',
          discovered_model_count: 1,
        }
      }
      if (config.method === 'get' && config.url === '/llm/registry') return currentRegistry
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })

    await getProviderModels({
      id: 'openai-official',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://api.openai.com/v1',
    })
    await putCredentials([
      {
        id: 'openai-official',
        name: 'OpenAI Official',
        provider_type: 'openai_compatible',
        api_key: 'sk-live',
        base_url: 'https://api.openai.com/v1',
      },
    ])

    expect(putPayloads[1].provider_endpoints['openai-official']).not.toHaveProperty('status')
    expect(putPayloads[1].provider_endpoints['openai-official']).not.toHaveProperty('last_test_at')
    expect(putPayloads[1].provider_endpoints['openai-official']).not.toHaveProperty('last_test_message')
  })

  it('restores official catalog-only route candidates from endpoint capability library', async () => {
    const officialEndpoint: ProviderEndpoint = {
      ...endpoint,
      endpoint_id: 'openai-official',
      display_name: 'OpenAI Official',
      base_url: 'https://api.openai.com/v1',
      provider_kind: 'official',
      metadata: {
        capability_library: [
          {
            model_id: 'gpt-image-1',
            status: 'catalog_candidate',
            route_status: 'unverified_manual',
            last_probe_message: 'No verified language route profile.',
            max_input_tokens: 8192,
            max_output_tokens: 4096,
            max_input_tokens_source: 'api_list',
            max_input_tokens_source_urls: ['https://api.openai.com/v1/models'],
            max_output_tokens_source: 'provider_doc',
            max_output_tokens_source_urls: ['https://developers.openai.com/api/docs/guides/image-generation'],
          },
        ],
      },
    }
    const officialRoute: ProviderRoute = {
      ...route,
      route_id: 'openai-official:gpt-5',
      endpoint_id: 'openai-official',
      route_slug: 'gpt-5',
      provider_model_id: 'gpt-5',
      canonical_id: 'gpt-5',
      display_name: 'GPT-5',
      status: 'verified',
    }
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'get' && config.url === '/llm/registry') {
        return registry({
          provider_endpoints: { 'openai-official': officialEndpoint },
          provider_routes: { [officialRoute.route_id]: officialRoute },
        })
      }
      throw new Error(`Unexpected request: ${config.method} ${config.url}`)
    })

    const credentials = await getCredentials({ hydrateSecrets: false })

    expect(credentials.providers[0].available_models?.map((model) => [model.id, model.status, model.last_probe_message])).toEqual([
      ['gpt-5', 'verified', null],
      ['gpt-image-1', 'unverified_manual', 'No verified language route profile.'],
    ])
    expect(credentials.providers[0].available_models?.[1].capabilities).toMatchObject({
      max_input_tokens: 8192,
      max_output_tokens: 4096,
      max_input_tokens_source: 'api_list',
      max_input_tokens_source_urls: ['https://api.openai.com/v1/models'],
      max_output_tokens_source: 'provider_doc',
      max_output_tokens_source_urls: ['https://developers.openai.com/api/docs/guides/image-generation'],
    })
  })

  it('does not clear a successful test on the next autosave when the registry response redacts the secret', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'put') {
        return registry({
          provider_endpoints: {
            'openrouter-custom': {
              ...endpoint,
              api_key: '**********',
              status: 'verified',
              last_test_at: '2026-05-25T12:10:00Z',
              last_test_message: 'Connected in 42ms. Model seen: openai/gpt-5.',
            },
          },
        })
      }
      if (config.method === 'post') {
        return {
          registry: registry({
            provider_endpoints: {
              'openrouter-custom': {
                ...endpoint,
                api_key: '**********',
                status: 'verified',
                last_test_at: '2026-05-25T12:10:00Z',
                last_test_message: 'Connected in 42ms. Model seen: openai/gpt-5.',
              },
            },
          }),
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 1,
        }
      }
      return registry()
    })

    await testProvider({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })
    await putCredentials([
      {
        id: 'openrouter-custom',
        name: 'OpenRouter Custom',
        api_key: 'sk-live',
        base_url: 'https://openrouter.ai/api/v1',
        provider_type: 'openai_compatible',
      },
    ])

    const autosavePayload = JSON.parse(String(seen[2].data))
    const endpointPayload = autosavePayload.provider_endpoints['openrouter-custom']
    expect(endpointPayload.api_key).toBe('sk-live')
    expect(endpointPayload).not.toHaveProperty('status')
    expect(endpointPayload).not.toHaveProperty('last_test_at')
    expect(endpointPayload).not.toHaveProperty('last_test_message')
  })

  it('preserves existing credential refs in ordinary endpoint save payloads', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      return registry({
        provider_endpoints: {
          'openrouter-custom': {
            ...endpoint,
            credential_ref: 'credential:openrouter-prod',
          },
        },
      })
    })

    await getCredentials({ hydrateSecrets: false })
    await putCredentials([
      {
        id: 'openrouter-custom',
        name: 'OpenRouter Custom',
        api_key: 'sk-live',
        base_url: 'https://openrouter.ai/api/v1',
        provider_type: 'openai_compatible',
      },
    ])

    const savePayload = JSON.parse(String(seen[1].data))
    expect(savePayload.provider_endpoints['openrouter-custom'].credential_ref).toBe('credential:openrouter-prod')
  })

  it('does not restore cached test result facts into ordinary save payloads', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'post') {
        return {
          registry: registry({
            provider_endpoints: {
              'openrouter-custom': {
                ...endpoint,
                api_key: '**********',
                status: 'verified',
                last_test_at: '2026-05-25T12:10:00Z',
                last_test_message: 'Connected in 42ms. Model seen: openai/gpt-5.',
              },
            },
          }),
          tested_endpoint_id: 'openrouter-custom',
          discovered_model_count: 1,
        }
      }
      if (config.method === 'put') {
        const sent = JSON.parse(String(config.data)).provider_endpoints['openrouter-custom']
        return registry({
          provider_endpoints: {
            'openrouter-custom': {
              ...endpoint,
              ...sent,
              api_key: '**********',
            },
          },
        })
      }
      return registry()
    })

    await testProvider({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'sk-live',
      base_url: 'https://openrouter.ai/api/v1',
    })
    await putCredentials([
      {
        id: 'openrouter-custom',
        name: 'OpenRouter Custom',
        api_key: 'sk-liv',
        base_url: 'https://openrouter.ai/api/v1',
        provider_type: 'openai_compatible',
      },
    ])
    await putCredentials([
      {
        id: 'openrouter-custom',
        name: 'OpenRouter Custom',
        api_key: 'sk-live',
        base_url: 'https://openrouter.ai/api/v1',
        provider_type: 'openai_compatible',
      },
    ])

    const editedPayload = JSON.parse(String(seen[2].data)).provider_endpoints['openrouter-custom']
    const restoredPayload = JSON.parse(String(seen[4].data)).provider_endpoints['openrouter-custom']
    expect(editedPayload.api_key).toBe('sk-liv')
    expect(restoredPayload.api_key).toBe('sk-live')
    for (const payload of [editedPayload, restoredPayload]) {
      expect(payload).not.toHaveProperty('status')
      expect(payload).not.toHaveProperty('last_test_at')
      expect(payload).not.toHaveProperty('last_test_message')
    }
  })

  it('does not expose stale routes as available models after autosave invalidates test params', async () => {
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      if (config.method === 'get') return currentRegistry
      if (config.method === 'put') {
        const sent = JSON.parse(String(config.data)).provider_endpoints['openrouter-custom']
        currentRegistry = registry({
          provider_endpoints: {
            'openrouter-custom': {
              ...endpoint,
              ...sent,
              api_key: '**********',
              status: 'unverified_manual',
              last_test_at: null,
              last_test_message: null,
            },
          },
          provider_routes: {
            [route.route_id]: route,
          },
        })
        return currentRegistry
      }
      return currentRegistry
    })

    await getCredentials()
    const saved = await putCredentials([
      {
        id: 'openrouter-custom',
        name: 'OpenRouter Custom',
        api_key: 'sk-openrouter-real',
        base_url: 'https://changed-openrouter.example/v1',
        provider_type: 'openai_compatible',
      },
    ])

    expect(saved.providers[0]).toMatchObject({
      last_test_status: 'untested',
      available_models: [],
      available_sdks: [],
    })
    expect(saved.providers[0].test_results?.at(-1)).toMatchObject({
      last_test_status: 'untested',
      available_models: [],
      available_sdks: [],
    })
  })

  it('projects v4 invalid-key endpoint tests into the restored API Keys error state', async () => {
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'put') return registry()
      if (config.method === 'post') return {
        ...endpoint,
        status: 'failed',
        last_test_at: '2026-05-25T12:12:00Z',
        last_test_message: 'Invalid API key (invalid_api_key).',
      }
      return registry()
    })

    const result = await testProvider({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'not-a-key',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(result.status).toBe('invalid_key')
    expect(result.error_code).toBe('invalid_api_key')
    expect(result.message).toBe('Invalid API key (invalid_api_key).')
  })

  it('keeps unauthorized v4 probe messages in the invalid-key state even with broad vendor codes', async () => {
    api.defaults.adapter = adapter((config) => {
      if (config.method === 'put') return registry()
      if (config.method === 'post') return {
        ...endpoint,
        status: 'failed',
        last_test_at: '2026-05-25T12:13:00Z',
        last_test_message: 'Invalid API key (invalid_request_error).',
      }
      return registry()
    })

    const result = await testProvider({
      id: 'openrouter-custom',
      provider_type: 'openai_compatible',
      api_key: 'not-a-key',
      base_url: 'https://openrouter.ai/api/v1',
    })

    expect(result.status).toBe('invalid_key')
    expect(result.error_code).toBe('invalid_request_error')
  })

  it('deletes cached endpoints that are absent from the API Keys save snapshot', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    let currentRegistry = registry()
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      if (config.method === 'get') return currentRegistry
      currentRegistry = registry({ provider_endpoints: {}, provider_routes: {} })
      return currentRegistry
    })

    await getCredentials()
    const saved = await putCredentials([])

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'get /llm/registry',
      'get /llm/registry/endpoints/openrouter-custom/secret',
      'delete /llm/registry/endpoints/openrouter-custom',
      'get /llm/registry',
    ])
    expect(saved.providers).toEqual([])
  })

  it('manual model test posts model ids to the endpoint-scoped API and projects models from returned routes', async () => {
    const manualRoute: ProviderRoute = {
      ...route,
      route_id: 'openrouter-custom:manual-model',
      route_slug: 'manual-model',
      provider_model_id: 'manual-model',
      canonical_id: 'manual-model',
      display_name: 'manual-model',
      status: 'verified',
      capabilities: {},
    }
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      return {
        registry: registry({
          provider_routes: {
            [route.route_id]: route,
            [manualRoute.route_id]: manualRoute,
          },
        }),
        results: [
          {
            model_id: 'manual-model',
            status: 'ok',
            route_id: 'openrouter-custom:manual-model',
            message: null,
          },
        ],
      }
    })

    const response = await testProviderModels({
      provider_id: 'openrouter-custom',
      model_ids: ['manual-model'],
    })

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'post /llm/endpoints/openrouter-custom/models/test',
    ])
    expect(JSON.parse(String(seen[0].data))).toEqual({ model_ids: ['manual-model'] })
    expect(response.results).toEqual([
      {
        model_id: 'manual-model',
        status: 'ok',
        route_id: 'openrouter-custom:manual-model',
        message: null,
      },
    ])
    expect(response.available_models.map((model) => model.id)).toEqual([
      'openai/gpt-5',
      'manual-model',
    ])
  })

  it('does not derive provider model states from raw endpoint and route facts', () => {
    const missingKeyEndpoint: ProviderEndpoint = {
      ...endpoint,
      api_key: null,
      status: 'unverified_manual',
    }
    const invalidModelRoute: ProviderRoute = {
      ...route,
      route_id: 'openrouter-custom:invalid-model',
      route_slug: 'invalid-model',
      provider_model_id: 'invalid-model',
      display_name: 'Invalid Model',
      status: 'failed',
      metadata: {
        reason_code: 'invalid_model',
      },
    }

    const groups = modelGroupsFromRegistry(registry({
      provider_endpoints: { [endpoint.endpoint_id]: missingKeyEndpoint },
      provider_routes: {
        [route.route_id]: {
          ...route,
          status: 'unverified_manual',
        },
        [invalidModelRoute.route_id]: invalidModelRoute,
      },
      model_groups: [],
    }))

    expect(groups).toEqual([])
  })

  it('keeps backend Cooling Down projection and retry timestamp', () => {
    const retryAt = '2026-05-26T18:30:00Z'
    const groups = modelGroupsFromRegistry(registry({
      model_groups: [
        {
          canonical_id: 'gpt-5',
          display_name: 'GPT-5',
          provider_models: [
            {
              route_id: route.route_id,
              provider_label: 'OpenRouter Custom',
              provider_kind: 'third_party',
              provider_model_id: 'openai/gpt-5',
              ui_state: 'cooling_down',
              ui_detail: 'Provider returned 429.',
              retry_at: retryAt,
              reason_code: 'rate_limited',
              capability_state: 'known',
              capabilities: route.capabilities,
            },
          ],
          status_summary: {
            ready: 0,
            untested: 0,
            cooling_down: 1,
            historical_ready: 0,
            failed: 0,
            off: 0,
          },
          capability_summary: {
            capability_known_count: 1,
            thinking: 'unknown',
            tools: 'unknown',
            structured_output: 'unknown',
            max_context_tokens: null,
            max_output_tokens: null,
          },
        },
      ],
    }))

    expect(groups[0].provider_models[0]).toMatchObject({
      ui_state: 'cooling_down',
      retry_at: retryAt,
      reason_code: 'rate_limited',
    })
  })

  it('uses non-empty backend model_groups without merging legacy provider_routes', () => {
    const groups = modelGroupsFromRegistry(registry({
      provider_routes: {
        [route.route_id]: route,
        'legacy-extra:gpt-5-mini': {
          ...route,
          route_id: 'legacy-extra:gpt-5-mini',
          endpoint_id: endpoint.endpoint_id,
          route_slug: 'gpt-5-mini',
          provider_model_id: 'gpt-5-mini',
          canonical_id: 'gpt-5-mini',
          display_name: 'GPT-5 Mini',
        },
      },
      model_groups: [
        {
          canonical_id: 'backend-only',
          display_name: 'Backend Only',
          provider_models: [],
          status_summary: {
            ready: 0,
            untested: 0,
            cooling_down: 0,
            historical_ready: 0,
            failed: 0,
            off: 0,
          },
          capability_summary: {
            capability_known_count: 0,
            thinking: 'unknown',
            tools: 'unknown',
            structured_output: 'unknown',
            max_context_tokens: null,
            max_output_tokens: null,
          },
        },
      ],
    }))

    expect(groups.map((group) => group.canonical_id)).toEqual(['backend-only'])
  })

  it('returns no model groups when backend projection is absent', () => {
    const legacyRegistry = registry()
    delete (legacyRegistry as Partial<RegistryResponse>).model_groups
    const groups = modelGroupsFromRegistry(legacyRegistry)

    expect(groups).toEqual([])
  })

  it('loads v3 backend roles into the LLM Roles authoring shape', async () => {
    api.defaults.adapter = adapter((config) => {
      if (config.url === '/llm/registry') {
        return registry({
          model_groups: [
            {
              canonical_id: 'gpt-5',
              display_name: 'GPT-5',
              provider_models: [
                {
                  route_id: route.route_id,
                  provider_label: 'OpenRouter Custom',
                  provider_kind: 'third_party',
                  provider_model_id: 'openai/gpt-5',
                  ui_state: 'ready',
                  ui_detail: null,
                  retry_at: null,
                  reason_code: null,
                  capability_state: 'known',
                  capabilities: route.capabilities,
                },
              ],
              status_summary: {
                ready: 1,
                untested: 0,
                cooling_down: 0,
                historical_ready: 0,
                failed: 0,
                off: 0,
              },
              capability_summary: {
                capability_known_count: 1,
                thinking: 'supported',
                tools: 'unknown',
                structured_output: 'unknown',
                max_context_tokens: null,
                max_output_tokens: null,
              },
            },
          ],
        })
      }
      if (config.url === '/llm/roles') {
        return {
          schema_version: 3,
          model_profiles: {},
          model_bundles: {},
          roles: {
            analyst: {
              role_kind: 'graph_agent',
              system_prompt_prefix: '',
              model_fallback_enabled: true,
              intent: { provider_preference: 'manual_order' },
              model_groups: [
                {
                  canonical_id: 'gpt-5',
                  display_name: 'GPT-5',
                  provider_models: [{ route_id: route.route_id }],
                },
              ],
              fallback_chain: [],
              lint_requirements: {},
            },
          },
        }
      }
      return registry({
        model_groups: [
          {
            canonical_id: 'gpt-5',
            display_name: 'GPT-5',
            provider_models: [
              {
                route_id: route.route_id,
                endpoint_id: endpoint.endpoint_id,
                provider_label: 'OpenRouter Custom',
                provider_kind: 'third_party',
                provider_model_id: 'openai/gpt-5',
                ui_state: 'ready',
                ui_detail: null,
                retry_at: null,
                reason_code: null,
                capability_state: 'known',
                capabilities: route.capabilities,
              },
            ],
            status_summary: {
              ready: 1,
              untested: 0,
              cooling_down: 0,
              historical_ready: 0,
              failed: 0,
              off: 0,
            },
            capability_summary: {
              capability_known_count: 1,
              thinking: 'unknown',
              tools: 'unknown',
              structured_output: 'unknown',
              max_context_tokens: null,
              max_output_tokens: null,
            },
          },
        ],
      })
    })

    const roles = await getRoles()

    expect(roles.models['gpt-5']).toMatchObject({
      name: 'GPT-5',
      providers: { [route.route_id]: 'openai/gpt-5' },
      reasoning: true,
    })
    expect(roles.providers[route.route_id]).toEqual({
      name: 'OpenRouter Custom',
      type: 'openai_compatible',
      endpoint_id: 'openrouter-custom',
    })
    expect(roles.roles.analyst).toMatchObject({
      role_kind: 'graph_agent',
      model_fallback_enabled: true,
      active_model: 'gpt-5',
      models: {
        'gpt-5': { providers: [route.route_id] },
      },
    })
    expect(Object.prototype.hasOwnProperty.call(roles.roles.analyst, 'model_fallback')).toBe(false)
  })

  it('keeps persisted model bundle groups addressable when roles reference them', async () => {
    api.defaults.adapter = adapter((config) => {
      if (config.url === '/llm/roles') {
        return {
          schema_version: 3,
          model_profiles: {},
          model_bundles: {
            premium_stack: {
              model_profile_id: 'premium_stack',
              display_name: 'Premium Stack',
              canonical_id: 'bundle:premium_stack',
              fallback_chain: [{ route_id: route.route_id }],
            },
          },
          roles: {
            analyst: {
              role_kind: 'graph_agent',
              system_prompt_prefix: '',
              model_fallback_enabled: true,
              intent: { provider_preference: 'manual_order' },
              model_groups: [
                {
                  canonical_id: 'bundle:premium_stack',
                  display_name: 'Premium Stack',
                  provider_models: [{ route_id: route.route_id }],
                },
              ],
              fallback_chain: [{ route_id: route.route_id }],
              lint_requirements: {},
            },
          },
        }
      }
      return registry({
        model_groups: [
          {
            canonical_id: 'gpt-5',
            display_name: 'GPT-5',
            provider_models: [
              {
                route_id: route.route_id,
                endpoint_id: endpoint.endpoint_id,
                provider_label: 'OpenRouter Custom',
                provider_kind: 'third_party',
                provider_model_id: 'openai/gpt-5',
                ui_state: 'ready',
                ui_detail: null,
                retry_at: null,
                reason_code: null,
                capability_state: 'known',
                capabilities: route.capabilities,
              },
            ],
            status_summary: {
              ready: 1,
              untested: 0,
              cooling_down: 0,
              historical_ready: 0,
              failed: 0,
              off: 0,
            },
            capability_summary: {
              capability_known_count: 1,
              thinking: 'unknown',
              tools: 'unknown',
              structured_output: 'unknown',
              max_context_tokens: null,
              max_output_tokens: null,
            },
          },
        ],
      })
    })

    const roles = await getRoles()

    expect(roles.models['bundle:premium_stack']).toMatchObject({
      name: 'Premium Stack',
      providers: { [route.route_id]: 'openai/gpt-5' },
    })
    expect(roles.roles.analyst.models['bundle:premium_stack']).toEqual({
      providers: [route.route_id],
    })
  })

  it('saves the LLM Roles authoring shape as v3 model groups', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.url === '/llm/registry') return registry()
      if (config.method === 'put' && config.url === '/llm/roles') {
        return JSON.parse(String(config.data))
      }
      return registry()
    })

    await putRoles({
      schema_version: 3,
      models: {
        'gpt-5': {
          name: 'GPT-5',
          providers: { [route.route_id]: 'openai/gpt-5' },
        },
      },
      providers: {
        [route.route_id]: { name: 'OpenRouter Custom', type: 'openai_compatible' },
      },
      roles: {
        analyst: {
          role_kind: 'graph_agent',
          model_fallback_enabled: false,
          active_model: 'gpt-5',
          models: {
            'gpt-5': { providers: [route.route_id], temperature: 0.2, max_tokens: 8192 },
          },
          system_prompt_prefix: '',
          lint_requirements: {},
        },
      },
    })

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual(['put /llm/roles', 'get /llm/registry'])
    expect(JSON.parse(String(seen[0].data))).toEqual({
      schema_version: 3,
      model_profiles: {},
      model_bundles: {},
      roles: {
        analyst: {
          role_kind: 'graph_agent',
          system_prompt_prefix: '',
          model_fallback_enabled: false,
          intent: { provider_preference: 'manual_order' },
          model_groups: [
            {
              canonical_id: 'gpt-5',
              display_name: 'GPT-5',
              provider_models: [{ route_id: route.route_id }],
            },
          ],
          fallback_chain: [],
          lint_requirements: {},
        },
      },
    })
  })

  it('does not collapse the returned model directory to empty when the registry cache is cold (roles-registry-hydration-prune)', async () => {
    // putRoles used to build its returned RolesData from `cachedRegistry ?? null`
    // instead of awaiting a fresh registry — with a cold cache (e.g. right
    // after syncVerifiedCommunityCatalog nulls it) the echoed-back `models`/
    // `providers` directories silently came back empty even though the role's
    // own provider routes were real. LlmRolesTab's pruning then mistook that
    // emptiness for "confirmed invalid" and wiped the role's real routes on
    // the very next autosave. putRoles must always resolve a real registry.
    const registryWithGpt5 = registry({
      model_groups: [
        {
          canonical_id: 'gpt-5',
          display_name: 'GPT-5',
          provider_models: [
            {
              route_id: route.route_id,
              endpoint_id: endpoint.endpoint_id,
              provider_label: 'OpenRouter Custom',
              provider_kind: 'third_party',
              provider_model_id: 'openai/gpt-5',
              ui_state: 'ready',
              ui_detail: null,
              retry_at: null,
              reason_code: null,
              capability_state: 'known',
              capabilities: route.capabilities,
            },
          ],
          status_summary: {
            ready: 1,
            untested: 0,
            cooling_down: 0,
            historical_ready: 0,
            failed: 0,
            off: 0,
          },
          capability_summary: {
            capability_known_count: 1,
            thinking: 'unknown',
            tools: 'unknown',
            structured_output: 'unknown',
            max_context_tokens: null,
            max_output_tokens: null,
          },
        },
      ],
    })
    api.defaults.adapter = adapter((config) => {
      if (config.url === '/llm/registry') return registryWithGpt5
      if (config.method === 'put' && config.url === '/llm/roles') {
        return JSON.parse(String(config.data))
      }
      return registryWithGpt5
    })

    const roles = await putRoles({
      schema_version: 3,
      models: {
        'gpt-5': {
          name: 'GPT-5',
          providers: { [route.route_id]: 'openai/gpt-5' },
        },
      },
      providers: {
        [route.route_id]: { name: 'OpenRouter Custom', type: 'openai_compatible' },
      },
      roles: {
        analyst: {
          role_kind: 'graph_agent',
          model_fallback_enabled: false,
          active_model: 'gpt-5',
          models: {
            'gpt-5': { providers: [route.route_id], temperature: 0.2, max_tokens: 8192 },
          },
          system_prompt_prefix: '',
          lint_requirements: {},
        },
      },
    })

    expect(Object.keys(roles.models)).not.toHaveLength(0)
    expect(Object.keys(roles.providers)).not.toHaveLength(0)
    expect(roles.roles.analyst.models['gpt-5'].providers).toEqual([route.route_id])
  })

  it('deletes a persisted role through the role delete endpoint', async () => {
    const seen: Array<{ method?: string; url?: string }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url })
      if (config.url === '/llm/registry') return registry()
      if (config.method === 'delete' && config.url === '/llm/roles/analyst') {
        return {
          schema_version: 3,
          model_profiles: {},
          model_bundles: {},
          roles: {},
        }
      }
      return registry()
    })

    const roles = await deleteRole('analyst')

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'delete /llm/roles/analyst',
      'get /llm/registry',
    ])
    expect(roles.roles.analyst).toBeUndefined()
  })

  it('deletes a persisted model bundle through the bundle delete endpoint', async () => {
    const seen: Array<{ method?: string; url?: string }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url })
      if (config.url === '/llm/registry') return registry()
      if (config.method === 'delete' && config.url === '/llm/model-bundles/premium_stack') {
        return {
          schema_version: 3,
          model_profiles: {},
          model_bundles: {},
          roles: {},
        }
      }
      return registry()
    })

    const roles = await deleteModelBundle('premium_stack')

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'delete /llm/model-bundles/premium_stack',
      'get /llm/registry',
    ])
    expect(roles.model_bundles?.premium_stack).toBeUndefined()
  })

  it('can force a route probe for Cooling Down Test Now', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      return route
    })

    await probeRoute(route.route_id, { capabilities: [], force: true })

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'post /llm/routes/openrouter-custom%3Agpt-5/probe?force=true',
    ])
    expect(JSON.parse(String(seen[0].data))).toEqual({ capabilities: [] })
  })

  it('probes a route for multimodal (image) input via the probe-multimodal endpoint', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      return route
    })

    await probeRouteMultimodal(route.route_id)

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'post /llm/routes/openrouter-custom%3Agpt-5/probe-multimodal',
    ])
  })

  it('routeAcceptsImageVerified is true only for probe-verified image input', () => {
    const base = { ...route }
    expect(
      routeAcceptsImageVerified({
        ...base,
        capabilities: {
          input_modalities: { value: ['text', 'image'], source: 'probed_verified' },
        },
      }),
    ).toBe(true)
    // catalog 声称(provider_doc)不算实测通过。
    expect(
      routeAcceptsImageVerified({
        ...base,
        capabilities: {
          input_modalities: { value: ['text', 'image'], source: 'provider_doc' },
        },
      }),
    ).toBe(false)
    // 没图 = 不认图。
    expect(
      routeAcceptsImageVerified({
        ...base,
        capabilities: {
          input_modalities: { value: ['text'], source: 'probed_verified' },
        },
      }),
    ).toBe(false)
    // 没探测过 = 不认图。
    expect(routeAcceptsImageVerified({ ...base, capabilities: {} })).toBe(false)
  })

  it('runs a persisted role test and returns provider diagnostics', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      return {
        role_name: 'analyst',
        status: 'warning',
        warnings: [{ message: 'Thinking is required but capability is unknown.' }],
        model_groups: [{
          canonical_id: 'gpt-5',
          display_name: 'GPT 5',
          provider_results: [{
            route_id: route.route_id,
            provider_label: 'OpenRouter Custom',
            provider_ui_state: 'cooling_down',
            role_fit: 'needs_test',
            admission_decision: 'temporary_skip',
            status: 'blocked',
            warnings: [{ message: 'Thinking is required but capability is unknown.' }],
            retry_at: '2026-12-31T00:00:00Z',
            message: 'Retry after transient rate limit.',
            resolved_settings: {},
          }],
        }],
      }
    })

    const result = await testRole('analyst')

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'post /llm/roles/analyst/test',
    ])
    expect(JSON.parse(String(seen[0].data))).toEqual({})
    expect(result.model_groups[0].provider_results[0]).toMatchObject({
      provider_label: 'OpenRouter Custom',
      provider_ui_state: 'cooling_down',
      role_fit: 'needs_test',
      admission_decision: 'temporary_skip',
      status: 'blocked',
    })
  })

  it('starts and reads persisted role test jobs', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.method === 'post') {
        return {
          job_id: 'job-1',
          role_name: 'analyst',
          status: 'running',
          message: 'Testing role routes.',
          provider_statuses: [{
            canonical_id: 'gpt-5',
            route_id: route.route_id,
            status: 'testing',
            message: null,
          }],
          result: null,
        }
      }
      return {
        job_id: 'job-1',
        role_name: 'analyst',
        status: 'completed',
        message: 'Role test completed.',
        provider_statuses: [{
          canonical_id: 'gpt-5',
          route_id: route.route_id,
          status: 'ok',
          message: null,
        }],
        result: {
          role_name: 'analyst',
          status: 'ok',
          warnings: [],
          model_groups: [],
        },
      }
    })

    const started = await startRoleTestJob('analyst')
    const finished = await getRoleTestJob(started.job_id)

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'post /llm/roles/analyst/test-jobs',
      'get /llm/role-test-jobs/job-1',
    ])
    expect(JSON.parse(String(seen[0].data))).toEqual({})
    expect(started.provider_statuses[0].status).toBe('testing')
    expect(finished.result?.status).toBe('ok')
  })
})
