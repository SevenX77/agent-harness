import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'
const SKILL_ID = 'smoke'

const skillDetail = {
  manifest: {
    schema_version: '2.0',
    type: 'graph',
    name: 'Smoke Skill',
    description: 'Round 3 API Keys smoke skill',
    license: null,
    version: null,
    author: null,
    metadata: null,
    context_mapping: {},
    io: { inputs: [], outputs: [] },
    phases: [],
  },
  file_paths: {},
  has_golden: false,
  latest_run_metadata: null,
  lint_result: null,
}

const skillSummary = {
  id: SKILL_ID,
  name: 'Smoke Skill',
  description: 'Round 3 API Keys smoke skill',
  phase_count: 0,
  has_golden: false,
  last_run_at: null,
  directory_path: '/tmp/smoke',
  config_mismatch: null,
}

type CredentialProvider = {
  id: string
  name: string
  api_key: string
  base_url: string
  provider_type: 'anthropic_compatible' | 'openai_compatible' | 'google_genai'
  last_test_status?: string
  last_test_at?: string
  last_test_message?: string
  last_error_code?: string
  available_models?: Array<{ id: string; capabilities?: Record<string, unknown> }>
  available_sdks?: string[]
  test_results?: CredentialTestResult[]
}

type CredentialTestResult = {
  params_fingerprint: string
  base_url: string
  provider_type: CredentialProvider['provider_type']
  last_test_status: string
  last_test_at?: string
  last_test_message?: string
  last_error_code?: string
  available_models?: CredentialProvider['available_models']
  available_sdks?: string[]
}

const initialProviders: CredentialProvider[] = [
  {
    id: 'deepseek-official',
    name: 'DeepSeek Official',
    api_key: 'sk-deepseek',
    base_url: 'https://api.deepseek.com',
    provider_type: 'openai_compatible',
    last_test_status: 'ok',
    last_test_at: '2026-05-19T00:00:00Z',
    last_test_message: '',
    last_error_code: '',
    available_sdks: ['openai_compatible'],
    available_models: [{ id: 'deepseek-chat', capabilities: { max_context_tokens: 64000 } }],
  },
  {
    id: 'openrouter-custom',
    name: 'OpenRouter Custom',
    api_key: 'sk-openrouter',
    base_url: 'https://openrouter.ai/api/v1',
    provider_type: 'openai_compatible',
    last_test_status: 'ok',
    last_test_at: '2026-05-19T00:00:00Z',
    last_test_message: '',
    last_error_code: '',
    available_sdks: ['openai_compatible'],
    available_models: [{ id: 'gpt-5', capabilities: { max_context_tokens: 128000 } }],
  },
]

function paramsFingerprint(provider: Pick<CredentialProvider, 'api_key' | 'base_url' | 'provider_type'>): string {
  return fnv1a32(JSON.stringify({
    api_key: provider.api_key || '',
    base_url: provider.base_url || '',
    provider_type: provider.provider_type ?? null,
  }))
}

