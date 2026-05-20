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
  await page.route('**/api/llm/credentials**', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = JSON.parse(route.request().postData() ?? '{}') as { providers?: CredentialProvider[] }
      providers = (body.providers ?? []).map((provider) => {
        const existing = providers.find((item) => item.id === provider.id)
        return {
          ...existing,
          ...provider,
          api_key: provider.api_key || existing?.api_key || '',
          last_test_status: existing?.last_test_status ?? 'untested',
          last_test_at: existing?.last_test_at ?? '',
          last_test_message: existing?.last_test_message ?? '',
          last_error_code: existing?.last_error_code ?? '',
          available_models: existing?.available_models ?? [],
          available_sdks: existing?.available_sdks ?? [],
        }
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
    }
    await fulfillJson(route, { notable_models: notable[providerKey] ?? ['manual/model'] })
  })
  await page.route('**/api/llm/providers/test-models', async (route) => {
    const body = JSON.parse(route.request().postData() ?? '{}') as { provider_id: string; model_ids: string[] }
    const provider = providers.find((item) => item.id === body.provider_id)
    const unique = Array.from(new Set(body.model_ids.filter(Boolean)))
    const results = unique.map((modelId) => ({ model_id: modelId, status: 'ok', latency_ms: 12, message: null }))
    const existingModels = provider?.available_models ?? []
    const byId = new Map(existingModels.map((model) => [model.id, model]))
    for (const modelId of unique) {
      if (!byId.has(modelId)) byId.set(modelId, { id: modelId, capabilities: { max_context_tokens: 200000 } })
    }
    const available_models = [...byId.values()]
    providers = providers.map((item) => item.id === body.provider_id ? { ...item, available_models } : item)
    await fulfillJson(route, { results, available_models })
  })
  await page.route('**/api/llm/providers/test', async (route) => {
    const body = JSON.parse(route.request().postData() ?? '{}') as { id: string }
    const provider = providers.find((item) => item.id === body.id)
    const available_models = provider?.available_models ?? []
    await fulfillJson(route, {
      status: 'ok',
      latency_ms: 150,
      model_seen: available_models[0]?.id ?? null,
      message: null,
      error_code: null,
      available_sdks: ['openai_compatible'],
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
  await page.getByRole('button', { name: 'API Keys' }).click()
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
    await expect(apiKeys.getByText('Not configured').first()).toBeVisible()
    await expect(apiKeys.getByText('deepseek-chat')).toBeVisible()
    await expect(apiKeys.getByText('gpt-5')).toBeVisible()
    await expect(apiKeys.getByText('SDK Protocol')).toHaveCount(0)
    await expect(apiKeys.getByText('OpenAI Compatible')).toHaveCount(0)
  })

  test('uses simplified Add Provider form with cancel and submit collapse', async ({ page }) => {
    await openApiKeys(page)

    await page.getByRole('button', { name: 'Add Provider' }).click()
    const form = page.getByTestId('add-provider-form')
    await expect(form).toBeVisible()
    await expect(form.getByLabel('Provider Name')).toBeVisible()
    await expect(form.getByLabel('Base URL')).toBeVisible()
    await expect(form.locator('input[aria-label="API Key"]')).toBeVisible()
    await expect(form.getByText('Official Provider')).toHaveCount(0)

    await form.getByRole('button', { name: 'Cancel' }).click()
    await expect(form).toHaveCount(0)

    await page.getByRole('button', { name: 'Add Provider' }).click()
    const reopened = page.getByTestId('add-provider-form')
    await reopened.getByLabel('Provider Name').fill('Together Custom')
    await reopened.getByLabel('Base URL').fill('https://api.together.xyz/v1')
    await reopened.locator('input[aria-label="API Key"]').fill('sk-together')
    const saveRequest = page.waitForRequest((request) => request.url().includes('/api/llm/credentials') && request.method() === 'PUT')
    await reopened.getByRole('button', { name: 'Add' }).click()
    await saveRequest
    await expect(page.getByTestId('add-provider-form')).toHaveCount(0)
    await expect(page.locator('input[aria-label="Provider Name"][value="Together Custom"]')).toBeVisible()
  })

  test('manual model probing appends deduped chips using mocked backend', async ({ page }) => {
    await openApiKeys(page)

    const openRouterCard = page.locator('[data-provider-id="openrouter-custom"]')
    await expect(openRouterCard.getByText('Manual model probing')).toBeVisible()
    await expect(openRouterCard.getByText('gpt-5')).toBeVisible()

    await openRouterCard.getByLabel('Manual model 1').fill('claude-opus-4-7')
    await openRouterCard.getByRole('button', { name: 'Add Model' }).click()
    await openRouterCard.getByLabel('Manual model 2').fill('gpt-5')
    const modelRequest = page.waitForRequest((request) => request.url().includes('/api/llm/providers/test-models') && request.method() === 'POST')
    await openRouterCard.getByRole('button', { name: 'Test Models' }).click()
    await modelRequest

    await expect(openRouterCard.getByText('claude-opus-4-7').first()).toBeVisible()
    await expect(openRouterCard.getByText('claude-opus-4-7: ok')).toBeVisible()
    await expect(openRouterCard.getByText('gpt-5')).toHaveCount(2)
  })
})
