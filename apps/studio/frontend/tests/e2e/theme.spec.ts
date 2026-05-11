import { expect, test } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

async function mockSkills(page: import('@playwright/test').Page) {
  await page.route('**/api/skills', async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify([]) })
  })
}

test.describe('Theme synchronization smoke', () => {
  test('persists explicit theme and follows OS theme without a stored preference', async ({ page }) => {
    await mockSkills(page)
    await page.addInitScript(() => {
      window.localStorage.setItem('theme', 'dark')
    })
    await page.goto(`${baseURL}/#/`)
    await expect(page.locator('html')).toHaveClass(/dark/)

    await page.evaluate(() => {
      window.localStorage.setItem('theme', 'light')
      window.dispatchEvent(new StorageEvent('storage', { key: 'theme', newValue: 'light' }))
    })
    await expect(page.locator('html')).toHaveClass(/light/)

    await page.evaluate(() => {
      window.localStorage.removeItem('theme')
      window.dispatchEvent(new StorageEvent('storage', { key: 'theme', newValue: null }))
    })
    await page.emulateMedia({ colorScheme: 'dark' })
    await expect(page.locator('html')).toHaveClass(/dark/)
    await page.emulateMedia({ colorScheme: 'light' })
    await expect(page.locator('html')).toHaveClass(/light/)
  })
})