function fnv1a32(value: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

function hasTestOutcome(provider: CredentialProvider): boolean {
  return Boolean(
    provider.last_test_status && provider.last_test_status !== 'untested' ||
    provider.last_test_at ||
    provider.last_test_message ||
    provider.last_error_code ||
    provider.available_models?.length ||
    provider.available_sdks?.length,
  )
}

function topLevelResult(provider: CredentialProvider): CredentialTestResult | null {
  if (!hasTestOutcome(provider)) return null
  return {
    params_fingerprint: paramsFingerprint(provider),
    base_url: provider.base_url || '',
    provider_type: provider.provider_type,
    last_test_status: provider.last_test_status ?? 'untested',
    last_test_at: provider.last_test_at ?? '',
    last_test_message: provider.last_test_message ?? '',
    last_error_code: provider.last_error_code ?? '',
    available_models: provider.available_models ?? [],
    available_sdks: provider.available_sdks ?? [],
  }
}

function upsertResult(results: CredentialTestResult[], result: CredentialTestResult | null): CredentialTestResult[] {
  if (!result) return results
  return [...results.filter((item) => item.params_fingerprint !== result.params_fingerprint), result]
}

function applyResult(provider: CredentialProvider, result: CredentialTestResult): CredentialProvider {
  return {
    ...provider,
    last_test_status: result.last_test_status,
    last_test_at: result.last_test_at ?? '',
    last_test_message: result.last_test_message ?? '',
    last_error_code: result.last_error_code ?? '',
    available_models: result.available_models ?? [],
    available_sdks: result.available_sdks ?? [],
  }
}

function resetResult(provider: CredentialProvider): CredentialProvider {
  return {
    ...provider,
    last_test_status: 'untested',
    last_test_at: '',
    last_test_message: '',
    last_error_code: '',
    available_models: [],
    available_sdks: [],
  }
}

function routeSlug(modelId: string): string {
  return modelId.toLowerCase().replace(/\//g, '.').replace(/_/g, '-').replace(/[^a-z0-9._-]+/g, '-')
}

function endpointStatus(provider: CredentialProvider): string {
  if (provider.last_test_status === 'ok') return 'verified'
  if (provider.last_test_status === 'error') return 'failed'
  return 'unverified_manual'
}

function registryFromProviders(providers: CredentialProvider[]) {
  const provider_endpoints = Object.fromEntries(providers.map((provider) => [
    provider.id,
    {
      endpoint_id: provider.id,
      display_name: provider.name,
      protocol: provider.provider_type,
      base_url: provider.base_url,
      api_key: provider.api_key,
      status: endpointStatus(provider),
      last_test_at: provider.last_test_at ?? null,
      last_test_message: provider.last_test_message ?? null,
      timeout_seconds: 120,
      trust_env: false,
      proxy_env: null,
      metadata: {},
    },
  ]))
  const provider_routes = Object.fromEntries(providers.flatMap((provider) => (
    (provider.available_models ?? []).map((model) => {
      const slug = routeSlug(model.id)
      const routeId = `${provider.id}:${slug}`
      return [
        routeId,
        {
          route_id: routeId,
          endpoint_id: provider.id,
          route_slug: slug,
          provider_model_id: model.id,
          canonical_id: slug,
          display_name: model.id,
          status: endpointStatus(provider),
          capabilities: Object.fromEntries(Object.entries(model.capabilities ?? {}).map(([key, value]) => [
            key,
            { value, source: 'api_list' },
          ])),
          metadata: {},
        },
      ]
    })
  )))
  return {
    provider_endpoints,
    provider_routes,
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
  }
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function mockBackend(page: Page) {
  let providers = structuredClone(initialProviders) as CredentialProvider[]

  await page.route('**/api/settings', async (route) => {
    await fulfillJson(route, { user_id: 'e2e-user', gitea_host: 'https://gitea.example' })
  })
  await page.route('**/api/skills', async (route) => {
    if (route.request().method() === 'GET') {
      await fulfillJson(route, [skillSummary])
      return
    }
    await route.continue()
  })
  await page.route(`**/api/skills/${SKILL_ID}`, async (route) => {
    await fulfillJson(route, skillDetail)
  })
  await page.route(`**/api/skills/${SKILL_ID}/copilot/context`, async (route) => {
    await fulfillJson(route, { accepted: true, summary: 'Edit at 1', reason: null })
  })
  await page.route('**/api/llm/registry', async (route) => {
    await fulfillJson(route, registryFromProviders(providers))
  })
  await page.route('**/api/llm/registry/endpoints**', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = JSON.parse(route.request().postData() ?? '{}') as {
        provider_endpoints?: Record<string, {
          endpoint_id: string
          display_name: string
          protocol: CredentialProvider['provider_type']
          base_url: string
          api_key?: string | null
        }>
      }
      const incoming = Object.values(body.provider_endpoints ?? {})
      providers = incoming.map((endpoint) => {
        const existing = providers.find((item) => item.id === endpoint.endpoint_id)
        const next: CredentialProvider = {
          id: endpoint.endpoint_id,
          name: endpoint.display_name,
          api_key: endpoint.api_key || existing?.api_key || '',
          base_url: endpoint.base_url,
          provider_type: endpoint.protocol,
          last_test_status: 'untested',
          last_test_at: '',
          last_test_message: '',
          last_error_code: '',
          available_models: [],
          available_sdks: [],
          test_results: existing?.test_results ?? [],
        }
        const cached = next.test_results?.find((result) => result.params_fingerprint === paramsFingerprint(next))
        return cached ? applyResult(next, cached) : resetResult(next)
      })
    }
    await fulfillJson(route, registryFromProviders(providers))
  })
  await page.route('**/api/llm/endpoints/*/test', async (route) => {
    const endpointId = decodeURIComponent(new URL(route.request().url()).pathname.split('/').at(-2) ?? '')
    providers = providers.map((provider) => {
      if (provider.id !== endpointId) return provider
      const result: CredentialTestResult = {
        params_fingerprint: paramsFingerprint(provider),
        base_url: provider.base_url,
        provider_type: provider.provider_type,
        last_test_status: 'ok',
        last_test_at: '2026-05-25T00:00:00Z',
        last_test_message: 'Credential present.',
        last_error_code: '',
        available_models: provider.available_models ?? [],
        available_sdks: [provider.provider_type],
      }
      return {
        ...applyResult(provider, result),
        test_results: upsertResult(provider.test_results ?? [], result),
      }
    })
    const endpoint = registryFromProviders(providers).provider_endpoints[endpointId]
    await fulfillJson(route, endpoint)
  })
  await page.route('**/api/llm/credentials**', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = JSON.parse(route.request().postData() ?? '{}') as { providers?: CredentialProvider[] }
      providers = (body.providers ?? []).map((provider) => {
        const existing = providers.find((item) => item.id === provider.id)
        const test_results = upsertResult(existing?.test_results ?? [], existing ? topLevelResult(existing) : null)
        const next = {
          ...existing,
          ...provider,
          api_key: provider.api_key || existing?.api_key || '',
          last_test_status: 'untested',
          last_test_at: '',
          last_test_message: '',
          last_error_code: '',
          available_models: [],
          available_sdks: [],
          test_results,
        }
        const cached = test_results.find((result) => result.params_fingerprint === paramsFingerprint(next))
        return cached ? applyResult(next, cached) : resetResult(next)
      })
    }
    await fulfillJson(route, { providers })
  })
  await page.route('**/api/llm/providers/notable-models**', async (route) => {
    const url = new URL(route.request().url())
    const providerKey = url.searchParams.get('provider_key') ?? ''
    const notable: Record<string, string[]> = {
      anthropic: ['claude-opus-4-7', 'claude-sonnet-4-7'],
      openai: ['gpt-5', 'gpt-4o'],
      gemini: ['gemini-2.5-pro', 'gemini-2.0-flash'],
      deepseek: ['deepseek-chat', 'deepseek-reasoner'],
      ark: ['doubao-seed-1-6'],
      openrouter: ['anthropic/claude-opus-4-7'],
      qiniu: ['deepseek-r1', 'deepseek-v3'],
      wavespeed: ['openai/gpt-5', 'anthropic/claude-opus-4'],
    }
    await fulfillJson(route, { notable_models: notable[providerKey] ?? ['manual/model'] })
  })
  await page.route('**/api/llm/endpoints/*/models/test', async (route) => {
    const endpointId = decodeURIComponent(new URL(route.request().url()).pathname.split('/').at(-3) ?? '')
    const body = JSON.parse(route.request().postData() ?? '{}') as { model_ids: string[] }
    const provider = providers.find((item) => item.id === endpointId)
    const unique = Array.from(new Set(body.model_ids.filter(Boolean)))
    const existingModels = provider?.available_models ?? []
    const results = unique.map((modelId) => {
      const knownModel = existingModels.some((model) => model.id === modelId)
      const ok = provider?.id !== 'openrouter-custom' || knownModel
      return {
        model_id: modelId,
        status: ok ? 'ok' : 'invalid_model',
        latency_ms: ok ? 12 : null,
        message: ok ? null : 'Model not found',
      }
    })
    const byId = new Map(existingModels.map((model) => [model.id, model]))
    for (const result of results) {
      if (result.status === 'ok' && !byId.has(result.model_id)) {
        byId.set(result.model_id, { id: result.model_id, capabilities: { max_context_tokens: 200000 } })
      }
    }
    const available_models = [...byId.values()]
    providers = providers.map((item) => item.id === endpointId ? {
      ...item,
      last_test_status: results.some((result) => result.status === 'ok') ? 'ok' : 'error',
      last_test_at: '2026-05-25T00:00:00Z',
      last_test_message: results.some((result) => result.status === 'ok') ? 'Credential present.' : 'Model not found.',
      last_error_code: results.some((result) => result.status === 'ok') ? '' : 'invalid_model',
      available_models,
      available_sdks: [item.provider_type],
    } : item)
    await fulfillJson(route, { results, registry: registryFromProviders(providers) })
  })
  await page.route('**/api/llm/providers/test', async (route) => {
    const body = JSON.parse(route.request().postData() ?? '{}') as { id: string; provider_type?: CredentialProvider['provider_type'] }
    const provider = providers.find((item) => item.id === body.id)
    const available_models = provider?.available_models ?? []
    await fulfillJson(route, {
      status: 'ok',
      latency_ms: 150,
      model_seen: available_models[0]?.id ?? null,
      message: null,
      error_code: null,
      available_sdks: [body.provider_type ?? provider?.provider_type ?? 'openai_compatible'],
      available_models,
    })
  })
  await page.route('**/api/llm/roles**', async (route) => {
    await fulfillJson(route, { models: {}, providers: {}, roles: {}, single_model_roles: [], peer_model_groups: {}, circuit_breaker: null })
  })
}

