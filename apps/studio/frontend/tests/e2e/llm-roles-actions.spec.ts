import { expect, test, type Page, type Route } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

const credentials = {
  providers: [
    {
      id: 'anthropic',
      name: 'Anthropic Official',
      api_key: 'sk-anthropic',
      base_url: 'https://api.anthropic.com',
      provider_type: 'anthropic_compatible',
      last_test_status: 'ok',
      last_test_at: '2026-05-24T00:00:00Z',
      last_test_message: '',
      last_error_code: '',
      available_sdks: ['anthropic_compatible'],
      available_models: [
        { id: 'claude-opus-4-7', capabilities: { thinking: true } },
      ],
    },
  ],
}

const registry = {
  provider_endpoints: {
    anthropic: {
      endpoint_id: 'anthropic',
      display_name: 'Anthropic Official',
      protocol: 'anthropic_compatible',
      base_url: 'https://api.anthropic.com',
      api_key: 'sk-anthropic',
      status: 'verified',
      last_test_at: '2026-05-24T00:00:00Z',
      last_test_message: '',
      timeout_seconds: 120,
      trust_env: false,
      proxy_env: null,
      metadata: {},
    },
  },
  provider_routes: {
    'anthropic:claude-opus-4-7': {
      route_id: 'anthropic:claude-opus-4-7',
      endpoint_id: 'anthropic',
      route_slug: 'claude-opus-4-7',
      provider_model_id: 'claude-opus-4-7',
      canonical_id: 'claude-opus-4-7',
      display_name: 'claude-opus-4-7',
      status: 'verified',
      capabilities: { thinking: { value: true, source: 'probed_verified' } },
      metadata: {},
    },
  },
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
}

const roles = {
  models: {
    'claude-opus-4-7': {
      name: 'claude-opus-4-7',
      providers: { anthropic: 'claude-opus-4-7' },
    },
  },
  providers: {
    anthropic: { name: 'Anthropic Official', type: 'anthropic_compatible' },
  },
  roles: {
    Premium: {
      model_fallback: true,
      active_model: 'claude-opus-4-7',
      models: {
        'claude-opus-4-7': {
          providers: ['anthropic'],
          temperature: null,
          max_tokens: null,
        },
      },
    },
  },
  single_model_roles: [],
  peer_model_groups: {},
  circuit_breaker: null,
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function mockSettingsBackend(page: Page) {
  await page.route('**/api/skills', async (route) => {
    await fulfillJson(route, [])
  })
  await page.route('**/api/settings', async (route) => {
    await fulfillJson(route, {
      user_id: 'e2e-user',
      gitea_host: 'https://gitea.example',
      default_skills_directory: '/tmp/skills',
    })
  })
  await page.route('**/api/llm/credentials**', async (route) => {
    await fulfillJson(route, credentials)
  })
  await page.route('**/api/llm/registry', async (route) => {
    await fulfillJson(route, registry)
  })
  await page.route('**/api/llm/roles**', async (route) => {
    await fulfillJson(route, roles)
  })
}

async function openLlmRoles(page: Page) {
  await mockSettingsBackend(page)
  await page.goto(`${baseURL}/#/`)
  await page.getByRole('button', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'LLM Roles', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'LLM Roles' })).toBeVisible()
}

test.describe('LLM Roles actions menu', () => {
  test('keeps role actions double-clicks from flashing the edit menu layer', async ({ page }) => {
    await openLlmRoles(page)

    const roleCard = page.locator('[data-role-name="Premium"]')
    const trigger = roleCard.locator('[data-role-actions-trigger="true"]')
    const editItem = page.locator('[data-role-edit-trigger="true"]')

    await expect(trigger).toBeVisible()

    await trigger.click()
    await expect(editItem).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(editItem).toHaveCount(0)

    await trigger.dblclick()
    await page.waitForTimeout(260)
    await expect(editItem).toHaveCount(0)
    await expect(trigger).toHaveAttribute('data-state', 'closed')
    await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).pointerEvents)).toBe('auto')

    await roleCard.getByText('Premium', { exact: true }).selectText()
    await expect.poll(() => page.evaluate(() => window.getSelection()?.toString() ?? '')).toBe('')
    await trigger.dblclick()
    await page.waitForTimeout(260)
    await expect(editItem).toHaveCount(0)
    await expect(trigger).toHaveAttribute('data-state', 'closed')
    await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).pointerEvents)).toBe('auto')

    await trigger.focus()
    await page.keyboard.press('Enter')
    await expect(editItem).toBeVisible()
  })
})
