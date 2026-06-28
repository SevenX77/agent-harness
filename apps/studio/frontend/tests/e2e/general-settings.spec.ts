import { expect, test, type Page, type Route } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

interface AppSettings {
  user_id: string
  gitea_host: string
  default_skills_directory: string
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
}

function mockNonSettingsBackend(page: Page) {
  return Promise.all([
    page.route('**/api/skills', (route) => fulfillJson(route, [])),
    page.route('**/api/llm/credentials**', (route) => fulfillJson(route, { providers: [] })),
    page.route('**/api/llm/registry', (route) =>
      fulfillJson(route, {
        provider_endpoints: {},
        provider_routes: {},
        runtime_policy: { provider_down_ttl_seconds: 60, probe_timeout_seconds: 5, token_escalation_rounds: 2 },
        model_profiles: {},
        model_groups: [],
        roles: {},
        canonical_groups: [],
        lint_results: [],
        setup_required: false,
      }),
    ),
    page.route('**/api/llm/roles**', (route) =>
      fulfillJson(route, {
        models: {},
        providers: {},
        roles: {},
        single_model_roles: [],
        peer_model_groups: {},
        circuit_breaker: null,
      }),
    ),
  ])
}

/**
 * Backend stub with a mutable app_settings store so that GET reflects prior
 * PUTs (proves persistence across reload). `putCount` lets a test assert the
 * 300ms debounce merges rapid edits into a single PUT.
 */
async function mockSettingsBackend(page: Page, initial: AppSettings) {
  const state = { saved: { ...initial }, putCount: 0 }
  await page.route('**/api/settings', async (route) => {
    const request = route.request()
    if (request.method() === 'PUT') {
      state.putCount += 1
      state.saved = JSON.parse(request.postData() ?? '{}') as AppSettings
      await fulfillJson(route, state.saved)
      return
    }
    await fulfillJson(route, state.saved)
  })
  return state
}

