import { expect, test } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173'

async function mockSkill(page: import('@playwright/test').Page) {
  await page.route('**/api/skills/smoke', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        manifest: {
          schema_version: '2.0',
          type: 'graph',
          name: 'Smoke Skill',
          description: 'Predict smoke skill',
          license: null,
          version: null,
          author: null,
          metadata: null,
          context_mapping: {},
          io: {
            inputs: [{ name: 'topic', source: 'runtime', type: 'string', default: '', required: true }],
            outputs: [{ name: 'summary', target: 'artifact', type: 'string', path: null }],
          },
          phases: [],
        },
        file_paths: {},
        has_golden: false,
        latest_run_metadata: null,
        lint_result: null,
      }),
    })
  })
}

test.describe('Predict workflow smoke', () => {
  test('locks predict when compile has not passed', async ({ page }) => {
    await mockSkill(page)
    await page.goto(`${baseURL}/#/skill/smoke/predict`)
    await expect(page.getByText('Predict is locked')).toBeVisible()
    await expect(page.getByRole('button', { name: /new predict/i })).toBeDisabled()
  })

  test('shows schema invalid from validate_input', async ({ page }) => {
    await page.addInitScript(() => {
      window.sessionStorage.setItem('studio-lint-status-smoke', 'passed')
    })
    await mockSkill(page)
    await page.route('**/api/skills/smoke/validate_input', async (route) => {
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          error_code: 'INPUT_VALIDATION_FAILED',
          http_status: 422,
          message: 'Input schema invalid',
          details: null,
          retry_strategy: 'not_retryable',
        }),
      })
    })

    await page.goto(`${baseURL}/#/skill/smoke/predict`)
    await page.getByRole('button', { name: /new predict/i }).click()
    await page.getByRole('button', { name: /validate input/i }).click()
    await expect(page.getByText('Input schema invalid')).toBeVisible()
  })

  test('runs real predict path, shows read-only golden references, and renders dark mode', async ({ page }) => {
    await page.addInitScript(() => {
      window.sessionStorage.setItem('studio-lint-status-smoke', 'passed')
    })
    await mockSkill(page)
    await page.route('**/api/skills/smoke/validate_input', async (route) => {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'valid' }) })
    })
    await page.route('**/api/skills/smoke/runs/predict', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 250))
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          run_id: 'predict-run-1',
          status: 'success',
          final_context: { summary: 'real predict output' },
          artifacts: [],
        }),
      })
    })
    await page.route('**/api/skills/smoke/golden', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([{
          id: 'predict-run-1',
          linked_input_id: 'predict-run-1',
          created_at: '2026-05-11T00:00:00Z',
          locked: false,
          content_path: '/tmp/golden/final_state.json',
        }]),
      })
    })

    await page.goto(`${baseURL}/#/skill/smoke/predict`)
    await page.locator('html').evaluate((node) => node.classList.add('dark'))
    await expect(page.locator('html')).toHaveClass(/dark/)

    await page.getByRole('button', { name: /new predict/i }).click()
    await page.getByRole('button', { name: /validate input/i }).click()
    await expect(page.getByRole('button', { name: /predicting/i })).toBeVisible()
    await expect(page.getByText('real predict output')).toBeVisible()
    await expect(page.getByText('Golden baselines')).toBeVisible()
    await expect(page.getByText('/tmp/golden/final_state.json')).toBeVisible()
    await expect(page.getByRole('button', { name: /save as golden/i })).toHaveCount(0)
  })
})