async function mockWebSocket(page: Page) {
  await page.addInitScript(() => {
    class MockWebSocket extends EventTarget {
      static readonly CONNECTING = 0
      static readonly OPEN = 1
      static readonly CLOSING = 2
      static readonly CLOSED = 3
      readonly url: string
      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      constructor(url: string) {
        super()
        this.url = url
        window.setTimeout(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event('open'))
        }, 0)
      }
      send() {
        window.setTimeout(() => {
          this.onmessage?.(new MessageEvent('message', { data: JSON.stringify({ type: 'done' }) }))
        }, 0)
      }
      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new CloseEvent('close'))
      }
    }
    Object.defineProperty(MockWebSocket, 'OPEN', { value: 1 })
    window.WebSocket = MockWebSocket as unknown as typeof WebSocket
  })
}

async function openApiKeys(page: Page) {
  await mockBackend(page)
  await mockWebSocket(page)
  await page.goto(`${baseURL}/#/skill/${SKILL_ID}/edit`)
  await page.getByRole('button', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'API Keys', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'API Keys' })).toBeVisible()
}

test.describe('Round 3 API Keys e2e', () => {
  test('renders Official and Third-party sections with round 3 provider cards', async ({ page }) => {
    await openApiKeys(page)

    const apiKeys = page.getByTestId('api-keys-list')
    await expect(apiKeys.getByRole('heading', { name: 'Official Providers' })).toBeVisible()
    await expect(apiKeys.getByText('Anthropic Official')).toBeVisible()
    await expect(apiKeys.getByText('OpenAI Official')).toBeVisible()
    await expect(apiKeys.getByText('Gemini Official')).toBeVisible()
    await expect(apiKeys.getByText('DeepSeek Official')).toBeVisible()
    await expect(apiKeys.getByText('Ark Official')).toBeVisible()
    await expect(apiKeys.getByRole('heading', { name: 'Third-party Providers' })).toBeVisible()
    await expect(apiKeys.locator('input[aria-label="Provider Name"][value="OpenRouter Custom"]')).toBeVisible()
    await expect(apiKeys.locator('[data-provider-id="openrouter-custom"]').getByText('Connected')).toBeVisible()
    await expect(apiKeys.getByText('deepseek-chat')).toBeVisible()
    await expect(apiKeys.getByText('gpt-5')).toBeVisible()
    await expect(apiKeys.getByText('Protocol')).toBeVisible()
    await expect(apiKeys.getByText('OpenAI compatible')).toBeVisible()
  })

  test('adds a third-party provider as a normal auto-saved card', async ({ page }) => {
    await openApiKeys(page)

    const saveRequest = page.waitForRequest((request) => request.url().includes('/api/llm/registry/endpoints') && request.method() === 'PUT')
    await page.getByRole('button', { name: 'Add Provider' }).click()
    await saveRequest

    await expect(page.getByTestId('add-provider-form')).toHaveCount(0)
    const newCard = page.locator('[data-provider-id^="custom-"]').last()
    await expect(newCard).toBeVisible()
    await expect(newCard.locator('input[aria-label="Provider Name"][value="New Provider"]')).toBeVisible()
    await expect(newCard.getByLabel('Protocol')).toHaveText('OpenAI compatible')

    await newCard.getByLabel('Provider Name').fill('Together Custom')
    await newCard.getByLabel('Protocol').click()
    await page.getByRole('option', { name: 'Anthropic compatible' }).click()
    await newCard.getByRole('textbox', { name: 'Base URL' }).fill('https://api.together.xyz/v1')
    await newCard.locator('input[name^="provider-secret-"]').fill('sk-together')
    await newCard.getByRole('textbox', { name: 'Endpoint test' }).fill('claude-opus-4-7')
    const endpointSaveRequest = page.waitForRequest((request) => request.url().includes('/api/llm/registry/endpoints') && request.method() === 'PUT')
    const testRequest = page.waitForRequest((request) => request.url().includes('/api/llm/endpoints/') && request.url().endsWith('/models/test') && request.method() === 'POST')
    await newCard.getByRole('button', { name: 'Test' }).click()
    const request = await endpointSaveRequest
    const body = JSON.parse(request.postData() ?? '{}') as { provider_endpoints: Record<string, { protocol: string }> }
    const savedEndpoint = Object.values(body.provider_endpoints).find((endpoint) => endpoint.protocol === 'anthropic_compatible')
    expect(savedEndpoint?.protocol).toBe('anthropic_compatible')
    await testRequest
    await expect(newCard.getByText('Connected')).toBeVisible()
    await expect(newCard.getByText('Available SDKs:')).toHaveCount(0)
    await expect(page.locator('input[aria-label="Provider Name"][value="Together Custom"]')).toBeVisible()
  })

  test('clears stale test outcome when provider test parameters change', async ({ page }) => {
    await openApiKeys(page)

    const providerCard = page.locator('[data-provider-id="openrouter-custom"]')
    await expect(providerCard.getByText('Connected')).toBeVisible()
    await expect(providerCard.getByText('Available Models:')).toBeVisible()

    const saveRequest = page.waitForRequest((request) => request.url().includes('/api/llm/registry/endpoints') && request.method() === 'PUT')
    await providerCard.getByRole('textbox', { name: 'Base URL' }).fill('https://openrouter.ai/api/v2')
    await expect(providerCard.getByText('Connected')).toHaveCount(0)
    await expect(providerCard.getByText('Available SDKs:')).toHaveCount(0)
    await saveRequest

    await expect(providerCard.getByText('Connected')).toHaveCount(0)
    await expect(providerCard.getByText('Available SDKs:')).toHaveCount(0)

    const restoreRequest = page.waitForRequest((request) => request.url().includes('/api/llm/registry/endpoints') && request.method() === 'PUT')
    await providerCard.getByRole('textbox', { name: 'Base URL' }).fill('https://openrouter.ai/api/v1')
    await restoreRequest

    await expect(providerCard.getByText('Connected')).toBeVisible()
    await expect(providerCard.getByText('Available Models:')).toBeVisible()
  })

  test('manual model probing checks candidates against registered v4 routes', async ({ page }) => {
    await openApiKeys(page)

    const openRouterCard = page.locator('[data-provider-id="openrouter-custom"]')
    await expect(openRouterCard.getByText('Manual model probing')).toBeVisible()
    await expect(openRouterCard.getByText('gpt-5')).toBeVisible()
    await openRouterCard.getByRole('button', { name: /Manual model probing/i }).click()
    await expect(openRouterCard.getByLabel('Manual model 1')).toBeVisible()
    await openRouterCard.getByRole('button', { name: /Manual model probing/i }).click()
    await expect(openRouterCard.getByLabel('Manual model 1')).toBeHidden()
    await openRouterCard.getByRole('button', { name: /Manual model probing/i }).click()

    await openRouterCard.getByLabel('Manual model 1').fill('claude-opus-4-7')
    await openRouterCard.getByRole('button', { name: 'Add Model', exact: true }).click()
    await openRouterCard.getByLabel('Manual model 2').fill('gpt-5')
    await openRouterCard.getByRole('button', { name: 'Test Models' }).click()

    await expect(openRouterCard.getByText('claude-opus-4-7: Model not found')).toBeVisible()
    await expect(openRouterCard.getByText('gpt-5: Available')).toBeVisible()
    await expect(openRouterCard.getByText('gpt-5')).toHaveCount(2)
  })
})
