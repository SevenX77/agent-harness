import { expect, test, type Page, type Route } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

function fulfillJson(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function mockHomeApi(page: Page) {
  await page.route('**/api/settings', async (route) => {
    await fulfillJson(route, {
      user_id: 'default',
      gitea_host: 'http://127.0.0.1:3000',
      default_skills_directory: '/Users/sevenx/Projects',
    })
  })
  // Home no longer depends on GET /api/skills for the Recent list (MRU-only),
  // but other widgets may still poll it; keep it benign.
  await page.route('**/api/skills', async (route) => {
    await fulfillJson(route, [])
  })
}

/**
 * N1 Home · atom #9 (recent-load-failure-fallback) — REAL-MACHINE acceptance.
 *
 * Seeds a CORRUPT localStorage MRU blob so the real readRecentWorkspacesResult
 * read path fails (the same failure source as a path-validation error). Asserts
 * the design contract: a LOCAL red box renders in the Recent region AND the
 * New skill / Open folder entries stay present and clickable (不阻塞入口, D11).
 *
 * Written for the gatekeeper's real-machine pass; not run in the focused suite.
 */
test.describe('Home Recent load-failure fallback (atom #9)', () => {
  test('shows a local red box on MRU read failure without blocking New/Open', async ({ page }) => {
    test.setTimeout(20_000)
    await page.addInitScript(() => {
      // Corrupt blob → JSON.parse throws → readRecentWorkspacesResult surfaces
      // a non-null error instead of swallowing it into [].
      window.localStorage.setItem('recentWorkspaces', '{not valid json')
    })
    await mockHomeApi(page)

    await page.goto(`${baseURL}/#/`)

    // Local red error box (shadcn destructive Alert) is visible in the Recent
    // region.
    const errorBox = page.getByRole('alert').filter({ hasText: 'Could not load recent skills' })
    await expect(errorBox).toBeVisible()

    // 不阻塞入口: both top-level entries remain present AND clickable.
    const newSkill = page.getByRole('button', { name: 'New skill' })
    const openFolder = page.getByRole('button', { name: 'Open folder' })
    await expect(newSkill).toBeEnabled()
    await expect(openFolder).toBeEnabled()

    // The New skill entry actually opens its dialog — proving the entry is not
    // merely rendered but operable while the Recent error box is shown.
    await newSkill.click()
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('renders no error box when the MRU read succeeds', async ({ page }) => {
    test.setTimeout(20_000)
    await page.addInitScript(() => {
      window.localStorage.setItem('recentWorkspaces', '[]')
    })
    await mockHomeApi(page)

    await page.goto(`${baseURL}/#/`)

    await expect(page.getByRole('button', { name: 'New skill' })).toBeEnabled()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
})
