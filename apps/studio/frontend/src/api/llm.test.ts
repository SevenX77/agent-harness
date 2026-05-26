import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api } from './client'
import {
  getCredentials,
  putCredentials,
  resetLlmApiCachesForTests,
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
  capabilities: {
    tool_protocol: { value: 'openai-tools', source: 'probed_verified' },
  },
  metadata: {},
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
      return registry()
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

  it('saves API Keys edits through v4 endpoint upsert without calling legacy credentials API', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      if (config.method === 'get') return registry()
      return registry({
        provider_endpoints: {
          'openrouter-custom': {
            ...endpoint,
            display_name: 'OpenRouter Renamed',
          },
        },
      })
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
    ])
    expect(JSON.parse(String(seen[2].data))).toEqual({
      provider_endpoints: {
        'openrouter-custom': {
          ...endpoint,
          display_name: 'OpenRouter Renamed',
          api_key: 'sk-openrouter-real',
        },
      },
    })
    expect(saved.providers[0].name).toBe('OpenRouter Renamed')
  })

  it('sends an explicit empty secret when the user clears an API key', async () => {
    const seen: Array<{ method?: string; url?: string; data?: unknown }> = []
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      if (config.method === 'get') return registry()
      return registry({
        provider_endpoints: {
          'openrouter-custom': {
            ...endpoint,
            api_key: null,
          },
        },
      })
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
      return registry()
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

    const credentials = await getCredentials()
    expect(credentials.providers[0].available_models?.map((model) => model.id)).toEqual([
      'openai/gpt-5',
      'anthropic/claude-sonnet-4.6',
    ])
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
    expect(autosavePayload.provider_endpoints['openrouter-custom']).toMatchObject({
      api_key: 'sk-live',
      status: 'verified',
      last_test_message: 'Connected in 42ms. Model seen: openai/gpt-5.',
    })
  })

  it('restores a cached test result into the backend payload when edited params match again', async () => {
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
    const restoredPayload = JSON.parse(String(seen[3].data)).provider_endpoints['openrouter-custom']
    expect(editedPayload).toMatchObject({
      api_key: 'sk-liv',
      status: 'unverified_manual',
      last_test_message: null,
    })
    expect(restoredPayload).toMatchObject({
      api_key: 'sk-live',
      status: 'verified',
      last_test_at: '2026-05-25T12:10:00Z',
      last_test_message: 'Connected in 42ms. Model seen: openai/gpt-5.',
    })
  })

  it('does not expose stale routes as available models after autosave invalidates test params', async () => {
    api.defaults.adapter = adapter((config) => {
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      if (config.method === 'get') return registry()
      if (config.method === 'put') {
        const sent = JSON.parse(String(config.data)).provider_endpoints['openrouter-custom']
        return registry({
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
      }
      return registry()
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
    api.defaults.adapter = adapter((config) => {
      seen.push({ method: config.method, url: config.url, data: config.data })
      if (config.url === '/llm/registry/endpoints/openrouter-custom/secret') {
        return { endpoint_id: 'openrouter-custom', api_key: 'sk-openrouter-real' }
      }
      if (config.method === 'get') return registry()
      return registry({ provider_endpoints: {}, provider_routes: {} })
    })

    await getCredentials()
    const saved = await putCredentials([])

    expect(seen.map((item) => `${item.method} ${item.url}`)).toEqual([
      'get /llm/registry',
      'get /llm/registry/endpoints/openrouter-custom/secret',
      'delete /llm/registry/endpoints/openrouter-custom',
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
})