async function openGeneralSettings(page: Page) {
  // about:blank first forces a real cross-document load every call, so a second
  // call in a test (the reload scenario) genuinely re-boots the app rather than
  // a no-op hash change. Persisted state lives server-side in the route mock.
  await page.goto('about:blank')
  await page.goto(`${baseURL}/#/`)
  await expect(page.getByRole('heading', { name: 'GSkill Studio' })).toBeVisible()
  await page.getByRole('button', { name: 'Settings' }).click()
  await expect(page.getByRole('button', { name: 'General' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Studio User ID' })).toBeVisible()
}

test.describe('General settings — identity & output paths', () => {
  test('#10/#15 editing the Studio User ID auto-saves the full 3-field PUT and shows Saved', async ({ page }) => {
    await mockNonSettingsBackend(page)
    const state = await mockSettingsBackend(page, {
      user_id: 'e2e-user',
      gitea_host: 'https://gitea.example',
      default_skills_directory: '/tmp/skills',
    })
    await openGeneralSettings(page)

    const putRequest = page.waitForRequest(
      (request) => request.url().includes('/api/settings') && request.method() === 'PUT',
    )
    const userId = page.getByRole('textbox', { name: 'Studio User ID' })
    await userId.fill('renamed-user')

    const body = JSON.parse((await putRequest).postData() ?? '{}') as AppSettings
    expect(body.user_id).toBe('renamed-user')
    // whole-object PUT, no field-level PATCH: all three fields are always present
    expect(body).toHaveProperty('gitea_host')
    expect(body).toHaveProperty('default_skills_directory')

    await expect(page.locator('[data-save-status="saved"]')).toBeVisible()
    expect(state.saved.user_id).toBe('renamed-user')
    await page.screenshot({ path: 'test-results/general-saved.png' })
  })

  test('#10 persisted User ID is restored after reload', async ({ page }) => {
    await mockNonSettingsBackend(page)
    await mockSettingsBackend(page, {
      user_id: 'e2e-user',
      gitea_host: 'https://gitea.example',
      default_skills_directory: '/tmp/skills',
    })
    await openGeneralSettings(page)

    await page.getByRole('textbox', { name: 'Studio User ID' }).fill('persist-me')
    await expect(page.locator('[data-save-status="saved"]')).toBeVisible()

    await openGeneralSettings(page)
    await expect(page.getByRole('textbox', { name: 'Studio User ID' })).toHaveValue('persist-me')
  })

  test('#15 rapid edits within the debounce window collapse into a single PUT', async ({ page }) => {
    await mockNonSettingsBackend(page)
    const state = await mockSettingsBackend(page, {
      user_id: '',
      gitea_host: '',
      default_skills_directory: '/tmp/skills',
    })
    await openGeneralSettings(page)

    const userId = page.getByRole('textbox', { name: 'Studio User ID' })
    await userId.focus()
    await userId.pressSequentially('abcd', { delay: 40 }) // 4 onChange events well within 300ms

    await page.waitForRequest((r) => r.url().includes('/api/settings') && r.method() === 'PUT')
    await page.waitForTimeout(400)
    expect(state.putCount).toBe(1)
    expect(state.saved.user_id).toBe('abcd')
  })

  test('#12 editing the default skill folder auto-saves default_skills_directory', async ({ page }) => {
    await mockNonSettingsBackend(page)
    const state = await mockSettingsBackend(page, {
      user_id: 'e2e-user',
      gitea_host: '',
      default_skills_directory: '/tmp/skills',
    })
    await openGeneralSettings(page)

    const putRequest = page.waitForRequest(
      (request) => request.url().includes('/api/settings') && request.method() === 'PUT',
    )
    await page.getByRole('textbox', { name: 'Default skill folder' }).fill('/tmp/typed-skills')

    const body = JSON.parse((await putRequest).postData() ?? '{}') as AppSettings
    expect(body.default_skills_directory).toBe('/tmp/typed-skills')
    await expect(page.locator('[data-save-status="saved"]')).toBeVisible()
    expect(state.saved.default_skills_directory).toBe('/tmp/typed-skills')
  })

  test('#15 an edit during an in-flight save is buffered and re-fired in order (no lost update)', async ({ page }) => {
    await mockNonSettingsBackend(page)
    const state = { saved: { user_id: '', gitea_host: '', default_skills_directory: '/tmp/skills' } as AppSettings, putCount: 0 }
    await page.route('**/api/settings', async (route) => {
      const request = route.request()
      if (request.method() === 'PUT') {
        state.putCount += 1
        const isFirst = state.putCount === 1
        state.saved = JSON.parse(request.postData() ?? '{}') as AppSettings
        if (isFirst) await new Promise((resolve) => setTimeout(resolve, 800)) // hold PUT#1 in-flight
        await fulfillJson(route, state.saved)
        return
      }
      await fulfillJson(route, state.saved)
    })
    await openGeneralSettings(page)

    // First edit → debounced PUT#1 starts and is held in-flight by the mock.
    await page.getByRole('textbox', { name: 'Studio User ID' }).fill('first')
    await page.waitForRequest((r) => r.url().includes('/api/settings') && r.method() === 'PUT')
    // Second edit while PUT#1 is in-flight → buffered into pendingSettings, re-fired after PUT#1 resolves.
    await page.getByRole('textbox', { name: 'Gitea Host' }).fill('https://second-host.example')

    await expect.poll(() => state.putCount, { timeout: 5000 }).toBe(2)
    // The buffered PUT#2 carries the merged latest state — neither edit is lost.
    expect(state.saved.user_id).toBe('first')
    expect(state.saved.gitea_host).toBe('https://second-host.example')
  })

  test('#13 Choose in web mode toasts "Desktop only" and does not save', async ({ page }) => {
    await mockNonSettingsBackend(page)
    const state = await mockSettingsBackend(page, {
      user_id: 'e2e-user',
      gitea_host: '',
      default_skills_directory: '/tmp/skills',
    })
    await openGeneralSettings(page)

    await page.getByRole('button', { name: 'Choose' }).click()
    await expect(page.getByText('Desktop only')).toBeVisible()
    await page.waitForTimeout(400)
    expect(state.putCount).toBe(0)
  })

  test('#15 a failing save surfaces an explicit error badge + toast (no silent failure)', async ({ page }) => {
    await mockNonSettingsBackend(page)
    await page.route('**/api/settings', async (route) => {
      if (route.request().method() === 'PUT') {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error_code: 'SETTINGS_WRITE_FAILED', message: 'boom' }),
        })
        return
      }
      await fulfillJson(route, { user_id: 'e2e-user', gitea_host: '', default_skills_directory: '/tmp/skills' })
    })
    await openGeneralSettings(page)

    await page.getByRole('textbox', { name: 'Studio User ID' }).fill('will-fail')
    await expect(page.locator('[data-save-status="error"]')).toBeVisible()
    await expect(page.getByText(/Settings save failed/i)).toBeVisible()
  })
})
