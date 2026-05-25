import { expect, test, type Page, type Route } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

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
    await fulfillJson(route, { providers: [] })
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

async function openApiKeys(page: Page) {
  await mockSettingsBackend(page)
  await page.goto(`${baseURL}/#/`)
  await page.getByRole('button', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'API Keys', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'API Keys' })).toBeVisible()
}

async function openLlmRoles(page: Page) {
  await mockSettingsBackend(page)
  await page.goto(`${baseURL}/#/`)
  await page.getByRole('button', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'LLM Roles', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'LLM Roles' })).toBeVisible()
}

test.describe('Native double-click guard', () => {
  async function observeNativeDoubleClickEvents(page: Page) {
    await page.evaluate(() => {
      type ObservedEvent = {
        defaultPrevented: boolean
        detail: number
        type: string
      }
      const events: ObservedEvent[] = []
      Object.assign(window, { __nativeDoubleClickEvents: events })
      document.addEventListener('mousedown', (event) => {
        if (event.detail >= 2) {
          events.push({
            defaultPrevented: event.defaultPrevented,
            detail: event.detail,
            type: event.type,
          })
        }
      }, true)
      document.addEventListener('dblclick', (event) => {
        events.push({
          defaultPrevented: event.defaultPrevented,
          detail: event.detail,
          type: event.type,
        })
      }, true)
    })
  }

  async function nativeDoubleClickEvents(page: Page) {
    return page.evaluate(() => (
      (window as unknown as { __nativeDoubleClickEvents: Array<{ defaultPrevented: boolean; detail: number; type: string }> })
        .__nativeDoubleClickEvents
    ))
  }

  async function dispatchCancelableEvent(page: Page, selector: string, eventType: string) {
    return page.locator(selector).first().evaluate((element, type) => {
      const event = new Event(type, { bubbles: true, cancelable: true })
      element.dispatchEvent(event)
      return event.defaultPrevented
    }, eventType)
  }

  test('prevents native double-click selection commands on non-editable settings chrome', async ({ page }) => {
    await openApiKeys(page)

    await observeNativeDoubleClickEvents(page)

    await page.getByRole('button', { name: 'Official Providers' }).dblclick()

    const events = await nativeDoubleClickEvents(page)
    expect(events.some((event) => event.type === 'mousedown' && event.detail >= 2 && event.defaultPrevented)).toBe(true)
    expect(events.some((event) => event.type === 'dblclick' && event.defaultPrevented)).toBe(true)
  })

  test('allows native double-click behavior inside editable fields', async ({ page }) => {
    await openApiKeys(page)
    await observeNativeDoubleClickEvents(page)

    await page.locator('input[name^="provider-secret-"]').first().dblclick()

    const events = await nativeDoubleClickEvents(page)
    expect(events.some((event) => event.type === 'mousedown' && event.detail >= 2 && event.defaultPrevented)).toBe(false)
    expect(events.some((event) => event.type === 'dblclick' && event.defaultPrevented)).toBe(false)
  })

  test('guards the same native double-click path on LLM Roles', async ({ page }) => {
    await openLlmRoles(page)
    await observeNativeDoubleClickEvents(page)

    await page.getByRole('button', { name: 'Graph Agent Roles' }).dblclick()

    const events = await nativeDoubleClickEvents(page)
    expect(events.some((event) => event.type === 'mousedown' && event.detail >= 2 && event.defaultPrevented)).toBe(true)
    expect(events.some((event) => event.type === 'dblclick' && event.defaultPrevented)).toBe(true)
  })

  test('prevents native selection start on non-editable chrome while preserving inputs', async ({ page }) => {
    await openApiKeys(page)

    await expect.poll(() => page.getByRole('heading', { name: 'API Keys' }).evaluate((element) => (
      getComputedStyle(element).userSelect
    ))).toBe('none')
    await expect.poll(() => page.locator('input[name^="provider-secret-"]').first().evaluate((element) => (
      getComputedStyle(element).userSelect
    ))).toBe('text')

    await expect(await page.getByRole('heading', { name: 'API Keys' }).evaluate((element) => {
      const event = new Event('selectstart', { bubbles: true, cancelable: true })
      element.dispatchEvent(event)
      return event.defaultPrevented
    })).toBe(true)
    await expect(await dispatchCancelableEvent(page, 'input[name^="provider-secret-"]', 'selectstart')).toBe(false)
  })
})
