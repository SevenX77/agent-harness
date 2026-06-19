import { expect, test, type Page, type Route } from '@playwright/test'

// #46/#47 (settings-ux-spec §2.4 / §6.5 check 2): the live role-test state is a
// pure projection of the backend SSOT (active job + persisted results). This e2e
// drives a job-based role test, switches away mid-test and back (remounting the
// tab), and asserts the state is restored from the backend — never blanked — and
// that no RoleTestResultPanel surface is rendered.

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

const routeId = 'anthropic:claude-opus-4-7'

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
      available_models: [{ id: 'claude-opus-4-7', capabilities: { thinking: true } }],
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
    [routeId]: {
      route_id: routeId,
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
  runtime_policy: { provider_down_ttl_seconds: 60, probe_timeout_seconds: 5, token_escalation_rounds: 2 },
  model_profiles: {},
  model_groups: [{
    canonical_id: 'claude-opus-4-7',
    display_name: 'Claude Opus 4.7',
    section_label: 'anthropic',
    provider_models: [{
      route_id: routeId,
      endpoint_id: 'anthropic',
      provider_label: 'Anthropic Official',
      provider_kind: 'official',
      provider_model_id: 'claude-opus-4-7',
      ui_state: 'ready',
      ui_detail: null,
      retry_at: null,
      reason_code: null,
      capability_state: 'known',
      capabilities: {},
    }],
    status_summary: { ready: 1, untested: 0, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
    capability_summary: {
      capability_known_count: 1,
      thinking: 'supported',
      tools: 'unknown',
      structured_output: 'unknown',
      max_context_tokens: null,
      max_output_tokens: null,
    },
  }],
  roles: {},
  canonical_groups: [],
  lint_results: [],
  setup_required: false,
}

const roles = {
  models: {
    'claude-opus-4-7': { name: 'claude-opus-4-7', providers: { [routeId]: 'claude-opus-4-7' } },
  },
  providers: {
    [routeId]: { name: 'Anthropic Official', type: 'anthropic_compatible', endpoint_id: 'anthropic' },
  },
  roles: {
    Premium: {
      model_fallback_enabled: true,
      active_model: 'claude-opus-4-7',
      models: {
        'claude-opus-4-7': { providers: [routeId], temperature: null, max_tokens: null },
      },
    },
  },
  single_model_roles: [],
  peer_model_groups: {},
  circuit_breaker: null,
}

const completedResult = {
  role_name: 'Premium',
  status: 'ok',
  warnings: [],
  model_groups: [{
    canonical_id: 'claude-opus-4-7',
    display_name: 'Claude Opus 4.7',
    provider_results: [{
      route_id: routeId,
      provider_label: 'Anthropic Official',
      provider_ui_state: 'ready',
      role_fit: 'using',
      admission_decision: 'admit',
      status: 'ok',
      warnings: [],
      retry_at: null,
      message: null,
      resolved_settings: {},
    }],
  }],
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
}

async function mockBackend(page: Page) {
  // Gate the job's terminal transition: the job stays "running" until the test
  // releases it, so we can reliably switch tabs while it is mid-flight.
  let pollCount = 0
  let releaseDone = false

  await page.route('**/api/skills', (route) => fulfillJson(route, []))
  await page.route('**/api/settings', (route) => fulfillJson(route, {
    user_id: 'e2e-user',
    gitea_host: 'https://gitea.example',
    default_skills_directory: '/tmp/skills',
  }))
  await page.route('**/api/llm/credentials**', (route) => fulfillJson(route, credentials))
  await page.route('**/api/llm/registry', (route) => fulfillJson(route, registry))

  // Register the broad roles catch-all FIRST so the more specific job/result
  // routes below take priority (Playwright matches last-registered routes first).
  await page.route('**/api/llm/roles**', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    if (request.method() === 'PUT' && pathname === '/api/llm/roles') {
      await fulfillJson(route, request.postDataJSON())
      return
    }
    await fulfillJson(route, roles)
  })

  await page.route('**/api/llm/roles/test-results', (route) => fulfillJson(route, { results: {} }))

  await page.route('**/api/llm/roles/*/test-jobs', async (route) => {
    await fulfillJson(route, {
      job_id: 'job-premium-1',
      role_name: 'Premium',
      status: 'running',
      provider_statuses: [
        { canonical_id: 'claude-opus-4-7', route_id: routeId, status: 'testing', message: null },
      ],
      result: null,
    })
  })

  await page.route('**/api/llm/role-test-jobs/*', async (route) => {
    pollCount += 1
    if (!releaseDone) {
      await fulfillJson(route, {
        job_id: 'job-premium-1',
        role_name: 'Premium',
        status: 'running',
        provider_statuses: [
          { canonical_id: 'claude-opus-4-7', route_id: routeId, status: 'testing', message: null },
        ],
        result: null,
      })
      return
    }
    await fulfillJson(route, {
      job_id: 'job-premium-1',
      role_name: 'Premium',
      status: 'completed',
      provider_statuses: [
        { canonical_id: 'claude-opus-4-7', route_id: routeId, status: 'ok', message: null },
      ],
      result: completedResult,
    })
  })

  return {
    pollCount: () => pollCount,
    release: () => {
      releaseDone = true
    },
  }
}

async function openLlmRoles(page: Page) {
  await page.goto(`${baseURL}/#/`)
  await page.getByRole('button', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'LLM Roles', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'LLM Roles' })).toBeVisible()
}

test.describe('LLM Roles test SSOT (#46)', () => {
  test('restores an in-flight role test from the backend after a tab switch and shows no result panel', async ({ page }) => {
    const control = await mockBackend(page)
    await openLlmRoles(page)

    const roleCard = page.locator('[data-role-name="Premium"]')
    await expect(roleCard).toBeVisible()

    // Start the test; the job stays running (gated) so the card shows live progress.
    await roleCard.getByRole('button', { name: 'Test' }).click()
    const testingLight = roleCard.locator('[data-role-route-status-light="true"][data-role-route-status="testing"]')
    await expect(testingLight).toBeVisible()
    await expect.poll(control.pollCount).toBeGreaterThan(0)

    // Switch away to API Keys, then back to LLM Roles: this unmounts + remounts the
    // tab. A component-local useState would lose the running progress; the module
    // store keeps polling the backend job, so the testing light must reappear.
    await page.getByRole('button', { name: 'API Keys', exact: true }).click()
    await expect(page.locator('[data-role-name="Premium"]')).toHaveCount(0)
    await page.getByRole('button', { name: 'LLM Roles', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'LLM Roles' })).toBeVisible()

    const roleCardAfter = page.locator('[data-role-name="Premium"]')
    await expect(
      roleCardAfter.locator('[data-role-route-status-light="true"][data-role-route-status="testing"]'),
    ).toBeVisible()

    // Release the job → it completes; the card settles to a Can Run light, projected
    // entirely from the backend job result (no blank reset).
    control.release()
    await expect(
      roleCardAfter.locator('[data-role-route-status-light="true"][data-role-route-status="runnable"]'),
    ).toBeVisible()

    // spec §2.4: no RoleTestResultPanel surface anywhere.
    await expect(page.locator('[data-role-test-result="true"]')).toHaveCount(0)
  })
})
