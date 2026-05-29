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

async function mockSettingsBackend(
  page: Page,
  overrides: {
    registry?: typeof registry
    roles?: typeof roles
    roleTest?: unknown
    onRolesPut?: (payload: unknown) => void
    onRoleTest?: (roleName: string) => void
    onRoleDelete?: (roleName: string) => void
  } = {},
) {
  const registryBody = overrides.registry ?? registry
  const rolesBody = overrides.roles ?? roles
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
    await fulfillJson(route, registryBody)
  })
  await page.route('**/api/llm/roles**', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    const testMatch = pathname.match(/\/api\/llm\/roles\/([^/]+)\/test$/)
    if (request.method() === 'POST' && testMatch) {
      const roleName = decodeURIComponent(testMatch[1])
      overrides.onRoleTest?.(roleName)
      await fulfillJson(route, overrides.roleTest ?? {
        role_name: roleName,
        status: 'ok',
        warnings: [],
        model_groups: [],
      })
      return
    }
    if (request.method() === 'PUT' && pathname === '/api/llm/roles') {
      const payload = request.postDataJSON()
      overrides.onRolesPut?.(payload)
      await fulfillJson(route, payload)
      return
    }
    const roleMatch = pathname.match(/\/api\/llm\/roles\/([^/]+)$/)
    if (request.method() === 'DELETE' && roleMatch) {
      const roleName = decodeURIComponent(roleMatch[1])
      overrides.onRoleDelete?.(roleName)
      const nextRoles = {
        ...rolesBody,
        roles: Object.fromEntries(
          Object.entries(rolesBody.roles).filter(([currentRoleName]) => currentRoleName !== roleName),
        ),
      }
      await fulfillJson(route, nextRoles)
      return
    }
    await fulfillJson(route, rolesBody)
  })
}

