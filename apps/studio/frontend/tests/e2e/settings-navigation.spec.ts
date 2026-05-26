import { expect, test, type Page, type Route } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function mockWelcomeAndSettingsBackend(page: Page) {
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
    await fulfillJson(route, { providers: [] })
  })
  await page.route('**/api/llm/registry', async (route) => {
    await fulfillJson(route, {
      provider_endpoints: {},
      provider_routes: {},
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
    })
  })
  await page.route('**/api/llm/roles**', async (route) => {
    await fulfillJson(route, {
      models: {},
      providers: {},
      roles: {},
      single_model_roles: [],
      peer_model_groups: {},
      circuit_breaker: null,
    })
  })
}

test.describe('Settings navigation', () => {
  test('returns from Settings to the welcome page when the logo is clicked', async ({ page }) => {
    await mockWelcomeAndSettingsBackend(page)
    await page.goto(`${baseURL}/#/`)

    await expect(page.getByRole('heading', { name: 'GSkill Studio' })).toBeVisible()
    await page.getByRole('button', { name: 'Settings' }).click()
    await expect(page.getByRole('button', { name: 'General' })).toBeVisible()

    await page.getByRole('button', { name: 'Back to Home' }).click()

    await expect(page.getByRole('heading', { name: 'GSkill Studio' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'General' })).toBeHidden()
  })
})
