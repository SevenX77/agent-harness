import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

const SKILL_ID = 'smoke'

const skillDetail = {
  manifest: {
    schema_version: '2.0',
    type: 'graph',
    name: 'Smoke Skill',
    description: 'LLM config v2 smoke skill',
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
  description: 'LLM config v2 smoke skill',
  phase_count: 0,
  has_golden: false,
  last_run_at: null,
  directory_path: '/tmp/smoke',
  config_mismatch: null,
}

const roleData = {
  models: {
    CL46T: { name: 'Claude Sonnet 4.6 Thinking', providers: { OC_CL_ANT: 'claude-sonnet-test' } },
    DS32R: { name: 'DeepSeek R1', providers: { DS: 'deepseek-reasoner' } },
  },
  providers: {
    OC_CL_ANT: { name: 'OpenCode Anthropic', type: 'anthropic_compatible', base_url: 'https://anthropic.example' },
    OC_CL: { name: 'OpenCode Claude', type: 'anthropic_compatible', base_url: 'https://claude.example' },
    WS_LLM: { name: 'WaveSpeed LLM', type: 'wavespeed_any_llm', base_url: 'https://wavespeed.example' },
    DS: { name: 'DeepSeek Official', type: 'openai_compatible', base_url: 'https://deepseek.example' },
  },
  roles: {
    copilot_chat: {
      temperature: 0.2,
      model_fallback: true,
      active_model: 'CL46T',
      models: {
        CL46T: { providers: ['OC_CL_ANT', 'OC_CL', 'WS_LLM'] },
        DS32R: { providers: ['DS'] },
      },
      system_prompt_prefix: null,
    },
    balanced: {
      temperature: 0.3,
      model_fallback: true,
      active_model: 'CL46T',
      models: { CL46T: { providers: ['OC_CL_ANT'] } },
      system_prompt_prefix: null,
    },
  },
  single_model_roles: [],
  peer_model_groups: {},
  circuit_breaker: null,
}

function credentials(ocClAntHasKey: boolean) {
  return {
    providers: [
      {
        provider_code: 'OC_CL_ANT',
        has_key: ocClAntHasKey,
        name: 'OpenCode Anthropic',
        base_url: 'https://anthropic.example',
        provider_type: 'anthropic_compatible',
      },
      {
        provider_code: 'OC_CL',
        has_key: false,
        name: 'OpenCode Claude',
        base_url: 'https://claude.example',
        provider_type: 'anthropic_compatible',
      },
      {
        provider_code: 'WS_LLM',
        has_key: false,
        name: 'WaveSpeed LLM',
        base_url: 'https://wavespeed.example',
        provider_type: 'wavespeed_any_llm',
      },
      {
        provider_code: 'DS',
        has_key: false,
        name: 'DeepSeek Official',
        base_url: 'https://deepseek.example',
        provider_type: 'openai_compatible',
      },
    ],
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
  let hasOcClAntKey = false

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
      const body = JSON.parse(route.request().postData() ?? '{}') as { providers?: Array<{ provider_code: string }> }
      hasOcClAntKey = Boolean(body.providers?.some((provider) => provider.provider_code === 'OC_CL_ANT'))
      await fulfillJson(route, credentials(hasOcClAntKey))
      return
    }
    await fulfillJson(route, credentials(hasOcClAntKey))
  })
  await page.route('**/api/llm/providers/test', async (route) => {
    await fulfillJson(route, {
      status: 'ok',
      latency_ms: 150,
      model_seen: 'claude-sonnet-4-6',
      message: null,
    })
  })
  await page.route('**/api/llm/roles**', async (route) => {
    if (route.request().url().includes('/api/llm/roles/copilot_chat')) {
      await fulfillJson(route, roleData.roles.copilot_chat)
      return
    }
    if (route.request().method() === 'PUT') {
      const next = JSON.parse(route.request().postData() ?? '{}')
      Object.assign(roleData, next)
      await fulfillJson(route, roleData)
      return
    }
    await fulfillJson(route, roleData)
  })
}

async function mockWebSocket(page: Page) {
  await page.addInitScript(() => {
    Object.assign(window, { __llmConfigV2WsMessages: [] })

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

      send(data: string) {
        ;(window as unknown as { __llmConfigV2WsMessages: string[] }).__llmConfigV2WsMessages.push(data)
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

test.describe('LLM config v2 e2e', () => {
  test('saves provider key, tests provider, edits copilot_chat, and sends model_override', async ({ page }) => {
    await mockBackend(page)
    await mockWebSocket(page)

    await page.goto(`${baseURL}/#/skill/${SKILL_ID}/edit`)
    await page.getByRole('button', { name: 'Settings' }).click()
    await page.getByRole('button', { name: 'API Keys' }).click()

    const credentialsRequest = page.waitForRequest((request) =>
      request.url().includes('/api/llm/credentials') && request.method() === 'PUT',
    )
    await page.getByRole('textbox', { name: 'OC_CL_ANT API key' }).fill('sk-test-anthropic-123')
    await credentialsRequest
    await expect(page.getByText('API key configured').first()).toBeVisible()

    await page.getByRole('button', { name: 'Test OC_CL_ANT' }).click()
    await expect(page.getByText('Connected (150ms)')).toBeVisible({ timeout: 3000 })

    await page.getByRole('button', { name: 'LLM Roles' }).click()
    await page.locator('select[aria-label="Role"]').selectOption('copilot_chat')
    await page.getByRole('button', { name: 'Move OC_CL_ANT down' }).click()
    const saveRequest = page.waitForRequest((request) =>
      request.url().includes('/api/llm/roles') && request.method() === 'PUT',
    )
    await page.getByRole('button', { name: 'Save' }).click()
    await saveRequest
    await expect(page.getByText('Roles saved')).toBeVisible({ timeout: 3000 })

    await page.getByRole('button', { name: 'Close settings' }).click()
    await page.getByRole('button', { name: /Smoke Skill/ }).first().click()
    await expect(page.getByRole('heading', { name: 'Copilot' })).toBeVisible()
    await page.getByRole('button', { name: 'Select Copilot model' }).click()
    await expect(page.getByRole('button', { name: 'Select model CL46T' })).toBeEnabled()

    await page.getByPlaceholder("Use '@' to mention nodes...").fill('hello copilot')
    await page.getByRole('button', { name: 'Send message' }).click()

    await expect
      .poll(async () => page.evaluate(() => (window as unknown as { __llmConfigV2WsMessages: string[] }).__llmConfigV2WsMessages.length))
      .toBe(1)
    const messages = await page.evaluate(() => (window as unknown as { __llmConfigV2WsMessages: string[] }).__llmConfigV2WsMessages)
    expect(JSON.parse(messages[0])).toMatchObject({
      user_message: 'hello copilot',
      model_override: 'CL46T',
    })
  })
})