async function openLlmRoles(
  page: Page,
  overrides: Parameters<typeof mockSettingsBackend>[1] = {},
) {
  await mockSettingsBackend(page, overrides)
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

  test('confirms role deletion and calls the persisted delete endpoint', async ({ page }) => {
    const deletedRoles: string[] = []
    await openLlmRoles(page, {
      onRoleDelete: (roleName) => deletedRoles.push(roleName),
    })

    const roleCard = page.locator('[data-role-name="Premium"]')
    await roleCard.locator('[data-role-actions-trigger="true"]').click()
    await page.getByRole('menuitem', { name: 'Delete' }).click()

    await expect(page.locator('[data-delete-confirm-dialog="true"]')).toHaveCount(0)
    await expect(page.locator('[data-sonner-toast]').getByText('Delete Premium?')).toBeVisible()
    await page.locator('[data-sonner-toast]').getByRole('button', { name: 'Cancel' }).click()
    await expect.poll(() => deletedRoles).toEqual([])
    await expect(roleCard).toBeVisible()

    await roleCard.locator('[data-role-actions-trigger="true"]').click()
    await page.getByRole('menuitem', { name: 'Delete' }).click()
    await page.locator('[data-sonner-toast]').getByRole('button', { name: 'Delete' }).click()

    await expect.poll(() => deletedRoles).toEqual(['Premium'])
    await expect(roleCard).toHaveCount(0)
  })

  test('saves role drafts before running persisted role test and renders provider diagnostics', async ({ page }) => {
    const routeId = 'deepseek-official:deepseek-v4-pro'
    const routeBackedRegistry: typeof registry = {
      ...registry,
      provider_endpoints: {
        'deepseek-official': {
          endpoint_id: 'deepseek-official',
          display_name: 'DeepSeek Official',
          protocol: 'openai_compatible',
          base_url: 'https://api.deepseek.com',
          api_key: 'sk-deepseek',
          status: 'verified',
          last_test_at: '2026-05-24T00:00:00Z',
          last_test_message: 'Connected. Model seen: deepseek-chat.',
          timeout_seconds: 120,
          trust_env: false,
          proxy_env: null,
          metadata: {},
        },
        openrouter: {
          endpoint_id: 'openrouter',
          display_name: 'OpenRouter',
          protocol: 'openai_compatible',
          base_url: 'https://openrouter.ai/api/v1',
          api_key: 'sk-openrouter',
          status: 'verified',
          last_test_at: '2026-05-24T00:00:00Z',
          last_test_message: 'Connected. Model seen: deepseek/deepseek-v4-pro.',
          timeout_seconds: 120,
          trust_env: false,
          proxy_env: null,
          metadata: {},
        },
      },
      provider_routes: {
        [routeId]: {
          route_id: routeId,
          endpoint_id: 'deepseek-official',
          route_slug: 'deepseek-v4-pro',
          provider_model_id: 'deepseek-chat',
          canonical_id: 'deepseek-v4-pro',
          display_name: 'DeepSeek V4 Pro',
          status: 'verified',
          capabilities: {},
          metadata: {},
        },
        'openrouter:deepseek-v4-pro': {
          route_id: 'openrouter:deepseek-v4-pro',
          endpoint_id: 'openrouter',
          route_slug: 'deepseek-v4-pro',
          provider_model_id: 'deepseek/deepseek-v4-pro',
          canonical_id: 'deepseek-v4-pro',
          display_name: 'DeepSeek V4 Pro',
          status: 'verified',
          capabilities: {},
          metadata: {},
        },
      },
    }
    const routeBackedRoles: typeof roles = {
      ...roles,
      models: {
        'deepseek-v4-pro': {
          name: 'DeepSeek V4 Pro',
          providers: {
            [routeId]: 'deepseek-chat',
            'openrouter:deepseek-v4-pro': 'deepseek/deepseek-v4-pro',
          },
        },
      },
      providers: {
        [routeId]: {
          name: 'DeepSeek Official',
          type: 'openai_compatible',
          endpoint_id: 'deepseek-official',
        },
        'openrouter:deepseek-v4-pro': {
          name: 'OpenRouter',
          type: 'openai_compatible',
          endpoint_id: 'openrouter',
        },
      },
      roles: {
        Analyst: {
          model_fallback: true,
          active_model: 'deepseek-v4-pro',
          models: {
            'deepseek-v4-pro': {
              providers: [routeId, 'openrouter:deepseek-v4-pro'],
              temperature: null,
              max_tokens: null,
            },
          },
        },
      },
    }
    const requestOrder: string[] = []
    await openLlmRoles(page, {
      registry: routeBackedRegistry,
      roles: routeBackedRoles,
      onRolesPut: () => requestOrder.push('PUT /api/llm/roles'),
      onRoleTest: (roleName) => requestOrder.push(`POST /api/llm/roles/${roleName}/test`),
      roleTest: {
        role_name: 'Analyst',
        status: 'warning',
        warnings: [{ message: 'Thinking is required but capability is unknown.' }],
        model_groups: [{
          canonical_id: 'deepseek-v4-pro',
          display_name: 'DeepSeek V4 Pro',
          provider_results: [
            {
              route_id: routeId,
              provider_label: 'DeepSeek Official',
              provider_ui_state: 'ready',
              role_fit: 'using',
              admission_decision: 'admit',
              status: 'ok',
              warnings: [],
              retry_at: null,
              message: null,
              resolved_settings: {},
            },
            {
              route_id: 'openrouter:deepseek-v4-pro',
              provider_label: 'OpenRouter',
              provider_ui_state: 'cooling_down',
              role_fit: 'needs_test',
              admission_decision: 'temporary_skip',
              status: 'blocked',
              warnings: [{ message: 'Thinking is required but capability is unknown.' }],
              retry_at: '2026-12-31T00:00:00Z',
              message: 'Retry after transient rate limit.',
              resolved_settings: {},
            },
          ],
        }],
      },
    })

    const roleCard = page.locator('[data-role-name="Analyst"]')
    await expect(roleCard.getByText('DeepSeek V4 Pro')).toBeVisible()
    await expect(roleCard.getByLabel('Provider status Connected')).toHaveCount(0)
    await expect(roleCard.locator('[data-role-route-status-light="true"][data-role-route-status="runnable"]')).toHaveCount(2)

    await roleCard.getByRole('switch', { name: 'Model fallback for Analyst' }).click()
    await roleCard.getByRole('button', { name: 'Test' }).click()

    await expect.poll(() => requestOrder).toEqual([
      'PUT /api/llm/roles',
      'POST /api/llm/roles/Analyst/test',
    ])
    const resultPanel = roleCard.locator('[data-role-test-result="true"]')
    await expect(resultPanel).toBeVisible()
    await expect(resultPanel.getByText('Needs Attention')).toBeVisible()
    await expect(resultPanel.getByText('DeepSeek Official')).toBeVisible()
    await expect(resultPanel.getByText('OpenRouter')).toBeVisible()
    await expect(resultPanel.getByText('Cooling Down')).toBeVisible()
    await expect(resultPanel.getByText('Needs Test')).toBeVisible()
    await expect(resultPanel.getByText('Retry after transient rate limit.')).toBeVisible()
    await expect(roleCard.getByText(routeId)).toHaveCount(0)
    await expect(roleCard.locator('[data-role-route-status-light="true"][data-role-route-status="runnable"]')).toHaveCount(1)
    await expect(roleCard.locator('[data-role-route-status-light="true"][data-role-route-status="blocked"]')).toHaveCount(1)
  })

  test('does not show aggregate model group status when every provider route test fails', async ({ page }) => {
    const routeIds = ['openrouter:gpt-5-4-mini', 'openai-official:gpt-5-4-mini']
    const routeBackedRegistry: typeof registry = {
      ...registry,
      provider_endpoints: {
        openrouter: {
          endpoint_id: 'openrouter',
          display_name: 'OpenRouter',
          protocol: 'openai_compatible',
          base_url: 'https://openrouter.ai/api/v1',
          api_key: 'sk-openrouter',
          status: 'verified',
          last_test_at: '2026-05-24T00:00:00Z',
          last_test_message: 'Connected.',
          timeout_seconds: 120,
          trust_env: false,
          proxy_env: null,
          metadata: {},
        },
        'openai-official': {
          endpoint_id: 'openai-official',
          display_name: 'OpenAI Official',
          protocol: 'openai_compatible',
          base_url: 'https://api.openai.com/v1',
          api_key: 'sk-openai',
          status: 'verified',
          last_test_at: '2026-05-24T00:00:00Z',
          last_test_message: 'Connected.',
          timeout_seconds: 120,
          trust_env: false,
          proxy_env: null,
          metadata: {},
        },
      },
      provider_routes: {
        [routeIds[0]]: {
          route_id: routeIds[0],
          endpoint_id: 'openrouter',
          route_slug: 'gpt-5-4-mini',
          provider_model_id: 'openai/gpt-5.4-mini',
          canonical_id: 'gpt-5-4-mini',
          display_name: 'GPT 5.4 Mini',
          status: 'verified',
          capabilities: {},
          metadata: {},
        },
        [routeIds[1]]: {
          route_id: routeIds[1],
          endpoint_id: 'openai-official',
          route_slug: 'gpt-5-4-mini',
          provider_model_id: 'gpt-5.4-mini',
          canonical_id: 'gpt-5-4-mini',
          display_name: 'GPT 5.4 Mini',
          status: 'verified',
          capabilities: {},
          metadata: {},
        },
      },
      model_groups: [{
        canonical_id: 'gpt-5-4-mini',
        display_name: 'GPT 5.4 Mini',
        section_label: 'openai',
        provider_models: [
          {
            route_id: routeIds[0],
            endpoint_id: 'openrouter',
            provider_label: 'OpenRouter',
            provider_kind: 'third_party',
            provider_model_id: 'openai/gpt-5.4-mini',
            ui_state: 'ready',
            ui_detail: null,
            retry_at: null,
            reason_code: null,
            capability_state: 'unknown',
            capabilities: {},
          },
          {
            route_id: routeIds[1],
            endpoint_id: 'openai-official',
            provider_label: 'OpenAI Official',
            provider_kind: 'official',
            provider_model_id: 'gpt-5.4-mini',
            ui_state: 'ready',
            ui_detail: null,
            retry_at: null,
            reason_code: null,
            capability_state: 'unknown',
            capabilities: {},
          },
        ],
        status_summary: {
          ready: 2,
          untested: 0,
          cooling_down: 0,
          needs_setup: 0,
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
      }],
    }
    const routeBackedRoles: typeof roles = {
      ...roles,
      models: {
        'gpt-5-4-mini': {
          name: 'GPT 5.4 Mini',
          providers: {
            [routeIds[0]]: 'openai/gpt-5.4-mini',
            [routeIds[1]]: 'gpt-5.4-mini',
          },
        },
      },
      providers: {
        [routeIds[0]]: {
          name: 'OpenRouter',
          type: 'openai_compatible',
          endpoint_id: 'openrouter',
        },
        [routeIds[1]]: {
          name: 'OpenAI Official',
          type: 'openai_compatible',
          endpoint_id: 'openai-official',
        },
      },
      roles: {
        Analyst: {
          model_fallback: true,
          active_model: 'gpt-5-4-mini',
          models: {
            'gpt-5-4-mini': {
              providers: routeIds,
              temperature: null,
              max_tokens: null,
            },
          },
        },
      },
    }

    await openLlmRoles(page, {
      registry: routeBackedRegistry,
      roles: routeBackedRoles,
      roleTest: {
        role_name: 'Analyst',
        status: 'failed',
        warnings: [],
        model_groups: [{
          canonical_id: 'gpt-5-4-mini',
          display_name: 'GPT 5.4 Mini',
          provider_results: routeIds.map((routeId, index) => ({
            route_id: routeId,
            provider_label: index === 0 ? 'OpenRouter' : 'OpenAI Official',
            provider_ui_state: 'ready',
            role_fit: 'using',
            admission_decision: 'admit',
            status: 'failed',
            warnings: [],
            retry_at: null,
            message: 'Network error.',
            resolved_settings: {},
          })),
        }],
      },
    })

    const roleCard = page.locator('[data-role-name="Analyst"]')
    await expect(roleCard.getByLabel('Provider status Connected')).toHaveCount(0)
    await expect(roleCard.locator('[data-role-route-status-light="true"][data-role-route-status="runnable"]')).toHaveCount(2)

    await roleCard.getByRole('button', { name: 'Test' }).click()

    await expect(roleCard.locator('[data-role-route-status-light="true"][data-role-route-status="blocked"]')).toHaveCount(2)
    await expect(roleCard.getByLabel('Provider status Failed')).toHaveCount(0)
    await expect(roleCard.getByLabel('Provider status Connected')).toHaveCount(0)
  })

  test('shows a lightweight pointer preview while dragging an available model group into a role', async ({ page }) => {
    const routeId = 'deepseek-official:deepseek-v4-flash'
    const registryWithModelGroup: typeof registry = {
      ...registry,
      provider_endpoints: {
        'deepseek-official': {
          endpoint_id: 'deepseek-official',
          display_name: 'DeepSeek Official',
          protocol: 'openai_compatible',
          base_url: 'https://api.deepseek.com',
          api_key: 'sk-deepseek',
          status: 'verified',
          last_test_at: '2026-05-24T00:00:00Z',
          last_test_message: 'Connected.',
          timeout_seconds: 120,
          trust_env: false,
          proxy_env: null,
          metadata: {},
        },
      },
      provider_routes: {
        [routeId]: {
          route_id: routeId,
          endpoint_id: 'deepseek-official',
          route_slug: 'deepseek-v4-flash',
          provider_model_id: 'deepseek-v4-flash',
          canonical_id: 'deepseek-v4-flash',
          display_name: 'DeepSeek V4 Flash',
          status: 'verified',
          capabilities: {},
          metadata: {},
        },
      },
      model_groups: [{
        canonical_id: 'deepseek-v4-flash',
        display_name: 'DeepSeek V4 Flash',
        section_label: 'deepseek',
        provider_models: [{
          route_id: routeId,
          endpoint_id: 'deepseek-official',
          provider_label: 'DeepSeek Official',
          provider_kind: 'official',
          provider_model_id: 'deepseek-v4-flash',
          ui_state: 'ready',
          ui_detail: null,
          retry_at: null,
          reason_code: null,
          capability_state: 'unknown',
          capabilities: {},
        }],
        status_summary: {
          ready: 1,
          untested: 0,
          cooling_down: 0,
          needs_setup: 0,
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
      }],
    }
    const emptyAnalystRoles: typeof roles = {
      ...roles,
      models: {},
      providers: {},
      roles: {
        Analyst: {
          model_fallback: true,
          active_model: '',
          models: {},
        },
      },
    }

    await openLlmRoles(page, { registry: registryWithModelGroup, roles: emptyAnalystRoles })

    const source = page.locator('[data-available-model-drag-source="true"][data-model-id="deepseek-v4-flash"]')
    const target = page.locator('[data-role-name="Analyst"] [data-model-drop-target="true"]')
    await expect(source).toBeVisible()
    await expect(target).toBeVisible()

    const sourceBox = await source.boundingBox()
    const targetBox = await target.boundingBox()
    if (!sourceBox || !targetBox) throw new Error('Drag source or target box unavailable.')

    await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(sourceBox.x + sourceBox.width / 2 - 20, sourceBox.y + sourceBox.height / 2 + 20, { steps: 2 })

    const preview = page.locator('[data-available-model-drag-preview="true"]')
    await expect(preview).toBeVisible()
    await expect(preview).toHaveAttribute('data-preview-update-mode', 'imperative-transform')
    await expect(preview).toContainText('DeepSeek V4 Flash')

    await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 6 })
    await page.mouse.up()

    const roleCard = page.locator('[data-role-name="Analyst"]')
    await expect(roleCard.getByText('DeepSeek V4 Flash')).toBeVisible()
    await expect(roleCard.getByText('DeepSeek Official')).toBeVisible()
    await expect(preview).toHaveCount(0)
  })

  test('maps rich route state into a single role route status in role cards', async ({ page }) => {
    const routeId = 'openrouter:gpt-5'
    const retryAt = '2026-12-31T00:00:00Z'
    const coolingRegistry: typeof registry = {
      ...registry,
      provider_endpoints: {
        openrouter: {
          endpoint_id: 'openrouter',
          display_name: 'OpenRouter',
          protocol: 'openai_compatible',
          base_url: 'https://openrouter.ai/api/v1',
          api_key: 'sk-openrouter',
          status: 'verified',
          last_test_at: '2026-05-24T00:00:00Z',
          last_test_message: 'Connected.',
          timeout_seconds: 120,
          trust_env: false,
          proxy_env: null,
          metadata: {},
        },
      },
      provider_routes: {
        [routeId]: {
          route_id: routeId,
          endpoint_id: 'openrouter',
          route_slug: 'gpt-5',
          provider_model_id: 'openai/gpt-5',
          canonical_id: 'gpt-5',
          display_name: 'GPT 5',
          status: 'verified',
          capabilities: {},
          metadata: {},
        },
      },
      model_groups: [{
        canonical_id: 'gpt-5',
        display_name: 'GPT 5',
        section_label: 'openai',
        provider_models: [{
          route_id: routeId,
          endpoint_id: 'openrouter',
          provider_label: 'OpenRouter',
          provider_kind: 'third_party',
          provider_model_id: 'openai/gpt-5',
          ui_state: 'cooling_down',
          ui_detail: 'Retry after transient rate limit.',
          retry_at: retryAt,
          reason_code: 'rate_limited',
          capability_state: 'partial',
          capabilities: {},
        }],
        status_summary: {
          ready: 0,
          untested: 0,
          cooling_down: 1,
          needs_setup: 0,
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
      }],
    }
    const coolingRoles: typeof roles = {
      ...roles,
      models: {
        'gpt-5': {
          name: 'GPT 5',
          providers: { [routeId]: 'openai/gpt-5' },
        },
      },
      providers: {
        [routeId]: {
          name: 'OpenRouter',
          type: 'openai_compatible',
          endpoint_id: 'openrouter',
        },
      },
      roles: {
        Analyst: {
          model_fallback: true,
          active_model: 'gpt-5',
          models: {
            'gpt-5': {
              providers: [routeId],
              temperature: null,
              max_tokens: null,
            },
          },
          materialization_report: {
            entries: [{
              canonical_id: 'gpt-5',
              route_id: routeId,
              role_fit: 'needs_test',
              warnings: [{ code: 'thinking_capability_unknown' }],
            }],
            warnings: [],
            skipped_provider_details: [],
          },
        },
      },
    }
    await openLlmRoles(page, { registry: coolingRegistry, roles: coolingRoles })

    const roleCard = page.locator('[data-role-name="Analyst"]')
    await expect(page.getByLabel('OpenRouter Cooling Down')).toBeVisible()
    const blockedLight = roleCard.locator('[data-role-route-status-light="true"][data-role-route-status="blocked"]')
    await expect(blockedLight).toBeVisible()
    await expect(roleCard.getByText('Blocked', { exact: true })).toHaveCount(0)
    await blockedLight.hover()
    await expect(page.getByText(
      'Blocked: Thinking is required but capability is unknown. Cooling Down: Retry after transient rate limit.',
    )).toBeVisible()
    await expect(roleCard.getByLabel('Provider state Cooling Down')).toHaveCount(0)
    await expect(roleCard.getByLabel('Role fit Needs Test')).toHaveCount(0)
    await expect(roleCard.getByRole('button', { name: 'Test Now' })).toHaveCount(0)
  })
})
